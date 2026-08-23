"""v2-native pending approvals & ask_user interactions (PendingBroker)."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.base.tools_class import Tool, use_approval_handler
from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import AgentState, Command, CommandRejected
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class StopLLM:
    async def complete(self, agent, messages, tools, **_kwargs):
        return LLMResponse(content="done", stop_requested=True)


class ScriptedLLM:
    def __init__(self, plan: list[LLMResponse]) -> None:
        self.plan = list(plan)

    async def complete(self, agent, messages, tools, **_kwargs):
        assert self.plan, "no scripted response left"
        return self.plan.pop(0)


async def _stub_summarizer(messages):
    # Tests never hit the network; run-end summarization is covered in
    # test_runtime_v2_context_tree.py with dedicated fakes.
    return "[RUN LOG]\nstub trajectory\n[HANDOVER]\nstub state"


async def _setup(llm=None):
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm or StopLLM(),
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline, run_summarizer=_stub_summarizer)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "pending"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    return core, project, result.data


async def _wait_for(predicate, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


# ---------------------------------------------------------------------- broker


@pytest.mark.asyncio
async def test_approval_approve_and_deny():
    core, project, agent = await _setup()
    await _wait_for(lambda: agent.state is AgentState.SUCCEEDED)
    # Pretend a fresh run is live so the broker can park the agent.
    core.agent_host.start_run(agent)

    async def ask():
        return await core.pending.request_approval(
            agent,
            tool_name="text_writer",
            details="write file",
            normalized_arguments={"path": "a.txt"},
            risk_summary="write a.txt",
            candidate_diff="+hello",
        )

    task = asyncio.create_task(ask())
    await _wait_for(lambda: agent.state is AgentState.WAITING_APPROVAL)
    pending = core.pending.list_pending_approvals(project.id)
    assert len(pending) == 1
    assert pending[0]["tool_name"] == "text_writer"
    assert pending[0]["candidate_diff"] == "+hello"

    await core.pending.decide_approval(project.id, pending[0]["id"], "approved", "")
    approved, reason = await task
    assert approved is True and reason == ""
    assert agent.state is AgentState.RUNNING
    assert core.pending.list_pending_approvals(project.id) == []

    task2 = asyncio.create_task(ask())
    await _wait_for(lambda: core.pending.list_pending_approvals(project.id))
    aid = core.pending.list_pending_approvals(project.id)[0]["id"]
    await core.pending.decide_approval(project.id, aid, "denied", "too risky")
    approved, reason = await task2
    assert approved is False and reason == "too risky"


@pytest.mark.asyncio
async def test_decide_unknown_approval_rejected():
    core, project, agent = await _setup()
    await _wait_for(lambda: agent.state is AgentState.SUCCEEDED)
    with pytest.raises(CommandRejected):
        await core.pending.decide_approval(project.id, "apv_nope", "approved", "")


@pytest.mark.asyncio
async def test_interaction_roundtrip():
    core, project, agent = await _setup()
    await _wait_for(lambda: agent.state is AgentState.SUCCEEDED)
    core.agent_host.start_run(agent)

    task = asyncio.create_task(core.pending.request_interaction(agent, "which solvent?"))
    await _wait_for(lambda: agent.state is AgentState.WAITING_INPUT)
    pending = core.pending.list_pending_interactions(project.id)
    assert len(pending) == 1
    assert pending[0]["prompt"] == "which solvent?"
    assert pending[0]["state"] == "pending"

    record = await core.pending.respond_interaction(project.id, pending[0]["interaction_id"], "ethanol")
    assert record["state"] == "responded"
    assert await task == "ethanol"
    assert agent.state is AgentState.RUNNING
    assert core.pending.list_pending_interactions(project.id) == []


@pytest.mark.asyncio
async def test_cancel_while_waiting_expires_request():
    core, project, agent = await _setup()
    await _wait_for(lambda: agent.state is AgentState.SUCCEEDED)
    core.agent_host.start_run(agent)

    task = asyncio.create_task(core.pending.request_interaction(agent, "ping?"))
    await _wait_for(lambda: agent.state is AgentState.WAITING_INPUT)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert core.pending.list_pending_interactions(project.id) == []
    responded = [
        e
        for e in core.event_log.query_project(project.id, types={"interaction.responded"})
        if e.data.get("expired")
    ]
    assert responded, "expiry event missing"


# ------------------------------------------------------------- tool-class hook


class _DummyDestructive(Tool):
    tool_id: str = "t-test-destructive"
    tool_name: str = "test_destructive"
    tool_description: str = "test"

    def is_destructive(self) -> bool:
        return True

    async def tool_call(self, user_input, session):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_request_approval_prefers_scoped_handler():
    tool = _DummyDestructive()
    seen = {}

    async def handler(**fields):
        seen.update(fields)
        return True, ""

    with use_approval_handler(handler):
        approved, reason = await tool.request_approval(
            "/nonexistent/db.sqlite",
            "as_x",
            "details text",
            tool_name="test_destructive",
            normalized_arguments={"a": 1},
            risk_summary="risk",
            candidate_diff="diff",
        )
    assert approved is True and reason == ""
    assert seen["tool_name"] == "test_destructive"
    assert seen["candidate_diff"] == "diff"


# ------------------------------------------------------ end-to-end via executor


@pytest.mark.asyncio
async def test_ask_user_end_to_end_via_command():
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="t1", name="ask_user", arguments={"question": "which solvent?"})],
            ),
            LLMResponse(content="used the answer", stop_requested=True),
        ]
    )
    core, project, coordinator = await _setup(llm)
    bus = CommandBus(core)

    await _wait_for(lambda: core.pending.list_pending_interactions(project.id))
    pending = core.pending.list_pending_interactions(project.id)
    assert "which solvent?" in pending[0]["prompt"]
    assert coordinator.state is AgentState.WAITING_INPUT

    result = await bus.execute(
        Command(
            type="interaction.respond",
            target={"project_id": project.id},
            payload={"interaction_id": pending[0]["interaction_id"], "response": "ethanol"},
        )
    )
    assert result.accepted is True
    await _wait_for(lambda: coordinator.state is AgentState.SUCCEEDED)

    tool_events = [
        e
        for e in core.event_log.query_session(coordinator.id)
        if e.type == "tool.finished" and e.data.get("tool_name") == "ask_user"
    ]
    assert tool_events and "ethanol" in tool_events[0].data["result_summary"]
