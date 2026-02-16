"""Async batch pipeline for processing multiple product images.

Imports directly from the existing agent tool functions and config.
Functions that use ToolContext get thin async wrappers; everything else
is called as-is.
"""

import asyncio
import html as html_mod
import os
import traceback
import uuid
from pathlib import Path

import pandas as pd
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from vertexai import Client as VertexClient
from vertexai import types as vertex_types

from product_fidelity_agent.config import (
    BUCKET_NAME,
    DESCRIPTION_MODEL,
    IMAGE_GEN_MODEL,
    LOCATION,
    MAX_RETRIES,
    PASSING_THRESHOLD,
    PROJECT_ID,
)
from product_fidelity_agent.tools.gcs import (
    image_to_base64,
    read_from_gcs,
    write_to_gcs,
)

# ---------------------------------------------------------------------------
# Prompts (loaded once)
# ---------------------------------------------------------------------------

_PROMPTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "product_fidelity_agent", "prompts"
)


def _load_prompt(filename: str) -> str:
    with open(os.path.join(_PROMPTS_DIR, filename)) as f:
        return f.read()


_SYSTEM_PROMPT: str | None = None
_USER_PROMPT: str | None = None


def _get_prompts() -> tuple[str, str]:
    global _SYSTEM_PROMPT, _USER_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _load_prompt("description_system.txt")
        _USER_PROMPT = _load_prompt("description_user.txt")
    return _SYSTEM_PROMPT, _USER_PROMPT


_RECONTEXTUALIZATION_PROMPT = (
    "Using the provided product image, generate a new image of the same product "
    "in a contextually appropriate setting. The new image should NOT have a white "
    "background, and should be contextualized based on the product itself. "
    "For example, if the product is a bag, the image should show the bag in a "
    "natural ad or professional photo setting. If the product is a dress, the "
    "image should show the dress in a natural model photo setting. "
    "If there is a person in the original product image, create a variation "
    "of the person with the product without copying the exact same pose and "
    "environment as in the original image. "
    "Keep the product exactly as it is — do not alter its design, colors, "
    "logos, or any visual details."
)

# ---------------------------------------------------------------------------
# Gemini client helper
# ---------------------------------------------------------------------------


def _gemini_client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
        http_options=types.HttpOptions(
            timeout=60 * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=5,
                initial_delay=1.0,
                jitter=0.3,
                max_delay=20.0,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Async wrappers for tool functions
# ---------------------------------------------------------------------------

sem = asyncio.Semaphore(5)


async def _describe(image_uri: str) -> str:
    """Generate a ground-truth description from a reference image."""
    system_prompt, user_prompt = _get_prompts()
    client = _gemini_client()

    ext = image_uri.lower().rsplit(".", 1)[-1]
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    content_parts = [
        types.Part.from_uri(file_uri=image_uri, mime_type=mime),
        user_prompt,
    ]

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=DESCRIPTION_MODEL,
        contents=content_parts,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=1,
        ),
    )
    return response.text


async def _refine(original_description: str, failing_verdicts: str) -> str:
    """Refine a description to emphasize failing attributes."""
    client = _gemini_client()

    refinement_prompt = f"""You are refining a product description for text-to-image generation.

The original description was used to generate an image, but the following attributes
were NOT faithfully reproduced in the generated image:

FAILING ATTRIBUTES:
{failing_verdicts}

ORIGINAL DESCRIPTION:
{original_description}

Your task: Rewrite the description to MORE STRONGLY EMPHASIZE the failing attributes.
- Keep ALL original details intact
- Add stronger, more explicit language for the failing attributes
- Add spatial/visual cues that help image generation models render these attributes correctly
- Do NOT remove any attributes — reinforce them
- Do NOT add new attributes that were not in the original
- Output only the refined description paragraph. 750 words max."""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=DESCRIPTION_MODEL,
        contents=refinement_prompt,
        config=types.GenerateContentConfig(temperature=0.7),
    )
    return response.text


