"""Background completion checks must not block the event loop on durable history."""

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentState
from tests.test_api_v2_history_threads import guard_history_reads
from tests.test_benchmark_watch import _core_with_agents, _set, _terminal, _watcher
from tests.test_dag_exit_approval import _controller


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["succeeded", "waiting_approval"])
async def test_benchmark_completion_reads_history_in_worker(tmp_path, monkeypatch, state):
    core, _, agent, sibling = await _core_with_agents(tmp_path)
    await _terminal(core, sibling, AgentState.CANCELLED, "cancel")
    await _set(core, agent, AgentState.RUNNING, "run_started")
    await _set(core, agent, AgentState(state), "allow_final" if state == "succeeded" else "wait_review")
    guard_history_reads(core.event_log, monkeypatch)
    decision = await _watcher().decide(core, agent)
    assert decision.kind == ("done" if state == "succeeded" else "cancel")
    await core.aclose()


@pytest.mark.asyncio
async def test_user_stop_audit_reads_authoritative_event_in_worker(tmp_path, monkeypatch):
    controller = await _controller(tmp_path, "stop-history-thread", "dag_record")
    core = RuntimeCore(strict_events=True)
    controller._core = core
    stop = core.event_log.append(
        "agent.cancel_requested", stream="agent", project_id="stop-history-thread",
        session_id="s1", data={"actor": "user"},
    )
    guard_history_reads(core.event_log, monkeypatch)
    gate = await controller.audit_stop("user_terminated", user_stop_event_id=stop.event_id)
    assert gate.action == "allow_final"
    await core.aclose()
