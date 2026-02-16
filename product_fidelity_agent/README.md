# Product Fidelity Eval — Multi-Agent System

A Google ADK agent pipeline that evaluates whether AI-generated product images and videos faithfully reproduce an original product. It generates a ground-truth text description from reference images, uses that description to generate candidate images (or videos), scores them with Gecko, and iteratively refines the description until the fidelity threshold is met or retries are exhausted.

## Agent Architecture

```
root_agent (SequentialAgent: ProductFidelityPipeline)
│
├── 1. InputAgent (LlmAgent)
│      Parses the user's request to extract GCS image URIs and SKU ID.
│      Initializes pipeline state.
│
├── 2. DescriptionAgent (LlmAgent)
│      Calls Gemini (gemini-3-pro-preview) with the reference product images
│      to generate a ground-truth text description.
│
├── 3. RefinementLoop (LoopAgent, max_iterations=3)
│   │
│   ├── ImageGenAgent (LlmAgent)
│   │     Generates a candidate product image using gemini-3-pro-image-preview.
│   │     On the first attempt, uses a generic recontextualization prompt.
│   │     On retries, augments the prompt with the refined description and
│   │     failing verdicts from the previous evaluation. Saves to GCS.
│   │
│   ├── EvaluationAgent (LlmAgent)
│   │     Runs Gecko text-to-image evaluation against the ground-truth
│   │     description, then calls the deterministic check_threshold tool:
│   │       • score >= 0.7  → escalate (exit loop, PASS)
│   │       • attempt >= 3  → escalate (exit loop, FAIL → HITL review)
│   │       • otherwise     → returns "retry"
│   │
│   └── RefinementAgent (LlmAgent)
│         Only reached on "retry". Calls Gemini to rewrite the description,
│         emphasizing the specific attributes that failed their rubric checks.
│         Always derives from the original description to prevent drift.
│
└── 4. ReportAgent (LlmAgent)
       Generates an HTML report with embedded source/candidate images,
       per-attempt scores, and individual rubric verdicts.
```

## Folder Structure

```
product_fidelity_agent/
├── __init__.py               # Exports root_agent
├── agent.py                  # Root SequentialAgent + LoopAgent wiring, InputAgent
├── callbacks.py              # inject_generated_image, cleanup_image_data
├── config.py                 # GCP project, model IDs, threshold (0.7), max retries (3)
├── agents/
│   ├── description_agent.py  # Ground-truth description generation
│   ├── image_gen_agent.py    # Candidate image generation
│   ├── evaluation_agent.py   # Gecko TEXT2IMAGE scoring + threshold check
│   ├── video_gen_agent.py    # Candidate video generation (Veo)
│   ├── video_evaluation_agent.py  # Gecko TEXT2VIDEO scoring + threshold check
│   ├── refinement_agent.py   # Description refinement on retry
│   └── report_agent.py       # HTML report generation
├── tools/
│   ├── gcs.py                # read_from_gcs, write_to_gcs, image_to_base64
│   ├── gemini.py             # generate_description, refine_description
│   ├── image_gen.py          # generate_product_image
│   ├── gecko.py              # run_gecko_evaluation, run_gecko_video_evaluation, check_threshold
│   ├── video_gen.py          # generate_product_video (Veo API)
│   └── reporting.py          # create_html_report
└── prompts/
    ├── description_system.txt
    └── description_user.txt
```

## State Flow

All data passes between agents via `tool_context.state`. Key state variables:

| Key | Set by | Used by |
|---|---|---|
| `image_uris` | InputAgent | DescriptionAgent |
| `sku_id` | InputAgent | ImageGenAgent, ReportAgent |
| `ground_truth_description` | DescriptionAgent | EvaluationAgent, RefinementAgent |
| `current_description` | DescriptionAgent / RefinementAgent | ImageGenAgent |
| `candidate_image_uri` | ImageGenAgent | EvaluationAgent |
| `gecko_score` | EvaluationAgent | ReportAgent |
| `failing_verdicts_text` | EvaluationAgent | RefinementAgent, ImageGenAgent (retries only) |
| `evaluation_history` | EvaluationAgent (appended each attempt) | ReportAgent |
| `evaluation_passed` | check_threshold | ReportAgent |
| `attempt` | InputAgent / RefinementAgent | ImageGenAgent, check_threshold |
| `candidate_video_uri` | VideoGenAgent | VideoEvaluationAgent |

## Video Pipeline

The video pipeline follows the same architecture as the image pipeline but swaps in video-specific agents:

