"""Lazy closure of interrupted tool/program lifecycles and pure planning."""

from __future__ import annotations

import asyncio
import contextlib
import threading

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import (
    RuntimeStore,
    plan_interrupted_invocations,
    restore_core,
)
from cloudra.runtime_v2.schemas import AgentState, Command


def test_recovery_keeps_reused_call_ids_in_distinct_attempts():
    from cloudra.runtime_v2.schemas import AgentSession

    core = RuntimeCore(strict_events=True)
    agent = AgentSession(id="a", project_id="p", role_id="explorer", display_name="a")
    first = _append(core, "tool.requested", agent, "run", {"tool_call_id": "same", "tool_name": "echo"})
    second = _append(core, "tool.requested", agent, "run", {"tool_call_id": "same", "tool_name": "echo"})
    raw = _append(core, "tool.result_recorded", agent, "run", {
        "tool_call_id": "same", "request_event_id": first.event_id, "result": {"data": 1},
    })
    another = _append(core, "tool.requested", agent, "next", {"tool_call_id": "same", "tool_name": "echo"})
    drafts = plan_interrupted_invocations(list(core.event_log))
    assert len(drafts) == 3
    by_request = {d.data["request_event_id"]: d.data for d in drafts}
    assert by_request[first.event_id]["effect_state"] == "completed"
    assert by_request[first.event_id]["raw_result_event_id"] == raw.event_id
    for req in (second, another):
        assert by_request[req.event_id]["effect_state"] == "not_started"
        assert by_request[req.event_id]["raw_result_event_id"] is None
    for draft in drafts:
        core.event_log.append(draft.type, stream=draft.stream, project_id=draft.project_id,
            session_id=draft.session_id, run_id=draft.run_id, data=draft.data)
    assert plan_interrupted_invocations(list(core.event_log)) == []


def _append(core: RuntimeCore, type_: str, agent, run_id: str, data: dict):
    return core.event_log.append(
        type_,
        stream="agent",
        project_id=agent.project_id,
        session_id=agent.id,
        run_id=run_id,
        data=data,
    )


