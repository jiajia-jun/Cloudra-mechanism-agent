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
