from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.context_manager import read_context_file
from cloudra.persistence.paths import context_path

description = (
    "Fetch the full execution report of a given sub-agent task. Looks up the complete reasoning, "
    "tool-call log, and final conclusion by Session ID. Use when the brief result from SubAgentLauncher is not enough to decide."
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
        session_id = user_input.session_id

        parts = session_id.split('_')
        if not parts:
            return GetSubAgentReport_output_schema(is_success=False, message="Invalid Session ID format.")

        agent_id = parts[0]
        conv_id = getattr(self.subagent, 'conversation_id', 'default') if self.subagent else 'default'

        context_file = context_path(conv_id, agent_id, session_id)
        if not context_file.exists():
            context_file = context_path(conv_id, agent_id)

        if not context_file.exists():
            return GetSubAgentReport_output_schema(is_success=False, message=f"No context record found for Agent ({agent_id}), session={session_id}.")

        try:
            # 同时支持 JSONL 新格式与旧版单 JSON 数组格式
            context_data = read_context_file(str(context_file))

            # 根据详细程度过滤内容
            report_lines = []
            for block in context_data:
                role = block.get('role')
                content = block.get('content', '')

                if user_input.detail_level == 'summary' and role != 'assistant':
                    continue

                # 如果是最后一条消息且只要 summary，则只取它
                if user_input.detail_level == 'summary' and block == context_data[-1]:
                    report_lines.append(f"[Final conclusion]: {content}")
                    break

                # 格式化输出
                prefix = f"[{role.upper()}]"
                if role == 'assistant' and 'reasoning_content' in block:
                    report_lines.append(f"{prefix} reasoning: {block['reasoning_content']}")

                if content:
                    report_lines.append(f"{prefix}: {content}")

                if 'tool_calls' in block:
                    for tc in block['tool_calls']:
                        func = tc.get('function', {})
                        report_lines.append(f"-> tool call: {func.get('name')} (args: {func.get('arguments')})")

            return GetSubAgentReport_output_schema(
                is_success=True,
                agent_name=agent_id,
                report_content="\n\n".join(report_lines),
                message="Report retrieved."
            )

        except Exception as e:
            return GetSubAgentReport_output_schema(is_success=False, message=f"Failed to parse report: {str(e)}")

def get_class():
    return GetSubAgentReport
