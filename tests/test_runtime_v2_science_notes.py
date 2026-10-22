"""Terminal TS observations reach shared PROCESS upkeep without a research write."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.failures import RunFailureKind
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.schemas import AgentState, Command, InvocationProtocol, OrchestrationMode
from cloudra.runtime_v2.supervision import find_project_supervisor, pending_supervision_summary
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step
from tests.test_runtime_v2_compute_notify import _setup_core
from tests.test_runtime_v2_process_notes import approve_file_changes as approve_file_changes

NOTE_KEY = "supervisor-research-observation"


def _completed_ts(project_id, child_id, work, outcome="candidate_only"):
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process, save_process_record
    from cloudra.tools.core.ts_process import TsJobStep, _terminal
    from tests.test_ts_stage_inputs import record_fixture

    work.mkdir(parents=True, exist_ok=True)
    db = ComputeDB().init()
    record = record_fixture(work, owner_conversation_id=project_id, owner_session_id=child_id)
    process = create_process(db, request_key=str(work), payload=dict(
        project_id=project_id, owner_id=child_id, workspace_dir=str(work),
        input=record.input.model_dump(mode="json")))
    source = work / "frequency.inp"
    source.write_text("Recorded native input")
    job = bind_stage_job(db, process_id=process["process_id"], declaration_revision=1,
        stage_key="product_frequency", attempt=1, job_payload=dict(
            conversation_id=project_id, session_id=child_id, path=str(source),
            state="ready", jobtype="orca", node_id="fixture"))
    native = work / ".cloudra" / f"calc-{job}.out.log"
    native.parent.mkdir(exist_ok=True)
    native.write_text("Recorded transport fixture output\nORCA TERMINATED NORMALLY\n")
    record.pipeline_id = process["process_id"]
    record.job_steps = [TsJobStep(purpose="product_frequency", job_id=job, state="done", input_path=str(source))]
    _terminal(record, "verdict", outcome, "Recorded endpoint identity: OCCP")
    save_process_record(db, process_id=process["process_id"], record=record.model_dump(mode="json"))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
    return job


async def _research_core(tmp_path):
    core, project, coordinator = await _setup_core()
    project.workspace_dir = str(tmp_path)
    coordinator.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    child = (await CommandBus(core).execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "small_mol", "parent_session_id": coordinator.id,
                 "settings": {"orchestration_mode": "dag_guided"}},
    ))).data
    return core, project, coordinator, child


def _injections(core, agent):
    return core.event_log.query_session(agent.id, types={"agent.message_injected"})


@pytest.mark.asyncio
async def test_terminal_ts_updates_supervisor_once_without_research_note_write(tmp_path):
    core, project, coordinator, child = await _research_core(tmp_path)
    first_job = await asyncio.to_thread(_completed_ts, project.id, child.id, tmp_path / "first")
    broker = ComputeNotifyBroker(core)
    await broker._poll_project(project.id)
    supervisor = find_project_supervisor(core, project.id)
    assert supervisor is not None
    first = core.notices.pin_content(supervisor.id, NOTE_KEY)
    assert first and "candidate_only" in first and f"calc-{first_job}.out.log" in first
    assert "Log:" in first
    assert len(_injections(core, supervisor)) == 1
    assert len(_injections(core, child)) == 1
    assert _injections(core, coordinator) == []
    assert not (tmp_path / "PROCESS.md").exists()
    assert not any((await pending_supervision_summary(project.id)).values())
    await broker._poll_project(project.id)
    assert len(_injections(core, supervisor)) == 1
    assert core.notices.pin_content(supervisor.id, NOTE_KEY) == first

    await asyncio.to_thread(_completed_ts, project.id, child.id, tmp_path / "second", "verified")
    await broker._poll_project(project.id)
    latest = core.notices.pin_content(supervisor.id, NOTE_KEY)
    assert latest and "outcome=verified" in latest and latest != first
    assert len(latest) < 2000
    notices = _injections(core, supervisor)
    assert len(notices) == 2  # each changed work version has one durable notification
    assert len({event.data["manifest"]["fingerprint"] for event in notices}) == 2
    await broker._poll_project(project.id)
    assert _injections(core, supervisor) == notices  # unchanged work is not redelivered
    assert len(_injections(core, child)) == 2
    assert not any((await pending_supervision_summary(project.id)).values())


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [AgentState.FAILED, AgentState.CANCELLED])
async def test_process_upkeep_does_not_revive_terminal_supervisor(tmp_path, state):
    core, project, coordinator, child = await _research_core(tmp_path)
    supervisor = (await CommandBus(core).execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "supervisor", "parent_session_id": coordinator.id},
    ))).data
    await core.agent_host.start_run(supervisor)
    if state is AgentState.CANCELLED:
        await CommandBus(core).execute(Command(type="agent.cancel", target={"session_id": supervisor.id}))
    else:
        await core.agent_host.finish_run(supervisor, outcome="failed", failure_kind=RunFailureKind.PIPELINE_INTERNAL)
    await asyncio.to_thread(_completed_ts, project.id, child.id, tmp_path / "first")
    await ComputeNotifyBroker(core)._poll_project(project.id)
    assert supervisor.state is state
    assert core.notices.pin_content(supervisor.id, NOTE_KEY)
    assert len(_injections(core, supervisor)) == 1
    assert _injections(core, coordinator) == []
    assert not any((await pending_supervision_summary(project.id)).values())


@pytest.mark.asyncio
async def test_zero_api_supervisor_writes_process_and_consumes_current_observation(tmp_path, approve_file_changes):
    release = asyncio.Event()
    provider = ScriptedProvider(by_role={
        "coordinator": [Step(stop=True)],
        "small_mol": [Step(wait_for=release, stop=True)],
        "supervisor": [Step(tools=[("write", {"path": "PROCESS.md", "content": "Observed TS evidence retained with native paths."})]), Step(stop=True)],
    })
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        coordinator = await harness.spawn("coordinator", protocol=InvocationProtocol.TRADITIONAL)
        await harness.wait_terminal(coordinator)
        parent_runs = len(harness.run_rows(coordinator))
        supervisor = await harness.spawn("supervisor", query="", protocol=InvocationProtocol.TRADITIONAL,
            parent=coordinator, orchestration_mode="dag_guided")
        child = await harness.spawn("small_mol", protocol=InvocationProtocol.TRADITIONAL,
            parent=coordinator, orchestration_mode="dag_guided")
        await harness.wait_for(lambda: provider.call_count("small_mol") == 1, "researcher waiting in its provider")
        await asyncio.to_thread(_completed_ts, harness.project.id, child.id, tmp_path / "first")
        await ComputeNotifyBroker(harness.core)._poll_project(harness.project.id)
        await harness.wait_for(lambda: (tmp_path / "PROCESS.md").is_file(), "Supervisor maintained PROCESS without research write")
        await harness.wait_terminal(supervisor)
        assert harness.core.notices.pin_content(supervisor.id, NOTE_KEY) is None
        assert len(harness.run_rows(coordinator)) == parent_runs
        assert child.state is AgentState.RUNNING
        assert not any((await pending_supervision_summary(harness.project.id)).values())
        pin = next(e for e in harness.events(supervisor) if e.type == "context.pin_set" and e.data["key"] == NOTE_KEY)
        tool = next(e for e in harness.events(supervisor) if e.type == "tool.result_recorded" and e.data["tool_name"] == "write")
        clear = next(e for e in harness.events(supervisor) if e.type == "context.pin_cleared" and e.data["key"] == NOTE_KEY)
        assert pin.seq < tool.seq < clear.seq
    finally:
        release.set()
        await harness.aclose()


@pytest.mark.parametrize("prior_consumed", [False, True])
def test_observation_batch_keeps_only_latest_update(prior_consumed):
    notices = NoticeManager()
    if prior_consumed:
        notices.pin("supervisor", NOTE_KEY, "Previously delivered observation")
        notices.collect_batch("supervisor", fresh=True)
        notices.confirm_consumed("supervisor")
    for content in ["Old pending observation", "Superseded pending observation", "Latest observation"]:
        notices.pin("supervisor", NOTE_KEY, content)
    notices.pin("supervisor", "guidance-scientific-reflection:scan", "Independent scientific reflection")
    batch = notices.collect_batch("supervisor", fresh=False)
    assert len(batch) == 2
    text = "\n".join(message["content"] for message in batch)
    assert "Old pending observation" not in text
    assert "Superseded pending observation" not in text
    assert text.count("Latest observation") == 1
    assert text.count("Independent scientific reflection") == 1
    assert notices.collect_batch("supervisor", fresh=False) == batch
    notices.confirm_consumed("supervisor")
    assert notices.collect_batch("supervisor", fresh=False) == []


@pytest.mark.parametrize("prior_consumed", [False, True])
def test_observation_retraction_omits_undelivered_updates(prior_consumed):
    notices = NoticeManager()
    if prior_consumed:
        notices.pin("supervisor", NOTE_KEY, "Previously delivered observation")
        notices.collect_batch("supervisor", fresh=True)
        notices.confirm_consumed("supervisor")
    notices.pin("supervisor", NOTE_KEY, "Pending observation")
    notices.unpin("supervisor", NOTE_KEY)
    batch = notices.collect_batch("supervisor", fresh=False)
    assert len(batch) == int(prior_consumed)
    assert "Pending observation" not in str(batch)


@pytest.mark.asyncio
async def test_zero_api_process_write_preserves_new_unread_observation(tmp_path, approve_file_changes):
    research_write, research_hold = asyncio.Event(), asyncio.Event()
    write_a, write_b = asyncio.Event(), asyncio.Event()
    research_text = "Research notes\n"
    text_a, text_b = "Supervisor merged A\n", "Supervisor merged B\n"
    provider = ScriptedProvider(by_role={
        "coordinator": [Step(stop=True)],
        "small_mol": [
            Step(wait_for=research_write, tools=[("write", {"path": "PROCESS.md", "content": research_text})]),
            Step(wait_for=research_hold),
        ],
        "supervisor": [
            Step(wait_for=write_a, tools=[("read", {"path": "PROCESS.md"}),
                ("write", {"path": "PROCESS.md", "content": text_a})]),
            Step(wait_for=write_b, tools=[("read", {"path": "PROCESS.md"}),
                ("write", {"path": "PROCESS.md", "content": text_b})]),
            Step(stop=True),
        ],
    })
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        coordinator = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(coordinator)
        supervisor = await harness.spawn("supervisor", query="", protocol="traditional",
            parent=coordinator, orchestration_mode="dag_guided")
        child = await harness.spawn("small_mol", protocol="traditional",
            parent=coordinator, orchestration_mode="dag_guided")
        await harness.wait_for(lambda: provider.call_count("small_mol") == 1, "researcher held")
        await asyncio.to_thread(_completed_ts, harness.project.id, child.id, tmp_path / "first")
        broker = ComputeNotifyBroker(harness.core)
        await broker._poll_project(harness.project.id)
        await harness.wait_for(lambda: provider.call_count("supervisor") == 1, "A entered Supervisor context")
        first = harness.core.notices.pin_content(supervisor.id, NOTE_KEY)
        research_write.set()
        await harness.wait_for(lambda: provider.call_count("small_mol") == 2, "researcher PROCESS write finished")
        assert harness.core.notices.pin_content(supervisor.id, NOTE_KEY) == first
        await asyncio.to_thread(_completed_ts, harness.project.id, child.id, tmp_path / "second", "verified")
        await broker._poll_project(harness.project.id)
        second = harness.core.notices.pin_content(supervisor.id, NOTE_KEY)
        assert second and second != first
        write_a.set()
        await harness.wait_for(lambda: provider.call_count("supervisor") == 2, "A write completed and B entered context")
        assert harness.core.notices.pin_content(supervisor.id, NOTE_KEY) == second
        assert await asyncio.to_thread((tmp_path / "PROCESS.md").read_text) == text_a
        write_b.set()
        await harness.wait_terminal(supervisor)
        assert await asyncio.to_thread((tmp_path / "PROCESS.md").read_text) == text_b
        assert harness.core.notices.pin_content(supervisor.id, NOTE_KEY) is None
        assert child.state is AgentState.RUNNING
        assert len(harness.run_rows(coordinator)) == 1
        assert not any((await pending_supervision_summary(harness.project.id)).values())
    finally:
        for gate in (research_write, research_hold, write_a, write_b):
            gate.set()
        await harness.aclose()


@pytest.mark.asyncio
async def test_zero_api_consumed_observation_update_survives_supervisor_stop(tmp_path, approve_file_changes):
    stop_a, research_hold = asyncio.Event(), asyncio.Event()
    provider = ScriptedProvider(by_role={
        "coordinator": [Step(stop=True)],
        "small_mol": [Step(wait_for=research_hold)],
        "supervisor": [
            Step(wait_for=stop_a, stop=True),
            Step(tools=[("write", {"path": "PROCESS.md", "content": "Supervisor merged latest result\n"})]),
            Step(stop=True),
        ],
    })
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        coordinator = await harness.spawn("coordinator", protocol="traditional")
        await harness.wait_terminal(coordinator)
        supervisor = await harness.spawn("supervisor", query="", protocol="traditional",
            parent=coordinator, orchestration_mode="dag_guided")
        child = await harness.spawn("small_mol", protocol="traditional",
            parent=coordinator, orchestration_mode="dag_guided")
        await harness.wait_for(lambda: provider.call_count("small_mol") == 1, "researcher held")
        await asyncio.to_thread(_completed_ts, harness.project.id, child.id, tmp_path / "first")
        broker = ComputeNotifyBroker(harness.core)
        await broker._poll_project(harness.project.id)
        await harness.wait_for(lambda: provider.call_count("supervisor") == 1, "A entered Supervisor context")
        await asyncio.to_thread(_completed_ts, harness.project.id, child.id, tmp_path / "second", "verified")
        await broker._poll_project(harness.project.id)
        await asyncio.to_thread(_completed_ts, harness.project.id, child.id, tmp_path / "third", "candidate_only")
        await broker._poll_project(harness.project.id)
        # A, B and C are distinct durable work versions; repeated polling is a no-op.
        notices = _injections(harness.core, supervisor)
        assert len(notices) == 3
        assert len({event.data["manifest"]["fingerprint"] for event in notices}) == 3
        await broker._poll_project(harness.project.id)
        assert _injections(harness.core, supervisor) == notices
        stop_a.set()
        await harness.wait_terminal(supervisor)
        assert (tmp_path / "PROCESS.md").exists()
        assert harness.core.notices.pin_content(supervisor.id, NOTE_KEY) is None
        assert provider.call_count("supervisor") == 3
        assert len(harness.run_rows(supervisor)) == 1
        assert len(harness.run_rows(coordinator)) == 1
        assert not any((await pending_supervision_summary(harness.project.id)).values())
    finally:
        stop_a.set()
        research_hold.set()
        await harness.aclose()
