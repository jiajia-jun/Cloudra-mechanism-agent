"""v2-native schedule reminders: events + in-memory timers.

The legacy ``schedule`` tool wrote ``scheduled_reminders`` rows and relied on
a v1 waiter that runtime_v2 never ran, so agents that ``stop`` after
scheduling slept forever.  This broker is intercepted by
``LegacyToolExecutor`` (same pattern as subagent_bridge / hub_bridge):

- create/list/cancel are projections over ``reminder.scheduled`` /
  ``reminder.cancelled`` / ``reminder.fired``
- ``schedule_id`` is the scheduled event's monotonic project ``seq``
- firing goes through ``agent.message`` (``[Reminder] ...``), which already
  reopens a terminal agent and schedules a new run
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import AgentSession, Command

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

logger = logging.getLogger(__name__)

_REMINDER_TYPES = {"reminder.scheduled", "reminder.cancelled", "reminder.fired"}


def _parse_wake_at(value: str) -> float:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(
            "wake_at must include a timezone so the reminder does not fire early or late across timezones"
        )
    return parsed.timestamp()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat()


def _ok(summary: str, **data: Any) -> ToolResult:
    payload = {"is_success": True, "message": summary, **data}
    return ToolResult(is_success=True, summary=summary, data=payload)


def _err(message: str) -> ToolResult:
    return ToolResult(
        is_success=False,
        summary=message,
        data={"is_success": False, "message": message},
    )


class ReminderBroker:
    def __init__(self, core: "RuntimeCore") -> None:
        self.core = core
        self._timers: dict[tuple[str, int], asyncio.Task] = {}

    async def close(self) -> None:
        tasks = list(self._timers.values())
        self._timers.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------ projection

    def pending(self, session_id: str) -> list[dict[str, Any]]:
        agent = self.core.agents.get(session_id)
        if agent is None:
            return []
        return self._pending_in_project(agent.project_id, session_id=session_id)

    def _pending_in_project(
        self, project_id: str, *, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        live: dict[int, dict[str, Any]] = {}
        for env in self.core.event_log.query_project(
            project_id, types=_REMINDER_TYPES, limit=10_000
        ):
            if env.type == "reminder.scheduled":
                if session_id is not None and env.session_id != session_id:
                    continue
                live[env.seq] = {
                    "schedule_id": env.seq,
                    "session_id": env.session_id,
                    "project_id": env.project_id,
                    "message": str(env.data.get("message") or ""),
                    "wake_at": env.data.get("wake_at"),
                    "wake_ts": float(env.data.get("wake_ts") or 0.0),
                }
            else:
                sid = env.data.get("schedule_id")
                if sid is not None:
                    live.pop(int(sid), None)
        return sorted(live.values(), key=lambda row: row["wake_ts"])

    def _all_pending(self) -> list[dict[str, Any]]:
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for agent in self.core.agents.values():
            if agent.project_id in seen:
                continue
            seen.add(agent.project_id)
            rows.extend(self._pending_in_project(agent.project_id))
        return rows

    # ------------------------------------------------------------------ events

    async def _emit(
        self,
        type: str,
        *,
        project_id: str,
        session_id: str,
        data: dict[str, Any],
    ):
        agent = self.core.agents.get(session_id)
        run_id = None
        if agent is not None and agent.current_run is not None:
            run_id = agent.current_run.run_id
        envelope = self.core.event_log.append(
            type,
            stream="agent",
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            data=data,
        )
        await self.core.event_hub.publish(envelope)
        return envelope

    # ------------------------------------------------------------------ arm / fire

    def _cancel_timer(self, project_id: str, schedule_id: int) -> None:
        task = self._timers.pop((project_id, schedule_id), None)
        if task is not None:
            task.cancel()

    def _arm(self, row: dict[str, Any]) -> None:
        project_id = row["project_id"]
        schedule_id = int(row["schedule_id"])
        session_id = row["session_id"]
        if session_id is None:
            return
        self._cancel_timer(project_id, schedule_id)
        delay = max(0.0, float(row["wake_ts"]) - time.time())
        key = (project_id, schedule_id)

        async def _wait_and_fire() -> None:
            try:
                if delay:
                    await asyncio.sleep(delay)
                await self._fire(project_id, session_id, schedule_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("reminder %s failed to fire", schedule_id)
            finally:
                self._timers.pop(key, None)

        self._timers[key] = asyncio.create_task(_wait_and_fire())

    async def _fire(self, project_id: str, session_id: str, schedule_id: int) -> None:
        pending = self._pending_in_project(project_id, session_id=session_id)
        row = next((item for item in pending if item["schedule_id"] == schedule_id), None)
        if row is None:
            return
        await self._emit(
            "reminder.fired",
            project_id=project_id,
            session_id=session_id,
            data={"schedule_id": schedule_id, "message": row["message"]},
        )
        self._cancel_timer(project_id, schedule_id)
        from cloudra.runtime_v2.commands import CommandBus

        content = f"[Reminder] {row['message']}".strip()
        await CommandBus(self.core).execute(
            Command(
                type="agent.message",
                target={"session_id": session_id},
                payload={"content": content},
                actor="system",
            )
        )

    async def rearm_all(self) -> None:
        """Rebuild timers from the event projection; overdue reminders fire now."""
        await self.close()
        for row in self._all_pending():
            self._arm(row)

    # ------------------------------------------------------------------ tool

    async def handle(self, agent: AgentSession, call: ToolCall) -> ToolResult:
        args = call.arguments or {}
        action = str(args.get("action") or "create")
        if action == "list":
            schedules = [
                {
                    "schedule_id": row["schedule_id"],
                    "message": row["message"],
                    "wake_at": row["wake_at"],
                }
                for row in self.pending(agent.id)
            ]
            return _ok(
                f"{len(schedules)} pending reminder(s).",
                schedule_id=None,
                wake_at=None,
                schedules=schedules,
            )
        if action == "cancel":
            raw_id = args.get("schedule_id")
            if raw_id is None:
                return _err("cancel requires schedule_id.")
            schedule_id = int(raw_id)
            row = next(
                (item for item in self.pending(agent.id) if item["schedule_id"] == schedule_id),
                None,
            )
            if row is None:
                return _err("No pending reminder found to cancel.")
            self._cancel_timer(agent.project_id, schedule_id)
            await self._emit(
                "reminder.cancelled",
                project_id=agent.project_id,
                session_id=agent.id,
                data={"schedule_id": schedule_id},
            )
            return _ok("Reminder cancelled.", schedule_id=schedule_id, schedules=[])
        if action != "create":
            return _err(f"Unknown action: {action}")
        message = str(args.get("message") or "").strip()
        if not message:
            return _err("create requires a non-empty message.")
        wake_at = args.get("wake_at")
        delay_seconds = args.get("delay_seconds")
        if (wake_at is None) == (delay_seconds is None):
            return _err("create must provide exactly one of wake_at or delay_seconds.")
        try:
            wake_ts = (
                _parse_wake_at(str(wake_at))
                if wake_at is not None
                else time.time() + float(delay_seconds)
            )
        except (TypeError, ValueError) as exc:
            return _err(f"Invalid wake time: {exc}")
        wake_iso = _iso(wake_ts)
        envelope = await self._emit(
            "reminder.scheduled",
            project_id=agent.project_id,
            session_id=agent.id,
            data={"message": message, "wake_at": wake_iso, "wake_ts": wake_ts},
        )
        row = {
            "schedule_id": envelope.seq,
            "session_id": agent.id,
            "project_id": agent.project_id,
            "message": message,
            "wake_at": wake_iso,
            "wake_ts": wake_ts,
        }
        self._arm(row)
        return _ok(
            f"Reminder scheduled; the agent will wake at {wake_iso}.",
            schedule_id=envelope.seq,
            wake_at=wake_iso,
            schedules=[],
        )
