import html
import os

from google.adk.tools.tool_context import ToolContext

from .gcs import image_to_base64


def _build_product_section(product: dict) -> str:
    """Build the HTML section for a single product."""
    sku_id = product.get("sku_id", "unknown")
    ground_truth = product.get("ground_truth_description", "")
    source_uris_raw = product.get("image_uris", "")
    source_uris = [u.strip() for u in source_uris_raw.split(",") if u.strip()]
    history = product.get("evaluation_history", [])
    passed = product.get("evaluation_passed", False)

    # --- Source images HTML ---
    source_images_html = ""
    for uri in source_uris:
        name = uri.split("/")[-1]
        b64_data, mime_type = image_to_base64(uri)
        if b64_data:
            img_tag = (
                f'<img src="data:{mime_type};base64,{b64_data}" '
                f'alt="{html.escape(name)}" '
                f'style="max-height:160px;max-width:200px;border-radius:4px;'
                f'border:1px solid #ccc;">'
            )
        else:
            img_tag = (
                f'<div style="height:160px;width:160px;background:#eee;'
                f"display:flex;align-items:center;justify-content:center;"
                f'border:1px solid #ccc;border-radius:4px;">'
                f'<span style="font-size:0.8em;color:#555;">'
                f"{html.escape(name)}</span></div>"
            )
        source_images_html += (
            f'<div style="text-align:center">{img_tag}'
            f'<div style="font-size:0.8em;margin-top:4px">'
            f"{html.escape(name)}</div></div>"
        )

    # --- Attempts HTML ---
    attempts_html = ""
    for entry in history:
        attempt_num = entry["attempt"]
        score = entry["score"]
        passing = entry.get("passing_verdicts", [])
        failing = entry.get("failing_verdicts", [])
        image_uri = entry.get("image_uri", "")

        score_class = (
            "score-high" if score >= 0.7
            else "score-medium" if score >= 0.4
            else "score-low"
        )

        # Candidate image
        img_html = ""
        if image_uri:
            b64_data, mime_type = image_to_base64(image_uri)
            if b64_data:
                img_html = (
                    f'<img src="data:{mime_type};base64,{b64_data}" '
                    f'alt="Attempt {attempt_num}" '
                    f'style="max-width:100%;border-radius:4px;border:1px solid #eee;">'
                )
            else:
                img_html = (
                    f'<div class="placeholder">Could not load: '
                    f"{html.escape(image_uri.split('/')[-1])}</div>"
                )

        # Verdicts
        verdicts_html = "<ul class='rubric-list'>"
        for v in passing:
            verdicts_html += (
                f"<li class='rubric-item rubric-pass'>"
                f"<span class='icon'>&#10003;</span> {html.escape(str(v))}</li>"
            )
        for v in failing:
            verdicts_html += (
                f"<li class='rubric-item rubric-fail'>"
                f"<span class='icon'>&#10007;</span> {html.escape(str(v))}</li>"
            )
        verdicts_html += "</ul>"

        total = len(passing) + len(failing)
        open_attr = "open" if score < 0.7 else ""

        attempts_html += f"""
        <details class="attempt" {open_attr}>
          <summary>
            <span class="attempt-label">Attempt {attempt_num}</span>
            <span class="score-badge {score_class}">{score:.2f}</span>
            <span class="stats">{len(passing)}/{total} passed</span>
          </summary>
          <div class="attempt-content">
            <div class="attempt-image">{img_html}</div>
            <div class="attempt-verdicts">{verdicts_html}</div>
          </div>
        </details>
        """

    # --- Final score ---
    final_score = history[-1]["score"] if history else 0.0
    result_label = "PASSED" if passed else "NEEDS REVIEW"
    result_color = "#188038" if passed else "#d93025"

    return f"""
    <div class="product-section">
      <h2 class="product-header" style="color:{result_color};">
        {html.escape(sku_id)} &mdash; {result_label} (Score: {final_score:.2f})
      </h2>
      <div class="meta">
        <div class="meta-images">{source_images_html}</div>
        <div class="meta-prompt">{html.escape(ground_truth)}</div>
      </div>
      {attempts_html}
    </div>
    """


