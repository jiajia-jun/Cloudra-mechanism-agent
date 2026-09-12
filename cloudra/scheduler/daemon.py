"""计算调度守护进程：与 API 进程彻底分家的排队 / 容量记账 / 崩溃对账器。

设计约定（详见 AGENTS.md）：

- **中央 compute.db 是唯一事实源**：守护进程与 API 之间不加任何新 IPC；
  认领用原子租约 UPDATE，状态同步靠各自重启后的对账收敛。compute_jobs
  已迁出会话库，认领/对账每 tick 只打这一份库。
- **执行面可靠性 = OS 级**：进程存活判定一律 flock 探测
  （`infra/flocks.py`），不读 PID、不解析 ps//proc 文本。
- **永不 kill 计算进程**：guard 死 → adopt guard 等 calc 锁释放后收尾；
  calc 活 → 等它跑完。取消只有用户/agent 显式 cancel_requested 一条路。
- 单实例：`data_dir/scheduler.lock` 排他 flock，抢不到即退出。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from cloudra.infra.compute_utils import (
    build_guard_cmd,
    guard_lock_path,
    guard_log_path,
    spawn_detached,
)
from cloudra.infra.flocks import is_lock_held, try_acquire_lock
from cloudra.persistence import paths
from cloudra.persistence.database import ComputeDB
from cloudra.runtime.compute_executor import _mark_failed, run_compute
from cloudra.services.compute_store import (
    claim_ready_compute_job_with_capacity,
    extend_compute_lease,
    list_running_jobs,
    reap_exhausted_compute_leases,
)

logger = logging.getLogger(__name__)

_RECONCILE_INTERVAL = 30.0
# 对账发现 guard 存活时把租约续到这个长度，防止租约过期被重复认领
_LEASE_RENEW_AFTER_CHECK = 3600
# adopt guard 刚拉起时的占位租约（它自持 guard 锁，下轮对账即转为保活续租）
_LEASE_AFTER_ADOPT_SPAWN = 300
# 同一作业的 adopt guard 重拉起最小间隔：adopt guard 崩溃（还没抢到 guard 锁
# 就退出）时每轮对账都会重拉起，落 ``<guard锁>.adopt_last_spawn`` 时间戳节流。
_ADOPT_RESPAWN_SECONDS = 60.0


def scheduler_lock_path() -> str:
    return str(paths.data_dir() / "scheduler.lock")


def _adopt_last_spawn_path(lock_path: str) -> str:
    return lock_path + ".adopt_last_spawn"


def _adopt_spawn_throttled(lock_path: str) -> bool:
    """距上次 adopt guard 拉起 < _ADOPT_RESPAWN_SECONDS。时间戳缺失/损坏视为可拉起。"""
    try:
        last = float(Path(_adopt_last_spawn_path(lock_path)).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return time.time() - last < _ADOPT_RESPAWN_SECONDS


def _record_adopt_spawn(lock_path: str) -> None:
    from cloudra.persistence.fs_utils import atomic_write_text

    atomic_write_text(_adopt_last_spawn_path(lock_path), f"{time.time():.3f}")


def _node_capacity() -> dict:
    """节点容量（本地单节点假设；注册表缺失/损坏时用保守兜底值）。"""
    try:
        from cloudra.services.nodes import NodeRegistry

        return dict(NodeRegistry.from_environment().node(None).resources)
    except Exception:
        from cloudra.services.nodes import default_resources

        return default_resources()


class SchedulerDaemon:
    """调度主循环：容量感知认领 + 定期对账。"""

    def __init__(
        self,
        *,
        poll_interval: float = 1.0,
        reconcile_interval: float = _RECONCILE_INTERVAL,
        worker_id: str | None = None,
    ) -> None:
        self.poll_interval = poll_interval
        self.reconcile_interval = reconcile_interval
        self.worker_id = worker_id or f"scheduler:{os.getpid()}"
        # 中央计算库（data_dir/compute.db），认领/对账只打这一份
        self.db = ComputeDB()
        self._stop = asyncio.Event()
        self._loop_task: asyncio.Task | None = None
        self._jobs: dict[int, asyncio.Task] = {}

    # ---- 生命周期 ----

    async def start(self) -> None:
        """进程内托管模式（benchmark）：主循环 detach 成后台 task。

        生产部署不走这里——调度守护是独立进程（`cloudra scheduler`），
        这里只为每题一个进程内 RuntimeCore 的 benchmark 后端服务。
        """
        if self._loop_task is not None:
            return
        self._stop.clear()
        self._loop_task = asyncio.create_task(self.serve(), name="compute-scheduler")

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

    async def serve(self) -> None:
        """建库（幂等）→ 启动即对账一次 → 进入认领主循环。

        每 tick 自检显式全停 marker（`cloudra stop` 写入 daemons.stop）：
        置位即干净退出（flock 随进程释放）。只停调度本身——在跑的
        guard/calculator 计算进程按铁律跑到终态，绝不连带 kill。
        """
        from cloudra.services.daemon_supervisor import daemons_shutdown_requested

        await asyncio.to_thread(self.db.init)
        await self._reconcile_all()
        last_reconcile = time.time()
        while not self._stop.is_set():
            if daemons_shutdown_requested():
                logger.info("daemons shutdown requested (stop marker); scheduler exiting")
                return
            claimed = await asyncio.to_thread(self._claim_one)
            if claimed is None:
                now = time.time()
                if now - last_reconcile >= self.reconcile_interval:
                    last_reconcile = now
                    await self._reconcile_all()
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    continue
                break
            job = asyncio.create_task(
                self._run(claimed), name=f"compute-job-{claimed}"
            )
            self._jobs[claimed] = job
            job.add_done_callback(lambda _t, key=claimed: self._jobs.pop(key, None))

    def stop(self) -> None:
        self._stop.set()

    # ---- 认领（容量感知） ----

    def _claim_one(self) -> int | None:
        """每 tick 对中央库做一次容量感知认领；认到返回 job id。"""
        try:
            return claim_ready_compute_job_with_capacity(
                self.db, worker_id=self.worker_id, capacity=_node_capacity()
            )
        except Exception:
            logger.exception("claim failed")
            return None

    async def _run(self, task_id: int) -> None:
        try:
            await run_compute(task_id, self.db, worker_id=self.worker_id)
        except Exception:
            logger.exception("compute job %s crashed", task_id)
            try:
                await _mark_failed(
                    self.db,
                    task_id,
                    "compute scheduler crashed before the job reached a terminal state",
                )
            except Exception:
                logger.exception("could not mark compute job %s failed", task_id)

    # ---- 对账（只探锁、只写 DB，永不 kill、不读 PID） ----

    async def _reconcile_all(self) -> None:
        try:
            await asyncio.to_thread(self._reconcile_central)
        except Exception:
            logger.exception("reconcile failed")
        try:
            await asyncio.to_thread(reap_exhausted_compute_leases, self.db)
        except Exception:
            logger.exception("reap failed")

    def _reconcile_central(self) -> None:
        """对中央库跑一次对账：running 的 local 作业逐条探 guard 锁。"""
        for row in list_running_jobs(self.db):
            task_id = int(row["id"])
            if (row["scheduler"] or "local") != "local":
                continue  # Slurm：租约重领路径已覆盖，sacct 是外部权威
            path = row["path"] or ""
            workdir = os.path.dirname(path)
            if not workdir:
                continue
            lock_path = guard_lock_path(workdir, task_id)
            if is_lock_held(lock_path):
                # guard 活着：续租防重领（租约只剩认领语义，存活以锁为准）
                extend_compute_lease(self.db, task_id, _LEASE_RENEW_AFTER_CHECK)
                continue
            if _adopt_spawn_throttled(lock_path):
                continue  # 60s 内已拉起过 adopt guard，等下轮对账（防崩溃循环轰炸）
            # guard 已死：spawn adopt guard 接管。calc 还在跑它会阻塞等锁；
            # calc 已结束它直接解析收尾；无日志则置 failed。conv_id 从行里取。
            logger.warning(
                "compute job %s: guard lock free, spawning adopt guard", task_id
            )
            try:
                spawn_detached(
                    build_guard_cmd(
                        task_id,
                        path,
                        row["conversation_id"] or "default",
                        self.db.path,
                        job_type=row["jobtype"] or "gaussian",
                        adopt=True,
                    ),
                    guard_log_path(workdir, task_id),
                )
                _record_adopt_spawn(lock_path)
                extend_compute_lease(self.db, task_id, _LEASE_AFTER_ADOPT_SPAWN)
            except Exception:
                logger.exception("could not spawn adopt guard for job %s", task_id)


def main() -> int:
    """CLI 入口：抢单实例锁后跑主循环（前台，SIGINT 退出）。"""
    from cloudra.infra.logging_setup import setup_logging

    # detach 场景 stderr 已被 spawn_detached 重定向进 scheduler.log；
    # 用 stream 而非 log_file，避免与重定向双写同一文件。
    setup_logging("cloudra", stream=sys.stderr)
    lock = scheduler_lock_path()
    fd = try_acquire_lock(lock)
    if fd is None:
        print(
            f"Another cloudra scheduler is already running (lock: {lock}); exiting."
        )
        return 1
    daemon = SchedulerDaemon()
    logger.info("compute scheduler started (worker_id=%s)", daemon.worker_id)
    try:
        asyncio.run(daemon.serve())
    except KeyboardInterrupt:
        logger.info("compute scheduler stopped by SIGINT")
    finally:
        os.close(fd)
    return 0
