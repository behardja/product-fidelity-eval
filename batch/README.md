# Batch Pipeline

Automated Batch Pipeline that processes multiple product images through the describe-generate-evaluate
pipeline. Designed for scalable, bulk generation & evaluation for scalable evaluation of product images while the Agent is intended for interactive HITL iteration and interaction.

## Overview

The batch pipeline takes a set of product images and for each one:

1. Generates a ground-truth description of the product
2. Generates a recontextualized candidate image
3. Evaluates the candidate against the description using Gecko
4. If the score is below threshold, refines the description and retries (up to 3 attempts)

Up to 5 images are processed in parallel. Progress is streamed to the
front-end in real time, and a summary HTML report is generated at the end.

## Relationship to Agent Tools

- **`product_fidelity_agent/tools/`** — The batch pipeline reuses the same
  Gemini, image generation, Gecko evaluation, and GCS functions defined in the
  agent's tools folder. It wraps them with thin adapters to pass arguments
  directly rather than through the agent's `ToolContext` state.

- **`product_fidelity_agent/prompts/`** — The same prompt templates used by
  the agent for description generation are loaded and used by the batch pipeline.

- **`product_fidelity_agent/config.py`** — Model names, project settings,
  thresholds, and retry limits are all imported from the shared config.

- **`server.py`** — The FastAPI server imports `run_batch` from this package
  and exposes it through the `/api/batch/*` endpoints.
