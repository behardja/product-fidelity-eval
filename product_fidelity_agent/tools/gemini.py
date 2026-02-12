import os

from google import genai
from google.genai import types
from google.adk.tools.tool_context import ToolContext

from ..config import PROJECT_ID, LOCATION, DESCRIPTION_MODEL

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


def _load_prompt(filename: str) -> str:
    with open(os.path.join(_PROMPTS_DIR, filename)) as f:
        return f.read()


def generate_description(image_uris: str, tool_context: ToolContext) -> dict:
    """Generate a ground-truth product description from reference images.

    Args:
        image_uris: Comma-separated GCS URIs of product reference images.

    Returns:
        dict with 'description' containing the generated ground-truth text.
    """
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
        http_options=types.HttpOptions(
            timeout=60 * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=5,
                initial_delay=1.0,
                jitter=0.3,
                max_delay=20.0,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            ),
        ),
    )

    system_instruction = _load_prompt("description_system.txt")
    user_prompt = _load_prompt("description_user.txt")

    uris = [u.strip() for u in image_uris.split(",")]
    content_parts = []
    for uri in uris:
        ext = uri.lower().rsplit(".", 1)[-1]
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        content_parts.append(types.Part.from_uri(file_uri=uri, mime_type=mime))
    content_parts.append(user_prompt)

    response = client.models.generate_content(
        model=DESCRIPTION_MODEL,
        contents=content_parts,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=1,
        ),
    )

    description = response.text
    tool_context.state["ground_truth_description"] = description
    tool_context.state["current_description"] = description
    tool_context.state["attempt"] = 1

    return {"status": "success", "description": description}


def refine_description(
    original_description: str, failing_verdicts: str, tool_context: ToolContext
) -> dict:
    """Refine a product description to emphasize attributes that failed evaluation.

    Always derives from the original description (not previous refinements)
    to prevent drift across iterations.

    Args:
        original_description: The original ground-truth description.
        failing_verdicts: Newline-separated list of failing rubric verdicts.

    Returns:
        dict with 'refined_description' containing the updated text.
    """
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
        http_options=types.HttpOptions(
            timeout=60 * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=5,
                initial_delay=1.0,
                jitter=0.3,
                max_delay=20.0,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            ),
        ),
    )

    refinement_prompt = f"""You are refining a product description for text-to-image generation.

The original description was used to generate an image, but the following attributes
were NOT faithfully reproduced in the generated image:

FAILING ATTRIBUTES:
{failing_verdicts}

ORIGINAL DESCRIPTION:
{original_description}

Your task: Rewrite the description to MORE STRONGLY EMPHASIZE the failing attributes.
- Keep ALL original details intact
- Add stronger, more explicit language for the failing attributes
- Add spatial/visual cues that help image generation models render these attributes correctly
- Do NOT remove any attributes — reinforce them
- Do NOT add new attributes that were not in the original
- Output only the refined description paragraph. 750 words max."""

    response = client.models.generate_content(
        model=DESCRIPTION_MODEL,
        contents=refinement_prompt,
        config=types.GenerateContentConfig(temperature=0.7),
    )

    refined = response.text
    tool_context.state["current_description"] = refined

    attempt = tool_context.state.get("attempt", 1)
    tool_context.state["attempt"] = attempt + 1

    return {"status": "success", "refined_description": refined}
