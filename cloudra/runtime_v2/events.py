"""Append-only event log and in-process event hub.

Rules:
- Every command accepted by the runtime must have appended an event *before*
  in-memory state changes.
- Event writers never know their readers; SSE and policy observers subscribe to
  the hub.
- The log keeps project-level ``seq`` and per-agent ``session_seq`` monotonic.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Awaitable, Callable, Iterable

from cloudra.runtime_v2.schemas import EventEnvelope

# Allowed event types -> short contract description.  Unknown types are rejected
# in test mode (CLOUDRA_STRICT_EVENTS=1) and always rejected in strict=True.
EVENT_TYPES: dict[str, str] = {
    # control events
    "project.created": "project established",
    "project.updated": "project name/workspace/archive changed",
    "project.settings_changed": "project defaults changed",
    "runtime.settings_changed": "global runtime defaults changed",
    "role.updated": "role profile changed",
    "agent.spawn_requested": "spawn accepted",
    "agent.spawned": "agent session created",
    "agent.spawn_rejected": "spawn rejected",
    "agent.settings_changed": "runtime settings changed",
    "agent.message_injected": "user or peer message delivered",
    "agent.cancel_requested": "cancel accepted",
    "agent.cancelled": "cancel completed, subprocesses reaped",
    "agent.restart_requested": "restart accepted",
    "agent.restarted": "new run started",
    "approval.requested": "approval waiting",
    "approval.decided": "approval decided",
    "interaction.requested": "ask_user waiting",
    "interaction.responded": "ask_user answered",
    "command.rejected": "command rejected with stable error code",
    # agent run events
    "agent.state_changed": "state machine transition",
    "run.started": "run started",
    "run.finished": "run finished",
    "llm.request_started": "llm request config snapshot",
    "llm.chunk": "streaming delta",
    "llm.completed": "llm request completed",
    "llm.retried": "llm transport retry",
    "llm.failed": "llm request failed",
    "tool.started": "tool started",
    "tool.blocked": "tool blocked by a policy stage",
    "tool.finished": "tool finished",
    "tool.approval_requested": "tool approval requested",
    "dag.mutation_proposed": "dag mutation proposed",
    "dag.mutation_accepted": "dag mutation accepted",
    "dag.mutation_rejected": "dag mutation rejected",
    "dag.evidence_bound": "evidence bound to graph element",
    "dag.gate_blocked": "substantive gate blocked a tool",
    "dag.supervisor_triggered": "supervisor woken by dag event",
    "compaction.started": "context compaction started",
    "compaction.finished": "context compaction finished",
    "loop.detected": "identical tool loop detected",
    "agent.warning": "non-fatal guard warning",
    "heartbeat": "sse keep-alive",
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
            import logging

            logging.getLogger("runtime_v2.events").warning("unregistered event type %s", type)
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
    def last_seq(self) -> int:
        return max(self._project_seqs.values(), default=0)

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

    def query_project(
        self,
        project_id: str,
        *,
        after_seq: int = 0,
        types: Iterable[str] | None = None,
        limit: int = 500,
    ) -> list[EventEnvelope]:
        wanted = frozenset(types) if types is not None else None
        return [
            event
            for event in self._events
            if event.project_id == project_id
            and event.seq > after_seq
            and (wanted is None or event.type in wanted)
        ][-limit:]

    def query_session(
        self,
        session_id: str,
        *,
        after_session_seq: int = 0,
        types: Iterable[str] | None = None,
        limit: int = 500,
    ) -> list[EventEnvelope]:
        wanted = frozenset(types) if types is not None else None
        return [
            event
            for event in self._events
            if event.session_id == session_id
            and (event.session_seq or 0) > after_session_seq
            and (wanted is None or event.type in wanted)
        ][-limit:]


class EventHub:
    """Fan-out for in-process subscribers (SSE adapters, policy observers)."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[EventEnvelope], Awaitable[None]]] = []

    def subscribe(self, handler: Callable[[EventEnvelope], Awaitable[None]]) -> Callable:
        self._subscribers.append(handler)
        return handler

    def unsubscribe(self, handler: Callable[[EventEnvelope], Awaitable[None]]) -> None:
        if handler in self._subscribers:
            self._subscribers.remove(handler)

    async def publish(self, envelope: EventEnvelope) -> None:
        for handler in list(self._subscribers):
            try:
                await handler(envelope)
            except Exception:
                # Observers must never break the command pipeline.  The hub is
                # fire-and-forget broadcast; failing subscribers are logged by
                # the API/SSE layer through its own diagnostics later.
                import logging

                logging.getLogger("runtime_v2.events").exception(
                    "event subscriber failed for %s", envelope.type
                )
