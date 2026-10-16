"""The initial project view is a bounded snapshot with a matching SSE cursor."""

from __future__ import annotations

import asyncio
import threading

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.completion import COMPLETION_EVENT_TYPES, COMPLETION_TAIL
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.api_v2.routers import projects as project_routes


async def _project_with_agent():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "view"}))).data
    agent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"},
    ))).data
    return core, project, agent


async def _finish(core, agent, basis):
    run_id = await core.agent_host.start_run(agent)
    core.record(
        "agent.completion_gate", stream="agent", project_id=agent.project_id,
        session_id=agent.id, run_id=run_id, data={"basis": basis},
    )
    await core.agent_host.finish_run(agent, outcome="succeeded")
    return run_id


@pytest.mark.asyncio
async def test_project_view_returns_current_agents_and_project_cursor():
    core, project, agent = await _project_with_agent()
    other = (await CommandBus(core).execute(Command(type="project.create", payload={"name": "other"}))).data
    for _ in range(10):
        core.record("agent.warning", stream="project", project_id=other.id, data={})
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver") as client:
        response = await client.get(f"/api/v2/projects/{project.id}/view")
    assert response.status_code == 200
    body = response.json()
    assert body["cursor"] == core.event_log.high_watermarks[project.id]
    assert [row["id"] for row in body["agents"]] == [agent.id]
    assert body["agents"][0]["completion"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", ["agent_host", "task_describer"])
async def test_project_snapshot_waits_for_appended_agent_projection(writer, monkeypatch):
    """A snapshot must not pair a new cursor with state from before that event."""
    core, project, agent = await _project_with_agent()
    entered = asyncio.Event()
    release = asyncio.Event()
    original_flush = core.event_writer._flush_locked

    async def paused_flush():
        entered.set()
        await release.wait()
        return await original_flush()

    monkeypatch.setattr(core.event_writer, "_flush_locked", paused_flush)
    if writer == "agent_host":
        update = asyncio.create_task(core.agent_host.start_run(agent))
    else:
        async def describe(*_args):
            return "Analyzing mechanism"
        monkeypatch.setattr("cloudra.runtime_v2.task_describer.generate_task_description", describe)
        update = asyncio.create_task(core.task_describer._process_task_update(agent, "Analyze", "en"))
    await asyncio.wait_for(entered.wait(), 2)
    assert core.event_log.high_watermarks[project.id] > 0

    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver") as client:
        pending = asyncio.create_task(client.get(f"/api/v2/projects/{project.id}/view"))
        await asyncio.sleep(0.01)
        try:
            assert not pending.done(), "snapshot skipped a pending state projection"
        finally:
            release.set()
            await update
            response = await pending
    assert response.status_code == 200
    body = response.json()
    assert body["cursor"] == core.event_log.high_watermarks[project.id]
    frozen = body["agents"][0]
    if writer == "agent_host":
        assert frozen["current_run"] is not None
    else:
        assert frozen["current_task"] == "Analyzing mechanism"


@pytest.mark.asyncio
async def test_project_view_freezes_agents_and_bounds_completion_to_captured_prefix(monkeypatch):
    core, project, agent = await _project_with_agent()
    first_run = await _finish(core, agent, "dag_verified")
    boundary = core.event_log.high_watermarks[project.id]
    session_boundary = core.event_log.high_session_watermarks[agent.id]
    frozen_updated_at = agent.model_dump(mode="json")["updated_at"]
    entered = threading.Event()
    release = threading.Event()
    original_query = core.event_log.query_session
    calls = []

    original_agent_dict = project_routes.agent_dict

    def paused_serialize(*args, **kwargs):
        entered.set()
        assert release.wait(5), "snapshot serialization was never released"
        return original_agent_dict(*args, **kwargs)

    def record_query(session_id, **kwargs):
        calls.append((session_id, kwargs, threading.get_ident()))
        return original_query(session_id, **kwargs)

    def no_project_history(*_args, **_kwargs):
        raise AssertionError("project view must not scan full project completion history")

    monkeypatch.setattr(project_routes, "agent_dict", paused_serialize)
    monkeypatch.setattr(core.event_log, "query_session", record_query)
    monkeypatch.setattr(core.event_log, "query_project", no_project_history)
    loop_thread = threading.get_ident()
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver") as client:
        request = asyncio.create_task(client.get(f"/api/v2/projects/{project.id}/view"))
        try:
            assert await asyncio.to_thread(entered.wait, 2), "view did not start snapshot serialization"
            # This must finish while completion is being read: the main write
            # lock is released after freezing the small in-memory snapshot.
            second_run = await asyncio.wait_for(_finish(core, agent, "scope_completed"), 2)
            assert second_run != first_run
        finally:
            release.set()
            response = await request
    assert response.status_code == 200
    body = response.json()
    assert body["cursor"] == boundary
    row = body["agents"][0]
    assert row["current_run"] is None
    assert row["updated_at"] == frozen_updated_at
    assert row["completion"]["run_id"] == first_run
    assert row["completion"]["verification_label"] == "verified"
    assert calls == [(agent.id, {
        "types": COMPLETION_EVENT_TYPES,
        "limit": COMPLETION_TAIL,
        "before_session_seq": session_boundary,
    }, calls[0][2])]
    assert calls[0][2] != loop_thread


@pytest.mark.asyncio
async def test_persisted_project_view_cursor_excludes_unflushed_tail(tmp_path):
    from cloudra.runtime_v2.persistence import RuntimeStore

    core, project, agent = await _project_with_agent()
    core.store = RuntimeStore(tmp_path / "runtime.db")
    await core.event_writer.flush()
    boundary = core.event_writer.persisted_watermarks()[project.id]
    pending = core.record(
        "agent.warning", stream="agent", project_id=project.id, session_id=agent.id,
        data={"message": "not persisted"},
    )
    assert pending.seq > boundary
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver") as client:
        response = await client.get(f"/api/v2/projects/{project.id}/view")
    assert response.status_code == 200
    assert response.json()["cursor"] == boundary
