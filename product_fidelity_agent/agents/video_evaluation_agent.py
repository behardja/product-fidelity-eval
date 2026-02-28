from google.adk.agents.llm_agent import LlmAgent

from ..config import AGENT_MODEL
from ..callbacks import cleanup_image_data, normalize_tool_args
from ..tools.gecko import run_gecko_video_evaluation, check_threshold

video_evaluation_agent = LlmAgent(
    name="VideoEvaluationAgent",
    model=AGENT_MODEL,
    include_contents="default",
    before_model_callback=cleanup_image_data,
    before_tool_callback=normalize_tool_args,
    instruction="""You are a product video evaluation coordinator.

Step 1: Call run_gecko_video_evaluation with:
  - prompt: {ground_truth_description?}
  - video_uri: {candidate_video_uri?}

Step 2: After evaluation completes, call check_threshold to determine the result.

The check_threshold tool makes the pass/retry/fail decision deterministically.
If it returns "pass" or "fail", the pipeline will exit the loop automatically.
If it returns "retry", output a brief summary and stop — the refinement agent
will handle the next step.

Output a brief summary of the evaluation result.""",
    tools=[run_gecko_video_evaluation, check_threshold],
    description=(
        "Evaluates candidate videos using Gecko TEXT2VIDEO and checks the "
        "fidelity threshold."
    ),
)
