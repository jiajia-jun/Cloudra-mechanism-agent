import os
import json
from pydantic import Field
from typing import Any, Optional
from cloudra.tools_class import Tool, input_schema, output_schema
from cloudra.session_class import Session
from cloudra.config import get_config

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
        data_dir = get_config().data_dir
        
        # 1. 尝试从 session_id 推断路径
        # session_id 格式通常为 {agent_id}_{timestamp}，如 a-1_20260523...
        parts = session_id.split('_')
        if not parts:
            return GetSubAgentReport_output_schema(is_success=False, message="无效的 Session ID 格式。")
        
        agent_id = parts[0]
        conv_id = getattr(self.subagent, 'conversation_id', 'default') if self.subagent else 'default'
        
        # 尝试定位 context 文件 (最权威的完整历史)
        context_file = os.path.join(data_dir, 'conversations', conv_id, 'contexts', f"{agent_id}.json")
        if not os.path.exists(context_file):
             # 兜底尝试默认路径
             context_file = os.path.join(data_dir, 'contexts', f"{agent_id}.json")

        if not os.path.exists(context_file):
            return GetSubAgentReport_output_schema(is_success=False, message=f"未找到该 Agent ({agent_id}) 的上下文记录。")

        try:
            with open(context_file, 'r', encoding='utf-8') as f:
                context_data = json.load(f)
            
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
