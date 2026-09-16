"""Web-hosted benchmark batch controller (GH #32 Phase 1).

A batch of benchmark tasks runs inside the live RuntimeCore — the same core
the API serves. Each task becomes a real project named ``benchmark:{task_id}``
whose coordinator works in a sandbox under the benchmark data dir, so the
existing project UI (timeline, DagPanel, compute monitor) is the per-task
drill-down view for free and the frontend sidebar can group the tasks by the
``benchmark:`` name prefix.

Differences from the CLI backend (``backend.RuntimeV2Backend``):

- No in-process scheduler: submitted compute jobs are claimed by the regular
  ``cloudra scheduler`` daemon, exactly like live research work.
- The method whitelist rides the project settings
  (``ProjectSettings.method_policy``), enforced by the live pipeline's
  ``MethodPolicyStage(core=core)`` — no extra stage is appended.
- The same ``watch.RunWatcher`` state machine decides when a task has
  genuinely finished (wait_background / wait_review semantics, GH #30);
  unattended spawn settings keep ask_user blocked (GH #31).
- Scoring reuses ``BenchmarkRunner.score_sandbox``; results land in the same
  ``benchmark.db`` schema as the CLI runner, tagged with ``batch_id``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

from cloudra.benchmark.refusal import RunOutcome, refusal_stats, should_refuse
from cloudra.benchmark.runner import (
    BenchmarkDB,
    BenchmarkRunner,
    RunResult,
    load_tasks,
    provenance_config,
)
from cloudra.benchmark.schema import TaskSpec, Tier
from cloudra.benchmark.watch import RunWatcher
from cloudra.runtime_v2.schemas import AgentState, Command, CommandRejected, new_id

logger = logging.getLogger(__name__)

# 批次事件流的环形缓冲上限（SSE 断线重连只重放快照，事件缓冲仅服务在线订阅者）。
_EVENT_BUFFER_MAX = 500

_AGENT_TERMINAL = frozenset(
    {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}
)


def repo_root() -> Path:
    """仓库根（ideapool 题集与 cloudra 包同仓）。"""
    import cloudra

    return Path(cloudra.__file__).resolve().parents[1]


TASK_TIERS: tuple[str, ...] = tuple(t.value for t in Tier)
"""内置题集档位（= schema.Tier 的枚举值，目录 ideapool/tasks/<tier>）。"""


def builtin_tier_dir(tier: str) -> Path:
    return repo_root() / "ideapool" / "tasks" / tier


def task_catalog() -> list[dict]:
    """内置档位清单（选题器的事实源）：档位、目录、题目 id。目录缺失时计 0 题，
    由 resolve_tasks_dirs 在启动时拒绝。"""
    out: list[dict] = []
    for tier in TASK_TIERS:
        d = builtin_tier_dir(tier)
        ids = [t.task_id for t in load_tasks(d)] if d.is_dir() else []
        out.append({
            "tier": tier,
            "path": str(d),
            "task_count": len(ids),
            "task_ids": ids,
        })
    return out


def resolve_tasks_dirs(dirs: list[str] | None,
                       tiers: list[str] | None = None) -> list[Path]:
    """题集目录解析：内置档位目录在前（按 TASK_TIERS 顺序）、自定义目录在后，
    重复目录只取一次；两者都缺省时回落到仓库内置 easy 档。自定义目录的绝对
    路径原样，相对路径先按进程 cwd、再按仓库根尝试。"""
    out: list[Path] = []
    unknown = sorted(set(tiers or []) - set(TASK_TIERS))
    if unknown:
        raise CommandRejected(
            "invalid_request", f"unknown tier: {', '.join(unknown)}"
        )
    for tier in TASK_TIERS:
        if tier not in (tiers or []):
            continue
        d = builtin_tier_dir(tier)
        if not d.is_dir():
            raise CommandRejected("invalid_request", f"tier tasks dir not found: {d}")
        out.append(d)
    for raw in dirs or []:
        p = Path(raw)
        candidates = [p] if p.is_absolute() else [Path.cwd() / p, repo_root() / p]
        resolved = next((c for c in candidates if c.is_dir()), None)
        if resolved is None:
            raise CommandRejected("invalid_request", f"tasks dir not found: {raw}")
        if resolved not in out:
            out.append(resolved)
    if not out:
        return [builtin_tier_dir("easy")]
    return out


class _TaskRunState:
    """一题在批次内的运行状态（易失；落库由 benchmark.db 承担）。"""

    def __init__(self, task: TaskSpec) -> None:
        self.task = task
        self.status = "queued"  # queued|running|scored|cancelled|error
        self.project_id = ""
        self.agent_id = ""
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.result: Optional[RunResult] = None
        self.error: str = ""


class BenchmarkBatch:
    """一批题的异步执行器。同一时间一个服务只持有一个活动批次。"""

    def __init__(
        self,
        core,
        bus,
        *,
        data_dir: Path,
        tasks: list[TaskSpec],
        tasks_dirs: list[str],
        concurrency: int,
        run_timeout_s: float,
        stuck_grace_s: float,
        poll_interval_s: float,
        emit: Callable[[str, dict], None],
    ) -> None:
        self.core = core
        self.bus = bus
        self.data_dir = Path(data_dir)
        self.sandboxes = self.data_dir / "sandboxes"
        self.concurrency = max(1, concurrency)
        self.emit = emit
        self.batch_id = new_id("batch")
        self.status = "idle"  # idle|running|stopping|done|error
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.config = {
            **provenance_config("web", tasks),
            "tasks_dirs": [str(d) for d in tasks_dirs],
            "task_ids": [t.task_id for t in tasks],
            "concurrency": self.concurrency,
            "run_timeout_s": run_timeout_s,
        }
        self.task_states = [_TaskRunState(t) for t in tasks]
        self._watcher_kwargs = {
            "run_timeout_s": run_timeout_s,
            "stuck_grace_s": stuck_grace_s,
            "poll_interval_s": poll_interval_s,
        }
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        # 评分复用 CLI 同一套管线（不跑 backend、不写库——record 由批次自己来）。
        # BenchmarkRunner 构造含同步 sqlite/mkdir：事件循环上禁止，start() 里
        # 经 to_thread 构造。
        self._runner: Optional[BenchmarkRunner] = None

    # ------------------------------------------------------------------ 生命周期

    async def start(self) -> None:
        """启动批次主循环（后台 task），立即返回。"""
        if self._task is not None:
            raise CommandRejected("state_conflict", "batch already started")
        self.status = "running"
        self.started_at = time.time()
        self._runner = await asyncio.to_thread(BenchmarkRunner, self.data_dir)
        await asyncio.to_thread(
            self._runner.db.record_batch, self.batch_id, "running", self.config
        )
        self.emit(
            "benchmark.batch_started",
            {"batch_id": self.batch_id, "task_count": len(self.task_states)},
        )
        self._task = asyncio.create_task(self._run(), name=f"benchmark-batch-{self.batch_id}")

    async def stop(self) -> None:
        """优雅终止：级联取消每个题目的 Agent（取消语义契约），不触碰
        scheduler/guard/QM 计算。批次主循环随后把剩余题落 cancelled。"""
        if self.status in {"idle", "done", "error"}:
            return
        self.status = "stopping"
        self._stop.set()
        for st in self.task_states:
            if not st.project_id:
                continue
            # 快照迭代：cancel 经 CommandBus 回写 core 时可能并发落新 agent
            for agent in list(self.core.agents.values()):
                if agent.project_id != st.project_id or agent.state in _AGENT_TERMINAL:
                    continue
                try:
                    await self.bus.execute(
                        Command(
                            type="agent.cancel",
                            target={"session_id": agent.id},
                            payload={"message": "[benchmark] batch stopped"},
                        )
                    )
                except CommandRejected:
                    continue

    async def shutdown(self, timeout_s: float = 5.0) -> None:
        """stop + 有界等待批次主循环收敛（API 关停用）。"""
        await self.stop()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=timeout_s)
            except asyncio.TimeoutError:
                logger.warning("batch %s did not finish within shutdown grace", self.batch_id)

    # ------------------------------------------------------------------ 主循环

    async def _run(self) -> None:
        try:
            sem = asyncio.Semaphore(self.concurrency)

            async def one(st: _TaskRunState) -> None:
                async with sem:
                    await self._run_one(st)

            await asyncio.gather(*(one(st) for st in self.task_states))
        except Exception:
            logger.exception("batch %s crashed", self.batch_id)
            self.status = "error"
        finally:
            # stopping 是 stop() 主动置的：收尾后落 stopped 而不是伪装 done。
            self.status = "stopped" if self.status == "stopping" else "done"
            self.finished_at = time.time()
            await asyncio.to_thread(
                self._runner.db.finish_batch, self.batch_id, self.status
            )
            self.emit(
                "benchmark.batch_finished",
                {"batch_id": self.batch_id, "status": self.status},
            )

    async def _run_one(self, st: _TaskRunState) -> None:
        task = st.task
        sandbox = self._sandbox_for(task.task_id)
        if self._stop.is_set():
            # 排队中被停：不 spawn、不评分，照常落 cancelled 行保证历史完整。
            await self._mark_cancelled(st)
            return
        try:
            live = await asyncio.to_thread(self._live_compute_in, sandbox)
            if live:
                # 该目录下还有未终态的作业在跑（理论上新批目录不会有，防呆）：
                # 绝不复用、绝不 kill 旧计算（执行面铁律）。
                await self._mark_infra_failure(
                    st,
                    f"sandbox {sandbox} still has live compute job(s) {live}; "
                    "refusing to reuse the directory (old compute is never killed)",
                )
                return
            await asyncio.to_thread(self._prepare_sandbox, sandbox)
        except OSError as exc:
            # 沙箱创建失败属基建故障：不在旧目录继续 spawn/评分。
            await self._mark_infra_failure(
                st,
                f"sandbox preparation failed for {task.task_id}: {exc}; "
                "refusing to run without a clean directory",
            )
            return

        st.status = "running"
        st.started_at = time.time()
        self.emit(
            "benchmark.task_started",
            {
                "batch_id": self.batch_id,
                "task_id": task.task_id,
                "tier": task.tier.value,
                "family": task.family,
                "name": task.name,
            },
        )
        try:
            project = (
                await self.bus.execute(
                    Command(
                        type="project.create",
                        payload={
                            "name": f"benchmark:{task.task_id}",
                            "workspace_dir": str(sandbox),
                            "settings": {
                                "orchestration_mode": task.prompt.orchestration_mode.value,
                                "method_policy": task.method_policy.model_dump(),
                            },
                        },
                    )
                )
            ).data
            st.project_id = project.id
            agent = (
                await self.bus.execute(
                    Command(
                        type="agent.spawn",
                        target={"project_id": project.id},
                        payload={
                            "role_id": task.prompt.role,
                            "query": task.prompt.query,
                            "settings": {
                                "orchestration_mode": task.prompt.orchestration_mode.value,
                                # 无人值守：审批走 yolo、ask_user 隐藏并
                                # fail-closed 拦截（GH #31）
                                "yolo": True,
                                "unattended": True,
                                "clean_context": True,
                            },
                        },
                    )
                )
            ).data
            st.agent_id = agent.id
            watcher = RunWatcher(
                pending_background=self._pending_background_factory(project.id, agent.id),
                **self._watcher_kwargs,
            )

            async def cancel(reason: str) -> None:
                logger.warning("cancelling benchmark agent %s: %s", agent.id, reason)
                await self.bus.execute(
                    Command(
                        type="agent.cancel",
                        target={"session_id": agent.id},
                        payload={"message": f"[benchmark] cancelled: {reason}"},
                    )
                )

            await watcher.wait(self.core, agent, cancel)

            # stop 只截断未竟工作：正常跑完（SUCCEEDED）的题照常评分，
            # 被 stop 级联取消的题落 cancelled。
            final = self.core.agents.get(agent.id)
            if self._stop.is_set() and (
                final is None or final.state is not AgentState.SUCCEEDED
            ):
                await self._mark_cancelled(st)
                return

            # 评分只读交付物：图 JSON + 日志 + 结构化拒答声明（不读最终消息）
            result = await asyncio.to_thread(
                self._runner.score_sandbox,
                task,
                sandbox,
            )
            result.batch_id = self.batch_id
            st.result = result
            st.status = "scored"
            await asyncio.to_thread(self._runner.db.record, result)
            self.emit(
                "benchmark.task_scored",
                {
                    "batch_id": self.batch_id,
                    "task_id": task.task_id,
                    "final_score": result.final_score,
                    "graph_score": result.graph_score,
                    "integrity_passed": result.integrity_passed,
                    "selfconsistency_passed": result.selfconsistency_passed,
                    "accuracy_score": result.accuracy_score,
                    "outcome": result.outcome,
                },
            )
        except Exception as exc:
            logger.exception("benchmark task %s crashed", task.task_id)
            st.status = "error"
            st.error = str(exc)
            self.emit(
                "benchmark.task_error",
                {"batch_id": self.batch_id, "task_id": task.task_id, "error": str(exc)},
            )
        finally:
            st.finished_at = time.time()

    # ------------------------------------------------------------------ helpers

    def _sandbox_for(self, task_id: str) -> Path:
        """本题在本批次下的沙箱：按批分目录，上一批交付物永久保留。"""
        return self.sandboxes / task_id / self.batch_id

    def _pending_background_factory(self, project_id: str, session_id: str):
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.compute_store import acount_pending_compute_jobs

        compute_db = ComputeDB()

        async def pending_background() -> bool:
            if bool(self.core.reminders.pending(session_id)):
                return True
            return bool(await acount_pending_compute_jobs(compute_db, project_id))

        return pending_background

    def _prepare_sandbox(self, sandbox: Path) -> None:
        # 沙箱按批分目录：本批目录天然干净，只建不删——上一批的交付物永久保留
        # （benchmark 数据珍贵，清理永由用户显式执行）。
        sandbox.mkdir(parents=True, exist_ok=True)

    def _live_compute_in(self, sandbox: Path) -> list[int]:
        """该沙箱目录下是否还有未终态的计算作业（中央 compute.db 是唯一权威）。

        读失败按"无占用"处理（下轮清理失败仍会落基建失败），绝不因诊断读
        失败阻断批次；只读，不改状态。
        """
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.compute_store import list_compute_jobs

        try:
            rows = list_compute_jobs(ComputeDB(), states=("ready", "running"))
        except Exception:
            return []
        root = str(Path(sandbox).resolve())
        return [
            int(row["id"])
            for row in rows
            if str(row.get("path") or "").startswith(root + os.sep)
        ]

    async def _mark_infra_failure(self, st: _TaskRunState, message: str) -> None:
        """基建失败终态：不 spawn、不评分，落一行带原因的失败记录并广播。"""
        st.status = "error"
        st.error = message
        result = RunResult(
            task_id=st.task.task_id,
            sandbox=str(self._sandbox_for(st.task.task_id)),
            outcome=RunOutcome.FAILED.value,
            batch_id=self.batch_id,
        )
        result.notes.append(f"infrastructure failure: {message}")
        st.result = result
        await asyncio.to_thread(self._runner.db.record, result)
        logger.warning("benchmark task %s failed before start: %s", st.task.task_id, message)
        self.emit(
            "benchmark.task_error",
            {"batch_id": self.batch_id, "task_id": st.task.task_id, "error": message},
        )

    def _cancelled_result(self, task: TaskSpec, sandbox: Path) -> RunResult:
        result = RunResult(
            task_id=task.task_id,
            sandbox=str(sandbox),
            outcome=RunOutcome.FAILED.value,
            batch_id=self.batch_id,
        )
        result.notes.append("cancelled by batch stop")
        return result

    async def _mark_cancelled(self, st: _TaskRunState) -> None:
        st.status = "cancelled"
        result = self._cancelled_result(st.task, self._sandbox_for(st.task.task_id))
        st.result = result
        await asyncio.to_thread(self._runner.db.record, result)
        self.emit(
            "benchmark.task_cancelled",
            {"batch_id": self.batch_id, "task_id": st.task.task_id},
        )

    def _final_message(self, session_id: str) -> str:
        events = self.core.event_log.query_session(session_id)
        for envelope in reversed(events):
            if envelope.type == "agent.message_emitted":
                return str((envelope.data or {}).get("content") or "")
        return ""

    # ------------------------------------------------------------------ 快照

    def snapshot(self) -> dict:
        tasks = []
        for st in self.task_states:
            r = st.result
            tasks.append({
                "task_id": st.task.task_id,
                "tier": st.task.tier.value,
                "family": st.task.family,
                "name": st.task.name,
                "status": st.status,
                "project_id": st.project_id,
                "agent_id": st.agent_id,
                "started_at": st.started_at,
                "finished_at": st.finished_at,
                "error": st.error,
                "final_score": r.final_score if r is not None else None,
                "graph_score": r.graph_score if r is not None else None,
                "integrity_passed": r.integrity_passed if r is not None else None,
                "selfconsistency_passed": r.selfconsistency_passed if r is not None else None,
                "accuracy_score": r.accuracy_score if r is not None else None,
                "outcome": r.outcome if r is not None else None,
                "notes": r.notes if r is not None else [],
            })
        stats = self._refusal_stats()
        return {
            "batch_id": self.batch_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "config": self.config,
            "tasks": tasks,
            "refusal": stats,
        }

    def _refusal_stats(self) -> dict:
        pairs = [
            (should_refuse(st.task), st.status == "scored" and st.result is not None
             and st.result.outcome == RunOutcome.REFUSED.value)
            for st in self.task_states
        ]
        stats = refusal_stats(pairs)
        return {
            "tp": stats.tp,
            "fp": stats.fp,
            "fn": stats.fn,
            "tn": stats.tn,
            "precision": stats.precision,
            "recall": stats.recall,
            "f1": stats.f1,
        }


class BenchmarkService:
    """API 侧的批次单例：启动/停止/状态/历史 + SSE 事件馈送。"""

    def __init__(self, core, bus, *, data_dir: Optional[Path] = None) -> None:
        self.core = core
        self.bus = bus
        self._data_dir_override = data_dir
        self._batch: Optional[BenchmarkBatch] = None
        self._lock = asyncio.Lock()
        self._events: deque[dict] = deque(maxlen=_EVENT_BUFFER_MAX)
        self._subscribers: set[asyncio.Queue] = set()

    # ------------------------------------------------------------------ 数据目录

    def _data_dir(self) -> Path:
        if self._data_dir_override is not None:
            return Path(self._data_dir_override)
        from cloudra.persistence.paths import data_dir

        return data_dir()

    # ------------------------------------------------------------------ 控制面

    def _active_batch(self) -> Optional[BenchmarkBatch]:
        batch = self._batch
        if batch is not None and batch.status in {"running", "stopping"}:
            return batch
        return None

    async def catalog(self) -> dict:
        """内置档位清单：前端选题器据此列出可选档位与题目数，不必手打路径。"""
        return {"tiers": await asyncio.to_thread(task_catalog)}

    async def start(self, *, tasks_dirs: list[str] | None, only: str,
                    concurrency: int, timeout: float,
                    tiers: list[str] | None = None) -> dict:
        async with self._lock:
            active = self._active_batch()
            if active is not None:
                raise CommandRejected(
                    "state_conflict",
                    f"batch {active.batch_id} is already {active.status}",
                )
            resolved = resolve_tasks_dirs(tasks_dirs, tiers)
            tasks = self._load_tasks_from(resolved, only)
            if not tasks:
                raise CommandRejected("invalid_request", "no benchmark tasks matched")
            batch = BenchmarkBatch(
                self.core,
                self.bus,
                data_dir=self._data_dir(),
                tasks=tasks,
                tasks_dirs=[str(d) for d in resolved],
                concurrency=concurrency,
                run_timeout_s=timeout,
                stuck_grace_s=300.0,
                poll_interval_s=2.0,
                emit=self._emit,
            )
            await batch.start()
            self._batch = batch
            return batch.snapshot()

    async def stop(self) -> dict:
        async with self._lock:
            batch = self._active_batch()
            if batch is None:
                raise CommandRejected("state_conflict", "no active benchmark batch")
            await batch.stop()
            return batch.snapshot()

    def status(self) -> dict:
        batch = self._batch
        if batch is None:
            return {
                "batch_id": None,
                "status": "idle",
                "started_at": None,
                "finished_at": None,
                "config": {},
                "tasks": [],
                "refusal": {},
            }
        return batch.snapshot()

    async def history(self) -> dict:
        db = await asyncio.to_thread(
            BenchmarkDB, self._data_dir() / "benchmark.db"
        )
        batches = await asyncio.to_thread(db.list_batches)
        for batch in batches:
            batch["runs"] = await asyncio.to_thread(db.list_runs_for, batch["batch_id"])
        return {"batches": batches}

    async def shutdown(self) -> None:
        async with self._lock:
            batch = self._batch
            if batch is not None and batch.status in {"running", "stopping"}:
                await batch.shutdown()

    # ------------------------------------------------------------------ 题集加载

    def _load_tasks_from(self, dirs: list[Path], only: str) -> list[TaskSpec]:
        wanted = {t.strip() for t in (only or "").split(",") if t.strip()}
        tasks: list[TaskSpec] = []
        for d in dirs:
            tasks.extend(load_tasks(d))
        if wanted:
            tasks = [t for t in tasks if t.task_id in wanted]
        return tasks

    # ------------------------------------------------------------------ 事件馈送

    def _emit(self, event_type: str, data: dict) -> None:
        event = {"type": event_type, "data": data}
        self._events.append(event)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)
