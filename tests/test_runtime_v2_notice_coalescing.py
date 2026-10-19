"""GH #205: durable notification versions coalesce without swallowing real work."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.schemas import AgentState
from cloudra.runtime_v2.supervision import find_project_supervisor, notify_supervisor
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step
from tests.test_runtime_v2_compute_notify import _insert_terminal_job, _notified_at, _setup_core
from tests.test_runtime_v2_supervision import _seed_pending_review


@pytest.mark.asyncio
@pytest.mark.parametrize("restore", [False, True])
async def test_compute_batch_is_one_durable_notice_and_retries_each_unacked_job(
    tmp_path, monkeypatch, restore,
):
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    core, project, coordinator = await _setup_core()
    core.store = RuntimeStore(tmp_path / "compute-batch.db")
    await core.event_writer.flush()
    jobs = [await asyncio.to_thread(
        _insert_terminal_job, project.id, session_id=coordinator.id, path="",
    ) for _ in range(3)]
    broker = ComputeNotifyBroker(core)
    mark = broker._mark_notified

    def fail_second_ack(job_id):
        if job_id == jobs[1]:
            raise OSError("interrupted second receipt")
        mark(job_id)

    with monkeypatch.context() as patcher:
        patcher.setattr(broker, "_mark_notified", fail_second_ack)
        await broker._poll_project(project.id)
    notices = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})
    assert len(notices) == 1
    assert all(f"Job {job}," in notices[0].data["content"] for job in jobs)
    assert await asyncio.to_thread(_notified_at, jobs[0]) is not None
    assert await asyncio.to_thread(_notified_at, jobs[1]) is None
    assert await asyncio.to_thread(_notified_at, jobs[2]) is None
    if restore:
        restored = RuntimeCore(strict_events=True)
        await asyncio.to_thread(restore_core, restored, core.store)
        core = restored
    await ComputeNotifyBroker(core)._poll_project(project.id)
    assert all(await asyncio.gather(*[
        asyncio.to_thread(_notified_at, job) for job in jobs
    ]))
    assert len(core.event_log.query_session(coordinator.id, types={"agent.message_injected"})) == 1
    inbox = core.mailbox.inbox(coordinator.id)
    assert inbox.qsize() == 1
    assert core.agents[coordinator.id].state is AgentState.QUEUED


@pytest.mark.asyncio
@pytest.mark.parametrize("restore", [False, True])
async def test_scenario_same_scientific_work_does_not_reopen_stopped_supervisor(tmp_path, restore):
    provider = ScriptedProvider(by_role={"supervisor": [Step(stop=True), Step(stop=True)]})
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        await harness.spawn("coordinator", query="")
        await _seed_pending_review(harness.project.id)
        await notify_supervisor(harness.core, harness.project.id, reason="new scientific review")
        supervisor = find_project_supervisor(harness.core, harness.project.id)
        await harness.wait_for(
            lambda: supervisor.state is AgentState.SUCCEEDED
            and harness.runner.task_for(supervisor.id) is None,
            "first Supervisor notification consumed",
        )
        if restore:
            project_id = harness.project.id
            await harness.aclose()
            harness = await ScenarioHarness.restore(tmp_path, provider=provider)
            assert harness.project.id == project_id
            supervisor = find_project_supervisor(harness.core, project_id)
        first_runs = len(harness.run_rows(supervisor))
        await notify_supervisor(harness.core, harness.project.id, reason="mechanical dirty flag changed")
        assert supervisor.state is AgentState.SUCCEEDED
        assert harness.runner.task_for(supervisor.id) is None
        assert len(harness.run_rows(supervisor)) == first_runs
        await _seed_pending_review(harness.project.id)
        await notify_supervisor(harness.core, harness.project.id, reason="new evidence to review")
        await harness.wait_for(
            lambda: len(harness.run_rows(supervisor)) == first_runs + 1
            and harness.runner.task_for(supervisor.id) is None,
            "new scientific work opens a fresh run",
        )
        assert provider.call_count("supervisor") == 2
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_scenario_consumed_observation_stays_deduplicated_and_explicit_calls_still_wake(tmp_path):
    from cloudra.runtime_v2.hub_bridge import handle_hub_tool
    from cloudra.runtime_v2.policies.base import ToolCall

    provider = ScriptedProvider(by_role={"supervisor": [Step(stop=True) for _ in range(4)]})
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        parent = await harness.spawn("coordinator", query="")
        await notify_supervisor(harness.core, harness.project.id, observation="Recorded TS outcome A")
        supervisor = find_project_supervisor(harness.core, harness.project.id)

        async def settled(count):
            await harness.wait_for(
                lambda: len(harness.run_rows(supervisor)) == count
                and harness.runner.task_for(supervisor.id) is None,
                f"Supervisor consumed {count} actionable work items",
            )

        await settled(1)
        from cloudra.runtime_v2.notices import RESEARCH_OBSERVATION_PIN_KEY

        harness.core.notices.unpin(supervisor.id, RESEARCH_OBSERVATION_PIN_KEY)
        await notify_supervisor(harness.core, harness.project.id, observation="Recorded TS outcome A")
        assert supervisor.state is AgentState.SUCCEEDED
        assert harness.runner.task_for(supervisor.id) is None
        await notify_supervisor(harness.core, harness.project.id, observation="Recorded TS outcome B")
        await settled(2)
        for index in range(2):
            result = await handle_hub_tool(harness.core, parent, ToolCall(
                id=f"explicit-{index}", name="agent_hub",
                arguments={"action": "call", "to": supervisor.id, "message": "Inspect this explicit task"},
            ))
            assert result.is_success
            await settled(index + 3)
        assert provider.call_count("supervisor") == 4
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_scenario_loaded_unread_work_wakes_once_without_duplicate_notice(tmp_path):
    provider = ScriptedProvider(by_role={"supervisor": [Step(stop=True)]})
    harness = await ScenarioHarness.start(tmp_path, provider=provider)
    try:
        await harness.spawn("coordinator", query="")
        supervisor = await harness.spawn("supervisor", query="")
        await _seed_pending_review(harness.project.id)
        await notify_supervisor(harness.core, harness.project.id, auto_wake=False)
        notices = harness.messages(supervisor)
        assert len(notices) == 1
        assert harness.runner.task_for(supervisor.id) is None
        await harness.aclose()
        harness = await ScenarioHarness.restore(tmp_path, provider=provider)
        supervisor = harness.core.agents[supervisor.id]
        await notify_supervisor(harness.core, harness.project.id)
        await harness.wait_for(
            lambda: supervisor.state is AgentState.SUCCEEDED
            and harness.runner.task_for(supervisor.id) is None,
            "loaded pending work resumed",
        )
        assert len(harness.messages(supervisor)) == 1
        assert provider.call_count("supervisor") == 1
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_scenario_same_note_bytes_do_not_rewake_but_new_content_does(tmp_path, monkeypatch):
    async def approve(*_args, **_kwargs):
        return True, "fixture write approved"

    monkeypatch.setattr("cloudra.base.tools_class.Tool.ensure_safety", approve)
    rewrite, change, hold = asyncio.Event(), asyncio.Event(), asyncio.Event()
    provider = ScriptedProvider(by_role={
        "coordinator": [
            Step(tools=[("write", {"path": "NOTES.md", "content": "one observation\n"})]),
            Step(wait_for=rewrite, tools=[("write", {"path": "NOTES.md", "content": "one observation\n"})]),
            Step(wait_for=change, tools=[("write", {"path": "NOTES.md", "content": "new evidence\n"})]),
            Step(wait_for=hold),
        ],
        "supervisor": [Step(stop=True), Step(stop=True)],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    try:
        parent = await harness.spawn(
            "coordinator", protocol="traditional", orchestration_mode="dag_guided", yolo=True,
        )
        await harness.wait_for(
            lambda: (supervisor := find_project_supervisor(harness.core, harness.project.id)) is not None
            and supervisor.state is AgentState.SUCCEEDED
            and harness.runner.task_for(supervisor.id) is None,
            "first note maintained",
        )
        supervisor = find_project_supervisor(harness.core, harness.project.id)
        rewrite.set()
        await harness.wait_for(
            lambda: len([tool for tool in harness.tool_events(parent)
                         if tool["tool_name"] == "write" and tool["is_success"] is not None]) == 2,
            "identical note rewrite completed",
        )
        assert supervisor.state is AgentState.SUCCEEDED
        assert len(harness.run_rows(supervisor)) == 1
        change.set()
        await harness.wait_for(
            lambda: len(harness.run_rows(supervisor)) == 2
            and harness.runner.task_for(supervisor.id) is None,
            "changed note maintained once",
        )
        assert provider.call_count("supervisor") == 2
    finally:
        await harness.aclose()