def create_html_report(tool_context: ToolContext) -> dict:
    """Generate a combined HTML evaluation report for all evaluated products.

    Reads from tool_context.state["all_products"] (list of product result dicts).

    Returns:
        dict with 'report_path' and 'summary'.
    """
    all_products = tool_context.state.get("all_products", [])

    if not all_products:
        return {"status": "error", "message": "No products to report on."}

    # Build per-product sections
    product_sections = []
    summaries = []
    for product in all_products:
        product_sections.append(_build_product_section(product))
        sku_id = product.get("sku_id", "unknown")
        history = product.get("evaluation_history", [])
        passed = product.get("evaluation_passed", False)
        final_score = history[-1]["score"] if history else 0.0
        result_label = "PASSED" if passed else "NEEDS REVIEW"
        summaries.append(
            f"SKU: {sku_id} | Result: {result_label} | "
            f"Score: {final_score:.2f} | Attempts: {len(history)}"
        )

    sections_html = "\n<hr class='product-divider'>\n".join(product_sections)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Product Fidelity Report</title>
<style>
  body {{ font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif; margin:0; background:#f4f4f4; color:#333; }}
  .container {{ max-width:1100px; margin:30px auto; background:#fff; padding:30px; border-radius:8px; box-shadow:0 2px 15px rgba(0,0,0,.08); }}
  h1 {{ color:#1a73e8; margin-top:0; border-bottom:2px solid #eee; padding-bottom:10px; }}
  .product-section {{ margin-bottom:30px; }}
  .product-header {{ margin-top:0; padding-bottom:8px; border-bottom:1px solid #eee; }}
  .product-divider {{ border:none; border-top:3px solid #e0e0e0; margin:30px 0; }}
  .meta {{ display:flex; gap:20px; margin-bottom:20px; background:#f8f9fa; padding:15px; border-radius:6px; }}
  .meta-images {{ display:flex; gap:12px; flex-wrap:wrap; }}
  .meta-prompt {{ flex:1; font-size:.9em; line-height:1.5; max-height:200px; overflow-y:auto; white-space:pre-wrap; background:#fff; padding:12px; border:1px solid #eee; border-radius:4px; }}
  .attempt {{ border:1px solid #e0e0e0; border-radius:8px; margin-bottom:10px; overflow:hidden; }}
  .attempt[open] {{ box-shadow:0 2px 8px rgba(0,0,0,.1); }}
  .attempt summary {{ padding:14px 18px; background:#fafafa; cursor:pointer; display:flex; align-items:center; gap:12px; list-style:none; }}
  .attempt summary::-webkit-details-marker {{ display:none; }}
  .attempt-label {{ font-weight:600; }}
  .attempt-content {{ display:flex; gap:20px; padding:18px; }}
  .attempt-image {{ flex:0 0 250px; }}
  .attempt-image img {{ max-width:100%; height:auto; }}
  .attempt-verdicts {{ flex:1; }}
  .score-badge {{ display:inline-block; padding:4px 12px; border-radius:14px; font-weight:bold; font-size:.9em; }}
  .score-high {{ background:#e6f4ea; color:#188038; }}
  .score-medium {{ background:#fef7e0; color:#b06000; }}
  .score-low {{ background:#fce8e6; color:#d93025; }}
  .stats {{ color:#666; font-size:.85em; }}
  .rubric-list {{ list-style:none; padding:0; margin:0; }}
  .rubric-item {{ margin-bottom:5px; padding:8px 10px; border-left:4px solid; border-radius:3px; font-size:.9em; }}
  .rubric-pass {{ border-color:#188038; background:#f6fef7; }}
  .rubric-fail {{ border-color:#d93025; background:#fef7f6; }}
  .icon {{ margin-right:6px; }}
  .placeholder {{ height:160px; display:flex; align-items:center; justify-content:center; background:#f0f0f0; border-radius:4px; font-size:.85em; color:#888; }}
</style>
</head>
<body>
<div class="container">
  <h1>Product Fidelity Report</h1>
  {sections_html}
</div>
</body>
</html>"""

    filename = "product_candidate_report.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    summary = (
        f"Total products: {len(all_products)}\n"
        + "\n".join(summaries)
    )

    return {"status": "success", "report_path": filename, "summary": summary}
