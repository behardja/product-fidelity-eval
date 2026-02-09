# Product Fidelity Eval — Multi-Agent System

A Google ADK agent pipeline that evaluates whether AI-generated product images faithfully reproduce an original product. It generates a ground-truth text description from reference images, uses that description to generate candidate images, scores them with Gecko, and iteratively refines the description until the fidelity threshold is met or retries are exhausted.

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
│   │     Generates a candidate product image from the current description
│   │     using gemini-3-pro-image-preview (Nano Banana Pro).
│   │     Saves the result to GCS.
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
agent/
├── agent.py                  # Root SequentialAgent + LoopAgent wiring, InputAgent
├── config.py                 # GCP project, model IDs, threshold (0.7), max retries (3)
├── agents/
│   ├── description_agent.py  # Ground-truth description generation
│   ├── image_gen_agent.py    # Candidate image generation
│   ├── evaluation_agent.py   # Gecko scoring + threshold check
│   ├── refinement_agent.py   # Description refinement on retry
│   └── report_agent.py       # HTML report generation
├── tools/
│   ├── gcs.py                # read_from_gcs, write_to_gcs, image_to_base64
│   ├── gemini.py             # generate_description, refine_description
│   ├── image_gen.py          # generate_product_image
│   ├── gecko.py              # run_gecko_evaluation, check_threshold
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
| `failing_verdicts_text` | EvaluationAgent | RefinementAgent |
| `evaluation_history` | EvaluationAgent (appended each attempt) | ReportAgent |
| `evaluation_passed` | check_threshold | ReportAgent |
| `attempt` | InputAgent / RefinementAgent | ImageGenAgent, check_threshold |

## Key Design Decisions

**Deterministic threshold** — The pass/retry/fail decision is a float comparison inside `check_threshold`, not an LLM call. It sets `tool_context.actions.escalate = True` to exit the LoopAgent directly.

**Drift prevention** — `refine_description` always takes `(original_description, failing_verdicts)` as input, never the previous refinement. The original description is stored separately and treated as immutable.

**Reinforcement, not removal** — Refinement strengthens emphasis on failing attributes rather than removing them, so score improvements reflect genuine fidelity gains.

**Prompts as files** — The system instruction and user prompt (~400+ words each) live in `prompts/` as plain text files to separate prompt engineering from code.

## Configuration

Set via environment variables or defaults in `config.py`:

| Variable | Default | Description |
|---|---|---|
| `PROJECT_ID` | `sandbox-401718` | GCP project |
| `LOCATION` | `global` | GCP region |
| `BUCKET_NAME` | `sandbox-401718-product-fidelity-evals` | GCS bucket for images |

Model and threshold constants in `config.py`:

| Constant | Value |
|---|---|
| `DESCRIPTION_MODEL` | `gemini-3-pro-preview` |
| `IMAGE_GEN_MODEL` | `gemini-3-pro-image-preview` |
| `AGENT_MODEL` | `gemini-3-pro-preview` |
| `PASSING_THRESHOLD` | `0.7` |
| `MAX_RETRIES` | `3` |

## Usage

```bash
adk web agent
```

Example prompt:

```
Evaluate product dress_pattern with images gs://sandbox-401718-product-fidelity-evals/dress_pattern.png
```
