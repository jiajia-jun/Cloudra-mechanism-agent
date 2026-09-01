"""v2-native compute job notifications: 中央 compute.db 轮询 -> agent.message。

计算作业终态的唯一事实源是中央库 ``data_dir/compute.db`` 的 ``compute_jobs``
表（guard/Slurm 进程终态 CAS 落库）；本 broker 不走任何进程间事件总线，只做
纯 DB 轮询：每 tick 一条带 LIMIT 的小 SELECT 扫"终态且 notified_at IS NULL"
的作业（限 7 天窗口防历史刷屏），只投递 ``conversation_id in core.projects``
的行（未加载项目跳过、不落 notified_at，项目打开时 ``ensure_project`` 立即
扫该项目），逐作业投递 ``agent.message`` 后落 ``notified_at``。投递失败不落
notified_at，下一 tick 自然重试。

锁纪律（细粒度，防跨进程 "database is locked"）：同步 SQLite 全部经
``asyncio.to_thread`` 卸载出事件循环，逐作业单行 UPDATE，不持长事务。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from cloudra.persistence.database import ComputeDB
from cloudra.runtime.compute_notify import build_compute_finish_content, resolve_submission_info
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.schemas import Command
from cloudra.services.compute_store import mark_notified, pending_terminal_jobs

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

logger = logging.getLogger(__name__)

# 补投窗口：只认最近 7 天内结束的作业，防升级后历史作业刷屏
_BACKFILL_WINDOW_SECONDS = 7 * 24 * 3600
# 每 tick 全局扫描的投递上限（小 SELECT 粒度上限）
_POLL_BATCH = 50


class ComputeNotifyBroker:
    """轮询中央 compute_jobs 表，把终态作业投递为 ``agent.message``。"""

    def __init__(self, core: "RuntimeCore", *, poll_interval: float = 2.0) -> None:
        self.core = core
        self.poll_interval = poll_interval
        self._poll_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._poll_task is not None:
            return
        self._poll_task = asyncio.create_task(self._poll_loop(), name="compute-notify")

    async def close(self) -> None:
        task, self._poll_task = self._poll_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def ensure_project(self, project_id: str) -> None:
        """项目打开时立即扫一次该项目，不等下个 tick。"""
        await self._poll_project(project_id)

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("compute notify poll failed")
            await asyncio.sleep(self.poll_interval)

    async def _poll_all(self) -> None:
        """每 tick 一条全局扫描；未加载项目的行跳过（不落 notified_at）。"""
        rows = await asyncio.to_thread(self._pending_terminal_jobs)
        for conversation_id, task_id, state, session_id in rows:
            if conversation_id not in self.core.projects:
                continue  # 项目未加载无投递目标
            try:
                await self._deliver(
                    conversation_id, task_id=task_id, state=state, session_id=session_id
                )
            except Exception:
                logger.exception(
                    "compute notify delivery failed for %s job %s", conversation_id, task_id
                )

    async def _poll_project(self, project_id: str) -> None:
        if project_id not in self.core.projects:
            return  # 项目未加载无投递目标
        rows = await asyncio.to_thread(self._pending_terminal_jobs, project_id)
        for _conv_id, task_id, state, session_id in rows:
            try:
                await self._deliver(
                    project_id, task_id=task_id, state=state, session_id=session_id
                )
            except Exception:
                logger.exception(
                    "compute notify delivery failed for %s job %s", project_id, task_id
                )

    @staticmethod
    def _pending_terminal_jobs(
        project_id: str | None = None,
    ) -> list[tuple[str, int, str, str | None]]:
        """终态且未通知的作业（限 7 天窗口）；读失败返回空，下轮再试。"""
        try:
            return pending_terminal_jobs(
                ComputeDB(),
                window_seconds=_BACKFILL_WINDOW_SECONDS,
                limit=_POLL_BATCH,
                conversation_id=project_id,
            )
        except Exception:
            return []

    async def _deliver(
        self,
        project_id: str,
        *,
        task_id: int,
        state: str,
        session_id: str | None,
    ) -> None:
        if project_id not in self.core.projects:
            return
        content = await self._content_for(task_id, state)

        delivered: set[str] = set()
        if isinstance(session_id, str) and session_id in self.core.agents:
            await self._send_message(session_id, content)
            delivered.add(session_id)

        coordinator = self._coordinator_for(project_id)
        if coordinator is not None and coordinator.id not in delivered:
            await self._send_message(coordinator.id, content)

        await asyncio.to_thread(self._mark_notified, task_id)

    async def _content_for(self, task_id: int, state: str) -> str:
        """通知文本一律由 DB 重建（唯一路径）：提交者信息 + 终态错误 + 日志路径。"""
        from cloudra.infra.compute_utils import get_log_path
        from cloudra.services.compute_store import aget_compute_job

        db = ComputeDB()
        info = await resolve_submission_info(db, task_id)
        fail_reason = ""
        job_type = "gaussian"
        try:
            row = await aget_compute_job(db, task_id)
            if row:
                info["path"] = row["path"] or info.get("path") or ""
                fail_reason = row["last_error"] or ""
                job_type = row["jobtype"] or job_type
        except Exception:
            pass
        input_path = str(info.get("path") or "")
        return build_compute_finish_content(
            task_id=task_id,
            state=state,
            input_path=input_path,
            # 纯字符串推导，不碰文件系统
            log_path=get_log_path(input_path, job_type=job_type) if input_path else "",
            fail_reason=fail_reason,
        )

    @staticmethod
    def _mark_notified(task_id: int) -> None:
        """投递完成后落 notified_at——去重只认它（notified_at IS NULL 过滤）。"""
        try:
            mark_notified(ComputeDB(), task_id)
        except Exception:
            logger.exception("could not mark compute job %s notified", task_id)

    def _coordinator_for(self, project_id: str):
        return next(
            (
                agent
                for agent in self.core.list_project_agents(project_id)
                if agent.role_id == "coordinator"
            ),
            None,
        )

    async def _send_message(self, session_id: str, content: str) -> None:
        body = content if content.startswith("[Compute job]") else f"[Compute job]\n{content}"
        await CommandBus(self.core).execute(
            Command(
                type="agent.message",
                target={"session_id": session_id},
                payload={"content": body},
                actor="system",
            )
        )
