# Analysis Report: Product Fidelity Eval Multi-Agent System

## What you have today

Your notebook (`notebooks/product_fidelity_eval_with_gecko.ipynb`) already implements the core pipeline end-to-end as a linear script:

1. Gemini generates a ground-truth text description from an original product image
2. That description becomes the "prompt" for Gecko's text-to-image evaluation
3. Gecko generates rubrics, scores candidate images, and produces rubric verdicts
4. An HTML report is generated with embedded images from GCS

The agent architecture in your Mermaid diagram and flow image is well-structured. The mental model of Root -> Sequence -> (Parallel Step 1 | Evaluation Step 2 | Report Step 3) maps cleanly to ADK's agent primitives (`SequentialAgent`, `ParallelAgent`, `LlmAgent`).

---

## Answers to your questions

### Question 1: Should the threshold decision be a tool/function or should the Agent LLM decide?

**Use a deterministic tool/function, not the LLM.** Here's why:

- **Reliability**: A threshold check is `score >= 0.7` — a float comparison. LLMs can and do get simple math wrong, especially with decimal precision. There's no reason to burn tokens and introduce non-determinism for `if score >= threshold`.
- **Auditability**: A deterministic function gives you a guaranteed-reproducible decision log. If you later need to debug why a product was retried vs. passed, you want a code path you can trace, not an LLM transcript you have to interpret.
- **Latency/Cost**: An LLM call for a comparison is wasteful. A Python function returns in microseconds.
- **Implementation**: In ADK, the evaluation agent's tool returns the Gecko score. Then use a **callback** or a simple branching function (not an LLM call) to route to pass/retry/fail. The evaluation agent can call a `check_threshold` tool that returns a structured result like `{"action": "pass"}` or `{"action": "retry", "attempt": 2}`. The agent then follows that directive. Alternatively, you can implement this as control flow in the `SequentialAgent`'s orchestration logic itself, outside any LLM agent.

### Question 2: Should the Final Report be done by the Root Agent or a separate agent?

**Use a separate Final Report agent.** Reasons:

- **Separation of concerns**: The Root Agent's job is orchestration — accepting user input, dispatching to the sequence, and presenting final output. Report generation involves GCS writes, HTML templating, and data aggregation. Mixing these into the root muddies its role.
- **Reusability**: A standalone report agent can be invoked independently (e.g., "regenerate the report for yesterday's run" without re-running the whole pipeline).
- **Testability**: You can test report generation in isolation with mock evaluation data.
- **Root Agent as presenter**: The Root Agent should *receive* the report artifact (GCS URI + summary) from the report agent and present it to the user in the chat interface. Think of it as: Report Agent = produces the artifact, Root Agent = delivers it to the user.

---

## Architectural insights and recommendations

### 1. Retry loop design

The Gecko evaluation produces granular rubric verdicts — each verdict maps to a specific product attribute (e.g., "V-neckline," "white floral motifs," "three-quarter length sleeves") with a pass/fail per item. This means the retry loop has real, actionable signal to work with on every iteration, not just a single aggregate score.

**Iterative refinement model:**

- **Iteration 1**: Original description + generate image + Gecko score. Suppose "matte rubberized grip" and "serif font logo" fail their rubric checks.
- **Iteration 2**: Gecko Tool B takes the *original* description plus the *specific failing verdicts* and produces a refined description that **emphasizes** the missed attributes — not removes them. The image gen model gets a prompt that more heavily weights what it got wrong. Re-generate image, re-score with Gecko.
- **Iteration N**: Same loop. Each pass narrows the gap by focusing the prompt on previously missed attributes.

**Critical constraint — always derive from the original:**

The refined description on each iteration should be derived from `(original_description, current_failing_verdicts)`, **not** from the previous iteration's refined description. This prevents drift over multiple iterations where the description evolves away from the source product. Keep the original description stored separately and immutable. Gecko Tool B should always receive the original as its anchor.

**The distinction that matters:**

The direction of refinement must be **reinforcement** of failing attributes (making them more prominent so the image gen model pays attention), never **removal** of them (which would inflate the score without improving fidelity). As long as Gecko Tool B strengthens emphasis on what the image gen missed, this is a legitimate iterative improvement loop — not gaming the metric.

**When to stop:**

