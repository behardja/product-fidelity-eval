import os

# --- GCP Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "cpg-cdp")
LOCATION = os.environ.get("LOCATION", "us-central1")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "sandbox-401718-product-fidelity-eval")

# --- Model IDs ---
DESCRIPTION_MODEL = "gemini-3-pro-preview"
IMAGE_GEN_MODEL = "gemini-3-pro-image-preview"
AGENT_MODEL = "gemini-3-pro-preview"  # For LlmAgent orchestration/tool-calling

# --- Evaluation Thresholds ---
PASSING_THRESHOLD = 0.7
MAX_RETRIES = 3
