import base64
from io import BytesIO

from google.cloud import storage
from PIL import Image


def read_from_gcs(gcs_uri: str) -> bytes:
    """Read a file from GCS and return its bytes."""
    path = gcs_uri[5:]  # Remove 'gs://'
    bucket_name = path.split("/")[0]
    blob_path = "/".join(path.split("/")[1:])

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    return blob.download_as_bytes()


def write_to_gcs(data: bytes, gcs_uri: str) -> str:
    """Write bytes to a GCS URI. Returns the URI."""
    path = gcs_uri[5:]
    bucket_name = path.split("/")[0]
    blob_path = "/".join(path.split("/")[1:])

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(data)
    return gcs_uri


def image_to_base64(
    gcs_uri: str, max_width: int = 600, quality: int = 70
) -> tuple[str | None, str | None]:
    """Load an image from GCS, resize, and return (base64_data, mime_type).

    Resizes to max_width (preserving aspect ratio) and compresses to JPEG
    to prevent token bloat when injected into chat.

    Returns (None, None) if the image cannot be loaded.
    """
    try:
        image_bytes = read_from_gcs(gcs_uri)
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        img = img.resize((max_width, int(img.height * (max_width / img.width))))
        buffer = BytesIO()
        img.save(buffer, "JPEG", quality=quality)
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return b64_data, "image/jpeg"
    except Exception as e:
        print(f"Warning: Could not load image {gcs_uri}: {e}")
        return None, None
