from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "Fetch the result of a dispatched sub-agent. By session_id: once the sub-agent reaches a terminal "
    "state (succeeded/failed/cancelled), returns its final emitted assistant message — for a crashed "
    "sub-agent, the recorded failure reason; while it is still running, only its current state is "
    "returned (ask again later). By group_id: returns the launch group's counters (state, "
    "pending/running counts) and per-item status including child session ids. Intermediate reasoning "
    "and the tool-call log are NOT included."
)

class GetSubAgentReport_input_schema(input_schema):
    session_id: str = Field(default="", description="Sub-agent Session ID to retrieve")
    group_id: str = Field(default="", description="Launch group ID to retrieve (returns group counters and per-item status)")

class GetSubAgentReport_output_schema(output_schema):
    is_success: bool = Field(description="Whether the report was retrieved")
    agent_name: str = Field(default="", description="Sub-agent name")
    report_content: str = Field(default="", description="Report body")
    message: str = Field(default="", description="Status note")
    group_id: str = Field(default="", description="Launch group ID, when querying a group")

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
