"""Runtime v2 first-slice tests: command pipeline, state machine, API routing."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall
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
    run_id = await core.agent_host.start_run(agent)
    await core.agent_host.finish_run(agent, outcome="succeeded")
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
    await core.agent_host.start_run(agent)

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
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
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
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v2/roles")
        assert resp.status_code == 200
        assert {role["role_id"] for role in resp.json()} >= {"coordinator", "small_mol"}
    # Transient streaming deltas are fanned out to subscribers but never
    # persisted into the runtime store.
    from cloudra.runtime_v2.schemas import EventEnvelope

    received = []

    async def collect(event):
        received.append(event)

    core.event_hub.subscribe(collect)
    await core.event_hub.publish(
        EventEnvelope(stream="agent", project_id="p1", seq=0, type="llm.chunk", data={"delta": "x"})
    )
    assert received and received[-1].type == "llm.chunk"
    assert not [e for e in core.store.query_project_events("p1") if e["type"] == "llm.chunk"]


@pytest.mark.asyncio
async def test_api_v2_control_surface_routes():
    app = create_v2_app(RuntimeCore(strict_events=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v2/projects",
            json={"name": "dag", "settings": {"orchestration_mode": "dag_record"}},
        )
        project = resp.json()["data"]

        resp = await client.get(f"/api/v2/projects/{project['id']}/dag/process")
        assert resp.status_code == 410  # process graph removed (delivery-only)

        resp = await client.get(f"/api/v2/projects/{project['id']}/dag/delivery")
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

        resp = await client.get(f"/api/v2/projects/{project['id']}/dag/projection")
        assert resp.status_code == 200
        projection = resp.json()
        assert projection["mode"] == "dag_record"
        assert projection["pending_reviews"] == []
        assert "frontier" not in projection

        resp = await client.get(f"/api/v2/projects/{project['id']}/dag/reviews")
        assert resp.status_code == 200
        assert resp.json() == {"pending": [], "recent": []}

        resp = await client.get(f"/api/v2/projects/{project['id']}/dag/draft")
        assert resp.status_code == 200
        assert resp.json() == {"mechanism_accepted": False, "draft": None}

        # replan is dag_guided-only: dag_record maps the ValueError to 422
        resp = await client.post(f"/api/v2/projects/{project['id']}/dag/replan", json={"note": ""})
        assert resp.status_code == 422

        # Regression: explicit nulls in a settings patch (the SPA round-trips
        # serialized defaults) must not poison subsequent spawns.
        resp = await client.patch(
            f"/api/v2/projects/{project['id']}",
            json={
                "settings": {
                    "orchestration_mode": "dag_record",
                    "defaults": {"model": None, "api_key": None, "orchestration_mode": "dag_record"},
                }
            },
        )
        assert resp.status_code == 200
        resp = await client.post(f"/api/v2/projects/{project['id']}/agents", json={"role_id": "coordinator"})
        assert resp.status_code == 201
        assert resp.json()["data"]["settings"]["orchestration_mode"] == "dag_record"


@pytest.mark.asyncio
async def test_api_v2_replan_queues_request_and_notifies():
    """Task 3：user replan 不再同步跑督导——持久化请求 + 通知 + queued 语义。

    响应不得伪报裁决结果；请求落 dag_review_requests（kind=exception，
    正文保留用户 note），项目唯一 Supervisor 被 spawn（无 runner 时 wake
    只落事件不调度）。
    """
    app = create_v2_app(RuntimeCore(strict_events=True))
    core = app.state.runtime_core
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v2/projects",
            json={"name": "replan-q", "settings": {"orchestration_mode": "dag_guided"}},
        )
        project = resp.json()["data"]
        await client.post(
            f"/api/v2/projects/{project['id']}/agents", json={"role_id": "coordinator"}
        )
        # 初始化 DAG bundle（等价于 agent 已进入 dag 模式）。
        resp = await client.get(f"/api/v2/projects/{project['id']}/dag/delivery")
        assert resp.status_code == 200

        resp = await client.post(
            f"/api/v2/projects/{project['id']}/dag/replan",
            json={"note": "please re-review the TS evidence"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] is True
        assert body["request_id"]
        assert "supervised" not in body and "mutations_accepted" not in body

        from cloudra.dag.store import DagStore
        from cloudra.persistence.database import ConversationDB

        request = DagStore(ConversationDB(project["id"])).get_review_request(
            body["request_id"]
        )
        assert request is not None
        assert request.state == "queued"
        assert request.kind == "exception"
        assert request.question == "please re-review the TS evidence"

        from cloudra.runtime_v2.supervision import find_project_supervisor

        supervisor = find_project_supervisor(core, project["id"])
        assert supervisor is not None
        coordinator = next(
            a for a in core.agents.values()
            if a.project_id == project["id"] and a.role_id == "coordinator"
        )
        assert supervisor.parent_session_id == coordinator.id


@pytest.mark.asyncio
async def test_api_v2_goal_context_compact_skills_routes():
    app = create_v2_app(RuntimeCore(strict_events=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/v2/projects", json={"name": "cmd-demo"})
        project = resp.json()["data"]
        resp = await client.post(
            f"/api/v2/projects/{project['id']}/agents",
            json={"role_id": "coordinator"},
        )
        agent = resp.json()["data"]

        goal = {"objective": "find the TS", "completion_criteria": "verified", "current_focus": ""}
        resp = await client.post(f"/api/v2/agents/{agent['id']}/goal", json=goal)
        assert resp.status_code == 200
        resp = await client.get(f"/api/v2/agents/{agent['id']}/goal")
        assert resp.json()["goal"]["objective"] == "find the TS"

        resp = await client.get(f"/api/v2/agents/{agent['id']}/context")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["session_id"] == agent["id"]
        assert stats["messages"] == 0
        assert set(stats["by_role"]) == {"user", "assistant", "tool"}

        resp = await client.post(f"/api/v2/agents/{agent['id']}/compact", json={})
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True

        # Mid-session orchestration mode switch: agents snapshot settings at
        # spawn, and settings_update must flip the live value for dag tools.
        assert agent["settings"]["orchestration_mode"] == "standard"
        resp = await client.patch(
            f"/api/v2/agents/{agent['id']}/settings",
            json={"orchestration_mode": "dag_guided"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["settings"]["orchestration_mode"] == "dag_guided"

        resp = await client.get("/api/v2/skills")
        assert resp.status_code == 200
        skills = resp.json()
        assert skills and all("name" in s and "content" in s for s in skills)


@pytest.mark.asyncio
async def test_api_error_mapping():
    app = create_v2_app(RuntimeCore(strict_events=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v2/agents/as_missing")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_stream_marks_replay_boundary():
    """SSE 回放末尾必须带 project.synced 边界标记，前端据此抑制历史事件
    触发的提示（审批 toast 等只应对新事件触发）。

    直接驱动 _sse_replay 生成器：httpx ASGITransport 会缓冲整个响应体，
    无限 SSE 流经它永远收不到 markers（send 要等 app 跑完才返回）。"""
    from cloudra.services.api_v2 import _sse_replay

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    result = await bus.execute(Command(type="project.create", payload={"name": "sse"}))
    project = result.data

    chunks = [chunk async for chunk in _sse_replay(core, project, 0)]
    text = "".join(chunks)
    # 回放事件（project.created）在前，边界标记在后
    assert text.index("project.created") < text.index("project.synced")
    assert "replayed_through" in text


@pytest.mark.asyncio
async def test_workspace_dir_normalized_and_relative_rejected(tmp_path):
    """workspace_dir 在命令层规范化：相对路径直接拒绝（下游会把它和 server
    cwd 拼出嵌套怪路径），不存在的绝对路径自动创建。"""
    bus = CommandBus(RuntimeCore(strict_events=True))
    bad = await bus.execute(
        Command(
            type="project.create",
            payload={"name": "bad", "workspace_dir": "home/user/nowhere"},
        )
    )
    assert bad.accepted is False
    assert bad.data["error"]["code"] == "invalid_request"

    target = tmp_path / "fresh-ws"
    good = await bus.execute(
        Command(
            type="project.create",
            payload={"name": "good", "workspace_dir": str(target)},
        )
    )
    assert good.accepted is True
    assert good.data.workspace_dir == str(target)
    assert target.is_dir()


@pytest.mark.asyncio
async def test_project_create_defaults_workspace_under_data_dir():
    """未提供 workspace_dir 时必须落到 per-project 默认工作区
    （data_dir/workspaces/<project_id>），而不是留 None 让下游
    文件/bash 工具解析到进程 cwd（GH #24）。"""
    from pathlib import Path

    from cloudra.infra.config import get_config

    bus = CommandBus(RuntimeCore(strict_events=True))
    result = await bus.execute(Command(type="project.create", payload={"name": "auto"}))
    assert result.accepted
    project = result.data
    expected = Path(get_config().data_dir) / "workspaces" / project.id
    assert project.workspace_dir == str(expected)
    assert expected.is_dir()


