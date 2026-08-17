"""Agent 自唤醒工具。v2 执行由 runtime_v2.reminders.ReminderBroker 拦截。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema


class ScheduleInput(input_schema):
    action: Literal["create", "list", "cancel"] = Field(
        default="create",
        description="create a reminder, list still-pending reminders, or cancel a reminder.",
    )
    message: Optional[str] = Field(
        default=None,
        description=(
            "Reminder text delivered back to the Agent on wake. Required for create. "
            "Write it as operating instructions to your future self: what to check "
            "(log paths, job_id, sub-agent sessions), what counts as done, "
            "and which old reminders to cancel afterward. A vague 'check on it' leaves you with nothing to do on wake."
        ),
    )
    wake_at: Optional[str] = Field(
        default=None,
        description="Wake time as timezone-aware ISO 8601, e.g. 2026-07-28T18:30:00+08:00.",
    )
    delay_seconds: Optional[float] = Field(
        default=None,
        ge=0,
        description="Wake this many seconds from now. Mutually exclusive with wake_at.",
    )
    schedule_id: Optional[int] = Field(
        default=None,
        description="Reminder ID to cancel; required for cancel.",
    )


class ScheduleOutput(output_schema):
    is_success: bool
    message: str
    schedule_id: Optional[int] = None
    wake_at: Optional[str] = None
    schedules: list[dict] = Field(default_factory=list)


class Schedule(Tool):
    tool_id: str = "t-13"
    tool_name: str = "schedule"
    tool_description: str = (
        "Have the current Agent wake itself later with a given reminder — for monitoring background compute or rechecking status. "
        "While a reminder exists, the current task stays waiting in the background; after waking you can set the next reminder from the new state. "
        "message is a memo to yourself: on wake only it and the then-current runtime state are available, "
        "so spell out what to check, the done criteria, and the next action. "
        "Use list to see all unfired reminders, and cancel with schedule_id to drop stale or superseded ones. "
        "Multiple create reminders all fire independently; they do not overwrite each other."
    )
    input_schema: Any = ScheduleInput
    output_schema: Any = ScheduleOutput

    def is_read(self) -> bool:
        # 自唤醒是 Agent 的时间通道：不触碰文件系统/系统状态，全体 Agent（含只读 explorer）都可用。
        return True

    async def tool_call(self, user_input: ScheduleInput, session: Session) -> ScheduleOutput:
        # Legacy SQLite waiter is gone; runtime_v2 LegacyToolExecutor intercepts
        # this tool name into ReminderBroker.  The body is a fallback only.
        return ScheduleOutput(
            is_success=False,
            message=(
                "[System error] schedule is handled by runtime_v2; "
                "the legacy reminder table is no longer consulted."
            ),
        )


def get_class():
    return Schedule