async def _generate_image(
    image_uri: str,
    sku_id: str,
    attempt: int,
    current_description: str | None = None,
    failing_verdicts_text: str | None = None,
) -> str:
    """Generate a recontextualized product image. Returns the GCS URI."""
    client = _gemini_client()

    ext = image_uri.lower().rsplit(".", 1)[-1]
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    content_parts = [
        types.Part.from_uri(file_uri=image_uri, mime_type=mime),
    ]

    if attempt > 1 and current_description and failing_verdicts_text:
        retry_prompt = (
            f"{_RECONTEXTUALIZATION_PROMPT}\n\n"
            f"IMPORTANT: A previous attempt failed fidelity checks. "
            f"Pay extra attention to the following attributes that were NOT "
            f"faithfully reproduced:\n{failing_verdicts_text}\n\n"
            f"Use this refined product description as guidance:\n{current_description}"
        )
        content_parts.append(retry_prompt)
    else:
        content_parts.append(_RECONTEXTUALIZATION_PROMPT)

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=IMAGE_GEN_MODEL,
        contents=content_parts,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    for part in response.parts:
        if part.inline_data is not None:
            image_bytes = part.inline_data.data
            image_id = str(uuid.uuid4())[:8]
            gcs_path = (
                f"gs://{BUCKET_NAME}/generated/{sku_id}/"
                f"attempt_{attempt}_{image_id}.png"
            )
            await asyncio.to_thread(write_to_gcs, image_bytes, gcs_path)
            return gcs_path

    raise RuntimeError("No image was generated by the model.")


RUBRIC_MAX_RETRIES = 3
RUBRIC_RETRY_DELAY = 10  # seconds


async def _gecko_eval(prompt: str, image_uri: str) -> dict:
    """Run Gecko text-to-image evaluation. Returns dict with score and verdicts."""

    def _call():
        vertex_client = VertexClient(project=PROJECT_ID, location=LOCATION)

        response_data = {
            "parts": [
                {"file_data": {"mime_type": "image/png", "file_uri": image_uri}}
            ],
            "role": "model",
        }
        eval_dataset = pd.DataFrame(
            {"prompt": [prompt], "response": [response_data]}
        )

        # Generate rubrics with retry on rate-limit (429) errors
        data_with_rubrics = None
        for rubric_attempt in range(1, RUBRIC_MAX_RETRIES + 1):
            try:
                data_with_rubrics = vertex_client.evals.generate_rubrics(
                    src=eval_dataset,
                    rubric_group_name="gecko_image_rubrics",
                    predefined_spec_name=vertex_types.RubricMetric.GECKO_TEXT2IMAGE,
                )
                if isinstance(data_with_rubrics, pd.DataFrame):
                    df = data_with_rubrics
                else:
                    df = getattr(data_with_rubrics, "eval_dataset_df", None)
                if (
                    df is not None
                    and "rubric_groups" in df.columns
                    and len(df) > 0
                    and df["rubric_groups"].iloc[0]
                ):
                    break
                print(
                    f"Rubric generation returned empty results "
                    f"(attempt {rubric_attempt}/{RUBRIC_MAX_RETRIES}), retrying..."
                )
                if rubric_attempt < RUBRIC_MAX_RETRIES:
                    import time
                    time.sleep(RUBRIC_RETRY_DELAY)
            except ClientError as e:
                if e.status_code == 429 and rubric_attempt < RUBRIC_MAX_RETRIES:
                    print(
                        f"Rubric generation rate-limited "
                        f"(attempt {rubric_attempt}/{RUBRIC_MAX_RETRIES}), "
                        f"retrying in {RUBRIC_RETRY_DELAY}s..."
                    )
                    import time
                    time.sleep(RUBRIC_RETRY_DELAY)
                else:
                    raise

        # Evaluate
        eval_result = vertex_client.evals.evaluate(
            dataset=data_with_rubrics,
            metrics=[vertex_types.RubricMetric.GECKO_TEXT2IMAGE],
        )

        # Extract results
        case = eval_result.eval_case_results[0]
        metric_data = case.response_candidate_results[0].metric_results
        metric_key = list(metric_data.keys())[0]
        data = metric_data[metric_key]
        score = data.score
        verdicts = data.rubric_verdicts

        if score is None and not verdicts:
            raise RuntimeError(
                "Evaluation infrastructure error: no score or verdicts returned."
            )

        score = score if score is not None else 0.0

        passing = []
        failing = []
        if verdicts:
            for v in verdicts:
                raw_verdict = getattr(v, "verdict", False)
                is_pass = str(raw_verdict).lower() == "true"
                try:
                    text = v.evaluated_rubric.content.property.description
                except AttributeError:
                    text = str(v)
                if is_pass:
                    passing.append(text)
                else:
                    failing.append(text)

        return {
            "score": score,
            "passing_verdicts": passing,
            "failing_verdicts": failing,
            "total_verdicts": len(passing) + len(failing),
            "passing_count": len(passing),
            "failing_count": len(failing),
        }

    return await asyncio.to_thread(_call)


