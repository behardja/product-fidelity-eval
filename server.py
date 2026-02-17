import asyncio
import json
import os
import time
from io import BytesIO
from pathlib import Path

# Load .env before any imports that read config
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

from fastapi import Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import storage
from PIL import Image
from pydantic import BaseModel

from batch.pipeline import run_batch

# ---------------------------------------------------------------------------
# ADK app
# ---------------------------------------------------------------------------

app = get_fast_api_app(
    agents_dir="./product_fidelity_agent",
    web=False,
    allow_origins=["http://localhost:3000"],
)

# ---------------------------------------------------------------------------
# GCS proxy helpers
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
CACHE_TTL = 300  # 5 minutes

_gcs_list_cache: dict[str, tuple[float, list[str]]] = {}


def _get_storage_client() -> storage.Client:
    return storage.Client()


def _list_images_cached(prefix: str) -> list[str]:
    """Return all image blob URIs under *prefix*, with a TTL cache."""
    now = time.time()
    if prefix in _gcs_list_cache:
        ts, images = _gcs_list_cache[prefix]
        if now - ts < CACHE_TTL:
            return images

    # prefix arrives without gs:// — e.g. "bucket/path/to/images/"
    parts = prefix.split("/", 1)
    bucket_name = parts[0]
    blob_prefix = parts[1] if len(parts) > 1 else ""

    client = _get_storage_client()
    blobs = client.list_blobs(bucket_name, prefix=blob_prefix)
    images = [
        f"gs://{bucket_name}/{b.name}"
        for b in blobs
        if b.name.lower().endswith(IMAGE_EXTENSIONS)
    ]
    _gcs_list_cache[prefix] = (now, images)
    return images


# ---------------------------------------------------------------------------
# GCS proxy endpoints
# ---------------------------------------------------------------------------


@app.get("/api/gcs/list")
def gcs_list(
    prefix: str = Query(..., description="GCS path without gs://"),
    page: int = Query(0, ge=0),
    page_size: int = Query(20, ge=1, le=100),
):
    images = _list_images_cached(prefix)
    total = len(images)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = page * page_size
    end = start + page_size
    return {
        "images": images[start:end],
        "total": total,
        "page": page,
        "total_pages": total_pages,
    }


@app.get("/api/gcs/thumbnail")
def gcs_thumbnail(
    uri: str = Query(..., description="Full gs:// URI"),
):
    path = uri[5:]  # strip "gs://"
    bucket_name = path.split("/")[0]
    blob_path = "/".join(path.split("/")[1:])

    client = _get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    raw_bytes = blob.download_as_bytes()

    img = Image.open(BytesIO(raw_bytes)).convert("RGB")
    max_width = 300
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)))

    buf = BytesIO()
    img.save(buf, "JPEG", quality=60)
    return Response(content=buf.getvalue(), media_type="image/jpeg")


# ---------------------------------------------------------------------------
# Report endpoint
# ---------------------------------------------------------------------------

REPORT_FILE = "product_candidate_report.html"


@app.get("/api/report")
def get_report():
    if not os.path.isfile(REPORT_FILE):
        return Response(content="No report generated yet.", status_code=404)
    return FileResponse(REPORT_FILE, media_type="text/html")


# ---------------------------------------------------------------------------
# Batch endpoints
# ---------------------------------------------------------------------------


class BatchStartRequest(BaseModel):
    prefix: str = ""
    image_uris: list[str] = []
    run_all: bool = False


# In-memory batch state (single batch at a time)
_batch_state: dict | None = None


@app.post("/api/batch/start")
async def batch_start(body: BatchStartRequest):
    global _batch_state

    if _batch_state and not _batch_state["task"].done():
        return Response(
            content=json.dumps({"error": "A batch is already running."}),
            status_code=409,
            media_type="application/json",
        )

    # Resolve image URIs
    if body.run_all and body.prefix:
        clean_prefix = body.prefix
        if clean_prefix.startswith("gs://"):
            clean_prefix = clean_prefix[5:]
        uris = _list_images_cached(clean_prefix)
    elif body.image_uris:
        uris = body.image_uris
    else:
        return Response(
            content=json.dumps({"error": "No images specified."}),
            status_code=400,
            media_type="application/json",
        )

    if not uris:
        return Response(
            content=json.dumps({"error": "No images found."}),
            status_code=400,
            media_type="application/json",
        )

    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_batch(uris, queue))

    _batch_state = {
        "task": task,
        "queue": queue,
        "results": None,
        "status": "running",
        "image_count": len(uris),
    }

    # Store results when task completes
    async def _store_results():
        try:
            results = await task
            _batch_state["results"] = results
            _batch_state["status"] = "complete"
        except asyncio.CancelledError:
            _batch_state["status"] = "cancelled"
        except Exception as e:
            _batch_state["status"] = "error"
            _batch_state["error"] = str(e)

    asyncio.create_task(_store_results())

    return {"batch_id": "current", "image_count": len(uris)}


@app.get("/api/batch/status")
async def batch_status():
    if not _batch_state:
        return Response(
            content=json.dumps({"error": "No batch running."}),
            status_code=404,
            media_type="application/json",
        )

    async def event_stream():
        queue = _batch_state["queue"]
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("status") == "complete":
                    break
            except asyncio.TimeoutError:
                # Send keepalive
                yield f"data: {json.dumps({'status': 'keepalive'})}\n\n"
            except Exception:
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


BATCH_REPORT_FILE = "batch_report.html"


@app.get("/api/batch/report")
def batch_report():
    if not os.path.isfile(BATCH_REPORT_FILE):
        return Response(content="No batch report generated yet.", status_code=404)
    return FileResponse(BATCH_REPORT_FILE, media_type="text/html")


@app.post("/api/batch/cancel")
async def batch_cancel():
    global _batch_state

    if not _batch_state or _batch_state["task"].done():
        return Response(
            content=json.dumps({"error": "No batch running."}),
            status_code=404,
            media_type="application/json",
        )

    _batch_state["task"].cancel()
    _batch_state["status"] = "cancelled"
    return {"status": "cancelled"}
