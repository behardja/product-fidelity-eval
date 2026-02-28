"""User-editable settings for the evaluation wrapper.

Edit the values below to match your GCP project and preferences.
Environment variables take precedence if set.
"""

import os

# --- GCP Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "sandbox-401718")
LOCATION = os.environ.get("LOCATION", "us-central1")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "sandbox-401718-product-fidelity-evals")

# --- Model IDs ---
DESCRIPTION_MODEL = "gemini-2.5-pro"
AGENT_MODEL = "gemini-2.5-pro"  # Used by ADK-native wrapper for orchestration agents

# --- Evaluation Thresholds ---
PASSING_THRESHOLD = 0.7
MAX_RETRIES = 3

# --- Media Type ---
MEDIA_TYPE = "image"  # "image" or "video"
