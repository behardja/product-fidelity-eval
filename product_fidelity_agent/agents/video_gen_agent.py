from google.adk.agents.llm_agent import LlmAgent

from ..config import AGENT_MODEL
from ..callbacks import inject_generated_video, cleanup_image_data
from ..tools.video_gen import generate_product_video

video_gen_agent = LlmAgent(
    name="VideoGenAgent",
    model=AGENT_MODEL,
    include_contents="none",
    instruction="""You are a product video generation coordinator.

Generate a candidate product video by calling the generate_product_video tool.
The tool will generate a short video showcasing the original product in an
appropriate setting using the Veo API.

Output only the resulting video URI.""",
    tools=[generate_product_video],
    before_model_callback=cleanup_image_data,
    after_model_callback=inject_generated_video,
    description="Generates a candidate product video from the current description.",
)
