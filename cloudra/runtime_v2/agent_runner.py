"""AgentRunner: one async task per running AgentSession.

The runner owns the loop around TurnPipeline.  Commands only mutate state or
deliver inbox messages; execution concurrency lives here.

统一运行结束门禁（Task 4A，计划 2026-09-05-event-driven-supervisor §6）：
显式 stop 与无 tool_calls 的纯文本最终回复都在 runner 收尾前经
``_evaluate_completion_gate`` 到达同一个判定边界；四态 continue_work /
wait_background / wait_review / allow_final 的处置（反馈下一轮 / 挂起等唤醒 /
挂起等裁决 / 落终态）只在这里发生，门禁不阻止结束时绝不 finish_run(succeeded)。

易失状态（3e）：``history``（本 run 的 LLM 对话原文）、``_tasks`` 与
``_exit_strikes``（无进展退出计数）都是**刻意易失**的——对话原文不跨 run、
不跨进程；计数器是 per-run shell 状态（run 只活在内存，重启后 running 的
agent 由恢复路径落 failed），耗尽后的 failed 终态本身是持久事件，恢复语义
不丢。跨 run 连续性由 context tree（handover + run 摘要）与
goal/DAG/memory/工作区的外化状态承载，重启恢复靠事件投影重建后由新消息驱动。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from cloudra.runtime_v2.context_tree import (
    SEED_MARKER,
    SUMMARY_EVENT_CAP,
    build_seed_context,
    build_summary_messages,
    fallback_run_summary,
    latest_handover,
    parse_summary_output,
)
from cloudra.runtime_v2.schemas import AgentSession, AgentState

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

logger = logging.getLogger(__name__)

# messages -> generated text; injected in tests, defaults to the agent's model.
RunSummarizer = Callable[[list[dict[str, Any]]], Awaitable[str]]


def _is_retryable(exc: Exception) -> bool:
    """Only transient failures are worth an in-place retry.

    HTTP 4xx (bad key, insufficient balance, invalid request) will fail again
    on every retry — fail fast instead of burning the retry budget.  408/429
    and 5xx / connection errors stay retryable.  Classification is by the
    ``status_code`` attribute so the kernel never imports the LLM SDK.
    """
    from cloudra.runtime_v2.event_writer import EventPersistenceError

    if isinstance(exc, EventPersistenceError):
        # A store failure means the event stream and the world may have
        # diverged; replaying the turn could repeat an unaudited effect.
        return False
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500 and status not in (408, 429):
        return False
    return True


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

# How many trailing messages the emergency compaction keeps verbatim.  Smaller
# than the manual default (20) because a run that already overflowed the
# window needs an aggressive cut; the recent tail usually contains the largest
# tool results.
EMERGENCY_COMPACT_KEEP_RECENT = 10

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

    A crashed turn is retried in place with the accumulated history (the crash
    means the turn never returned, so nothing was appended — retrying is a
    clean redo of the LLM request).  Only after ``max_turn_retries`` does the
    run finish as failed; users should never have to retry transient failures
    by hand.
    """

    def __init__(
        self,
        core: "RuntimeCore",
        pipeline: "TurnPipeline",
        *,
        max_turn_retries: int = 2,
        retry_backoff: tuple[float, ...] = (2.0, 4.0),
        run_summarizer: RunSummarizer | None = None,
        max_exit_strikes: int = DEFAULT_MAX_EXIT_STRIKES,
    ) -> None:
        self.core = core
        self.pipeline = pipeline
        self.max_turn_retries = max_turn_retries
        self.retry_backoff = retry_backoff
        self.run_summarizer = run_summarizer
        self.max_exit_strikes = max_exit_strikes
        self._tasks: dict[str, asyncio.Task] = {}
        # 停止准入：cancel_all（shutdown）后拒绝一切 schedule/唤醒重排——
        # 否则取消收尾期间投递的消息会经 _task_finished 竞态关闭逻辑重新
        # 拉起新 run，关停后仍发新 LLM 请求（停止语义契约 3）。
        self._accepting = True
        # session 作用域的后台任务登记（finalize 等）：session_id -> tasks。
        # 刻意易失（与 _tasks 同理）；用户取消/shutdown 据此取消并 await
        # 同作用域收尾（停止语义契约 1/3）。
        self._background: dict[str, set[asyncio.Task]] = {}
        # 无进展退出计数：session_id -> (run_id, 缺口指纹, 连续次数)。
        # 刻意易失（见模块 docstring）。
        self._exit_strikes: dict[str, tuple[str, str, int]] = {}

    # ------------------------------------------------------------------ public

    def schedule(self, session_id: str) -> None:
        if not self._accepting:
            return
        task = self._tasks.get(session_id)
        if task is not None and not task.done():
            return
        agent = self.core.require_agent(session_id)
        if agent.state is AgentState.RUNNING and task is not None and not task.done():
            return
        task = asyncio.create_task(self._run(agent), name=f"agent:{session_id}")
        self._tasks[session_id] = task
        task.add_done_callback(lambda done: self._task_finished(session_id, done))

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
        """登记 session 作用域的后台任务（finalize 等）；完成自动出登记。

        ``_schedule_run_finalize`` 必须走这里，禁止裸 create_task——未登记的
        后台任务用户取消/shutdown 都碰不到（Task 0 取证 R1/R2）。
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

        作用域为 session（取消任一 run 即收掉该 session 的未完成收尾）。
        先快照并取消既有后台任务再取消 run task：run task 的取消收尾会补
        登记一个 cancelled 结局的 finalize（纯本地确定性收尾，不发 LLM），
        它不在快照内、不被取消，随后由 drain 等它写完本地终态。
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
        """等掉取消收尾期间补登记的后台任务（cancelled 结局的确定性 finalize）。

        这些任务无 LLM 调用、有界完成；轮次上限只是防回归的保险。
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
                core.agent_host.resume(agent)
                # A fresh run starts with empty history; any compaction
                # requested against the previous in-memory history is
                # meaningless now.  resume has no run.started event (whose
                # apply clears the projection on the other two paths), so the
                # shell discards the entry here.
                core.pending_compactions.pop(agent.id, None)
            elif agent.current_run is not None and agent.state is AgentState.RUNNING:
                # The command layer already started/resumed this run and only
                # scheduled the task afterwards.
                run_id = agent.current_run.run_id
            else:
                run_id = core.agent_host.start_run(agent)
            history: list[dict] = []
            seed_count = 0
            seeded = False
            while agent.state is AgentState.RUNNING:
                inbox_messages = self._drain_inbox(agent)
                if not history and not inbox_messages:
                    inbox = core.mailbox.ensure_inbox(agent.id)
                    message = await inbox.get()
                    inbox_messages.append(message)
                if not seeded:
                    # Continuity comes from the context tree: the newest
                    # HANDOVER plus every verbatim instruction message paired
                    # with compressed summaries of past runs.  Empty on the
                    # very first run.  The messages this turn is about to
                    # receive are excluded — they arrive via the inbox and
                    # must not appear twice.
                    seeded = True
                    exclude = frozenset(
                        str(m.get("message_id")) for m in inbox_messages if m.get("message_id")
                    )
                    seed = build_seed_context(
                        core.event_log, agent.id, exclude_message_ids=exclude
                    )
                    history.extend(seed)
                    seed_count = len(seed)
                inbox_messages = await self._prepare_inbox_messages(agent, inbox_messages)
                if history:
                    keep_recent = core.pending_compactions.get(agent.id)
                    if keep_recent is not None:
                        core.pending_compactions.pop(agent.id, None)
                        await self._apply_compaction(agent, run_id, history, keep_recent)
                attempt = 0
                overflow_phase = 0
                while True:
                    try:
                        project = core.require_project(agent.project_id)
                        outcome = await self.pipeline.run_turn(
                            agent=agent,
                            run_id=run_id,
                            settings=agent.settings.model_copy(deep=True),
                            capabilities=agent.capabilities,
                            inbox_messages=inbox_messages,
                            history=history,
                            workspace_dir=project.workspace_dir,
                            notices=core.notices,
                        )
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        if history and _is_context_length_error(exc) and overflow_phase < 2:
                            from cloudra.runtime_v2.compaction import (
                                can_compact_completed_user_turns,
                            )

                            # Phase 0: fold earlier completed user turns.
                            # Empty prior tails skip straight to the current
                            # chapter so a first overflow still emits one compact.
                            if overflow_phase == 0 and can_compact_completed_user_turns(
                                history
                            ):
                                await self._apply_compaction(
                                    agent,
                                    run_id,
                                    history,
                                    keep_recent=0,
                                    trigger="context_overflow",
                                    unit="prior_turns",
                                )
                                overflow_phase = 1
                                continue
                            await self._apply_compaction(
                                agent,
                                run_id,
                                history,
                                keep_recent=EMERGENCY_COMPACT_KEEP_RECENT,
                                trigger="context_overflow",
                            )
                            overflow_phase = 2
                            continue
                        attempt += 1
                        if attempt > self.max_turn_retries or not _is_retryable(exc):
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
                await self._append_history(agent, history, inbox_messages, outcome)
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
                    )
                    if gate.action == "continue_work":
                        # 被拦的最终回复可作中间说明展示，但状态与交付处置一致
                        # （计划 §6 第 8 条）：不 finish、不登记交付处置。
                        if outcome.content:
                            self._emit_run_message(agent, run_id, outcome.content)
                        strike, exhausted = self._track_exit_strike(agent, run_id, gate)
                        if exhausted:
                            notice = (
                                f"[Completion gate] Run ended as failed: {self.max_exit_strikes} "
                                f"exit attempts were rejected without new progress (latest: "
                                f"{gate.reason}). The run was NOT marked complete; send a new "
                                "message to resume with fresh instructions."
                            )
                            self._emit_run_message(agent, run_id, notice)
                            core.agent_host.finish_run(
                                agent,
                                outcome="failed",
                                error=(
                                    f"completion gate: {self.max_exit_strikes} exit attempts "
                                    f"without progress ({gate.reason})"
                                ),
                            )
                            self._deliver_child_completion(agent)
                            self._schedule_run_finalize(
                                agent, run_id, history, seed_count, outcome="failed"
                            )
                            break
                        # 缺口/下一步反馈进下一轮（mailbox 投递即持久审计
                        # agent.message_injected + 下一轮 drain 消费）。
                        core.mailbox.deliver(
                            to_session_id=agent.id,
                            project_id=agent.project_id,
                            content=self._gate_feedback_text(gate, strike=strike),
                            sender="completion_gate",
                        )
                        continue
                    if gate.action == "wait_review":
                        # 退出审批请求已在门禁内持久化（同 basis 去重复用）且
                        # Supervisor 已按状态表通知；挂起等裁决，不落终态。
                        if outcome.content:
                            self._emit_run_message(agent, run_id, outcome.content)
                        core.agent_host.transition(
                            agent,
                            AgentState.WAITING_APPROVAL,
                            reason="wait_review",
                            run_id=run_id,
                        )
                        # 裁决通知/新消息可能恰在判定期间投递：与 wait_approval
                        # 分支同一防 lost-wakeup 握手，迁移后立即复查收件箱。
                        if self._inbox_has_pending(agent):
                            core.agent_host.transition(
                                agent,
                                AgentState.RUNNING,
                                reason="review_notification_received",
                                run_id=run_id,
                            )
                            continue
                        break
                    # wait_background（有可核实唤醒来源的挂起，不是交付）与
                    # allow_final（审计通过/有效批准/agent 声明）才走到收尾。
                    # Schedule polls compact on stop; user-turn stops keep the
                    # tool trajectory.  400 overflow compact (above) is the
                    # fallback for a user conversation that outgrew the window.
                    from cloudra.runtime_v2.compaction import last_instruction_is_reminder

                    if last_instruction_is_reminder(history):
                        await self._apply_compaction(
                            agent, run_id, history, keep_recent=0, trigger="stop"
                        )
                    if outcome.content:
                        self._emit_run_message(agent, run_id, outcome.content)
                    for stage in getattr(self.pipeline, "stages", ()):
                        hook = getattr(stage, "on_run_end", None)
                        if hook is not None:
                            await hook(agent, explicit_stop=explicit_stop)
                    core.agent_host.finish_run(agent, outcome="succeeded")
                    # peek 与 finish 之间到达的消息：deliver 方的 wake 此刻仍可能
                    # 撞在 RUNNING 上（事件未应用前）；状态已 SUCCEEDED 后复查并
                    # 显式 wake 开新 run，关掉最后一段竞态窗口。
                    if self._inbox_has_pending(agent):
                        core.agent_host.wake(agent, runner=core.runner)
                    self._deliver_child_completion(agent)
                    self._schedule_run_finalize(
                        agent, run_id, history, seed_count, outcome="succeeded"
                    )
                    break
                if outcome.decision in {"wait_input", "wait_approval"}:
                    core.agent_host.transition(
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
                        core.agent_host.transition(
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
            # agent.cancelled after host.cancel().  Still record the partial
            # trajectory in the context tree (deterministic summary only).
            self._deliver_child_completion(agent)
            self._schedule_run_finalize(agent, run_id, history, seed_count, outcome="cancelled")
            raise
        except Exception as exc:  # pipeline crash becomes a durable failure
            logger.exception("agent %s pipeline failed", agent.id)
            if agent.state is AgentState.RUNNING:
                core.agent_host.finish_run(agent, outcome="failed", error=str(exc))
            self._deliver_child_completion(agent)
            self._schedule_run_finalize(agent, run_id, history, seed_count, outcome="failed")
        finally:
            # Flush the tail events (message_emitted, finish_run's
            # state_changed/run.finished, or a crashed turn's partial events)
            # so SSE clients and the store see the complete run lifecycle.
            try:
                await self._publish_new_events(cursor)
            except Exception:
                logger.exception("agent %s final event flush failed", agent.id)

    def _deliver_child_completion(self, agent: AgentSession) -> None:
        from cloudra.runtime_v2.subagent_bridge import deliver_child_completion_to_parent

        deliver_child_completion_to_parent(self.core, agent)

    def _emit_run_message(self, agent: AgentSession, run_id: str, content: str) -> None:
        self.core.event_log.append(
            "agent.message_emitted",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"sender": agent.role_id, "content": content},
        )

    async def _evaluate_completion_gate(self, agent: AgentSession, run_id: str, *, explicit_stop: bool, stop_arguments: dict | None):
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
                ctx, explicit_stop=explicit_stop, stop_arguments=stop_arguments
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

    @staticmethod
    async def _image_part(path: str) -> dict | None:
        """Encode a workspace image as an OpenAI image_url part (None on failure)."""
        from cloudra.infra.media import encode_image_data_url

        url = await asyncio.to_thread(encode_image_data_url, path)
        if url is None:
            return None
        return {"type": "image_url", "image_url": {"url": url}}

    async def _prepare_inbox_messages(self, agent: AgentSession, messages: list[dict]) -> list[dict]:
        """Normalize user-attached images into the message content.

        Vision on → content becomes a parts list (text + image_url parts);
        vision off → one English fallback line per image.  The pipeline and
        the history append both consume ``item["content"]``, so this single
        normalization covers the current turn and later turns identically.
        """
        prepared = []
        for item in messages:
            images = [p for p in (item.get("images") or []) if isinstance(p, str) and p]
            if not images:
                prepared.append(item)
                continue
            content = str(item.get("content") or "")
            if not self._vision_enabled(agent):
                fallback = "".join(f"\n[User attached image: {path}]" for path in images)
                prepared.append({**item, "content": content + fallback})
                continue
            parts: list[dict] = [{"type": "text", "text": content}]
            for path in images:
                part = await self._image_part(path)
                if part is not None:
                    parts.append(part)
                else:
                    parts.append({"type": "text", "text": f"[User attached image: {path} (could not be loaded)]"})
            prepared.append({**item, "content": parts})
        return prepared

    async def _tool_result_content(self, agent: AgentSession, result) -> object:
        """History content for one tool result, with image re-injection.

        A result carrying ``image_paths`` (or a single ``image_path``) is
        re-injected as image_url parts when visual mode is on and the model
        can see; otherwise the summary gains one English fallback line per
        path.  There is no N-image cap.
        """
        from cloudra.runtime_v2.invocation import image_paths_from_tool_result

        summary = result.summary
        paths = image_paths_from_tool_result(result)
        if not paths:
            return summary
        if not self._vision_enabled(agent):
            extra = "".join(
                f"\n[Image rendered at: {path} — the configured model has no "
                "vision support; inspect the file directly if needed.]"
                for path in paths
            )
            return (summary or "") + extra
        parts: list[dict] = [{"type": "text", "text": summary or ""}]
        for path in paths:
            part = await self._image_part(path)
            if part is not None:
                parts.append(part)
        if len(parts) == 1:
            return summary
        return parts

    async def _append_history(self, agent: AgentSession, history: list[dict], inbox_messages: list[dict], outcome) -> None:
        for item in inbox_messages:
            history.append({"role": "user", "content": item.get("content", "")})
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
            history.append(entry)
        for call, result in outcome.tool_exchanges:
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": await self._tool_result_content(agent, result),
                }
            )
        if outcome.blocked_call is not None:
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": outcome.blocked_call.id,
                    "content": outcome.message or "blocked by policy",
                }
            )

    async def _apply_compaction(
        self,
        agent: AgentSession,
        run_id: str,
        history: list[dict],
        keep_recent: int,
        trigger: str = "manual",
        *,
        unit: str = "tail",
    ) -> dict:
        from cloudra.runtime_v2.compaction import (
            compact_completed_user_turns,
            compact_history,
            summarize_with_agent_settings,
        )

        core = self.core
        core.event_log.append(
            "compaction.started",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={
                "keep_recent": keep_recent,
                "history_messages": len(history),
                "trigger": trigger,
                "unit": unit,
            },
        )
        handoff_path: str | None = None
        handoff_text = ""

        async def summarizer(messages):
            return await summarize_with_agent_settings(agent, messages)

        try:
            if unit == "prior_turns":
                new_history, stats = await compact_completed_user_turns(
                    history, summarizer, trigger=trigger
                )
            else:
                new_history, stats = await compact_history(
                    history,
                    keep_recent,
                    summarizer,
                    trigger=trigger,
                )
        except Exception as exc:
            # Compaction is best-effort: a summarization failure must never
            # kill the run; the uncompacted history stays in place.
            logger.exception("agent %s compaction failed", agent.id)
            stats = {"compacted": False, "error": str(exc)}
        else:
            if stats.get("compacted"):
                history[:] = new_history
                # The in-memory handoff dies with the run; append it to a
                # workspace file so later runs and human auditors still have
                # the summary.  Best-effort: a write failure only skips the
                # file and the pointer note.
                handoff_idx = int(stats.get("handoff_index") or 0)
                handoff_text = str(history[handoff_idx].get("content") or "")
                handoff_path = await self._persist_compaction_handoff(
                    agent, stats, handoff_text
                )
                if handoff_path:
                    history[handoff_idx]["content"] = str(
                        history[handoff_idx].get("content") or ""
                    ) + (
                        f"\n\n(The full compaction summary was appended to the "
                        f"workspace file: {handoff_path})"
                    )
                if trigger == "context_overflow" and core.notices is not None:
                    core.notices.push(
                        agent.id,
                        "[Context compact] History after the last user/schedule "
                        "message was compacted because the context window overflowed. "
                        "Continue the current task by calling tools. This is not a "
                        "new user request — do not stop just to acknowledge the compact.",
                    )
        finished: dict = dict(stats)
        finished["trigger"] = trigger
        if handoff_path:
            finished["handoff_path"] = handoff_path
        if handoff_text:
            # Keep the compaction change itself in the context tree: the full
            # summary text rides on the event, not just the workspace file.
            finished["summary"] = handoff_text[:SUMMARY_EVENT_CAP]
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
                        f"after_messages={stats.get('after_messages')}\n\n"
                        f"{handoff_text}\n"
                    )
                return rel_path
            except OSError:
                logger.exception("compaction handoff write failed for %s", agent.id)
                return None

        return await asyncio.to_thread(write)

    def _schedule_run_finalize(
        self,
        agent: AgentSession,
        run_id: str,
        history: list[dict],
        seed_count: int,
        *,
        outcome: str,
    ) -> None:
        """Detach run-context finalization from the runner task.

        Finalization makes an LLM call; if it ran inline, the runner task
        would outlive the state transition and ``schedule()`` would dedupe a
        newly woken run against the still-alive old task — the wake would be
        swallowed.  The detached task publishes its own events to the hub.
        Registered via ``track_background`` so user cancel / shutdown can
        cancel and await it (停止语义契约 1/3).
        """
        task = asyncio.create_task(
            self._finalize_run_context(agent, run_id, history, seed_count, outcome=outcome),
            name=f"finalize:{agent.id}",
        )
        self.track_background(agent.id, task, label=f"finalize:{outcome}")

    async def _finalize_run_context(
        self,
        agent: AgentSession,
        run_id: str,
        history: list[dict],
        seed_count: int,
        *,
        outcome: str,
    ) -> None:
        """Fold a finished run into the context tree.  Best-effort throughout.

        succeeded runs get one LLM call producing the run trajectory summary
        plus a rewritten HANDOVER; failed/cancelled runs (or a broken
        summarizer) degrade to a deterministic event-derived summary and keep
        the previous handover.  Nothing here may break run teardown.
        """
        core = self.core
        try:
            # Exclude an intact seed block so summaries never summarize
            # earlier summaries; a mid-run compaction already folded the seed
            # into its handoff, in which case the whole history is new work.
            body = history
            if (
                seed_count
                and len(history) > seed_count
                and str(history[0].get("content") or "").startswith(SEED_MARKER)
            ):
                body = history[seed_count:]
            run_events = [
                event
                for event in core.event_log
                if event.session_id == agent.id
                and event.run_id == run_id
                and event.type in {"tool.finished", "agent.message_emitted", "run.finished"}
            ]
            # A succeeded run with no work beyond the seed leaves nothing to
            # record; failed/cancelled runs always record — even an empty one
            # documents the crash through its run.finished event.
            if not body and outcome == "succeeded":
                return
            session_seqs = [
                event.session_seq
                for event in core.event_log
                if event.session_id == agent.id
                and event.run_id == run_id
                and event.session_seq is not None
            ]
            seq_range = (
                {"start": min(session_seqs), "end": max(session_seqs)} if session_seqs else None
            )
            handover = latest_handover(core.event_log, agent.id)
            fallback = outcome != "succeeded"
            if not fallback and agent.state is AgentState.CANCELLED:
                # 停止语义契约 1：用户取消后，该 session 的收尾禁止新发 LLM
                # 摘要请求——退化为本地可确定的摘要（取消发生在 finalize
                # 已调度未发请求窗口时的准入检查；已登记的 finalize 同时会
                # 被 cancel/cancel_all 直接取消）。
                fallback = True
            run_log = ""
            new_handover: str | None = None
            if not fallback:
                try:
                    from cloudra.runtime_v2.compaction import (
                        _serialize,
                        summarize_with_agent_settings,
                    )

                    summarizer = self.run_summarizer or (
                        lambda messages: summarize_with_agent_settings(agent, messages)
                    )
                    output = await summarizer(
                        build_summary_messages(
                            handover[0] if handover else None, _serialize(body)
                        )
                    )
                    run_log, new_handover = parse_summary_output(output or "")
                    if not run_log:
                        fallback = True
                except Exception:
                    # The summary must never kill teardown; fall back to the
                    # deterministic trajectory and keep the old handover.
                    logger.exception("agent %s run summarization failed", agent.id)
                    fallback = True
            if fallback:
                run_log = fallback_run_summary(run_events)
                new_handover = None
            core.event_log.append(
                "context.run_summarized",
                stream="agent",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=run_id,
                data={
                    "summary": run_log[:SUMMARY_EVENT_CAP],
                    "outcome": outcome,
                    "fallback": fallback,
                    "seq_range": seq_range,
                },
            )
            # Detached from the runner task, so flush directly — nobody else
            # will flush these events to SSE subscribers.
            await core.event_writer.flush()
            if new_handover:
                core.event_log.append(
                    "context.handover_updated",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={
                        "handover": new_handover,
                        "based_on_run_id": run_id,
                        "revision": (handover[1] if handover else 0) + 1,
                    },
                )
                await core.event_writer.flush()
                await self._persist_handover(agent, new_handover)
        except Exception:
            logger.exception("agent %s run-context finalization failed", agent.id)

    async def _persist_handover(self, agent: AgentSession, handover_text: str) -> str | None:
        """Overwrite the workspace handover file with the latest snapshot.

        Returns the workspace-relative path on success, ``None`` otherwise —
        never raises.  The file is an audit/readable copy; the authoritative
        handover is the newest ``context.handover_updated`` event.
        """
        try:
            project = self.core.require_project(agent.project_id)
        except Exception:
            return None
        workspace = project.workspace_dir
        if not workspace:
            return None
        rel_path = ".cloudra/handover.md"
        path = os.path.join(workspace, rel_path)

        def write() -> str | None:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(f"# Handover — agent {agent.id}\n\n{handover_text}\n")
                return rel_path
            except OSError:
                logger.exception("handover write failed for %s", agent.id)
                return None

        return await asyncio.to_thread(write)

    async def _publish_new_events(self, before: int) -> None:
        # The shared writer tracks the unpublished cursor itself; ``before``
        # is kept for the existing call-site shape.
        await self.core.event_writer.flush()
