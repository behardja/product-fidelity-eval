from google.adk.agents.llm_agent import LlmAgent

from ..config import AGENT_MODEL
from ..callbacks import inject_generated_image, cleanup_image_data
from ..tools.image_gen import generate_product_image

image_gen_agent = LlmAgent(
    name="ImageGenAgent",
    model=AGENT_MODEL,
    include_contents="none",
    instruction="""You are a product image generation coordinator.

Generate a candidate product image by calling the generate_product_image tool.
The tool will recontextualize the original product image into an appropriate setting.

Output only the resulting image URI.""",
    tools=[generate_product_image],
    before_model_callback=cleanup_image_data,
    after_model_callback=inject_generated_image,
    description="Generates a candidate product image from the current description.",
)
