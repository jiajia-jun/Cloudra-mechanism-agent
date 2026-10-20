"""mark_compute_job_failed: reconcile orphaned compute jobs."""

import json
import os
from pathlib import Path

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.tools.Chemtool.mark_compute_job_failed import (
    MarkComputeJobFailed,
    MarkComputeJobFailed_input_schema,
)

_RECORDED = json.loads((Path(__file__).parent / "fixtures/compute_failure_reconciliation_20261021.json").read_text())


def _insert_job(db: ComputeDB, *, state: str = "running", path: str = "/tmp/h2.gjf",
                jobtype: str = "gaussian", scheduler: str = "local", job_id: int | None = None) -> int:
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (id, conversation_id, session_id, path, state, jobtype,
             start_timestamp, end_timestamp, scheduler, scheduler_options)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id, "default", "sess-1", path, state, jobtype,
                -1, -1, scheduler, json.dumps({"type": scheduler}),
            ),
        )
        job_id = int(cur.lastrowid)
        con.commit()
    return job_id


@pytest.mark.asyncio
async def test_running_job_marked_failed_with_reason():
    # 工具 subagent 为 None 时落到 "default" 会话归属
    db = ComputeDB().init()
    job_id = _insert_job(db, state="running")

    result = await MarkComputeJobFailed().tool_call(
        MarkComputeJobFailed_input_schema(job_id=job_id, reason="guard process dead"),
        session=None,
    )

    assert result.is_success is True, result.message
    assert result.previous_state == "running"
    with db.connect() as con:
        row = con.execute(
            "SELECT state, last_error FROM compute_jobs WHERE id=?", (job_id,)
        ).fetchone()
    assert row[0] == "failed"
    assert row[1] == "guard process dead"


@pytest.mark.asyncio
async def test_terminal_job_marking_refused():
    db = ComputeDB().init()
    job_id = _insert_job(db, state="done")

    result = await MarkComputeJobFailed().tool_call(
        MarkComputeJobFailed_input_schema(job_id=job_id, reason="cleanup"),
        session=None,
    )
    assert result.is_success is False
    assert result.previous_state == "done"
    assert "already terminal" in result.message


@pytest.mark.asyncio
async def test_reason_is_required():
    result = await MarkComputeJobFailed().tool_call(
        MarkComputeJobFailed_input_schema(job_id=1, reason="  "),
        session=None,
    )
    assert result.is_success is False
    assert "reason is required" in result.message


@pytest.mark.asyncio
async def test_cancel_requested_is_not_reported_as_failed():
    """CAS 没改行时不得回报成功——cancel_requested 仍非终态。"""
    db = ComputeDB().init()
    job_id = _insert_job(db, state="cancel_requested")

    result = await MarkComputeJobFailed().tool_call(
        MarkComputeJobFailed_input_schema(job_id=job_id, reason="orphan"),
        session=None,
    )
    assert result.is_success is False
    assert result.previous_state == "cancel_requested"
    with db.connect() as con:
        state = con.execute(
            "SELECT state FROM compute_jobs WHERE id=?", (job_id,)
        ).fetchone()[0]
    assert state == "cancel_requested"


@pytest.mark.asyncio
@pytest.mark.parametrize("jobtype", ["gaussian", "orca"])
@pytest.mark.parametrize("lock_kind", ["calc", "guard"])
async def test_public_failure_refuses_native_held_lock(tmp_path, jobtype, lock_kind):
    from cloudra.infra.compute_utils import calc_lock_path, guard_lock_path
    from cloudra.infra.flocks import try_acquire_lock
    from cloudra.services.compute_store import get_compute_job

    db = ComputeDB().init()
    job_id = _insert_job(db, path=str(tmp_path / "input.inp"), jobtype=jobtype)
    lock_path = {"calc": calc_lock_path, "guard": guard_lock_path}[lock_kind](str(tmp_path), job_id)
    fd = try_acquire_lock(lock_path)
    assert fd is not None
    try:
        result = await MarkComputeJobFailed().tool_call(
            MarkComputeJobFailed_input_schema(job_id=job_id, reason="superseded; free the slot"),
            session=None,
        )
        assert not result.is_success
        assert "lock" in result.message
        assert get_compute_job(db, job_id)["state"] == "running"
        assert get_compute_job(db, job_id)["last_error"] in (None, "")
    finally:
        os.close(fd)


@pytest.mark.asyncio
async def test_public_failure_cannot_withdraw_ready_job():
    from cloudra.services.compute_store import get_compute_job

    db = ComputeDB().init()
    job_id = _insert_job(db, state="ready")
    result = await MarkComputeJobFailed().tool_call(
        MarkComputeJobFailed_input_schema(job_id=job_id, reason="withdraw superseded job"),
        session=None,
    )
    assert not result.is_success
    assert "cancel" in result.message.lower()
    assert get_compute_job(db, job_id)["state"] == "ready"


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduler", ["slurm", "ssh_local", "ssh_slurm"])
async def test_public_failure_keeps_remote_liveness_unknown(scheduler, tmp_path):
    from cloudra.services.compute_store import get_compute_job

    db = ComputeDB().init()
    job_id = _insert_job(db, path=str(tmp_path / "input.inp"), scheduler=scheduler)
    result = await MarkComputeJobFailed().tool_call(
        MarkComputeJobFailed_input_schema(job_id=job_id, reason="no local process visible"),
        session=None,
    )
    assert not result.is_success
    assert "remote" in result.message.lower()
    assert get_compute_job(db, job_id)["state"] == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize("lock_kind", ["calc", "guard"])
