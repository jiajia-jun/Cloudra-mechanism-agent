"""AgentRunner: one async task per running AgentSession.

The runner owns the loop around TurnPipeline.  Commands only mutate state or
deliver inbox messages; execution concurrency lives here.

统一运行结束门禁（Task 4A，计划 2026-09-05-event-driven-supervisor §6）：
显式 stop 与无 tool_calls 的纯文本最终回复都在 runner 收尾前经
``_evaluate_completion_gate`` 到达同一个判定边界；四态 continue_work /
wait_background / wait_review / allow_final 的处置（反馈下一轮 / 挂起等唤醒 /
挂起等裁决 / 落终态）只在这里发生，门禁不阻止结束时绝不 finish_run(succeeded)。

上下文模型（Task 4，计划 2026-09-13-harness-cache-continuity）：LLM 上下文
是 **session 级事件溯源投影**（core.session_contexts，经 context.
prefix_installed/appended/compacted 由 apply_event 重建），跨 run、跨重启
连续；run 只是执行生命周期，不再各自重建对话。每个 run 创建自己的
ContextPrefix owner，但 owner 状态从会话投影回灌（restored），跨 run 不重装
前缀。发送 LLM 请求前，本轮输入（前缀增量/inbox/通知）经
ContextBroker.commit_input 落事件并持久化；响应后 assistant/tool 消息经
append_output 落事件——恰好一次。compact 的候选上下文经
ContextBroker.install_compacted 一条事件原子安装。

易失状态（3e）：``_tasks`` 与 ``_exit_strikes``（无进展退出计数）是
**刻意易失**的 per-run shell 状态——run 只活在内存，重启后 running 的
agent 由恢复路径落 failed；耗尽后的 failed 终态本身是持久事件，恢复语义
不丢。
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cloudra.runtime_v2.dispatcher import WakePolicy
from cloudra.runtime_v2.failures import RunFailureKind, classify_failure, is_retryable
from cloudra.runtime_v2.schemas import AgentSession, AgentState

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

logger = logging.getLogger(__name__)


# Provider-specific phrasings for "input exceeded the model's context window".
# A bare 400 is not enough: it can also mean a malformed request (bad tool
# schema, invalid parameter) that no amount of compaction would fix.
_CONTEXT_OVERFLOW_MARKERS = (
    "context length",
    "maximum context",
    "context_length_exceeded",
    "context window",
    "exceeds the maximum",
    "reduce the length",
    "input is too long",
    "prompt is too long",
    "too many tokens",
    "payload size exceeds",
)

# 预算触发的重试闸门：一次压缩被拒后，投影要再长出可用预算的这个比例才
# 重新尝试。拒因（结构校验失败/摘要不缩短/合并容量不足）在同样输入上会同样
# 失败，逐轮重试只是把整段轨迹反复喂给摘要模型。
COMPACT_RETRY_GROWTH = 0.10

# 同一 run 内"同状态无进展退出"的上限：completion gate 连续以相同缺口指纹
# 拒绝结束达到该次数后，run 落 failed（可恢复非成功状态）并提示用户，
# 不无限消耗模型请求（计划 §6 防自循环）。
DEFAULT_MAX_EXIT_STRIKES = 3


def _is_context_length_error(exc: Exception) -> bool:
    """True when the provider rejected the request for exceeding its window."""
    status = getattr(exc, "status_code", None)
    if status not in (400, 413):
        return False
    text = str(exc).lower()
    return any(marker in text for marker in _CONTEXT_OVERFLOW_MARKERS)


class AgentRunner:
    """One async task per running agent.

    A crashed turn is retried in place: the input was committed to the
    session context projection before the request was sent (and the failed
    turn appended no output), so the retry rebuilds an identical request
    from the projection.  Only after ``max_turn_retries`` does the run
    finish as failed; users should never have to retry transient failures
    by hand.
    """

    def __init__(
        self,
        core: "RuntimeCore",
        pipeline: "TurnPipeline",
        *,
        max_turn_retries: int = 5,
        retry_backoff: tuple[float, ...] = (2.0, 4.0, 8.0, 15.0, 30.0),
        max_exit_strikes: int = DEFAULT_MAX_EXIT_STRIKES,
    ) -> None:
        self.core = core
        self.pipeline = pipeline
        from cloudra.runtime_v2.turn_pipeline import TurnPipeline

        if isinstance(pipeline, TurnPipeline):
            # An injected standalone pipeline joins this core's one durable
            # event path, including when its store attaches after the runner.
            pipeline.event_log = core.event_log
            pipeline.event_hub = core.event_hub
            pipeline.event_writer = core.event_writer
            pipeline.invocations.event_writer = core.event_writer
            pipeline.js_runtime.event_writer = core.event_writer
        self.max_turn_retries = max_turn_retries
        self.retry_backoff = retry_backoff
        self.max_exit_strikes = max_exit_strikes
        self._tasks: dict[str, asyncio.Task] = {}
        # 停止准入：cancel_all（shutdown）后拒绝一切 schedule/唤醒重排——
        # 否则取消收尾期间投递的消息会经 _task_finished 竞态关闭逻辑重新
        # 拉起新 run，关停后仍发新 LLM 请求（停止语义契约 3）。
        self._accepting = True
        # session 作用域的后台任务登记（子 agent 终态回报、launch group 等）：
        # session_id -> tasks。刻意易失（与 _tasks 同理）；用户取消/shutdown
        # 据此取消并 await 同作用域收尾（停止语义契约 1/3）。
        self._background: dict[str, set[asyncio.Task]] = {}
        # 无进展退出计数：session_id -> (run_id, 缺口指纹, 连续次数)。
        # 刻意易失（见模块 docstring）。
        self._exit_strikes: dict[str, tuple[str, str, int]] = {}
        # 压缩被拒时的投影 token 规模：session_id -> tokens。预算触发的重试
        # 闸门（_compaction_retry_due）；刻意易失，重启后允许立即重试一次。
        self._compact_refusals: dict[str, int] = {}
        # Concurrent child/supervisor completions can observe the same parked
        # coordinator. The event marker is durable; this lock closes the live
        # check-then-deliver race for one project.
        self._quiescence_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------ public

    def prune_orphaned_state(self) -> None:
        """Release session/project caches after a hard deletion."""
        sessions = set(self.core.agents)
        for mapping in (self._exit_strikes, self._compact_refusals):
            for session_id in mapping.keys() - sessions:
                mapping.pop(session_id)
        for project_id in self._quiescence_locks.keys() - self.core.projects.keys():
            self._quiescence_locks.pop(project_id)

    def task_for(self, session_id: str) -> asyncio.Task | None:
        """Current run task, if any (also includes a queued group permit)."""
        return self._tasks.get(session_id)

    def schedule(self, session_id: str) -> asyncio.Task | None:
        if not self._accepting:
            return None
        task = self._tasks.get(session_id)
        if task is not None and not task.done():
            return task
        agent = self.core.require_agent(session_id)
        if agent.state is AgentState.RUNNING and task is not None and not task.done():
            return task
        run_semaphore = self.core.launch_groups.run_semaphore(session_id)

        async def run_with_permit() -> None:
            if run_semaphore is None:
                await self._run(agent)
            else:
                async with run_semaphore:
                    await self._run(agent)

        task = asyncio.create_task(run_with_permit(), name=f"agent:{session_id}")
        self._tasks[session_id] = task
        task.add_done_callback(lambda done: self._task_finished(session_id, done))
        return task

    def _task_finished(self, session_id: str, task: asyncio.Task) -> None:
        """Drop a completed task, then close the wakeup race at its boundary.

        A mailbox delivery can observe WAITING/RUNNING while the runner is in
        its final event flush.  ``schedule`` correctly refuses a second task
        while the old task is alive, so the done callback must retry after the
        task is actually gone if the wake changed the projection to RUNNING.
        """
        if self._tasks.get(session_id) is not task:
            return
        self._tasks.pop(session_id, None)
        agent = self.core.agents.get(session_id)
        if agent is None or agent.state is not AgentState.RUNNING:
            return
        if self._inbox_has_pending(agent):
            self.schedule(session_id)

    def track_background(
        self, session_id: str, task: asyncio.Task, *, label: str
    ) -> asyncio.Task:
        """登记 session 作用域的后台任务；完成自动出登记。

        后台任务（子 agent 回报、launch group worker 等）必须走这里，禁止
        裸 create_task——未登记的后台任务用户取消/shutdown 都碰不到
        （Task 0 取证 R1/R2）。
        """
        self._background.setdefault(session_id, set()).add(task)
        task.add_done_callback(lambda done: self._background_finished(session_id, done))
        return task

    def _background_finished(self, session_id: str, task: asyncio.Task) -> None:
        entry = self._background.get(session_id)
        if entry is None:
            return
        entry.discard(task)
        if not entry:
            self._background.pop(session_id, None)

    async def cancel(self, session_id: str) -> None:
        """取消 run task + 该 session 全部已登记后台任务并 await。

        作用域为 session（取消任一 run 即收掉该 session 的未完成后台工作）。
        先快照并取消既有后台任务再取消 run task，随后 drain 等本地收尾写完。
        """
        background = [t for t in self._background.get(session_id, ()) if not t.done()]
        for task in background:
            task.cancel()
        task = self._tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if background:
            await asyncio.gather(*background, return_exceptions=True)
        await self._drain_background(session_id)

    async def cancel_all(self) -> None:
        """shutdown 用：先停准入（此后不再 schedule 任何 run），再取消全部
        session 的 run/background 任务并 await。"""
        self._accepting = False
        for session_id in list({*self._tasks, *self._background}):
            await self.cancel(session_id)

    async def _drain_background(self, session_id: str) -> None:
        """等掉取消收尾期间补登记的后台任务。

        这些任务有界完成；轮次上限只是防回归的保险。
        """
        for _ in range(5):
            pending = [
                t for t in self._background.get(session_id, ()) if not t.done()
            ]
            if not pending:
                return
            await asyncio.gather(*pending, return_exceptions=True)

    # ------------------------------------------------------------------ private

    async def _run(self, agent: AgentSession) -> None:
        core = self.core
        # Hub cursor: everything appended from this point on must reach the
        # hub (SSE, persistence).  start_run/resume and the final
        # message_emitted/finish_run events land outside the per-turn publish,
        # so the cursor spans the whole task and a final flush runs on exit.
        cursor = len(core.event_log)
        try:
            if agent.current_run is not None and agent.state in {
                AgentState.WAITING_INPUT,
                AgentState.WAITING_APPROVAL,
            }:
                run_id = agent.current_run.run_id
                await core.agent_host.resume(agent)
                # 上下文是 session 级投影：resume 不重置它；pending 压缩请求
                # 跨 run 存活，由下面的主循环应用到会话上下文。
            elif agent.current_run is not None and agent.state is AgentState.RUNNING:
                # The command layer already started/resumed this run and only
                # scheduled the task afterwards.
                run_id = agent.current_run.run_id
            else:
                run_id = await core.agent_host.start_run(agent)
            contexts = core.contexts
            # 上下文前缀 owner（Task 2/4）：每个 run 创建一个，但状态从会话
            # 级上下文投影回灌（restored）——跨 run/重启不重装前缀，
            # 静态协议与动态快照只在真实变化时以追加消息表达。
            context_prefix = None
            prompt_provider = getattr(self.pipeline, "prompt_provider", None)
            if prompt_provider is not None:
                context_prefix = prompt_provider.begin_context(
                    agent=agent,
                    workspace_dir=core.require_project(agent.project_id).workspace_dir,
                    tool_names=agent.capabilities.tools,
                    restored=contexts.prefix_state(agent.id),
                )
            turns = 0
            while agent.state is AgentState.RUNNING:
                inbox_messages = self._drain_inbox(agent)
                if turns == 0 and not inbox_messages:
                    inbox = core.mailbox.ensure_inbox(agent.id)
                    message = await inbox.get()
                    inbox_messages.append(message)
                turns += 1
                inbox_messages = await asyncio.to_thread(
                    self._prepare_inbox_messages, agent, inbox_messages
                )
                if contexts.current_messages(agent.id):
                    if agent.id in core.pending_compactions:
                        await self._consume_pending_compaction(
                            agent, run_id, context_prefix=context_prefix
                        )
                # 在 pipeline 装好本轮输入、动态前缀和通知后再检查容量。
                # inbox 已落入投影；压缩时仍保留当前指令原文。
                preserve_ids = {
                    str(item["message_id"]) for item in inbox_messages if item.get("message_id")
                }

                async def prepare_context(messages, estimated_tokens):
                    return await self._prepare_context(
                        agent, run_id, messages, estimated_tokens,
                        context_prefix=context_prefix, preserve_message_ids=preserve_ids,
                    )
                attempt = 0
                overflow_compacted = False
                while True:
                    try:
                        project = core.require_project(agent.project_id)
                        outcome = await self.pipeline.run_turn(
                            agent=agent,
                            run_id=run_id,
                            settings=agent.settings.model_copy(deep=True),
                            capabilities=agent.capabilities,
                            inbox_messages=inbox_messages,
                            workspace_dir=project.workspace_dir,
                            notices=core.notices,
                            context_prefix=context_prefix,
                            context_broker=contexts,
                            vision_enabled=self._vision_enabled(agent),
                            prepare_context=prepare_context,
                        )
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        current = contexts.current_messages(agent.id)
                        if current and _is_context_length_error(exc) and not overflow_compacted:
                            # 统一的一次全量压缩；压缩被拒（不缩短/校验失败/
                            # 容量不足）= 同一输入无进展，本 run 不重复压缩。
                            stats = await self._apply_compaction(
                                agent,
                                run_id,
                                trigger="context_overflow",
                                context_prefix=context_prefix,
                                preserve_message_ids=preserve_ids,
                            )
                            overflow_compacted = True
                            if stats.get("compacted"):
                                continue
                        attempt += 1
                        if attempt > self.max_turn_retries or not is_retryable(exc):
                            raise
                        delay = self.retry_backoff[min(attempt - 1, len(self.retry_backoff) - 1)]
                        core.event_log.append(
                            "run.retry",
                            stream="agent",
                            project_id=agent.project_id,
                            session_id=agent.id,
                            run_id=run_id,
                            data={
                                "attempt": attempt,
                                "max_retries": self.max_turn_retries,
                                "error": str(exc),
                                "next_delay_s": delay,
                            },
                        )
                        await asyncio.sleep(delay)
                    finally:
                        await self._publish_new_events(cursor)
                        cursor = len(core.event_log)
                # 响应落上下文：完整 assistant/tool 消息（恰好一次；输入已在
                # 发送前经 commit_input 入投影）。
                await self._commit_turn_output(agent, run_id, outcome)
                if outcome.decision == "stop":
                    # 不变量"RUNNING 的下个轮次 drain 收件箱"只在还有下个轮次时
                    # 成立：轮次中途到达的消息（如异步子 agent 终态回报，其 wake
                    # 对 RUNNING 是 no-op）在 stop 收尾后将无人 drain。收件箱非空
                    # 时续跑一轮而不是收尾。
                    if self._inbox_has_pending(agent):
                        continue
                    # 统一运行结束门禁（Task 4A）：显式 stop 与纯文本最终回复
                    # 都在这里裁决；门禁不放行时绝不 finish_run(succeeded)。
                    explicit_stop = any(
                        call.name == self.pipeline.stop_tool
                        for call, _result in outcome.tool_exchanges
                    )
                    stop_arguments = None
                    if explicit_stop:
                        stop_arguments = next(
                            (
                                call.arguments
                                for call, _result in outcome.tool_exchanges
                                if call.name == self.pipeline.stop_tool
                            ),
                            None,
                        )
                    gate, _source = await self._evaluate_completion_gate(
                        agent,
                        run_id,
                        explicit_stop=explicit_stop,
                        stop_arguments=stop_arguments,
                        candidate_answer=outcome.content,
                    )
                    if gate.action == "continue_work":
                        # Keep the candidate private until the completion gate permits delivery.
                        strike, exhausted = self._track_exit_strike(agent, run_id, gate)
                        if exhausted:
                            notice = (
                                f"[Completion gate] Run ended as failed: {self.max_exit_strikes} "
                                f"exit attempts were rejected without new progress (latest: "
                                f"{gate.reason}). The run was NOT marked complete; send a new "
                                "message to resume with fresh instructions."
                            )
                            self._emit_run_message(agent, run_id, notice)
                            await core.agent_host.finish_run(
                                agent,
                                outcome="failed",
                                error=(
                                    f"completion gate: {self.max_exit_strikes} exit attempts "
                                    f"without progress ({gate.reason})"
                                ),
                                failure_kind=RunFailureKind.COMPLETION_NO_PROGRESS,
                            )
                            await self._deliver_completion(agent)
                            break
                        # 缺口/下一步反馈进下一轮（mailbox 投递即持久审计
                        # agent.message_injected + 下一轮 drain 消费）。
                        # 本 run 正在跑、下一轮就会 drain inbox → 不唤醒。
                        await core.dispatcher.commit_and_deliver(
                            to_session_id=agent.id,
                            project_id=agent.project_id,
                            content=self._gate_feedback_text(gate, strike=strike),
                            sender="completion_gate",
                            wake=WakePolicy.NEVER,
                        )
                        continue
                    if gate.action == "wait_review":
                        # 退出审批请求已在门禁内持久化（同 basis 去重复用）且
                        # Supervisor 已按状态表通知；挂起等裁决，不落终态。
                        await core.agent_host.transition(
                            agent,
                            AgentState.WAITING_APPROVAL,
                            reason="wait_review",
                            run_id=run_id,
                        )
                        # 裁决通知/新消息可能恰在判定期间投递：与 wait_approval
                        # 分支同一防 lost-wakeup 握手，迁移后立即复查收件箱。
                        if self._inbox_has_pending(agent):
                            await core.agent_host.transition(
                                agent,
                                AgentState.RUNNING,
                                reason="review_notification_received",
                                run_id=run_id,
                            )
                            continue
                        # 诚实回执（在收件箱复查之后投递，避免自己的反馈触发
                        # 立刻唤醒空转）：stop 工具只确认收到请求，
                        # stop 实际在等 Supervisor 退出裁决——必须把审批回路
                        # 讲清楚，否则 agent 无法区分 接受/待审/被拒 三种结局。
                        await core.dispatcher.commit_and_deliver(
                            to_session_id=agent.id,
                            project_id=agent.project_id,
                            content=self._wait_review_feedback_text(gate),
                            sender="completion_gate",
                            run_id=run_id,
                            wake=WakePolicy.NEVER,
                        )
                        break
                    # wait_background（有可核实唤醒来源的挂起，不是交付）与
                    # allow_final（审计通过/有效批准/agent 声明）才走到收尾。
                    # Task 5 起 schedule stop 不再无条件 compact——压缩触发只有
                    # 手动 compact / 达到上下文预算 / 真实 overflow 三种。
                    # The compute broker marks a terminal job notified only after
                    # its message is delivered. A notice arriving during the gate
                    # must be read before this run becomes a child's first final
                    # result. Top-level agents retain the existing finish/wake
                    # boundary, which starts a fresh run for late user/child input.
                    # Share the target lock with MessageDispatcher so a delivery
                    # cannot slip between this check and finish_run.
                    async with core.dispatcher.target_lock(agent.id):
                        if agent.parent_session_id and self._inbox_has_pending(agent):
                            continue
                        for stage in getattr(self.pipeline, "stages", ()):
                            hook = getattr(stage, "on_run_end", None)
                            if hook is not None:
                                await hook(agent, explicit_stop=explicit_stop)
                        final_answer = gate.final_answer if gate.final_answer is not None else outcome.content
                        if gate.action == "allow_final" and final_answer:
                            self._emit_run_message(agent, run_id, final_answer)
                        elif gate.action == "wait_background":
                            self._emit_run_message(agent, run_id, gate.reason or "Run paused awaiting background work.")
                        await core.agent_host.finish_run(agent, outcome="succeeded")
                        # CommandBus may enqueue outside MessageDispatcher; keep
                        # the existing post-finish wake handshake for that path.
                        if self._inbox_has_pending(agent):
                            await core.agent_host.wake(agent, runner=core.runner)
                    await self._deliver_completion(agent)
                    break
                if outcome.decision in {"wait_input", "wait_approval"}:
                    await core.agent_host.transition(
                        agent,
                        (
                            AgentState.WAITING_INPUT
                            if outcome.decision == "wait_input"
                            else AgentState.WAITING_APPROVAL
                        ),
                        reason=outcome.decision,
                        run_id=run_id,
                    )
                    # A durable review/approval notification may have been
                    # delivered while the policy was deciding.  Check after
                    # entering WAITING so the notifier cannot lose this wake
                    # in the RUNNING -> WAITING race.
                    if self._inbox_has_pending(agent):
                        # The current runner task is still alive, so
                        # AgentHost.wake() would refuse to schedule a second
                        # task. Resume this task explicitly and let its next
                        # iteration drain the notification.
                        await core.agent_host.transition(
                            agent,
                            AgentState.RUNNING,
                            reason="review_notification_received",
                            run_id=run_id,
                        )
                        continue
                    break
                # "continue" (including blocked-tool feedback) loops again
        except asyncio.CancelledError:
            # Command handler already transitioned the agent and emitted
            # agent.cancelled after host.cancel().  会话上下文投影里已落
            # 的内容（发送前的输入、已完成的轮次输出）保持原样——投影只
            # 记录真实进入过上下文的消息，无需收尾摘要。
            await self._deliver_completion(agent)
            raise
        except Exception as exc:  # pipeline crash becomes a durable failure
            logger.exception("agent %s pipeline failed", agent.id)
            if agent.state is AgentState.RUNNING:
                # 失败分类只在这一处派生（failures.classify_failure），事件里
                # 落枚举，error 文本只供人阅读。
                await core.agent_host.finish_run(
                    agent,
                    outcome="failed",
                    error=str(exc),
                    failure_kind=classify_failure(exc),
                )
            await self._deliver_completion(agent)
        finally:
            # Flush the tail events (message_emitted, finish_run's
            # state_changed/run.finished, or a crashed turn's partial events)
            # so SSE clients and the store see the complete run lifecycle.
            try:
                await self._publish_new_events(cursor)
            except Exception as exc:
                logger.exception("agent %s final event flush failed", agent.id)
                from cloudra.runtime_v2.event_writer import EventPersistenceError

                if isinstance(exc, EventPersistenceError):
                    raise

    async def _deliver_completion(self, agent: AgentSession) -> None:
        from cloudra.runtime_v2.peer_completion import deliver_peer_completion
        from cloudra.runtime_v2.subagent_bridge import deliver_child_completion_to_parent

        if agent.role_id == 'supervisor' and agent.state.value in {'failed', 'cancelled'}:
            from cloudra.runtime_v2.supervision import reconcile_supervision

            # Preserve the existing scientific-backlog failure alert, without
            # reporting notebook maintenance as a completed research subtask.
            await reconcile_supervision(self.core, agent.project_id)
        await deliver_child_completion_to_parent(self.core, agent)
        await deliver_peer_completion(self.core, agent)
        await self.maybe_wake_parked_delivery(agent.project_id)

    async def maybe_wake_parked_delivery(self, project_id: str) -> None:
        """Resume a guided delivery wait once all project background work settles.

        Called by terminal agent and compute-notice events. The notice is
        durable and keyed to the parked run, so duplicate terminal callbacks
        and restarts cannot create another LLM wake for the same wait.
        """
        if not self._accepting:
            return
        from cloudra.dag.stop_audit import (
            has_running_siblings,
            pending_compute_jobs_exist,
        )
        from cloudra.runtime_v2.agent_host import is_background_parked

        core = self.core
        snapshots = [
            (agent, agent.model_copy(deep=True)) for agent in core.agents.values()
            if agent.project_id == project_id
            and agent.role_id == "coordinator"
        ]
        candidates = await asyncio.to_thread(lambda: [
            (agent, snapshot) for agent, snapshot in snapshots
            if is_background_parked(core, snapshot)
        ])
        if not candidates:
            return
        lock = self._quiescence_locks.setdefault(project_id, asyncio.Lock())
        async with lock:
            for coordinator, snapshot in candidates:
                def still_parked():
                    return (
                        core.agents.get(coordinator.id) is coordinator
                        and coordinator.state is snapshot.state
                        and coordinator.current_run is None
                        and coordinator.updated_at == snapshot.updated_at
                    )

                if not still_parked():
                    continue
                if not await asyncio.to_thread(is_background_parked, core, coordinator):
                    continue
                gate = await asyncio.to_thread(
                    core.event_log.query_session, coordinator.id, types={"agent.completion_gate"}, limit=1,
                )
                if not gate or gate[0].data.get("source") != "dag":
                    continue
                parked_run_id = gate[0].run_id
                if not parked_run_id:
                    continue
                if await pending_compute_jobs_exist(
                    data_dir=None, project_id=project_id,
                ):
                    continue
                if await asyncio.to_thread(
                    has_running_siblings, core, project_id=project_id, session_id=coordinator.id,
                ) or await asyncio.to_thread(core.reminders.pending, coordinator.id):
                    continue
                # The DB check awaits; a regular child message may have
                # already woken this coordinator in the meantime.
                if not still_parked() or not await asyncio.to_thread(is_background_parked, core, coordinator):
                    continue
                # Only scan the durable history after project work has
                # settled. Most child/compute callbacks return above.
                marker = await asyncio.to_thread(lambda: next((
                    event for event in core.event_log.iter_events(
                        session_id=coordinator.id, types={"agent.message_injected"},
                        after_session_seq=gate[0].session_seq or 0,
                    )
                    if event.type == "agent.message_injected"
                    and event.session_id == coordinator.id
                    and (event.data.get("manifest") or {}).get("kind")
                    == "background_quiescence"
                    and (event.data.get("manifest") or {}).get("parked_run_id")
                    == parked_run_id
                ), None))
                if not still_parked():
                    continue
                if marker is not None:
                    # A process can stop after persisting the marker but
                    # before enqueue/wake. Reuse that message rather than
                    # writing a duplicate, and close the interrupted wake.
                    from cloudra.runtime_v2.mailbox import Mailbox

                    async with core.dispatcher.target_lock(coordinator.id):
                        if not still_parked():
                            continue
                        inbox = core.mailbox.inbox(coordinator.id)
                        if inbox is None or inbox.empty():
                            core.mailbox.enqueue(
                                coordinator.id,
                                Mailbox.message_payload(
                                    message_id=str(marker.data["message_id"]),
                                    sender=str(marker.data["sender"]),
                                    content=str(marker.data["content"]),
                                ),
                            )
                        await core.agent_host.wake(coordinator, runner=core.runner)
                    continue
                await core.dispatcher.commit_and_deliver(
                    to_session_id=coordinator.id,
                    project_id=project_id,
                    content=(
                        "[Background work settled] Project background work has "
                        "finished. Recheck delivery and outstanding reviews."
                    ),
                    sender="background_quiescence",
                    manifest={
                        "kind": "background_quiescence",
                        "parked_run_id": parked_run_id,
                    },
                    wake=WakePolicy.PARK_TERMINAL,
                )

    def _emit_run_message(self, agent: AgentSession, run_id: str, content: str) -> None:
        self.core.event_log.append(
            "agent.message_emitted",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"sender": agent.role_id, "content": content},
        )

    async def _evaluate_completion_gate(self, agent: AgentSession, run_id: str, *, explicit_stop: bool, stop_arguments: dict | None, candidate_answer: str = ""):
        """唯一的运行结束判定边界（Task 4A，计划 §6）。

        显式 stop 与无 tool_calls 的纯文本最终回复都流经这里：各 PolicyStage
        的 ``audit_run_end`` 钩子给出本域判定（dag 交付覆盖 / schedule 后台
        事实核查），无意见的 stage 不参与；多域判定取最保守结果
        （wait_background > wait_review > continue_work > allow_final）。
        没有任何门禁意见时按 agent 声明放行——standard 普通问答可结束，但
        如实标注为声明而非已验证完成。判定结论落 ``agent.completion_gate``
        审计事件。返回 (StopGate, source)。
        """
        from cloudra.runtime_v2.policies.base import PipelineContext

        core = self.core
        try:
            project = core.require_project(agent.project_id)
            workspace_dir = project.workspace_dir
        except Exception:
            workspace_dir = None
        ctx = PipelineContext(
            agent=agent,
            run_id=run_id,
            settings_snapshot=agent.settings.model_copy(deep=True),
            capabilities=agent.capabilities,
            inbox_messages=[],
            emit=self.pipeline._emitter(agent, run_id),
            workspace_dir=workspace_dir,
            notices=core.notices,
        )
        verdicts: list[tuple[Any, str]] = []
        for stage in getattr(self.pipeline, "stages", ()):
            hook = getattr(stage, "audit_run_end", None)
            if hook is None:
                continue
            verdict = await hook(
                ctx, explicit_stop=explicit_stop, stop_arguments=stop_arguments, candidate_answer=candidate_answer
            )
            if verdict is not None:
                verdicts.append((verdict, getattr(stage, "name", "unknown")))
        if verdicts:
            rank = {"wait_background": 0, "wait_review": 1, "continue_work": 2, "allow_final": 3}
            gate, source = min(verdicts, key=lambda item: rank.get(item[0].action, 3))
        else:
            from cloudra.dag.stop_audit import StopGate

            gate = StopGate(
                action="allow_final",
                reason=(
                    "no completion gate applies to this agent; the run ends as an "
                    "agent-declared result (not independently verified)"
                ),
                basis="declared",
            )
            source = "declared"
        core.event_log.append(
            "agent.completion_gate",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={
                "action": gate.action,
                "source": source,
                "explicit_stop": explicit_stop,
                "reason": gate.reason,
                "request_id": gate.request_id,
                # 收尾依据（结构化）：投影成 UI 的「已验证完成 / 部分交付 /
                # 未独立验证」。绝不由 reason 文本反推。
                "basis": gate.basis,
            },
        )
        return gate, source

    def _track_exit_strike(self, agent: AgentSession, run_id: str, gate) -> tuple[int, bool]:
        """同状态重复无进展退出的有界计数（刻意易失 per-run shell 状态）。

        指纹 = 判定理由 + 开放缺口集合：缺口变了算有进展、重新计数；同一缺口
        状态反复退出才累计，达到 ``max_exit_strikes`` 返回 exhausted=True。
        """
        report = gate.report
        gaps = []
        if report is not None:
            gaps = [
                *(getattr(report, "unresolved", None) or []),
                *(getattr(report, "inconclusive", None) or []),
            ]
        fingerprint = gate.reason + "|" + ",".join(
            f"{getattr(gap, 'code', '')}:{getattr(gap, 'target_id', '')}" for gap in gaps
        )
        last = self._exit_strikes.get(agent.id)
        strike = last[2] + 1 if last is not None and last[:2] == (run_id, fingerprint) else 1
        self._exit_strikes[agent.id] = (run_id, fingerprint, strike)
        return strike, strike >= self.max_exit_strikes

    def _wait_review_feedback_text(self, gate) -> str:
        """wait_review 挂起前的退出审批回路说明（模型可读的诚实回执）。"""
        return (
            "[Completion gate] Stop is pending Supervisor review, not accepted: "
            f"a final review for your proposed delivery was submitted (request_id={gate.request_id}) "
            "and this run is now suspended awaiting the decision; "
            "the stop tool only acknowledged the request. What happens next:\n"
            "- The Supervisor's decision arrives as a [Supervisor review decision] "
            "notice and wakes you.\n"
            "- On accept: call stop again with the same declared delivery_disposition; "
            "the runtime binds the current Supervisor approval automatically.\n"
            "- On reject or needs_evidence: the reason and next action arrive as feedback; resolve "
            "them (or close the gaps) and stop again."
        )

    def _gate_feedback_text(self, gate, *, strike: int) -> str:
        from cloudra.dag.stop_audit import format_gate_gaps

        lines = [f"[Completion gate] This run cannot finish yet: {gate.reason}"]
        gap_lines = format_gate_gaps(gate.report)
        if gap_lines:
            lines.append("Open gaps:")
            lines.extend(gap_lines)
        lines.append(
            "Next: resolve the items above (for DAG deliveries, bind the supporting "
            "evidence and submit it for review with dag_bind_evidence, close the gap, "
            "or re-declare with delivery_disposition='partial'), then stop again. "
            f"Exit attempt {strike}/{self.max_exit_strikes} without new progress; "
            "repeating the same exit without progress ends the run as failed."
        )
        return "\n".join(lines)

    def _drain_inbox(self, agent: AgentSession) -> list[dict]:
        inbox = self.core.mailbox.inbox(agent.id)
        if inbox is None:
            return []
        messages = []
        while True:
            try:
                messages.append(inbox.get_nowait())
            except asyncio.QueueEmpty:
                return messages

    def _inbox_has_pending(self, agent: AgentSession) -> bool:
        """收件箱是否有未读消息（不消费）。"""
        inbox = self.core.mailbox.inbox(agent.id)
        return inbox is not None and not inbox.empty()

    def _provider_supports_vision(self, agent: AgentSession) -> bool:
        """Vision capability of the configured provider/model.

        The check lives on the LLM provider (adapters.LegacyLLMProvider);
        providers without the method (test fakes, custom bridges) are
        assumed vision-capable, matching the settings default.
        """
        checker = getattr(getattr(self.pipeline, "llm", None), "supports_vision", None)
        if checker is None:
            return True
        try:
            return bool(checker(agent))
        except Exception:
            return False

    def _vision_enabled(self, agent: AgentSession) -> bool:
        # getattr: the visual_mode setting is added to schemas by a sibling
        # change; until then the default is on.
        return bool(getattr(agent.settings, "visual_mode", True)) and self._provider_supports_vision(agent)

    def _prepare_inbox_messages(self, agent: AgentSession, messages: list[dict]) -> list[dict]:
        """Normalize user-attached images into stable ``image_ref`` parts.

        进上下文投影的消息只存稳定引用（路径 + fallback 文本），不重嵌
        base64；发送前由 turn_pipeline.resolve_media_references 按当前
        vision 能力解析为 data URL 或文本降级。
        """
        from cloudra.infra.media import snapshot_image_reference

        prepared = []
        for item in messages:
            images = [p for p in (item.get("images") or []) if isinstance(p, str) and p]
            if not images:
                prepared.append(item)
                continue
            parts: list[dict] = [{"type": "text", "text": str(item.get("content") or "")}]
            parts.extend(
                snapshot_image_reference(
                    path, conv_id=agent.project_id,
                    fallback=f"[User attached image: {path}]",
                )
                for path in images
            )
            prepared.append({**item, "content": parts})
        return prepared

    def _tool_result_content(self, agent: AgentSession, result) -> object:
        """Context content for one tool result, with image re-injection."""
        from cloudra.runtime_v2.invocation import tool_result_context_content

        return tool_result_context_content(agent, result)

    async def _commit_turn_output(self, agent: AgentSession, run_id: str, outcome) -> None:
        """响应消息恰好一次落进会话上下文投影（context.appended）。

        输入（前缀增量/inbox/通知）已在发送前由 ContextBroker.commit_input
        入投影；这里只用同一事件原子追加 assistant tool_calls 与全部匹配的
        tool outputs。run_turn 失败/取消时不调用，不能留下 provider 拒绝的
        半条工具调用；已提交的输入仍留在投影里（它确实进入过请求）。
        """
        entries: list[dict] = []
        tool_calls = [call for call, _ in outcome.tool_exchanges]
        if outcome.blocked_call is not None:
            tool_calls.append(outcome.blocked_call)
        if outcome.content or tool_calls:
            entry: dict = {"role": "assistant", "content": outcome.content}
            if outcome.reasoning:
                entry["reasoning_content"] = outcome.reasoning
            if tool_calls:
                # Structured form; the LLM adapter converts these into the
                # wire format (assistant tool_calls + matching tool messages).
                entry["tool_calls"] = [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in tool_calls
                ]
            entries.append(entry)
        for call, result in outcome.tool_exchanges:
            entries.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": await asyncio.to_thread(self._tool_result_content, agent, result),
                    **({'tool_document_compact_content':result.data['tool_document_compact_content']}
                       if isinstance(result.data, dict) and result.data.get('tool_document_compact_content') else {}),
                    **({'tool_documents':[{'name':doc['name'],'revision':doc['revision']} for doc in result.data.get('documents',[])]}
                       if call.name=='get_tool_docs' and result.is_success else {}),
                    **({'tool_documents': result.data['tool_documents']}
                       if call.name == 'js_exec' and isinstance(result.data, dict)
                       and result.data.get('tool_documents') else {}),
                }
            )
        if outcome.blocked_call is not None:
            entries.append(
                {
                    "role": "tool",
                    "tool_call_id": outcome.blocked_call.id,
                    "content": outcome.message or "blocked by policy",
                }
            )
        await self.core.contexts.append_output(agent=agent, run_id=run_id, messages=entries)

    async def _prompt_token_ratio(self, agent: AgentSession, model: str) -> float:
        # Local tokenizers differ from the provider's. Reuse the last real
        # request's ratio, including after a restart; summary calls are excluded.
        before = None
        while True:
            completed = await asyncio.to_thread(
                self.core.event_log.query_session, agent.id, types=("llm.completed",),
                before_session_seq=before, limit=1,
            )
            if not completed:
                return 1.0
            sample = completed[-1].data
            before = completed[-1].session_seq - 1
            if sample.get("kind") == "summary":
                continue
            if sample.get("model") != model:
                return 1.0
            usage = sample.get("usage") or {}
            actual = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            previous = sample.get("estimated_prompt_tokens") or 0
            if previous > 0 and actual > 0:
                return max(1.0, actual / previous)

    async def _prepare_context(
        self, agent: AgentSession, run_id: str, messages: list[dict], estimated_tokens: int,
        *, context_prefix=None, preserve_message_ids: set[str],
    ) -> list[dict]:
        """Apply the budget to the complete request, corrected by observed usage."""
        from cloudra.runtime_v2.compaction import usable_prompt_tokens
        from cloudra.runtime_v2.turn_pipeline import ContextBudgetError, resolve_media_references

        settings = self._effective_settings(agent)
        window = settings.context_window or 128_000
        budget = usable_prompt_tokens(window, settings.max_tokens)
        ratio = await self._prompt_token_ratio(agent, settings.model)
        tokens = math.ceil(estimated_tokens * ratio)
        if tokens > budget and self._compaction_retry_due(agent.id, tokens, budget):
            stats = await self._apply_compaction(
                agent, run_id, trigger="budget", context_prefix=context_prefix,
                preserve_message_ids=preserve_message_ids,
            )
            if stats.get("compacted"):
                messages = await resolve_media_references(
                    self.core.contexts.current_messages(agent.id),
                    vision_enabled=self._vision_enabled(agent),
                )
                estimated_tokens = await self.pipeline.estimate_prompt_tokens(agent, messages)
                tokens = math.ceil(estimated_tokens * ratio)
            else:
                self._compact_refusals[agent.id] = tokens
        if tokens + settings.max_tokens > window:
            raise ContextBudgetError(
                f"Configured token budget exceeded: input={tokens}, "
                f"output reserve={settings.max_tokens}, window={window}. "
                "Compaction could not make the request fit. Shorten the input "
                "or adjust context_window / max_tokens."
            )
        return messages

    def _effective_settings(self, agent: AgentSession):
        """容量判定用的生效设置：spawn 快照里 context_window=0 表示未设置，
        真实窗口由 provider 桥接从 config 槽位补全（与遥测解析生效 model
        同一钩子）；无钩子的 provider（测试 fake）回退快照原值。"""
        resolver = getattr(getattr(self.pipeline, "llm", None), "resolve_effective_settings", None)
        if resolver is not None:
            return resolver(agent)
        return agent.settings

    def _compaction_retry_due(
        self, session_id: str, tokens_now: int, budget_tokens: int
    ) -> bool:
        """预算触发闸门：上次被拒后投影需再长出预算的 ``COMPACT_RETRY_GROWTH``。

        同一份输入重跑摘要只会得到同样的拒绝（且每次都要把整段轨迹重新
        喂给摘要模型），所以按"有实质新进展"放行，而不是逐轮重试。
        """
        refused_at = self._compact_refusals.get(session_id)
        if refused_at is None:
            return True
        step = max(int(budget_tokens * COMPACT_RETRY_GROWTH), 1024)
        return tokens_now - refused_at >= step

    async def _consume_pending_compaction(
        self,
        agent: AgentSession,
        run_id: str,
        *,
        context_prefix=None,
    ) -> dict:
        """Apply a manual compact request; drop pending only after a successful install."""
        stats = await self._apply_compaction(
            agent, run_id, context_prefix=context_prefix
        )
        if stats.get("compacted"):
            self.core.pending_compactions.discard(agent.id)
        return stats

    async def _apply_compaction(
        self,
        agent: AgentSession,
        run_id: str,
        trigger: str = "manual",
        *,
        context_prefix=None,
        preserve_message_ids: set[str] | None = None,
    ) -> dict:
        from cloudra.runtime_v2.compaction import (
            SUMMARY_EVENT_CAP,
            compact_context,
            estimate_messages_tokens,
            summarize_with_agent_settings,
        )

        core = self.core
        # 压缩对象是 session 级上下文投影（跨 run 连续）：候选输入冻结时
        # 记录投影版本，install_compacted 只在版本未变时原子安装——压缩
        # 期间到达的新消息绝不丢（版本不符即放弃候选，不覆盖新增纠正）。
        history = core.contexts.current_messages(agent.id)
        preserve_message_ids = preserve_message_ids or set()
        preserved = [
            message for message in history
            if str(message.get("message_id") or "") in preserve_message_ids
        ]
        compactable = [
            message for message in history
            if str(message.get("message_id") or "") not in preserve_message_ids
        ] if preserved else history
        expected_version = len(history)
        ctx = core.session_contexts.get(agent.id)
        old_head_len = int((((ctx.prefix_meta if ctx else None) or {})).get("prefix_len") or 0)
        core.event_log.append(
            "compaction.started",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={
                "history_messages": len(history),
                "trigger": trigger,
            },
        )
        handoff_path: str | None = None
        handoff_text = ""

        async def summarizer(messages):
            return await summarize_with_agent_settings(
                agent, messages, event_log=core.event_log, run_id=run_id
            )

        # 压缩是上下文边界：harness 前缀按当前状态重新装配（动态快照取最新），
        # 当前 pin 通知重渲染进新上下文的头部。
        head: list[dict] = []
        head_meta = None
        if context_prefix is not None:
            head, head_meta = await context_prefix.current_prefix()
            head_meta = {**((ctx.prefix_meta if ctx else None) or {}), **head_meta}
        notices_render = (
            core.notices.render_current(agent.id) if core.notices is not None else []
        )
        settings = self._effective_settings(agent)

        try:
            new_context, stats = await compact_context(
                compactable,
                head=head,
                notices=notices_render,
                summarize=summarizer,
                context_window=settings.context_window,
                max_output=settings.max_tokens,
                token_ratio=await self._prompt_token_ratio(agent, settings.model),
                trigger=trigger,
                old_head_len=old_head_len,
                # 摘要调用有界等待：provider 对超大摘要停滞时按 segment_failed
                # /merge_failed 收敛，不让一次调用把轮次无限挂住（GH #40）。
                # thinking 模型单段摘要实测可达 3-5 分钟（GH #48：首答 194s
                # + 重问撞 300s 超时 → 永久拒替换），下限抬到 600s。
                summary_timeout=(
                    max(float(settings.timeout), 600.0) if settings.timeout else 600.0
                ),
            )
        except Exception as exc:
            # Compaction is best-effort: a summarization failure must never
            # kill the run; the uncompacted context stays in place (no event,
            # no projection change).
            logger.exception("agent %s compaction failed", agent.id)
            stats = {"compacted": False, "error": str(exc) or type(exc).__name__}
        else:
            if stats.get("compacted"):
                new_context.extend(preserved)
                stats["after_messages"] = len(new_context)
                # 压缩摘要同时落工作区审计文件，供人与后续会话回读。
                # Best-effort: a write failure only skips the file and the
                # pointer note.
                handoff_idx = int(stats.get("handoff_index") or 0)
                handoff_text = str(new_context[handoff_idx].get("content") or "")
                handoff_path = await self._persist_compaction_handoff(
                    agent, stats, handoff_text
                )
                if handoff_path:
                    new_context[handoff_idx]["content"] = str(
                        new_context[handoff_idx].get("content") or ""
                    ) + (
                        f"\n\n(The full compaction summary was appended to the "
                        f"workspace file: {handoff_path})"
                    )
                installed = await core.contexts.install_compacted(
                    agent=agent,
                    run_id=run_id,
                    messages=new_context,
                    prefix_meta=head_meta,
                    expected_version=expected_version,
                    trigger=trigger,
                )
                if installed and context_prefix is not None:
                    # owner 采纳新头部：后续轮次 matches() 命中，不重装。
                    context_prefix.adopt(head, head_meta)
                if not installed:
                    stats = {
                        **stats,
                        "compacted": False,
                        "reason": "context_changed",
                    }
                elif trigger == "context_overflow" and core.notices is not None:
                    core.notices.push(
                        agent.id,
                        "[Context compact] Earlier work was compacted because the "
                        "context window overflowed. Continue the current task by "
                        "calling tools. This is not a new user request — do not "
                        "stop just to acknowledge the compact.",
                    )
        finished: dict = dict(stats)
        finished["trigger"] = trigger
        if handoff_path:
            finished["handoff_path"] = handoff_path
        if handoff_text:
            finished["summary"] = handoff_text[:SUMMARY_EVENT_CAP]
        if finished.get("compacted"):
            self._compact_refusals.pop(agent.id, None)
        else:
            # 记下被拒时的投影规模：预算触发要等投影再长出新进展才重试。
            self._compact_refusals[agent.id] = await asyncio.to_thread(
                estimate_messages_tokens, history
            )
        core.event_log.append(
            "compaction.finished",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data=finished,
        )
        return finished

    async def _persist_compaction_handoff(
        self, agent: AgentSession, stats: dict, handoff_text: str
    ) -> str | None:
        """Append a compaction summary to the project's audit file.

        Returns the workspace-relative path on success, ``None`` when there is
        no workspace or the append failed — never raises.
        """
        try:
            project = self.core.require_project(agent.project_id)
        except Exception:
            return None
        workspace = project.workspace_dir
        if not workspace:
            return None
        rel_path = ".cloudra/context_compacts.md"
        path = os.path.join(workspace, rel_path)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        def write() -> str | None:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(
                        f"\n## {stamp} — agent {agent.id}\n"
                        f"before_messages={stats.get('before_messages')} "
                        f"after_messages={stats.get('after_messages')} "
                        f"segments={len(stats.get('segments') or [])} "
                        f"trajectory_tokens={stats.get('trajectory_tokens')} "
                        f"summary_tokens={stats.get('summary_tokens')}\n\n"
                        f"{handoff_text}\n"
                    )
                return rel_path
            except OSError:
                logger.exception("compaction handoff write failed for %s", agent.id)
                return None

        return await asyncio.to_thread(write)

    async def _publish_new_events(self, before: int) -> None:
        # The shared writer tracks the unpublished cursor itself; ``before``
        # is kept for the existing call-site shape.
        await self.core.event_writer.flush()