- Score >= threshold: pass, move on.
- Max retries exhausted and still failing: flag for HITL review. Attach the full rubric verdict history across all attempts so the reviewer can see which attributes are persistently missed — this is valuable diagnostic data that the iterative loop produces as a side effect.

### 2. Image generation via Nano Banana (Gemini image generation)

Nano Banana is a Gemini image generation API call. Since it's already within the Gemini ecosystem, this simplifies the tool implementation — you can use the same `google-genai` client you're already using for description generation, just targeting the image generation endpoint. Wrap it as a tool that takes the ground-truth description (or refined description on retries) as input, calls the Gemini image generation API, writes the result to GCS, and returns the GCS URI so it can be passed directly to the evaluation step.

### 3. State passing between steps

The Parallel Agent in Step 1 produces two outputs: a text description and a candidate image URI. Both need to flow into Step 2. In ADK, use the session state (`context.state`) or the agent's output to pass these artifacts. Define a clear schema for what Step 1 produces:

```json
{
  "sku_id": "sku_001",
  "ground_truth_description": "...",
  "candidate_image_uri": "gs://...",
  "attempt": 1
}
```

### 4. One product at a time (HITL) vs. batch

The agent-based system is designed for interactive, HITL use: a user requests evaluation for a specific product, the pipeline runs, the user reviews the result, and then may request another. The conversation itself is the loop — no `LoopAgent` or "for-each" primitive is needed. The Root Agent handles one product per user request.

Batch processing (running the generation + evaluation pipeline across an entire catalog without human interaction between each SKU) is a separate concern with different requirements around concurrency, error handling, and monitoring. This will be a separate application, likely orchestrated outside the agent system (e.g., Cloud Workflows, Pub/Sub fan-out, or a simple script calling the same tools directly).

---

## Proposed folder structure

```
product-fidelity-eval/
├── agent/
│   ├── __init__.py
│   ├── agent.py                     # Root Agent definition + SequentialAgent wiring
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── description_agent.py     # Step 1A: Generate ground-truth description (Gemini)
│   │   ├── image_gen_agent.py       # Step 1B: Generate candidate image (Nano Banana / Imagen)
│   │   ├── evaluation_agent.py      # Step 2:  Gecko scoring + threshold check
│   │   └── report_agent.py          # Step 3:  HTML report generation + GCS upload
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── gcs.py                   # read_from_gcs, write_to_gcs, list_objects
│   │   ├── gemini.py                # generate_description (wraps Gemini call)
│   │   ├── image_gen.py             # generate_product_image (wraps Imagen/NanoBanana)
│   │   ├── gecko.py                 # run_gecko_evaluation, check_threshold (deterministic)
│   │   └── reporting.py             # create_html_report (extracted from notebook)
│   ├── config.py                    # Project ID, location, thresholds, max retries, model IDs
│   ├── prompts/
│   │   ├── description_system.txt   # System instruction for ground-truth generation
│   │   └── description_user.txt     # User prompt template for multi-image synthesis
│   └── imgs/
│       └── agent_flow.jpg
├── notebooks/
│   └── product_fidelity_eval_with_gecko.ipynb
├── tests/
│   ├── __init__.py
│   ├── test_tools.py                # Unit tests for tools (mock GCS, mock Gecko)
│   └── test_agents.py               # Integration tests for agent wiring
├── pyproject.toml                   # Dependencies: google-cloud-aiplatform, google-genai, google-adk
├── README.md
└── .env.example                     # PROJECT_ID, LOCATION, BUCKET_NAME, etc.
```

### Key decisions in this structure

| Decision | Rationale |
|---|---|
| `agents/` separate from `tools/` | Agents define *behavior and orchestration*; tools define *capabilities*. An agent calls tools, not the other way around. |
| `prompts/` as text files | Keeps long system instructions out of Python code. Easier to iterate on prompt engineering without touching logic. Your notebook's `system_instruction` and `text_prompt` are both 400+ words — they belong in files. |
| `config.py` for constants | Threshold values, max retries, model IDs, bucket names — centralize these so they're not scattered across agents. |
| `reporting.py` in tools | Your notebook's `create_gecko_html_report` function is already 150+ lines of standalone logic. Extract it as a tool the report agent calls. |
| No `utils/` folder | You don't need one yet. Resist creating it until you have genuinely shared utility code that doesn't fit in tools or config. |
| `tests/` | Mock the GCS and Gecko API calls. The threshold logic and report generation are pure functions — easy to unit test. |
