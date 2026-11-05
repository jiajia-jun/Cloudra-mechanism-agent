"""Delegated task lifecycle through the Cloudra HTTP API."""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentSession, Project
from cloudra.services.api_v2 import create_v2_app

START = "/api/v2/tasks"
RESULT = "/api/v2/projects/p/agents/a/result"


@pytest_asyncio.fixture
async def runtime():
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="Existing")
    async with AsyncClient(
        transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver",
    ) as client:
        yield core, client
    await core.aclose()


def _emit(core, event_type, run_id, **data):
    return core.event_log.append(
        event_type, stream="agent", project_id="p", session_id="a", run_id=run_id, data=data,
    )


def _agent(core):
    agent = AgentSession(id="a", project_id="p", role_id="coordinator", display_name="Coordinator")
    core.agents[agent.id] = agent
    return agent


@pytest.mark.asyncio
async def test_start_existing_project_serializes_coordinator_spawn(runtime):
    core, client = runtime
    responses = await asyncio.gather(*(
        client.post(START, json={"task": "Study reaction", "project_id": "p"})
        for _ in range(2)
    ))
    assert sorted(response.status_code for response in responses) == [201, 409]
    created = next(response.json() for response in responses if response.status_code == 201)
    agent = core.agents[created["session_id"]]
    assert agent.project_id == created["project_id"] == "p"
    assert agent.role_id == "coordinator"
    messages = core.event_log.query_session(agent.id, types={"agent.message_injected"})
    assert [event.data["content"] for event in messages] == ["Study reaction"]


