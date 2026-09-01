"""容量感知认领：priority/FIFO 排序、容量跳过、attempt 重置（中央 compute.db）。"""

from __future__ import annotations

import time

from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import (
    claim_ready_compute_job_with_capacity,
    compute_inflight_usage,
    reset_compute_attempt_count,
)

CAP = {"max_concurrent": 2, "cpus": 8, "memory_mb": 8192}


def _insert(db: ComputeDB, *, state="ready", priority=0, req_cpus=1,
            req_mem=None, lease=None) -> int:
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype, start_timestamp,
             end_timestamp, scheduler, scheduler_options, priority, req_cpus,
             req_memory_mb, lease_expires_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "sched-conv", "sess-1", "/tmp/x.gjf", state, "gaussian",
                -1, -1, "local", "{}", priority, req_cpus, req_mem, lease,
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def _running(db: ComputeDB, *, req_cpus=1, req_mem=None) -> int:
    return _insert(db, state="running", req_cpus=req_cpus, req_mem=req_mem,
                   lease=time.time() + 3600)


def test_priority_beats_fifo():
    db = ComputeDB().init()
    low = _insert(db, priority=0)
    high = _insert(db, priority=5)
    claimed = claim_ready_compute_job_with_capacity(db, worker_id="w", capacity=CAP)
    assert claimed == high
    # 第二个位置留给低优先级
    claimed2 = claim_ready_compute_job_with_capacity(db, worker_id="w", capacity=CAP)
    assert claimed2 == low


def test_fifo_within_same_priority():
    db = ComputeDB().init()
    first = _insert(db)
    second = _insert(db)
    assert claim_ready_compute_job_with_capacity(db, worker_id="w", capacity=CAP) == first
    assert claim_ready_compute_job_with_capacity(db, worker_id="w", capacity=CAP) == second


def test_slots_full_blocks_everything():
    db = ComputeDB().init()
    _running(db)
    _running(db)
    _insert(db)
    assert claim_ready_compute_job_with_capacity(db, worker_id="w", capacity=CAP) is None


def test_oversized_skipped_without_blocking_small_jobs():
    db = ComputeDB().init()
    _running(db, req_cpus=7)  # 剩 1 核
    _insert(db, req_cpus=4)   # 放不下，应被跳过
    small = _insert(db, req_cpus=1)
    assert claim_ready_compute_job_with_capacity(db, worker_id="w", capacity=CAP) == small


def test_null_memory_charged_fair_share():
    db = ComputeDB().init()
    _running(db)  # 未声明内存 → 按公平份额 8192//2=4096 记账
    usage = compute_inflight_usage(db, default_mem=CAP["memory_mb"] // CAP["max_concurrent"])
    assert usage == (1, 1, 4096)


def test_expired_lease_reclaimable():
    db = ComputeDB().init()
    job = _insert(db, state="running", lease=time.time() - 10)
    # 租约过期不占容量（claim 会把它作为候选重领）
    assert compute_inflight_usage(db, default_mem=4096) == (0, 0, 0)
    assert claim_ready_compute_job_with_capacity(db, worker_id="w2", capacity=CAP) == job


def test_reset_attempt_count_only_for_owner():
    db = ComputeDB().init()
    job = _insert(db, state="running", lease=time.time() + 3600)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET attempt_count=2, lease_owner='w' WHERE id=?", (job,))
        con.commit()
    reset_compute_attempt_count(db, job, "other-worker")
    with db.connect() as con:
        assert con.execute("SELECT attempt_count FROM compute_jobs WHERE id=?", (job,)).fetchone()[0] == 2
    reset_compute_attempt_count(db, job, "w")
    with db.connect() as con:
        assert con.execute("SELECT attempt_count FROM compute_jobs WHERE id=?", (job,)).fetchone()[0] == 0
