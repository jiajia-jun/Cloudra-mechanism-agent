"""v2-native schedule reminders: events + in-memory timers / check pollers.

The legacy ``schedule`` tool wrote ``scheduled_reminders`` rows and relied on
a v1 waiter that runtime_v2 never ran, so agents that ``stop`` after
scheduling slept forever.  This broker is intercepted by
``LegacyToolExecutor`` (same pattern as subagent_bridge / hub_bridge):

- create/list/cancel are projections over ``reminder.scheduled`` /
  ``reminder.cancelled`` / ``reminder.fired``
- ``schedule_id`` is the scheduled event's monotonic project ``seq``
- firing goes through ``agent.message`` (``[Reminder] ...``), which already
  reopens a terminal agent and schedules a new run
- optional ``check_command`` arms a read-only poller alongside the timeout;
  first of (exit 0, timeout) wins
"""

from __future__ import annotations

import asyncio
import logging
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from cloudra.infra.tool_errors import validation_feedback
from cloudra.runtime_v2.check_command import (
    CHECK_RUN_TIMEOUT_SECONDS,
    CheckCommandError,
    run_check_command,
    validate_check_command,
    validate_interval,
)
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


def _wake_content(message: str, *, reason: str | None, output: str = "") -> str:
    body = f"[Reminder] {message}".strip()
    if not reason:
        return body
    lines = [body, f"[Wake reason: {reason}]"]
    extra = (output or "").strip()
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def _row_from_event(env) -> dict[str, Any]:
    data = env.data
    check_command = data.get("check_command")
    interval = data.get("interval_seconds")
    return {
        "schedule_id": env.seq,
        "session_id": env.session_id,
        "project_id": env.project_id,
        "message": str(data.get("message") or ""),
        "wake_at": data.get("wake_at"),
        "wake_ts": float(data.get("wake_ts") or 0.0),
        "check_command": str(check_command) if check_command else None,
        "interval_seconds": float(interval) if interval is not None else None,
    }


