"""Reminder receipts, terminal cancellation, and cancellation/fire ordering."""

import asyncio
import json

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.invocation import tool_result_context_content
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command


async def _actor(core, project=None):
    bus = CommandBus(core)
    if project is None:
        project = (await bus.execute(Command(type="project.create", payload={"name": "reminder receipts"}))).data
    agent = (await bus.execute(Command(type="agent.spawn", target={"project_id": project.id},
                                      payload={"role_id": "coordinator"}))).data
    return project, agent


async def _call(core, agent, action, **arguments):
    return await LegacyToolExecutor(core).execute(agent, ToolCall("schedule", "schedule", {"action": action, **arguments}))


@pytest.mark.asyncio
async def test_create_and_list_receipts_reach_model_context_with_their_complete_data():
    core = RuntimeCore(strict_events=True)
    _, agent = await _actor(core)
    try:
        created = await _call(core, agent, "create", message="check original log", delay_seconds=3600)
        listed = await _call(core, agent, "list")

        for result in (created, listed):
            content = tool_result_context_content(agent, result)
            assert '"schedule_id"' in content
            assert json.loads(content) == result.data
        assert listed.data["schedules"][0]["schedule_id"] == created.data["schedule_id"]
        assert listed.data["schedules"][0]["message"] == "check original log"
    finally:
        await core.reminders.close()


@pytest.mark.asyncio
async def test_schedule_receipts_survive_real_turn_context_and_runtime_restore(tmp_path):
    from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step

    provider = ScriptedProvider(default=[
        Step(tools=[("schedule", {"message": "inspect log", "delay_seconds": 3600})]),
        Step(tools=[("schedule", {"action": "list"})]),
        Step(stop=True),
    ])
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    restored = None
    try:
        agent = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(agent)
        await harness.wait_for(lambda: harness.runner.task_for(agent.id) is None, "completion flush")
        contexts = harness.core.contexts.current_messages(agent.id)
        receipts = [json.loads(item["content"]) for item in contexts
                    if item.get("role") == "tool" and '"schedule_id"' in item.get("content", "")]
        assert len(receipts) == 2
        assert receipts[1]["schedules"][0]["schedule_id"] == receipts[0]["schedule_id"]
        await harness.bus.flush_snapshot()
        await harness.core.reminders.close()
        restored = await ScenarioHarness.restore(tmp_path)
        assert restored.core.contexts.current_messages(agent.id) == contexts
        listed = await _call(restored.core, restored.core.agents[agent.id], "list")
        assert json.loads(tool_result_context_content(restored.core.agents[agent.id], listed)) == receipts[1]
    finally:
        await harness.core.reminders.close()
        await harness.aclose()
        if restored is not None:
            await restored.core.reminders.close()
            await restored.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["cancelled", "fired"])
async def test_owned_terminal_cancellation_is_an_accurate_noop_after_snapshot_restore(tmp_path, terminal):
    core = RuntimeCore(strict_events=True)
    store = RuntimeStore(tmp_path / "runtime.db")
    core.store = store
    project, agent = await _actor(core)
    try:
        created = await _call(core, agent, "create", message="inspect native output", delay_seconds=3600)
        schedule_id = created.data["schedule_id"]
        if terminal == "cancelled":
            assert (await _call(core, agent, "cancel", schedule_id=schedule_id)).is_success
        else:
            await core.reminders._fire(project.id, agent.id, schedule_id)
        await CommandBus(core).flush_snapshot()
    finally:
        await core.reminders.close()

    restored = RuntimeCore(strict_events=True)
    await asyncio.to_thread(restore_core, restored, store)
    restored_agent = restored.agents[agent.id]
    before = restored.event_log.high_watermarks[project.id]

    result = await _call(restored, restored_agent, "cancel", schedule_id=schedule_id)

    assert result.is_success
    assert f"already {terminal}" in result.data["message"]
    if terminal == "fired":
        assert "not withdrawn" in result.data["message"]
    assert result.data["schedule_id"] == schedule_id
    assert restored.event_log.high_watermarks[project.id] == before
    assert restored.reminders.pending(agent.id) == []


@pytest.mark.asyncio
async def test_unknown_and_foreign_reminders_are_still_rejected():
    core = RuntimeCore(strict_events=True)
    project, owner = await _actor(core)
    _, foreign = await _actor(core, project)
    try:
        created = await _call(core, owner, "create", message="owned", delay_seconds=3600)
        schedule_id = created.data["schedule_id"]
        await _call(core, owner, "cancel", schedule_id=schedule_id)

        for agent, identifier in ((foreign, schedule_id), (owner, schedule_id + 1000)):
            result = await _call(core, agent, "cancel", schedule_id=identifier)
            assert not result.is_success
            assert "already" not in result.data["message"]
    finally:
        await core.reminders.close()


@pytest.mark.asyncio
async def test_fired_history_cannot_be_reported_as_withdrawn_by_a_later_cancel_event():
    core = RuntimeCore(strict_events=True)
    project, agent = await _actor(core)
    try:
        created = await _call(core, agent, "create", message="sent", delay_seconds=3600)
        schedule_id = created.data["schedule_id"]
        await core.reminders._fire(project.id, agent.id, schedule_id)
        # A pre-existing cancellation/fire race can have recorded both events.
        await core.reminders._emit("reminder.cancelled", project_id=project.id,
                                   session_id=agent.id, data={"schedule_id": schedule_id})
        result = await _call(core, agent, "cancel", schedule_id=schedule_id)

        assert result.is_success
        assert "already fired" in result.data["message"]
        assert "not withdrawn" in result.data["message"]
    finally:
        await core.reminders.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["fired", "cancelled"])
async def test_cancellation_and_fire_share_one_terminal_decision(monkeypatch, first):
    core = RuntimeCore(strict_events=True)
    project, agent = await _actor(core)
    created = await _call(core, agent, "create", message="race", delay_seconds=3600)
    schedule_id = created.data["schedule_id"]
    entered, release = asyncio.Event(), asyncio.Event()
    emit = core.reminders._emit

    async def held_emit(event_type, **kwargs):
        if event_type == f"reminder.{first}":
            entered.set()
            await release.wait()
        return await emit(event_type, **kwargs)

    monkeypatch.setattr(core.reminders, "_emit", held_emit)

    async def fire():
        return await core.reminders._fire(project.id, agent.id, schedule_id)

    async def cancel():
        return await _call(core, agent, "cancel", schedule_id=schedule_id)

    winner = asyncio.create_task(fire() if first == "fired" else cancel())
    loser = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        loser = asyncio.create_task(cancel() if first == "fired" else fire())
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(loser), timeout=0.05)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(winner, loser), timeout=1)
        terminal = [event.type for event in core.event_log.query_project(project.id)
                    if event.type in {"reminder.fired", "reminder.cancelled"}]
        assert terminal == [f"reminder.{first}"]
        notices = [event for event in core.event_log.query_session(agent.id)
                   if event.type == "agent.message_injected" and "[Reminder]" in event.data.get("content", "")]
        assert len(notices) == (1 if first == "fired" else 0)
        if first == "fired":
            assert results[1].is_success
            assert "already fired" in results[1].data["message"]
    finally:
        release.set()
        await asyncio.gather(winner, *([loser] if loser else []), return_exceptions=True)
        await core.reminders.close()
