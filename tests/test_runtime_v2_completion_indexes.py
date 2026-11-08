"""Completion obligations survive cache eviction without retaining event history."""

from types import SimpleNamespace

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.peer_completion import PeerCompletionIndex
from cloudra.runtime_v2.schemas import AgentSession
from cloudra.runtime_v2.subagent_bridge import ChildCompletionIndex


def _core():
    parent = AgentSession(id="parent", project_id="p", role_id="coordinator", display_name="parent")
    child = AgentSession(
        id="child", project_id="p", role_id="explorer", display_name="child", parent_session_id=parent.id
    )
    peer = AgentSession(
        id="peer", project_id="p", role_id="researcher", display_name="peer", requested_by_session_id=parent.id
    )
    return SimpleNamespace(agents={a.id: a for a in (parent, child, peer)}, event_log=EventLog(strict=True))


def _event(core, kind, session="child", run="r1", **data):
    return core.event_log.append(kind, stream="agent", project_id="p", session_id=session, run_id=run, data=data)


def test_child_index_keeps_current_assignment_and_first_final_across_snapshot():
    core = _core()
    index = ChildCompletionIndex()
    parked = [
        _event(core, "agent.completion_gate", action="wait_background"),
        _event(core, "agent.state_changed", to="succeeded"),
    ]
    for event in parked:
        index.apply(event, core)
    assert index.terminal_by_session == {}
    final = _event(core, "agent.state_changed", run="r2", to="succeeded")
    index.apply(final, core)
    index.apply(_event(core, "agent.state_changed", run="r3", to="failed"), core)
    assert index.terminal_by_session["child"].event_id == final.event_id
    index.apply(
        _event(
            core,
            "agent.message_injected",
            session="parent",
            manifest={"kind": "child_completion", "session_id": "child", "terminal_event_id": final.event_id},
        ),
        core,
    )
    restored = ChildCompletionIndex()
    restored.restore(index.snapshot())
    assert restored.terminal_by_session["child"].event_id == final.event_id
    assert restored.reported_by_session == {"child": final.event_id}
    restored.apply(
        _event(
            core,
            "agent.message_injected",
            manifest={"kind": "task_assignment", "session_id": "child", "parent_session_id": "parent"},
        ),
        core,
    )
    assert restored.terminal_by_session == {}
    assert restored.reported_by_session == {}
    latest = _event(core, "agent.state_changed", run="r4", to="failed")
    restored.apply(latest, core)
    assert restored.terminal_by_session["child"].event_id == latest.event_id
    # Replaying an old event after the new assignment cannot resurrect it.
    restored.apply(final, core)
    assert restored.terminal_by_session["child"].event_id == latest.event_id
    restored.prune({"parent"})
    assert all(not value for key, value in restored.snapshot().items() if key != "watermarks")


def test_peer_index_freezes_first_final_and_dedup_across_snapshot():
    core = _core()
    index = PeerCompletionIndex()
    for event in [
        _event(core, "agent.completion_gate", session="peer", action="wait_background"),
        _event(core, "agent.state_changed", session="peer", to="succeeded"),
    ]:
        index.apply(event, core)
    assert index.terminal_by_session == {}
    message = _event(core, "agent.message_emitted", session="peer", run="r2", content="first result")
    final = _event(core, "agent.state_changed", session="peer", run="r2", to="failed")
    finished = _event(
        core, "run.finished", session="peer", run="r2", outcome="failed", failure_kind="provider_permanent"
    )
    for event in [
        message,
        final,
        finished,
        _event(core, "agent.message_emitted", session="peer", run="r3", content="later result"),
        _event(core, "agent.state_changed", session="peer", run="r3", to="succeeded"),
    ]:
        index.apply(event, core)
    restored = PeerCompletionIndex()
    restored.restore(index.snapshot())
    assert restored.terminal_by_session["peer"].event_id == final.event_id
    assert restored.final_message_by_session["peer"].data["content"] == "first result"
    assert restored.finished_by_run[("peer", "r2")].data["failure_kind"] == "provider_permanent"
    restored.apply(
        _event(
            core,
            "agent.message_injected",
            session="parent",
            manifest={"kind": "peer_call_completion", "session_id": "peer"},
        ),
        core,
    )
    assert ("parent", "peer") in restored.reported
    restored.prune({"parent"})
    assert all(not value for key, value in restored.snapshot().items() if key != "watermarks")


