"""benchmark/batch.py — GH #32 Web 控制面批次（服务层 + API 路由）。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.benchmark.batch import BenchmarkService
from cloudra.benchmark.runner import BenchmarkDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentState, CommandRejected


def _task_json(task_id: str, tier: str = "easy") -> str:
    from cloudra.benchmark.schema import (
        GoldSpec,
        PromptSpec,
        SystemSpec,
        TaskSpec,
    )
    from cloudra.runtime_v2.schemas import OrchestrationMode

    task = TaskSpec(
        task_id=task_id,
        tier=tier,
        prompt=PromptSpec(query="solve it", orchestration_mode=OrchestrationMode.STANDARD),
        system=SystemSpec(reactants=["C"]),
        gold=GoldSpec(
            mechanism_graph={
                "nodes": [{"id": "R", "role": "reactant", "smiles": ["C"]}],
                "edges": [],
            }
        ),
    )
    return json.dumps(task.model_dump(mode="json"))


def _write_tasks(dir_path, *ids: str, tier: str = "easy") -> str:
    dir_path.mkdir(parents=True, exist_ok=True)
    for tid in ids:
        (dir_path / f"{tid}.json").write_text(_task_json(tid, tier=tier))
    return str(dir_path)


def _patch_builtin_tiers(monkeypatch, tmp_path, tiers: dict[str, tuple[str, ...]]):
    """把内置档位目录指到 tmp_path（真实题库不动，只验证解析与路由接线）。"""
    import cloudra.benchmark.batch as batch_mod

    root = tmp_path / "tiers"
    for tier, ids in tiers.items():
        _write_tasks(root / tier, *ids, tier=tier)
    monkeypatch.setattr(batch_mod, "builtin_tier_dir", lambda tier: root / tier)
    return root


async def _wait_until(predicate, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        if predicate():
            return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.01)


def _service(tmp_path, core=None):
    core = core or RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    service = BenchmarkService(core, bus, data_dir=tmp_path / "bench")
    return core, bus, service


@pytest.mark.asyncio
async def test_batch_runs_task_scores_and_persists(tmp_path):
    core, bus, service = _service(tmp_path)
    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")

    snap = await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1, timeout=60.0)
    assert snap["status"] == "running" and snap["batch_id"]
    batch = service._batch
    await _wait_until(lambda: batch.task_states[0].agent_id)

    st = batch.task_states[0]
    agent = core.require_agent(st.agent_id)
    assert st.project_id.startswith("prj")
    await core.agent_host.start_run(agent)  # finish_run 需要 current_run
    core.event_log.append(
        "agent.message_emitted",
        stream="agent",
        project_id=st.project_id,
        session_id=agent.id,
        data={"content": "Done. The computed barrier is 5.0 kcal/mol."},
    )
    await core.agent_host.finish_run(agent, outcome="succeeded")

    await asyncio.wait_for(batch._task, timeout=5.0)
    final = service.status()
    assert final["status"] == "done"
    assert final["tasks"][0]["status"] == "scored"
    assert final["tasks"][0]["final_score"] == -1.0  # 空沙箱无图 → 零证据倒扣
    assert any(
        "no parseable mechanism graph" in n for n in final["tasks"][0]["notes"]
    )

    db = BenchmarkDB(tmp_path / "bench" / "benchmark.db")
    batches = db.list_batches()
    assert len(batches) == 1 and batches[0]["status"] == "done"
    runs = db.list_runs_for(final["batch_id"])
    assert [r["task_id"] for r in runs] == ["T1"]

    history = await service.history()
    assert history["batches"][0]["batch_id"] == final["batch_id"]


@pytest.mark.asyncio
async def test_batch_stop_cancels_running_tasks(tmp_path):
    core, bus, service = _service(tmp_path)
    tasks_dir = _write_tasks(tmp_path / "tasks", "T1", "T2")
    await service.start(tasks_dirs=[tasks_dir], only="", concurrency=2, timeout=60.0)
    batch = service._batch
    await _wait_until(lambda: all(st.agent_id for st in batch.task_states))

    for st in batch.task_states:
        await core.agent_host.transition(
            core.require_agent(st.agent_id), AgentState.RUNNING, reason="run_started"
        )

    snap = await service.stop()
    assert snap["status"] == "stopping"

    await asyncio.wait_for(batch._task, timeout=5.0)
    final = service.status()
    assert final["status"] == "stopped"
    assert all(t["status"] == "cancelled" for t in final["tasks"])
    db = BenchmarkDB(tmp_path / "bench" / "benchmark.db")
    runs = db.list_runs_for(final["batch_id"])
    assert {r["task_id"] for r in runs} == {"T1", "T2"}
    assert all("cancelled by batch stop" in r["notes"] for r in runs)


@pytest.mark.asyncio
@pytest.mark.parametrize("gate_action", ["wait_background", "allow_final"])
async def test_batch_stop_converges_with_succeeded_agent_and_live_compute(
    tmp_path, gate_action
):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import aget_compute_job, ainsert_compute_job

    core, _bus, service = _service(tmp_path)
    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")
    await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1, timeout=30.0)
    batch = service._batch
    await _wait_until(lambda: batch.task_states[0].agent_id)
    agent = core.require_agent(batch.task_states[0].agent_id)
    run_id = await core.agent_host.start_run(agent)
    core.event_log.append(
        "agent.completion_gate", stream="agent", project_id=agent.project_id,
        session_id=agent.id, run_id=run_id,
        data={"action": gate_action, "source": "schedule"},
    )
    await core.agent_host.finish_run(agent, outcome="succeeded")
    db = await ComputeDB().ainit()
    job_id = await ainsert_compute_job(
        db, node_id="node-local", conversation_id=agent.project_id,
        session_id=agent.id, path=str(tmp_path / "input.gjf"),
        state="ready", jobtype="gaussian", scheduler="local", scheduler_options="{}",
    )

    await service.stop()
    await asyncio.wait_for(batch._task, timeout=1.0)

    task = service.status()["tasks"][0]
    assert service.status()["status"] == "stopped"
    assert task["status"] == "cancelled"
    assert agent.state is (
        AgentState.CANCELLED if gate_action == "wait_background" else AgentState.SUCCEEDED
    )
    assert (await aget_compute_job(db, job_id))["state"] == "ready"


@pytest.mark.asyncio
async def test_service_rejects_second_start_and_unknown_dir(tmp_path):
    core, bus, service = _service(tmp_path)
    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")
    await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1, timeout=60.0)
    with pytest.raises(CommandRejected) as exc:
        await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1, timeout=60.0)
    assert exc.value.code == "state_conflict"

    with pytest.raises(CommandRejected):
        core2 = RuntimeCore(strict_events=True)
        bus2 = CommandBus(core2)
        svc2 = BenchmarkService(core2, bus2, data_dir=tmp_path / "bench2")
        await svc2.start(
            tasks_dirs=[str(tmp_path / "missing")], only="", concurrency=1, timeout=60.0
        )


@pytest.mark.asyncio
async def test_router_status_start_stop_history(tmp_path):
    from cloudra.services.api_v2 import create_v2_app

    core = RuntimeCore(strict_events=True)
    app = create_v2_app(core)
    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        idle = (await client.get("/api/v2/benchmark/status")).json()
        assert idle["status"] == "idle"

        running = (
            await client.post(
                "/api/v2/benchmark/start",
                json={"tasks_dirs": [tasks_dir], "concurrency": 1, "timeout": 60.0},
            )
        ).json()
        assert running["status"] == "running"

        conflict = await client.post(
            "/api/v2/benchmark/start", json={"tasks_dirs": [tasks_dir]}
        )
        assert conflict.status_code == 409

        stopping = (await client.post("/api/v2/benchmark/stop")).json()
        assert stopping["status"] == "stopping"

        # 等待批次收敛（无 runner 的 agent 被 stop 级联取消）
        deadline = asyncio.get_running_loop().time() + 5.0
        while True:
            status = (await client.get("/api/v2/benchmark/status")).json()
            if status["status"] == "stopped":
                break
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.01)

        history = (await client.get("/api/v2/benchmark/runs")).json()
        assert history["batches"][0]["status"] == "stopped"
        assert [r["task_id"] for r in history["batches"][0]["runs"]] == ["T1"]


@pytest.mark.asyncio
async def test_status_and_runs_agree_the_moment_a_batch_reaches_terminal(
    tmp_path, monkeypatch
):
    """/status（内存快照）报终态的那一刻，/runs（历史 DB）必须已经一致。

    注入一次慢落库，把"内存已翻终态、库还没写"的窗口放大到确定可测：终态必须
    先落库、再发布到内存。旧顺序（内存先翻，DB 经 to_thread 后写）会让两个接口
    在收敛瞬间对同一批次给出矛盾答案——本机全量跑实测偶发红
    （test_router_status_start_stop_history，单跑 20 次不复现、只在全量负载下偶发）。
    """
    import time as _time

    from cloudra.benchmark.runner import BenchmarkDB
    from cloudra.services.api_v2 import create_v2_app

    real_finish_batch = BenchmarkDB.finish_batch

    def slow_finish_batch(self, batch_id, status):
        _time.sleep(0.5)  # 放大发布顺序错误的窗口
        return real_finish_batch(self, batch_id, status)

    monkeypatch.setattr(BenchmarkDB, "finish_batch", slow_finish_batch)

    core = RuntimeCore(strict_events=True)
    app = create_v2_app(core)
    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await client.post(
            "/api/v2/benchmark/start",
            json={"tasks_dirs": [tasks_dir], "concurrency": 1, "timeout": 60.0},
        )
        await client.post("/api/v2/benchmark/stop")

        deadline = _time.monotonic() + 30.0
        while True:
            status = (await client.get("/api/v2/benchmark/status")).json()["status"]
            if status == "stopped":
                break
            assert _time.monotonic() < deadline, "batch did not converge to stopped"
            await asyncio.sleep(0.01)

        # 内存侧刚报终态，历史侧必须已经是同一终态（同序：DB -> 内存 -> 事件）
        history = (await client.get("/api/v2/benchmark/runs")).json()

    assert history["batches"][0]["status"] == "stopped"


# ---------------------------------------------------------------------------
# Task 5（P1）：沙箱生命周期契约（失败即基建失败；占用目录拒绝复用）
# ---------------------------------------------------------------------------

async def _insert_job(path, state="running", conversation_id="prj_old"):
    """直接落一条 compute_jobs 行（DB 事实，不是假执行）。"""
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import ainsert_compute_job

    db = await ComputeDB().ainit()
    return await ainsert_compute_job(
        db, node_id="node-local", conversation_id=conversation_id, session_id="as_old", path=str(path),
        state=state, jobtype="gaussian", scheduler="local", scheduler_options="{}",
    )


@pytest.mark.asyncio
async def test_pending_background_includes_terminal_job_awaiting_notice(tmp_path):
    from cloudra.benchmark.batch import BenchmarkBatch
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.schemas import Command
    from cloudra.services.compute_store import ainsert_compute_job, mark_notified

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "notice"}))).data
    agent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator"},
    ))).data
    batch = BenchmarkBatch(
        core, bus, data_dir=tmp_path, tasks=[], tasks_dirs=[], concurrency=1,
        run_timeout_s=30.0, stuck_grace_s=5.0, poll_interval_s=0.01,
        emit=lambda *_args: None,
    )
    db = await ComputeDB().ainit()
    job_id = await ainsert_compute_job(
        db, node_id="node-local", conversation_id=project.id, session_id=agent.id,
        path=str(tmp_path / "input.gjf"), state="done", jobtype="gaussian",
        scheduler="local", scheduler_options="{}",
    )
    pending = batch._pending_background_factory(project.id, agent.id)
    assert await pending() is True
    mark_notified(db, job_id)
    assert await pending() is False

    child = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "explorer", "parent_session_id": agent.id},
    ))).data
    child_job = await ainsert_compute_job(
        db, node_id="node-local", conversation_id=project.id, session_id=child.id,
        path=str(tmp_path / "child.gjf"), state="done", jobtype="gaussian",
        scheduler="local", scheduler_options="{}",
    )
    assert await pending() is True
    mark_notified(db, child_job)
    assert await pending() is False


@pytest.mark.asyncio
async def test_watcher_timeout_never_scores_parked_succeeded_agent(tmp_path, monkeypatch):
    from cloudra.benchmark.watch import RunWatcher

    async def timeout(self, core, agent, cancel):
        await core.agent_host.start_run(agent)
        await core.agent_host.finish_run(agent, outcome="succeeded")
        await cancel("benchmark run timeout (test)")
        return "benchmark run timeout (test)"

    monkeypatch.setattr(RunWatcher, "wait", timeout)
    core, _bus, service = _service(tmp_path)
    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")
    await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1, timeout=30.0)
    await asyncio.wait_for(service._batch._task, timeout=5.0)

    task = service.status()["tasks"][0]
    assert task["status"] == "error"
    assert "timeout" in task["error"]
    db = BenchmarkDB(tmp_path / "bench" / "benchmark.db")
    runs = db.list_runs_for(service.status()["batch_id"])
    assert len(runs) == 1
    assert runs[0]["final_score"] == 0.0  # watcher 超时：基建失败 0 分行
    assert any("watcher" in note for note in runs[0]["notes"])


@pytest.mark.asyncio
async def test_batch_sandbox_reset_failure_is_infrastructure_error(tmp_path, monkeypatch):
    """沙箱创建失败必须落明确的基建失败：不 spawn、不评分。"""
    core, bus, service = _service(tmp_path)
    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")

    import cloudra.benchmark.batch as batch_mod

    def _boom(self, sandbox):
        raise OSError("sandbox is not creatable")

    monkeypatch.setattr(batch_mod.BenchmarkBatch, "_prepare_sandbox", _boom)
    await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1, timeout=30.0)
    batch = service._batch
    await asyncio.wait_for(batch._task, timeout=10.0)

    final = service.status()
    task = final["tasks"][0]
    assert task["status"] == "error", task
    assert "sandbox" in task["error"].lower(), task["error"]
    # 没有 spawn（无 agent、无项目），也没有评分落库
    assert not task["agent_id"] and not task["project_id"], task
    db = BenchmarkDB(tmp_path / "bench" / "benchmark.db")
    runs = db.list_runs_for(final["batch_id"])
    assert len(runs) == 1 and runs[0]["final_score"] == 0.0  # 基建失败 0 分行
    assert any("sandbox" in note.lower() for note in runs[0]["notes"]), runs[0]["notes"]


@pytest.mark.asyncio
async def test_batch_refuses_sandbox_with_live_compute(tmp_path, monkeypatch):
    """沙箱目录下仍有未竟计算时：拒绝复用该目录（不删旧输入/输出、不 kill
    旧计算），落明确基建失败。沙箱已按批分目录（不复用旧批目录），本用例
    钉住的是这层防呆守卫本身——把目标目录指到带活在跑的作业的目录上。"""
    core, bus, service = _service(tmp_path)
    sandbox = service._data_dir() / "sandboxes" / "occupied"
    sandbox.mkdir(parents=True)
    in_use = sandbox / "calc" / "input.gjf"
    in_use.parent.mkdir(parents=True)
    in_use.write_text("#p HF/3-21G\n\nH2\n\n0 1\nH 0 0 0\nH 0 0 0.74\n", encoding="utf-8")
    job_id = await _insert_job(in_use, state="running")

    import cloudra.benchmark.batch as batch_mod

    monkeypatch.setattr(batch_mod.BenchmarkBatch, "_sandbox_for", lambda self, task_id: sandbox)

    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")
    await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1, timeout=30.0)
    batch = service._batch
    await asyncio.wait_for(batch._task, timeout=10.0)

    final = service.status()
    task = final["tasks"][0]
    assert task["status"] == "error", task
    assert "live compute" in task["error"].lower() or "占用" in task["error"], task["error"]
    # 旧输入/输出未被删除，旧作业仍在册（绝不 kill 计算）
    assert in_use.is_file()
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import list_compute_jobs

    rows = list_compute_jobs(ComputeDB())
    assert [r["id"] for r in rows] == [job_id]
    assert rows[0]["state"] == "running"


# ---------------------------------------------------------------------------
# 档位选题（内置档位免手打路径）
# ---------------------------------------------------------------------------

def test_resolve_tasks_dirs_orders_dedupes_and_rejects(tmp_path, monkeypatch):
    from cloudra.benchmark.batch import TASK_TIERS, resolve_tasks_dirs

    root = _patch_builtin_tiers(
        monkeypatch, tmp_path,
        {"easy": ("E1",), "normal": ("N1",), "hard": ("H1",), "impossible": ("I1",)},
    )
    custom = Path(_write_tasks(tmp_path / "custom", "X1"))

    # 内置档位按 TASK_TIERS 顺序，自定义目录在后
    got = resolve_tasks_dirs([str(custom)], ["impossible", "easy"])
    assert got == [root / "easy", root / "impossible", custom]

    # 同一个目录重复出现只取一次（档位 + 手打同一路径）
    assert resolve_tasks_dirs([str(root / "easy")], ["easy"]) == [root / "easy"]

    # 两者都空 = 内置 easy 档（CLI/旧客户端行为不变）
    assert resolve_tasks_dirs(None, None) == [root / "easy"]
    assert resolve_tasks_dirs([], []) == [root / "easy"]

    with pytest.raises(CommandRejected) as exc:
        resolve_tasks_dirs(None, ["bogus"])
    assert "unknown tier" in exc.value.message
    assert TASK_TIERS[0] == "easy" and set(TASK_TIERS) == {"easy", "normal", "hard", "impossible"}


def test_task_catalog_lists_builtin_tiers(tmp_path, monkeypatch):
    from cloudra.benchmark.batch import task_catalog

    root = _patch_builtin_tiers(
        monkeypatch, tmp_path,
        {"easy": ("E1", "E2"), "normal": ("N1",), "hard": ("H1",), "impossible": ("I1",)},
    )
    catalog = task_catalog()
    assert [c["tier"] for c in catalog] == ["easy", "normal", "hard", "impossible"]
    assert [c["task_count"] for c in catalog] == [2, 1, 1, 1]
    assert catalog[0]["task_ids"] == ["E1", "E2"]
    assert catalog[0]["path"] == str(root / "easy")

    # 缺目录只报 0 题（不炸）；启动时由 resolve_tasks_dirs 拒绝
    (root / "hard" / "H1.json").unlink()
    assert [c["task_count"] for c in task_catalog()] == [2, 1, 0, 1]


def test_catalog_lists_real_task_bank():
    """仓库真实题库仍按四档可枚举（生成器改题集后这里同步可见）。"""
    from cloudra.benchmark.batch import builtin_tier_dir, task_catalog

    catalog = {c["tier"]: c for c in task_catalog()}
    assert len(catalog) == 4
    for entry in catalog.values():
        assert entry["task_count"] == len(entry["task_ids"])
        assert str(builtin_tier_dir(entry["tier"])) == entry["path"]
    assert catalog["easy"]["task_count"] > 0 and catalog["impossible"]["task_count"] > 0


@pytest.mark.asyncio
async def test_service_start_by_tiers(tmp_path, monkeypatch):
    """tiers 选题直接落成批次任务；自定义目录可与之并存。"""
    _patch_builtin_tiers(
        monkeypatch, tmp_path,
        {"easy": ("E1",), "normal": ("N1",), "hard": ("H1",), "impossible": ("I1", "I2")},
    )
    core, bus, service = _service(tmp_path)
    custom = _write_tasks(tmp_path / "custom", "X9")

    snap = await service.start(
        tasks_dirs=[custom], only="", concurrency=1, timeout=60.0,
        tiers=["impossible", "hard"],
    )
    assert [(t["task_id"], t["tier"]) for t in snap["tasks"]] == [
        ("H1", "hard"), ("I1", "impossible"), ("I2", "impossible"), ("X9", "easy"),
    ]
    assert snap["config"]["tasks_dirs"][:2] == [
        str(tmp_path / "tiers" / "hard"), str(tmp_path / "tiers" / "impossible"),
    ]
    await service.stop()
    await asyncio.wait_for(service._batch._task, timeout=5.0)

    # 未知档位 400，且不留下半启动的批次
    core2 = RuntimeCore(strict_events=True)
    svc2 = BenchmarkService(core2, CommandBus(core2), data_dir=tmp_path / "bench2")
    with pytest.raises(CommandRejected) as exc:
        await svc2.start(tasks_dirs=None, only="", concurrency=1, timeout=60.0,
                         tiers=["easyy"])
    assert exc.value.code == "invalid_request"
    assert svc2.status()["batch_id"] is None


@pytest.mark.asyncio
async def test_router_catalog_and_tiers(tmp_path, monkeypatch):
    from cloudra.services.api_v2 import create_v2_app

    _patch_builtin_tiers(
        monkeypatch, tmp_path,
        {"easy": ("E1",), "normal": ("N1",), "hard": ("H1",), "impossible": ("I1",)},
    )
    core = RuntimeCore(strict_events=True)
    app = create_v2_app(core)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        catalog = (await client.get("/api/v2/benchmark/catalog")).json()
        assert [c["tier"] for c in catalog["tiers"]] == ["easy", "normal", "hard", "impossible"]
        assert catalog["tiers"][0]["task_ids"] == ["E1"]

        running = (
            await client.post(
                "/api/v2/benchmark/start",
                json={"tiers": ["hard"], "concurrency": 1, "timeout": 60.0},
            )
        ).json()
        assert [t["task_id"] for t in running["tasks"]] == ["H1"]

        await client.post("/api/v2/benchmark/stop")
        deadline = asyncio.get_running_loop().time() + 5.0
        while True:
            status = (await client.get("/api/v2/benchmark/status")).json()
            if status["status"] == "stopped":
                break
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.01)

        bad = await client.post("/api/v2/benchmark/start", json={"tiers": ["nope"]})
        assert bad.status_code == 400
        assert bad.json()["detail"]["code"] == "invalid_request"
