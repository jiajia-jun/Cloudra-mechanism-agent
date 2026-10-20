"""Real Agent turns isolate final review while preserving the user's full scope."""

from __future__ import annotations

import asyncio
import json

import pytest

from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.supervision import find_project_supervisor, notify_supervisor
from tests.agent_scenarios import (
    ScenarioHarness,
    ScriptedProvider,
    Step,
    independent_partial_review_steps,
)


@pytest.mark.asyncio
async def test_partial_exit_final_supervisor_is_independent_in_actual_llm_turns(tmp_path):
    """默认策略/真实裁决工具：新会话读完整人类任务，裁决只唤醒原请求人。"""
    original_task = (
        "Original task: compare electronic barriers, without ZPE or thermal corrections. "
        + "Full task detail. " * 900
        + "End of the complete original task."
    )
    user_constraint = "User update: preserve the original native files and do not change the method."
    prior_intent = "PROCESS_SUPERVISOR_PRIVATE_INTENT: require an unrelated Gibbs comparison."
    attempt, review_ready = [asyncio.Event() for _ in range(2)]
    review = Step(wait_for=review_ready)
    provider = ScriptedProvider(by_role=independent_partial_review_steps(
        review, attempt, prior_intent=prior_intent,
    ))
    harness = await ScenarioHarness.start(tmp_path, provider=provider, workspace_dir=tmp_path)
    try:
        await harness.bus.execute(Command(type="role.update", target={"role_id": "supervisor"},
            payload={"default_settings": {
                "orchestration_mode": "dag_guided", "invocation_protocol": "traditional",
            }}))
        coordinator = await harness.spawn("coordinator", original_task,
            protocol="traditional", orchestration_mode="dag_guided")
        await harness.wait_for(lambda: provider.call_count("coordinator") == 1,
                               "first Coordinator invocation")
        await harness.bus.execute(Command(type="agent.message", actor="user",
            target={"session_id": coordinator.id}, payload={"content": user_constraint}))
        await notify_supervisor(harness.core, harness.project.id,
                                observation="An earlier research result is ready for inspection.")
        process = find_project_supervisor(harness.core, harness.project.id)
        assert process is not None
        await harness.wait_terminal(process)
        assert prior_intent in json.dumps(harness.core.session_contexts[process.id].messages)
        process_runs = len([e for e in harness.events(process) if e.type == "run.started"])

        attempt.set()
        await harness.wait_for(lambda: coordinator.state.value == "waiting_approval",
                               "partial delivery parked for review")
        finals = [agent for agent in harness.core.agents.values()
                  if agent.role_id == "supervisor" and agent.final_review_request_id]
        assert len(finals) == 1
        final = finals[0]
        assert final.id != process.id
        assert find_project_supervisor(harness.core, harness.project.id).id == process.id
        await harness.wait_for(lambda: provider.call_count("supervisor") == 2,
                               "independent final-review LLM invocation")
        final_messages = [messages for role, messages in provider.calls if role == "supervisor"][-1]
        actual_input = json.dumps(final_messages, ensure_ascii=False)
        assert original_task in actual_input
        assert user_constraint in actual_input
        assert prior_intent not in actual_input
        assert final.final_review_request_id in actual_input
        assert not any(message.get("manifest", {}).get("request_id") == final.final_review_request_id
                       for message in harness.messages(process))

        db = await asyncio.to_thread(lambda: ConversationDB(harness.project.id).init())
        store = DagStore(db)
        request = await asyncio.to_thread(store.get_review_request, final.final_review_request_id)
        assert request.kind == "exit" and request.requester == coordinator.id
        review.tools = [
            ("dag_view_evidence", {"review_id": request.request_id}),
            ("dag_review_evidence", {"request_id": request.request_id, "verdict": "accept",
                "reason": "The scoped partial delivery honestly retains its missing evidence."}),
        ]
        review_ready.set()
        await harness.wait_for(lambda: any(tool["tool_name"] == "dag_review_evidence"
            and tool["status"] == "completed" for tool in harness.tool_events(final)),
            "real final-review verdict")
        await harness.wait_terminal(final)
        verdict_tool = next(tool for tool in harness.tool_events(final)
                            if tool["tool_name"] == "dag_review_evidence")
        assert verdict_tool["is_success"]
        decision = await asyncio.to_thread(store.get_review_decision_for_request, request.request_id)
        assert decision.verdict == "accept"
        await harness.wait_terminal(coordinator)
        assert coordinator.state.value == "succeeded"
        assert provider.call_count("coordinator") == 2
        gates = [event.data for event in harness.events(coordinator)
                 if event.type == "agent.completion_gate" and event.data.get("explicit_stop")]
        assert [gate["action"] for gate in gates] == ["wait_review", "allow_final"]
        assert gates[-1]["basis"] == "supervisor_approved"
        assert len([e for e in harness.events(process) if e.type == "run.started"]) == process_runs
        assert not any(tool["tool_name"] == "dag_review_evidence"
                       for tool in harness.tool_events(process))
        assert not any(tool["tool_name"] == "submit_compute_job"
                       for agent in harness.core.agents.values() for tool in harness.tool_events(agent))
    finally:
        for release in (attempt, review_ready):
            release.set()
        await harness.aclose()
