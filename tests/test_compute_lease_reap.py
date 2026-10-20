"""租约耗尽 reap 必须以 calc/guard flock 为存活判定，不得误杀还在跑的作业。"""

from __future__ import annotations

import os
import time

import pytest

from cloudra.infra.compute_utils import calc_lock_path
from cloudra.infra.flocks import try_acquire_lock
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import (
    get_compute_job,
    insert_compute_job,
    reap_exhausted_compute_leases,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="fcntl flock is POSIX-only")


def _exhausted_running(db: ComputeDB, path: str, *, attempts: int = 3) -> int:
    job_id = insert_compute_job(
        db,
        node_id="node-local",
        conversation_id="conv",
        session_id="s1",
        path=path,
        state="running",
        jobtype="gaussian",
        scheduler="local",
    )
    with db.connect() as con:
        con.execute(
            "UPDATE compute_jobs SET lease_expires_at=?, attempt_count=? WHERE id=?",
            (time.time() - 10, attempts, job_id),
        )
        con.commit()
    return job_id


def test_reap_skips_job_whose_calc_lock_is_held(tmp_path):
    workdir = tmp_path / "job"
    workdir.mkdir()
    inp = workdir / "input.gjf"
    inp.write_text("x\n")
    db = ComputeDB().init()
    job_id = _exhausted_running(db, str(inp))
    fd = try_acquire_lock(calc_lock_path(str(workdir), job_id))
    assert fd is not None
    try:
        reaped = reap_exhausted_compute_leases(db, max_attempts=3)
        assert reaped == []
        assert get_compute_job(db, job_id)["state"] == "running"
    finally:
        os.close(fd)


def test_reap_fails_job_when_no_lock_held(tmp_path):
    workdir = tmp_path / "job"
    workdir.mkdir()
    inp = workdir / "input.gjf"
    inp.write_text("x\n")
    db = ComputeDB().init()
    job_id = _exhausted_running(db, str(inp))
    reaped = reap_exhausted_compute_leases(db, max_attempts=3)
    assert reaped == [job_id]
    row = get_compute_job(db, job_id)
    assert row["state"] == "failed"
    assert "lease retry budget exhausted" in (row["last_error"] or "")


@pytest.mark.parametrize("scheduler", ["slurm", "ssh_local", "ssh_slurm"])
def test_reap_leaves_submitted_remote_execution_to_poller(tmp_path, scheduler):
    db = ComputeDB().init()
    job_id = _exhausted_running(db, str(tmp_path / "input.inp"))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET scheduler=?,scheduler_job_id='submitted-123' WHERE id=?",
                    (scheduler, job_id))
        con.commit()
    assert reap_exhausted_compute_leases(db) == []
    assert get_compute_job(db, job_id)["state"] == "running"
