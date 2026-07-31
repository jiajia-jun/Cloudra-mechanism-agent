from typing import Any

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema


class StopTool_input_schema(input_schema):
    reason: str = Field(
        default="",
        description="停止原因，可选"
    )
    final_answer: str = Field(
        default="",
        description="【非常重要】如果是答题/评测任务，请务必在这里填入你的最终精简答案（例如 A,B 或 245.8）。工具会自动将其包裹为 [ANSWER] 标签。"
    )


class StopTool_output_schema(output_schema):
    stopped: bool = Field(
        default=True,
        description="是否成功停止"
    )
    message: str = Field(
        default="任务已停止",
        description="停止确认信息"
    )


class StopTool(Tool):
    tool_id: str = 't-stop'
    tool_name: str = 'stop'
    tool_description: str = (
        "结束当前任务并停止 ReAct 循环；调用后本轮其余工具仍会执行完毕，随后整个循环终止。"
        "适用：任务已完成、目标已达成，或确认无法继续推进需要收尾时。"
        "不适用：还需要向用户提问澄清（用 ask_user）、还有后续步骤没做完时不要提前 stop。"
        "注意：答题/评测任务务必在 final_answer 里填入最终精简答案。"
    )
    input_schema: Any = StopTool_input_schema
    output_schema: Any = StopTool_output_schema

    async def tool_call(
        self,
        user_input: StopTool_input_schema,
        session: Session
    ) -> StopTool_output_schema:
        """不做任何业务操作，仅返回停止确认。"""
        ans_str = ""
        if user_input.final_answer:
            ans_str = f" [ANSWER]{user_input.final_answer}[/ANSWER]"

        msg = f"任务已停止。原因：{user_input.reason}{ans_str}" if user_input.reason else f"任务已停止。{ans_str}"
        return StopTool_output_schema(
            stopped=True,
            message=msg
        )


def get_class():
    return StopTool
