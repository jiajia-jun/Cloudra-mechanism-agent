from typing import Any

from pydantic import Field

from cloudra.context_manager import read_context_file
from cloudra.paths import context_path
from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "获取指定子 Agent 任务的完整执行报告。通过 Session ID 检索其完整的推理过程、"
    "工具调用记录以及最终结论。当 SubAgentLauncher 返回的简要结果不足以辅助决策时使用。"
)

class GetSubAgentReport_input_schema(input_schema):
    session_id: str = Field(description="要检索的子 Agent Session ID")
    detail_level: str = Field(
        default="full",
        description="报告详细程度: 'full' (完整上下文和日志), 'summary' (仅最终结论), 'steps' (仅推理步骤和工具调用)"
    )

class GetSubAgentReport_output_schema(output_schema):
    is_success: bool = Field(description="是否成功获取报告")
    agent_name: str = Field(default="", description="子 Agent 名称")
    report_content: str = Field(default="", description="报告详细内容")
    message: str = Field(default="", description="状态说明")

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
            return GetSubAgentReport_output_schema(is_success=False, message="无效的 Session ID 格式。")

        agent_id = parts[0]
        conv_id = getattr(self.subagent, 'conversation_id', 'default') if self.subagent else 'default'

        context_file = context_path(conv_id, agent_id, session_id)
        if not context_file.exists():
            context_file = context_path(conv_id, agent_id)

        if not context_file.exists():
            return GetSubAgentReport_output_schema(is_success=False, message=f"未找到 Agent ({agent_id}) 的上下文记录, session={session_id}。")

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
                    report_lines.append(f"【最终结论】: {content}")
                    break

                # 格式化输出
                prefix = f"[{role.upper()}]"
                if role == 'assistant' and 'reasoning_content' in block:
                    report_lines.append(f"{prefix} 推理: {block['reasoning_content']}")

                if content:
                    report_lines.append(f"{prefix}: {content}")

                if 'tool_calls' in block:
                    for tc in block['tool_calls']:
                        func = tc.get('function', {})
                        report_lines.append(f"-> 调用工具: {func.get('name')} (参数: {func.get('arguments')})")

            return GetSubAgentReport_output_schema(
                is_success=True,
                agent_name=agent_id,
                report_content="\n\n".join(report_lines),
                message="报告获取成功。"
            )

        except Exception as e:
            return GetSubAgentReport_output_schema(is_success=False, message=f"报告解析失败: {str(e)}")

def get_class():
    return GetSubAgentReport
