"""Cancellation must finish terminal delivery without waiting on its own owner."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentState, Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class _HangingLLM:
    def __init__(self):
        self.entered = asyncio.Event()

    async def complete(self, *_args, **_kwargs):
        self.entered.set()
        await asyncio.Event().wait()


class _NoTools:
    async def execute(self, *_args, **_kwargs):
        raise AssertionError("the blocked model has not requested a tool")


@pytest.mark.asyncio
@pytest.mark.parametrize(("relationship", "report_kind"), [
    ("parent_session_id", "child_completion"),
    ("requested_by_session_id", "peer_call_completion"),
    (None, "background_quiescence"),
])
async def test_cancel_running_agent_preserves_terminal_delivery(tmp_path, relationship, report_kind):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={
        "name": "cancel-delivery", "workspace_dir": str(tmp_path),
    }))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator", "settings": {"orchestration_mode": "dag_guided" if relationship is None else "standard"}},
    ))).data
    await core.agent_host.start_run(parent)
    if relationship is None:
        core.record(
            "agent.completion_gate", stream="agent", project_id=project.id, session_id=parent.id,
            run_id=parent.current_run.run_id,
            data={"action": "wait_background", "source": "dag", "reason": "waiting for background work"},
        )
        await core.agent_host.finish_run(parent, outcome="succeeded")
    else:
        await core.agent_host.transition(parent, AgentState.WAITING_INPUT, reason="wait_input")
    llm = _HangingLLM()
    core.runner = AgentRunner(core, TurnPipeline(
        event_log=core.event_log, stages=(), llm=llm, tools=_NoTools(),
    ))
    child = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={
            "role_id": "explorer", "query": "wait",
            **({relationship: parent.id} if relationship is not None else {}),
        },
    ))).data
    await asyncio.wait_for(llm.entered.wait(), 10)
    cancel = asyncio.create_task(bus.execute(Command(
        type="agent.cancel", target={"session_id": child.id},
    )))
    try:
        done, _ = await asyncio.wait([cancel], timeout=1)
        assert done, "cancel waited on child cleanup that needs the command's write lock"
        result = await cancel
        assert result.accepted
        assert child.state is AgentState.CANCELLED
        assert parent.state is AgentState.RUNNING
        reports = core.event_log.query_session(parent.id, types={"agent.message_injected"})
        assert sum(event.data.get("manifest", {}).get("kind") == report_kind for event in reports) == 1
        assert core.runner.task_for(child.id) is None
    finally:
        if not cancel.done():
            cancel.cancel()
        await asyncio.gather(cancel, return_exceptions=True)
        await core.runner.cancel_all()


@pytest.mark.asyncio
async def test_child_cancel_does_not_deadlock_parent_finishing_under_delivery_lock(tmp_path):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={
        "name": "finish-cancel", "workspace_dir": str(tmp_path),
    }))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"},
    ))).data
    entered_end, release_end = asyncio.Event(), asyncio.Event()

    class PauseParentEnd:
        async def before_llm(self, _ctx, _messages):
            pass

        async def on_run_end(self, agent, **_kwargs):
            if agent.id == parent.id:
                entered_end.set()
                await release_end.wait()

    class FinishParentLLM(_HangingLLM):
        async def complete(self, agent, *_args, **_kwargs):
            if agent.id == parent.id:
                return LLMResponse(content="done", stop_requested=True)
            return await super().complete(agent)

    llm = FinishParentLLM()
    core.runner = AgentRunner(core, TurnPipeline(
        event_log=core.event_log, stages=[PauseParentEnd()], llm=llm, tools=_NoTools(),
    ))
    child = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={
            "role_id": "explorer", "parent_session_id": parent.id, "query": "wait",
        },
    ))).data
    await asyncio.wait_for(llm.entered.wait(), 10)
    await bus.execute(Command(type="agent.message", target={"session_id": parent.id}, payload={"content": "finish"}))
    await asyncio.wait_for(entered_end.wait(), 5)
    cancel = asyncio.create_task(bus.execute(Command(type="agent.cancel", target={"session_id": child.id})))
    try:
        # Parent owns its delivery lock; child cancellation reaches its report
        # while the command still owns command_lock. Finishing the parent must
        # be able to publish/apply its state without that command lock.
        await asyncio.sleep(0.02)
        assert not cancel.done()
        release_end.set()
        done, _ = await asyncio.wait([cancel], timeout=2)
        assert done, "parent finalization and child cancellation inverted their lock order"
        assert (await cancel).accepted
        assert child.state is AgentState.CANCELLED
        reports = core.event_log.query_session(parent.id, types={"agent.message_injected"})
        assert sum(event.data.get("manifest", {}).get("kind") == "child_completion" for event in reports) == 1
    finally:
        release_end.set()
        if not cancel.done():
            cancel.cancel()
        await asyncio.gather(cancel, return_exceptions=True)
        await core.runner.cancel_all()
