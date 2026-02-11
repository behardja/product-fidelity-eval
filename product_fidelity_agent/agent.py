from google.adk.agents import LoopAgent, SequentialAgent
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext

from .config import AGENT_MODEL, MAX_RETRIES
from .agents.description_agent import description_agent
from .agents.image_gen_agent import image_gen_agent
from .agents.evaluation_agent import evaluation_agent
from .agents.refinement_agent import refinement_agent
from .agents.report_agent import report_agent


# --- Tool for input parsing ---

def initialize_evaluation(
    image_uris: str, sku_id: str, tool_context: ToolContext
) -> dict:
    """Initialize the product fidelity evaluation pipeline.

    Args:
        image_uris: Comma-separated GCS URIs of product reference images.
        sku_id: Product SKU identifier.

    Returns:
        dict confirming initialization with the provided parameters.
    """
    tool_context.state["image_uris"] = image_uris
    tool_context.state["sku_id"] = sku_id
    tool_context.state["attempt"] = 1
    tool_context.state["evaluation_history"] = []
    tool_context.state["evaluation_passed"] = False
    return {
        "status": "initialized",
        "sku_id": sku_id,
        "image_count": len([u for u in image_uris.split(",") if u.strip()]),
    }


# --- Input Agent (first step — parses user request) ---

input_agent = LlmAgent(
    name="InputAgent",
    model=AGENT_MODEL,
    instruction="""You are the input coordinator for a product fidelity evaluation pipeline.

Parse the user's request and extract:
1. The GCS image URI(s) of the product reference images (gs://... paths)
2. The product SKU identifier

Then call the initialize_evaluation tool with:
- image_uris: comma-separated GCS URIs
- sku_id: the product identifier

If the user does not provide a SKU ID, use the full filename stem (filename without
the extension) as the SKU ID. For example:
- "gs://bucket/dress_pattern.png" → sku_id = "dress_pattern"
- "gs://bucket/SKU-002-Fiorelli-Women-s-Nicole-Crossbody-Bag-Brown-Floral.png" → sku_id = "SKU-002-Fiorelli-Women-s-Nicole-Crossbody-Bag-Brown-Floral"

Output a confirmation that the pipeline has been initialized.""",
    tools=[initialize_evaluation],
    description="Parses user input and initializes the evaluation pipeline state.",
)


# --- Refinement Loop (Image Gen → Evaluation → Refinement) ---

refinement_loop = LoopAgent(
    name="RefinementLoop",
    sub_agents=[
        image_gen_agent,
        evaluation_agent,
        refinement_agent,
    ],
    max_iterations=MAX_RETRIES,
)


# --- Root Pipeline ---

root_agent = SequentialAgent(
    name="ProductFidelityPipeline",
    sub_agents=[
        input_agent,
        description_agent,
        refinement_loop,
        report_agent,
    ],
    description=(
        "End-to-end product fidelity evaluation pipeline: parses input, "
        "generates a ground-truth description, iteratively generates and "
        "evaluates candidate images, and produces an HTML report."
    ),
)
