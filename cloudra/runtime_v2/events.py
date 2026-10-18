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
import sys
import threading
from collections import OrderedDict, defaultdict, deque
from itertools import islice
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
    "agent.task_updated": "agent running task description updated",
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
    "tool.progress": "executor-reported phase, normalized inputs and explicit job/wait links",
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
    "launch_group.created": "swarm launch group declared (items + concurrency cap)",
    "launch_group.item_dispatched": "launch group item dispatched to a child session",
    "launch_group.item_finished": "launch group item reached a terminal state",
    "launch_group.finished": "launch group reached a terminal state (finished/cancelled/interrupted)",
    "context.run_summarized": "historical: per-run trajectory summary (removed with the auto finalize pipeline in Task 4)",
    "context.handover_updated": "historical: per-run handover snapshot (removed with the auto finalize pipeline in Task 4)",
    "context.pin_set": "resident context notice pinned or replaced",
    "context.pin_cleared": "resident context notice unpinned",
    "context.injected": "one-shot context notice injected",
    "context.prefix_installed": "session context prefix installed (static protocol + initial dynamic snapshots)",
    "context.appended": "messages appended to the session LLM context (input before send, output after response)",
    "context.compacted": "session context atomically replaced by a compacted candidate",
    'tool_documents.selection_started': 'initial tool document selection started durably',
    'tool_documents.selection_finished': 'initial selection outcome and document messages recorded',
    "project.synced": "sse replay backlog boundary (hub-only control marker)",
}


class UnknownEventType(ValueError):
    pass


def event_size_bytes(envelope: EventEnvelope) -> int:
    """Estimate retained envelope memory without serializing large payloads."""
    seen: set[int] = set()

    def size(value) -> int:
        if id(value) in seen:
            return 0
        seen.add(id(value))
        total = sys.getsizeof(value)
        if isinstance(value, dict):
            total += sum(size(k) + size(v) for k, v in value.items())
        elif isinstance(value, (list, tuple)):
            total += sum(size(item) for item in value)
        return total

    return sys.getsizeof(envelope) + size(envelope.__dict__)


