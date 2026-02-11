from google.adk.agents.llm_agent import LlmAgent

from ..config import AGENT_MODEL
from ..callbacks import cleanup_image_data
from ..tools.reporting import create_html_report

report_agent = LlmAgent(
    name="ReportAgent",
    model=AGENT_MODEL,
    include_contents="none",
    before_model_callback=cleanup_image_data,
    instruction="""You are a report generation coordinator.

Generate an HTML evaluation report by calling the create_html_report tool.

After the report is generated, output a summary for the user including:
- Product SKU: {sku_id}
- Evaluation result (passed or needs review): {evaluation_passed}
- Final score: {gecko_score}
- Total attempts made
- Report file location""",
    tools=[create_html_report],
    description=(
        "Generates an HTML evaluation report from the pipeline results."
    ),
)
