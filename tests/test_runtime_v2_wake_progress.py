"""Background results wake promptly without bypassing unfinished work."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import AgentState, Command
from tests.agent_scenarios import (
    ScenarioHarness,
    ScriptedProvider,
    background_completion_resume_steps,
)
from tests.test_runtime_v2_compute_notify import _insert_terminal_job, _notified_at


def _complete_job(job_id):
    with ComputeDB().connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job_id,))


async def _settled(harness, agent, runs):
    await harness.wait_for(
        lambda: len(harness.run_rows(agent)) == runs
        and harness.runner.task_for(agent.id) is None,
        "completed scripted runs",
    )


async def _stale_reminder(harness, agent, tmp_path, monkeypatch):
    async def approved(*_args, **_kwargs):
        return True, "read-only fixture check"

    monkeypatch.setattr(harness.core.reminders, "_approve_check", approved)
    result = await harness.core.reminders.handle(agent, ToolCall(
        id="old-reminder", name="schedule", arguments={
            "action": "create", "message": "Check the abandoned calculation",
            "delay_seconds": 3600, "interval_seconds": 300,
            "check_command": f"test -f {tmp_path / 'abandoned.log'}",
        },
    ))
    assert result.is_success


@pytest.mark.asyncio
@pytest.mark.parametrize("blocker", [None, "compute", "child"])
async def test_scenario_completed_compute_wakes_despite_unrelated_reminder(
    tmp_path, monkeypatch, blocker,
):
    hold = asyncio.Event()
    provider = ScriptedProvider(by_role={"coordinator": background_completion_resume_steps(hold)})
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    try:
        parent = await harness.spawn("coordinator", query="", orchestration_mode="dag_record")
        await _stale_reminder(harness, parent, tmp_path, monkeypatch)
        job = await asyncio.to_thread(_insert_terminal_job, harness.project.id,
                                      session_id=parent.id, state="running", path="")
        extra_job = child = None
        if blocker == "compute":
            extra_job = await asyncio.to_thread(_insert_terminal_job, harness.project.id,
                                                session_id=parent.id, state="running", path="")
        elif blocker == "child":
            child = await harness.spawn("explorer", query="")
        await harness.bus.execute(Command(type="agent.message", target={"session_id": parent.id},
                                          payload={"content": "Watch the calculation"}))
        await _settled(harness, parent, 1)
        gates = harness.core.event_log.query_session(parent.id, types={"agent.completion_gate"})
        assert [gate.data["action"] for gate in gates] == ["wait_background"]
        assert parent.state is AgentState.SUCCEEDED

        await asyncio.to_thread(_complete_job, job)
        broker = ComputeNotifyBroker(harness.core)
        await broker._poll_project(harness.project.id)
        assert await asyncio.to_thread(_notified_at, job) is not None
        if blocker:
            assert parent.state is AgentState.SUCCEEDED
            assert provider.call_count("coordinator") == 1
            if extra_job is not None:
                await asyncio.to_thread(_complete_job, extra_job)
                await broker._poll_project(harness.project.id)
            else:
                await harness.core.agent_host.start_run(child)
                await harness.core.agent_host.finish_run(child, outcome="succeeded")
                await harness.runner._deliver_completion(child)
        await harness.wait_for(lambda: provider.call_count("coordinator") == 2,
                               "completed calculation wakes before old reminder", timeout=1)
        assert parent.state is AgentState.RUNNING
        assert len(harness.core.reminders.pending(parent.id)) == 1
        notices = [event for event in harness.messages(parent)
                   if (event.get("manifest") or {}).get("kind") == "background_quiescence"]
        assert len(notices) == 1
        await broker._poll_project(harness.project.id)
        assert provider.call_count("coordinator") == 2
    finally:
        await harness.core.reminders.close()
        await harness.aclose()


@pytest.mark.asyncio
async def test_scenario_reminder_wait_does_not_wake_itself(tmp_path, monkeypatch):
    hold = asyncio.Event()
    provider = ScriptedProvider(by_role={"coordinator": background_completion_resume_steps(hold)})
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    try:
        parent = await harness.spawn("coordinator", query="", orchestration_mode="dag_record")
        await _stale_reminder(harness, parent, tmp_path, monkeypatch)
        await harness.bus.execute(Command(type="agent.message", target={"session_id": parent.id},
                                          payload={"content": "Wait for the reminder"}))
        await _settled(harness, parent, 1)
        await harness.runner.maybe_wake_parked_delivery(harness.project.id)
        assert parent.state is AgentState.SUCCEEDED
        assert provider.call_count("coordinator") == 1
    finally:
        await harness.core.reminders.close()
        await harness.aclose()


@pytest.mark.asyncio
async def test_new_compute_during_quiescence_lookup_still_blocks_wake(tmp_path, monkeypatch):
    from tests.test_runtime_v2_background_quiescence import _finish, _setup

    core, runner, _bus, project, parent = await _setup(tmp_path)
    await _finish(core, parent, "wait_background")
    original = core.event_log.iter_events
    inserted = []

    def new_compute(**filters):
        if not inserted and filters.get("types") == {"agent.message_injected"}:
            inserted.append(_insert_terminal_job(project.id, session_id=parent.id, state="running", path=""))
        yield from original(**filters)

    monkeypatch.setattr(core.event_log, "iter_events", new_compute)
    await runner.maybe_wake_parked_delivery(project.id, background_finished=True)
    assert inserted
    assert parent.state is AgentState.SUCCEEDED
