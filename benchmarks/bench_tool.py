from typing import Any

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema


class BenchTool_input_schema(input_schema):
    answer: str = Field(
        default="",
        description="【核心参数】你的最终提交答案。请在此处填入干净的答案文本（例如选项字母、数值或具体的推断结果）。"
    )

class BenchTool_output_schema(output_schema):
    is_success: bool = Field(
        default=True,
        description="是否成功记录"
    )
    message: str = Field(
        default="答案已成功提交到后台评分系统。",
        description="系统反馈"
    )

class BenchTool(Tool):
    tool_id: str = 't-bench'
    tool_name: str = 'submit_benchmark_answer'
    tool_description: str = (
        "【测试专用交卷工具】当你处于 Benchmark/考试模式并且已经得出了最终的答案时，"
        "必须调用此工具将答案提交到系统评测端。\n"
        "【注意】本工具仅负责记录分数，调用成功后并不会终止你的思考，"
        "因此你必须在收到“提交成功”的反馈后，紧接着调用 stop 工具来结束整个任务。"
    )
    input_schema: Any = BenchTool_input_schema
    output_schema: Any = BenchTool_output_schema

    async def tool_call(
        self,
        user_input: BenchTool_input_schema,
        session: Session
    ) -> BenchTool_output_schema:
        # 核心逻辑：严格遵循架构纯洁性，绝不污染 Agent 或 Session 实例。
        # 通过 Conversation 容器，将答案以文件形式固化到当前会话的物理沙箱中。
        import json
        import os

        from cloudra.conversation_class import Conversation

        if hasattr(self, 'subagent') and self.subagent and hasattr(self.subagent, 'conversation_id'):
            conv = Conversation(conv_id=self.subagent.conversation_id)
            ans_path = os.path.join(conv.path, "benchmark_answer.json")
            with open(ans_path, 'w', encoding='utf-8') as f:
                json.dump({"answer": user_input.answer.strip()}, f)

        return BenchTool_output_schema(
            is_success=True,
            message="交卷成功！后台评测系统已记录该题答案。请立即调用 stop 工具以彻底结束当前推理循环。"
        )

def get_class():
    return BenchTool
