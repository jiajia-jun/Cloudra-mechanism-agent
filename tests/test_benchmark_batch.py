"""benchmark/batch.py — GH #32 Web 控制面批次（服务层 + API 路由）。"""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.benchmark.batch import BenchmarkService
from cloudra.benchmark.runner import BenchmarkDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentState, CommandRejected


def _task_json(task_id: str) -> str:
    from cloudra.benchmark.schema import (
        GoldSpec,
        PromptSpec,
        SystemSpec,
        TaskSpec,
    )
    from cloudra.runtime_v2.schemas import OrchestrationMode

    task = TaskSpec(
        task_id=task_id,
        tier="easy",
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


def _write_tasks(dir_path, *ids: str) -> str:
    dir_path.mkdir(parents=True, exist_ok=True)
    for tid in ids:
        (dir_path / f"{tid}.json").write_text(_task_json(tid))
    return str(dir_path)


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
    core.agent_host.start_run(agent)  # finish_run 需要 current_run
    core.event_log.append(
        "agent.message_emitted",
        stream="agent",
        project_id=st.project_id,
        session_id=agent.id,
        data={"content": "Done. The computed barrier is 5.0 kcal/mol."},
    )
    core.agent_host.finish_run(agent, outcome="succeeded")

    await asyncio.wait_for(batch._task, timeout=5.0)
    final = service.status()
    assert final["status"] == "done"
    assert final["tasks"][0]["status"] == "scored"
    assert final["tasks"][0]["final_score"] == -1.0  # 空沙箱无图 → 零证据倒扣
    assert final["tasks"][0]["outcome"] == "failed"

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
        core.agent_host.transition(
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
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