@pytest.mark.asyncio
async def test_orchestration_mode_switch_opens_dag_tool(tmp_path):
    """发出消息后切换编排模式：agent.settings_update 落 dag_record 后，
    dag_view 工具门禁必须打开（此前 agent 报 disabled in standard mode）。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "switch"}))
    project = next(iter(core.projects.values()))
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator", "query": "hi"},
            )
        )
    ).data
    executor = LegacyToolExecutor(core)

    async def dag_view():
        return await executor.execute(
            agent, ToolCall(id="t1", name="dag_view", arguments={"graph_kind": "both"})
        )

    blocked = await dag_view()
    assert blocked.is_success is False
    assert "disabled in standard" in blocked.summary

    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"orchestration_mode": "dag_record"},
        )
    )
    allowed = await dag_view()
    assert allowed.is_success is True, allowed.summary


def test_query_session_before_cursor_pages_backwards():
    """`before_session_seq` is the lazy-audit backwards-paging cursor:
    each page returns the newest `limit` events at or below the cursor."""
    from cloudra.runtime_v2.events import EventLog

    log = EventLog(strict=True)
    for i in range(10):
        log.append("agent.warning", stream="agent", project_id="p", session_id="s", data={"i": i})

    newest = log.query_session("s", limit=3, tail=True)
    assert [e.session_seq for e in newest] == [8, 9, 10]

    older = log.query_session("s", before_session_seq=8, limit=3, tail=True)
    assert [e.session_seq for e in older] == [6, 7, 8]

    first = log.query_session("s", before_session_seq=6, limit=3, tail=True)
    assert [e.session_seq for e in first] == [4, 5, 6]

    # A short final page signals "no older events".
    tail = log.query_session("s", before_session_seq=4, limit=3, tail=True)
    assert [e.session_seq for e in tail] == [2, 3, 4]

    # forward paging is unaffected by the new parameter
    forward = log.query_session("s", limit=3, tail=False)
    assert [e.session_seq for e in forward] == [1, 2, 3]


@pytest.mark.asyncio
async def test_runtime_config_endpoints_read_patch_and_persist(tmp_path, monkeypatch):
    """Global config GET/PATCH: masked keys, live mutation of the singleton,
    YAML persistence, and write-only key semantics."""
    from cloudra.infra.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg.coordinator, "model", "old-model")
    monkeypatch.setattr(cfg.coordinator, "key", "old-key")

    app = create_v2_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get("/api/v2/runtime/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["coordinator"]["model"] == "old-model"
        assert body["coordinator"]["key_set"] is True
        assert "key" not in body["coordinator"]  # write-only

        resp = await client.patch(
            "/api/v2/runtime/config",
            json={"slot": "coordinator", "changes": {"model": "new-model", "key": "new-key"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["coordinator"]["model"] == "new-model"
        assert body["coordinator"]["key_set"] is True
        assert cfg.coordinator.model == "new-model"  # live on the singleton
        assert "new-model" in (tmp_path / "config.yaml").read_text(encoding="utf-8")

        resp = await client.patch(
            "/api/v2/runtime/config",
            json={"slot": "coordinator", "changes": {"key": ""}},
        )
        assert resp.json()["coordinator"]["key_set"] is False
        assert cfg.coordinator.key == ""

        # unknown slot is a 422, not a silent no-op
        resp = await client.patch(
            "/api/v2/runtime/config",
            json={"slot": "other", "changes": {"model": "x"}},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_v2_dag_mutations_malformed_operation_is_422():
    """请求体里的畸形 operation 是客户端校验错误（422），不得冒 500。"""
    app = create_v2_app(RuntimeCore(strict_events=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v2/projects",
            json={"name": "dag-422", "settings": {"orchestration_mode": "dag_record"}},
        )
        project = resp.json()["data"]
        # 初始化 DAG bundle（等价于 agent 已进入 dag 模式）。
        resp = await client.get(f"/api/v2/projects/{project['id']}/dag/delivery")
        assert resp.status_code == 200

        resp = await client.post(
            f"/api/v2/projects/{project['id']}/dag/mutations",
            json={"operations": [{"op": "definitely_not_an_op"}], "rationale": "bad"},
        )
        assert resp.status_code == 422
        assert "Invalid graph operation" in resp.json()["detail"]