- **`VideoGenAgent`** — Generates a candidate product video using the Veo API (`veo-3.1-generate-preview`) with the reference product image as an asset reference. Configured via `VIDEO_ASPECT_RATIO`, `VIDEO_DURATION_SECONDS`, and other constants in `config.py`.
- **`VideoEvaluationAgent`** — Runs Gecko `TEXT2VIDEO` evaluation against the ground-truth description and calls the same `check_threshold` tool for the pass/retry/fail decision.

## Key Design Decisions

**Deterministic threshold** — The pass/retry/fail decision is a float comparison inside `check_threshold`, not an LLM call. It sets `tool_context.actions.escalate = True` to exit the LoopAgent directly.

**Drift prevention** — `refine_description` always takes `(original_description, failing_verdicts)` as input, never the previous refinement. The original description is stored separately and treated as immutable.

**Reinforcement, not removal** — Refinement strengthens emphasis on failing attributes rather than removing them, so score improvements reflect genuine fidelity gains.

**Prompts as files** — The system instruction and user prompt (~400+ words each) live in `prompts/` as plain text files to separate prompt engineering from code.

## Prerequisites

### GCP APIs

The following APIs must be enabled on your project:

- **Vertex AI API** (`aiplatform.googleapis.com`)
- **Cloud Storage API** (`storage.googleapis.com`)

### GCS bucket structure

The pipeline reads reference images from and writes generated images to a single GCS bucket. The bucket must exist before running the agent, and reference images must be uploaded to the bucket root (or any path — the full `gs://` URI is passed at runtime).

Generated images are written automatically by the pipeline under a `generated/` prefix:

```
gs://<BUCKET_NAME>/
├── <reference_image_1>.png        # You upload these (input)
├── <reference_image_2>.png
├── ...
└── generated/                     # Created automatically by the pipeline (output)
    └── <sku_id>/
        ├── attempt_1_<uuid>.png
        ├── attempt_2_<uuid>.png
        └── ...
```

- **Reference images** — upload product photos (PNG, JPG, WEBP) to the bucket before running. These are the source-of-truth images that Gemini analyzes to produce the ground-truth description. Pass their full `gs://` URIs in the user prompt.
- **`generated/{sku_id}/`** — created at runtime by `generate_product_image`. Each attempt gets a unique filename with the attempt number and a short UUID.
- **HTML report** — written to the local filesystem as `gecko_report_{sku_id}.html`, not to GCS.

### Authentication

The pipeline uses Application Default Credentials. Ensure your environment is authenticated:

```bash
gcloud auth application-default login
```

The authenticated principal needs these IAM roles (or equivalent):

- `roles/storage.objectAdmin` on the bucket (read reference images, write generated images)
- `roles/aiplatform.user` on the project (Gemini API, Vertex AI Evals / Gecko)

### Python dependencies

```
google-adk
google-genai
google-cloud-storage
vertexai
pandas
Pillow
```

## Configuration

Set via environment variables or edit the defaults in `config.py`. **You must update `PROJECT_ID` and `BUCKET_NAME` to match your own GCP environment:**

| Variable | Default | Description |
|---|---|---|
| `PROJECT_ID` | `cpg-cdp` | **Set to your GCP project ID** |
| `LOCATION` | `us-central1` | GCP region |
| `BUCKET_NAME` | `sandbox-401718-product-fidelity-eval` | **Set to your GCS bucket** |

Model and threshold constants in `config.py`:

| Constant | Value | Description |
|---|---|---|
| `DESCRIPTION_MODEL` | `gemini-3-pro-preview` | Ground-truth description generation |
| `IMAGE_GEN_MODEL` | `gemini-3-pro-image-preview` | Candidate image generation |
| `VIDEO_GEN_MODEL` | `veo-3.1-generate-preview` | Candidate video generation |
| `AGENT_MODEL` | `gemini-3-pro-preview` | LlmAgent orchestration |
| `PASSING_THRESHOLD` | `0.7` | Minimum Gecko score to pass |
| `MAX_RETRIES` | `3` | Max refinement attempts (image) |
| `VIDEO_MAX_RETRIES` | `3` | Max refinement attempts (video) |

## To Do

- [x] On retries, augment the image generation prompt with the refined description and failing verdicts from Gecko evaluation
- [ ] Investigate whether using the refined description on the first attempt (not just retries) produces higher-fidelity results

## Usage

```bash
adk web agent
```

Example prompt:

```
Generate Candidate images and Evaluate product dress_pattern with images gs://<BUCKET_NAME>/dress_pattern.png
```
