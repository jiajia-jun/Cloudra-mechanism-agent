from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema


class StopTool_input_schema(input_schema):
    reason: str = Field(
        default="",
        description="Reason for stopping, optional"
    )
    final_answer: str = Field(
        default="",
        description="[CRITICAL] For quiz/eval tasks, put your final concise answer here (e.g. A,B or 245.8). The tool wraps it in an [ANSWER] tag."
    )
    delivery_disposition: Literal["complete", "partial", "user_terminated"] = Field(
        default="complete",
        description=(
            "DAG-mode delivery declaration: complete must pass evidence-derived coverage; "
            "partial finishes with remaining gaps (this is a final delivery statement, not a pause); "
            "user_terminated means the user asked to stop. "
            "If background jobs/reminders are still pending, stop only suspends — no audit and no disposition is recorded."
        ),
    )
    approval_id: str | None = Field(
        default=None,
        description="Durable Supervisor exit decision id approving a partial result.",
    )
    user_stop_event_id: str | None = Field(
        default=None,
        description="Event id of the user's explicit stop/cancel command.",
    )


class StopTool_output_schema(output_schema):
    stopped: bool = Field(
        default=True,
        description="Whether the loop was stopped"
    )
    message: str = Field(
        default="Task stopped",
        description="Stop confirmation message"
    )


class StopTool(Tool):
    tool_id: str = 't-stop'
    tool_name: str = 'stop'
    tool_description: str = (
        "End the current task and stop the ReAct loop; remaining tools in this round still finish, then the loop terminates. "
        "Use for: the task is done, the goal is met, or you confirm you cannot proceed and need to wrap up. "
        "Also used to suspend while waiting on background work: schedule a wake-up first, then stop; "
        "the session is persisted as waiting (not completed), and the loop resumes when the reminder fires or an external event arrives — "
        "suspension is not delivery, so DAG mode does not run a delivery audit at this point. "
        "Do not use for: questions that still need the user (use ask_user), or stopping early while later steps remain and no wake-up is scheduled. "
        "Note: for quiz/eval tasks, put the final concise answer in final_answer."
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

        msg = f"Task stopped. Reason: {user_input.reason}{ans_str}" if user_input.reason else f"Task stopped.{ans_str}"
        return StopTool_output_schema(
            stopped=True,
            message=msg
        )


def get_class():
    return StopTool
