from google.adk.agents.llm_agent import LlmAgent

from ..config import AGENT_MODEL
from ..callbacks import cleanup_image_data
from ..tools.gecko import run_gecko_evaluation, check_threshold

evaluation_agent = LlmAgent(
    name="EvaluationAgent",
    model=AGENT_MODEL,
    include_contents="none",
    before_model_callback=cleanup_image_data,
    instruction="""You are a product image evaluation coordinator.

Step 1: Call run_gecko_evaluation with:
  - prompt: {ground_truth_description}
  - image_uri: {candidate_image_uri}

Step 2: After evaluation completes, call check_threshold to determine the result.

The check_threshold tool makes the pass/retry/fail decision deterministically.
If it returns "pass" or "fail", the pipeline will exit the loop automatically.
If it returns "retry", output a brief summary and stop — the refinement agent
will handle the next step.

Output a brief summary of the evaluation result.""",
    tools=[run_gecko_evaluation, check_threshold],
    description=(
        "Evaluates candidate images using Gecko and checks the fidelity "
        "threshold."
    ),
)
