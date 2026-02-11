import base64

from google.cloud import storage


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


def image_to_base64(gcs_uri: str) -> tuple[str | None, str | None]:
    """Load an image from GCS and return (base64_data, mime_type).

    Returns (None, None) if the image cannot be loaded.
    """
    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    ext = gcs_uri.lower().rsplit(".", 1)[-1]
    mime_type = mime_map.get(ext, "image/png")

    try:
        image_bytes = read_from_gcs(gcs_uri)
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        return b64_data, mime_type
    except Exception as e:
        print(f"Warning: Could not load image {gcs_uri}: {e}")
        return None, None