class ReminderBroker:
    def __init__(self, core: "RuntimeCore") -> None:
        self.core = core
        self._timers: dict[tuple[str, int], list[asyncio.Task]] = {}
        self._last_check: dict[tuple[str, int], tuple[int, str]] = {}
        self._fire_lock = asyncio.Lock()
        self._pending: dict[str, dict[int, dict[str, Any]]] = {}
        self._through: dict[str, int] = {}

    def apply(self, event) -> None:
        if event.type not in _REMINDER_TYPES or event.seq <= self._through.get(event.project_id, 0):
            return
        self._through[event.project_id] = event.seq
        rows = self._pending.setdefault(event.project_id, {})
        if event.type == "reminder.scheduled":
            rows[event.seq] = _row_from_event(event)
        elif event.data.get("schedule_id") is not None:
            rows.pop(int(event.data["schedule_id"]), None)

    def snapshot(self) -> dict[str, Any]:
        return deepcopy({"pending": self._pending, "through": self._through})

    def restore(self, payload: dict[str, Any]) -> None:
        self._pending = {pid: {int(key): deepcopy(row) for key, row in rows.items()}
                         for pid, rows in payload.get("pending", {}).items()}
        self._through = dict(payload.get("through", {}))

    def prune_projects(self, project_ids: set[str]) -> None:
        """Cancel only local reminder timers belonging to deleted projects."""
        for mapping in (self._pending, self._through):
            for project_id in mapping.keys() - project_ids:
                mapping.pop(project_id)
        for project_id, schedule_id in list(self._timers):
            if project_id not in project_ids:
                self._cancel_timer(project_id, schedule_id)
        for key in list(self._last_check):
            if key[0] not in project_ids:
                self._last_check.pop(key)

    async def close(self) -> None:
        groups = list(self._timers.values())
        self._timers.clear()
        self._last_check.clear()
        tasks = [task for group in groups for task in group]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------ projection

    def pending(self, session_id: str) -> list[dict[str, Any]]:
        agent = self.core.agents.get(session_id)
        if agent is None:
            return []
        return self.pending_in_project(agent.project_id, session_id=session_id)

    def pending_in_project(
        self, project_id: str, *, session_id: str | None = None, through_seq: int | None = None
    ) -> list[dict[str, Any]]:
        if through_seq is not None and through_seq < self._through.get(project_id, 0):
            # An explicitly captured historical view may predate a new reminder
            # mutation. Ordinary current-state requests never read history.
            live = {}
            for event in self.core.event_log.iter_project(project_id, before_seq=through_seq, types=_REMINDER_TYPES):
                if event.type == "reminder.scheduled":
                    live[event.seq] = _row_from_event(event)
                elif event.data.get("schedule_id") is not None:
                    live.pop(int(event.data["schedule_id"]), None)
            rows = live.values()
        else:
            rows = list(self._pending.get(project_id, {}).values())
        return sorted((deepcopy(row) for row in rows if session_id is None or row["session_id"] == session_id),
                      key=lambda row: row["wake_ts"])

    def _all_pending(self) -> list[dict[str, Any]]:
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for agent in self.core.agents.values():
            if agent.project_id in seen:
                continue
            seen.add(agent.project_id)
            rows.extend(self.pending_in_project(agent.project_id))
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
        await self.core.event_writer.flush()
        return envelope

    # ------------------------------------------------------------------ arm / fire

    def _cancel_timer(self, project_id: str, schedule_id: int) -> None:
        key = (project_id, schedule_id)
        tasks = self._timers.pop(key, [])
        self._last_check.pop(key, None)
        current = asyncio.current_task()
        for task in tasks:
            if task is not current:
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
        check_command = row.get("check_command")
        interval = row.get("interval_seconds")
        timeout_reason = "check_timeout" if check_command else None

        async def _wait_and_fire() -> None:
            try:
                if delay:
                    await asyncio.sleep(delay)
                output = ""
                last = self._last_check.get(key)
                if last is not None:
                    output = f"Last check exit_code={last[0]}\n{last[1]}".strip()
                await self._fire(
                    project_id, session_id, schedule_id, reason=timeout_reason, output=output
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("reminder %s failed to fire", schedule_id)

        tasks = [asyncio.create_task(_wait_and_fire())]
        # Overdue reminders fire on the timeout arm immediately; do not catch
        # up a backlog of check polls after a restart.
        if check_command and delay > 0:
            tasks.append(
                asyncio.create_task(
                    self._poll_until_ready(
                        key,
                        project_id=project_id,
                        session_id=session_id,
                        schedule_id=schedule_id,
                        command=str(check_command),
                        interval=float(interval or 0.0),
                    )
                )
            )
        self._timers[key] = tasks

    async def _poll_until_ready(
        self,
        key: tuple[str, int],
        *,
        project_id: str,
        session_id: str,
        schedule_id: int,
        command: str,
        interval: float,
    ) -> None:
        first = True
        try:
            while True:
                if not first:
                    await asyncio.sleep(max(0.0, interval))
                first = False
                if session_id not in self.core.agents:
                    await self._abandon(project_id, session_id, schedule_id)
                    return
                cwd = self._workspace_of(session_id)
                code, output = await run_check_command(
                    command, cwd=cwd, timeout=CHECK_RUN_TIMEOUT_SECONDS
                )
                self._last_check[key] = (code, output)
                if code == 0:
                    await self._fire(
                        project_id,
                        session_id,
                        schedule_id,
                        reason="check_succeeded",
                        output=output,
                    )
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reminder %s check poller failed", schedule_id)

    def _workspace_of(self, session_id: str) -> str | None:
        agent = self.core.agents.get(session_id)
        if agent is None:
            return None
        project = self.core.projects.get(agent.project_id)
        if project is None:
            return None
        return project.workspace_dir

    async def _abandon(self, project_id: str, session_id: str, schedule_id: int) -> None:
        async with self._fire_lock:
            pending = await asyncio.to_thread(self.pending_in_project, project_id, session_id=session_id)
            if not any(item["schedule_id"] == schedule_id for item in pending):
                self._cancel_timer(project_id, schedule_id)
                return
            await self._emit(
                "reminder.cancelled",
                project_id=project_id,
                session_id=session_id,
                data={"schedule_id": schedule_id, "reason": "agent_gone"},
            )
            self._cancel_timer(project_id, schedule_id)

    async def _fire(
        self,
        project_id: str,
        session_id: str,
        schedule_id: int,
        *,
        reason: str | None = None,
        output: str = "",
    ) -> None:
        async with self._fire_lock:
            pending = await asyncio.to_thread(self.pending_in_project, project_id, session_id=session_id)
            row = next((item for item in pending if item["schedule_id"] == schedule_id), None)
            if row is None:
                return
            if session_id not in self.core.agents:
                await self._emit(
                    "reminder.cancelled",
                    project_id=project_id,
                    session_id=session_id,
                    data={"schedule_id": schedule_id, "reason": "agent_gone"},
                )
                self._cancel_timer(project_id, schedule_id)
                return
            fired = {"schedule_id": schedule_id, "message": row["message"]}
            if reason:
                fired["reason"] = reason
            await self._emit(
                "reminder.fired",
                project_id=project_id,
                session_id=session_id,
                data=fired,
            )
            self._cancel_timer(project_id, schedule_id)
        from cloudra.runtime_v2.commands import CommandBus

        content = _wake_content(row["message"], reason=reason, output=output)
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
        await self.core.event_writer.flush()
        for row in self._all_pending():
            self._arm(row)

    # ------------------------------------------------------------------ tool

    async def handle(self, agent: AgentSession, call: ToolCall) -> ToolResult:
        from cloudra.tools.Managetool.schedule import ScheduleInput

        try:
            args = ScheduleInput.model_validate(call.arguments).model_dump()
        except ValidationError as exc:
            return _err(validation_feedback(exc))
        action = str(args.get("action") or "create")
        if action == "list":
            schedules = [
                {
                    "schedule_id": row["schedule_id"],
                    "message": row["message"],
                    "wake_at": row["wake_at"],
                    "check_command": row.get("check_command"),
                    "interval_seconds": row.get("interval_seconds"),
                }
                for row in await asyncio.to_thread(self.pending, agent.id)
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
                (item for item in await asyncio.to_thread(self.pending, agent.id) if item["schedule_id"] == schedule_id),
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
        return await self._create(agent, args)

    async def _create(self, agent: AgentSession, args: dict[str, Any]) -> ToolResult:
        message = str(args.get("message") or "").strip()
        if not message:
            return _err("create requires a non-empty message.")
        check_command = str(args.get("check_command") or "").strip() or None
        wake_at = args.get("wake_at")
        delay_seconds = args.get("delay_seconds")
        timeout_seconds = args.get("timeout_seconds")
        interval_raw = args.get("interval_seconds")

        try:
            wake_ts, wake_iso, interval_seconds = _parse_create_timing(
                check_command=check_command,
                wake_at=wake_at,
                delay_seconds=delay_seconds,
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_raw,
            )
        except (TypeError, ValueError, CheckCommandError) as exc:
            return _err(str(exc))

        if check_command:
            try:
                validate_check_command(check_command)
            except CheckCommandError as exc:
                return _err(str(exc))
            approved, reason = await self._approve_check(
                agent,
                check_command=check_command,
                interval_seconds=float(interval_seconds),
                wake_iso=wake_iso,
                message=message,
            )
            if not approved:
                return _err(
                    "Wake check was not approved; reminder was not created."
                    + (f" Rejection reason: {reason}" if reason else "")
                )

        data: dict[str, Any] = {"message": message, "wake_at": wake_iso, "wake_ts": wake_ts}
        if check_command:
            data["check_command"] = check_command
            data["interval_seconds"] = interval_seconds
        envelope = await self._emit(
            "reminder.scheduled",
            project_id=agent.project_id,
            session_id=agent.id,
            data=data,
        )
        row = _row_from_event(envelope)
        self._arm(row)
        if check_command:
            summary = (
                f"Reminder scheduled; polling {check_command!r} every {interval_seconds:g}s "
                f"until {wake_iso} (whichever comes first)."
            )
        else:
            summary = f"Reminder scheduled; the agent will wake at {wake_iso}."
        return _ok(
            summary,
            schedule_id=envelope.seq,
            wake_at=wake_iso,
            schedules=[],
        )

    async def _approve_check(
        self,
        agent: AgentSession,
        *,
        check_command: str,
        interval_seconds: float,
        wake_iso: str,
        message: str,
    ) -> tuple[bool, str]:
        if getattr(agent.settings, "yolo", False):
            return True, ""
        details = (
            "Action: Recurring read-only wake check\n"
            f"Command: {check_command}\n"
            f"Interval: {interval_seconds:g}s\n"
            f"Timeout: {wake_iso}\n"
            f"Message: {message}"
        )
        return await self.core.pending.request_approval(
            agent,
            tool_name="schedule",
            details=details,
            normalized_arguments={
                "check_command": check_command,
                "interval_seconds": interval_seconds,
                "wake_at": wake_iso,
                "message": message,
            },
            risk_summary="recurring read-only wake check while the agent sleeps",
            candidate_diff="",
        )


def _parse_create_timing(
    *,
    check_command: str | None,
    wake_at: Any,
    delay_seconds: Any,
    timeout_seconds: Any,
    interval_seconds: Any,
) -> tuple[float, str, float | None]:
    if check_command:
        deadline_count = sum(x is not None for x in (wake_at, delay_seconds, timeout_seconds))
        if deadline_count != 1:
            raise CheckCommandError(
                "check_command requires exactly one of timeout_seconds, delay_seconds, or wake_at. "
                "Example: schedule(action=\"create\", message=\"check job 12\", "
                "check_command=\"test -f job.done\", interval_seconds=30, timeout_seconds=600)."
            )
        if interval_seconds is None:
            raise CheckCommandError("check_command requires interval_seconds.")
        if wake_at is not None:
            wake_ts = _parse_wake_at(str(wake_at))
            timeout_from_now = wake_ts - time.time()
        else:
            timeout_from_now = float(
                timeout_seconds if timeout_seconds is not None else delay_seconds
            )
            wake_ts = time.time() + timeout_from_now
        interval = float(interval_seconds)
        validate_interval(interval, timeout_from_now)
        return wake_ts, _iso(wake_ts), interval
    if timeout_seconds is not None or interval_seconds is not None:
        raise CheckCommandError(
            "timeout_seconds and interval_seconds are only valid with check_command."
        )
    if (wake_at is None) == (delay_seconds is None):
        raise CheckCommandError("create must provide exactly one of wake_at or delay_seconds.")
    wake_ts = (
        _parse_wake_at(str(wake_at)) if wake_at is not None else time.time() + float(delay_seconds)
    )
    return wake_ts, _iso(wake_ts), None
