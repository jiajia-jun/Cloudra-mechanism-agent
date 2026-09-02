"""AgentRunner: one async task per running AgentSession.

The runner owns the loop around TurnPipeline.  Commands only mutate state or
deliver inbox messages; execution concurrency lives here.

易失状态（3e）：``history``（本 run 的 LLM 对话原文）与 ``_tasks`` 都是
**刻意易失**的——对话原文不跨 run、不跨进程；跨 run 连续性由 context
tree（handover + run 摘要）与 goal/DAG/memory/工作区的外化状态承载，
重启恢复靠事件投影重建后由新消息驱动。
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
        run_summarizer: RunSummarizer | None = None,
    ) -> None:
        self.core = core
        self.pipeline = pipeline
        self.max_turn_retries = max_turn_retries
        self.retry_backoff = retry_backoff
        self.run_summarizer = run_summarizer
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
                await self._append_history(agent, history, inbox_messages, outcome)
                if outcome.decision == "stop":
                    # Primary cadence: one stop → one compact of the agent
                    # tail after the last user/schedule message.  400 overflow
                    # compact (above) is a mid-run fallback, not a substitute.
                    await self._apply_compaction(
                        agent, run_id, history, keep_recent=0, trigger="stop"
                    )
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
                    break
                # "continue" (including blocked-tool feedback) loops again
        except asyncio.CancelledError:
            # Command handler already transitioned the agent and emitted
            # agent.cancelled after host.cancel().  Still record the partial
            # trajectory in the context tree (deterministic summary only).
            self._schedule_run_finalize(agent, run_id, history, seed_count, outcome="cancelled")
            raise
        except Exception as exc:  # pipeline crash becomes a durable failure
            logger.exception("agent %s pipeline failed", agent.id)
            if agent.state is AgentState.RUNNING:
                core.agent_host.finish_run(agent, outcome="failed", error=str(exc))
            self._schedule_run_finalize(agent, run_id, history, seed_count, outcome="failed")
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

        A result carrying ``image_path`` is re-injected as an image_url part
        when visual mode is on and the model can see; otherwise the summary
        text gains one English fallback line pointing at the file.
        """
        summary = result.summary
        data = result.data if isinstance(result.data, dict) else {}
        image_path = data.get("image_path")
        if not image_path or not isinstance(image_path, str):
            return summary
        if not getattr(agent.settings, "visual_mode", True):
            return summary
        if not self._provider_supports_vision(agent):
            return (summary or "") + (
                f"\n[Image rendered at: {image_path} — the configured model has no "
                "vision support; inspect the file directly if needed.]"
            )
        part = await self._image_part(image_path)
        if part is None:
            return summary
        return [{"type": "text", "text": summary or ""}, part]

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
        handoff_text = ""
        try:
            new_history, stats = await compact_history(
                history,
                keep_recent,
                lambda messages: summarize_with_agent_settings(agent, messages),
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
        """
        asyncio.create_task(
            self._finalize_run_context(agent, run_id, history, seed_count, outcome=outcome),
            name=f"finalize:{agent.id}",
        )

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
            envelope = core.event_log.append(
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
            # Detached from the runner task, so publish directly — nobody else
            # will flush these events to SSE subscribers.
            await core.event_hub.publish(envelope)
            if new_handover:
                envelope = core.event_log.append(
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
                await core.event_hub.publish(envelope)
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
        for event in list(self.core.event_log)[before:]:
            await self.core.event_hub.publish(event)
