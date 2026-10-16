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

The writer is deliberately ephemeral: cursors are global append offsets,
independent of resident-cache eviction. ``mark_restored`` follows restoration
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
        on_persisted: Callable[[EventEnvelope], None] | None = None,
    ) -> None:
        self._log = event_log
        self._hub = event_hub
        # Resolved lazily on every flush: the API attaches core.store after
        # core construction, so a fixed reference would miss the attachment.
        self._store_provider = store_provider
        self._on_persisted = on_persisted
        self._lock = asyncio.Lock()
        self._persisted = 0
        self._published = 0

    async def flush(self) -> None:
        """Persist the unflushed prefix in order, then publish unpublished events."""
        async with self._lock:
            unpublished = await self._flush_locked()
        await self._publish(unpublished)

    async def _flush_locked(self) -> list[EventEnvelope]:
        """Persist/capture the next publishable prefix while the writer lock is held."""
        store = self._store_provider() if self._store_provider is not None else None
        if store is not None:
            self._log.attach_store(store)
        start = min(self._persisted, self._published) if store is not None else self._published
        events = (
            self._log.events_since(start) if start >= self._log.resident_start_index
            else await asyncio.to_thread(self._log.events_since, start)
        )
        end = start + len(events)
        if store is not None:
            index = self._persisted
            while index < end:
                envelope = events[index - start]
                # An append can commit and still raise before the caller
                # receives its acknowledgement. Probe by the durable id
                # before treating that event as unpersisted.
                try:
                    await asyncio.to_thread(store.append_event, envelope)
                except Exception as exc:
                    probe = getattr(store, "has_event", None)
                    committed = False
                    if callable(probe):
                        try:
                            committed = await asyncio.to_thread(
                                probe, envelope.event_id
                            )
                        except Exception:
                            # Unknown durability must remain a failure.
                            pass
                    if not committed:
                        raise EventPersistenceError(
                            f"event persistence failed for {envelope.type}: {exc}"
                        ) from exc
                self._persisted = index + 1
                self._log.mark_persisted(index + 1, envelope)
                if self._on_persisted is not None:
                    self._on_persisted(envelope)
                index += 1
        unpublished = events[max(0, self._published - start):]
        if store is None and self._on_persisted is not None:
            for envelope in unpublished:
                self._on_persisted(envelope)
        # Mark before publishing: hub callbacks may re-enter flush, and
        # the hub dedupes by event_id, so this cannot double-deliver.
        self._published = end
        return unpublished

    async def _publish(self, events: list[EventEnvelope]) -> None:
        if self._hub is not None:
            for envelope in events:
                await self._hub.publish(envelope)

    async def commit_and_apply(
        self,
        drafts: list[EventDraft] | tuple[EventDraft, ...],
        apply: Callable[[EventEnvelope], None],
    ) -> None:
        """Append, persist and project one agent-state batch under the existing lock.

        Snapshots can share this lock without waiting on runner side effects.
        Hub callbacks run after projection and after releasing the writer lock.
        """
        error = None
        async with self._lock:
            keep = len(self._log)
            envelopes = [self._log.append(
                draft.type, stream=draft.stream, project_id=draft.project_id,
                session_id=draft.session_id, run_id=draft.run_id, data=draft.data,
            ) for draft in drafts]
            try:
                unpublished = await self._flush_locked()
            except EventPersistenceError as exc:
                self.discard_unpersisted(keep=keep)
                # Own drafts form a contiguous append range. Apply exactly its
                # durable prefix without querying evicted historical events.
                durable_count = min(len(envelopes), max(0, self._persisted - keep))
                if durable_count != len(envelopes):
                    error = exc
                envelopes = envelopes[:durable_count]
                unpublished = await self._persisted_unpublished_locked()
            for envelope in envelopes:
                apply(envelope)
        await self._publish(unpublished)
        if error is not None:
            raise error

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
            # flush may have persisted this draft, then failed on a later
            # concurrently appended event. The caller's commit succeeded;
            # publish its durable prefix and do not provoke a duplicate retry.
            if self._persisted <= before_append:
                raise
            await self.publish_persisted()
        return envelope

    async def _persisted_unpublished_locked(self) -> list[EventEnvelope]:
        unpublished = (
            self._log.events_since(self._published, self._persisted)
            if self._published >= self._log.resident_start_index
            else await asyncio.to_thread(self._log.events_since, self._published, self._persisted)
        )
        self._published = max(self._published, self._persisted)
        return unpublished

    async def publish_persisted(self) -> None:
        """Publish only the durable prefix after a failed flush, without retrying writes."""
        async with self._lock:
            unpublished = await self._persisted_unpublished_locked()
        await self._publish(unpublished)

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
            self._hub.mark_restored(self._log.high_watermarks)

    def mark_recovery_persisted(self) -> None:
        """Recovery writes are durable but remain available for live publication."""
        self._persisted = len(self._log)
