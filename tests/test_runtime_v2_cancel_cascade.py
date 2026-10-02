"""Cancel cascade (C2): cancelling an agent cascades to its live children and
to any launch groups it owns.

- async (is_wait=False) children reach a cancelled terminal instead of
  running on and burning LLM/compute; their reports park at the cancelled
  parent (park-don't-wake), never wake it;
- launch groups owned by the cancelled parent stop spawning, per-item states
  settle, and the group worker task is registered with the runner so cancel
  and shutdown both observe it;
- cancel during an is_wait swarm keeps the existing CancelledError cascade;
- service shutdown with a live launch group reaps everything.
"""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import AgentState, Command
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class CascadeLLM:
    """Coordinator follows a scripted plan, then parks; children park in their
    first LLM call until cancelled (no further requests may fire)."""

    def __init__(self, plan: list[LLMResponse]) -> None:
        self.plan = list(plan)
        self.child_calls = 0
        self.child_entered = asyncio.Event()

    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id != "coordinator":
            self.child_calls += 1
            self.child_entered.set()
            await asyncio.Event().wait()  # parks until the task is cancelled
        if self.plan:
            return self.plan.pop(0)
        await asyncio.Event().wait()  # parent parks once the plan is exhausted


async def _setup(llm) -> tuple[RuntimeCore, object, object]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "cascade"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={
                "role_id": "coordinator",
                "query": "solve it",
                "settings": {"invocation_protocol": "traditional"},
            },
        )
    )
    return core, project, result.data


async def _wait_until(predicate, timeout: float = 10.0, what: str = "condition"):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.01)


def _children(core, parent_id: str):
    return [a for a in core.agents.values() if a.parent_session_id == parent_id]


async def _cancel(core, session_id: str):
    await CommandBus(core).execute(
        Command(type="agent.cancel", target={"session_id": session_id}, payload={})
    )


