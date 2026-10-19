"""CLI interruption stops per-task runtimes without cancelling compute jobs."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from cloudra.benchmark.runner import BenchmarkDB
from cloudra.benchmark.schema import TaskSpec


def _tasks(directory: Path, count: int = 3) -> None:
    directory.mkdir()
    for index in range(count):
        task = TaskSpec.model_validate({
            "task_id": f"T{index}", "tier": "easy",
            "prompt": {"query": "wait", "orchestration_mode": "standard"},
            "system": {"reactants": ["C"]},
            "gold": {"mechanism_graph": {
                "nodes": [{"id": "R", "role": "reactant", "smiles": ["C"]}],
                "edges": [],
            }},
        })
        (directory / f"T{index}.json").write_text(task.model_dump_json(), encoding="utf-8")


_SIGNAL_SCRIPT = """
import asyncio
import json
import sys
import time
from pathlib import Path

from cloudra.benchmark import backend
from cloudra.benchmark.__main__ import main
from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker

marker_dir = Path(sys.argv[1])
original_close = ComputeNotifyBroker.close

async def close(self):
    await original_close(self)
    project = next(iter(self.core.projects.values()))
    await asyncio.to_thread((marker_dir / (project.name.split(':')[-1] + '.broker')).touch)

ComputeNotifyBroker.close = close

class WaitingLLM:
    async def complete(self, agent, messages, tools, **kwargs):
        def ready():
            db = ComputeDB().init()
            with db.connect() as connection:
                connection.execute(
                    'INSERT INTO compute_jobs '
                    '(conversation_id, session_id, path, state, jobtype, start_timestamp) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (agent.project_id, agent.id, 'fake.gjf', 'running', 'gaussian', time.time()),
                )
                connection.commit()
            (marker_dir / (agent.project_id + '.ready')).touch()
        await asyncio.to_thread(ready)
        await asyncio.Event().wait()

class LocalBackend(backend.RuntimeV2Backend):
    def __init__(self, **kwargs):
        kwargs.update(llm=WaitingLLM(), start_scheduler=False, poll_interval_s=0.01)
        super().__init__(**kwargs)

    async def _run_task(self, task, sandbox):
        try:
            return await super()._run_task(task, sandbox)
        finally:
            core = self.core_by_task(task.task_id)
            if core is not None and core.runner is not None:
                payload = {
                    'states': [agent.state.value for agent in core.agents.values()],
                    'tasks': len(core.runner._tasks),
                    'background': len(core.runner._background),
                }
                await asyncio.to_thread(
                    (marker_dir / (task.task_id + '.closed')).write_text, json.dumps(payload),
                )