@pytest.mark.asyncio
async def test_start_returns_project_id_if_spawn_is_rejected(runtime, monkeypatch):
    core, client = runtime
    execute = CommandBus.execute

    async def execute_with_missing_coordinator(self, command):
        if command.type == "agent.spawn":
            command.payload["role_id"] = "missing"
        return await execute(self, command)

    monkeypatch.setattr(CommandBus, "execute", execute_with_missing_coordinator)
    response = await client.post(START, json={"task": "Study reaction", "name": "New"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "not_found"
    assert core.projects[detail["project_id"]].name == "New"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"task": "  ", "name": "New"},
    {"task": "Study"},
    {"task": "Study", "project_id": "p", "name": "New"},
    {"task": "Study", "project_id": "p", "workspace_dir": "/tmp"},
    {"task": "Study", "name": "New", "role_id": "explorer"},
])
async def test_start_validates_exclusive_project_inputs(runtime, payload):
    _core, client = runtime
    assert (await client.post(START, json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_result_tracks_parked_then_final_then_reopened_run(runtime):
    core, client = runtime
    agent = _agent(core)
    parked_id = await core.agent_host.start_run(agent)
    _emit(core, "agent.completion_gate", parked_id, action="wait_background", basis="background_wait")
    _emit(core, "agent.message_emitted", parked_id, content="A job is running.")
    await core.agent_host.finish_run(agent, outcome="succeeded")
    parked = await client.get(RESULT)
    assert parked.json()["status"] == "pending"
    assert parked.json()["agent"]["activity"] == "waiting_background"

    await core.agent_host.wake(agent)
    run_id = agent.current_run.run_id
    _emit(core, "agent.completion_gate", run_id, action="allow_final", basis="declared")
    _emit(core, "agent.message_emitted", run_id, content="Delivered.")
    await core.agent_host.finish_run(agent, outcome="succeeded")
    finished = core.event_log.query_session(agent.id, types={"run.finished"}, limit=1)[0]
    response = await client.get(RESULT)
    assert response.json() == {
        "status": "finished",
        "result": {
            "terminal_event_id": finished.event_id, "run_outcome": "succeeded",
            "summary": "Delivered.", "verification_label": "unverified",
            "completion_basis": "declared", "unresolved": [], "artifacts": [],
        },
    }
    sent = await client.post("/api/v2/agents/a/messages", json={"content": "Extend the study."})
    assert sent.status_code == 200
    assert (await client.get(RESULT)).json()["status"] == "pending"


@pytest.mark.asyncio
async def test_result_does_not_return_previous_run_summary_or_foreign_session(runtime):
    core, client = runtime
    agent = _agent(core)
    old_run = await core.agent_host.start_run(agent)
    _emit(core, "agent.message_emitted", old_run, content="Earlier run.")
    await core.agent_host.finish_run(agent, outcome="succeeded")
    await core.agent_host.wake(agent)
    await core.agent_host.finish_run(agent, outcome="succeeded")
    response = await client.get(RESULT)
    assert response.json()["result"]["summary"] is None

    core.projects["other"] = Project(id="other", name="Other")
    foreign = RESULT.replace("/p/", "/other/")
    assert (await client.get(foreign)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot_changed", [False, True])
async def test_result_returns_only_artifact_bound_when_delivery_finished(runtime, tmp_path, snapshot_changed):
    import hashlib
    from types import SimpleNamespace

    from cloudra.dag.models import CoverageGateResult, DeliveryReport
    from cloudra.dag.stop_audit import StopGate
    from cloudra.persistence.artifacts import ArtifactService
    from cloudra.persistence.database import ConversationDB
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.services.session_store import ensure_session_record

    core, client = runtime
    agent = _agent(core)
    core.projects["p"].workspace_dir = str(tmp_path)
    run_id = await core.agent_host.start_run(agent)
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("Previous artifact")
    def register_unrelated():
        ensure_session_record(ConversationDB("p"), agent.id, agent.role_id)
        ArtifactService().register_file(
            conversation_id="p", session_id=agent.id, source=unrelated, allowed_root=tmp_path,
        )

    await asyncio.to_thread(register_unrelated)

    source = tmp_path / "mechanism_graph.json"
    source.write_text("Workspace graph has already been edited")
    snapshot = tmp_path / ".cloudra" / "evidence" / "snapshot.json"
    snapshot.parent.mkdir(parents=True)
    graph = b'{"nodes": [], "edges": []}'
    snapshot.write_bytes(b"Changed after audit" if snapshot_changed else graph)
    gap = CoverageGateResult(code="missing_evidence", target_type="edge", target_id="e1", detail="IRC pending")
    report = DeliveryReport(
        complete=False, unresolved=[gap], output_artifact={
            "path": str(source), "snapshot_path": str(snapshot), "sha256": hashlib.sha256(graph).hexdigest(),
        },
    )

    class CommittedDagStage:
        async def on_run_end(self, _agent, *, explicit_stop):
            return report

    runner = AgentRunner(core, SimpleNamespace(stages=[CommittedDagStage()]))
    gate = StopGate(action="allow_final", report=report, basis="partial_recorded")
    _emit(core, "agent.completion_gate", run_id, action=gate.action, basis=gate.basis)
    assert await runner._finish_gated_run(agent, run_id, gate, explicit_stop=True, candidate_answer="Partial.")
    result = (await client.get(RESULT)).json()["result"]
    assert result["verification_label"] == "partial"
    if snapshot_changed:
        assert result["unresolved"] == [
            "IRC pending", "The audited delivery file could not be registered for download.",
        ]
        assert result["artifacts"] == []
        return
    assert result["unresolved"] == ["IRC pending"]
    assert len(result["artifacts"]) == 1
    artifact = result["artifacts"][0]
    assert artifact["name"] == "mechanism_graph.json"
    assert artifact["uri"] == f'cloudra://projects/p/artifacts/{artifact["artifact_id"]}'
    payload = await client.get(f'/api/v2/artifacts/{artifact["artifact_id"]}/download?project_id=p')
    assert payload.content == graph


@pytest.mark.asyncio
async def test_custom_workspace_is_existing_canonical_and_independent(runtime, tmp_path):
    core, client = runtime
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    nested = workspace / "nested"
    nested.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(workspace, target_is_directory=True)
    payload = {"task": "Study", "name": "With inputs", "workspace_dir": str(alias)}

    created = await client.post(START, json=payload)
    assert created.status_code == 201
    assert core.projects[created.json()["project_id"]].workspace_dir == str(workspace.resolve())

    for path in (workspace, nested, tmp_path):
        conflict = await client.post(START, json={**payload, "workspace_dir": str(path)})
        assert conflict.status_code == 409
    for path in ("relative", str(tmp_path / "missing")):
        invalid = await client.post(START, json={**payload, "workspace_dir": path})
        assert invalid.status_code == 400


@pytest.mark.asyncio
async def test_result_does_not_treat_narration_as_a_final_answer(runtime):
    core, client = runtime
    agent = _agent(core)
    run_id = await core.agent_host.start_run(agent)
    _emit(core, "agent.message_emitted", run_id, content="I will inspect the files.")
    _emit(core, "agent.completion_gate", run_id, action="allow_final", basis="declared")
    await core.agent_host.finish_run(agent, outcome="succeeded")
    assert (await client.get(RESULT)).json()["result"]["summary"] is None


@pytest.mark.asyncio
async def test_long_wait_returns_descendant_question_only(runtime):
    core, client = runtime
    agent = _agent(core)
    child = AgentSession(
        id="child", project_id="p", role_id="explorer", display_name="Child", parent_session_id=agent.id,
    )
    unrelated = AgentSession(id="other", project_id="p", role_id="explorer", display_name="Other")
    for active in (agent, child, unrelated):
        core.agents[active.id] = active
        await core.agent_host.start_run(active)

    other_question = asyncio.create_task(core.pending.request_interaction(unrelated, "Unrelated?"))
    result_request = asyncio.create_task(client.get(RESULT, params={"wait_seconds": 10}))
    await asyncio.sleep(0)
    child_question = asyncio.create_task(core.pending.request_interaction(child, "A research question?"))
    try:
        response = await asyncio.wait_for(result_request, timeout=1)
        data = response.json()
        assert data["status"] == "pending"
        assert [(row["session_id"], row["prompt"]) for row in data["pending"]] == [
            (child.id, "A research question?"),
        ]
    finally:
        for task in (other_question, child_question):
            task.cancel()
        await asyncio.gather(other_question, child_question, return_exceptions=True)


@pytest.mark.asyncio
async def test_remote_task_start_cannot_select_server_workspace(runtime, tmp_path, monkeypatch):
    core, _client = runtime
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "test-secret-token")
    async with AsyncClient(
        transport=ASGITransport(app=create_v2_app(core), client=("203.0.113.10", 5000)),
        base_url="http://testserver",
        headers={"Authorization": "Bearer test-secret-token"},
    ) as remote:
        response = await remote.post(START, json={"task": "Study", "name": "New", "workspace_dir": str(tmp_path)})
        assert response.status_code == 403
        response = await remote.post(START, json={"task": "Study", "name": "New"})
        assert response.status_code == 201
        assert core.projects[response.json()["project_id"]].workspace_dir != str(tmp_path)