# ---------------------------------------------------------------------------
# Per-image pipeline
# ---------------------------------------------------------------------------


async def process_image(uri: str, progress_queue: asyncio.Queue) -> dict:
    """Run the full describe -> generate -> evaluate -> retry pipeline for one image."""
    sku_id = Path(uri).stem
    evaluation_history = []

    async with sem:
        await progress_queue.put({"sku": sku_id, "status": "running"})

        try:
            # Step 1: Generate ground-truth description
            description = await _describe(uri)
            original_description = description
            failing_verdicts_text = None

            for attempt in range(1, MAX_RETRIES + 1):
                # Step 2: Generate candidate image
                candidate_uri = await _generate_image(
                    uri, sku_id, attempt, description, failing_verdicts_text
                )

                # Step 3: Evaluate with Gecko
                result = await _gecko_eval(description, candidate_uri)

                evaluation_history.append({
                    "attempt": attempt,
                    "score": result["score"],
                    "passing_verdicts": result["passing_verdicts"],
                    "failing_verdicts": result["failing_verdicts"],
                    "image_uri": candidate_uri,
                })

                if result["score"] >= PASSING_THRESHOLD:
                    await progress_queue.put({
                        "sku": sku_id,
                        "status": "passed",
                        "score": result["score"],
                        "attempt": attempt,
                    })
                    return {
                        "sku_id": sku_id,
                        "passed": True,
                        "score": result["score"],
                        "attempts": attempt,
                        "description": original_description,
                        "candidate_uri": candidate_uri,
                        "reference_uri": uri,
                        "evaluation_history": evaluation_history,
                    }

                # Step 4: Refine description for retry
                failing_verdicts_text = "\n".join(
                    f"- {v}" for v in result["failing_verdicts"]
                )
                if attempt < MAX_RETRIES:
                    description = await _refine(
                        original_description, failing_verdicts_text
                    )

            # All retries exhausted
            final_score = evaluation_history[-1]["score"]
            await progress_queue.put({
                "sku": sku_id,
                "status": "failed",
                "score": final_score,
                "attempt": MAX_RETRIES,
            })
            return {
                "sku_id": sku_id,
                "passed": False,
                "score": final_score,
                "attempts": MAX_RETRIES,
                "description": original_description,
                "candidate_uri": candidate_uri,
                "reference_uri": uri,
                "evaluation_history": evaluation_history,
            }

        except asyncio.CancelledError:
            await progress_queue.put({"sku": sku_id, "status": "cancelled"})
            return {
                "sku_id": sku_id,
                "passed": False,
                "score": 0.0,
                "attempts": len(evaluation_history),
                "description": "",
                "candidate_uri": "",
                "reference_uri": uri,
                "evaluation_history": evaluation_history,
                "error": "cancelled",
            }
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"BATCH ERROR for {sku_id} ({uri}):")
            traceback.print_exc()
            print(f"{'='*60}\n")
            await progress_queue.put({
                "sku": sku_id,
                "status": "error",
                "message": str(e),
            })
            return {
                "sku_id": sku_id,
                "passed": False,
                "score": 0.0,
                "attempts": len(evaluation_history),
                "description": "",
                "candidate_uri": "",
                "reference_uri": uri,
                "evaluation_history": evaluation_history,
                "error": str(e),
            }


# ---------------------------------------------------------------------------
# Batch orchestrator
# ---------------------------------------------------------------------------


