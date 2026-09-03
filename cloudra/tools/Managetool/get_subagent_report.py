from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "Fetch the full execution report of a given sub-agent task. Looks up the complete reasoning, "
    "tool-call log, and final conclusion by Session ID. Use when the brief result from subagent_launcher is not enough to decide."
)

class GetSubAgentReport_input_schema(input_schema):
    session_id: str = Field(description="Sub-agent Session ID to retrieve")
    detail_level: str = Field(
        default="full",
        description="Report detail: 'full' (full context and logs), 'summary' (final conclusion only), 'steps' (reasoning steps and tool calls only)"
    )

class GetSubAgentReport_output_schema(output_schema):
    is_success: bool = Field(description="Whether the report was retrieved")
    agent_name: str = Field(default="", description="Sub-agent name")
    report_content: str = Field(default="", description="Report body")
    message: str = Field(default="", description="Status note")

class GetSubAgentReport(Tool):
    tool_id: str = 't-report'
    tool_name: str = 'get_subagent_report'
    tool_description: str = description
    input_schema: Any = GetSubAgentReport_input_schema
    output_schema: Any = GetSubAgentReport_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: GetSubAgentReport_input_schema, session: Session) -> GetSubAgentReport_output_schema:
        # Legacy 报告检索已删除；runtime_v2 的 LegacyToolExecutor 在执行前按工具名
        # 拦截到 subagent_bridge，此 body 只是兜底。
        return GetSubAgentReport_output_schema(
            is_success=False,
            message="[System error] get_subagent_report is handled by runtime_v2; the legacy report path no longer exists.",
        )

def get_class():
    return GetSubAgentReport
