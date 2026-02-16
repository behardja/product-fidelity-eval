import time

import pandas as pd
from vertexai import Client as VertexClient
from vertexai import types as vertex_types
from google.genai.errors import ClientError
from google.adk.tools.tool_context import ToolContext

from ..config import PROJECT_ID, LOCATION, PASSING_THRESHOLD, MAX_RETRIES

RUBRIC_MAX_RETRIES = 3
RUBRIC_RETRY_DELAY = 10  # seconds


def run_gecko_evaluation(
    prompt: str, image_uri: str, tool_context: ToolContext
) -> dict:
    """Run Gecko text-to-image evaluation on a candidate image.

    Args:
        prompt: The ground-truth description to evaluate against.
        image_uri: GCS URI of the candidate image to evaluate.

    Returns:
        dict with score, verdict counts, and lists of passing/failing verdicts.
    """
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
            # Verify rubrics were actually generated (the SDK may silently
            # swallow errors and return data with empty rubric content)
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
            # Rubrics came back empty — treat as a transient failure
            print(
                f"Rubric generation returned empty results "
                f"(attempt {rubric_attempt}/{RUBRIC_MAX_RETRIES}), retrying..."
            )
            if rubric_attempt < RUBRIC_MAX_RETRIES:
                time.sleep(RUBRIC_RETRY_DELAY)
        except ClientError as e:
            if e.status_code == 429 and rubric_attempt < RUBRIC_MAX_RETRIES:
                print(
                    f"Rubric generation rate-limited "
                    f"(attempt {rubric_attempt}/{RUBRIC_MAX_RETRIES}), "
                    f"retrying in {RUBRIC_RETRY_DELAY}s..."
                )
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

    # Detect evaluation infrastructure failures: if score is None and there
    # are no verdicts, the eval didn't actually run (e.g. missing rubrics).
    if score is None and not verdicts:
        return {
            "status": "error",
            "message": (
                "Evaluation infrastructure error: no score or verdicts "
                "returned. This is likely due to a transient rate-limit "
                "on the judge model. Please retry."
            ),
        }

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

    # Store in state
    tool_context.state["gecko_score"] = score
    tool_context.state["rubric_verdicts"] = {
        "passing": passing,
        "failing": failing,
    }
    tool_context.state["failing_verdicts_text"] = "\n".join(
        f"- {v}" for v in failing
    )

    # Track history across attempts
    history = tool_context.state.get("evaluation_history", [])
    history.append(
        {
            "attempt": tool_context.state.get("attempt", 1),
            "score": score,
            "passing_verdicts": passing,
            "failing_verdicts": failing,
            "image_uri": image_uri,
        }
    )
    tool_context.state["evaluation_history"] = history

    return {
        "status": "success",
        "score": score,
        "total_verdicts": len(passing) + len(failing),
        "passing_count": len(passing),
        "failing_count": len(failing),
        "failing_verdicts": failing,
    }


def run_gecko_video_evaluation(
    prompt: str, video_uri: str, tool_context: ToolContext
) -> dict:
    """Run Gecko text-to-video evaluation on a candidate video.

    Args:
        prompt: The ground-truth description to evaluate against.
        video_uri: GCS URI of the candidate video to evaluate.

    Returns:
        dict with score, verdict counts, and lists of passing/failing verdicts.
    """
    vertex_client = VertexClient(project=PROJECT_ID, location=LOCATION)

    response_data = {
        "parts": [
            {"file_data": {"mime_type": "video/mp4", "file_uri": video_uri}}
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
                rubric_group_name="gecko_video_rubrics",
                predefined_spec_name=vertex_types.RubricMetric.GECKO_TEXT2VIDEO,
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
                time.sleep(RUBRIC_RETRY_DELAY)
        except ClientError as e:
            if e.status_code == 429 and rubric_attempt < RUBRIC_MAX_RETRIES:
                print(
                    f"Rubric generation rate-limited "
                    f"(attempt {rubric_attempt}/{RUBRIC_MAX_RETRIES}), "
                    f"retrying in {RUBRIC_RETRY_DELAY}s..."
                )
                time.sleep(RUBRIC_RETRY_DELAY)
            else:
                raise

    # Evaluate
    eval_result = vertex_client.evals.evaluate(
        dataset=data_with_rubrics,
        metrics=[vertex_types.RubricMetric.GECKO_TEXT2VIDEO],
    )

    # Extract results
    case = eval_result.eval_case_results[0]
    metric_data = case.response_candidate_results[0].metric_results
    metric_key = list(metric_data.keys())[0]
    data = metric_data[metric_key]
    score = data.score
    verdicts = data.rubric_verdicts

    if score is None and not verdicts:
        return {
            "status": "error",
            "message": (
                "Evaluation infrastructure error: no score or verdicts "
                "returned. This is likely due to a transient rate-limit "
                "on the judge model. Please retry."
            ),
        }

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

    # Store in state (same keys as image evaluation)
    tool_context.state["gecko_score"] = score
    tool_context.state["rubric_verdicts"] = {
        "passing": passing,
        "failing": failing,
    }
    tool_context.state["failing_verdicts_text"] = "\n".join(
        f"- {v}" for v in failing
    )

    # Track history across attempts
    history = tool_context.state.get("evaluation_history", [])
    history.append(
        {
            "attempt": tool_context.state.get("attempt", 1),
            "score": score,
            "passing_verdicts": passing,
            "failing_verdicts": failing,
            "image_uri": video_uri,
        }
    )
    tool_context.state["evaluation_history"] = history

    return {
        "status": "success",
        "score": score,
        "total_verdicts": len(passing) + len(failing),
        "passing_count": len(passing),
        "failing_count": len(failing),
        "failing_verdicts": failing,
    }


def check_threshold(tool_context: ToolContext) -> dict:
    """Check if the current Gecko score meets the passing threshold.

    This is a deterministic check - no LLM reasoning is involved in the
    pass/retry/fail decision. Call this after run_gecko_evaluation.

    Returns:
        dict with 'action' (pass, retry, or fail), score, and context.
    """
    score = tool_context.state.get("gecko_score", 0.0)
    attempt = tool_context.state.get("attempt", 1)

    if score >= PASSING_THRESHOLD:
        tool_context.state["evaluation_passed"] = True
        tool_context.actions.escalate = True
        return {
            "action": "pass",
            "score": score,
            "threshold": PASSING_THRESHOLD,
            "attempt": attempt,
            "message": (
                f"Score {score:.2f} meets threshold {PASSING_THRESHOLD}. "
                "Evaluation passed."
            ),
        }

    if attempt >= MAX_RETRIES:
        tool_context.state["evaluation_passed"] = False
        tool_context.actions.escalate = True
        return {
            "action": "fail",
            "score": score,
            "threshold": PASSING_THRESHOLD,
            "attempt": attempt,
            "max_attempts": MAX_RETRIES,
            "message": (
                f"Score {score:.2f} below threshold after {attempt} attempts. "
                "Flagged for HITL review."
            ),
        }

    # Retry needed
    failing_verdicts = tool_context.state.get("rubric_verdicts", {}).get(
        "failing", []
    )
    return {
        "action": "retry",
        "score": score,
        "threshold": PASSING_THRESHOLD,
        "attempt": attempt,
        "max_attempts": MAX_RETRIES,
        "failing_verdicts": failing_verdicts,
        "message": (
            f"Score {score:.2f} below threshold {PASSING_THRESHOLD}. "
            f"Attempt {attempt}/{MAX_RETRIES}. Refinement needed."
        ),
    }
