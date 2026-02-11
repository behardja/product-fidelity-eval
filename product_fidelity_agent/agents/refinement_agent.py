from google.adk.agents.llm_agent import LlmAgent

from ..config import AGENT_MODEL
from ..tools.gemini import refine_description

refinement_agent = LlmAgent(
    name="RefinementAgent",
    model=AGENT_MODEL,
    include_contents="none",
    instruction="""You are a description refinement coordinator.

The candidate image did not pass the fidelity threshold. Refine the product
description to better emphasize the attributes that failed evaluation.

Call refine_description with:
  - original_description: {ground_truth_description}
  - failing_verdicts: the failing verdicts listed below

Failing verdicts from the latest evaluation:
{failing_verdicts_text}

Output only the refined description.""",
    tools=[refine_description],
    description=(
        "Refines the product description based on failing evaluation verdicts, "
        "always deriving from the original to prevent drift."
    ),
)