async def run_batch(
    image_uris: list[str],
    progress_queue: asyncio.Queue,
) -> list[dict]:
    """Process all images concurrently and return sorted results."""
    results = await asyncio.gather(
        *[process_image(uri, progress_queue) for uri in image_uris],
        return_exceptions=False,
    )
    # Sort lowest score first (worst products surface for review)
    results = sorted(results, key=lambda r: r["score"])

    await progress_queue.put({"status": "complete", "total": len(results)})

    # Generate batch report
    _generate_report(results)

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _build_product_section(product: dict) -> str:
    """Build the HTML section for a single product in the batch report."""
    sku_id = product.get("sku_id", "unknown")
    description = product.get("description", "")
    reference_uri = product.get("reference_uri", "")
    history = product.get("evaluation_history", [])
    passed = product.get("passed", False)
    error = product.get("error")

    # Reference image
    ref_img_html = ""
    if reference_uri:
        b64_data, mime_type = image_to_base64(reference_uri)
        if b64_data:
            name = reference_uri.split("/")[-1]
            ref_img_html = (
                f'<div style="text-align:center">'
                f'<img src="data:{mime_type};base64,{b64_data}" '
                f'alt="{html_mod.escape(name)}" '
                f'style="max-height:160px;max-width:200px;border-radius:4px;'
                f'border:1px solid #ccc;">'
                f'<div style="font-size:0.8em;margin-top:4px">'
                f"{html_mod.escape(name)}</div></div>"
            )

    # Attempts
    attempts_html = ""
    for entry in history:
        attempt_num = entry["attempt"]
        score = entry["score"]
        passing = entry.get("passing_verdicts", [])
        failing = entry.get("failing_verdicts", [])
        image_uri = entry.get("image_uri", "")

        score_class = (
            "score-high" if score >= 0.7
            else "score-medium" if score >= 0.4
            else "score-low"
        )

        img_html = ""
        if image_uri:
            b64_data, mime_type = image_to_base64(image_uri)
            if b64_data:
                img_html = (
                    f'<img src="data:{mime_type};base64,{b64_data}" '
                    f'alt="Attempt {attempt_num}" '
                    f'style="max-width:100%;border-radius:4px;border:1px solid #eee;">'
                )

        verdicts_html = "<ul class='rubric-list'>"
        for v in failing:
            verdicts_html += (
                f"<li class='rubric-item rubric-fail'>"
                f"<span class='icon'>&#10007;</span> {html_mod.escape(str(v))}</li>"
            )
        for v in passing:
            verdicts_html += (
                f"<li class='rubric-item rubric-pass'>"
                f"<span class='icon'>&#10003;</span> {html_mod.escape(str(v))}</li>"
            )
        verdicts_html += "</ul>"

        total = len(passing) + len(failing)
        open_attr = "open" if score < 0.7 else ""

        attempts_html += f"""
        <details class="attempt" {open_attr}>
          <summary>
            <span class="attempt-label">Attempt {attempt_num}</span>
            <span class="score-badge {score_class}">{score:.2f}</span>
            <span class="stats">{len(passing)}/{total} passed</span>
          </summary>
          <div class="attempt-content">
            <div class="attempt-image">{img_html}</div>
            <div class="attempt-verdicts">{verdicts_html}</div>
          </div>
        </details>
        """

    final_score = history[-1]["score"] if history else 0.0
    if error:
        result_label = f"ERROR: {html_mod.escape(error)}"
        result_color = "#f59e0b"
    elif passed:
        result_label = "PASSED"
        result_color = "#188038"
    else:
        result_label = "NEEDS REVIEW"
        result_color = "#d93025"

    return f"""
    <div class="product-section">
      <h2 class="product-header" style="color:{result_color};">
        {html_mod.escape(sku_id)} &mdash; {result_label} (Score: {final_score:.2f})
      </h2>
      <div class="meta">
        <div class="meta-images">{ref_img_html}</div>
        <div class="meta-prompt">{html_mod.escape(description)}</div>
      </div>
      {attempts_html}
    </div>
    """


def _generate_report(results: list[dict]) -> str:
    """Generate the batch HTML report. Returns the file path."""
    if not results:
        return ""

    # Summary stats
    total = len(results)
    passed_count = sum(1 for r in results if r.get("passed"))
    failed_count = total - passed_count
    scores = [r["score"] for r in results if r.get("evaluation_history")]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    total_attempts = sum(r.get("attempts", 0) for r in results)
    avg_attempts = total_attempts / total if total else 0.0

    summary_html = f"""
    <div class="summary">
      <h2>Batch Summary</h2>
      <div class="summary-grid">
        <div class="summary-card">
          <div class="summary-value">{total}</div>
          <div class="summary-label">Total Products</div>
        </div>
        <div class="summary-card" style="border-color:#188038">
          <div class="summary-value" style="color:#188038">{passed_count}</div>
          <div class="summary-label">Passed</div>
        </div>
        <div class="summary-card" style="border-color:#d93025">
          <div class="summary-value" style="color:#d93025">{failed_count}</div>
          <div class="summary-label">Needs Review</div>
        </div>
        <div class="summary-card">
          <div class="summary-value">{avg_score:.2f}</div>
          <div class="summary-label">Avg Gecko Score</div>
        </div>
        <div class="summary-card">
          <div class="summary-value">{avg_attempts:.1f}</div>
          <div class="summary-label">Avg Attempts</div>
        </div>
      </div>
    </div>
    """

    # Product sections (already sorted lowest first)
    product_sections = [_build_product_section(r) for r in results]
    sections_html = "\n<hr class='product-divider'>\n".join(product_sections)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Batch Product Fidelity Report</title>
