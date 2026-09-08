"""runtime_v2-backed agent backend for the benchmark runner.

Per task this spins up an in-process runtime_v2 kernel (RuntimeCore +
TurnPipeline + AgentRunner), spawns the task's coordinator agent with the task
query against the per-task sandbox as the project workspace, waits for a
terminal state, then returns the agent's final message plus the barrier
extracted from it (the final message is the input to refusal classification —
see `refusal.py`). The method whitelist is enforced by appending
`MethodPolicyStage` to the pipeline; compute jobs submitted via
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
import re
import threading
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from cloudra.benchmark.policy_stage import MethodPolicyStage
from cloudra.benchmark.runner import BackendResult
from cloudra.benchmark.schema import TaskSpec
from cloudra.runtime_v2.schemas import AgentState

logger = logging.getLogger(__name__)

TERMINAL_STATES = frozenset({AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED})

# waiting_input / waiting_approval 不是终态：benchmark 无人值守，挂起超过
# stuck_grace 就取消该题（yolo 已开，正常路径不该出现审批等待）。
_STUCK_STATE_VALUES = frozenset({AgentState.WAITING_INPUT.value, AgentState.WAITING_APPROVAL.value})

# 最终总结里的能垒抓取：优先匹配明确指认的决速步（RDS / rate-determining step）
# 能垒；未明确标明时取文本中最后一个 "<number> kcal/mol" 出现（总结陈述通常在最末）。
_RDS_BARRIER_RE = re.compile(
    r"(?:rds|rate[- ]determining(?:[- ]step)?)\s*(?:barrier|energy|enthalpy)?\s*(?:is|of|:|=)?\s*(-?\d+(?:\.\d+)?)\s*kcal\s*/?\s*mol",
    re.IGNORECASE,
)
_BARRIER_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*kcal\s*/?\s*mol", re.IGNORECASE)


def extract_reported_barrier(text: str) -> Optional[float]:
    """Last "<number> kcal/mol" in the agent's final summary, or None."""
    if not text:
        return None
    rds_match = _RDS_BARRIER_RE.search(text)
    if rds_match:
        return float(rds_match.group(1))
    matches = _BARRIER_RE.findall(text)
    return float(matches[-1]) if matches else None


class RuntimeV2Backend:
    """`AgentBackend` implementation: run each task on the real runtime_v2.

    `llm` / `tools` / `run_summarizer` are injectable so tests can run the
    whole wiring hermetically; production defaults are the legacy bridges.
    """

    def __init__(
        self,
        *,
        run_timeout_s: float = 7200.0,
        stuck_grace_s: float = 300.0,
        poll_interval_s: float = 2.0,
        llm: Any = None,
        tools: Any = None,
        run_summarizer: Optional[Callable[[list[dict]], Awaitable[str]]] = None,
        start_scheduler: bool = True,
    ) -> None:
        self.run_timeout_s = run_timeout_s
        self.stuck_grace_s = stuck_grace_s
        self.poll_interval_s = poll_interval_s
        self.llm = llm
        self.tools = tools
        self.run_summarizer = run_summarizer
        self.start_scheduler = start_scheduler
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

    def __call__(self, task: TaskSpec, sandbox: Path) -> BackendResult:
        return asyncio.run(self._run_task(task, Path(sandbox)))

    async def _run_task(self, task: TaskSpec, sandbox: Path) -> BackendResult:
        from cloudra.runtime_v2.adapters import (
            LegacyLLMProvider,
            LegacyPromptProvider,
            LegacyToolExecutor,
            legacy_default_runtime_settings,
        )
        from cloudra.runtime_v2.agent_runner import AgentRunner
        from cloudra.runtime_v2.commands import CommandBus
        from cloudra.runtime_v2.core import RuntimeCore
        from cloudra.runtime_v2.policies import default_stages
        from cloudra.runtime_v2.schemas import Command
        from cloudra.runtime_v2.turn_pipeline import TurnPipeline

        sandbox.mkdir(parents=True, exist_ok=True)
        sandbox = sandbox.resolve()

        core = RuntimeCore(strict_events=True)
        with self._cores_lock:
            self._cores[task.task_id] = core
        core.runtime_defaults = legacy_default_runtime_settings()
        stage = MethodPolicyStage(task.method_policy, base_dir=sandbox)
        stages = [*default_stages(core), stage]
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
        core.runner = AgentRunner(core, pipeline, run_summarizer=self.run_summarizer)
        scheduler = None
        if self.start_scheduler:
            from cloudra.scheduler.daemon import SchedulerDaemon

            # worker_id 含 pid+task_id：并行跑题时同进程多个实例不能共享
            # 默认的 scheduler:<pid>，否则租约归属互相串。
            scheduler = SchedulerDaemon(worker_id=f"scheduler:{os.getpid()}:{task.task_id}")
            await scheduler.start()

        agent = None
        bus = CommandBus(core)
        try:
            project = (
                await bus.execute(
                    Command(
                        type="project.create",
                        payload={"name": f"benchmark:{task.task_id}", "workspace_dir": str(sandbox)},
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
                                # Each benchmark case is isolated from global
                                # cross-task memory and AGENTS injection.
                                "clean_context": True,
                            },
                        },
                    )
                )
                ).data
            await self._wait_terminal(bus, agent)
            message = self._final_message(core, agent.id)
            barrier = extract_reported_barrier(message)
            if message and barrier is None:
                logger.warning("agent %s final message reports no barrier", agent.id)
            return BackendResult(barrier=barrier, final_message=message)
        finally:
            if agent is not None and core.runner is not None:
                await core.runner.cancel(agent.id)
            # benchmark core 默认无 store（不落盘），这里是契约性的关机补快照：
            # 将来接入持久化时无需再改。
            await bus.flush_snapshot()
            if scheduler is not None:
                await scheduler.close()

    async def _wait_terminal(self, bus, agent) -> None:
        from cloudra.runtime_v2.schemas import Command

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.run_timeout_s
        stuck_since: float | None = None
        while agent.state not in TERMINAL_STATES:
            now = loop.time()
            reason = ""
            if now > deadline:
                reason = f"benchmark run timeout ({self.run_timeout_s}s)"
            elif agent.state.value in _STUCK_STATE_VALUES:
                stuck_since = stuck_since if stuck_since is not None else now
                if now - stuck_since > self.stuck_grace_s:
                    reason = f"agent stuck in {agent.state.value} with nobody to answer"
            else:
                stuck_since = None
            if reason:
                logger.warning("cancelling benchmark agent %s: %s", agent.id, reason)
                await bus.execute(
                    Command(
                        type="agent.cancel",
                        target={"session_id": agent.id},
                        payload={"message": f"[benchmark] cancelled: {reason}"},
                    )
                )
                break
            await asyncio.sleep(self.poll_interval_s)

    def _final_message(self, core, session_id: str) -> str:
        """agent 最后一条 message_emitted 的原文（无则空串）。

        拒答分类与能垒抓取共用这一条消息：拒答声明通常就是收尾陈述。"""
        events = core.event_log.query_session(session_id)
        for envelope in reversed(events):
            if envelope.type == "agent.message_emitted":
                return str((envelope.data or {}).get("content") or "")
        return ""