def test_indexes_keep_only_current_facts_for_many_parked_runs():
    core = _core()
    child, peer = ChildCompletionIndex(), PeerCompletionIndex()
    for n in range(1000):
        for session, index in [("child", child), ("peer", peer)]:
            for event in [
                _event(core, "run.started", session=session, run=str(n)),
                _event(core, "agent.message_emitted", session=session, run=str(n), content="working"),
                _event(core, "agent.completion_gate", session=session, run=str(n), action="wait_background"),
                _event(core, "agent.state_changed", session=session, run=str(n), to="succeeded"),
                _event(core, "run.finished", session=session, run=str(n), outcome="succeeded"),
            ]:
                index.apply(event, core)
    assert len(str(child.snapshot())) < 1000
    assert len(str(peer.snapshot())) < 2000


def test_agent_list_reuses_bounded_session_completion(monkeypatch):
    from cloudra.services.api_v2.views import agent_dict, agent_dicts

    core = _core()
    _event(core, "agent.completion_gate", action="finish", basis="scope_completed")
    _event(core, "run.finished", outcome="succeeded")
    expected = [agent_dict(core, a) for a in core.agents.values()]

    def scan_project(*args, **kwargs):
        raise AssertionError("Agent list must reuse the bounded session completion reader")

    monkeypatch.setattr(core.event_log, "query_project", scan_project)
    assert agent_dicts(core, core.agents.values()) == expected


def test_live_completion_reads_reuse_indexes_and_only_load_missing_child_report(monkeypatch):
    from cloudra.runtime_v2.peer_completion import build_peer_completion_index, peer_completion_message
    from cloudra.runtime_v2.subagent_bridge import (
        build_child_completion_index,
        child_completion_message,
        child_final_event,
    )

    core = _core()
    core.child_completions = ChildCompletionIndex()
    core.peer_completions = PeerCompletionIndex()
    for session in ("child", "peer"):
        for event in [
            _event(core, "run.started", session=session),
            _event(core, "agent.message_emitted", session=session, content="finished work"),
            _event(core, "agent.state_changed", session=session, to="succeeded"),
            _event(core, "run.finished", session=session, outcome="succeeded"),
        ]:
            core.child_completions.apply(event, core)
            core.peer_completions.apply(event, core)
    original_iter = core.event_log.iter_events
    requested_sessions = []

    def only_targeted_history(**filters):
        assert filters.get("session_id") == "child", "Completion reads must never scan global history"
        requested_sessions.append(filters["session_id"])
        return original_iter(**filters)

    monkeypatch.setattr(core.event_log, "iter_events", only_targeted_history)
    assert build_child_completion_index(core) is core.child_completions
    assert build_peer_completion_index(core) is core.peer_completions
    assert child_final_event(core, core.agents["child"]) is not None
    assert peer_completion_message(core, core.agents["peer"])[2]["final_summary"] == "finished work"
    assert requested_sessions == []
    report = child_completion_message(core, core.agents["child"])
    assert report[2]["final_summary"] == "finished work"
    assert requested_sessions == ["child"]
    core.child_completions.apply(_event(core, "agent.message_injected", session="parent", manifest=report[2]), core)
    assert child_completion_message(core, core.agents["child"]) is None
    assert requested_sessions == ["child"]


def test_completion_watermarks_are_per_project_after_snapshot():
    core = _core()
    child = core.agents["child"].model_copy(update={"id": "other-child", "project_id": "other"})
    peer = core.agents["peer"].model_copy(update={"id": "other-peer", "project_id": "other"})
    core.agents.update({child.id: child, peer.id: peer})
    indexes = [ChildCompletionIndex(), PeerCompletionIndex()]
    for _ in range(25):
        event = _event(core, "agent.message_emitted", content="working")
        for index in indexes:
            index.apply(event, core)
    for index, agent in zip(indexes, (child, peer)):
        resumed = type(index)()
        resumed.restore(index.snapshot())
        event = core.event_log.append(
            "agent.state_changed",
            stream="agent",
            project_id="other",
            session_id=agent.id,
            run_id="other-run",
            data={"to": "failed"},
        )
        resumed.apply(event, core)
        assert resumed.terminal_by_session[agent.id].event_id == event.event_id
