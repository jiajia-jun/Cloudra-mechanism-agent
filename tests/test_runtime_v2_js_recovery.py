"""Restore-time closure of interrupted tool/program lifecycles (pure scan)."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import (
    RuntimeStore,
    plan_interrupted_invocations,
    restore_core,
)
from cloudra.runtime_v2.schemas import Command


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
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
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
    run_id = "run_1"
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
    for envelope in core.event_log:
        store.append_event(envelope)
    return store, core, agent


@pytest.mark.asyncio
async def test_restore_closes_interrupted_lifecycles(tmp_path):
    store, _, agent = await _seed(tmp_path)
    core2 = RuntimeCore(strict_events=True)
    restore_core(core2, store)

    finished = [e for e in core2.event_log if e.type == "tool.finished"]
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

    programs = [e for e in core2.event_log if e.type == "program.finished"]
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
    types = [e.type for e in core2.event_log]
    assert types.count("tool.started") == 2
    assert types.count("program.submitted") == 1
    assert types.count("program.started") == 1

    # The recovered terminals are durable too.
    persisted_types = [e["type"] for e in store.query_project_events(agent.project_id)]
    assert persisted_types.count("tool.finished") == 4
    assert persisted_types.count("program.finished") == 1


@pytest.mark.asyncio
async def test_repeated_restore_adds_no_duplicate_terminals(tmp_path):
    store, _, agent = await _seed(tmp_path)
    core2 = RuntimeCore(strict_events=True)
    restore_core(core2, store)
    count_after_first = len(list(core2.event_log))

    core3 = RuntimeCore(strict_events=True)
    restore_core(core3, store)
    assert len(list(core3.event_log)) == count_after_first
    persisted_types = [e["type"] for e in store.query_project_events(agent.project_id)]
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
