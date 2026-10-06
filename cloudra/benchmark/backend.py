"""runtime_v2-backed agent backend for the benchmark runner.

Per task this spins up an in-process runtime_v2 kernel (RuntimeCore +
TurnPipeline + AgentRunner), spawns the task's coordinator agent with the task
query against the per-task sandbox as the project workspace, and waits for the
task to genuinely finish (see ``watch.py`` for the wait_background /
wait_review state machine, GH #30). The task method policy is installed in project settings before agents start,
so the default policy chain and automatic TS submissions share its authority; compute jobs submitted via
`submit_compute_job` are claimed and executed by a per-task in-process
`SchedulerDaemon` (production runs it as a separate `cloudra scheduler`
process instead).

Process-wide isolation is the caller's job: the benchmark CLI points the
global config's `data_dir` at the benchmark data dir before any tool runs, so
session stores, compute jobs and MEMORY.md never touch the live conversation
data dir. LLM credentials still come from the normal global config slots
(coordinator/follower), unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any

from cloudra.benchmark.schema import TaskSpec
from cloudra.benchmark.watch import RunWatcher

logger = logging.getLogger(__name__)

class RuntimeV2Backend:
    """`AgentBackend` implementation: run each task on the real runtime_v2.

    `llm` / `tools` are injectable so tests can run the
    whole wiring hermetically; production defaults are the legacy bridges.
    """

    def __init__(
        self,
        *,
        stuck_grace_s: float = 300.0,
        poll_interval_s: float = 2.0,
        llm: Any = None,
        tools: Any = None,
        start_scheduler: bool = True,
        store_path: Any = None,
    ) -> None:
        self.stuck_grace_s = stuck_grace_s
        self.poll_interval_s = poll_interval_s
        self.llm = llm
        self.tools = tools
        self.start_scheduler = start_scheduler
        # 事件级持久化（可选但 CLI 默认开）：全战役共享一个 runtime-v2.db，
        # 只 append 不 restore——benchmark core 是一次性的，恢复语义无意义；
        # 崩溃后事件历史与 token 遥测（cloudra stats tokens）仍可查。
        self.store_path = Path(store_path) if store_path is not None else None
        # 每次任务的 RuntimeCore 按 task_id 留存，供测试与调试内省事件日志；
        # 并行跑题时多线程并发写，用锁保护。
        self._cores: dict[str, Any] = {}
        self._cores_lock = threading.Lock()

    @property
    def last_core(self) -> Any:
        """最近一次任务的 core（串行调试便利）；并行时用 core_by_task()。"""
        with self._cores_lock:
            return next(reversed(self._cores.values())) if self._cores else None

    def core_by_task(self, task_id: str) -> Any:
        with self._cores_lock:
            return self._cores.get(task_id)

    def __call__(self, task: TaskSpec, sandbox: Path) -> None:
        asyncio.run(self._run_task(task, Path(sandbox)))

    async def _run_task(self, task: TaskSpec, sandbox: Path) -> None:
        from cloudra.runtime_v2.adapters import (
            LegacyLLMProvider,
            LegacyPromptProvider,
            LegacyToolExecutor,
            legacy_default_runtime_settings,
        )
        from cloudra.runtime_v2.agent_runner import AgentRunner
        from cloudra.runtime_v2.commands import CommandBus
        from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
        from cloudra.runtime_v2.core import RuntimeCore
        from cloudra.runtime_v2.policies import default_stages
        from cloudra.runtime_v2.schemas import Command
        from cloudra.runtime_v2.turn_pipeline import TurnPipeline

        sandbox.mkdir(parents=True, exist_ok=True)
        sandbox = sandbox.resolve()

        core = RuntimeCore(strict_events=True)
        with self._cores_lock:
            self._cores[task.task_id] = core
        if self.store_path is not None:
            from cloudra.runtime_v2.persistence import RuntimeStore

            # 与 services/api_v2/app.py 同款接法；多题共享一个库文件，append
            # 经 to_thread 卸载，WAL + busy_timeout 由 RuntimeStore 自带。
            core.store = RuntimeStore(self.store_path)

            async def persist_event(envelope) -> None:
                # llm.chunk deltas 是瞬时 hub 事件：无回放价值，落库会灌爆事件表。
                if envelope.type == "llm.chunk":
                    return
                await asyncio.to_thread(core.store.append_event, envelope)

            core.event_hub.subscribe(persist_event)
        core.runtime_defaults = legacy_default_runtime_settings()
        stages = default_stages(core)
        executor = self.tools or LegacyToolExecutor(core)
        from cloudra.runtime_v2.invocation import InvocationService

        invocations = InvocationService(
            event_writer=core.event_writer, stages=stages, tools=executor, agents=core.agents
        )
        pipeline = TurnPipeline(
            event_log=core.event_log,
            stages=stages,
            llm=self.llm or LegacyLLMProvider(),
            tools=executor,
            prompt_provider=LegacyPromptProvider(),
            event_hub=core.event_hub,
            notices=core.notices,
            invocations=invocations,
        )
        core.runner = AgentRunner(core, pipeline)
        # CLI uses a private RuntimeCore, so the live Web service's notify
        # broker cannot see its sessions.  Start one here to deliver terminal
        # compute notices and wake parked child runs.
        broker = ComputeNotifyBroker(core, poll_interval=self.poll_interval_s)
        scheduler = None
        agent = None
        bus = CommandBus(core)
        try:
            await broker.start()
            if self.start_scheduler:
                from cloudra.scheduler.daemon import SchedulerDaemon

                # worker_id 含 pid+task_id：并行跑题时同进程多个实例不能共享
                # 默认的 scheduler:<pid>，否则租约归属互相串。
                scheduler = SchedulerDaemon(worker_id=f"scheduler:{os.getpid()}:{task.task_id}")
                await scheduler.start()
            project = (
                await bus.execute(
                    Command(
                        type="project.create",
                        payload={
                            "name": f"benchmark:{task.task_id}",
                            "workspace_dir": str(sandbox),
                            "settings": {"benchmark_task_id": task.task_id,
                                         "method_policy": task.method_policy.model_dump(mode="json")},
                        },
                    )
                )
            ).data
            agent = (
                await bus.execute(
                    Command(
                        type="agent.spawn",
                        target={"project_id": project.id},
                        payload={
                            "role_id": task.prompt.role,
                            "query": task.prompt.query,
                            "settings": {
                                "orchestration_mode": task.prompt.orchestration_mode.value,
                                # 无人值守：破坏性工具审批走 yolo 自动通道
                                "yolo": True,
                                # 无人值守（GH #31）：隐藏并 fail-closed 拦截
                                # ask_user，绝不允许挂进 waiting_input
                                "unattended": True,
                                # Each benchmark case is isolated from global
                                # cross-task memory and AGENTS injection.
                                "clean_context": True,
                            },
                        },
                    )
                )
                ).data
            await self._wait_terminal(bus, agent)
            # 评分只读交付物（图 + 日志）：后端不回传任何
            # 供评分使用的文本/数字，杜绝"拿模型自述给自己打分"。
        finally:
            await broker.close()
            if agent is not None and core.runner is not None:
                await core.runner.cancel(agent.id)
            # 契约性关机补快照：core 接了 store 时把会话上下文投影落盘。
            await bus.flush_snapshot()
            if scheduler is not None:
                await scheduler.close()

    async def _wait_terminal(self, bus, agent) -> None:
        """等题目真正结束（watch.RunWatcher 的 wait_background/wait_review
        语义，GH #30），无人回应的卡死状态才按宽限期取消该题。"""
        from cloudra.persistence.database import ComputeDB
        from cloudra.runtime_v2.schemas import AgentState, Command
        from cloudra.services.compute_store import (
            acount_active_compute_job_states,
            pending_terminal_jobs,
        )

        core = bus.core
        compute_db = ComputeDB()

        async def background_pending() -> bool:
            # compute.db 是计算作业的唯一权威；reminders 与子 agent 存活由
            # watcher 的 core 投影承担（子 agent 见 has_running_peers）。
            if bool(core.reminders.pending(agent.id)):
                return True
            if await acount_active_compute_job_states(compute_db, agent.project_id):
                return True
            return bool(
                await asyncio.to_thread(
                    pending_terminal_jobs, compute_db, window_seconds=0, limit=1,
                    conversation_id=agent.project_id,
                )
            )

        async def resume_background() -> None:
            # Compute notices for coordinators are deliberately parked by the
            # general broker.  This unattended benchmark watcher resumes its
            # coordinator once the notice reaches the inbox.
            if agent.state is AgentState.SUCCEEDED and core.runner is not None:
                await core.agent_host.wake(agent, runner=core.runner)

        watcher = RunWatcher(
            stuck_grace_s=self.stuck_grace_s,
            poll_interval_s=self.poll_interval_s,
            pending_background=background_pending,
            resume_background=resume_background,
        )

        async def cancel(reason: str) -> None:
            logger.warning("cancelling benchmark agent %s: %s", agent.id, reason)
            await bus.execute(
                Command(
                    type="agent.cancel",
                    target={"session_id": agent.id},
                    payload={"message": f"[benchmark] cancelled: {reason}"},
                )
            )

        wait_error = await watcher.wait(core, agent, cancel)
        if wait_error is not None:
            raise TimeoutError(wait_error)

    def _final_message(self, core, session_id: str) -> str:
        """agent 最后一条 message_emitted 的原文——**仅作诊断日志**，不参与评分。"""
        events = core.event_log.query_session(session_id)
        for envelope in reversed(events):
            if envelope.type == "agent.message_emitted":
                return str((envelope.data or {}).get("content") or "")
        return ""
