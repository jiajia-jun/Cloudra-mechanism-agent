from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import ClientDisconnect, Request

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import Command, EventEnvelope
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.api_v2.context import ApiContext
from cloudra.services.api_v2.routers.events import build_router


async def _stream(core, project_id, cursor):
    async def receive():
        await asyncio.Event().wait()

    request = Request({"type": "http"}, receive=receive)
    route = build_router(ApiContext(core, CommandBus(core), [])).routes[0]
    return await route.endpoint(project_id, request, cursor)


def _decode(chunk):
    return json.loads(chunk.split("data: ", 1)[1])


@pytest.mark.asyncio
async def test_slow_project_stream_overflow_disconnects_without_blocking_publisher(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "slow"}))).data
    cursor = core.event_log.high_watermarks[project.id]
    response = await _stream(core, project.id, cursor)
    assert _decode(await anext(response.body_iterator))["type"] == "project.synced"

    async def publish_chunks():
        for _ in range(2000):
            await core.event_hub.publish(EventEnvelope(
                type="llm.chunk", stream="agent", project_id=project.id, seq=0,
                data={"kind": "content", "delta": "x" * 1024},
            ))

    try:
        await asyncio.wait_for(publish_chunks(), timeout=2)
        assert not core.event_hub._subscribers, "overflow must immediately release the subscriber"
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(response.body_iterator), timeout=1)
    finally:
        await response.body_iterator.aclose()
        await core.aclose()


@pytest.mark.asyncio
async def test_overflow_reconnect_replays_every_durable_event_from_client_cursor(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    project = (await CommandBus(core).execute(Command(
        type="project.create", payload={"name": "reconnect"},
    ))).data
    cursor = core.event_log.high_watermarks[project.id]
    response = await _stream(core, project.id, cursor)
    await anext(response.body_iterator)
    expected = []
    for index in range(300):
        event = await core.event_writer.commit(EventDraft(
            "agent.warning", stream="agent", project_id=project.id, data={"index": index},
        ))
        expected.append(event.event_id)
    try:
        assert not core.event_hub._subscribers
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(response.body_iterator), timeout=1)
        reconnected = await _stream(core, project.id, cursor)
        try:
            recovered = []
            while True:
                event = _decode(await asyncio.wait_for(anext(reconnected.body_iterator), timeout=1))
                if event["type"] == "project.synced":
                    assert event["data"]["replayed_through"] == cursor + 300
                    break
                recovered.append(event["event_id"])
            assert recovered == expected
        finally:
            await reconnected.body_iterator.aclose()
    finally:
        await response.body_iterator.aclose()
        await core.aclose()


@pytest.mark.asyncio
async def test_project_stream_pre_start_disconnect_does_not_retain_subscriber():
    core = RuntimeCore()
    project = (await CommandBus(core).execute(Command(
        type="project.create", payload={"name": "pre-start"},
    ))).data
    response = await _stream(core, project.id, 0)

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            raise OSError("client disconnected before response body")

    try:
        # ASGI 2.4 reports a dead connection through send(), before the body is entered.
        with pytest.raises(ClientDisconnect):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    finally:
        await response.body_iterator.aclose()
    assert not core.event_hub._subscribers
    await core.aclose()


@pytest.mark.asyncio
async def test_stream_byte_budget_disconnects_before_large_results_accumulate(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    project = (await CommandBus(core).execute(Command(
        type="project.create", payload={"name": "large-results"},
    ))).data
    cursor = core.event_log.high_watermarks[project.id]
    response = await _stream(core, project.id, cursor)
    await anext(response.body_iterator)
    try:
        for index in range(3):
            await core.event_writer.commit(EventDraft(
                "agent.warning", stream="agent", project_id=project.id,
                data={"content": str(index) + "x" * (4 * 1024 * 1024)},
            ))
        assert not core.event_hub._subscribers, "count bounds alone allow multi-gigabyte queues"
        with pytest.raises(StopAsyncIteration):
            await anext(response.body_iterator)
        # The full oversized data remains available from authoritative storage.
        restored = await asyncio.to_thread(core.event_log.query_project, project.id, types={"agent.warning"})
        assert [e.data["content"][0] for e in restored] == ["0", "1", "2"]
        assert all(len(e.data["content"]) == 4 * 1024 * 1024 + 1 for e in restored)
    finally:
        await response.body_iterator.aclose()
        await core.aclose()


@pytest.mark.asyncio
async def test_reentrant_publication_keeps_reconnect_cursor_gap_free(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    project = (await CommandBus(core).execute(Command(
        type="project.create", payload={"name": "reentrant"},
    ))).data
    cursor = core.event_log.high_watermarks[project.id]

    async def nested(event):
        if event.type == "agent.warning" and event.data.get("index") == 1:
            await core.event_writer.commit(EventDraft(
                "agent.warning", stream="agent", project_id=project.id, data={"index": 2},
            ))

    handler = core.event_hub.subscribe(nested)
    response = await _stream(core, project.id, cursor)
    await anext(response.body_iterator)
    try:
        outer = await core.event_writer.commit(EventDraft(
            "agent.warning", stream="agent", project_id=project.id, data={"index": 1},
        ))
        first = _decode(await anext(response.body_iterator))
        assert first["seq"] == outer.seq, "a higher cursor must not precede an unseen durable event"
        assert first["data"]["index"] == 1
        await response.body_iterator.aclose()
        reconnected = await _stream(core, project.id, first["seq"])
        try:
            recovered = _decode(await anext(reconnected.body_iterator))
            assert recovered["seq"] == first["seq"] + 1
            assert recovered["data"]["index"] == 2
        finally:
            await reconnected.body_iterator.aclose()
    finally:
        await response.body_iterator.aclose()
        core.event_hub.unsubscribe(handler)
        await core.aclose()


@pytest.mark.asyncio
async def test_project_stream_requires_explicit_incremental_cursor():
    core = RuntimeCore()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v2/projects/missing/stream")
            assert response.status_code == 422
            assert response.json()["detail"][0]["loc"] == ["query", "cursor"]
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_stream_does_not_advance_past_a_pending_event_that_can_be_rolled_back(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    project = (await CommandBus(core).execute(Command(
        type="project.create", payload={"name": "pending-tail"},
    ))).data
    cursor = core.event_log.high_watermarks[project.id]
    pending = core.event_log.append(
        "agent.warning", stream="project", project_id=project.id,
        data={"content": "not persisted"},
    )
    response = await _stream(core, project.id, cursor)
    try:
        first = _decode(await anext(response.body_iterator))
        assert first["type"] == "project.synced"
        assert first["data"]["replayed_through"] == cursor
        core.event_writer.discard_unpersisted()
        actual = await core.event_writer.commit(EventDraft(
            "agent.warning", stream="project", project_id=project.id,
            data={"content": "actual durable event"},
        ))
        assert actual.seq == pending.seq
        delivered = _decode(await asyncio.wait_for(anext(response.body_iterator), 1))
        assert delivered["event_id"] == actual.event_id
    finally:
        await response.body_iterator.aclose()
        await core.aclose()
