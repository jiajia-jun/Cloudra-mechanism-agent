"""A Hub-created peer reports its first task without becoming a child."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.event_writer import EventPersistenceError
from cloudra.runtime_v2.failures import RunFailureKind
from cloudra.runtime_v2.peer_completion import deliver_peer_completion
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class _AnswerLLM:
    async def complete(self, agent, messages, tools, **_kwargs):
        return LLMResponse(content=f"{agent.role_id} answer", stop_requested=True)


async def _sessions(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "peers"}))).data
    requester = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "explorer"},
            )
        )
    ).data
    peer = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "researcher",
                    "requested_by_session_id": requester.id,
                    "query": "Research this question",
                },
            )
        )
    ).data
    return core, store, bus, requester, peer


@pytest.mark.asyncio
async def test_spawn_cannot_combine_peer_requester_with_child_parent(tmp_path):
    core, _store, bus, requester, _peer = await _sessions(tmp_path)
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": requester.project_id},
            payload={
                "role_id": "researcher",
                "parent_session_id": requester.id,
                "requested_by_session_id": requester.id,
            },
        )
    )
    assert result.accepted is False
    assert result.data["error"]["code"] == "invalid_request"
    assert not any(
        agent.parent_session_id == requester.id and agent.requested_by_session_id == requester.id
        for agent in core.agents.values()
    )


async def _finish(core, peer, *, text: str, outcome: str, failure_kind=None, gate_action=None):
    run_id = await core.agent_host.start_run_durable(peer)
    await core.event_writer.commit(
        EventDraft(
            "agent.message_emitted",
            stream="agent",
            project_id=peer.project_id,
            session_id=peer.id,
            run_id=run_id,
            data={"sender": peer.role_id, "content": text},
        )
    )
    if gate_action is not None:
        await core.event_writer.commit(
            EventDraft(
                "agent.completion_gate",
                stream="agent",
                project_id=peer.project_id,
                session_id=peer.id,
                run_id=run_id,
                data={"action": gate_action, "reason": "test gate", "source": "test"},
            )
        )
    await core.agent_host.finish_run_durable(
        peer, outcome=outcome, failure_kind=failure_kind,
        error="pipeline failed" if outcome == "failed" else None,
    )
    return run_id


def _reports(core, requester_id):
    return [
        event
        for event in core.event_log
        if event.session_id == requester_id and event.type == "agent.message_injected"
        if (event.data.get("manifest") or {}).get("kind") == "peer_call_completion"
    ]


@pytest.mark.asyncio
async def test_runner_sends_peer_result_without_parent_relationship(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    core.runner = AgentRunner(
        core,
        TurnPipeline(
            event_log=core.event_log,
            stages=default_stages(),
            llm=_AnswerLLM(),
            tools=LegacyToolExecutor(core),
        ),
    )
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "run"}))).data
    requester = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "explorer"},
            )
        )
    ).data
    peer = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "researcher",
                    "requested_by_session_id": requester.id,
                    "query": "Find evidence",
                },
            )
        )
    ).data
    assert peer.parent_session_id is None
    deadline = asyncio.get_running_loop().time() + 5.0
    while not _reports(core, requester.id):
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("peer finished without reporting to its requester")
        await asyncio.sleep(0.01)
    assert peer.state.value == "succeeded"
    assert _reports(core, requester.id)[0].data["manifest"]["final_summary"] == "researcher answer"
    await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_success_report_is_durable_and_peer_is_not_a_child(tmp_path):
    core, store, _bus, requester, peer = await _sessions(tmp_path)
    assert peer.parent_session_id is None
    assert peer.requested_by_session_id == requester.id

    first_run = await _finish(core, peer, text="first answer", outcome="succeeded")
    await deliver_peer_completion(core, peer, wake=False)

    reports = _reports(core, requester.id)
    assert len(reports) == 1
    manifest = reports[0].data["manifest"]
    assert manifest["session_id"] == peer.id
    assert manifest["run_id"] == first_run
    assert manifest["state"] == "succeeded"
    assert manifest["final_summary"] == "first answer"
    assert "[Peer finished]" in reports[0].data["content"]
    assert store.query_project_events(peer.project_id)[-1]["type"] == "agent.message_injected"

    await _finish(
        core, peer, text="unrelated later run", outcome="failed",
        failure_kind=RunFailureKind.PIPELINE_INTERNAL,
    )
    await deliver_peer_completion(core, peer, wake=False)
    assert len(_reports(core, requester.id)) == 1


@pytest.mark.asyncio
async def test_failure_report_contains_first_run_outcome(tmp_path):
    core, _store, _bus, requester, peer = await _sessions(tmp_path)
    await _finish(
        core, peer, text="partial finding", outcome="failed",
        failure_kind=RunFailureKind.PIPELINE_INTERNAL,
    )
    await deliver_peer_completion(core, peer, wake=False)
    manifest = _reports(core, requester.id)[0].data["manifest"]
    assert manifest["state"] == "failed"
    assert manifest["failure_kind"] == RunFailureKind.PIPELINE_INTERNAL.value
    assert manifest["final_summary"] == "partial finding"


@pytest.mark.asyncio
async def test_cancel_queued_peer_reports_without_run(tmp_path):
    core, _store, bus, requester, peer = await _sessions(tmp_path)
    result = await bus.execute(Command(type="agent.cancel", target={"session_id": peer.id}))
    assert result.accepted
    assert peer.state.value == "cancelled"
    reports = _reports(core, requester.id)
    assert len(reports) == 1
    manifest = reports[0].data["manifest"]
    assert manifest["state"] == "cancelled"
    assert manifest["run_id"] is None


@pytest.mark.asyncio
async def test_restore_repairs_gap_and_uses_first_run_even_after_later_run(tmp_path):
    core, store, _bus, requester, peer = await _sessions(tmp_path)
    first_run = await _finish(core, peer, text="original answer", outcome="succeeded")
    await _finish(
        core, peer, text="later failure", outcome="failed",
        failure_kind=RunFailureKind.PIPELINE_INTERNAL,
    )
    # The first run reached a durable terminal state, but its completion
    # message was never committed before process restart.
    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    reports = _reports(restored, requester.id)
    assert len(reports) == 1
    manifest = reports[0].data["manifest"]
    assert manifest["run_id"] == first_run
    assert manifest["state"] == "succeeded"
    assert manifest["final_summary"] == "original answer"

    again = RuntimeCore(strict_events=True)
    again.store = store
    restore_core(again, store)
    assert len(_reports(again, requester.id)) == 1


@pytest.mark.asyncio
async def test_wait_background_does_not_consume_peer_result_obligation_across_restore(tmp_path):
    core, store, _bus, requester, peer = await _sessions(tmp_path)
    waiting_run = await _finish(
        core, peer, text="computation still running", outcome="succeeded",
        gate_action="wait_background",
    )
    await deliver_peer_completion(core, peer, wake=False)
    assert not _reports(core, requester.id)

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    assert not _reports(restored, requester.id)

    resumed_peer = restored.agents[peer.id]
    final_run = await _finish(
        restored, resumed_peer, text="verified final answer", outcome="succeeded",
        gate_action="allow_final",
    )
    await deliver_peer_completion(restored, resumed_peer, wake=False)
    reports = _reports(restored, requester.id)
    assert len(reports) == 1
    assert reports[0].data["manifest"]["run_id"] == final_run
    assert reports[0].data["manifest"]["run_id"] != waiting_run
    assert reports[0].data["manifest"]["final_summary"] == "verified final answer"

    again = RuntimeCore(strict_events=True)
    again.store = store
    restore_core(again, store)
    assert len(_reports(again, requester.id)) == 1


@pytest.mark.asyncio
async def test_restore_indexes_multiple_peer_results_independently(tmp_path):
    core, store, bus, requester, waiting_peer = await _sessions(tmp_path)
    other_peer = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": waiting_peer.project_id},
                payload={
                    "role_id": "small_mol",
                    "requested_by_session_id": requester.id,
                    "query": "Inspect the structure",
                },
            )
        )
    ).data
    await _finish(
        core, waiting_peer, text="waiting for compute", outcome="succeeded",
        gate_action="wait_background",
    )
    await _finish(core, other_peer, text="structure ready", outcome="succeeded")

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    reports = _reports(restored, requester.id)
    assert len(reports) == 1
    assert reports[0].data["manifest"]["session_id"] == other_peer.id
    assert reports[0].data["manifest"]["final_summary"] == "structure ready"

    await _finish(
        restored, restored.agents[waiting_peer.id],
        text="compute result ready", outcome="succeeded", gate_action="allow_final",
    )
    await deliver_peer_completion(restored, restored.agents[waiting_peer.id], wake=False)
    assert {report.data["manifest"]["session_id"] for report in _reports(restored, requester.id)} == {
        waiting_peer.id, other_peer.id,
    }


@pytest.mark.asyncio
async def test_restore_does_not_duplicate_delivered_report(tmp_path):
    core, store, _bus, requester, peer = await _sessions(tmp_path)
    await _finish(core, peer, text="done", outcome="succeeded")
    await deliver_peer_completion(core, peer, wake=False)
    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    assert len(_reports(restored, requester.id)) == 1


@pytest.mark.asyncio
async def test_failed_completion_write_is_not_visible_and_restore_repairs_it(tmp_path):
    core, store, _bus, requester, peer = await _sessions(tmp_path)
    await _finish(core, peer, text="durable answer", outcome="succeeded")
    original_append = store.append_event

    def reject_report(event):
        if event.type == "agent.message_injected" and event.session_id == requester.id:
            raise OSError("simulated report write failure")
        return original_append(event)

    store.append_event = reject_report
    with pytest.raises(EventPersistenceError):
        await deliver_peer_completion(core, peer, wake=False)
    assert not _reports(core, requester.id)
    assert core.mailbox.inbox(requester.id).empty()

    store.append_event = original_append
    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    assert len(_reports(restored, requester.id)) == 1


@pytest.mark.asyncio
async def test_restore_reports_interrupted_peer_and_does_not_wake_requester(tmp_path):
    core, store, _bus, requester, peer = await _sessions(tmp_path)
    await core.agent_host.start_run_durable(peer)
    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    assert restored.agents[peer.id].state.value == "failed"
    assert restored.agents[requester.id].state.value == "queued"
    reports = _reports(restored, requester.id)
    assert len(reports) == 1
    assert reports[0].data["manifest"]["failure_kind"] == "runtime_interrupted"


@pytest.mark.asyncio
async def test_cancelled_requester_keeps_report_in_inbox_after_restore(tmp_path):
    core, store, bus, requester, peer = await _sessions(tmp_path)
    await bus.execute(Command(type="agent.cancel", target={"session_id": requester.id}))
    assert peer.state.value == "queued"
    await _finish(core, peer, text="peer survived", outcome="succeeded")
    await deliver_peer_completion(core, peer)
    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    assert restored.agents[requester.id].state.value == "cancelled"
    inbox = restored.mailbox.inbox(requester.id)
    assert inbox is not None
    assert "[Peer finished]" in inbox.get_nowait()["content"]
