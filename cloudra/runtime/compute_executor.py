"""Claim ready compute_jobs and launch the calculator guard (or Slurm).

v1 deleted the worker that called ``claim_ready_compute_job``, so async
``submit_compute_job`` rows sat in ``ready`` forever.  ``ComputeBroker`` is
that worker: FastAPI lifespan starts it; it scans conversation DBs, claims
with a lease, then runs ``run_compute``.

Local jobs spawn the detached guard and extend the lease so a later poll
does not start a second calculator.  Slurm jobs stay in this process and
renew the lease while ``run_slurm_compute`` polls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time

from cloudra.infra.compute_utils import check_job_type, launch_compute_processes
from cloudra.infra.slurm import run_slurm_compute
from cloudra.persistence import paths
from cloudra.persistence.database import ConversationDB
from cloudra.services.session_store import claim_ready_compute_job, renew_task_lease

logger = logging.getLogger("cloudra.compute_executor")

# After the guard is detached, keep the lease so expired-lease reclaim
# does not double-launch a job the guard already owns.
_LOCAL_LEASE_AFTER_SPAWN = 14 * 24 * 3600
_SLURM_LEASE_SECONDS = 60
_SLURM_RENEW_EVERY = 20.0
_REAP_INTERVAL = 30.0


def _iter_conversation_dbs() -> list[tuple[str, str]]:
    root = paths.conversations_dir()
    if not root.is_dir():
        return []
    found: list[tuple[str, str]] = []
    for child in root.iterdir():
        db_path = child / "tasks" / "database.db"
        if db_path.is_file():
            found.append((child.name, str(db_path)))
    return found


async def _mark_failed(db: ConversationDB, task_id: int, message: str) -> None:
    logger.error("compute job %s failed: %s", task_id, message)
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET state=?, end_timestamp=?, last_error=? WHERE id=?",
            ("failed", time.time(), message[:500], task_id),
        )
        await con.commit()
    try:
        # D5/D11：失败终态入 CallReview 收件箱（非 dag 模式内部跳过）
        from cloudra.dag.controller import enqueue_compute_review

        await enqueue_compute_review(db, task_id, "failed")
    except Exception:
        logger.exception("could not enqueue compute review for job %s", task_id)


async def _extend_lease(db: ConversationDB, task_id: int, seconds: int) -> None:
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET lease_expires_at=? WHERE id=? AND state='running'",
            (time.time() + max(10, int(seconds)), task_id),
        )
        await con.commit()


async def _renew_slurm_lease(
    db: ConversationDB,
    task_id: int,
    worker_id: str,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_SLURM_RENEW_EVERY)
            return
        except asyncio.TimeoutError:
            await asyncio.to_thread(
                renew_task_lease,
                db,
                table="compute_jobs",
                task_id=task_id,
                worker_id=worker_id,
                lease_seconds=_SLURM_LEASE_SECONDS,
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
    db_path: str,
    *,
    worker_id: str | None = None,
) -> int:
    """Execute an already-claimed compute job. Returns process-style exit code."""
    db = ConversationDB.from_path(db_path)
    async with db.aconnect() as con:
        cur = await con.execute(
            """SELECT conversation_id, path, jobtype, scheduler, scheduler_options
            FROM compute_jobs WHERE id=?""",
            (task_id,),
        )
        row = await cur.fetchone()
    if row is None:
        logger.error("compute job %s not found in %s", task_id, db_path)
        return 1

    conv_id, raw_path, job_type, scheduler, raw_options = row
    kind, options = _scheduler_payload(scheduler, raw_options)
    path = (raw_path or "").strip()
    job_type = (job_type or "").strip()
    conv_id = (conv_id or "").strip() or "default"

    if not path or not job_type:
        await _mark_failed(db, task_id, f"compute job {task_id} is missing path or job type")
        return 1

    if kind == "slurm":
        stop = asyncio.Event()
        renewer = None
        if worker_id:
            renewer = asyncio.create_task(
                _renew_slurm_lease(db, task_id, worker_id, stop),
                name=f"compute-lease-{task_id}",
            )
        try:
            rc = await run_slurm_compute(task_id, db_path, scheduler=options)
            # Slurm 作业在 run_slurm_compute 内到达终态并落库；读回终态入
            # CallReview 收件箱（rev_compute_<id> 去重，非 dag 模式内部跳过）。
            try:
                async with db.aconnect() as con:
                    cur = await con.execute(
                        "SELECT state FROM compute_jobs WHERE id=?", (task_id,)
                    )
                    row = await cur.fetchone()
                if row and row[0] in ("done", "failed"):
                    from cloudra.dag.controller import enqueue_compute_review

                    await enqueue_compute_review(db, task_id, row[0])
            except Exception:
                logger.exception("could not enqueue compute review for job %s", task_id)
            return rc
        except Exception as exc:
            await _mark_failed(db, task_id, f"Slurm compute failed: {exc}")
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
        db_path=db_path,
        wait_for_calculator=False,
    )
    if not ok:
        await _mark_failed(db, task_id, msg)
        return 1
    await _extend_lease(db, task_id, _LOCAL_LEASE_AFTER_SPAWN)
    return 0


class ComputeBroker:
    """Background loop: claim ready compute_jobs and run them."""

    def __init__(self, *, poll_interval: float = 1.0, worker_id: str | None = None) -> None:
        self.poll_interval = poll_interval
        self.worker_id = worker_id or f"compute:{os.getpid()}"
        self._stop = asyncio.Event()
        self._loop_task: asyncio.Task | None = None
        self._jobs: dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._stop.clear()
        self._loop_task = asyncio.create_task(self._loop(), name="compute-broker")

    async def close(self) -> None:
        self._stop.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
            self._loop_task = None
        jobs = list(self._jobs.values())
        for task in jobs:
            task.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        self._jobs.clear()

    def _claim_one(self) -> tuple[int, str] | None:
        for _conv_id, db_path in _iter_conversation_dbs():
            try:
                db = ConversationDB.from_path(db_path)
                job_id = claim_ready_compute_job(db, worker_id=self.worker_id)
            except Exception:
                logger.exception("claim failed for %s", db_path)
                continue
            if job_id is not None:
                return job_id, db_path
        return None

    async def _loop(self) -> None:
        last_reap = 0.0
        while not self._stop.is_set():
            claimed = await asyncio.to_thread(self._claim_one)
            if claimed is None:
                now = time.time()
                if now - last_reap >= _REAP_INTERVAL:
                    last_reap = now
                    await asyncio.to_thread(self._reap_orphans)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    continue
                return
            task_id, db_path = claimed
            job = asyncio.create_task(
                self._run(task_id, db_path),
                name=f"compute-job-{task_id}",
            )
            self._jobs[task_id] = job
            job.add_done_callback(lambda _t, key=task_id: self._jobs.pop(key, None))

    @staticmethod
    def _reap_orphans() -> None:
        """把已耗尽重试预算且租约过期的 running 作业置为 failed。

        覆盖"executor 反复崩溃、最后一次租约过期后无人认领"的孤儿；
        租约未到期或还有重试预算的作业不动（正常重试/等待路径照旧）。
        """
        from cloudra.services.session_store import reap_exhausted_leases

        for _conv_id, db_path in _iter_conversation_dbs():
            try:
                reap_exhausted_leases(ConversationDB.from_path(db_path))
            except Exception:
                logger.exception("reap failed for %s", db_path)

    async def _run(self, task_id: int, db_path: str) -> None:
        try:
            await run_compute(task_id, db_path, worker_id=self.worker_id)
        except Exception:
            logger.exception("compute job %s crashed", task_id)
            try:
                await _mark_failed(
                    ConversationDB.from_path(db_path),
                    task_id,
                    "compute executor crashed before the job reached a terminal state",
                )
            except Exception:
                logger.exception("could not mark compute job %s failed", task_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a claimed compute job")
    parser.add_argument("--task_id", type=int, required=True)
    parser.add_argument("--db_path", type=str, required=True)
    args = parser.parse_args(argv)
    return asyncio.run(run_compute(args.task_id, args.db_path))


if __name__ == "__main__":
    sys.exit(main())
