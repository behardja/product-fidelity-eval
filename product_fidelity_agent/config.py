import os

from google.adk.models.google_llm import Gemini
from google.genai import types

# --- GCP Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "sandbox-401718")
LOCATION = os.environ.get("LOCATION", "us-central1")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "sandbox-401718-product-fidelity-evals")

# --- Model IDs ---
DESCRIPTION_MODEL = "gemini-3-pro-preview"
IMAGE_GEN_MODEL = "gemini-3-pro-image-preview"

# Agent orchestration model — uses Gemini instance so ADK's internal LLM
# calls retry on 429/5xx instead of failing immediately.
AGENT_MODEL = Gemini(
    model="gemini-3-pro-preview",
    retry_options=types.HttpRetryOptions(
        attempts=5,
        initial_delay=2.0,
        jitter=1.0,
        max_delay=20.0,
        http_status_codes=[408, 429, 500, 502, 503, 504],
    ),
)

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