async def _seed(tmp_path):
    """A core+store with one agent and a hand-built interrupted history."""
    store = await asyncio.to_thread(RuntimeStore, tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    await bus.execute(
        Command(
            type="agent.spawn", target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    agent = next(iter(core.agents.values()))
    run_id = await core.agent_host.start_run(agent)
    exec_id = "exec_1"
    # Child A: requested only -> not_started.
    # Child B: requested+started -> unknown.
    # Child C: requested+started+result_recorded -> completed (postprocessing cut).
    for suffix, stages in (("a", 1), ("b", 2), ("c", 3)):
        call_id = f"tc_{suffix}"
        _append(core, "tool.requested", agent, run_id, {
            "tool_call_id": call_id, "tool_name": "echo",
            "arguments_summary": {}, "execution_id": exec_id,
        })
        if stages >= 2:
            _append(core, "tool.started", agent, run_id, {
                "tool_call_id": call_id, "tool_name": "echo",
                "arguments_summary": {}, "execution_id": exec_id,
            })
        if stages >= 3:
            _append(core, "tool.result_recorded", agent, run_id, {
                "tool_call_id": call_id, "tool_name": "echo", "execution_id": exec_id,
                "result": {"is_success": True, "summary": "ok", "data": {}, "duration_ms": 1},
            })
    # A finished traditional call must not be touched.
    _append(core, "tool.requested", agent, run_id, {
        "tool_call_id": "tc_done", "tool_name": "echo",
        "arguments_summary": {}, "execution_id": None,
    })
    _append(core, "tool.finished", agent, run_id, {
        "tool_call_id": "tc_done", "tool_name": "echo", "execution_id": None,
        "status": "completed", "effect_state": "completed", "is_success": True,
        "result_summary": "ok", "duration_ms": 1, "raw_result_event_id": None, "error": None,
    })
    # The program itself: submitted+started, never finished.
    _append(core, "program.submitted", agent, run_id, {
        "execution_id": exec_id, "outer_tool_call_id": "wire_1",
        "code": "text(1);", "source_hash": "abc",
    })
    _append(core, "program.started", agent, run_id, {
        "execution_id": exec_id, "outer_tool_call_id": "wire_1",
    })
    await core.event_writer.flush()
    await bus.flush_snapshot()
    return store, core, agent


@pytest.mark.asyncio
@pytest.mark.parametrize("command_type", ["agent.message", "agent.restart"])
async def test_reopening_closes_only_interrupted_run(tmp_path, command_type):
    store, source, agent = await _seed(tmp_path)
    old_run = agent.current_run.run_id
    # Unfinished records from another run/session must remain untouched.
    unrelated = _append(source, "tool.requested", agent, "older_run", {
        "tool_call_id": "older", "tool_name": "echo",
    })
    other = agent.model_copy(update={"id": "other_session"})
    _append(source, "tool.requested", other, "other_run", {
        "tool_call_id": "other", "tool_name": "echo",
    })
    # Evict the actual requests from the resident cache and the 500-row tail.
    for i in range(520):
        _append(source, "tool.progress", agent, old_run, {"tool_call_id": "tc_b", "phase": str(i)})
    await source.event_writer.flush()
    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    await asyncio.to_thread(restore_core, core2, store)
    assert core2.agents[agent.id].state is AgentState.FAILED
    before = await asyncio.to_thread(core2.event_log.query_session, agent.id, limit=None)
    assert len([e for e in before if e.type == "tool.finished"]) == 1
    assert not [e for e in before if e.type == "program.finished"]

    queries = []
    read_events = store.read_events
    def tracked_read(**filters):
        queries.append((filters, threading.get_ident()))
        return read_events(**filters)
    store.read_events = tracked_read
    result = await CommandBus(core2).execute(Command(
        type=command_type, target={"session_id": agent.id},
        payload={"content": "continue"} if command_type == "agent.message" else {},
    ))
    assert result.accepted
    assert queries and all(thread_id != threading.get_ident() for _, thread_id in queries)
    lifecycle = [filters for filters, _ in queries if "tool.requested" in (filters.get("types") or ())]
    assert len(lifecycle) == 1
    assert lifecycle[0]["session_id"] == agent.id
    assert lifecycle[0]["run_id"] == old_run
    assert lifecycle[0]["limit"] is None
    assert "stop_index" not in lifecycle[0]  # no global OFFSET walk to find a session boundary

    events = await asyncio.to_thread(core2.event_log.query_session, agent.id, limit=None)
    finished = [e for e in events if e.type == "tool.finished"]
    by_call = {e.data["tool_call_id"]: e.data for e in finished}
    assert by_call["tc_a"]["status"] == "interrupted"
    assert by_call["tc_a"]["effect_state"] == "not_started"
    assert by_call["tc_a"]["raw_result_event_id"] is None
    assert by_call["tc_b"]["effect_state"] == "unknown"
    assert by_call["tc_c"]["effect_state"] == "completed"
    assert by_call["tc_c"]["raw_result_event_id"]  # retained raw-result reference
    assert by_call["tc_done"]["status"] == "completed"  # untouched original
    # Every recovered terminal carries the interruption error, never a success.
    for call_id in ("tc_a", "tc_b", "tc_c"):
        assert by_call[call_id]["is_success"] is False
        assert by_call[call_id]["error"]["code"] == "interrupted"

    programs = [e for e in events if e.type == "program.finished"]
    assert len(programs) == 1
    program = programs[0].data
    assert program["status"] == "interrupted"
    assert program["error"]["code"] == "interrupted"
    assert program["outer_tool_call_id"] == "wire_1"
    receipts = {r["call_id"]: r for r in program["calls"]}
    assert receipts["tc_a"]["effect_state"] == "not_started"
    assert receipts["tc_b"]["effect_state"] == "unknown"
    assert receipts["tc_c"]["effect_state"] == "completed"
    assert receipts["tc_c"]["raw_result_event_id"] == by_call["tc_c"]["raw_result_event_id"]

    # Recovery is facts-only: no new started/submitted rows, i.e. no executor,
    # no JS process and no scheduler job was invoked.
    types = [e.type for e in events]
    assert types.count("tool.started") == 2
    assert types.count("program.submitted") == 1
    assert types.count("program.started") == 1

    recovery = [e for e in events if e.type in {"tool.finished", "program.finished"} and e.data.get("status") == "interrupted"]
    assert all(e.run_id == old_run for e in recovery)
    assert recovery[-1].type == "program.finished"
    reopened = next(e for e in events if e.type == "agent.state_changed" and e.data.get("to") == "queued")
    assert recovery[-1].session_seq < reopened.session_seq
    assert not any(e.type == "tool.finished" and e.data.get("request_event_id") == unrelated.event_id for e in events)

    # The recovered terminals are durable too.
    persisted = await asyncio.to_thread(store.read_events, project_id=agent.project_id, limit=None)
    persisted_types = [e.type for e in persisted]
    assert persisted_types.count("tool.finished") == 4
    assert persisted_types.count("program.finished") == 1


@pytest.mark.asyncio
async def test_repeated_restore_and_reopening_add_no_duplicate_terminals(tmp_path):
    store, _, agent = await _seed(tmp_path)
    core2 = RuntimeCore(strict_events=True)
    core2.store = store
    await asyncio.to_thread(restore_core, core2, store)
    bus = CommandBus(core2)
    result = await bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "continue"}))
    assert result.accepted
    count_after_first = len(core2.event_log)

    core3 = RuntimeCore(strict_events=True)
    core3.store = store
    await asyncio.to_thread(restore_core, core3, store)
    # The reopened run itself becomes interrupted, with no unfinished tools.
    assert len(core3.event_log) == count_after_first + 2
    result = await CommandBus(core3).execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "continue again"}))
    assert result.accepted
    persisted = await asyncio.to_thread(store.read_events, project_id=agent.project_id, limit=None)
    persisted_types = [e.type for e in persisted]
    assert persisted_types.count("tool.finished") == 4
    assert persisted_types.count("program.finished") == 1


