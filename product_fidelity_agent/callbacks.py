import re
import uuid

from google.genai import types

from .config import BUCKET_NAME
from .tools.gcs import image_to_base64, write_to_gcs


def _get_text(llm_response):
    """Extract concatenated text from an LlmResponse's content parts."""
    if not llm_response.content or not llm_response.content.parts:
        return None
    texts = [p.text for p in llm_response.content.parts if p.text]
    return "".join(texts) if texts else None


def inject_generated_image(callback_context, llm_response):
    """after_model_callback: inject candidate image as base64 markdown into the response.

    Reads the candidate_image_uri from state (set by generate_product_image tool),
    fetches the image from GCS, and appends it as an inline markdown image so the
    ADK web UI renders it in the chat.

    On the first attempt, also displays the original reference image(s) for
    side-by-side comparison.
    """
    # Only inject on final text responses, not intermediate tool-call responses
    if not _get_text(llm_response):
        return None

    parts_to_append = []

    # On first attempt, show the original reference image(s)
    if not callback_context.state.get("_reference_images_shown"):
        image_uris = callback_context.state.get("image_uris", "")
        uris = [u.strip() for u in image_uris.split(",") if u.strip()]
        for uri in uris:
            b64_data, mime_type = image_to_base64(uri)
            if b64_data:
                name = uri.split("/")[-1]
                md = f"![{name}](data:{mime_type};base64,{b64_data})"
                parts_to_append.append(
                    types.Part(text=f"\n\n**Reference:** {name}\n{md}\n")
                )
        callback_context.state["_reference_images_shown"] = True

    # Inject the candidate image
    candidate_uri = callback_context.state.get("candidate_image_uri")
    if candidate_uri:
        b64_data, mime_type = image_to_base64(candidate_uri)
        if b64_data:
            markdown_img = f"![candidate_image](data:{mime_type};base64,{b64_data})"
            attempt = callback_context.state.get("attempt", 1)
            parts_to_append.append(
                types.Part(text=f"\n\n**Candidate (attempt {attempt}):**\n{markdown_img}\n")
            )

    for part in parts_to_append:
        llm_response.content.parts.append(part)
    return None


def extract_uploaded_images(callback_context, llm_request):
    """before_model_callback: detect user-uploaded images, save to GCS.

    When a user uploads images directly in the ADK chat, they arrive as
    inline_data parts. This callback writes them to GCS and replaces the
    inline data with a text placeholder containing the GCS URI, so the
    root agent can parse and use it like any other GCS URI.
    """
    for content in llm_request.contents:
        if content.role != "user":
            continue
        new_parts = []
        for part in content.parts:
            if hasattr(part, "inline_data") and part.inline_data is not None:
                data = part.inline_data.data
                mime = part.inline_data.mime_type or "image/png"
                ext = mime.split("/")[-1]
                if ext == "jpeg":
                    ext = "jpg"
                filename = f"{uuid.uuid4().hex[:8]}.{ext}"
                gcs_uri = f"gs://{BUCKET_NAME}/uploads/{filename}"
                write_to_gcs(data, gcs_uri)
                new_parts.append(
                    types.Part(text=f"[Uploaded image saved to: {gcs_uri}]")
                )
            else:
                new_parts.append(part)
        content.parts = new_parts
    return None


def save_product_results(callback_context):
    """after_agent_callback: save evaluation results and reset per-product state.

    Called after EvaluationPipeline completes. Appends the current product's
    results to the all_products accumulator and resets per-product state keys
    so the next product starts clean.
    """
    all_products = callback_context.state.get("all_products", [])
    all_products.append({
        "sku_id": callback_context.state.get("sku_id"),
        "image_uris": callback_context.state.get("image_uris"),
        "ground_truth_description": callback_context.state.get("ground_truth_description"),
        "evaluation_history": callback_context.state.get("evaluation_history", []),
        "evaluation_passed": callback_context.state.get("evaluation_passed", False),
    })
    callback_context.state["all_products"] = all_products

    # Reset per-product state for next iteration
    callback_context.state["sku_id"] = None
    callback_context.state["image_uris"] = None
    callback_context.state["ground_truth_description"] = None
    callback_context.state["current_description"] = None
    callback_context.state["evaluation_history"] = []
    callback_context.state["evaluation_passed"] = False
    callback_context.state["attempt"] = 1
    callback_context.state["gecko_score"] = None
    callback_context.state["rubric_verdicts"] = None
    callback_context.state["failing_verdicts_text"] = None
    callback_context.state["candidate_image_uri"] = None
    callback_context.state["_reference_images_shown"] = False

    return None


def cleanup_image_data(callback_context, llm_request):
    """before_model_callback: strip base64 image data from request contents.

    Replaces inline base64 markdown images with lightweight placeholder tags
    to prevent token bloat if conversation history is ever included.
    """
    pattern = (
        r"!\[[^\]]*\]\(data:image/"
        r"(?:jpeg|png|gif|bmp|webp);base64,[A-Za-z0-9+/=\s]+\)"
    )
    for content in llm_request.contents:
        for part in content.parts:
            if hasattr(part, "text") and part.text:
                part.text = re.sub(pattern, "[image]", part.text)
    return None