class EventLog:
    def __init__(self, *, strict: bool = False) -> None:
        self.strict = strict
        self._events: list[EventEnvelope] = []
        self._by_id: dict[str, EventEnvelope] = {}
        self._project_seqs: dict[str, int] = defaultdict(int)
        self._session_seqs: dict[str, int] = defaultdict(int)
        self._store = None
        self._base_index = 0
        self._count = 0
        self._durable_count = 0
        self._durable_projects: dict[str, int] = {}
        self._durable_sessions: dict[str, int] = {}
        self._sizes: deque[int] = deque()
        self._cached_bytes = 0
        self._lock = threading.RLock()
        # Engineering cache limits, independent of chemistry or LLM budgets.
        self._max_cached_events = 512
        self._max_cached_bytes = 8 * 1024 * 1024

    def attach_store(self, store) -> None:
        """Attach complete durable history; this does not load or replay it."""
        if callable(getattr(store, "iter_events", None)):
            self._store = store

    def _retain(self, envelope: EventEnvelope) -> None:
        self._events.append(envelope)
        self._by_id[envelope.event_id] = envelope
        size = event_size_bytes(envelope)
        self._sizes.append(size)
        self._cached_bytes += size

    def _prune(self) -> None:
        if self._store is None:
            return  # Memory-only embedders have no other authority.
        remove = 0
        while (
            len(self._events) - remove > self._max_cached_events
            or self._cached_bytes > self._max_cached_bytes
        ) and self._base_index + remove < self._durable_count:
            event = self._events[remove]
            self._by_id.pop(event.event_id, None)
            self._cached_bytes -= self._sizes.popleft()
            remove += 1
        if remove:
            # Readers retain the old list with a fixed length across yields.
            self._events = self._events[remove:]
            self._base_index += remove

    def mark_persisted(self, count: int, envelope: EventEnvelope) -> None:
        """Advance the durable prefix only after the store acknowledges it."""
        with self._lock:
            self._durable_count = count
            self._durable_projects[envelope.project_id] = envelope.seq
            if envelope.session_id is not None and envelope.session_seq is not None:
                self._durable_sessions[envelope.session_id] = envelope.session_seq
            self._prune()

    def durable_metadata(self) -> dict[str, Any]:
        """Freeze the existing durable counters alongside the state snapshot."""
        with self._lock:
            return {"count": self._durable_count, "projects": dict(self._durable_projects),
                    "sessions": dict(self._durable_sessions)}

    def restore_from_store(self, store) -> None:
        """Restore counters plus a finite payload cache, keeping history on disk."""
        self.attach_store(store)
        count, projects, sessions = store.event_metadata()
        with self._lock:
            self._events.clear()
            self._by_id.clear()
            self._sizes.clear()
            self._cached_bytes = 0
            self._count = self._durable_count = count
            self._project_seqs = defaultdict(int, projects)
            self._session_seqs = defaultdict(int, sessions)
            self._durable_projects = dict(projects)
            self._durable_sessions = dict(sessions)
            recent, size = [], 0
            for event in store.iter_events(limit=self._max_cached_events, tail=True):
                cost = event_size_bytes(event)
                if size + cost > self._max_cached_bytes:
                    break
                recent.append(event)
                size += cost
            recent.reverse()
            self._base_index = count - len(recent)
            for event in recent:
                self._retain(event)
            self._prune()

    def events_since(self, index: int, stop: int | None = None) -> list[EventEnvelope]:
        """Global append offsets, unaffected by resident-cache eviction.

        Synchronous: consume through ``asyncio.to_thread`` in async callers.
        The writer's normal path reads only its small resident pending tail.
        """
        with self._lock:
            stop = min(self._count, self._count if stop is None else stop)
            if index >= self._base_index:
                return self._events[max(0, index - self._base_index): max(0, stop - self._base_index)]
            store, durable = self._store, self._durable_count
            pending = self._events[max(0, durable - self._base_index): max(0, stop - self._base_index)]
        return store.read_events(start_index=max(0, index), stop_index=min(stop, durable)) + pending

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
        with self._lock:
            self._retain(envelope)
            self._count += 1
        return envelope

    def get(self, event_id: str) -> EventEnvelope | None:
        with self._lock:
            resident = self._by_id.get(event_id)
            store = self._store
        return resident if resident is not None or store is None else store.get_event(event_id)

    def __iter__(self):
        return self.iter_events()

    def __len__(self) -> int:
        return self._count

    @property
    def resident_start_index(self) -> int:
        """First append offset served without touching durable storage."""
        return self._base_index

    @property
    def high_watermarks(self) -> dict[str, int]:
        """每项目的 seq 高水位。seq 是 per-project 计数，快照水位必须逐项目
        记录——单个全局 max 会让快照后他项目 seq ≤ max 的新事件被增量重放
        永久漏掉（3b 修复的丢事件 bug）。"""
        return dict(self._project_seqs)

    @property
    def high_session_watermarks(self) -> dict[str, int]:
        return dict(self._session_seqs)

    def watermarks_for_prefix(self, count: int) -> dict[str, int]:
        """前 ``count`` 条事件的 per-project seq 水位（已落盘前缀用）。"""
        if count == self._durable_count:
            return dict(self._durable_projects)
        marks: dict[str, int] = {}
        for envelope in self.events_since(0, max(0, count)):
            current = marks.get(envelope.project_id, 0)
            if envelope.seq > current:
                marks[envelope.project_id] = envelope.seq
        return marks

    def restore(self, envelopes: list[EventEnvelope]) -> None:
        """Replay persisted envelopes without generating new seq numbers."""
        for envelope in envelopes:
            self._retain(envelope)
            self._count += 1
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
        if keep >= self._count:
            return
        if keep < self._durable_count:
            raise ValueError("cannot discard durable events")
        local_keep = keep - self._base_index
        dropped = self._events[local_keep:]
        self._events = self._events[:local_keep]
        while len(self._sizes) > local_keep:
            self._cached_bytes -= self._sizes.pop()
        self._count = keep
        for envelope in dropped:
            self._by_id.pop(envelope.event_id, None)
        self._project_seqs = defaultdict(int, self._durable_projects)
        self._session_seqs = defaultdict(int, self._durable_sessions)
        for envelope in self._events[max(0, self._durable_count - self._base_index):]:
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
        return self._query(project_id=project_id, after_seq=after_seq, types=types, limit=limit, tail=tail)

    def query_session(
        self,
        session_id: str,
        *,
        run_id: str | None = None,
        after_session_seq: int = 0,
        before_session_seq: int | None = None,
        types: Iterable[str] | None = None,
        limit: int | None = 500,
        tail: bool = True,
    ) -> list[EventEnvelope]:
        return self._query(session_id=session_id, run_id=run_id, after_session_seq=after_session_seq,
                           before_session_seq=before_session_seq, types=types, limit=limit, tail=tail)

    def known_file_sha256(self, project_id: str, session_id: str,
                           relative_path: str, absolute_path: str) -> str | None:
        """A session's last known file version survives context compaction."""
        if self._store is not None:
            return self._store.known_file_sha256(project_id, session_id, relative_path, absolute_path)
        with self._lock:
            for event in reversed(self._events):
                if event.project_id != project_id:
                    continue
                if event.type == 'project.updated' and 'workspace_dir' in event.data.get('changes', {}):
                    return None
                if event.session_id != session_id or event.type != 'tool.result_recorded':
                    continue
                result = event.data.get('result') or {}
                data = result.get('data') or {}
                if result.get('is_success') is not True:
                    continue
                name = event.data.get('tool_name')
                if name == 'read' and data.get('kind') == 'text':
                    path, digest = data.get('path'), data.get('sha256')
                elif name in ('write', 'edit') and data.get('status') == 'applied':
                    path, digest = data.get('filepath'), data.get('after_sha256')
                else:
                    continue
                if path in (relative_path, absolute_path):
                    return digest
        return None

    def _read_snapshot(self, filters):
        """Pin a lazy resident suffix and bound only the older, uncached prefix."""
        with self._lock:
            store = self._store
            resident = islice(iter(self._events), len(self._events))
            if store is None or self._base_index == 0:
                return store, None, resident
            cached_durable = self._events[:self._durable_count - self._base_index]
            older = dict(filters)
            session_id = filters.get("session_id")
            project_id = filters.get("project_id")
            if project_id is None and filters.get("after_seq", 0):
                boundaries = dict(self._durable_projects)
                for event in cached_durable:
                    if event.project_id in boundaries:
                        boundaries[event.project_id] = min(boundaries[event.project_id], event.seq - 1)
                if max(boundaries.values(), default=0) <= filters["after_seq"]:
                    return store, None, resident
            if session_id is not None:
                boundary = self._durable_sessions.get(session_id, 0)
                for event in cached_durable:
                    if event.session_id == session_id and event.session_seq is not None:
                        boundary = min(boundary, event.session_seq - 1)
                        break
                before = filters.get("before_session_seq")
                boundary = min(boundary, before) if before is not None else boundary
                if boundary <= max(0, filters.get("after_session_seq", 0)):
                    return store, None, resident
                # Session sequences pin the prefix without a global row OFFSET.
                older["before_session_seq"] = boundary
            elif project_id is not None:
                boundary = self._durable_projects.get(project_id, 0)
                for event in cached_durable:
                    if event.project_id == project_id:
                        boundary = min(boundary, event.seq - 1)
                        break
                before = filters.get("before_seq")
                boundary = min(boundary, before) if before is not None else boundary
                if boundary <= filters.get("after_seq", 0):
                    return store, None, resident
                older["before_seq"] = boundary
            else:
                boundaries = dict(self._durable_projects)
                for event in cached_durable:
                    boundaries[event.project_id] = min(boundaries[event.project_id], event.seq - 1)
                older["before_seqs"] = boundaries
        return store, older, resident

    def _query(self, *, limit, tail, **filters) -> list[EventEnvelope]:
        wanted = filters.get("types")
        filters["types"] = frozenset(wanted) if wanted is not None else None
        store, older, resident = self._read_snapshot(filters)
        extra = [event for event in resident if self._matches(event, filters)]
        if tail and limit is not None and len(extra) >= limit:
            return extra[-limit:]
        durable = []
        if older is not None:
            missing = limit - len(extra) if tail and limit is not None else limit
            durable = store.read_events(limit=missing, tail=tail, **older)
        matched = durable + extra
        if limit is None:
            return matched
        return matched[-limit:] if tail else matched[:limit]

    @staticmethod
    def _matches(event, filters) -> bool:
        return (
            (filters.get("project_id") is None or event.project_id == filters["project_id"])
            and (filters.get("session_id") is None or event.session_id == filters["session_id"])
            and (filters.get("run_id") is None or event.run_id == filters["run_id"])
            and event.seq > filters.get("after_seq", 0)
            and (filters.get("before_seq") is None or event.seq <= filters["before_seq"])
            and (event.session_seq or 0) > filters.get("after_session_seq", -1)
            and (filters.get("before_session_seq") is None or (event.session_seq or 0) <= filters["before_session_seq"])
            and (filters.get("types") is None or event.type in filters["types"])
        )

    def iter_project(self, project_id: str, *, after_seq: int = 0,
                     before_seq: int | None = None, types=None):
        """Stream project evidence through a captured durable-prefix boundary."""
        return self.iter_events(project_id=project_id, after_seq=after_seq,
                                before_seq=before_seq, types=types)

    def iter_events(self, *, types=None, project_id=None, session_id=None,
                    after_seq=0, before_seq=None, after_session_seq=-1, before_session_seq=None):
        """Stream filtered evidence without decoding unrelated raw results."""
        filters = {"project_id": project_id, "session_id": session_id,
                   "after_seq": after_seq, "before_seq": before_seq,
                   "after_session_seq": after_session_seq, "before_session_seq": before_session_seq,
                   "types": frozenset(types) if types is not None else None}
        store, older, resident = self._read_snapshot(filters)
        if older is not None:
            yield from store.iter_events(**older)
        yield from (event for event in resident if self._matches(event, filters))


