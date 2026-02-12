from google.adk.agents import LoopAgent, SequentialAgent
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext

from .config import AGENT_MODEL, MAX_RETRIES
from .callbacks import extract_uploaded_images, save_product_results
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


# --- Evaluation Pipeline (Description + Refinement for one product) ---
# after_agent_callback saves results to all_products and resets per-product state

evaluation_pipeline = SequentialAgent(
    name="EvaluationPipeline",
    sub_agents=[description_agent, refinement_loop],
    after_agent_callback=save_product_results,
    description="Generates description and runs iterative refinement for one product.",
)


# --- Product Pipeline (Evaluation + Report, runs deterministically) ---

product_pipeline = SequentialAgent(
    name="ProductPipeline",
    sub_agents=[evaluation_pipeline, report_agent],
    description="Evaluates one product and generates/updates the combined HTML report.",
)


# --- Root Pipeline (conversational orchestrator) ---

root_agent = LlmAgent(
    name="ProductFidelityPipeline",
    model=AGENT_MODEL,
    before_model_callback=extract_uploaded_images,
    instruction="""You are the orchestrator for a product fidelity evaluation pipeline.

Users can provide product images in two ways:
- **GCS URIs:** e.g. gs://bucket/dress.png (use directly)
- **Uploaded images:** images uploaded in the chat are automatically saved to GCS.
  You will see "[Uploaded image saved to: gs://...]" in the message — use that URI.

For each product the user wants to evaluate:
1. Parse the GCS image URI(s) and SKU ID from the user's message
2. Call initialize_evaluation with the parsed data
3. Transfer to ProductPipeline — it will automatically run evaluation and generate the HTML report

After ProductPipeline returns, summarize the result and let the user know they can provide another product.

SKU ID rules:
- If user provides a SKU ID, use it
- Otherwise derive from filename stem (e.g. gs://bucket/dress.png → dress)
""",
    tools=[initialize_evaluation],
    sub_agents=[product_pipeline],
)
