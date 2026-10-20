"""Shared execution pieces for claimed compute_jobs (guard, Slurm, or SSH remote).

The scheduler daemon (``cloudra.scheduler``) claims rows from the central
compute.db with a lease and drives ``run_compute``; this module holds the
execution half.

Local jobs spawn the detached guard and extend the lease so a later poll
does not start a second calculator.  Slurm and SSH-remote jobs stay in the
claiming process and renew the lease while ``run_slurm_compute`` /
``run_remote_compute`` polls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from cloudra.infra.compute_utils import check_job_type, launch_compute_processes
from cloudra.infra.slurm import run_slurm_compute
from cloudra.persistence.database import ComputeDB
from cloudra.runtime.remote_compute import REMOTE_KINDS, run_remote_compute
from cloudra.services.compute_store import (
    aextend_compute_lease,
    afail_compute_job,
    aget_compute_job,
    renew_compute_lease,
    reset_compute_attempt_count,
)

logger = logging.getLogger(__name__)

# After the guard is detached, keep the lease so expired-lease reclaim
# does not double-launch a job the guard already owns. The scheduler
# daemon's reconciler renews the lease while the guard lock is held, so
# this only needs to comfortably outlive one reconcile interval.
_LOCAL_LEASE_AFTER_SPAWN = 3600
_POLLER_LEASE_SECONDS = 60
_POLLER_RENEW_EVERY = 20.0


async def _mark_failed(db: ComputeDB, task_id: int, message: str) -> None:
    try:
        wrote = await afail_compute_job(db, task_id, message)
    except ValueError as exc:
        logger.warning("compute failure not recorded: %s", exc)
        return
    if not wrote:
        return
    logger.error("compute job %s failed: %s", task_id, message)
    try:
        # D5/D11：失败终态入 CallReview 收件箱（非 dag 模式内部跳过）
        from cloudra.dag.controller import enqueue_compute_review

        await enqueue_compute_review(task_id, "failed")
    except Exception:
        logger.exception("could not enqueue compute review for job %s", task_id)


async def _renew_lease(
    db: ComputeDB,
    task_id: int,
    worker_id: str,
    stop: asyncio.Event,
) -> None:
    """poller 型作业（Slurm/SSH 远端）的租约续约循环：认领进程即看守。"""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_POLLER_RENEW_EVERY)
            return
        except asyncio.TimeoutError:
            await asyncio.to_thread(
                renew_compute_lease,
                db,
                task_id=task_id,
                worker_id=worker_id,
                lease_seconds=_POLLER_LEASE_SECONDS,
            )


def _scheduler_payload(scheduler: str | None, raw_options: str | None) -> tuple[str, dict]:
    options: dict = {}
    if raw_options:
        try:
            parsed = json.loads(raw_options)
            if isinstance(parsed, dict):
                options = parsed
        except json.JSONDecodeError:
            options = {}
    kind = (scheduler or options.get("type") or "local").strip().lower() or "local"
    return kind, options


async def run_compute(
    task_id: int,
    db: ComputeDB | None = None,
    *,
    worker_id: str | None = None,
) -> int:
    """Execute an already-claimed compute job. Returns process-style exit code."""
    db = db or ComputeDB()
    row = await aget_compute_job(db, task_id)
    if row is None:
        logger.error("compute job %s not found in %s", task_id, db.path)
        return 1

    kind, options = _scheduler_payload(row["scheduler"], row["scheduler_options"])
    path = (row["path"] or "").strip()
    job_type = (row["jobtype"] or "").strip()
    conv_id = (row["conversation_id"] or "").strip() or "default"

    # 认领成功即清零重试计数：attempt_count 只累计"真失败"（没能拉起）；
    # 服务重启导致的重认领不应消耗预算（修复 Slurm 作业重启 3 次被误 reap）。
    if worker_id:
        await asyncio.to_thread(
            reset_compute_attempt_count, db, task_id, worker_id
        )

    if not path or not job_type:
        await _mark_failed(db, task_id, f"compute job {task_id} is missing path or job type")
        return 1

    if not row.get("scheduler_job_id"):
        from cloudra.services.ts_pipeline_store import verify_stage_input
        try:
            await asyncio.to_thread(verify_stage_input, db, task_id)
        except (OSError, ValueError) as exc:
            await _mark_failed(db, task_id, str(exc))
            return 1

    if kind == "slurm" or kind in REMOTE_KINDS:
        # poller 型作业（本机 Slurm / SSH 远端）：认领进程内轮询即看守，租约随 poll 续
        stop = asyncio.Event()
        renewer = None
        if worker_id:
            renewer = asyncio.create_task(
                _renew_lease(db, task_id, worker_id, stop),
                name=f"compute-lease-{task_id}",
            )
        try:
            if kind == "slurm":
                rc = await run_slurm_compute(task_id, db.path, scheduler=options)
            else:
                rc = await run_remote_compute(task_id, db.path)
            # 作业在 run_*_compute 内到达终态并落库；读回终态入
            # CallReview 收件箱（rev_compute_<id> 去重，非 dag 模式内部跳过）。
            try:
                settled = await aget_compute_job(db, task_id)
                if settled and settled["state"] in ("done", "failed"):
                    from cloudra.dag.controller import enqueue_compute_review

                    await enqueue_compute_review(task_id, settled["state"])
            except Exception:
                logger.exception("could not enqueue compute review for job %s", task_id)
            return rc
        except Exception as exc:
            # Submission may already have been accepted even when persisting
            # its handle failed. The existing reconciler recovers that handle;
            # an empty local receipt cannot establish remote process exit.
            logger.warning(
                "compute job %s: %s execution status unconfirmed; keeping ledger for reconciliation: %s",
                task_id, kind, exc,
            )
            return 1
        finally:
            stop.set()
            if renewer is not None:
                renewer.cancel()
                await asyncio.gather(renewer, return_exceptions=True)

    workdir = os.path.dirname(path) or "."
    ok, msg = check_job_type(job_type, workdir)
    if not ok:
        await _mark_failed(db, task_id, msg)
        return 1

    ok, msg = await launch_compute_processes(
        task_id=task_id,
        input_file=path,
        job_type=job_type,
        conv_id=conv_id,
        db_path=db.path,
        wait_for_calculator=False,
    )
    if not ok:
        await _mark_failed(db, task_id, msg)
        return 1
    await aextend_compute_lease(db, task_id, _LOCAL_LEASE_AFTER_SPAWN)
    return 0
