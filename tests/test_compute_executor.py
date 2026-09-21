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


@pytest.mark.asyncio
async def test_run_slurm_compute_retries_sacct_errors_without_failing_ledger(monkeypatch, tmp_path):
    from cloudra.infra import slurm
    from cloudra.services.compute_store import get_compute_job

    db = ComputeDB().init()
    inp = tmp_path / "h2.gjf"
    inp.write_text("#p\n")
    job_id = _insert_job(
        db,
        state="running",
        path=str(inp),
        scheduler="slurm",
        scheduler_options={"type": "slurm", "poll_seconds": 0.01},
    )
    with db.connect() as con:
        con.execute(
            "UPDATE compute_jobs SET scheduler_job_id='999' WHERE id=?",
            (job_id,),
        )
        con.commit()

    calls = {"n": 0}

    def fake_query(_job_id: str):
        calls["n"] += 1
        if calls["n"] == 1:
            raise slurm.SlurmError("sacct failed")
        return "COMPLETED", "0:0"

    monkeypatch.setattr(slurm, "query_job", fake_query)
    monkeypatch.setattr(
        slurm,
        "_engine_success_from_log",
        lambda *_a, **_k: True,
    )

    rc = await slurm.run_slurm_compute(
        job_id, db.path, scheduler={"poll_seconds": 0.01}
    )
    assert rc == 0
    assert get_compute_job(db, job_id)["state"] == "done"
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_run_slurm_compute_completed_does_not_clobber_cancel(monkeypatch, tmp_path):
    """sacct 查询窗口里 cancel-all 已落 cancel_requested：COMPLETED 不得盖成 done。"""
    from cloudra.infra import slurm
    from cloudra.services.compute_store import get_compute_job

    db = ComputeDB().init()
    inp = tmp_path / "h2.gjf"
    inp.write_text("#p\n")
    job_id = _insert_job(
        db,
        state="running",
        path=str(inp),
        scheduler="slurm",
        scheduler_options={"type": "slurm", "poll_seconds": 0.01},
    )
    with db.connect() as con:
        con.execute(
            "UPDATE compute_jobs SET scheduler_job_id='888' WHERE id=?",
            (job_id,),
        )
        con.commit()

    cancelled = {"n": 0}

    def fake_query(_job_id: str):
        with db.connect() as con:
            con.execute(
                "UPDATE compute_jobs SET state='cancel_requested' WHERE id=?",
                (job_id,),
            )
            con.commit()
        return "COMPLETED", "0:0"

    def fake_cancel(_job_id: str):
        cancelled["n"] += 1

    monkeypatch.setattr(slurm, "query_job", fake_query)
    monkeypatch.setattr(slurm, "cancel_job", fake_cancel)
    monkeypatch.setattr(
        slurm,
        "_engine_success_from_log",
        lambda *_a, **_k: True,
    )

    rc = await slurm.run_slurm_compute(
        job_id, db.path, scheduler={"poll_seconds": 0.01}
    )
    assert rc == 1
    assert get_compute_job(db, job_id)["state"] == "cancelled"
    assert cancelled["n"] == 1


def test_reconcile_lists_running_slurm_jobs_for_reattach():
    from cloudra.scheduler.daemon import SchedulerDaemon

    db = ComputeDB().init()
    job_id = _insert_job(db, state="running", scheduler="slurm")
    with db.connect() as con:
        con.execute(
            "UPDATE compute_jobs SET scheduler_job_id='555' WHERE id=?",
            (job_id,),
        )
        con.commit()
    daemon = SchedulerDaemon()
    orphans = daemon._reconcile_central()
    assert job_id in orphans


def test_reconcile_reattaches_cancel_requested_slurm_jobs():
    """cancel-all 把 Slurm 作业改成 cancel_requested 后，重启对账必须重挂 poller，否则 scancel 永远不会跑。"""
    from cloudra.scheduler.daemon import SchedulerDaemon

    db = ComputeDB().init()
    job_id = _insert_job(db, state="cancel_requested", scheduler="slurm")
    with db.connect() as con:
        con.execute(
            "UPDATE compute_jobs SET scheduler_job_id='556' WHERE id=?",
            (job_id,),
        )
        con.commit()
    daemon = SchedulerDaemon()
    orphans = daemon._reconcile_central()
    assert job_id in orphans


def test_reconcile_recovers_slurm_job_id_after_sbatch_before_mark(monkeypatch):
    """sbatch 已成功、scheduler_job_id 还没回写：对账按 job-name 找回句柄再重挂。"""
    from cloudra.scheduler.daemon import SchedulerDaemon

    db = ComputeDB().init()
    job_id = _insert_job(db, state="running", scheduler="slurm")
    monkeypatch.setattr(
        "cloudra.scheduler.daemon.query_job_by_name",
        lambda name: "777" if name == f"cloudra-{job_id}" else None,
    )
    daemon = SchedulerDaemon()
    orphans = daemon._reconcile_central()
    assert job_id in orphans
    with db.connect() as con:
        stored = con.execute(
            "SELECT scheduler_job_id FROM compute_jobs WHERE id=?",
            (job_id,),
        ).fetchone()[0]
    assert stored == "777"


def test_reconcile_cancels_stuck_slurm_cancel_requested_without_handle(monkeypatch):
    """cancel_requested 且找回不了 Slurm 句柄：过了启动宽限期后应收口为 cancelled。"""
    from cloudra.scheduler.daemon import SchedulerDaemon
    from cloudra.services.compute_store import get_compute_job

    db = ComputeDB().init()
    job_id = _insert_job(db, state="cancel_requested", scheduler="slurm")
    with db.connect() as con:
        con.execute(
            "UPDATE compute_jobs SET start_timestamp=? WHERE id=?",
            (time.time() - 120, job_id),
        )
        con.commit()
    monkeypatch.setattr("cloudra.scheduler.daemon.query_job_by_name", lambda _name: None)
    daemon = SchedulerDaemon()
    orphans = daemon._reconcile_central()
    assert job_id not in orphans
    assert get_compute_job(db, job_id)["state"] == "cancelled"


def test_reconcile_keeps_fresh_slurm_cancel_requested_without_handle(monkeypatch):
    """刚提交、句柄还没回写：宽限期内不得把 cancel_requested 收口掉。"""
    from cloudra.scheduler.daemon import SchedulerDaemon
    from cloudra.services.compute_store import get_compute_job

    db = ComputeDB().init()
    job_id = _insert_job(db, state="cancel_requested", scheduler="slurm")
    with db.connect() as con:
        con.execute(
            "UPDATE compute_jobs SET start_timestamp=? WHERE id=?",
            (time.time(), job_id),
        )
        con.commit()
    monkeypatch.setattr("cloudra.scheduler.daemon.query_job_by_name", lambda _name: None)
    daemon = SchedulerDaemon()
    orphans = daemon._reconcile_central()
    assert job_id not in orphans
    assert get_compute_job(db, job_id)["state"] == "cancel_requested"
