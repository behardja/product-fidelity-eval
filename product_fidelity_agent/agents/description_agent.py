from google.adk.agents.llm_agent import LlmAgent

from ..config import AGENT_MODEL
from ..tools.gemini import generate_description

description_agent = LlmAgent(
    name="DescriptionAgent",
    model=AGENT_MODEL,
    include_contents="none",
    instruction="""You are a product description generation coordinator.

Your task is to generate a ground-truth description of the product from its
reference images.

Call the generate_description tool with the image URIs: {image_uris}

Output only the generated description text, nothing else.""",
    tools=[generate_description],
    output_key="ground_truth_description",
    description=(
        "Generates a ground-truth product description from reference images "
        "using Gemini."
    ),
)
