"""Compute executor / scheduler daemon: claim ready jobs and drive run_compute."""

from __future__ import annotations

import asyncio
import json
import sys
import time

import pytest

from cloudra.persistence.database import ComputeDB


def _insert_job(db: ComputeDB, *, state: str = "ready", path: str = "/tmp/h2.gjf",
                jobtype: str = "gaussian", scheduler: str = "local",
                scheduler_options: dict | None = None,
                conversation_id: str = "proj-1") -> int:
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype,
             start_timestamp, end_timestamp, scheduler, scheduler_options)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                conversation_id, "sess-1", path, state, jobtype,
                -1, -1, scheduler,
                json.dumps(scheduler_options or {"type": scheduler}, ensure_ascii=False),
            ),
        )
        job_id = int(cur.lastrowid)
        con.commit()
    return job_id


def _job_row(db: ComputeDB, job_id: int) -> dict:
    with db.connect() as con:
        cur = con.execute(
            """SELECT state, last_error, lease_owner, lease_expires_at, path
            FROM compute_jobs WHERE id=?""",
            (job_id,),
        )
        row = cur.fetchone()
    keys = ("state", "last_error", "lease_owner", "lease_expires_at", "path")
    return dict(zip(keys, row))


@pytest.mark.asyncio
async def test_run_compute_launches_detached_guard_for_local_job(monkeypatch):
    from cloudra.runtime.compute_executor import run_compute

    db = ComputeDB().init()
    gjf = "/tmp/cloudra-test.gjf"
    job_id = _insert_job(db, state="running", path=gjf, conversation_id="proj-local")
    launched: list[dict] = []

    async def fake_launch(**kwargs):
        launched.append(kwargs)
        return True, ""

    monkeypatch.setattr(
        "cloudra.runtime.compute_executor.check_job_type",
        lambda job_type, workdir: (True, ""),
    )
    monkeypatch.setattr(
        "cloudra.runtime.compute_executor.launch_compute_processes", fake_launch
    )

    rc = await run_compute(job_id, db)
    assert rc == 0
    assert launched == [
        {
            "task_id": job_id,
            "input_file": gjf,
            "job_type": "gaussian",
            "conv_id": "proj-local",
            "db_path": db.path,
            "wait_for_calculator": False,
        }
    ]
    row = _job_row(db, job_id)
    assert row["state"] == "running"
    # spawn 后租约延长到 1h（守护进程对账器在 guard 锁存活期间负责续租），
    # 不再是过去的 14 天静态租约
    assert row["lease_expires_at"] > time.time() + 1800
    assert row["lease_expires_at"] <= time.time() + 3600 + 60


@pytest.mark.asyncio
async def test_run_compute_marks_failed_when_input_missing():
    from cloudra.runtime.compute_executor import run_compute

    db = ComputeDB().init()
    job_id = _insert_job(db, state="running", path="")

    rc = await run_compute(job_id, db)
    assert rc == 1
    row = _job_row(db, job_id)
    assert row["state"] == "failed"
    assert row["last_error"]


@pytest.mark.asyncio
async def test_run_compute_dispatches_slurm(monkeypatch):
    from cloudra.runtime.compute_executor import run_compute

    db = ComputeDB().init()
    job_id = _insert_job(
        db, state="running", scheduler="slurm",
        scheduler_options={"type": "slurm", "partition": "compute"},
    )
    called: list[tuple] = []

    async def fake_slurm(task_id, db_path, *, scheduler, **_kwargs):
        called.append((task_id, db_path, scheduler))
        return 0

    monkeypatch.setattr("cloudra.runtime.compute_executor.run_slurm_compute", fake_slurm)

    rc = await run_compute(job_id, db)
    assert rc == 0
    assert called[0][0] == job_id
    assert called[0][1] == db.path
    assert called[0][2]["partition"] == "compute"


@pytest.mark.asyncio
async def test_scheduler_claims_ready_job_and_runs(monkeypatch):
    from cloudra.scheduler.daemon import SchedulerDaemon

    db = ComputeDB().init()
    gjf = "/tmp/claim.gjf"
    job_id = _insert_job(db, state="ready", path=gjf)
    launched: list[int] = []

    async def fake_launch(**kwargs):
        launched.append(int(kwargs["task_id"]))
        return True, ""

    monkeypatch.setattr(
        "cloudra.runtime.compute_executor.check_job_type",
        lambda job_type, workdir: (True, ""),
    )
    monkeypatch.setattr(
        "cloudra.runtime.compute_executor.launch_compute_processes", fake_launch
    )

    # reconcile_interval 拉满：测试只验认领+拉起路径，不触发 adopt guard 对账
    daemon = SchedulerDaemon(
        poll_interval=0.05, reconcile_interval=9999.0, worker_id="test-worker"
    )
    await daemon.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if launched:
                break
            await asyncio.sleep(0.05)
        assert launched == [job_id]
        row = _job_row(db, job_id)
        assert row["state"] == "running"
        assert row["lease_owner"] == "test-worker"
    finally:
        await daemon.close()


@pytest.mark.skipif(not sys.platform.startswith(("linux", "darwin")), reason="POSIX only")
def test_calc_spawn_preexec_lowers_priority():
    """guard 拉 calculator 的 preexec_fn 必须真的把子进程 nice 降下来。

    控制面在 CPU 打满时靠 CFS 权重差存活；回归成不降权会让状态同步链路
    被计算任务饿死。
    """
    import subprocess

    from cloudra.runtime.monitor import _CALC_NICE_LEVEL, _lower_sched_priority

    out = subprocess.check_output(
        [sys.executable, "-c", "import os; print(os.getpriority(0, 0))"],
        preexec_fn=_lower_sched_priority,
    )
    assert int(out.strip()) >= _CALC_NICE_LEVEL
