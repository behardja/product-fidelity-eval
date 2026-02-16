from google.adk.agents import LoopAgent, SequentialAgent
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext

from .config import AGENT_MODEL, MAX_RETRIES, VIDEO_MAX_RETRIES
from .callbacks import extract_uploaded_images, save_product_results, cleanup_image_data
from .agents.description_agent import description_agent
from .agents.image_gen_agent import image_gen_agent
from .agents.evaluation_agent import evaluation_agent
from .agents.video_gen_agent import video_gen_agent
from .agents.video_evaluation_agent import video_evaluation_agent
from .agents.refinement_agent import refinement_agent
from .agents.report_agent import report_agent
from .tools.gemini import refine_description, generate_description
from .tools.reporting import create_html_report


# --- Tool for input parsing ---

def initialize_evaluation(
    image_uris: str, sku_id: str, generation_type: str = "image",
    tool_context: ToolContext = None,
) -> dict:
    """Initialize the product fidelity evaluation pipeline.

    Args:
        image_uris: Comma-separated GCS URIs of product reference images.
        sku_id: Product SKU identifier.
        generation_type: Either "image" (default) or "video".

    Returns:
        dict confirming initialization with the provided parameters.
    """
    tool_context.state["image_uris"] = image_uris
    tool_context.state["sku_id"] = sku_id
    tool_context.state["generation_type"] = generation_type
    tool_context.state["attempt"] = 1
    tool_context.state["evaluation_history"] = []
    tool_context.state["evaluation_passed"] = False
    return {
        "status": "initialized",
        "sku_id": sku_id,
        "generation_type": generation_type,
        "image_count": len([u for u in image_uris.split(",") if u.strip()]),
    }


# --- Duplicate agents for the video pipeline ---
# ADK agents can only have one parent, so we create separate instances
# with distinct names for the video pipeline.

video_description_agent = LlmAgent(
    name="VideoDescriptionAgent",
    model=AGENT_MODEL,
    include_contents="none",
    instruction=description_agent.instruction,
    tools=[generate_description],
    output_key="ground_truth_description",
    description=description_agent.description,
)

video_refinement_agent = LlmAgent(
    name="VideoRefinementAgent",
    model=AGENT_MODEL,
    include_contents="none",
    before_model_callback=cleanup_image_data,
    instruction=refinement_agent.instruction,
    tools=[refine_description],
    description=refinement_agent.description,
)

video_report_agent = LlmAgent(
    name="VideoReportAgent",
    model=AGENT_MODEL,
    include_contents="none",
    before_model_callback=cleanup_image_data,
    instruction=report_agent.instruction,
    tools=[create_html_report],
    description=report_agent.description,
)


# --- Image Refinement Loop (Image Gen → Evaluation → Refinement) ---

refinement_loop = LoopAgent(
    name="RefinementLoop",
    sub_agents=[
        image_gen_agent,
        evaluation_agent,
        refinement_agent,
    ],
    max_iterations=MAX_RETRIES,
)


# --- Video Refinement Loop (Video Gen → Video Evaluation → Refinement) ---

video_refinement_loop = LoopAgent(
    name="VideoRefinementLoop",
    sub_agents=[
        video_gen_agent,
        video_evaluation_agent,
        video_refinement_agent,
    ],
    max_iterations=VIDEO_MAX_RETRIES,
)


# --- Evaluation Pipeline (Description + Refinement for one product) ---
# after_agent_callback saves results to all_products and resets per-product state

evaluation_pipeline = SequentialAgent(
    name="EvaluationPipeline",
    sub_agents=[description_agent, refinement_loop],
    after_agent_callback=save_product_results,
    description="Generates description and runs iterative image refinement for one product.",
)


# --- Video Evaluation Pipeline (Description + Video Refinement for one product) ---

video_evaluation_pipeline = SequentialAgent(
    name="VideoEvaluationPipeline",
    sub_agents=[video_description_agent, video_refinement_loop],
    after_agent_callback=save_product_results,
    description="Generates description and runs iterative video refinement for one product.",
)


# --- Product Pipeline (Evaluation + Report, runs deterministically) ---

product_pipeline = SequentialAgent(
    name="ProductPipeline",
    sub_agents=[evaluation_pipeline, report_agent],
    description="Evaluates one product (image) and generates/updates the combined HTML report.",
)


# --- Video Product Pipeline (Video Evaluation + Report) ---

video_product_pipeline = SequentialAgent(
    name="VideoProductPipeline",
    sub_agents=[video_evaluation_pipeline, video_report_agent],
    description="Evaluates one product (video) and generates/updates the combined HTML report.",
)


# --- Root Pipeline (conversational orchestrator) ---

root_agent = LlmAgent(
    name="ProductFidelityPipeline",
    model=AGENT_MODEL,
    before_model_callback=extract_uploaded_images,
    instruction="""You are the orchestrator for a product fidelity evaluation pipeline.

Users can request either IMAGE or VIDEO generation for product evaluation:
- **Default (image):** If the user does not explicitly mention video, use image generation.
  Call initialize_evaluation with generation_type="image", then transfer to ProductPipeline.
- **Video:** If the user explicitly requests video generation (e.g., "generate a video",
  "video evaluation", "create a product video"), use video generation.
  Call initialize_evaluation with generation_type="video", then transfer to VideoProductPipeline.
- **Both:** If the user asks to generate BOTH image and video, inform them that
  simultaneous generation is not currently supported but may be added in the future.
  Ask them to choose one.

Users can provide product images in two ways:
- **GCS URIs:** e.g. gs://bucket/dress.png (use directly)
- **Uploaded images:** images uploaded in the chat are automatically saved to GCS.
  You will see "[Uploaded image saved to: gs://...]" in the message — use that URI.

For each product the user wants to evaluate:
1. Parse the GCS image URI(s) and SKU ID from the user's message
2. Call initialize_evaluation with the parsed data and the appropriate generation_type
3. Transfer to ProductPipeline (for images) or VideoProductPipeline (for videos)

After the pipeline returns, summarize the result and let the user know they can provide another product.

SKU ID rules:
- If user provides a SKU ID, use it
- Otherwise derive from filename stem (e.g. gs://bucket/dress.png → dress)
""",
    tools=[initialize_evaluation],
    sub_agents=[product_pipeline, video_product_pipeline],
)
