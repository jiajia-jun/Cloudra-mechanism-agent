from pydantic import Field
from typing import Any
from cloudra.tools_class import Tool, input_schema, output_schema
from cloudra.session_class import Session


class StopTool_input_schema(input_schema):
    reason: str = Field(
        default="",
        description="停止原因，可选"
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
        "结束当前任务并停止 ReAct 循环。"
        "当 agent 判断任务已完成、无需继续推理或行动时调用此工具。"
        "调用后当前循环轮次内的其他工具仍会执行完毕，随后整个 ReAct 循环终止。"
    )
    input_schema: Any = StopTool_input_schema
    output_schema: Any = StopTool_output_schema

    async def tool_call(
        self,
        user_input: StopTool_input_schema,
        session: Session
    ) -> StopTool_output_schema:
        """不做任何业务操作，仅返回停止确认。"""
        return StopTool_output_schema(
            stopped=True,
            message=f"任务已停止。原因：{user_input.reason}" if user_input.reason else "任务已停止"
        )


def get_class():
    return StopTool
