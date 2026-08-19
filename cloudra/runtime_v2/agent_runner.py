"""AgentRunner: one async task per running AgentSession.

The runner owns the loop around TurnPipeline.  Commands only mutate state or
deliver inbox messages; execution concurrency lives here.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cloudra.runtime_v2.schemas import AgentSession, AgentState

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

logger = logging.getLogger("runtime_v2.agent_runner")


def _is_retryable(exc: Exception) -> bool:
    """Only transient failures are worth an in-place retry.

    HTTP 4xx (bad key, insufficient balance, invalid request) will fail again
    on every retry — fail fast instead of burning the retry budget.  408/429
    and 5xx / connection errors stay retryable.  Classification is by the
    ``status_code`` attribute so the kernel never imports the LLM SDK.
    """
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
    ) -> None:
        self.core = core
        self.pipeline = pipeline
        self.max_turn_retries = max_turn_retries
        self.retry_backoff = retry_backoff
        self._tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ public

    def schedule(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task is not None and not task.done():
            return
        agent = self.core.require_agent(session_id)
        if agent.state is AgentState.RUNNING and task is not None and not task.done():
            return
        task = asyncio.create_task(self._run(agent), name=f"agent:{session_id}")
        self._tasks[session_id] = task
        task.add_done_callback(lambda _done: self._tasks.pop(session_id, None))

    async def cancel(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

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
            elif agent.current_run is not None and agent.state is AgentState.RUNNING:
                # The command layer already started/resumed this run and only
                # scheduled the task afterwards.
                run_id = agent.current_run.run_id
            else:
                run_id = core.agent_host.start_run(agent)
            history: list[dict] = []
            # A fresh run starts with empty history; any compaction requested
            # against the previous run's history is meaningless now.
            core.pending_compactions.pop(agent.id, None)
            while agent.state is AgentState.RUNNING:
                inbox_messages = self._drain_inbox(agent)
                if not history and not inbox_messages:
                    inbox = core.mailbox.ensure_inbox(agent.id)
                    message = await inbox.get()
                    inbox_messages.append(message)
                if history:
                    keep_recent = core.pending_compactions.get(agent.id)
                    if keep_recent is not None:
                        core.pending_compactions.pop(agent.id, None)
                        await self._apply_compaction(agent, run_id, history, keep_recent)
                attempt = 0
                emergency_compacted = False
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
                        if (
                            not emergency_compacted
                            and history
                            and _is_context_length_error(exc)
                        ):
                            # The provider rejected the request for exceeding
                            # its context window.  Compact the history once and
                            # retry the same turn; a second overflow (or any
                            # other 4xx) fails the run as before.
                            emergency_compacted = True
                            await self._apply_compaction(
                                agent,
                                run_id,
                                history,
                                keep_recent=EMERGENCY_COMPACT_KEEP_RECENT,
                                trigger="context_overflow",
                            )
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
                self._append_history(history, inbox_messages, outcome)
                if outcome.decision == "stop":
                    if outcome.content:
                        core.event_log.append(
                            "agent.message_emitted",
                            stream="agent",
                            project_id=agent.project_id,
                            session_id=agent.id,
                            run_id=run_id,
                            data={"sender": agent.role_id, "content": outcome.content},
                        )
                    # D8.3：区分显式 stop 与最终消息收尾——dag 模式下后者
                    # 由 dag policy stage 自动记录 partial 交付处置。
                    explicit_stop = any(
                        call.name == self.pipeline.stop_tool
                        for call, _result in outcome.tool_exchanges
                    )
                    for stage in getattr(self.pipeline, "stages", ()):
                        hook = getattr(stage, "on_run_end", None)
                        if hook is not None:
                            await hook(agent, explicit_stop=explicit_stop)
                    core.agent_host.finish_run(agent, outcome="succeeded")
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
                    break
                # "continue" (including blocked-tool feedback) loops again
        except asyncio.CancelledError:
            # Command handler already transitioned the agent and emitted
            # agent.cancelled after host.cancel().
            raise
        except Exception as exc:  # pipeline crash becomes a durable failure
            logger.exception("agent %s pipeline failed", agent.id)
            if agent.state is AgentState.RUNNING:
                core.agent_host.finish_run(agent, outcome="failed", error=str(exc))
        finally:
            # Flush the tail events (message_emitted, finish_run's
            # state_changed/run.finished, or a crashed turn's partial events)
            # so SSE clients and the store see the complete run lifecycle.
            try:
                await self._publish_new_events(cursor)
            except Exception:
                logger.exception("agent %s final event flush failed", agent.id)

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

    @staticmethod
    def _append_history(history: list[dict], inbox_messages: list[dict], outcome) -> None:
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
                    "content": result.summary,
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
    ) -> None:
        from cloudra.runtime_v2.compaction import compact_history, summarize_with_agent_settings

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
            },
        )
        handoff_path: str | None = None
        try:
            new_history, stats = await compact_history(
                history,
                keep_recent,
                lambda messages: summarize_with_agent_settings(agent, messages),
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
                handoff_path = await self._persist_compaction_handoff(
                    agent, stats, str(history[0].get("content") or "")
                )
                if handoff_path:
                    history[0]["content"] = str(history[0].get("content") or "") + (
                        f"\n\n(The full compaction summary was appended to the "
                        f"workspace file: {handoff_path})"
                    )
        finished: dict = dict(stats)
        finished["trigger"] = trigger
        if handoff_path:
            finished["handoff_path"] = handoff_path
        core.event_log.append(
            "compaction.finished",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data=finished,
        )

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

    async def _publish_new_events(self, before: int) -> None:
        for event in list(self.core.event_log)[before:]:
            await self.core.event_hub.publish(event)
