"""Compute executor / broker: claim ready jobs that v1 workers used to pick up."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from cloudra.persistence.database import ConversationDB


def _insert_job(db: ConversationDB, *, state: str = "ready", path: str = "/tmp/h2.gjf",
                jobtype: str = "gaussian", scheduler: str = "local",
                scheduler_options: dict | None = None) -> int:
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype,
             start_timestamp, end_timestamp, scheduler, scheduler_options)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                db.conversation_id, "sess-1", path, state, jobtype,
                -1, -1, scheduler,
                json.dumps(scheduler_options or {"type": scheduler}, ensure_ascii=False),
            ),
        )
        job_id = int(cur.lastrowid)
        con.commit()
    return job_id


def _job_row(db: ConversationDB, job_id: int) -> dict:
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

    db = ConversationDB("proj-local").init()
    gjf = "/tmp/cloudra-test.gjf"
    job_id = _insert_job(db, state="running", path=gjf)
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

    rc = await run_compute(job_id, db.path)
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
    assert row["lease_expires_at"] > time.time() + 86400


@pytest.mark.asyncio
async def test_run_compute_marks_failed_when_input_missing():
    from cloudra.runtime.compute_executor import run_compute

    db = ConversationDB("proj-bad").init()
    job_id = _insert_job(db, state="running", path="")

    rc = await run_compute(job_id, db.path)
    assert rc == 1
    row = _job_row(db, job_id)
    assert row["state"] == "failed"
    assert row["last_error"]


@pytest.mark.asyncio
async def test_run_compute_dispatches_slurm(monkeypatch):
    from cloudra.runtime.compute_executor import run_compute

    db = ConversationDB("proj-slurm").init()
    job_id = _insert_job(
        db, state="running", scheduler="slurm",
        scheduler_options={"type": "slurm", "partition": "compute"},
    )
    called: list[tuple] = []

    async def fake_slurm(task_id, db_path, *, scheduler, **_kwargs):
        called.append((task_id, db_path, scheduler))
        return 0

    monkeypatch.setattr("cloudra.runtime.compute_executor.run_slurm_compute", fake_slurm)

    rc = await run_compute(job_id, db.path)
    assert rc == 0
    assert called[0][0] == job_id
    assert called[0][1] == db.path
    assert called[0][2]["partition"] == "compute"


@pytest.mark.asyncio
async def test_broker_claims_ready_job_and_runs(monkeypatch):
    from cloudra.runtime.compute_executor import ComputeBroker

    db = ConversationDB("proj-claim").init()
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

    broker = ComputeBroker(poll_interval=0.05, worker_id="test-worker")
    await broker.start()
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
        await broker.close()
