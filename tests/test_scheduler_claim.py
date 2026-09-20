"""容量感知认领（按节点分池）：priority/FIFO 排序、每节点独立额度、
未知节点跳过、attempt 重置（中央 compute.db）。

容量池解耦的核心契约：每个节点只在自己的额度内认领，本地额度与云端额度
互不吃；作业归属节点不在注册表里时**跳过不认领**（绝不改投到别的机器上跑）。
"""

from __future__ import annotations

import time

from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import (
    claim_ready_compute_job_with_capacity,
    compute_inflight_usage_by_node,
    reset_compute_attempt_count,
)

# 两个节点各自的额度：本地 2 槽 / 8 核，云端 4 槽 / 32 核
CAPS = {
    "workstation": {"max_concurrent": 2, "cpus": 8, "memory_mb": 8192},
    "hpc": {"max_concurrent": 4, "cpus": 32, "memory_mb": 32768},
}
DEFAULT_NODE = "workstation"
FAIR_SHARE = {"workstation": 4096, "hpc": 8192}


def _claim(db: ComputeDB):
    return claim_ready_compute_job_with_capacity(
        db, worker_id="w", capacities=CAPS, default_node_id=DEFAULT_NODE
    )


def _insert(db: ComputeDB, *, node_id=DEFAULT_NODE, state="ready", priority=0,
            req_cpus=1, req_mem=None, lease=None, scheduler="local") -> int:
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO compute_jobs
            (conversation_id, session_id, path, state, jobtype, start_timestamp,
             end_timestamp, node_id, scheduler, scheduler_options, priority, req_cpus,
             req_memory_mb, lease_expires_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "sched-conv", "sess-1", "/tmp/x.gjf", state, "gaussian",
                -1, -1, node_id, scheduler, "{}", priority, req_cpus, req_mem, lease,
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def _running(db: ComputeDB, *, node_id=DEFAULT_NODE, req_cpus=1, req_mem=None) -> int:
    return _insert(db, node_id=node_id, state="running", req_cpus=req_cpus,
                   req_mem=req_mem, lease=time.time() + 3600)


def test_priority_beats_fifo():
    db = ComputeDB().init()
    low = _insert(db, priority=0)
    high = _insert(db, priority=5)
    assert _claim(db) == high
    # 第二个位置留给低优先级
    assert _claim(db) == low


def test_fifo_within_same_priority():
    db = ComputeDB().init()
    first = _insert(db)
    second = _insert(db)
    assert _claim(db) == first
    assert _claim(db) == second


def test_slots_full_blocks_everything():
    db = ComputeDB().init()
    _running(db)
    _running(db)
    _insert(db)
    assert _claim(db) is None


def test_oversized_skipped_without_blocking_small_jobs():
    db = ComputeDB().init()
    _running(db, req_cpus=7)  # 本节点剩 1 核
    _insert(db, req_cpus=4)   # 放不下，应被跳过
    small = _insert(db, req_cpus=1)
    assert _claim(db) == small


def test_node_quotas_are_independent():
    """本地节点被占满不影响云端节点的额度——容量池解耦的核心契约。"""
    db = ComputeDB().init()
    _running(db, node_id="workstation", req_cpus=8)   # 本地满
    _running(db, node_id="workstation", req_cpus=1)
    local_job = _insert(db, node_id="workstation")     # 属于本地：认不到
    cloud_job = _insert(db, node_id="hpc")             # 属于云端：照常认领

    assert _claim(db) == cloud_job
    # 本地已满：属于本地的作业仍认不到（不会因为云端有空闲就被改投）
    assert _claim(db) is None
    with db.connect() as con:
        state = con.execute(
            "SELECT state FROM compute_jobs WHERE id=?", (local_job,)
        ).fetchone()[0]
    assert state == "ready"


def test_cloud_usage_does_not_consume_local_quota():
    db = ComputeDB().init()
    # 云端 4 槽全占，本地一槽未用
    for _ in range(4):
        _running(db, node_id="hpc", req_cpus=8)
    local_job = _insert(db, node_id="workstation")
    assert _claim(db) == local_job


def test_null_node_id_rows_are_charged_to_default_node():
    """旧行的 node_id 为 NULL：既占用默认节点额度，也归属默认节点认领。"""
    db = ComputeDB().init()
    legacy = _insert(db, node_id=None, state="running", lease=time.time() + 3600)
    usage = compute_inflight_usage_by_node(
        db, default_node_id=DEFAULT_NODE, fair_share_mb=FAIR_SHARE
    )
    assert usage["workstation"] == {"slots": 1, "cpus": 1, "memory_mb": 4096}
    assert "hpc" not in usage

    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='ready', lease_expires_at=NULL WHERE id=?", (legacy,))
        con.commit()
    assert _claim(db) == legacy


def test_unknown_node_job_is_skipped_not_rerouted():
    """作业归属的节点不在注册表里：跳过不认领（绝不改投到别的机器跑），
    而且不阻塞后面属于已注册节点的作业。"""
    db = ComputeDB().init()
    orphan = _insert(db, node_id="decommissioned")
    known = _insert(db, node_id="hpc")
    assert _claim(db) == known
    # 只剩孤儿作业时认领不到（它必须等节点重新注册或被取消）
    assert _claim(db) is None
    with db.connect() as con:
        state = con.execute("SELECT state FROM compute_jobs WHERE id=?", (orphan,)).fetchone()[0]
    assert state == "ready"


def test_null_memory_charged_fair_share():
    db = ComputeDB().init()
    _running(db)  # 未声明内存 → 按本节点公平份额 8192//2=4096 记账
    usage = compute_inflight_usage_by_node(
        db, default_node_id=DEFAULT_NODE, fair_share_mb=FAIR_SHARE
    )
    assert usage["workstation"] == {"slots": 1, "cpus": 1, "memory_mb": 4096}


def test_expired_running_not_reclaimed_by_scheduler_claim():
    db = ComputeDB().init()
    _insert(db, state="running", lease=time.time() - 10)
    # 过期 running 仍占容量直到对账 reap/fail（防止超卖）
    usage = compute_inflight_usage_by_node(
        db, default_node_id=DEFAULT_NODE, fair_share_mb=FAIR_SHARE
    )
    assert usage["workstation"] == {"slots": 1, "cpus": 1, "memory_mb": 4096}
    # claim 只认 ready，绝不抢占 running（归对账器 adopt/reap 处理）
    assert _claim(db) is None


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


def test_afail_compute_job_cas_protection():
    import asyncio

    from cloudra.services.compute_store import afail_compute_job

    async def _run():
        db = ComputeDB().init()
        running = _insert(db, state="running")
        assert await afail_compute_job(db, running, "err") is True
        # already failed: CAS returns False
        assert await afail_compute_job(db, running, "err2") is False

        # cancelled: cannot overwrite
        cancelled = _insert(db, state="cancelled")
        assert await afail_compute_job(db, cancelled, "err") is False
        with db.connect() as con:
            assert con.execute("SELECT state FROM compute_jobs WHERE id=?", (cancelled,)).fetchone()[0] == "cancelled"

        # done: cannot overwrite
        done = _insert(db, state="done")
        assert await afail_compute_job(db, done, "err") is False
        with db.connect() as con:
            assert con.execute("SELECT state FROM compute_jobs WHERE id=?", (done,)).fetchone()[0] == "done"

    asyncio.run(_run())


def test_cancel_requested_counts_toward_inflight_usage():
    """Slurm cancel_requested 仍占节点槽：poller 未 scancel 完之前不得再认领。"""
    db = ComputeDB().init()
    _insert(db, state="cancel_requested", scheduler="slurm")
    _insert(db, state="cancel_requested", scheduler="slurm")
    _insert(db)
    assert _claim(db) is None