async def test_shared_failure_refuses_held_lock_off_loop(tmp_path, lock_kind, monkeypatch):
    import threading

    from cloudra.infra.compute_utils import calc_lock_path, guard_lock_path
    from cloudra.infra.flocks import try_acquire_lock
    from cloudra.runtime.compute_executor import _mark_failed
    from cloudra.services.compute_store import afail_compute_job, get_compute_job

    db = ComputeDB().init()
    job_id = _insert_job(db, path=str(tmp_path / "input.inp"))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET lease_expires_at=12345 WHERE id=?", (job_id,))
        con.commit()
    lock_path = {"calc": calc_lock_path, "guard": guard_lock_path}[lock_kind](str(tmp_path), job_id)
    fd = try_acquire_lock(lock_path)
    assert fd is not None
    enqueued = []
    async def enqueue(*args):
        enqueued.append(args)
    monkeypatch.setattr("cloudra.dag.controller.enqueue_compute_review", enqueue)
    import cloudra.infra.flocks as flocks
    original_probe = flocks.is_lock_held
    loop_thread = threading.get_ident()
    def probe(path):
        assert threading.get_ident() != loop_thread
        return original_probe(path)
    monkeypatch.setattr(flocks, "is_lock_held", probe)
    try:
        with pytest.raises(ValueError, match="lock"):
            await afail_compute_job(db, job_id, "launch error")
        await _mark_failed(db, job_id, "launch error")
        assert enqueued == []
        assert get_compute_job(db, job_id)["state"] == "running"
        assert get_compute_job(db, job_id)["lease_expires_at"] == 12345
    finally:
        os.close(fd)


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduler", ["slurm", "ssh_local", "ssh_slurm"])
async def test_shared_failure_preserves_submitted_remote_job(scheduler, tmp_path):
    from cloudra.services.compute_store import afail_compute_job, get_compute_job

    db = ComputeDB().init()
    job_id = _insert_job(db, path=str(tmp_path / "input.inp"), scheduler=scheduler)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET scheduler_job_id='remote-123' WHERE id=?", (job_id,))
        con.commit()
    with pytest.raises(ValueError, match="remote"):
        await afail_compute_job(db, job_id, "poller disconnected")
    assert get_compute_job(db, job_id)["state"] == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize("call", _RECORDED["calls"], ids=lambda call: str(call["request"]["arguments"]["job_id"]))
async def test_real_withdrawal_calls_preserve_live_and_queued_jobs(call, tmp_path, monkeypatch):
    from cloudra.infra.compute_utils import calc_lock_path, guard_lock_path
    from cloudra.infra.flocks import try_acquire_lock
    from cloudra.services.compute_store import get_compute_job

    arguments = call["request"]["arguments"]
    previous = call["receipt"]["result"]["previous_state"]
    job_id = arguments["job_id"]
    db = ComputeDB().init()
    _insert_job(db, state=previous, path=str(tmp_path / "input.inp"), jobtype="orca", job_id=job_id)
    enqueued = []
    async def enqueue(*args):
        enqueued.append(args)
    monkeypatch.setattr("cloudra.dag.controller.enqueue_compute_review", enqueue)
    locks = []
    if str(job_id) in _RECORDED["held_after_wrong_failure"]:
        observed = _RECORDED["held_after_wrong_failure"][str(job_id)]
        assert observed["jobtype"] == "orca"
        for kind, helper in (("calc", calc_lock_path), ("guard", guard_lock_path)):
            assert observed["locks"][kind]
            fd = try_acquire_lock(helper(str(tmp_path), job_id))
            assert fd is not None
            locks.append(fd)
    try:
        result = await MarkComputeJobFailed().tool_call(
            MarkComputeJobFailed_input_schema(**arguments), session=None,
        )
        assert not result.is_success
        assert get_compute_job(db, job_id)["state"] == previous
        assert enqueued == []
    finally:
        for fd in locks:
            os.close(fd)


@pytest.mark.asyncio
async def test_executor_does_not_review_failed_when_cas_did_not_write(tmp_path, monkeypatch):
    from cloudra.runtime.compute_executor import _mark_failed

    db = ComputeDB().init()
    job_id = _insert_job(db, state="done", path=str(tmp_path / "input.inp"))
    enqueued = []
    async def enqueue(*args):
        enqueued.append(args)
    monkeypatch.setattr("cloudra.dag.controller.enqueue_compute_review", enqueue)
    await _mark_failed(db, job_id, "late exception")
    assert enqueued == []
