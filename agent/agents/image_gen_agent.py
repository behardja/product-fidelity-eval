from google.adk.agents.llm_agent import LlmAgent

from ..config import AGENT_MODEL
from ..tools.image_gen import generate_product_image

image_gen_agent = LlmAgent(
    name="ImageGenAgent",
    model=AGENT_MODEL,
    include_contents="none",
    instruction="""You are a product image generation coordinator.

Generate a candidate product image from the current description by calling
the generate_product_image tool with the following description:

{current_description}

Output only the resulting image URI.""",
    tools=[generate_product_image],
    description="Generates a candidate product image from the current description.",
)
