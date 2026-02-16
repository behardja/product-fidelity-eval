# Batch Pipeline

Automated pipeline that processes multiple product images through the describe-generate-evaluate
loop. Designed for scalable, bulk evaluation while the agent is intended for interactive HITL iteration.

## Overview

The batch pipeline takes a set of product images and for each one:

1. Generates a ground-truth description of the product using Gemini
2. Generates a recontextualized candidate image
3. Evaluates the candidate against the description using Gecko `TEXT2IMAGE`
4. If the score is below threshold, refines the description and retries (up to 3 attempts)

Up to 5 images are processed in parallel (controlled by `asyncio.Semaphore`). Progress is streamed to the
front-end in real time via SSE, and a summary HTML report (`batch_report.html`) is generated at the end.

## API Endpoints

The batch pipeline is exposed through `server.py` at the following endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/api/batch/start` | POST | Starts a batch run. Accepts `{ prefix, image_uris, run_all }` |
| `/api/batch/status` | GET | SSE stream of per-image progress events (`running`, `passed`, `failed`, `error`) |
| `/api/batch/report` | GET | Serves the generated HTML report |
| `/api/batch/cancel` | POST | Cancels a running batch |

Only one batch can run at a time. Starting a new batch while one is running returns `409 Conflict`.

## Usage

The batch pipeline is typically invoked through the front-end's Batch Mode, but can also be triggered directly:

```bash
curl -X POST http://localhost:8000/api/batch/start \
  -H "Content-Type: application/json" \
  -d '{"prefix": "gs://your-bucket/product-images/", "run_all": true}'
```

Or with specific images:

```bash
curl -X POST http://localhost:8000/api/batch/start \
  -H "Content-Type: application/json" \
  -d '{"image_uris": ["gs://your-bucket/product-a.png", "gs://your-bucket/product-b.png"]}'
```

## Relationship to Agent Tools

- **`product_fidelity_agent/tools/`** — The batch pipeline reuses the same
  Gemini, image generation, Gecko evaluation, and GCS functions defined in the
  agent's tools folder. It wraps them with thin async adapters to pass arguments
  directly rather than through the agent's `ToolContext` state.

- **`product_fidelity_agent/prompts/`** — The same prompt templates used by
  the agent for description generation are loaded and used by the batch pipeline.

- **`product_fidelity_agent/config.py`** — Model names, project settings,
  thresholds, and retry limits are all imported from the shared config.

- **`server.py`** — The FastAPI server imports `run_batch` from this package
  and exposes it through the `/api/batch/*` endpoints.

## Folder Structure

```
batch/
├── __init__.py     # Package init
└── pipeline.py     # Async batch orchestrator, per-image pipeline, HTML report generation
```