<style>
  body {{ font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif; margin:0; background:#f4f4f4; color:#333; }}
  .container {{ max-width:1100px; margin:30px auto; background:#fff; padding:30px; border-radius:8px; box-shadow:0 2px 15px rgba(0,0,0,.08); }}
  h1 {{ color:#1a73e8; margin-top:0; border-bottom:2px solid #eee; padding-bottom:10px; }}
  .summary {{ margin-bottom:30px; padding:20px; background:#f8f9fa; border-radius:8px; }}
  .summary h2 {{ margin-top:0; color:#333; }}
  .summary-grid {{ display:flex; gap:16px; flex-wrap:wrap; }}
  .summary-card {{ flex:1; min-width:120px; padding:16px; background:#fff; border-radius:8px; border-left:4px solid #1a73e8; text-align:center; }}
  .summary-value {{ font-size:1.8em; font-weight:bold; color:#1a73e8; }}
  .summary-label {{ font-size:0.85em; color:#666; margin-top:4px; }}
  .product-section {{ margin-bottom:30px; }}
  .product-header {{ margin-top:0; padding-bottom:8px; border-bottom:1px solid #eee; }}
  .product-divider {{ border:none; border-top:3px solid #e0e0e0; margin:30px 0; }}
  .meta {{ display:flex; gap:20px; margin-bottom:20px; background:#f8f9fa; padding:15px; border-radius:6px; }}
  .meta-images {{ display:flex; gap:12px; flex-wrap:wrap; }}
  .meta-prompt {{ flex:1; font-size:.9em; line-height:1.5; max-height:200px; overflow-y:auto; white-space:pre-wrap; background:#fff; padding:12px; border:1px solid #eee; border-radius:4px; }}
  .attempt {{ border:1px solid #e0e0e0; border-radius:8px; margin-bottom:10px; overflow:hidden; }}
  .attempt[open] {{ box-shadow:0 2px 8px rgba(0,0,0,.1); }}
  .attempt summary {{ padding:14px 18px; background:#fafafa; cursor:pointer; display:flex; align-items:center; gap:12px; list-style:none; }}
  .attempt summary::-webkit-details-marker {{ display:none; }}
  .attempt-label {{ font-weight:600; }}
  .attempt-content {{ display:flex; gap:20px; padding:18px; }}
  .attempt-image {{ flex:0 0 250px; }}
  .attempt-image img {{ max-width:100%; height:auto; }}
  .attempt-verdicts {{ flex:1; }}
  .score-badge {{ display:inline-block; padding:4px 12px; border-radius:14px; font-weight:bold; font-size:.9em; }}
  .score-high {{ background:#e6f4ea; color:#188038; }}
  .score-medium {{ background:#fef7e0; color:#b06000; }}
  .score-low {{ background:#fce8e6; color:#d93025; }}
  .stats {{ color:#666; font-size:.85em; }}
  .rubric-list {{ list-style:none; padding:0; margin:0; }}
  .rubric-item {{ margin-bottom:5px; padding:8px 10px; border-left:4px solid; border-radius:3px; font-size:.9em; }}
  .rubric-pass {{ border-color:#188038; background:#f6fef7; }}
  .rubric-fail {{ border-color:#d93025; background:#fef7f6; }}
  .icon {{ margin-right:6px; }}
</style>
</head>
<body>
<div class="container">
  <h1>Batch Product Fidelity Report</h1>
  {summary_html}
  {sections_html}
</div>
</body>
</html>"""

    filename = "batch_report.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    return filename
