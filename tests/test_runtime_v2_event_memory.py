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
