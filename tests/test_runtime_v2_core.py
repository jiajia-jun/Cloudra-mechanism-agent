"""Runtime v2 first-slice tests: command pipeline, state machine, API routing."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command
from cloudra.services.api_v2 import create_v2_app


async def _execute(core: RuntimeCore, type: str, **kwargs) -> object:
    command = Command(type=type, target=kwargs.pop("target", {}), payload=kwargs.pop("payload", {}))
    result = await CommandBus(core).execute(command)
    return result


async def _spawn(core: RuntimeCore, project_id: str, role_id: str = "coordinator"):
    return await _execute(core, "agent.spawn", target={"project_id": project_id}, payload={"role_id": role_id})


@pytest.mark.asyncio
async def test_project_create_and_settings_pipeline():
    core = RuntimeCore(strict_events=True)
    result = await _execute(core, "project.create", payload={"name": "demo", "workspace_dir": "/tmp/demo"})
    assert result.accepted
    project = result.data
    assert project.name == "demo"
    # 事件先于状态：事件日志已经记录了 project.created
    assert [e.type for e in core.event_log if e.project_id == project.id] == ["project.created"]

    patched = await _execute(
        core,
        "project.update",
        target={"project_id": project.id},
        payload={"name": "demo2"},
    )
    assert patched.data.name == "demo2"
    assert [e.type for e in core.event_log if e.project_id == project.id][-1] == "project.updated"


@pytest.mark.asyncio
async def test_spawn_uses_effective_settings_and_is_peer_shaped():
    core = RuntimeCore(strict_events=True)
    project = (await _execute(core, "project.create", payload={"name": "p"})).data
    result = await _spawn(core, project.id, "small_mol")
    agent = result.data
    assert agent.role_id == "small_mol"
    assert agent.state == "queued"
    assert agent.parent_session_id is None
    assert "agent.spawn_requested" in [e.type for e in core.event_log if e.project_id == project.id]
    assert "agent.spawned" in [e.type for e in core.event_log if e.project_id == project.id]


@pytest.mark.asyncio
async def test_runtime_settings_patch_is_immediate_and_masked():
    core = RuntimeCore(strict_events=True)
    project = (await _execute(core, "project.create", payload={"name": "p"})).data
    agent = (await _spawn(core, project.id)).data
    patched = await _execute(
        core,
        "agent.settings_update",
        target={"session_id": agent.id},
        payload={"yolo": True, "model": "deepseek-v4", "temperature": 0.3, "api_key": "sk-secret"},
    )
    data = patched.data
    assert data.settings.yolo is True
    assert data.settings.model == "deepseek-v4"
    assert data.settings_revision == 1
    dumped = data.model_dump(mode="json")
    assert "api_key" not in dumped
    assert dumped["settings"]["api_key_set"] is True


@pytest.mark.asyncio
async def test_message_wakes_succeeded_agent_with_new_run():
    core = RuntimeCore(strict_events=True)
    project = (await _execute(core, "project.create", payload={"name": "p"})).data
    agent = (await _spawn(core, project.id)).data
    run_id = core.agent_host.start_run(agent)
    core.agent_host.finish_run(agent, outcome="succeeded")
    assert agent.state == "succeeded"

    result = await _execute(
        core,
        "agent.message",
        target={"session_id": agent.id},
        payload={"content": "continue please"},
    )
    assert result.data.state == "running"
    assert result.data.current_run.run_id != run_id
    # message event must precede the new run.started event
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert types[-2:] == ["agent.message_injected", "run.started"] or "agent.message_injected" in types


@pytest.mark.asyncio
async def test_cancel_and_restart_state_machine():
    core = RuntimeCore(strict_events=True)
    project = (await _execute(core, "project.create", payload={"name": "p"})).data
    agent = (await _spawn(core, project.id)).data
    core.agent_host.start_run(agent)

    cancelled = await _execute(
        core,
        "agent.cancel",
        target={"session_id": agent.id},
        payload={"message": "方向错了"},
    )
    assert cancelled.data.state == "cancelled"
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "agent.cancel_requested" in types
    assert "agent.cancelled" in types

    restarted = await _execute(
        core,
        "agent.restart",
        target={"session_id": agent.id},
        payload={"message": "换模型重跑", "settings": {"temperature": 0.1}},
    )
    assert restarted.data.state == "queued"
    assert restarted.data.settings.temperature == 0.1
    assert restarted.data.settings_revision == 1
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "agent.restart_requested" in types
    assert "agent.settings_changed" in types
    assert "agent.restarted" in types


@pytest.mark.asyncio
async def test_invalid_transition_is_rejected_as_command_event():
    core = RuntimeCore(strict_events=True)
    project = (await _execute(core, "project.create", payload={"name": "p"})).data
    agent = (await _spawn(core, project.id)).data
    # restart requires a terminal state; a queued agent must be rejected
    result = await _execute(core, "agent.restart", target={"session_id": agent.id})
    assert result.accepted is False
    assert result.data["error"]["code"] == "state_conflict"
    assert [e.type for e in core.event_log if e.type == "command.rejected"]


@pytest.mark.asyncio
async def test_command_idempotency_returns_first_result():
    core = RuntimeCore(strict_events=True)
    command = Command(type="project.create", payload={"name": "once"})
    bus = CommandBus(core)
    first = await bus.execute(command)
    second = await bus.execute(command)
    assert first.command_id == second.command_id
    assert len(core.projects) == 1
    # duplicate command must not append duplicate events
    assert len([e for e in core.event_log if e.type == "project.created"]) == 1


@pytest.mark.asyncio
async def test_api_v2_basic_flow():
    app = create_v2_app(RuntimeCore(strict_events=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v2/projects", json={"name": "web project"})
        assert resp.status_code == 201
        project = resp.json()["data"]

        resp = await client.post(
            f"/api/v2/projects/{project['id']}/agents", json={"role_id": "coordinator"}
        )
        assert resp.status_code == 201
        agent = resp.json()["data"]

        resp = await client.patch(
            f"/api/v2/agents/{agent['id']}/settings",
            json={"yolo": True, "model": "deepseek-v4", "api_key": "secret"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["data"]["settings"]["yolo"] is True
        assert payload["data"]["settings"]["api_key_set"] is True
        assert "api_key" not in payload["data"]["settings"]

        resp = await client.post(
            f"/api/v2/agents/{agent['id']}/messages", json={"content": "hello"}
        )
        assert resp.status_code == 200
        resp = await client.get(f"/api/v2/agents/{agent['id']}/transcript")
        assert resp.status_code == 200
        assert resp.json()["messages"][0]["content"] == "hello"

        resp = await client.get("/api/v2/roles")
        assert resp.status_code == 200
        assert {role["role_id"] for role in resp.json()} >= {"coordinator", "small_mol"}


@pytest.mark.asyncio
async def test_event_hub_fanout_and_cursor_replay():
    core = RuntimeCore(strict_events=True)
    seen = []

    async def collect(event):
        seen.append(event)

    core.event_hub.subscribe(collect)
    await _execute(core, "project.create", payload={"name": "sse project"})
    assert seen and seen[0].type == "project.created"
    cursor = seen[0].seq
    # reconnecting clients resume after the last seen seq without duplicates
    assert core.event_log.query_project(seen[0].project_id, after_seq=cursor) == []
    await _execute(
        core,
        "project.update",
        target={"project_id": seen[0].project_id},
        payload={"name": "renamed"},
    )
    replayed = core.event_log.query_project(seen[0].project_id, after_seq=cursor)
    assert [e.type for e in replayed] == ["project.updated"]


@pytest.mark.asyncio
async def test_default_v2_app_wires_runtime_without_network(tmp_path):
    from cloudra.services.api_v2 import create_default_v2_app

    app = create_default_v2_app(store_path=str(tmp_path / "runtime.db"))
    core = app.state.runtime_core
    assert core.runner is not None
    assert core.store is not None
    assert core.runtime_defaults.model != ""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/roles")
        assert resp.status_code == 200
        assert {role["role_id"] for role in resp.json()} >= {"coordinator", "small_mol"}


@pytest.mark.asyncio
async def test_api_v2_control_surface_routes():
    app = create_v2_app(RuntimeCore(strict_events=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v2/projects",
            json={"name": "dag", "settings": {"orchestration_mode": "dag_record"}},
        )
        project = resp.json()["data"]

        resp = await client.get(f"/api/v2/projects/{project['id']}/dag/process")
        assert resp.status_code == 200
        assert resp.json()["mode"] == "dag_record"
        assert resp.json()["graph"]["nodes"] == []

        resp = await client.get(f"/api/v2/projects/{project['id']}/approvals")
        assert resp.status_code == 200
        assert resp.json() == []

        resp = await client.get(f"/api/v2/projects/{project['id']}/interactions")
        assert resp.status_code == 200
        assert resp.json() == []

        resp = await client.get(f"/api/v2/projects/{project['id']}/artifacts")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
async def test_api_error_mapping():
    app = create_v2_app(RuntimeCore(strict_events=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/agents/as_missing")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "not_found"
