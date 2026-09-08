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
        # 证据快照待收集：核心文件暂不可读时入此表，后续 tick 静默重试
        # （不重复投递通知）；收齐后一次性补发"证据已可复查"。
        # task_id -> (project_id, session_id, recovered)
        self._snapshot_retries: dict[int, tuple[str, str | None, bool]] = {}

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
        await self._retry_snapshots()

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
        snapshot_note, complete = await self._snapshot_core_evidence(
            project_id, task_id, session_id
        )
        if snapshot_note:
            content = f"{content}\n{snapshot_note}"
        if not complete:
            self._snapshot_retries[task_id] = (project_id, session_id, False)

        delivered: set[str] = set()
        if isinstance(session_id, str) and session_id in self.core.agents:
            await self._send_message(session_id, content)
            delivered.add(session_id)
        elif not delivered:
            # 仅当提交会话未指定或不可达（ghost session 回落）时才交付 Coordinator 兜底，
            # 绝不把子 Agent 负责的底层计算作业无脑广播给 Coordinator。
            coordinator = self._coordinator_for(project_id)
            if coordinator is not None:
                await self._send_message(coordinator.id, content)

        await asyncio.to_thread(self._mark_notified, task_id)

    async def _content_for(self, task_id: int, state: str) -> str:
        """通知文本一律由 DB 重建（唯一路径）：提交者信息 + 终态错误 + 日志路径。"""
        from cloudra.infra.compute_utils import resolve_log_path
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
        library_hits = await self._library_hits(state, job_type, fail_reason, input_path)
        return build_compute_finish_content(
            task_id=task_id,
            state=state,
            input_path=input_path,
            # log_path 与 query_compute_job 统一走 resolve_log_path（GH #20）：
            # 优先 guard state json 记录的真实日志，回退引擎惯例预测
            log_path=resolve_log_path(input_path, job_type=job_type, task_id=task_id) if input_path else "",
            fail_reason=fail_reason,
            library_hits=library_hits,
        )

    async def _library_hits(
        self,
        state: str,
        job_type: str,
        fail_reason: str,
        input_path: str,
    ) -> list[dict]:
        """Auto-retrieve the chem-kb library for a terminal state.

        Retrieval is best-effort: a broken provider / uninstalled plugin
        yields no hits and the notification is delivered unchanged.
        """
        from cloudra.runtime.compute_notify import build_compute_knowledge_query
        from cloudra.runtime_v2.knowledge import search_library

        query = build_compute_knowledge_query(
            state=state, job_type=job_type, fail_reason=fail_reason, input_path=input_path
        )
        try:
            return await search_library(query, limit=3)
        except Exception:
            logger.exception("compute notify knowledge retrieval failed for %s", state)
            return []

    @staticmethod
    def _mark_notified(task_id: int) -> None:
        """投递完成后落 notified_at——去重只认它（notified_at IS NULL 过滤）。"""
        try:
            mark_notified(ComputeDB(), task_id)
        except Exception:
            logger.exception("could not mark compute job %s notified", task_id)

    async def _core_files_for(self, task_id: int) -> tuple[list[str], str]:
        """作业的核心证据文件与未落盘日志。

        返回 (files, missing_log)：输入文件总是入快照候选；日志按 GH #20
        同口径解析，但只有真实存在的才入候选——引擎惯例预测的日志可能
        从不落盘（如本机 ORCA stdout 构建），那不是"暂不可读"，标
        log_not_collected 但不进入重试循环。"""
        from cloudra.infra.compute_utils import resolve_log_path
        from cloudra.services.compute_store import aget_compute_job

        input_path = ""
        job_type = "gaussian"
        try:
            row = await aget_compute_job(ComputeDB(), task_id)
            if row:
                input_path = row["path"] or ""
                job_type = row["jobtype"] or job_type
        except Exception:
            return [], ""
        files = [input_path] if input_path else []
        missing_log = ""
        if input_path:
            from pathlib import Path

            log_path = resolve_log_path(input_path, job_type=job_type, task_id=task_id)
            if log_path and Path(log_path).is_file():
                if log_path not in files:
                    files.append(log_path)
            elif log_path:
                missing_log = log_path
        return files, missing_log

    async def _snapshot_core_evidence(
        self,
        project_id: str,
        task_id: int,
        session_id: str | None,
    ) -> tuple[str, bool]:
        """终态通知前登记核心文件的不可变 ArtifactService 快照。

        返回 (note, complete)：可读的登记/复用快照（同一文件重复收集按
        hash 复用，同名覆盖的新内容是新 attempt 绝不合并）；不可读源
        显式标 evidence_unavailable（complete=False，进入静默重试，
        不吞异常假装可复查）。
        """
        from pathlib import Path

        from cloudra.persistence.artifacts import ArtifactService
        from cloudra.persistence.database import ConversationDB
        from cloudra.services import session_store

        files, missing_log = await self._core_files_for(task_id)
        if not files and not missing_log:
            return "", True
        owner_session = session_id
        if not owner_session:
            coordinator = self._coordinator_for(project_id)
            owner_session = coordinator.id if coordinator is not None else None
        if not owner_session:
            return "[Evidence snapshot] evidence_unavailable: no live session to own artifacts", False
        # ArtifactService 要求 legacy session 行存在；runtime_v2 agent 不一定有，
        # 与 turn_pipeline 同一助手 get-or-create。
        await asyncio.to_thread(
            session_store.ensure_session_record,
            ConversationDB(project_id),
            owner_session,
            owner_session,
        )

        service = ArtifactService()
        lines: list[str] = []
        complete = True
        if missing_log:
            lines.append(f"log_not_collected: {missing_log}")
        for path_str in files:
            path = Path(path_str)
            try:
                artifact, created = await asyncio.to_thread(
                    service.snapshot_file,
                    conversation_id=project_id,
                    session_id=owner_session,
                    source=path,
                    allowed_root=path.parent,
                )
            except Exception as exc:
                complete = False
                logger.warning(
                    "compute evidence snapshot failed for job %s file %s: %s",
                    task_id, path_str, exc,
                )
                lines.append(f"evidence_unavailable: {path_str} ({type(exc).__name__})")
                continue
            tag = "registered" if created else "reused"
            lines.append(
                f"{artifact.artifact_id} {artifact.name} "
                f"(sha256:{artifact.sha256[:12]}…, {tag})"
            )
        header = "[Evidence snapshot]"
        return f"{header} " + "; ".join(lines), complete

    async def _retry_snapshots(self) -> None:
        """静默重试暂不可读的快照收集；收齐后一次性补发可复查通知。"""
        for task_id, (project_id, session_id, recovered) in list(self._snapshot_retries.items()):
            if recovered or project_id not in self.core.projects:
                continue
            try:
                note, complete = await self._snapshot_core_evidence(
                    project_id, task_id, session_id
                )
            except Exception:
                logger.exception("compute evidence snapshot retry failed for job %s", task_id)
                continue
            if not complete:
                continue
            self._snapshot_retries[task_id] = (project_id, session_id, True)
            target = session_id
            if target is None or target not in self.core.agents:
                coordinator = self._coordinator_for(project_id)
                target = coordinator.id if coordinator is not None else None
            if target is not None:
                await self._send_message(
                    target,
                    f"[Compute job] Evidence for job {task_id} is now available for review.\n{note}",
                )
            del self._snapshot_retries[task_id]

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
        agent = self.core.agents.get(session_id)
        if agent is not None and agent.role_id == "coordinator":
            # Coordinator 绝不被计算任务唤醒（只由 AgentHub / Supervisor 裁决唤醒）：
            # 终态通知仅静默存入收件箱驻留（park-don't-wake），不发 agent.message 强制 wake。
            self.core.mailbox.deliver(
                to_session_id=session_id,
                project_id=agent.project_id,
                content=body,
                sender="system",
            )
            return
        await CommandBus(self.core).execute(
            Command(
                type="agent.message",
                target={"session_id": session_id},
                payload={"content": body},
                actor="system",
            )
        )
