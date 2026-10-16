"""Polling views read the selected session/run instead of project history."""

import pytest

from tests.test_api_v2_observability import client_for, emit, request, setup_core


@pytest.mark.asyncio
async def test_tool_call_list_and_detail_never_scan_project(monkeypatch):
    core = setup_core()
    wanted = request(core)
    emit(core, "tool.finished", {"tool_call_id": "same", "status": "completed"})

    def reject(*args, **kwargs):
        raise AssertionError("tool receipts must not scan project history")

    monkeypatch.setattr(core.event_log, "iter_project", reject)
    async with client_for(core) as client:
        page = await client.get("/api/v2/agents/a/tool-calls", params={"limit": 1})
        assert page.status_code == 200
        assert page.json()["items"][0]["request_event_id"] == wanted.event_id
        detail = await client.get(f"/api/v2/agents/a/tool-calls/{wanted.event_id}")
        assert detail.status_code == 200
        assert detail.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_activity_reads_only_current_run_and_constant_tails(monkeypatch):
    core = setup_core()
    for index in range(10):
        request(core, call=f"old-{index}", run=f"past-{index}")
    wanted = request(core, call="current")
    queries = []
    original = core.event_log.query_session

    def query(session_id, **filters):
        queries.append(filters)
        assert filters.get("limit") is not None or filters.get("run_id") == "r"
        return original(session_id, **filters)

    def reject(*args, **kwargs):
        raise AssertionError("activity must not scan project history")

    monkeypatch.setattr(core.event_log, "iter_project", reject)
    monkeypatch.setattr(core.event_log, "query_session", query)
    async with client_for(core) as client:
        response = await client.get("/api/v2/projects/p/activity")
        assert response.status_code == 200
        a = response.json()["agents"][0]
        assert [row["request_event_id"] for row in a["active_calls"]] == [wanted.event_id]
    assert queries


@pytest.mark.asyncio
async def test_historical_detail_stops_at_its_finished_attempt(monkeypatch):
    core = setup_core()
    wanted = request(core)
    emit(core, "tool.finished", {"tool_call_id": "same", "status": "completed"})
    for index in range(600):
        request(core, call=f"later-{index}")
    original = core.event_log.query_session
    queries = []

    def query(session_id, **filters):
        if filters.get("run_id") == "r" and "tool.started" in filters.get("types", ()):
            assert filters.get("limit") == 500
            assert filters.get("tail") is False
            queries.append(filters)
        return original(session_id, **filters)

    monkeypatch.setattr(core.event_log, "query_session", query)
    async with client_for(core) as client:
        response = await client.get(f"/api/v2/agents/a/tool-calls/{wanted.event_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
    assert len(queries) == 1
