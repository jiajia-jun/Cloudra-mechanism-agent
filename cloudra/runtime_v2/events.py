"""Append-only event log and in-process event hub.

Rules:
- Every command accepted by the runtime must have appended an event *before*
  in-memory state changes.
- Event writers never know their readers; SSE and policy observers subscribe to
  the hub.
- The log keeps project-level ``seq`` and per-agent ``session_seq`` monotonic.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Iterable

from cloudra.runtime_v2.schemas import EventEnvelope

logger = logging.getLogger(__name__)

# Allowed event types -> short contract description.  Unknown types are rejected
# in test mode (CLOUDRA_STRICT_EVENTS=1) and always rejected in strict=True.
EVENT_TYPES: dict[str, str] = {
    # control events
    "project.created": "project established",
    "project.updated": "project name/workspace/archive changed",
    "project.settings_changed": "project defaults changed",
    "project.deleted": "project hard-deleted (tombstone; support data cleaned)",
    "role.updated": "role profile changed",
    "agent.spawn_requested": "spawn accepted",
    "agent.spawned": "agent session created",
    "agent.spawn_rejected": "spawn rejected",
    "agent.settings_changed": "runtime settings changed",
    "agent.message_injected": "user or peer message delivered",
    "agent.message_emitted": "assistant final message produced",
    "agent.cancel_requested": "cancel accepted",
    "agent.cancelled": "cancel completed, subprocesses reaped",
    "agent.restart_requested": "restart accepted",
    "agent.restarted": "new run started",
    "agent.context_reset": "session context reset by explicit restart command",
    "approval.requested": "approval waiting",
    "approval.decided": "approval decided",
    "approval.expired": "approval expired without a decision (process restart)",
    "interaction.requested": "ask_user waiting",
    "interaction.responded": "ask_user answered",
    "interaction.expired": "ask_user expired without a response (process restart)",
    "command.rejected": "command rejected with stable error code",
    # agent run events
    "agent.state_changed": "state machine transition",
    "run.started": "run started",
    "run.retry": "crashed turn auto-retried with preserved history",
    "run.finished": "run finished",
    "agent.completion_gate": "unified run-end gate verdict (explicit stop and plain-text final reply alike)",
    "llm.request_started": "llm request config snapshot",
    "llm.chunk": "streaming delta",
    "llm.completed": "llm request completed",
    "llm.failed": "llm request failed",
    "agent.thinking": "persisted reasoning segment of one LLM call",
    "tool.requested": "tool call requested (durable before any policy/tool effect)",
    "tool.started": "tool admitted by policy; executor about to run",
    "tool.result_recorded": "raw tool result durably recorded before postprocessing",
    "tool.blocked": "tool blocked by a policy stage",
    "tool.finished": "tool finished",
    "tool.approval_requested": "tool approval requested",
    "program.submitted": "js program source submitted (durable before launch)",
    "program.started": "js host handshook; program about to start",
    "program.output": "explicit js program output (text value)",
    "program.finished": "js program finished with child call receipts",
    "dag.gate_blocked": "substantive gate blocked a tool",
    "hub.posted": "agent forum post",
    "hub.notification_consumed": "agent consumed a directed hub notification",
    "compaction.started": "context compaction started",
    "compaction.finished": "context compaction finished",
    "compaction.requested": "manual context compaction requested",
    "reminder.scheduled": "agent self-wake reminder created",
    "reminder.cancelled": "agent self-wake reminder cancelled",
    "reminder.fired": "agent self-wake reminder delivered",
    "email.received": "inbound email delivered to a session by the listener",
    "loop.detected": "identical tool loop detected",
    "agent.warning": "non-fatal guard warning",
    "context.run_summarized": "historical: per-run trajectory summary (removed with the auto finalize pipeline in Task 4)",
    "context.handover_updated": "historical: per-run handover snapshot (removed with the auto finalize pipeline in Task 4)",
    "context.pin_set": "resident context notice pinned or replaced",
    "context.pin_cleared": "resident context notice unpinned",
    "context.injected": "one-shot context notice injected",
    "context.prefix_installed": "session context prefix installed (static protocol + initial dynamic snapshots)",
    "context.appended": "messages appended to the session LLM context (input before send, output after response)",
    "context.compacted": "session context atomically replaced by a compacted candidate",
    "project.synced": "sse replay backlog boundary (hub-only control marker)",
}


class UnknownEventType(ValueError):
    pass


class EventLog:
    def __init__(self, *, strict: bool = False) -> None:
        self.strict = strict
        self._events: list[EventEnvelope] = []
        self._by_id: dict[str, EventEnvelope] = {}
        self._project_seqs: dict[str, int] = defaultdict(int)
        self._session_seqs: dict[str, int] = defaultdict(int)

    def append(
        self,
        type: str,
        *,
        stream: str,
        project_id: str,
        data: dict[str, Any] | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> EventEnvelope:
        if type not in EVENT_TYPES:
            if self.strict:
                raise UnknownEventType(type)
            # Unknown types are allowed for forward evolution, but never silent:
            # strict mode and tests catch typos.
            logger.warning("unregistered event type %s", type)
        self._project_seqs[project_id] += 1
        session_seq = None
        if session_id is not None:
            self._session_seqs[session_id] += 1
            session_seq = self._session_seqs[session_id]
        envelope = EventEnvelope(
            stream=stream,
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            seq=self._project_seqs[project_id],
            session_seq=session_seq,
            type=type,
            data=data or {},
        )
        self._events.append(envelope)
        self._by_id[envelope.event_id] = envelope
        return envelope

    def get(self, event_id: str) -> EventEnvelope | None:
        return self._by_id.get(event_id)

    def __iter__(self):
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)

    @property
    def high_watermarks(self) -> dict[str, int]:
        """每项目的 seq 高水位。seq 是 per-project 计数，快照水位必须逐项目
        记录——单个全局 max 会让快照后他项目 seq ≤ max 的新事件被增量重放
        永久漏掉（3b 修复的丢事件 bug）。"""
        return dict(self._project_seqs)

    def watermarks_for_prefix(self, count: int) -> dict[str, int]:
        """前 ``count`` 条事件的 per-project seq 水位（已落盘前缀用）。"""
        marks: dict[str, int] = {}
        for envelope in self._events[: max(0, count)]:
            current = marks.get(envelope.project_id, 0)
            if envelope.seq > current:
                marks[envelope.project_id] = envelope.seq
        return marks

    def restore(self, envelopes: list[EventEnvelope]) -> None:
        """Replay persisted envelopes without generating new seq numbers."""
        for envelope in envelopes:
            self._events.append(envelope)
            self._by_id[envelope.event_id] = envelope
            self._project_seqs[envelope.project_id] = max(
                self._project_seqs[envelope.project_id], envelope.seq
            )
            if envelope.session_id is not None and envelope.session_seq is not None:
                self._session_seqs[envelope.session_id] = max(
                    self._session_seqs[envelope.session_id], envelope.session_seq
                )

    def discard_tail(self, keep: int) -> None:
        """Drop unpersisted events and rewind seq watermarks to the kept prefix.

        ``keep`` is the number of envelopes to retain (the EventWriter persist
        cursor).  Callers must not discard events that have already been
        applied; CommandBus only uses this on persist-before-apply failure.
        """
        if keep < 0:
            raise ValueError("keep must be >= 0")
        if keep >= len(self._events):
            return
        dropped = self._events[keep:]
        self._events = self._events[:keep]
        for envelope in dropped:
            self._by_id.pop(envelope.event_id, None)
        self._project_seqs.clear()
        self._session_seqs.clear()
        for envelope in self._events:
            self._project_seqs[envelope.project_id] = max(
                self._project_seqs[envelope.project_id], envelope.seq
            )
            if envelope.session_id is not None and envelope.session_seq is not None:
                self._session_seqs[envelope.session_id] = max(
                    self._session_seqs[envelope.session_id], envelope.session_seq
                )

    def query_project(
        self,
        project_id: str,
        *,
        after_seq: int = 0,
        types: Iterable[str] | None = None,
        limit: int | None = 500,
        tail: bool = True,
    ) -> list[EventEnvelope]:
        wanted = frozenset(types) if types is not None else None
        matched = [
            event
            for event in self._events
            if event.project_id == project_id
            and event.seq > after_seq
            and (wanted is None or event.type in wanted)
        ]
        if limit is None:
            return matched
        return matched[-limit:] if tail else matched[:limit]

    def query_session(
        self,
        session_id: str,
        *,
        after_session_seq: int = 0,
        before_session_seq: int | None = None,
        types: Iterable[str] | None = None,
        limit: int = 500,
        tail: bool = True,
    ) -> list[EventEnvelope]:
        wanted = frozenset(types) if types is not None else None
        matched = [
            event
            for event in self._events
            if event.session_id == session_id
            and (event.session_seq or 0) > after_session_seq
            and (
                before_session_seq is None
                or (event.session_seq or 0) <= before_session_seq
            )
            and (wanted is None or event.type in wanted)
        ]
        # tail=True：最近 limit 条（默认，看最新；before_session_seq 是向后翻页游标）；
        # tail=False：从头分页（全量回放）
        return matched[-limit:] if tail else matched[:limit]


class EventHub:
    """Fan-out for in-process subscribers (SSE adapters, policy observers)."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[EventEnvelope], Awaitable[None]]] = []
        # Ephemeral idempotency window for persistent events: publication is
        # deduplicated by event_id so reentrant flushes (a subscriber that
        # submits commands) never double-deliver.  seq=0 streaming chunks
        # (llm.chunk / project.synced) are hub-only and never deduplicated.
        self._delivered_ids: set[str] = set()

    def subscribe(self, handler: Callable[[EventEnvelope], Awaitable[None]]) -> Callable:
        self._subscribers.append(handler)
        return handler

    def unsubscribe(self, handler: Callable[[EventEnvelope], Awaitable[None]]) -> None:
        if handler in self._subscribers:
            self._subscribers.remove(handler)

    def mark_delivered(self, event_id: str) -> None:
        """Record an event as already published (restore backfill)."""
        self._delivered_ids.add(event_id)

    async def publish(self, envelope: EventEnvelope) -> None:
        if envelope.seq != 0:
            if envelope.event_id in self._delivered_ids:
                return
            # Mark before callbacks: a subscriber re-entering the hub through
            # a nested command must not re-deliver this envelope.
            self._delivered_ids.add(envelope.event_id)
        for handler in list(self._subscribers):
            try:
                await handler(envelope)
            except Exception:
                # Observers must never break the command pipeline.  The hub is
                # fire-and-forget broadcast; failing subscribers are logged by
                # the API/SSE layer through its own diagnostics later.
                logger.exception("event subscriber failed for %s", envelope.type)
