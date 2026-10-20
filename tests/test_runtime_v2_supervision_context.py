"""Supervisors read the complete authoritative user task, not peer reasoning."""

import asyncio
import hashlib
import json
import threading
from pathlib import Path

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import Command


async def _project(bus, query):
    project = (await bus.execute(Command(type="project.create", payload={"name": "context"}))).data
    root = (await bus.execute(Command(type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator", "query": query}))).data
    return project, root


@pytest.mark.asyncio
async def test_root_query_and_later_user_constraints_are_complete_and_project_scoped():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    query = "Original task: " + "whole task detail; " * 1200 + "without ZPE or thermal corrections."
    project, root = await _project(bus, query)
    first = core.event_log.query_session(root.id, types={"agent.message_injected"})[0]
    assert first.data["sender"] == "user", "A user-created task must retain user provenance."
    correction = "User correction: compare both channels against the same reactant reference."
    await bus.execute(Command(type="agent.message", target={"session_id": root.id},
                              payload={"content": correction}))
    peer = (await bus.execute(Command(type="agent.spawn", actor="agent", target={"project_id": project.id},
        payload={"role_id": "small_mol", "requested_by_session_id": root.id,
                 "query": "Peer instruction: add a Gibbs requirement."}))).data
    await bus.execute(Command(type="agent.message", actor="agent", target={"session_id": root.id},
                              payload={"content": "Peer says the user now requires Gibbs energies."}))
    await bus.execute(Command(type="agent.message", actor="system", target={"session_id": root.id},
                              payload={"content": "System notice: read PROCESS.md."}))
    core.event_log.append("context.appended", stream="agent", project_id=project.id,
                         session_id=root.id, data={"messages": [{"role": "assistant",
                         "content": "Prior reasoning: more thermochemistry must be better."}]})
    child_constraint = "Direct user correction sent to the specialist."
    await bus.execute(Command(type="agent.message", target={"session_id": peer.id},
                              payload={"content": child_constraint}))
    await _project(bus, "Unrelated project's user task.")

    from cloudra.runtime_v2.supervision_context import project_task_context

    context = await asyncio.to_thread(project_task_context, core, project.id)
    assert query in context
    assert correction in context
    assert child_constraint in context
    assert context.index(query) < context.index(correction) < context.index(child_constraint)
    assert "Peer instruction" not in context
    assert "Peer says" not in context
    assert "System notice" not in context
    assert "Prior reasoning" not in context
    assert "Unrelated project's" not in context


@pytest.mark.asyncio
async def test_human_spawn_with_parent_and_public_forum_constraints_reach_supervisor():
    from cloudra.runtime_v2.hub_bridge import post_user_post
    from cloudra.runtime_v2.supervision_context import project_task_context

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, root = await _project(bus, "Original human task.")
    specialist_task = "Human's direct specialist constraint: electronic energies only."
    await bus.execute(Command(type="agent.spawn", actor="user", target={"project_id": project.id},
        payload={"role_id": "small_mol", "parent_session_id": root.id, "query": specialist_task}))
    forum_constraint = "Untargeted forum correction: preserve both stereochemical channels."
    await post_user_post(core, project.id, topic="Scope", content=forum_constraint)
    broadcast_constraint = "Broadcast user correction: retain original native logs."
    await post_user_post(core, project.id, topic="Evidence", content=broadcast_constraint,
                         kind="broadcast")
    context = await asyncio.to_thread(project_task_context, core, project.id)
    assert specialist_task in context
    assert forum_constraint in context
    assert context.count(broadcast_constraint) == 1
    assert context.index(specialist_task) < context.index(forum_constraint) < context.index(broadcast_constraint)
    await core.aclose()


@pytest.mark.asyncio
async def test_system_spawn_query_is_not_promoted_to_a_user_requirement():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "system-only"}))).data
    await bus.execute(Command(type="agent.spawn", actor="system", target={"project_id": project.id},
        payload={"role_id": "coordinator", "query": "System-generated research instruction."}))

    from cloudra.runtime_v2.supervision_context import project_task_context

    context = await asyncio.to_thread(project_task_context, core, project.id)
    assert "System-generated research instruction" not in context
    assert "No user request is recorded" in context


@pytest.mark.asyncio
async def test_task_context_survives_event_cache_eviction_and_restart(tmp_path):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    core.event_log._max_cached_events = 3
    bus = CommandBus(core)
    query = "Formal complete task; compare electronic energies only."
    project, root = await _project(bus, query)
    for index in range(30):
        core.event_log.append("agent.warning", stream="agent", project_id=project.id,
                              session_id=root.id, data={"index": index})
    await core.event_writer.flush()
    assert core.event_log.resident_start_index > 0
    correction = "Later user constraint, beyond the resident event prefix."
    await bus.execute(Command(type="agent.message", target={"session_id": root.id},
                              payload={"content": correction}))
    await asyncio.to_thread(core.event_log.restore_from_store, core.store)

    from cloudra.runtime_v2.supervision_context import project_task_context

    context = await asyncio.to_thread(project_task_context, core, project.id)
    assert query in context
    assert correction in context
    assert "index" not in context