backend.RuntimeV2Backend = LocalBackend
raise SystemExit(main(sys.argv[2:]))
"""


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
@pytest.mark.parametrize("concurrency", [1, 2])
def test_cli_signal_stops_workers_and_records_batch(tmp_path, signum, concurrency):
    tasks_dir, data_dir = tmp_path / "tasks", tmp_path / "benchmark"
    markers = tmp_path / "markers"
    markers.mkdir()
    _tasks(tasks_dir)
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", _SIGNAL_SCRIPT, str(markers),
         "--tasks-dir", str(tasks_dir), "--data-dir", str(data_dir),
         "--backend", "runtime_v2", "--concurrency", str(concurrency)],
        cwd=Path(__file__).resolve().parents[1],
        env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 15
        while len(list(markers.glob("*.ready"))) < concurrency and process.poll() is None:
            if time.monotonic() > deadline:
                pytest.fail("each isolated worker loop must reach the scripted provider")
            time.sleep(0.02)
        if process.poll() is not None:
            output, errors = process.communicate()
            pytest.fail(f"CLI exited before signal: {output}\n{errors}")
        process.send_signal(signum)
        try:
            output, errors = process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            pytest.fail("CLI signal must release every worker and the thread pool")
        assert process.returncode == 128 + signum, (output, errors)
        batches = BenchmarkDB(data_dir / "benchmark.db").list_batches()
        assert len(batches) == 1
        assert batches[0]["status"] == "stopped"
        assert batches[0]["finished_at"] is not None
        runs = BenchmarkDB(data_dir / "benchmark.db").list_runs_for(batches[0]["batch_id"])
        assert {run["task_id"] for run in runs} == {"T0", "T1", "T2"}
        assert all("cancelled by batch stop" in run["notes"] for run in runs), (runs, output, errors)
        assert all(run["final_score"] == 0.0 for run in runs)
        started = {f"T{index}" for index in range(concurrency)}
        assert {path.stem for path in markers.glob("*.closed")} == started
        assert {path.stem for path in markers.glob("*.broker")} == started
        for path in markers.glob("*.closed"):
            assert json.loads(path.read_text()) == {
                "states": ["cancelled"], "tasks": 0, "background": 0,
            }
        with sqlite3.connect(data_dir / "runtime" / "compute.db") as connection:
            assert connection.execute("SELECT state FROM compute_jobs").fetchall() == [
                ("running",),
            ] * concurrency
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


@pytest.mark.parametrize("crash", [False, True])
def test_cli_restores_signal_handlers_after_completion_and_error(tmp_path, monkeypatch, crash):
    from cloudra.benchmark.__main__ import main
    from cloudra.benchmark.runner import BenchmarkRunner

    tasks_dir, data_dir = tmp_path / "tasks", tmp_path / "benchmark"
    _tasks(tasks_dir, count=1)
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    def finish(self, tasks, concurrency):
        assert all(signal.getsignal(sig) is not previous[sig] for sig in previous)
        if crash:
            raise RuntimeError("worker collection failed")
        return []

    monkeypatch.setattr(BenchmarkRunner, "run_all", finish)
    arguments = ["--tasks-dir", str(tasks_dir), "--data-dir", str(data_dir)]
    if crash:
        with pytest.raises(RuntimeError, match="worker collection failed"):
            main(arguments)
    else:
        assert main(arguments) == 0
    assert {sig: signal.getsignal(sig) for sig in previous} == previous
    batch = BenchmarkDB(data_dir / "benchmark.db").list_batches()[0]
    assert batch["status"] == ("error" if crash else "done")
    assert batch["finished_at"] is not None


@pytest.mark.parametrize("close_error", [False, True])
def test_backend_crash_finishes_all_cleanup_even_when_broker_close_fails(
    tmp_path, monkeypatch, close_error,
):
    from cloudra.benchmark.backend import RuntimeV2Backend
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from cloudra.runtime_v2.schemas import Command
    from cloudra.scheduler.daemon import SchedulerDaemon

    tasks_dir = tmp_path / "tasks"
    _tasks(tasks_dir, count=1)
    task = TaskSpec.model_validate_json((tasks_dir / "T0.json").read_text())
    reached_provider = []
    closed = []

    class WaitingLLM:
        async def complete(self, agent, messages, tools, **kwargs):
            reached_provider.append(agent.id)
            await asyncio.Event().wait()

    async def fail_wait(self, bus, agent):
        for payload in (
            {"role_id": "explorer", "parent_session_id": agent.id},
            {"role_id": "explorer"},
        ):
            await bus.execute(Command(
                type="agent.spawn", target={"project_id": agent.project_id}, payload=payload,
            ))
        while not reached_provider:
            await asyncio.sleep(0)
        raise RuntimeError("watcher failed")

    original_close = ComputeNotifyBroker.close

    async def broker_close(self):
        await original_close(self)
        closed.append("broker")
        if close_error:
            raise RuntimeError("notifier close failed")

    async def scheduler_start(self):
        pass

    async def scheduler_close(self):
        closed.append("scheduler")

    monkeypatch.setattr(RuntimeV2Backend, "_wait_terminal", fail_wait)
    monkeypatch.setattr(ComputeNotifyBroker, "close", broker_close)
    monkeypatch.setattr(SchedulerDaemon, "start", scheduler_start)
    monkeypatch.setattr(SchedulerDaemon, "close", scheduler_close)
    backend = RuntimeV2Backend(llm=WaitingLLM(), store_path=tmp_path / "runtime.db")
    message = "notifier close failed" if close_error else "watcher failed"
    with pytest.raises(RuntimeError, match=message):
        backend(task, tmp_path / "sandbox")
    assert closed == ["broker", "scheduler"]
    core = backend.last_core
    assert len(core.agents) == 3
    assert {agent.state.value for agent in core.agents.values()} == {"cancelled"}
    assert not core.runner._tasks
    assert not core.runner._background
    snapshot, _ = core.store.load_snapshot()
    assert {agent["state"] for agent in snapshot["agents"].values()} == {"cancelled"}


def test_parallel_collection_failure_requests_stop_before_joining_workers(tmp_path):
    from cloudra.benchmark.runner import BenchmarkRunner, load_tasks

    tasks_dir = tmp_path / "tasks"
    _tasks(tasks_dir, count=2)
    stop_event, peer_started = threading.Event(), threading.Event()
    stopped = []

    def backend(task, sandbox):
        if task.task_id == "T0":
            assert peer_started.wait(timeout=2)
            raise KeyboardInterrupt("collection interrupted")
        peer_started.set()
        stopped.append(stop_event.wait(timeout=2))

    runner = BenchmarkRunner(tmp_path / "benchmark", backend=backend, stop_event=stop_event)
    with pytest.raises(KeyboardInterrupt, match="collection interrupted"):
        runner.run_all(load_tasks(tasks_dir), concurrency=2)
    assert stopped == [True]
    assert runner.db.list_runs_for("")[0]["notes"] == ["cancelled by batch stop"]
