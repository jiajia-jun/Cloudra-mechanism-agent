"""v2-native schedule reminders: event-sourced, timer-fired, reopen via agent.message."""

from __future__ import annotations

import asyncio
import time

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command


async def _execute(core: RuntimeCore, type: str, **kwargs):
    return await CommandBus(core).execute(
        Command(type=type, target=kwargs.pop("target", {}), payload=kwargs.pop("payload", {}))
    )


async def _spawn_ready(core: RuntimeCore):
    project = (await _execute(core, "project.create", payload={"name": "p"})).data
    agent = (
        await _execute(
            core,
            "agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    ).data
    return project, agent


async def _wait_for(predicate, timeout: float = 2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


def _tiny_interval(monkeypatch) -> None:
    monkeypatch.setattr("cloudra.runtime_v2.check_command.MIN_INTERVAL_SECONDS", 0.05)


def _schedule_call(action: str, **arguments) -> ToolCall:
    return ToolCall(id="tc-sched", name="schedule", arguments={"action": action, **arguments})


@pytest.mark.asyncio
async def test_create_fires_and_reopens_agent_with_reminder_message():
    core = RuntimeCore(strict_events=True)
    project, agent = await _spawn_ready(core)
    core.agent_host.start_run(agent)
    core.agent_host.finish_run(agent, outcome="succeeded")
    assert agent.state.value == "succeeded"

    executor = LegacyToolExecutor(core)
    created = await executor.execute(
        agent,
        _schedule_call("create", message="check gaussian log", delay_seconds=0.05),
    )
    assert created.is_success is True
    schedule_id = created.data["schedule_id"]
    assert isinstance(schedule_id, int)
    types = [e.type for e in core.event_log.query_project(project.id)]
    assert "reminder.scheduled" in types

    await asyncio.sleep(0.25)

    types = [e.type for e in core.event_log.query_project(project.id)]
    assert "reminder.fired" in types
    injected = [
        e for e in core.event_log.query_session(agent.id) if e.type == "agent.message_injected"
    ]
    assert any("[Reminder]" in str(e.data.get("content", "")) for e in injected)
    assert "check gaussian log" in injected[-1].data["content"]
    assert agent.state.value == "running"
    assert agent.current_run is not None


@pytest.mark.asyncio
async def test_cancel_prevents_fire():
    core = RuntimeCore(strict_events=True)
    project, agent = await _spawn_ready(core)
    executor = LegacyToolExecutor(core)
    created = await executor.execute(
        agent,
        _schedule_call("create", message="stale", delay_seconds=0.15),
    )
    schedule_id = created.data["schedule_id"]
    cancelled = await executor.execute(
        agent, _schedule_call("cancel", schedule_id=schedule_id)
    )
    assert cancelled.is_success is True
    types = [e.type for e in core.event_log.query_project(project.id)]
    assert "reminder.cancelled" in types

    await asyncio.sleep(0.3)
    types = [e.type for e in core.event_log.query_project(project.id)]
    assert "reminder.fired" not in types
    injected = [e for e in core.event_log if e.type == "agent.message_injected"]
    assert not any("[Reminder]" in str(e.data.get("content", "")) for e in injected)


@pytest.mark.asyncio
async def test_list_is_event_projection():
    core = RuntimeCore(strict_events=True)
    _project, agent = await _spawn_ready(core)
    executor = LegacyToolExecutor(core)
    first = await executor.execute(
        agent, _schedule_call("create", message="one", delay_seconds=30)
    )
    second = await executor.execute(
        agent, _schedule_call("create", message="two", delay_seconds=60)
    )
    listed = await executor.execute(agent, _schedule_call("list"))
    assert listed.is_success is True
    ids = {row["schedule_id"] for row in listed.data["schedules"]}
    assert ids == {first.data["schedule_id"], second.data["schedule_id"]}

    await executor.execute(
        agent, _schedule_call("cancel", schedule_id=first.data["schedule_id"])
    )
    listed = await executor.execute(agent, _schedule_call("list"))
    remaining = {row["schedule_id"] for row in listed.data["schedules"]}
    assert remaining == {second.data["schedule_id"]}


@pytest.mark.asyncio
async def test_rearm_all_fires_overdue_reminders():
    core = RuntimeCore(strict_events=True)
    project, agent = await _spawn_ready(core)
    past = time.time() - 5
    envelope = core.event_log.append(
        "reminder.scheduled",
        stream="agent",
        project_id=project.id,
        session_id=agent.id,
        data={
            "message": "overdue check",
            "wake_at": "2020-01-01T00:00:00+00:00",
            "wake_ts": past,
        },
    )
    await core.reminders.rearm_all()
    await asyncio.sleep(0.05)

    types = [e.type for e in core.event_log.query_project(project.id)]
    assert "reminder.fired" in types
    fired = [e for e in core.event_log if e.type == "reminder.fired"]
    assert fired[0].data["schedule_id"] == envelope.seq
    injected = [e for e in core.event_log if e.type == "agent.message_injected"]
    assert any("overdue check" in str(e.data.get("content", "")) for e in injected)


@pytest.mark.asyncio
async def test_check_command_success_wakes_with_reason(monkeypatch):
    _tiny_interval(monkeypatch)
    core = RuntimeCore(strict_events=True)
    _project, agent = await _spawn_ready(core)
    agent.settings = agent.settings.model_copy(update={"yolo": True})
    core.agent_host.start_run(agent)
    core.agent_host.finish_run(agent, outcome="succeeded")

    created = await core.reminders.handle(
        agent,
        _schedule_call(
            "create",
            message="look at the log",
            check_command="true",
            interval_seconds=0.05,
            timeout_seconds=2,
        ),
    )
    assert created.is_success is True
    await _wait_for(lambda: any(e.type == "reminder.fired" for e in core.event_log))
    fired = [e for e in core.event_log if e.type == "reminder.fired"]
    assert fired[-1].data.get("reason") == "check_succeeded"
    injected = [e for e in core.event_log if e.type == "agent.message_injected"]
    content = str(injected[-1].data.get("content", ""))
    assert "[Reminder] look at the log" in content
    assert "[Wake reason: check_succeeded]" in content
    assert agent.state.value == "running"


@pytest.mark.asyncio
async def test_check_command_timeout_wakes_with_reason(monkeypatch):
    _tiny_interval(monkeypatch)
    core = RuntimeCore(strict_events=True)
    _project, agent = await _spawn_ready(core)
    agent.settings = agent.settings.model_copy(update={"yolo": True})
    core.agent_host.start_run(agent)
    core.agent_host.finish_run(agent, outcome="succeeded")

    created = await core.reminders.handle(
        agent,
        _schedule_call(
            "create",
            message="still running",
            check_command="false",
            interval_seconds=0.05,
            timeout_seconds=0.2,
        ),
    )
    assert created.is_success is True
    await _wait_for(lambda: any(e.type == "reminder.fired" for e in core.event_log), timeout=2.0)
    fired = [e for e in core.event_log if e.type == "reminder.fired"]
    assert fired[-1].data.get("reason") == "check_timeout"
    injected = [e for e in core.event_log if e.type == "agent.message_injected"]
    content = str(injected[-1].data.get("content", ""))
    assert "[Wake reason: check_timeout]" in content
    assert "still running" in content


@pytest.mark.asyncio
async def test_check_command_cancel_prevents_fire(monkeypatch):
    _tiny_interval(monkeypatch)
    core = RuntimeCore(strict_events=True)
    project, agent = await _spawn_ready(core)
    agent.settings = agent.settings.model_copy(update={"yolo": True})
    created = await core.reminders.handle(
        agent,
        _schedule_call(
            "create",
            message="stale check",
            check_command="false",
            interval_seconds=0.05,
            timeout_seconds=1,
        ),
    )
    cancelled = await core.reminders.handle(
        agent, _schedule_call("cancel", schedule_id=created.data["schedule_id"])
    )
    assert cancelled.is_success is True
    await asyncio.sleep(0.25)
    types = [e.type for e in core.event_log.query_project(project.id)]
    assert "reminder.fired" not in types


@pytest.mark.asyncio
async def test_check_command_deadline_error_shows_correct_usage():
    core = RuntimeCore(strict_events=True)
    _project, agent = await _spawn_ready(core)
    agent.settings = agent.settings.model_copy(update={"yolo": True})
    created = await core.reminders.handle(
        agent,
        _schedule_call(
            "create",
            message="bad timing",
            check_command="true",
            interval_seconds=5,
            timeout_seconds=60,
            delay_seconds=10,
        ),
    )
    assert created.is_success is False
    assert "exactly one of timeout_seconds, delay_seconds, or wake_at" in created.summary
    assert "interval_seconds=30" in created.summary
    assert not any(e.type == "reminder.scheduled" for e in core.event_log)


@pytest.mark.asyncio
async def test_check_command_rejected_is_not_scheduled():
    core = RuntimeCore(strict_events=True)
    _project, agent = await _spawn_ready(core)
    agent.settings = agent.settings.model_copy(update={"yolo": True})
    created = await core.reminders.handle(
        agent,
        _schedule_call(
            "create",
            message="nope",
            check_command="rm -rf /tmp/x",
            interval_seconds=5,
            timeout_seconds=60,
        ),
    )
    assert created.is_success is False
    assert not any(e.type == "reminder.scheduled" for e in core.event_log)


@pytest.mark.asyncio
async def test_overdue_check_rearm_fires_timeout_not_success():
    core = RuntimeCore(strict_events=True)
    project, agent = await _spawn_ready(core)
    past = time.time() - 5
    envelope = core.event_log.append(
        "reminder.scheduled",
        stream="agent",
        project_id=project.id,
        session_id=agent.id,
        data={
            "message": "overdue file check",
            "wake_at": "2020-01-01T00:00:00+00:00",
            "wake_ts": past,
            "check_command": "true",
            "interval_seconds": 5,
        },
    )
    await core.reminders.rearm_all()
    await _wait_for(lambda: any(e.type == "reminder.fired" for e in core.event_log))
    fired = [e for e in core.event_log if e.type == "reminder.fired"]
    assert fired[0].data["schedule_id"] == envelope.seq
    assert fired[0].data.get("reason") == "check_timeout"


@pytest.mark.asyncio
async def test_check_command_requires_approval_when_not_yolo(monkeypatch):
    _tiny_interval(monkeypatch)
    core = RuntimeCore(strict_events=True)
    project, agent = await _spawn_ready(core)
    core.agent_host.start_run(agent)
    task = asyncio.create_task(
        core.reminders.handle(
            agent,
            _schedule_call(
                "create",
                message="need approval",
                check_command="true",
                interval_seconds=0.05,
                timeout_seconds=2,
            ),
        )
    )
    await _wait_for(lambda: bool(core.pending.list_pending_approvals(project.id)))
    pending = core.pending.list_pending_approvals(project.id)
    assert pending[0]["tool_name"] == "schedule"
    assert not any(e.type == "reminder.scheduled" for e in core.event_log)
    await core.pending.decide_approval(project.id, pending[0]["id"], "approved", "")
    created = await task
    assert created.is_success is True
    assert any(e.type == "reminder.scheduled" for e in core.event_log)
    await core.reminders.close()
