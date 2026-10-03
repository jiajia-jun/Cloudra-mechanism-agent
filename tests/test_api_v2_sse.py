from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.events import EventLog
from cloudra.services.api_v2.sse import _sse_replay


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("count", "cursor", "expected_queries"),
    [
        (0, 0, [0]),
        (1, 0, [0]),
        (500, 0, [0, 500]),
        (501, 0, [0, 500]),
        (1000, 0, [0, 500, 1000]),
        (1201, 0, [0, 500, 1000]),
        (1201, 200, [200, 700, 1200]),
        (1201, 1201, [1201]),
        (0, 42, [42]),
    ],
)
async def test_sse_replay_reads_bounded_pages(count, cursor, expected_queries, monkeypatch):
    log = EventLog(strict=True)
    for index in range(count):
        log.append(
            "agent.warning",
            stream="agent",
            project_id="project-1",
            session_id="session-1",
            data={"index": index},
        )

    calls: list[int] = []
    original = asyncio.to_thread
    page_cursor = cursor

    async def consume_page(func):
        nonlocal page_cursor
        calls.append(page_cursor)
        events = await original(func)
        assert len(events) <= 500
        if events:
            page_cursor = events[-1].seq
        return events

    monkeypatch.setattr(asyncio, "to_thread", consume_page)
    core = SimpleNamespace(event_log=log)
    project = SimpleNamespace(id="project-1")

    chunks = [chunk async for chunk in _sse_replay(core, project, cursor=cursor)]

    envelopes = [json.loads(chunk.split("data: ", 1)[1]) for chunk in chunks]
    events, synced = envelopes[:-1], envelopes[-1]
    assert [event["seq"] for event in events] == list(range(cursor + 1, count + 1))
    assert [event["data"]["index"] for event in events] == list(range(cursor, count))
    assert synced["type"] == "project.synced"
    assert synced["seq"] == 0
    assert synced["data"]["replayed_through"] == max(cursor, count)
    assert calls == expected_queries


@pytest.mark.asyncio
async def test_sse_replay_scans_once_and_does_not_prefetch_history():
    class CountingList(list):
        visits = 0

        def __iter__(self):
            for event in super().__iter__():
                self.visits += 1
                yield event

    log = EventLog(strict=True)
    for index in range(1201):
        log.append('agent.warning', stream='agent', project_id='project-1', data={'index': index})
    counted = CountingList(log._events)
    log._events = counted
    replay = _sse_replay(SimpleNamespace(event_log=log), SimpleNamespace(id='project-1'), 0)
    first = await anext(replay)
    assert json.loads(first.split('data: ', 1)[1])['seq'] == 1
    assert counted.visits <= 500, 'first page must not materialize the entire backlog'
    rest = [chunk async for chunk in replay]
    assert len(rest) == 1201  # 1200 events plus the synced marker
    assert counted.visits == 1201, 'history must be scanned once, not once per page'


@pytest.mark.asyncio
async def test_sse_replay_keeps_initial_boundary_with_interleaved_projects():
    log = EventLog(strict=True)
    for _ in range(501):
        log.append('agent.warning', stream='agent', project_id='other')
        log.append('agent.warning', stream='agent', project_id='project-1')
    replay = _sse_replay(SimpleNamespace(event_log=log), SimpleNamespace(id='project-1'), 0)
    first = await anext(replay)
    log.append('agent.warning', stream='agent', project_id='project-1')
    envelopes = [json.loads(chunk.split('data: ', 1)[1]) for chunk in [first, *[c async for c in replay]]]
    assert [e['seq'] for e in envelopes[:-1]] == list(range(1, 502))
    assert all(e['project_id'] == 'project-1' for e in envelopes)
    assert envelopes[-1]['data']['replayed_through'] == 501
