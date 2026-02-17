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

Generate a combined HTML evaluation report for ALL evaluated products by calling
the create_html_report tool.

After the report is generated, output a summary including:
- Total products evaluated
- Per-product results (SKU, pass/fail, score)
- Report file location""",
    tools=[create_html_report],
    description=(
        "Generates an HTML evaluation report from the pipeline results."
    ),
)
