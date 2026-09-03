"""v2-native sub-agent dispatch: launcher/swarm/report via the kernel."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.subagent_bridge import handle_native_tool
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class RoleRoutedLLM:
    """Coordinator gets a scripted dispatch plan; every child echoes its task."""

    def __init__(self, plan: list[LLMResponse]) -> None:
        self.plan = list(plan)

    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id != "coordinator":
            user_msgs = [m for m in messages if m.get("role") == "user"]
            task = str(user_msgs[-1].get("content", "") if user_msgs else "")[:40]
            return LLMResponse(content=f"{agent.role_id} done: {task}", stop_requested=True)
        if not self.plan:
            # Async child completion wakes the parent with a mailbox report;
            # extra coordinator turns after the scripted plan are acks.
            return LLMResponse(content="acked sub-agent report", stop_requested=True)
        return self.plan.pop(0)


async def _stub_summarizer(messages):
    # Tests never hit the network; run-end summarization is covered in
    # test_runtime_v2_context_tree.py with dedicated fakes.
    return "[RUN LOG]\nstub trajectory\n[HANDOVER]\nstub state"


async def _setup(llm) -> tuple[RuntimeCore, object, object]:
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline, run_summarizer=_stub_summarizer)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "dispatch"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "solve it"},
        )
    )
    return core, project, result.data


async def _wait_state(agent, state: str, timeout: float = 10.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


def _children(core, parent_id: str):
    return [a for a in core.agents.values() if a.parent_session_id == parent_id]


@pytest.mark.asyncio
async def test_launcher_wait_spawns_v2_child_and_returns_result():
    llm = RoleRoutedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="subagent_launcher",
                        arguments={"agent_id": "a-1", "query": "explore X", "is_wait": True},
                    )
                ],
            ),
            LLMResponse(content="final", stop_requested=True),
        ]
    )
    core, _, coordinator = await _setup(llm)
    await _wait_state(coordinator, "succeeded")

    children = _children(core, coordinator.id)
    assert len(children) == 1
    child = children[0]
    assert child.role_id == "explorer"  # a-1 mapped
    assert child.state.value == "succeeded"

    tool_events = [
        e
        for e in core.event_log.query_session(coordinator.id)
        if e.type == "tool.finished" and e.data.get("tool_name") == "subagent_launcher"
    ]
    assert tool_events, "launcher tool call missing"
    assert tool_events[0].data["is_success"] is True
    assert "explorer done: explore X" in tool_events[0].data["result_summary"]
    # The child really ran on the v2 kernel.
    child_events = [e.type for e in core.event_log.query_session(child.id)]
    assert "run.started" in child_events
    assert "agent.message_emitted" in child_events


@pytest.mark.asyncio
async def test_launcher_nowait_then_report():
    llm = RoleRoutedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="subagent_launcher",
                        arguments={"agent_id": "a-4", "query": "optimize water", "is_wait": False},
                    )
                ],
            ),
            LLMResponse(content="final", stop_requested=True),
        ]
    )
    core, _, coordinator = await _setup(llm)
    await _wait_state(coordinator, "succeeded")
    child = _children(core, coordinator.id)[0]
    assert child.role_id == "small_mol"
    await _wait_state(child, "succeeded")

    report = await handle_native_tool(
        core, coordinator, ToolCall(id="t2", name="get_subagent_report", arguments={"session_id": child.id})
    )
    assert report.is_success is True
    assert "optimize water" in report.summary

    missing = await handle_native_tool(
        core, coordinator, ToolCall(id="t3", name="get_subagent_report", arguments={"session_id": "as_nope"})
    )
    assert missing.is_success is False


def _completion_injections(core, parent_id: str, child_id: str):
    return [
        e
        for e in core.event_log.query_session(parent_id, types={"agent.message_injected"})
        if child_id in str(e.data.get("content", ""))
    ]


@pytest.mark.asyncio
async def test_async_child_completion_injects_parent_mailbox_and_wakes():
    """is_wait=False: child terminal must land in the parent's mailbox and wake it."""
    llm = RoleRoutedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="subagent_launcher",
                        arguments={"agent_id": "a-1", "query": "explore X", "is_wait": False},
                    )
                ],
            ),
            LLMResponse(content="dispatched", stop_requested=True),
            LLMResponse(content="received child report", stop_requested=True),
        ]
    )
    core, _, coordinator = await _setup(llm)
    # 全套测试负载下异步 spawn 可能被拖慢：窗口给足余量（15s），
    # 单跑/慢机均稳定，失败只可能来自真实未 spawn。
    deadline = asyncio.get_running_loop().time() + 15.0
    children: list = []
    while asyncio.get_running_loop().time() < deadline:
        children = _children(core, coordinator.id)
        if children:
            break
        await asyncio.sleep(0.01)
    if not children:
        states = {a.id: a.state.value for a in core.agents.values()}
        tool_events = [
            e.type
            for e in core.event_log.query_session(coordinator.id)
            if e.type.startswith("tool.")
        ][-10:]
        raise AssertionError(
            "no children spawned; "
            f"coordinator={coordinator.state.value}; agents={states}; "
            f"last tool events={tool_events}"
        )
    assert len(children) == 1
    child = children[0]
    await _wait_state(child, "succeeded")

    reports = _completion_injections(core, coordinator.id, child.id)
    assert reports, "child completion must be delivered to the parent mailbox"
    body = reports[0].data["content"]
    assert "[Sub-agent finished]" in body
    assert child.id in body
    assert "succeeded" in body
    assert "explore X" in body

    await _wait_state(coordinator, "succeeded")
    emitted = [
        e
        for e in core.event_log.query_session(coordinator.id, types={"agent.message_emitted"})
        if "received child report" in str(e.data.get("content", ""))
    ]
    assert emitted, "parent must wake on the mailbox report and continue"


