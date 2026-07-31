"""Coordinator 自唤醒工具。提醒持久化在 conversation 数据库中。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field

from cloudra import events
from cloudra.database import ConversationDB, aretry_on_locked, get_database_path
from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema


class ScheduleInput(input_schema):
    action: Literal["create", "list", "cancel"] = Field(
        default="create",
        description="create 创建提醒，list 查看仍在等待的提醒，cancel 取消提醒。",
    )
    message: Optional[str] = Field(
        default=None,
        description="醒来时送回给 Agent 的提醒内容。create 时必填，应包含醒来后要检查什么。",
    )
    wake_at: Optional[str] = Field(
        default=None,
        description="带时区的 ISO 8601 唤醒时间，例如 2026-07-28T18:30:00+08:00。",
    )
    delay_seconds: Optional[float] = Field(
        default=None,
        ge=0,
        description="从现在起多少秒后唤醒。与 wake_at 二选一。",
    )
    schedule_id: Optional[int] = Field(
        default=None,
        description="要取消的提醒 ID；cancel 时必填。",
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
        "让当前 Agent 在未来自行醒来并收到指定提醒，适合持续监控后台计算或稍后复查状态。"
        "提醒存在时当前任务会在后台保持等待；醒来后可根据新状态再次设置下一次提醒。"
        "使用 list 查看所有尚未触发的提醒，使用 cancel 按 schedule_id 取消过时或已被替代的提醒。"
        "多个 create 提醒会彼此独立地全部触发，不会自动覆盖。"
    )
    input_schema: Any = ScheduleInput
    output_schema: Any = ScheduleOutput

    def is_manage(self) -> bool:
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
            raise ValueError("wake_at 必须包含时区，避免后台任务在不同时区下提前或延后唤醒")
        return parsed.timestamp()

    async def tool_call(self, user_input: ScheduleInput, session: Session) -> ScheduleOutput:
        conversation_id, agent_id = self._identity()
        db = ConversationDB.from_path(get_database_path(conversation_id))
        await db.ainit()

        if user_input.action == "list":
            async with db.aconnect() as con:
                cur = await con.execute(
                    """
                    SELECT id, content, wake_at FROM scheduled_reminders
                    WHERE conversation_id=? AND agent_id=? AND state='pending'
                    ORDER BY wake_at
                    """,
                    (conversation_id, agent_id),
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
                message=f"共有 {len(schedules)} 个待触发提醒。",
                schedules=schedules,
            )

        if user_input.action == "cancel":
            if user_input.schedule_id is None:
                return ScheduleOutput(is_success=False, message="cancel 必须提供 schedule_id。")

            async def cancel() -> int:
                async with db.aconnect() as con:
                    cur = await con.execute(
                        """
                        UPDATE scheduled_reminders SET state='cancelled'
                        WHERE id=? AND conversation_id=? AND agent_id=? AND state='pending'
                        """,
                        (user_input.schedule_id, conversation_id, agent_id),
                    )
                    await con.commit()
                    return cur.rowcount

            changed = await aretry_on_locked(cancel)
            if changed:
                await events.aemit(conversation_id, "schedule_changed")
            return ScheduleOutput(
                is_success=changed > 0,
                message="提醒已取消。" if changed else "未找到可取消的待触发提醒。",
                schedule_id=user_input.schedule_id,
            )

        if not user_input.message or not user_input.message.strip():
            return ScheduleOutput(is_success=False, message="create 必须提供非空 message。")
        if (user_input.wake_at is None) == (user_input.delay_seconds is None):
            return ScheduleOutput(
                is_success=False,
                message="create 必须且只能提供 wake_at 或 delay_seconds 其中一个。",
            )

        try:
            wake_timestamp = (
                self._parse_wake_at(user_input.wake_at)
                if user_input.wake_at is not None
                else time.time() + float(user_input.delay_seconds)
            )
        except (TypeError, ValueError) as exc:
            return ScheduleOutput(is_success=False, message=f"无效的唤醒时间：{exc}")

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
            message=f"提醒已安排，Agent 将于 {wake_iso} 醒来。",
            schedule_id=schedule_id,
            wake_at=wake_iso,
        )


def get_class():
    return Schedule
