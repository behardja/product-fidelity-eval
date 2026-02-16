import os
import time
from io import BytesIO

from fastapi import Query, Response
from fastapi.responses import FileResponse
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import storage
from PIL import Image

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