async def _parked_child_with_job():
    """A child has ended one run to wait for its own durable compute notice."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.effects import EventDraft
    from cloudra.services.compute_store import ainsert_compute_job

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(
        type="project.create", payload={"name": "parked cancellation"},
    ))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator"},
    ))).data
    child = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "small_mol", "parent_session_id": parent.id},
    ))).data
    job_id = await ainsert_compute_job(
        await ComputeDB().ainit(), conversation_id=project.id, session_id=child.id,
        path="/tmp/parked-cancel.gjf", state="ready", jobtype="gaussian",
        node_id="local",
    )
    run_id = await core.agent_host.start_run(child)
    await core.event_writer.commit(EventDraft(
        "agent.completion_gate", stream="agent", project_id=project.id,
        session_id=child.id, run_id=run_id,
        data={"action": "wait_background", "reason": "compute pending", "source": "schedule"},
    ))
    await core.agent_host.finish_run(child, outcome="succeeded")
    assert child.state is AgentState.SUCCEEDED
    return core, project, parent, child, job_id


async def _complete_job_and_notify(core, project_id: str, job_id: int) -> None:
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker

    db = ComputeDB()
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET state='done' WHERE id=?", (job_id,),
        )
        await con.commit()
    await ComputeNotifyBroker(core)._poll_project(project_id)


@pytest.mark.asyncio
async def test_cancel_parent_cancels_child_parked_on_compute_without_cancelling_job():
    core, project, parent, child, job_id = await _parked_child_with_job()

    await _cancel(core, parent.id)

    assert parent.state is AgentState.CANCELLED
    assert child.state is AgentState.CANCELLED
    await _complete_job_and_notify(core, project.id, job_id)
    assert child.state is AgentState.CANCELLED
    assert len(core.event_log.query_session(child.id, types={"run.started"})) == 1
    from cloudra.persistence.database import ComputeDB
    async with ComputeDB().aconnect() as con:
        row = await (await con.execute(
            "SELECT state FROM compute_jobs WHERE id=?", (job_id,),
        )).fetchone()
    assert row[0] == "done", "cancel only stops the agent, not its compute job"


@pytest.mark.asyncio
async def test_cancel_launch_group_cancels_child_parked_on_compute():
    core, project, parent, child, job_id = await _parked_child_with_job()
    group = await core.launch_groups.create(
        group_id="grp_parked_cancel", parent_session_id=parent.id,
        project_id=project.id, items=[("item", "work")], max_concurrency=1,
        spawner=lambda _query: asyncio.sleep(0, result=child),
    )
    await _wait_until(
        lambda: group.items[0].child_session_id == child.id,
        what="parked child assigned to group",
    )

    await core.launch_groups.cancel(group.group_id)

    assert group.state == "cancelled"
    assert group.items[0].state == "cancelled"
    assert child.state is AgentState.CANCELLED
    await _complete_job_and_notify(core, project.id, job_id)
    assert child.state is AgentState.CANCELLED
    assert len(core.event_log.query_session(child.id, types={"run.started"})) == 1


@pytest.mark.asyncio
async def test_shutdown_does_not_cancel_child_parked_on_compute():
    """A service restart must leave the compute notice able to resume its child."""
    core, project, parent, child, job_id = await _parked_child_with_job()
    group = await core.launch_groups.create(
        group_id="grp_parked_shutdown", parent_session_id=parent.id,
        project_id=project.id, items=[("item", "work")], max_concurrency=1,
        spawner=lambda _query: asyncio.sleep(0, result=child),
    )
    await _wait_until(
        lambda: group.items[0].child_session_id == child.id,
        what="parked child assigned to group",
    )

    await core.aclose()

    assert group.state == "cancelled"
    assert child.state is AgentState.SUCCEEDED
    from cloudra.persistence.database import ComputeDB
    async with ComputeDB().aconnect() as con:
        row = await (await con.execute(
            "SELECT state FROM compute_jobs WHERE id=?", (job_id,),
        )).fetchone()
    assert row[0] == "ready"


@pytest.mark.asyncio
async def test_cancel_parent_cascades_to_async_child():
    """Cancelling a parent whose async child is mid-run must cancel the child:
    cancelled terminal, no new LLM requests from it, and its completion report
    parks at the cancelled parent without waking it."""
    llm = CascadeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="subagent_launcher",
                        arguments={"role_id": "explorer", "query": "explore X", "is_wait": False},
                    )
                ],
            ),
        ]
    )
    core, _, coordinator = await _setup(llm)
    await asyncio.wait_for(llm.child_entered.wait(), timeout=10)
    child = _children(core, coordinator.id)[0]
    assert child.state is AgentState.RUNNING

    await _cancel(core, coordinator.id)

    assert coordinator.state is AgentState.CANCELLED
    assert child.state is AgentState.CANCELLED
    cancel_requests = [
        e for e in core.event_log.query_session(child.id) if e.type == "agent.cancel_requested"
    ]
    assert cancel_requests, "cascade must record a cancel request for the child"
    assert cancel_requests[0].data.get("cause") == "parent_cancelled"
    # Parked report reaches the cancelled parent's mailbox; no wake, no new run.
    inbox = core.mailbox.inbox(coordinator.id)
    assert inbox is not None and not inbox.empty(), "child report must park at the parent"
    assert "[Sub-agent finished]" in inbox.get_nowait()["content"]
    assert coordinator.state is AgentState.CANCELLED
    assert not [e for e in core.event_log.query_session(coordinator.id) if e.type == "run.started"][1:]
    await asyncio.sleep(0.05)
    assert llm.child_calls == 1, "cancelled child fired another LLM request"


@pytest.mark.asyncio
async def test_cancel_parent_cancels_launch_group():
    """A running launch group owned by the cancelled parent stops spawning;
    queued and running items settle to cancelled and the only spawned child is
    cascade-cancelled too."""
    llm = CascadeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="subagent_swarm",
                        arguments={
                            "role_id": "explorer",
                            "prompt_template": "scan {{item}}",
                            "items": ["alpha", "beta", "gamma"],
                            "is_wait": False,
                            "max_concurrency": 1,
                        },
                    )
                ],
            ),
        ]
    )
    core, _, coordinator = await _setup(llm)
    await asyncio.wait_for(llm.child_entered.wait(), timeout=10)
    manager = core.launch_groups
    assert manager is not None
    group = next(iter(manager._groups.values()))
    await _wait_until(lambda: group.running_count == 1, what="first group child running")

    await _cancel(core, coordinator.id)

    assert coordinator.state is AgentState.CANCELLED
    assert group.state == "cancelled"
    assert all(item.state == "cancelled" for item in group.items)
    assert group._task is not None and group._task.done()
    children = _children(core, coordinator.id)
    assert len(children) == 1, "cancelled group kept spawning"
    assert all(c.state is AgentState.CANCELLED for c in children)
    assert coordinator.id not in core.runner._background, "group worker task leaked the registry"
    await asyncio.sleep(0.05)
    assert len(_children(core, coordinator.id)) == 1, "no further spawns after cancel"
    assert llm.child_calls == 1


@pytest.mark.asyncio
async def test_cancel_during_wait_swarm_still_cascades():
    """Green guard for the pre-existing path: cancelling a parent parked in an
    is_wait swarm still cancels every spawned child."""
    llm = CascadeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="subagent_swarm",
                        arguments={
                            "role_id": "explorer",
                            "prompt_template": "scan {{item}}",
                            "items": ["alpha", "beta"],
                            "is_wait": True,
                        },
                    )
                ],
            ),
        ]
    )
    core, _, coordinator = await _setup(llm)
    await _wait_until(lambda: llm.child_calls == 2, what="both swarm children parked in the LLM")

    await _cancel(core, coordinator.id)

    assert coordinator.state is AgentState.CANCELLED
    children = _children(core, coordinator.id)
    assert len(children) == 2
    assert all(c.state is AgentState.CANCELLED for c in children)
    await asyncio.sleep(0.05)
    assert llm.child_calls == 2


@pytest.mark.asyncio
async def test_aclose_with_live_launch_group_leaves_no_orphans():
    """Service shutdown with a live launch group: the group worker (registered
    via track_background) and every runner task are cancelled and awaited; no
    orphaned tasks, no further spawns."""
    llm = CascadeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="subagent_swarm",
                        arguments={
                            "role_id": "explorer",
                            "prompt_template": "scan {{item}}",
                            "items": ["alpha", "beta", "gamma"],
                            "is_wait": False,
                            "max_concurrency": 1,
                        },
                    )
                ],
            ),
        ]
    )
    core, _, coordinator = await _setup(llm)
    await asyncio.wait_for(llm.child_entered.wait(), timeout=10)
    group = next(iter(core.launch_groups._groups.values()))
    await _wait_until(lambda: group.running_count == 1, what="first group child running")

    await core.aclose()

    assert core.runner._tasks == {}
    assert core.runner._background == {}
    assert group.state == "cancelled"
    assert group._task is not None and group._task.done()
    await asyncio.sleep(0.05)
    assert len(_children(core, coordinator.id)) == 1, "shutdown left a spawning group behind"
    assert llm.child_calls == 1