def test_planner_ignores_complete_history():
    core = RuntimeCore(strict_events=True)
    from cloudra.runtime_v2.schemas import AgentSession

    agent = AgentSession(id="a", project_id="p", role_id="explorer", display_name="explorer")
    _append(core, "program.submitted", agent, "r", {
        "execution_id": "e", "outer_tool_call_id": "w", "code": "x", "source_hash": "h",
    })
    _append(core, "program.finished", agent, "r", {
        "execution_id": "e", "outer_tool_call_id": "w", "status": "completed",
        "duration_ms": 1, "error": None, "calls": [],
    })
    assert plan_interrupted_invocations(list(core.event_log)) == []


@pytest.mark.asyncio
async def test_cold_restore_does_not_scan_global_lifecycles(tmp_path, monkeypatch):
    store, _, agent = await _seed(tmp_path)
    statements = []
    connect = store._connect
    @contextlib.contextmanager
    def traced_connect():
        with connect() as con:
            con.set_trace_callback(statements.append)
            yield con
    monkeypatch.setattr(store, "_connect", traced_connect)
    # Model a million durable records without creating irrelevant payloads.
    metadata = store.event_metadata
    def million_record_metadata():
        _, projects, sessions = metadata()
        return 1_000_000, projects, sessions
    monkeypatch.setattr(store, "event_metadata", million_record_metadata)
    restored = RuntimeCore(strict_events=True)
    await asyncio.to_thread(restore_core, restored, store)
    assert restored.agents[agent.id].state is AgentState.FAILED
    lifecycle_queries = [sql for sql in statements if "FROM events WHERE" in sql and "type IN" in sql and "'tool.requested'" in sql]
    assert lifecycle_queries == []
    rows = await asyncio.to_thread(store.query_project_events, agent.project_id)
    assert len([row for row in rows if row["type"] == "tool.finished"]) == 1
    assert not [row for row in rows if row["type"] == "program.finished"]


@pytest.mark.asyncio
async def test_live_and_parked_message_paths_do_not_query_recovery(tmp_path, monkeypatch):
    store, core, agent = await _seed(tmp_path)
    def unexpected_query(**filters):
        raise AssertionError(f"unexpected history query: {filters}")
    monkeypatch.setattr(store, "read_events", unexpected_query)
    bus = CommandBus(core)
    result = await bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "still running"}))
    assert result.accepted
    # Invalid restart retains state_conflict and cannot close live invocations.
    rejected = await bus.execute(Command(type="agent.restart", target={"session_id": agent.id}))
    assert not rejected.accepted
    assert rejected.data["error"]["code"] == "state_conflict"
    agent.state = AgentState.FAILED
    parked = await bus.execute(Command(type="agent.message", actor="system", target={"session_id": agent.id}, payload={"content": "notice"}))
    assert parked.accepted and agent.state is AgentState.FAILED
    invalid = await bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": ""}))
    assert not invalid.accepted


