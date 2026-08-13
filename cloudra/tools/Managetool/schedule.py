"""Agent 自唤醒工具。提醒持久化在 conversation 数据库中。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra import events
from cloudra.persistence.database import ConversationDB, aretry_on_locked, get_database_path


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
        # 自唤醒是 Agent 的时间通道：不触碰文件系统/系统状态，
        # 只写 conversation 库里的提醒表，全体 Agent（含只读 explorer）都可用。
        return True

    def _identity(self) -> tuple[str, str]:
        conversation_id = (
            getattr(self.subagent, "conversation_id", "default") if self.subagent else "default"
        ) or "default"
        agent_id = getattr(self.subagent, "id", "a-0") if self.subagent else "a-0"
        return conversation_id, agent_id

    @staticmethod
    def _parse_wake_at(value: str) -> float:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            raise ValueError("wake_at must include a timezone so the reminder does not fire early or late across timezones")
        return parsed.timestamp()

    async def tool_call(self, user_input: ScheduleInput, session: Session) -> ScheduleOutput:
        conversation_id, agent_id = self._identity()
        db = ConversationDB.from_path(get_database_path(conversation_id))
        await db.ainit()

        if user_input.action == "list":
            session_id = getattr(session, "id", None)
            # 有 session 身份时只看本 session 的提醒（含无 session 的旧提醒）；
            # 无身份（测试/旧调用）保持原行为，列出本 agent 全部。
            if session_id is not None:
                where = ("conversation_id=? AND agent_id=? AND state='pending' "
                         "AND (session_id IS NULL OR session_id=?)")
                params = (conversation_id, agent_id, session_id)
            else:
                where = "conversation_id=? AND agent_id=? AND state='pending'"
                params = (conversation_id, agent_id)
            async with db.aconnect() as con:
                cur = await con.execute(
                    f"""
                    SELECT id, content, wake_at FROM scheduled_reminders
                    WHERE {where}
                    ORDER BY wake_at
                    """,
                    params,
                )
                rows = await cur.fetchall()
            schedules = [
                {
                    "schedule_id": row[0],
                    "message": row[1],
                    "wake_at": datetime.fromtimestamp(row[2]).astimezone().isoformat(),
                }
                for row in rows
            ]
            return ScheduleOutput(
                is_success=True,
                message=f"{len(schedules)} pending reminder(s).",
                schedules=schedules,
            )

        if user_input.action == "cancel":
            if user_input.schedule_id is None:
                return ScheduleOutput(is_success=False, message="cancel requires schedule_id.")

            async def cancel() -> int:
                session_id = getattr(session, "id", None)
                if session_id is not None:
                    where = ("id=? AND conversation_id=? AND agent_id=? AND state='pending' "
                             "AND (session_id IS NULL OR session_id=?)")
                    params = (user_input.schedule_id, conversation_id, agent_id, session_id)
                else:
                    where = "id=? AND conversation_id=? AND agent_id=? AND state='pending'"
                    params = (user_input.schedule_id, conversation_id, agent_id)
                async with db.aconnect() as con:
                    cur = await con.execute(
                        f"UPDATE scheduled_reminders SET state='cancelled' WHERE {where}",
                        params,
                    )
                    await con.commit()
                    return cur.rowcount

            changed = await aretry_on_locked(cancel)
            if changed:
                await events.aemit(conversation_id, "schedule_changed")
            return ScheduleOutput(
                is_success=changed > 0,
                message="Reminder cancelled." if changed else "No pending reminder found to cancel.",
                schedule_id=user_input.schedule_id,
            )

        if not user_input.message or not user_input.message.strip():
            return ScheduleOutput(is_success=False, message="create requires a non-empty message.")
        if (user_input.wake_at is None) == (user_input.delay_seconds is None):
            return ScheduleOutput(
                is_success=False,
                message="create must provide exactly one of wake_at or delay_seconds.",
            )

        try:
            wake_timestamp = (
                self._parse_wake_at(user_input.wake_at)
                if user_input.wake_at is not None
                else time.time() + float(user_input.delay_seconds)
            )
        except (TypeError, ValueError) as exc:
            return ScheduleOutput(is_success=False, message=f"Invalid wake time: {exc}")

        async def create() -> int:
            async with db.aconnect() as con:
                cur = await con.execute(
                    """
                    INSERT INTO scheduled_reminders
                    (conversation_id, agent_id, session_id, content, wake_at, state, created_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        conversation_id,
                        agent_id,
                        getattr(session, "id", None),
                        user_input.message.strip(),
                        wake_timestamp,
                        time.time(),
                    ),
                )
                await con.commit()
                return cur.lastrowid

        schedule_id = await aretry_on_locked(create)
        await events.aemit(conversation_id, "schedule_changed")
        wake_iso = datetime.fromtimestamp(wake_timestamp).astimezone().isoformat()
        return ScheduleOutput(
            is_success=True,
            message=f"Reminder scheduled; the agent will wake at {wake_iso}.",
            schedule_id=schedule_id,
            wake_at=wake_iso,
        )


def get_class():
    return Schedule
