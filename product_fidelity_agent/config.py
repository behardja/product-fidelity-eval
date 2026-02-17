import os

# --- GCP Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "cpg-cdp")
LOCATION = os.environ.get("LOCATION", "us-central1")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "sandbox-401718-product-fidelity-eval")

# --- Model IDs ---
DESCRIPTION_MODEL = "gemini-3-pro-preview"
IMAGE_GEN_MODEL = "gemini-3-pro-image-preview"
AGENT_MODEL = "gemini-3-pro-preview"  # For LlmAgent orchestration/tool-calling

# --- Video Generation ---
VIDEO_GEN_MODEL = "veo-3.1-generate-preview"
VIDEO_ASPECT_RATIO = "16:9"
VIDEO_GENERATE_AUDIO = False
VIDEO_DURATION_SECONDS = 4
VIDEO_NUMBER_OF_VIDEOS = 1
VIDEO_MAX_RETRIES = 3  # configurable retry count for video refinement loop

# --- Evaluation Thresholds ---
PASSING_THRESHOLD = 0.7
MAX_RETRIES = 3