@pytest.mark.asyncio
async def test_recovery_persistence_failure_does_not_reopen_agent(tmp_path, monkeypatch):
    from cloudra.runtime_v2.event_writer import EventPersistenceError
    store, _, agent = await _seed(tmp_path)
    core = RuntimeCore(strict_events=True)
    core.store = store
    await asyncio.to_thread(restore_core, core, store)
    append = store.append_event
    def fail_recovery(event):
        if event.type == "tool.finished" and event.data.get("status") == "interrupted":
            raise OSError("disk unavailable")
        append(event)
    monkeypatch.setattr(store, "append_event", fail_recovery)
    command = Command(type="agent.message", target={"session_id": agent.id}, payload={"content": "continue"})
    bus = CommandBus(core)
    with pytest.raises(EventPersistenceError):
        await bus.execute(command)
    assert core.agents[agent.id].state is AgentState.FAILED
    assert core.agents[agent.id].current_run is None
    events = await asyncio.to_thread(core.event_log.query_session, agent.id, limit=None)
    assert not [e for e in events if e.type == "tool.finished" and e.data.get("status") == "interrupted"]
    monkeypatch.setattr(store, "append_event", append)
    assert (await bus.execute(command)).accepted


@pytest.mark.asyncio
async def test_concurrent_messages_recover_each_call_once(tmp_path):
    store, _, agent = await _seed(tmp_path)
    core = RuntimeCore(strict_events=True)
    core.store = store
    await asyncio.to_thread(restore_core, core, store)
    # A second process restart before reopening must retain the recovery scope.
    again = RuntimeCore(strict_events=True)
    again.store = store
    await asyncio.to_thread(restore_core, again, store)
    bus = CommandBus(again)
    results = await asyncio.gather(*(
        bus.execute(Command(type="agent.message", target={"session_id": agent.id}, payload={"content": message}))
        for message in ("continue", "more context")
    ))
    assert all(result.accepted for result in results)
    events = await asyncio.to_thread(again.event_log.query_session, agent.id, limit=None)
    interrupted = [e for e in events if e.type == "tool.finished" and e.data.get("status") == "interrupted"]
    assert len(interrupted) == 3
    assert len({e.data["request_event_id"] for e in interrupted}) == 3
    assert len([e for e in events if e.type == "program.finished"]) == 1
    assert len([e for e in events if e.type == "run.started"]) == 2


@pytest.mark.asyncio
async def test_reentrant_message_during_recovery_does_not_duplicate_calls_or_runs(tmp_path):
    store, _, agent = await _seed(tmp_path)
    core = RuntimeCore(strict_events=True)
    core.store = store
    await asyncio.to_thread(restore_core, core, store)
    bus = CommandBus(core)
    nested = []

    async def subscriber(event):
        if event.type == "tool.finished" and event.data.get("status") == "interrupted" and not nested:
            nested.append(None)
            nested[0] = await bus.execute(Command(
                type="agent.message", target={"session_id": agent.id},
                payload={"content": "extra context from subscriber"},
            ))

    core.event_hub.subscribe(subscriber)
    result = await bus.execute(Command(
        type="agent.message", target={"session_id": agent.id}, payload={"content": "continue"},
    ))
    assert result.accepted and nested[0].accepted
    events = await asyncio.to_thread(core.event_log.query_session, agent.id, limit=None)
    interrupted = [e for e in events if e.type == "tool.finished" and e.data.get("status") == "interrupted"]
    assert len(interrupted) == 3
    assert len({e.data["request_event_id"] for e in interrupted}) == 3
    assert len([e for e in events if e.type == "program.finished"]) == 1
    assert len([e for e in events if e.type == "run.started"]) == 2


@pytest.mark.asyncio
async def test_restore_finishes_run_when_previous_restore_failed_midway(tmp_path, monkeypatch):
    store, _, agent = await _seed(tmp_path)
    append = store.append_event

    def fail_run_terminal(event):
        if event.type == "run.finished":
            raise OSError("interrupted recovery write")
        append(event)

    monkeypatch.setattr(store, "append_event", fail_run_terminal)
    with pytest.raises(OSError):
        await asyncio.to_thread(restore_core, RuntimeCore(strict_events=True), store)
    monkeypatch.setattr(store, "append_event", append)
    core = RuntimeCore(strict_events=True)
    core.store = store
    await asyncio.to_thread(restore_core, core, store)
    assert core.agents[agent.id].state is AgentState.FAILED
    assert core.agents[agent.id].current_run is None
    result = await CommandBus(core).execute(Command(
        type="agent.message", target={"session_id": agent.id}, payload={"content": "continue"},
    ))
    assert result.accepted
    events = await asyncio.to_thread(core.event_log.query_session, agent.id, limit=None)
    assert len([e for e in events if e.type == "tool.finished" and e.data.get("status") == "interrupted"]) == 3
    assert len([e for e in events if e.type == "program.finished"]) == 1
