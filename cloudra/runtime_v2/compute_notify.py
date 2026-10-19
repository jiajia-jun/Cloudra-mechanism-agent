"""v2-native compute job notifications: 中央 compute.db 轮询 -> agent.message。

计算作业终态的唯一事实源是中央库 ``data_dir/compute.db`` 的 ``compute_jobs``
表（guard/Slurm 进程终态 CAS 落库）；本 broker 不走任何进程间事件总线，只做
纯 DB 轮询：每 tick 先按已加载项目 SELECT "终态且 notified_at IS NULL"
（不按结束时间截断，宕机窗口不丢），再扫一小批未加载行只为把已删除
项目的死信落 ``notified_at``。只投递 ``conversation_id in core.projects``
的行（未加载项目跳过、不落 notified_at；**已硬删除的项目**——事件日志里有 project.deleted tombstone——
永不加载，记 warning 并落 notified_at 终结）。同批按收件人合并持久化通知，
消息保留各作业编号，逐作业落 ``notified_at``；每位收件人只唤醒一次，不等待其他作业。
TS 流水线中间作业由系统自动推进；受阻、终态或 ts_guess 报告可疑虚频方向时
通知并唤醒所属 Agent。方向建议不阻止 IRC，也不自动取消计算。
投递失败不落 notified_at，下一 tick 自然重试。
首次看到已加载项目时，从既有运行文件找回管线编号，按编号读取权威进度；
已确认但未推进的终态作业按编号重新挂回既有通知队列，复用持久化失败重试，
不另起后台任务，不定期遍历文件或查询未结束管线清单。

锁纪律（细粒度，防跨进程 "database is locked"）：同步 SQLite 全部经
``asyncio.to_thread`` 卸载出事件循环，逐作业单行 UPDATE，不持长事务。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from cloudra.persistence.database import ComputeDB
from cloudra.runtime.compute_notify import resolve_submission_info
from cloudra.runtime_v2.dispatcher import WakePolicy, should_wake
from cloudra.services.compute_store import (
    mark_notified,
    pending_terminal_jobs,
)

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

logger = logging.getLogger(__name__)

# 兼容 pending_terminal_jobs 签名；查询本身不再按结束时间截断。
_BACKFILL_WINDOW_SECONDS = 0
# 每 tick 全局扫描的投递上限（小 SELECT 粒度上限）
_POLL_BATCH = 50


@dataclass
class _ComputeNotice:
    project_id: str
    task_id: int
    target_id: str
    content: str | None
    observation: str | None = None


class ComputeNotifyBroker:
    """轮询中央 compute_jobs 表，把终态作业投递为 ``agent.message``。"""

    def __init__(self, core: "RuntimeCore", *, poll_interval: float = 2.0) -> None:
        self.core = core
        self.poll_interval = poll_interval
        self._poll_task: asyncio.Task | None = None
        # Project delivery and the periodic loop can run at the same time. A
        # single scan/delivery owner prevents both from selecting an unacked
        # row and committing the same notice twice.
        self._poll_lock = asyncio.Lock()
        # 证据快照待收集：核心文件暂不可读时入此表，后续 tick 静默重试
        # （不重复投递通知）；收齐后一次性补发"证据已可复查"。
        # task_id -> (project_id, session_id, recovered)
        self._snapshot_retries: dict[int, tuple[str, str | None, bool]] = {}
        self._recovered_projects: set[str] = set()

    async def start(self) -> None:
        if self._poll_task is not None:
            return
        self._poll_task = asyncio.create_task(self._poll_loop(), name="compute-notify")

    async def close(self) -> None:
        task, self._poll_task = self._poll_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

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
        async with self._poll_lock:
            await self._poll_all_locked()

    async def _poll_all_locked(self) -> None:
        """每 tick 先扫已加载项目，再扫一小批未加载行只为终结已删除项目。

        已加载项目单独 SELECT，不被其它会话的未通知积压占满 LIMIT。
        未加载且未删除的行仍跳过、不落 notified_at。已被硬删除的项目（事件日志里有
        project.deleted tombstone）记 warning 并落 notified_at 终结。
        """
        loaded = list(self.core.projects)
        self._recovered_projects.intersection_update(loaded)

        if loaded:
            await self._poll_loaded_projects(loaded)

        parked = await asyncio.to_thread(self._pending_terminal_jobs)
        for conversation_id, task_id, _state, _session_id in parked:
            if conversation_id in loaded:
                continue
            if conversation_id in self.core.deleted_project_ids:
                logger.warning(
                    "compute job %s belongs to deleted project %s; marking notified "
                    "without delivery",
                    task_id,
                    conversation_id,
                )
                await asyncio.to_thread(self._mark_notified, task_id)
        await self._retry_snapshots()

    async def _poll_project(self, project_id: str) -> None:
        async with self._poll_lock:
            if project_id not in self.core.projects:
                return  # 项目未加载无投递目标
            await self._poll_loaded_projects([project_id])

    async def _poll_loaded_projects(self, project_ids: list[str]) -> None:
        from cloudra.persistence.paths import project_workspace_dir
        from cloudra.tools.core.ts_pipeline_driver import recover_project_jobs

        for project_id in project_ids:
            if project_id in self._recovered_projects:
                continue
            workspace = self.core.projects[project_id].workspace_dir or str(project_workspace_dir(project_id))
            await asyncio.to_thread(recover_project_jobs, ComputeDB(), project_id, workspace)
            self._recovered_projects.add(project_id)
        rows = await asyncio.to_thread(self._pending_terminal_jobs, conversation_ids=project_ids)
        await self._deliver_batch(rows)

    async def _deliver_batch(
        self, rows: list[tuple[str, int, str, str | None]]
    ) -> None:
        """Wake once per recipient with an acknowledged notice in this poll.

        Other active jobs or a terminal backlog cannot delay result handling.
        System-owned TS intermediate results stay silent. Persist one body per
        recipient, then acknowledge each job before waking that recipient.
        """
        notices: dict[str, list[_ComputeNotice]] = {}
        delivery_failed: set[tuple[str, str]] = set()
        for project_id, task_id, state, session_id in rows:
            key = (project_id, session_id) if session_id else None
            if key is not None and key in delivery_failed:
                continue
            try:
                notice = await self._prepare_notice(
                    project_id, task_id=task_id, state=state,
                    session_id=session_id,
                )
                if notice is not None:
                    notices.setdefault(notice.target_id, []).append(notice)
            except Exception:
                if key is not None:
                    # Retry the failed notice and later rows in order; any
                    # earlier acknowledged results remain available now.
                    delivery_failed.add(key)
                logger.exception(
                    "compute notify delivery failed for %s job %s", project_id, task_id
                )
        for target_id, group in notices.items():
            try:
                fresh = [notice for notice in group if notice.content is not None]
                if fresh:
                    await self._send_message(
                        target_id, "\n\n".join(notice.content for notice in fresh), wake=False,
                        job_ids=[notice.task_id for notice in fresh],
                    )
                    for notice in fresh:
                        if notice.observation is not None:
                            from cloudra.runtime_v2.supervision import notify_supervisor

                            try:
                                await notify_supervisor(
                                    self.core, notice.project_id,
                                    reason="Terminal TS observation recorded", observation=notice.observation,
                                )
                            except Exception:
                                logger.warning("Could not notify Supervisor about TS job %s",
                                               notice.task_id, exc_info=True)
                # One durable body identifies every job. If one ack fails, later
                # jobs remain pending and reuse this same receipt on retry.
                for notice in group:
                    await asyncio.to_thread(self._mark_notified, notice.task_id)
                await self._wake_notified_child(target_id)
            except Exception:
                logger.exception("compute batch delivery failed for %s", target_id)
        # A coordinator can already have consumed the child's first final
        # report and be parked waiting for later compute. Once all notices in
        # this batch are durable, let the runner test project quiescence.
        hook = getattr(self.core.runner, "maybe_wake_parked_delivery", None)
        if hook is not None:
            for project_id in {row[0] for row in rows}:
                await hook(project_id)

    @staticmethod
    def _pending_terminal_jobs(
        project_id: str | None = None,
        conversation_ids: list[str] | None = None,
    ) -> list[tuple[str, int, str, str | None]]:
        """终态且未通知的作业；读失败返回空，下轮再试。"""
        try:
            return pending_terminal_jobs(
                ComputeDB(),
                window_seconds=_BACKFILL_WINDOW_SECONDS,
                limit=_POLL_BATCH,
                conversation_id=project_id,
                conversation_ids=conversation_ids,
            )
        except Exception:
            return []

    async def _prepare_notice(
        self,
        project_id: str,
        *,
        task_id: int,
        state: str,
        session_id: str | None,
    ) -> _ComputeNotice | None:
        if project_id not in self.core.projects:
            return
        from cloudra.services.ts_pipeline_context import use_runtime_authority
        from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal
        with use_runtime_authority(self.core):
            pipeline = await asyncio.to_thread(handle_process_job_terminal, ComputeDB(), task_id)
        # 已持久化的通知继续走 ack/wake；重试时告警可能已随修订变成历史。
        target_id = await asyncio.to_thread(self._delivery_target, project_id, task_id)
        frequency = next((step.get('frequency_analysis') or {} for step in
                          (pipeline or {}).get('record', {}).get('job_steps', [])
                          if step.get('purpose') == 'frequency' and step.get('job_id') == task_id), {})
        alignment = frequency.get('mode_alignment') or {}
        if (pipeline is not None and pipeline['status'] in ('waiting', 'running')
                and target_id is None and alignment.get('status') not in {'misaligned', 'undecidable'}):
            await asyncio.to_thread(self._mark_notified, task_id)
            return
        observation = None
        content = None
        if target_id is None:
            view = None
            record = None
            if pipeline is not None:
                record = pipeline['record']

                from cloudra.tools.core.ts_state_view import recorded_notification_view
                view = await asyncio.to_thread(recorded_notification_view, ComputeDB(), record)
            content = await self._content_for(task_id, state, view=view, record=record)
            snapshot_note, complete = await self._snapshot_core_evidence(
                project_id, task_id, session_id
            )
            if snapshot_note:
                content = f"{content}\n{snapshot_note}"
            if not complete:
                self._snapshot_retries[task_id] = (project_id, session_id, False)

            if isinstance(session_id, str) and session_id in self.core.agents:
                target_id = session_id
            else:
                # A missing submitter falls back to the coordinator. Never
                # broadcast a child's calculation result to it otherwise.
                coordinator = self._coordinator_for(project_id)
                target_id = coordinator.id if coordinator is not None else None
            if target_id is None:
                return
            if view is not None:
                from cloudra.runtime_v2.policies.guidance import guide_ts_process

                guide_ts_process(self.core.notices, target_id, view)
            owner = self.core.agents.get(target_id)
            from cloudra.runtime_v2.schemas import OrchestrationMode

            if (view is not None and owner is not None
                    and owner.settings.orchestration_mode is OrchestrationMode.DAG_GUIDED
                    and view.get('status') in {'ended', 'blocked'}):
                observation = self._research_observation(view, content)
        return _ComputeNotice(project_id, task_id, target_id, content, observation)

    @staticmethod
    def _research_observation(view: dict, content: str) -> str:
        """One bounded recorded outcome, not a scientific review or a causal diagnosis."""
        verdict = view.get('result') or {}
        blocked = view.get('blocked') or {}
        lines = ["[Current TS observation — document maintenance]",
            f"TS {view['run_id']}: status={view.get('status')}; stage={view.get('stage')}; "
            f"outcome={verdict.get('outcome') or 'unverified'}; "
            f"workflow_verified={str(verdict.get('verified') is True).lower()}."]
        if blocked.get('failure_class'):
            lines.append(f"Recorded failure classification: {blocked['failure_class']}.")
        reason = verdict.get('reason') or blocked.get('message')
        if reason:
            lines.append('Recorded check: ' + str(reason)[:240])
        lines.extend(line for line in content.splitlines() if line.startswith('Evidence:'))
        lines.append('Merge this observation and its source paths into PROCESS.md. '
            'It is not a DAG review verdict or proof of a chemical cause.')
        return '\n'.join(lines)[:1800]

    def _delivery_target(self, project_id: str, task_id: int) -> str | None:
        if self.core.store is not None:
            return self.core.store.compute_delivery_target(project_id, task_id)
        # Memory-only embedders have no database; the resident event log is
        # their complete authority and does not need a second retained index.
        target = None
        for event in self.core.event_log.iter_project(project_id, types={"agent.message_injected"}):
            manifest = event.data.get("manifest")
            if (event.session_id and isinstance(manifest, dict)
                    and manifest.get("kind") == "compute_completion"
                    and (manifest.get("task_id") == task_id
                         or task_id in manifest.get("task_ids", []))):
                target = event.session_id
        return target

    async def _wake_notified_child(self, session_id: str) -> None:
        async with self.core.dispatcher.target_lock(session_id):
            agent = self.core.agents.get(session_id)
            inbox = self.core.mailbox.inbox(session_id)
            if (
                agent is not None
                and agent.role_id != "coordinator"
                and inbox is not None
                and not inbox.empty()
                and await asyncio.to_thread(should_wake, self.core, agent, WakePolicy.PARK_TERMINAL)
            ):
                await self.core.agent_host.wake(agent, runner=self.core.runner)

    async def _content_for(
        self, task_id: int, state: str, *, view: dict | None = None, record: dict | None = None,
    ) -> str:
        """Small recorded facts; complete TS diagnostics remain available through inspect."""
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
        log_path = await asyncio.to_thread(resolve_log_path, input_path,
            job_type=job_type, task_id=task_id) if input_path else ""
        lines = [f"Compute Event: Job {task_id}, state={state}."]
        evidence = []
        if log_path:
            evidence.append(f"Log: {log_path}")
        if input_path:
            evidence.append(f"Input: {Path(input_path).name}" if log_path else f"Input: {input_path}")
            if job_type == 'shell':
                evidence.append(f"Working directory: {Path(input_path).parent}")
        if view is not None:
            verdict = view.get('result') or {}
            blocked = view.get('blocked') or {}
            verified = verdict.get('verified') is True
            attempt = view.get('failed_attempt') or {}
            purpose = attempt.get('purpose', '') if attempt.get('job_id') == task_id else ''
            if not purpose and record:
                steps = [*record.get('job_steps', []), record.get('scan_step') or {}]
                purpose = next((step.get('purpose', '') for step in steps if step.get('job_id') == task_id), '')
            stage = ' / '.join(str(part) for part in [view.get('stage'), purpose] if part)
            lines[0] += f" TS {view['run_id']}: {stage}."
            window = self._reaction_window(record, view, purpose, job_type)
            if window:
                lines.append('Reaction Window: ' + window)
            reason = fail_reason or verdict.get('reason') or blocked.get('message') or view.get('message')
            observation = f"outcome={verdict['outcome']}; " if verdict.get('outcome') else ''
            observation += f"verified={str(verified).lower()}."
            if reason:
                observation += f" {reason}"
            lines.append('Physical Reality: ' + observation)
            inspect = f"ts_inspect(run_id={view['run_id']!r})"
            frequency = view.get('frequency_analysis') or {}
            alignment = frequency.get('mode_alignment') or {}
            if (frequency.get('job_id') == task_id
                    and alignment.get('status') in {'misaligned', 'undecidable'}):
                lines.append('Advisory from ts_guess: ' + str(alignment.get('message') or alignment['status']))
                next_action = (f'Use {inspect} to review the mode and current jobs. '
                    'This check is advisory and may be wrong; it does not block or cancel jobs. '
                    'Decide whether to keep the pipeline running or call ts_stop with a reason, '
                    'then revise the guess with ts_resume when appropriate.')
            elif verified:
                next_action = ('Submit the verified native logs through the DAG evidence tools.'
                    if view.get('details_path') else f'Use {inspect} for the verified evidence, then submit its native logs through the DAG evidence tools.')
            elif blocked.get('failure_class') == 'scan_no_candidate':
                next_action = (f"Use {inspect} to compare the native structures and logs. "
                    'Test alternative approach orientation or asynchronous bond changes with sequential scans; '
                    'consider tool-generated GSM/NEB guesses. These are hypotheses, not established causes; '
                    'record the observation and evidence paths in PROCESS.md before choosing the next test.')
            elif blocked.get('failure_class') == 'wrong_mode' or verdict.get('outcome') == 'candidate_only':
                next_action = (f"Use {inspect} to check the native mode/IRC endpoints and intended bond changes. "
                    'Distinguish numerical failure from a different reaction connection, then choose the next test.')
            elif view.get('status') == 'blocked':
                next_action = f"Use {inspect} for diagnostics, then revise the research input with ts_resume as needed."
            else:
                next_action = f"Inspect the observed chemistry and choose the next distinguishing test; use {inspect} for details."
            if view.get('details_path'):
                evidence.append(f"Details: {view['details_path']}")
        elif job_type == 'shell':
            if state == 'done':
                lines.append('Process: Shell script exited successfully.')
                next_action = 'Inspect the captured log and output files in the working directory.'
            else:
                if state != 'cancelled' and fail_reason:
                    lines.append(f"Process: {fail_reason}")
                next_action = f'Use query_compute_job(task_id={task_id}) and the captured log to diagnose the failure before retrying.'
        elif state == 'done':
            lines.append('Physical Reality: Calculation finished; scientific verification is not implied.')
            next_action = 'Use log_parser on the native log to inspect energy, convergence and frequencies.'
        else:
            if state != 'cancelled' and fail_reason:
                lines.append(f"Physical Reality: {fail_reason}")
            next_action = f'Use query_compute_job(task_id={task_id}) and the native log to diagnose the failure before retrying.'
        if state == 'cancelled':
            next_action = 'Do not resubmit or restart without a new explicit user request.'
        lines.append(f"NEXT: {next_action}")
        if evidence:
            lines.append('Evidence: ' + '; '.join(evidence))
        return '\n'.join(lines)

    @staticmethod
    def _reaction_window(record: dict | None, view: dict, purpose: str, engine: str) -> str:
        """Display existing current declarations, never infer connectivity from coordinates."""
        parts = []
        value = (record or {}).get('input', {}) if (record or {}).get('format_version') == 7 else {}
        reaction = value.get('reaction') or {}
        for role in ('reactant', 'product'):
            facts = []
            if reaction.get(f'{role}_smiles'):
                facts.append(reaction[f'{role}_smiles'])
            structure = view.get('structures', {}).get(role) or {}
            for field, label in (('atom_count', 'atoms'), ('components', 'components')):
                if isinstance(structure.get(field), int):
                    facts.append(f"{structure[field]} {label}")
            if facts:
                parts.append(f"{role}: " + ', '.join(facts))
        for field in ('charge', 'multiplicity'):
            if reaction.get(field) is not None:
                parts.append(f"{field}={reaction[field]}")
        centres = (record or {}).get('effective_reaction_center') or reaction.get('reaction_center')
        if centres and value:
            parts.append('centres (1-based): ' + ', '.join(f'{a + 1}-{b + 1}' for a, b in centres))
        guess = value.get('guess') or {}
        if purpose == 'scan' and guess.get('kind') == 'scan':
            calculation = guess.get('calculation') or {}
            if calculation.get('ref'):
                calculation = value.get('calculations', {}).get(calculation['ref']) or {}
            scan_engine = calculation.get('engine') or engine
            if scan_engine in ('orca', 'gaussian', 'xtb'):
                base = 0 if scan_engine == 'orca' else 1
                coordinates = []
                for scan in guess.get('scans', []):
                    atoms = ','.join(str(atom + base) for atom in scan['atoms'])
                    extent = (f"{scan['scan_start']}→" if scan.get('scan_start') is not None else 'end=') + str(scan['scan_end'])
                    units = 'Å' if scan['coord_type'] == 'bond' else 'degrees'
                    coordinates.append(f"{scan['coord_type']}({atoms}) {extent} {units}, scan_steps={scan['scan_steps']}")
                if coordinates:
                    parts.append(f"scan declaration ({scan_engine}, {base}-based): " + '; '.join(coordinates))
        return '; '.join(parts)

    @staticmethod
    def _mark_notified(task_id: int) -> None:
        """Acknowledge the durable notice in compute.db after inbox delivery."""
        try:
            mark_notified(ComputeDB(), task_id)
        except Exception:
            logger.exception("could not mark compute job %s notified", task_id)
            raise

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

            log_path = await asyncio.to_thread(resolve_log_path, input_path, job_type=job_type, task_id=task_id)
            if log_path and await asyncio.to_thread(Path(log_path).is_file):
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
            return "Evidence could not be recorded: no live session is available.", False
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
            lines.append("Native output is not available yet.")
        for path_str in files:
            path = Path(path_str)
            try:
                await asyncio.to_thread(
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
                lines.append(f"Evidence could not be recorded: {path.name} ({type(exc).__name__}).")
                continue
        return "; ".join(lines), complete

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
            target = session_id
            if target is None or target not in self.core.agents:
                coordinator = self._coordinator_for(project_id)
                target = coordinator.id if coordinator is not None else None
            if target is not None:
                await self._send_message(
                    target,
                    f"[Compute job] Evidence for job {task_id} is now available for review.\n{note}",
                    wake=True,
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

    async def _send_message(
        self, session_id: str, content: str, *, wake: bool = True,
        job_ids: list[int] | None = None,
    ) -> None:
        body = content if content.startswith("[Compute job]") else f"[Compute job]\n{content}"
        agent = self.core.agents.get(session_id)
        manifest = (
            {"kind": "compute_completion", "task_ids": job_ids}
            if job_ids is not None else None
        )
        if agent is not None and agent.role_id == "coordinator":
            # Coordinator 绝不被计算任务唤醒（只由 AgentHub / Supervisor 裁决唤醒）：
            # 终态通知仅静默存入收件箱驻留（park-don't-wake），不发 agent.message 强制 wake。
            await self.core.dispatcher.commit_and_deliver(
                to_session_id=session_id,
                project_id=agent.project_id,
                content=body,
                sender="system",
                manifest=manifest,
                wake=WakePolicy.NEVER,
            )
            return
        if agent is not None:
            await self.core.dispatcher.commit_and_deliver(
                to_session_id=session_id,
                project_id=agent.project_id,
                content=body,
                sender="system",
                manifest=manifest,
                wake=WakePolicy.PARK_TERMINAL if wake else WakePolicy.NEVER,
            )
