"""Durable evidence must outlive the bounded resident event cache."""

from __future__ import annotations

import asyncio
import gc
import tracemalloc
import weakref

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.events import EventHub
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core


@pytest.mark.asyncio
async def test_durable_payload_cache_has_count_and_byte_bounds(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    first_id = None
    for index in range(600):
        event = await core.event_writer.commit(EventDraft(
            "tool.result_recorded", "agent", "p", "a", None,
            {"result": {"content": f"{index}:" + "x" * 32768}},
        ))
        first_id = first_id or event.event_id
    assert len(core.event_log) == 600
    assert len(core.event_log._events) <= 512
    assert sum(len(e.data["result"]["content"]) for e in core.event_log._events) <= 8 * 1024 * 1024
    old = await asyncio.to_thread(core.event_log.get, first_id)
    assert old is not None and old.data["result"]["content"].startswith("0:")
    page = await asyncio.to_thread(core.event_log.query_session, "a", limit=3, tail=False)
    assert [e.session_seq for e in page] == [1, 2, 3]
    tail = await asyncio.to_thread(core.event_log.query_project, "p", after_seq=598)
    assert [e.seq for e in tail] == [599, 600]


@pytest.mark.asyncio
async def test_oversized_durable_output_is_not_retained(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    event = await core.event_writer.commit(EventDraft(
        "tool.result_recorded", "agent", "p", "a", None,
        {"result": {"content": "x" * (9 * 1024 * 1024)}},
    ))
    event_id = event.event_id
    reference = weakref.ref(event)
    del event
    gc.collect()
    assert reference() is None
    historical = await asyncio.to_thread(core.event_log.get, event_id)
    assert historical is not None
    assert len(historical.data["result"]["content"]) == 9 * 1024 * 1024


@pytest.mark.asyncio
async def test_restart_reads_old_history_without_full_materialization(tmp_path):
    class StreamingOnlyStore(RuntimeStore):
        def events_after(self, last_seqs):
            raise AssertionError("restore must stream rather than materialize all events")

    store = StreamingOnlyStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    first_id = None
    for index in range(600):
        event = await core.event_writer.commit(EventDraft(
            "agent.thinking", "agent", f"p{index % 2}", f"a{index % 2}", None,
            {"content": f"{index}:" + "x" * 16384},
        ))
        first_id = first_id or event.event_id
    restored = RuntimeCore(strict_events=True)
    restored.store = store
    await asyncio.to_thread(restore_core, restored, store)
    assert len(restored.event_log) == 600
    assert len(restored.event_log._events) <= 512
    assert (await asyncio.to_thread(restored.event_log.get, first_id)).seq == 1
    for project in range(2):
        event = await restored.event_writer.commit(EventDraft(
            "agent.thinking", "agent", f"p{project}", f"a{project}", None,
            {"content": "after restart"},
        ))
        assert event.seq == 301 and event.session_seq == 301
    assert len(restored.event_log) == 602
    assert restored.event_writer.persisted_watermarks() == {"p0": 301, "p1": 301}


@pytest.mark.asyncio
async def test_hub_deduplication_is_bounded_and_keeps_inflight_reentry():
    from cloudra.runtime_v2.events import EventLog

    log, hub = EventLog(strict=True), EventHub()
    first = log.append("agent.thinking", stream="agent", project_id="p", data={})
    seen = []

    async def nested(event):
        seen.append(event.event_id)
        if event.event_id == first.event_id:
            for _ in range(1500):
                other = log.append("agent.thinking", stream="agent", project_id="p", data={})
                await hub.publish(other)
            await hub.publish(first)

    hub.subscribe(nested)
    await hub.publish(first)
    assert seen.count(first.event_id) == 1
    assert len(seen) == 1501
    assert len(hub._delivered_ids) <= 1024


def test_recovery_releases_completed_raw_results():
    from cloudra.runtime_v2.persistence import plan_interrupted_invocations
    from cloudra.runtime_v2.schemas import EventEnvelope

    def completed_calls():
        for index in range(160):
            request = f"request-{index}"
            for kind, data in (
                ("tool.requested", {"tool_call_id": str(index), "tool_name": "read"}),
                ("tool.result_recorded", {"tool_call_id": str(index), "request_event_id": request,
                                          "result": {"content": f"{index}:" + "x" * 131072}}),
                ("tool.finished", {"tool_call_id": str(index), "request_event_id": request,
                                   "status": "completed", "effect_state": "completed"}),
            ):
                yield EventEnvelope(stream="agent", project_id="p", session_id="a", run_id="run",
                                    event_id=request if kind == "tool.requested" else f"{kind}-{index}",
                                    seq=index * 3 + 1, type=kind, data=data)

    tracemalloc.start()
    try:
        assert plan_interrupted_invocations(completed_calls()) == []
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 3 * 1024 * 1024, "completed raw evidence must not be accumulated by recovery"


@pytest.mark.asyncio
async def test_eviction_preserves_lost_ack_and_failure_rollback(tmp_path):
    class UncertainStore(RuntimeStore):
        def append_event(self, event):
            if event.type == "agent.warning":
                raise RuntimeError("disk full")
            super().append_event(event)
            if event.data.get("lost_ack"):
                raise RuntimeError("acknowledgement lost")

    core = RuntimeCore(strict_events=True)
    core.store = UncertainStore(tmp_path / "runtime.db")
    seen = []

    async def published(event):
        seen.append(event.event_id)

    core.event_hub.subscribe(published)
    for index in range(530):
        await core.event_writer.commit(EventDraft(
            "agent.thinking", "agent", f"p{index % 2}", f"a{index % 2}", None,
            {"content": str(index)},
        ))
    durable = await core.event_writer.commit(EventDraft(
        "agent.thinking", "agent", "p0", "a0", None,
        {"content": "x" * (9 * 1024 * 1024), "lost_ack": True},
    ))
    assert durable.seq == 266 and seen.count(durable.event_id) == 1
    with pytest.raises(RuntimeError, match="persistence failed"):
        await core.event_writer.commit(EventDraft("agent.warning", "agent", "p0", "a0", None, {}))
    assert len(core.event_log) == 531
    assert core.event_writer.persisted_watermarks() == {"p0": 266, "p1": 265}
    next_event = await core.event_writer.commit(EventDraft("agent.thinking", "agent", "p0", "a0", None, {}))
    assert next_event.seq == 267 and next_event.session_seq == 267
    assert len(seen) == 532


@pytest.mark.asyncio
async def test_disk_history_iteration_can_resume_on_another_worker_thread(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from itertools import islice

    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    for index in range(130):
        await core.event_writer.commit(EventDraft("agent.thinking", "agent", "p", "a", None, {"index": index}))
    history = core.event_log.iter_project("p")
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as first, ThreadPoolExecutor(max_workers=1) as second:
        page1 = await loop.run_in_executor(first, lambda: list(islice(history, 50)))
        page2 = await loop.run_in_executor(second, lambda: list(islice(history, 80)))
    assert [e.seq for e in page1 + page2] == list(range(1, 131))


@pytest.fixture
def cached_history(tmp_path, monkeypatch):
    from cloudra.runtime_v2.events import EventLog

    store = RuntimeStore(tmp_path / "cached-runtime.db")
    log = EventLog(strict=True)
    log.attach_store(store)
    log._max_cached_events = 4
    events = []
    for index in range(8):
        event = log.append(
            "agent.thinking" if index % 3 == 0 else "agent.warning",
            stream="agent", project_id=f"p{index % 2}",
            session_id=f"a{index % 2}", run_id="old" if index < 4 else "new",
            data={"index": index},
        )
        store.append_event(event)
        log.mark_persisted(index + 1, event)
        events.append(event)
    reads = []
    original = store.iter_events

    def read(**filters):
        reads.append(filters)
        yield from original(**filters)

    monkeypatch.setattr(store, "iter_events", read)
    return log, store, events, reads


@pytest.mark.parametrize("reader", ["project", "session", "iter_project", "iter_all"])
def test_recent_filtered_history_uses_cache_without_storage(cached_history, reader):
    log, _, _, reads = cached_history
    if reader == "project":
        result = log.query_project("p0", after_seq=2, limit=None)
    elif reader == "session":
        result = log.query_session("a0", after_session_seq=2, run_id="new", limit=None)
    elif reader == "iter_project":
        result = list(log.iter_project("p0", after_seq=2))
    else:
        result = list(log.iter_events(after_seq=2))
    assert [event.data["index"] for event in result] == ([4, 5, 6, 7] if reader == "iter_all" else [4, 6])
    assert reads == [], "resident durable payloads must not be read again from storage"


@pytest.mark.parametrize("scope", ["project", "session"])
def test_tail_limit_satisfied_by_cache_never_reads_storage(cached_history, scope):
    log, _, _, reads = cached_history
    result = log.query_project("p0", limit=2) if scope == "project" else log.query_session("a0", limit=2)
    assert [event.data["index"] for event in result] == [4, 6]
    assert reads == []


@pytest.mark.parametrize("scope", ["project", "session", "iter_all"])
def test_cache_boundary_reads_only_missing_older_prefix(cached_history, scope):
    log, _, _, reads = cached_history
    if scope == "project":
        result = log.query_project("p0", limit=3)
    elif scope == "session":
        result = log.query_session("a0", limit=3)
    else:
        result = list(log.iter_events())
    assert [event.data["index"] for event in result] == (list(range(8)) if scope == "iter_all" else [2, 4, 6])
    assert len(reads) == 1
    if scope == "iter_all":
        assert reads[0]["stop_index"] == 4
    else:
        assert reads[0]["limit"] == 1, "only one older result is missing from the cached tail"
        boundary = "before_seq" if scope == "project" else "before_session_seq"
        assert reads[0][boundary] == 2


def test_cache_merge_keeps_head_order_and_all_filters(cached_history):
    log, _, _, _ = cached_history
    head = log.query_project("p0", limit=3, tail=False)
    assert [event.data["index"] for event in head] == [0, 2, 4]
    filtered = log.query_session("a0", run_id="new", types=["agent.warning"], before_session_seq=3)
    assert [event.data["index"] for event in filtered] == [4]
    assert [event.data["index"] for event in log.iter_project("p1", before_seq=3, types=["agent.warning"])] == [1, 5]


def test_restored_cache_and_rollback_keep_interleaved_boundaries(cached_history):
    from cloudra.runtime_v2.events import EventLog

    _, store, _, reads = cached_history
    restored = EventLog(strict=True)
    restored._max_cached_events = 4
    restored.restore_from_store(store)
    reads.clear()
    dropped = restored.append("agent.warning", stream="agent", project_id="p0", session_id="a0")
    restored.discard_tail(8)
    kept = restored.append("agent.warning", stream="agent", project_id="p1", session_id="a1")
    result = restored.query_project("p1", after_seq=2, limit=None)
    assert [event.seq for event in result] == [3, 4, 5]
    assert result[-1].event_id == kept.event_id
    assert dropped.event_id not in {event.event_id for event in restored.iter_events(after_seq=2)}
    assert reads == []


def test_iteration_snapshot_survives_persist_eviction_without_holding_lock(cached_history, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    log, store, events, _ = cached_history
    pending = log.append("agent.warning", stream="agent", project_id="p0", session_id="a0")
    original = store.iter_events

    def persist_during_read(**filters):
        store.append_event(pending)
        log.mark_persisted(9, pending)
        log.append("agent.warning", stream="agent", project_id="p1", session_id="a1")
        yield from original(**filters)

    monkeypatch.setattr(store, "iter_events", persist_during_read)
    history = log.iter_events()
    first = next(history)
    with ThreadPoolExecutor(max_workers=1) as worker:
        # If iteration retained the log lock across yield, the worker would block.
        assert worker.submit(log.get, events[-1].event_id).result(timeout=2) is not None
    result = [first, *history]
    assert [event.event_id for event in result] == [event.event_id for event in events] + [pending.event_id]


@pytest.mark.parametrize("session_id,after_seq,expected", [("fresh", 0, [8]), ("a0", 2, [4, 6])])
def test_recent_session_iterator_skips_absent_older_prefix(cached_history, session_id, after_seq, expected):
    log, _, _, reads = cached_history
    log.append("agent.warning", stream="agent", project_id="p2", session_id="fresh", data={"index": 8})
    result = list(log.iter_events(session_id=session_id, after_seq=after_seq))
    assert [event.data["index"] for event in result] == expected
    assert reads == []


def test_cached_iterator_does_not_prefetch_a_long_unpersisted_tail(cached_history):
    class CountingList(list):
        visits = 0

        def __iter__(self):
            for event in super().__iter__():
                self.visits += 1
                yield event

    log, _, _, reads = cached_history
    for index in range(1201):
        log.append("agent.warning", stream="agent", project_id="p0", data={"index": index + 8})
    counted = CountingList(log._events)
    log._events = counted
    history = log.iter_events(after_seq=2)
    first = next(history)
    assert first.data["index"] == 4
    assert counted.visits <= 500, "the first page must not walk the pending backlog"
    result = [first, *history]
    assert [event.data["index"] for event in result] == list(range(4, 1209))
    assert counted.visits == 1205, "the fixed resident suffix must be scanned only once"
    assert reads == []