@pytest.mark.asyncio
async def test_context_pin_refreshes_user_updates_without_sync_history_reads_on_loop(monkeypatch):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project, root = await _project(bus, "Original user task.")
    supervisor = (await bus.execute(Command(type="agent.spawn", actor="system",
        target={"project_id": project.id}, payload={"role_id": "supervisor",
        "parent_session_id": root.id}))).data
    loop_thread = threading.get_ident()
    query = core.event_log.query_project

    def assert_off_loop(*args, **kwargs):
        assert threading.get_ident() != loop_thread
        return query(*args, **kwargs)

    monkeypatch.setattr(core.event_log, "query_project", assert_off_loop)

    from cloudra.runtime_v2.supervision_context import (
        SUPERVISOR_TASK_PIN_KEY,
        sync_supervisor_task_context,
    )

    await sync_supervisor_task_context(core, supervisor)
    first_pin = core.notices.pin_content(supervisor.id, SUPERVISOR_TASK_PIN_KEY)
    assert "Original user task." in first_pin
    before = core.event_log.high_session_watermarks[supervisor.id]
    await sync_supervisor_task_context(core, supervisor)
    assert core.event_log.high_session_watermarks[supervisor.id] == before
    await bus.execute(Command(type="agent.message", target={"session_id": root.id},
                              payload={"content": "New user restriction: keep the requested method."}))
    await sync_supervisor_task_context(core, supervisor)
    updated = core.notices.pin_content(supervisor.id, SUPERVISOR_TASK_PIN_KEY)
    assert "Original user task." in updated
    assert "New user restriction: keep the requested method." in updated
    assert core.event_log.high_session_watermarks[supervisor.id] > before


@pytest.mark.asyncio
async def test_real_hb10_blind_task_replay_reaches_process_and_final_supervisors():
    """原通知确实漏题干；新用户入口重放完整盲题，不篡改旧 sender。"""
    from cloudra.runtime_v2.supervision_context import (
        SUPERVISOR_TASK_PIN_KEY,
        sync_supervisor_task_context,
    )

    fixture = Path(__file__).parent / "fixtures" / "supervisor_task_context_20261020"
    manifest = json.loads((fixture / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((fixture / name).read_bytes()).hexdigest() == expected["sha256"]
    case = json.loads((fixture / "case.json").read_text())
    historical_request = case["original_root_message"]["data"]
    old_notice = case["first_supervisor_notice"]["data"]
    original_task = historical_request["content"]
    clause = case["pre_contract_input_audit"]["required_clause"]
    assert historical_request["sender"] == "system"
    assert old_notice["sender"] == "system"
    assert clause in original_task and clause not in old_notice["content"]
    assert not case["pre_contract_input_audit"]["required_clause_present"]
    assert case["coverage_contract_call"]["data"]["arguments_summary"]["require_thermochemistry"] is True
    assert case["coverage_contract_result"]["data"]["result"]["is_success"] is True

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    try:
        project, root = await _project(bus, original_task)
        replayed = core.event_log.query_session(root.id, types={"agent.message_injected"})[0]
        assert replayed.data["sender"] == "user"
        assert replayed.event_id != case["original_root_message"]["event_id"]
        for final_request in (None, "new-fixture-exit-request"):
            supervisor = (await bus.execute(Command(type="agent.spawn", actor="system",
                target={"project_id": project.id}, payload={
                    "role_id": "supervisor", "parent_session_id": root.id,
                    "final_review_request_id": final_request,
                }))).data
            await bus.execute(Command(type="agent.message", actor="system",
                target={"session_id": supervisor.id}, payload={"content": old_notice["content"]}))
            await sync_supervisor_task_context(core, supervisor)
            scope = core.notices.pin_content(supervisor.id, SUPERVISOR_TASK_PIN_KEY)
            assert original_task in scope
            assert clause in scope
            assert old_notice["content"] not in scope
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_partial_final_reviewer_receives_untried_work_and_stopping_reason_contract(tmp_path):
    """真实最终模型输入必须区分科学限制、暂未找到与尚未尝试，不能只审停机措辞。"""
    from cloudra.runtime_v2.adapters import LegacyPromptProvider
    from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step

    query = "Find the requested path using the permitted method; preserve unresolved evidence honestly."
    provider = ScriptedProvider(by_role={
        "coordinator": [Step(tools=[("stop", {
            "delivery_disposition": "partial", "reason": "A validated path has not been found.",
        })])],
        "supervisor": [Step(stop=True)],
    })
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    harness.pipeline.prompt_provider = LegacyPromptProvider()
    try:
        await harness.spawn("coordinator", query, protocol="traditional", orchestration_mode="dag_guided")
        await harness.wait_for(lambda: provider.call_count("supervisor") > 0,
                               "independent partial-delivery review receives its actual model input")
        reviewers = [agent for agent in harness.core.agents.values() if agent.final_review_request_id]
        assert len(reviewers) == 1
        messages = next(messages for role, messages in provider.calls if role == "supervisor")
        model_input = "\n".join(message["content"] for message in messages
                                if isinstance(message.get("content"), str))
        assert query in model_input
        for requirement in (
            "evidence-supported scientific/allowed-method limits",
            "tried-but-unresolved searches",
            "reasonable permitted next steps not attempted",
            "why work stopped: user instruction, explicit budget/resource limit, or the Agent's own choice",
            "what each could resolve",
            "within scope and available budget/resources, return needs_evidence",
            "Stopping or finite failures do not prove infeasibility/inaccessibility",
            "without demanding exhaustive or out-of-scope research",
        ):
            assert requirement in model_input
    finally:
        await harness.aclose()
