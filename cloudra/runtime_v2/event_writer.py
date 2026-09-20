"""Shared event writer: append -> ordered durable persistence -> publication.

One writer per RuntimeCore, shared by CommandBus, PendingBroker, the agent
runner and the invocation service.  It replaces ad-hoc publish/persist pairs
with a single write-ahead path:

- ``flush`` persists every not-yet-persisted log event **in log order** via
  the current RuntimeStore (when one is attached), then publishes every
  not-yet-published event to the hub.  Persisting the whole unflushed prefix
  means a durable event can never be restored without its project/run
  ancestors.
- A failing store write propagates to the caller *before* any hub
  publication or effect, so a consumer never observes an event that is not
  durable (EventHub's swallowed observer exceptions cannot be the
  persistence guarantee).
- The flush lock covers only the persistence/cursor critical section; hub
  callbacks run outside it, so a subscriber that submits commands re-enters
  the writer without deadlock.  Publication itself is idempotent by
  event_id inside EventHub (seq=0 streaming chunks excepted).
- Persistence and publication cursors are tracked separately: attaching a
  store after memory-only events backfills them without republishing.

The writer is deliberately ephemeral: cursors are process-local indices into
the in-memory log.  ``mark_restored`` is called right after restore backfill
to keep replayed history from being re-persisted/re-published.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.events import EventHub, EventLog
from cloudra.runtime_v2.schemas import EventEnvelope

if TYPE_CHECKING:
    from cloudra.runtime_v2.persistence import RuntimeStore


class EventPersistenceError(RuntimeError):
    """A store write failed mid-dispatch.

    Dedicated non-retryable type: AgentRunner must fail the run instead of
    retrying, because a retry could replay an effect that already happened
    on the other side of the unaudited gap.
    """


class EventWriter:
    def __init__(
        self,
        event_log: EventLog,
        event_hub: EventHub | None = None,
        store_provider: Callable[[], "RuntimeStore | None"] | None = None,
    ) -> None:
        self._log = event_log
        self._hub = event_hub
        # Resolved lazily on every flush: the API attaches core.store after
        # core construction, so a fixed reference would miss the attachment.
        self._store_provider = store_provider
        self._lock = asyncio.Lock()
        self._persisted = 0
        self._published = 0

    async def flush(self) -> None:
        """Persist the unflushed prefix in order, then publish unpublished events."""
        async with self._lock:
            events = list(self._log)
            store = self._store_provider() if self._store_provider is not None else None
            if store is not None:
                index = self._persisted
                while index < len(events):
                    # Advance only on success: a failure leaves the cursor at
                    # the last durable event and propagates to the caller.
                    try:
                        await asyncio.to_thread(store.append_event, events[index])
                    except Exception as exc:
                        raise EventPersistenceError(
                            f"event persistence failed for {events[index].type}: {exc}"
                        ) from exc
                    self._persisted = index + 1
                    index += 1
            unpublished = events[self._published :]
            # Mark before publishing: hub callbacks may re-enter flush, and
            # the hub dedupes by event_id, so this cannot double-deliver.
            self._published = len(events)
        if self._hub is not None:
            for envelope in unpublished:
                await self._hub.publish(envelope)

    async def commit(self, draft: EventDraft) -> EventEnvelope:
        """Append one draft to the log and durably flush; returns the envelope."""
        before_append = len(self._log)
        envelope = self._log.append(
            draft.type,
            stream=draft.stream,
            project_id=draft.project_id,
            session_id=draft.session_id,
            run_id=draft.run_id,
            data=draft.data,
        )
        try:
            await self.flush()
        except EventPersistenceError:
            self.discard_unpersisted(keep=before_append)
            raise
        return envelope

    def discard_unpersisted(self, keep: int | None = None) -> None:
        """Drop log events that never made it to the store.

        Persist-before-apply paths call this on ``EventPersistenceError`` so a
        later flush cannot durably write events that were never applied.
        If ``keep`` is provided, drop only events appended after ``keep``.
        """
        target = self._persisted if keep is None else max(self._persisted, keep)
        self._log.discard_tail(target)
        if self._published > target:
            self._published = target

    def persisted_watermarks(self) -> dict[str, int]:
        """Per-project seq high-water of events the writer has durably stored.

        Snapshot ``last_seqs`` must use this, not live ``EventLog.high_watermarks``:
        a concurrent append can raise the live marks before the new event is
        persisted, and restore would then skip it via ``events_after``.
        """
        return self._log.watermarks_for_prefix(self._persisted)

    def mark_restored(self) -> None:
        """Treat the current log as already persisted/published (post-backfill).

        Called immediately after restore backfill, before recovery events are
        appended, so replayed history is neither re-persisted nor re-published.
        """
        self._persisted = len(self._log)
        self._published = len(self._log)
        if self._hub is not None:
            for envelope in self._log:
                self._hub.mark_delivered(envelope.event_id)