@pytest.mark.asyncio
async def test_swarm_expands_items_and_aggregates():
    llm = RoleRoutedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="subagent_swarm",
                        arguments={
                            "agent_id": "a-1",
                            "prompt_template": "scan {{item}}",
                            "items": ["alpha", "beta"],
                            "is_wait": True,
                        },
                    )
                ],
            ),
            LLMResponse(content="final", stop_requested=True),
        ]
    )
    core, _, coordinator = await _setup(llm)
    await _wait_state(coordinator, "succeeded")

    children = _children(core, coordinator.id)
    assert len(children) == 2
    assert all(c.state.value == "succeeded" for c in children)
    tool_events = [
        e
        for e in core.event_log.query_session(coordinator.id)
        if e.type == "tool.finished" and e.data.get("tool_name") == "subagent_swarm"
    ]
    assert "alpha" in tool_events[0].data["result_summary"]
    assert "beta" in tool_events[0].data["result_summary"]


@pytest.mark.asyncio
async def test_spawn_permission_enforced_for_roles():
    core, _, coordinator = await _setup(RoleRoutedLLM([LLMResponse(content="x", stop_requested=True)]))
    await _wait_state(coordinator, "succeeded")
    # Simulate a non-coordinator caller (explorer has can_spawn=False).
    fake = coordinator.model_copy(update={"id": "as_fake_explorer", "role_id": "explorer"})
    core.agents[fake.id] = fake
    result = await handle_native_tool(
        core, fake, ToolCall(id="t9", name="subagent_launcher", arguments={"agent_id": "a-1", "query": "x", "is_wait": True})
    )
    assert result.is_success is False
    assert "cannot spawn" in result.summary


@pytest.mark.asyncio
async def test_child_inherits_parent_yolo_at_spawn():
    """yolo 是对整个任务的信任授权：父开了 yolo，spawn 出的子 agent 必须继承，
    否则子 agent 仍逐项弹审批。"""
    llm = RoleRoutedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="subagent_launcher",
                        arguments={"agent_id": "a-1", "query": "explore X", "is_wait": False},
                    )
                ],
            ),
            LLMResponse(content="final", stop_requested=True),
        ]
    )
    core, project, coordinator = await _setup(llm)
    # runner 可能已开始跑：在子 agent spawn 前把父的 yolo 打上。
    # 直接改内存快照即可——settings 在每次工具执行时现读。
    coordinator.settings = coordinator.settings.model_copy(update={"yolo": True})
    await _wait_state(coordinator, "succeeded")

    child = _children(core, coordinator.id)[0]
    assert child.settings.yolo is True
    await _wait_state(child, "succeeded")


@pytest.mark.asyncio
async def test_swarm_and_launcher_spawn_share_legacy_identity():
    """D13 回归：swarm 与 launcher 派生的子 agent 走同一条身份映射——
    DAG 侧的 legacy id 由 role_id 经 legacy_agent_id_for_role 推出，
    绝不退回 session uuid（首个 swarm 曾以 session id 当 actor 的 bug）。"""
    from cloudra.runtime_v2.policies.dag_stage import DagPolicyStage
    from cloudra.subagents.registry import legacy_agent_id_for_role

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "identity"}))
    project = next(iter(core.projects.values()))
    parent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data

    launched = await handle_native_tool(
        core,
        parent,
        ToolCall(
            id="t1",
            name="subagent_launcher",
            arguments={"agent_id": "a-4", "query": "", "is_wait": False},
        ),
    )
    swarmed = await handle_native_tool(
        core,
        parent,
        ToolCall(
            id="t2",
            name="subagent_swarm",
            arguments={
                "agent_id": "a-4",
                "prompt_template": "do {{item}}",
                "items": ["x"],
                "is_wait": False,
            },
        ),
    )
    assert launched.is_success
    assert swarmed.is_success

    children = [a for a in core.agents.values() if a.parent_session_id == parent.id]
    assert len(children) == 2
    for child in children:
        assert child.role_id == "small_mol"
        legacy = legacy_agent_id_for_role(child.role_id)
        assert legacy == "a-4"
        assert legacy != child.id
        assert DagPolicyStage._legacy_agent_id(child.role_id) == "a-4"


@pytest.mark.asyncio
async def test_child_inherits_parent_orchestration_mode():
    from cloudra.runtime_v2.schemas import OrchestrationMode

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "dag_guided_proj"}))
    project = next(iter(core.projects.values()))
    parent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "coordinator",
                    "settings": {"orchestration_mode": OrchestrationMode.DAG_GUIDED.value},
                },
            )
        )
    ).data
    assert parent.settings.orchestration_mode is OrchestrationMode.DAG_GUIDED

    launched = await handle_native_tool(
        core,
        parent,
        ToolCall(
            id="t1",
            name="subagent_launcher",
            arguments={"agent_id": "a-6", "query": "dft job", "is_wait": False},
        ),
    )
    assert launched.is_success
    child = [a for a in core.agents.values() if a.parent_session_id == parent.id][0]
    assert child.settings.orchestration_mode is OrchestrationMode.DAG_GUIDED