class EventHub:
    """Fan-out for in-process subscribers (SSE adapters, policy observers)."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[EventEnvelope], Awaitable[None]]] = []
        # Ephemeral idempotency window for persistent events: publication is
        # deduplicated by event_id so reentrant flushes (a subscriber that
        # submits commands) never double-deliver.  seq=0 streaming chunks
        # (llm.chunk / project.synced) are hub-only and never deduplicated.
        self._delivered_ids: OrderedDict[str, None] = OrderedDict()
        self._inflight: set[str] = set()
        self._restored_watermarks: dict[str, int] = {}

    def subscribe(self, handler: Callable[[EventEnvelope], Awaitable[None]]) -> Callable:
        self._subscribers.append(handler)
        return handler

    def unsubscribe(self, handler: Callable[[EventEnvelope], Awaitable[None]]) -> None:
        if handler in self._subscribers:
            self._subscribers.remove(handler)

    def mark_delivered(self, event_id: str) -> None:
        """Record an event as already published (restore backfill)."""
        self._delivered_ids[event_id] = None
        while len(self._delivered_ids) > 1024:
            self._delivered_ids.popitem(last=False)

    def mark_restored(self, watermarks: dict[str, int]) -> None:
        self._restored_watermarks = dict(watermarks)

    async def publish(self, envelope: EventEnvelope) -> None:
        if envelope.seq != 0:
            if (
                envelope.event_id in self._delivered_ids
                or envelope.event_id in self._inflight
                or envelope.seq <= self._restored_watermarks.get(envelope.project_id, 0)
            ):
                return
            # Mark before callbacks: a subscriber re-entering the hub through
            # a nested command must not re-deliver this envelope.
            self._inflight.add(envelope.event_id)
            self.mark_delivered(envelope.event_id)
        try:
            for handler in list(self._subscribers):
                try:
                    await handler(envelope)
                except Exception:
                    logger.exception("event subscriber failed for %s", envelope.type)
        finally:
            self._inflight.discard(envelope.event_id)
