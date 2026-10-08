"""Historical reads can hit SQLite and must leave the API event loop free."""

import asyncio
from functools import wraps

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentSession, Project
from cloudra.services.api_v2 import create_v2_app


def guard_history_reads(log, monkeypatch):
    def check_thread():
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise AssertionError("historical storage read ran on the API event loop")

    for name in ("get", "query_session", "query_project"):
        original = getattr(log, name)

        def guarded(*args, _original=original, **kwargs):
            check_thread()
            return _original(*args, **kwargs)

        monkeypatch.setattr(log, name, wraps(original)(guarded))
    for name in ("iter_events", "iter_project"):
        original = getattr(log, name)

        def guarded_iterator(*args, _original=original, **kwargs):
            check_thread()
            yield from _original(*args, **kwargs)

        monkeypatch.setattr(log, name, wraps(original)(guarded_iterator))


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [
    "/api/v2/agents/a",
    "/api/v2/agents/a/transcript",
    "/api/v2/agents/a/events",
    "/api/v2/agents/a/events/{event_id}",
    "/api/v2/agents/a/tool-calls",
    "/api/v2/projects/p/agents",
    "/api/v2/projects/p/activity",
    "/api/v2/projects/p/approvals",
    "/api/v2/projects/p/interactions",
    "/api/v2/projects/p/reminders/pending",
])
async def test_api_history_reads_run_in_workers(endpoint, monkeypatch):
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="history")
    core.agents["a"] = AgentSession(
        id="a", project_id="p", role_id="explorer", display_name="reader", state="succeeded"
    )
    event = core.event_log.append(
        "agent.message_emitted", stream="agent", project_id="p", session_id="a",
        data={"content": "historical evidence"},
    )
    guard_history_reads(core.event_log, monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver"
    ) as client:
        response = await client.get(endpoint.format(event_id=event.event_id))
    assert response.status_code == 200
    if endpoint.endswith("/events"):
        assert response.json()[0]["data"]["content"] == "historical evidence"
    elif "{event_id}" in endpoint:
        assert response.json()["event_id"] == event.event_id
    await core.aclose()


@pytest.mark.asyncio
async def test_command_agent_response_reads_completion_in_worker(monkeypatch):
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="history")
    core.agents["a"] = AgentSession(
        id="a", project_id="p", role_id="explorer", display_name="reader", state="succeeded"
    )
    guard_history_reads(core.event_log, monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver"
    ) as client:
        response = await client.patch("/api/v2/agents/a/settings", json={"temperature": 0.3})
    assert response.status_code == 200
    assert response.json()["data"]["id"] == "a"
    await core.aclose()
