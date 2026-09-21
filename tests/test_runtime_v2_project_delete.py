"""项目硬删除：tombstone 事件 + 支撑数据清理（workspace/compute.db 不动）。

安全语义（两步道）：只允许删已归档项目；项目内有存活 agent 拒绝；有非终态
compute job（ready/running/cancel_requested）在 CommandBus 拒绝。删除本体是
``project.deleted`` tombstone——事件日志（权威）不物理删，重放后 core 同样
不含该项目；磁盘侧清 conversations/<pid>/ 整树与该项目 artifact 文件。
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.persistence import paths
from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.commands import CommandBus, _delete_project_data
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import Command
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.compute_store import get_compute_job, insert_compute_job


async def _persist_event(store, event):
    await asyncio.to_thread(store.append_event, event)


async def _execute(core: RuntimeCore, type: str, **kwargs) -> object:
    command = Command(type=type, target=kwargs.pop("target", {}), payload=kwargs.pop("payload", {}))
    return await CommandBus(core).execute(command)


async def _create(core: RuntimeCore, name: str = "p"):
    return (await _execute(core, "project.create", payload={"name": name})).data


async def _archive(core: RuntimeCore, project_id: str) -> None:
    await _execute(core, "project.update", target={"project_id": project_id}, payload={"archived": True})


async def _spawn(core: RuntimeCore, project_id: str):
    return (
        await _execute(
            core, "agent.spawn", target={"project_id": project_id}, payload={"role_id": "coordinator"}
        )
    ).data


# --------------------------------------------------------------------- decider


@pytest.mark.asyncio
async def test_delete_requires_archived_project():
    core = RuntimeCore(strict_events=True)
    project = await _create(core)
    result = await _execute(core, "project.delete", target={"project_id": project.id})
    assert result.accepted is False
    assert result.data["error"]["code"] == "state_conflict"
    assert project.id in core.projects


@pytest.mark.asyncio
async def test_delete_rejects_live_agents():
    core = RuntimeCore(strict_events=True)
    project = await _create(core)
    await _archive(core, project.id)
    await _spawn(core, project.id)  # queued 是存活态
    result = await _execute(core, "project.delete", target={"project_id": project.id})
    assert result.accepted is False
    assert result.data["error"]["code"] == "state_conflict"
    assert project.id in core.projects


@pytest.mark.asyncio
async def test_delete_command_rejects_active_compute_jobs():
    core = RuntimeCore(strict_events=True)
    project = await _create(core)
    await _archive(core, project.id)
    db = ComputeDB().init()
    insert_compute_job(
        db,
        node_id="node-local",
        conversation_id=project.id,
        session_id=None,
        path="/tmp/input.gjf",
        state="running",
        jobtype="gaussian",
    )
    result = await _execute(core, "project.delete", target={"project_id": project.id})
    assert result.accepted is False
    assert result.data["error"]["code"] == "state_conflict"
    assert "active compute" in result.data["error"]["message"]
    assert project.id in core.projects


@pytest.mark.asyncio
async def test_delete_removes_project_and_agents_from_core():
    core = RuntimeCore(strict_events=True)
    project = await _create(core)
    await _archive(core, project.id)
    agent = await _spawn(core, project.id)
    # 终态 agent 不阻塞删除
    core.agent_host.start_run(agent)
    core.agent_host.finish_run(agent, outcome="succeeded")
    core.mailbox.ensure_inbox(agent.id)

    result = await _execute(core, "project.delete", target={"project_id": project.id})

    assert result.accepted
    assert result.data == {"deleted": project.id}
    assert project.id not in core.projects
    assert agent.id not in core.agents
    assert core.mailbox.inbox(agent.id) is None
    tombstone = [e for e in core.event_log if e.type == "project.deleted"]
    assert len(tombstone) == 1 and tombstone[0].project_id == project.id
    # apply 幂等（重放安全）：重复应用同一 tombstone 不抛错
    apply_event(core, tombstone[0])
    assert project.id not in core.projects


@pytest.mark.asyncio
async def test_delete_tombstone_survives_replay(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.event_hub.subscribe(lambda event: _persist_event(store, event))
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "p"}))).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    core.agent_host.start_run(agent)
    core.agent_host.finish_run(agent, outcome="succeeded")
    await bus.execute(
        Command(type="project.update", target={"project_id": project.id}, payload={"archived": True})
    )
    await bus.execute(Command(type="project.delete", target={"project_id": project.id}))
    await bus.flush_snapshot()

    # 新 core 从同一 store 恢复：tombstone 生效，项目/agent 不复活
    core2 = RuntimeCore(strict_events=True)
    restore_core(core2, store)
    assert project.id not in core2.projects
    assert agent.id not in core2.agents
    # 事件不物理删除：tombstone 审计仍在事件表里
    types = [e["type"] for e in store.query_project_events(project.id)]
    assert "project.deleted" in types


# --------------------------------------------------------------------- effect


def test_delete_project_data_removes_conversation_tree_and_artifacts(tmp_path):
    pid = "prj-deleteme"
    db_path = paths.conversation_db_path(pid)
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(str(db_path)) as con:
        con.execute("CREATE TABLE artifacts (artifact_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO artifacts VALUES ('art-1')")
    artifact_dir = paths.data_dir() / "artifacts" / "art-1"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "f.txt").write_text("x", encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir()

    _delete_project_data(pid)

    assert not paths.conversation_dir(pid).exists()
    assert not artifact_dir.exists()
    # workspace_dir 是用户数据，永不删
    assert workspace.exists()
    # 幂等：再删一次（库与目录已不存在）不抛错
    _delete_project_data(pid)


def test_delete_project_data_ignores_unsafe_artifact_ids(tmp_path):
    pid = "prj-safe-art"
    db_path = paths.conversation_db_path(pid)
    db_path.parent.mkdir(parents=True)
    outside = tmp_path / "outside-keep"
    outside.mkdir()
    (outside / "keep.txt").write_text("stay", encoding="utf-8")
    with sqlite3.connect(str(db_path)) as con:
        con.execute("CREATE TABLE artifacts (artifact_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO artifacts VALUES (?)", (str(outside),))
        con.execute("INSERT INTO artifacts VALUES ('..')")
        con.execute("INSERT INTO artifacts VALUES ('art-ok')")
    safe_dir = paths.data_dir() / "artifacts" / "art-ok"
    safe_dir.mkdir(parents=True)
    (safe_dir / "f.txt").write_text("x", encoding="utf-8")

    _delete_project_data(pid)

    assert outside.exists()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "stay"
    assert not safe_dir.exists()


# --------------------------------------------------------------------- 路由门禁


@pytest.mark.asyncio
async def test_hard_delete_route_gates_on_active_compute_jobs():
    app = create_v2_app(RuntimeCore(strict_events=True))
    core = app.state.runtime_core
    db = ComputeDB().init()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/v2/projects", json={"name": "doomed"})
        project_id = resp.json()["data"]["id"]

        # hard=false 保持现状：归档
        resp = await client.delete(f"/api/v2/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["archived"] is True

        # 有非终态 compute job → 409，提示先 cancel-all
        job_id = insert_compute_job(
            db,
            node_id="node-local",
            conversation_id=project_id,
            session_id=None,
            path="/tmp/input.gjf",
            state="ready",
            jobtype="gaussian",
        )
        resp = await client.delete(f"/api/v2/projects/{project_id}?hard=true")
        assert resp.status_code == 409

        # 作业落终态后门禁放开：硬删除成功，项目消失
        from cloudra.services.compute_store import acancel_all_compute_jobs

        await acancel_all_compute_jobs(db)
        assert get_compute_job(db, job_id)["state"] == "cancelled"
        resp = await client.delete(f"/api/v2/projects/{project_id}?hard=true")
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True
        assert resp.json()["data"] == {"deleted": project_id}
        assert project_id not in core.projects
        resp = await client.get("/api/v2/projects", params={"include_archived": True})
        assert all(p["id"] != project_id for p in resp.json())


@pytest.mark.asyncio
async def test_hard_delete_route_rejects_unarchived_project():
    app = create_v2_app(RuntimeCore(strict_events=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/v2/projects", json={"name": "keep"})
        project_id = resp.json()["data"]["id"]
        resp = await client.delete(f"/api/v2/projects/{project_id}?hard=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] is False
        assert body["data"]["error"]["code"] == "state_conflict"


# ------------------------------------------------------- compute_notify 健壮性


def _set_end_timestamp(db: ComputeDB, task_id: int) -> None:
    import time

    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET end_timestamp=? WHERE id=?", (time.time(), task_id))
        con.commit()


@pytest.mark.asyncio
async def test_deleted_project_terminal_jobs_are_marked_notified_without_delivery():
    """已硬删除项目的终态未通知作业：记 warning 并落 notified_at 终结（不再
    每 tick 重扫死信）；从未存在过的项目仍按"未加载"跳过，不落 notified_at。"""
    core = RuntimeCore(strict_events=True)
    project = await _create(core)
    await _archive(core, project.id)
    await _execute(core, "project.delete", target={"project_id": project.id})

    db = ComputeDB().init()
    deleted_job = insert_compute_job(
        db, node_id="node-local", conversation_id=project.id, session_id=None,
        path="/tmp/a.gjf", state="done", jobtype="gaussian",
    )
    unknown_job = insert_compute_job(
        db, node_id="node-local", conversation_id="prj-neverexisted", session_id=None,
        path="/tmp/b.gjf", state="done", jobtype="gaussian",
    )
    _set_end_timestamp(db, deleted_job)
    _set_end_timestamp(db, unknown_job)

    broker = ComputeNotifyBroker(core)
    await broker._poll_all()

    assert get_compute_job(db, deleted_job)["notified_at"] is not None
    assert get_compute_job(db, unknown_job)["notified_at"] is None
