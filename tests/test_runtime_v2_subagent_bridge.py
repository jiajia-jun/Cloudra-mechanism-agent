"""v2-native sub-agent dispatch: launcher/swarm/report via the kernel."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.dispatcher import WakePolicy
from cloudra.runtime_v2.failures import RunFailureKind
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
    await bus.execute(Command(type="project.create", payload={"name": "dispatch"}))
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
    waits = [e for e in core.event_log.query_session(coordinator.id) if e.type == "tool.progress"]
    assert any({'kind': 'agent', 'target_id': child.id} in e.data['waits'] for e in waits)


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
    assert "manifest" in report.data
    assert report.data["manifest"]["session_id"] == child.id
    assert report.data["manifest"]["state"] == "succeeded"
    assert report.data["manifest"]["final_summary"]

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
async def test_stop_with_pending_inbox_continues_instead_of_finishing():
    """stop 竞态（CI 3.13 红点的确定性复现）：轮次中途收件箱来消息——异步
    子 agent 终态回报在父 agent 仍在 RUNNING 时 deliver+wake，而 wake 对
    RUNNING 是 no-op（"下个轮次 drain 收件箱"）。若本轮以 stop 收尾，消息将
    无人 drain。不变量：stop 前收件箱非空必须续跑一轮，不得直接 finish。"""
    core = RuntimeCore(strict_events=True)

    class MidTurnDeliveryLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                # 轮次进行中投递收件箱消息（此刻 wake 对 RUNNING 无效）
                await core.dispatcher.commit_and_deliver(
                    to_session_id=agent.id,
                    project_id=agent.project_id,
                    content="late child report",
                    sender="a-1",
                    wake=WakePolicy.NEVER,
                )
                return LLMResponse(content="done", stop_requested=True)
            return LLMResponse(content="processed late report", stop_requested=True)

    llm = MidTurnDeliveryLLM()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=LegacyToolExecutor(core),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "race"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "go"},
        )
    )
    coordinator = result.data
    await _wait_state(coordinator, "succeeded")

    assert llm.calls >= 2, "pending inbox message must force one more turn before stop"
    emitted = [
        e
        for e in core.event_log.query_session(coordinator.id, types={"agent.message_emitted"})
        if "processed late report" in str(e.data.get("content", ""))
    ]
    assert emitted, "the late inbox message must be drained by a follow-up turn"


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
async def test_launcher_empty_query_rejected_no_spawn():
    """GH 回归：字段为空不发送——JS 协议下模型曾传 `prompt`（而非 schema 的
    `query`），launcher 以空 query 静默 spawn 出永不调度的僵尸子 agent（只落
    agent.spawned，无 run、无 prompt 注入）。必须响亮拒绝，绝不 spawn。"""
    core, _, coordinator = await _setup(
        RoleRoutedLLM([LLMResponse(content="x", stop_requested=True)])
    )
    await _wait_state(coordinator, "succeeded")

    for args in (
        {"agent_id": "a-4", "query": ""},
        {"agent_id": "a-4", "prompt": "task"},  # 生产事故形状：键名错误
        {"agent_id": "a-4", "query": "   "},
    ):
        result = await handle_native_tool(
            core, coordinator, ToolCall(id="t1", name="subagent_launcher", arguments=args)
        )
        assert result.is_success is False, args
        assert "nothing was dispatched" in result.summary, args
    assert _children(core, coordinator.id) == []


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
    coordinator.settings = coordinator.settings.model_copy(update={"yolo": True, "clean_context": True})
    await _wait_state(coordinator, "succeeded")

    child = _children(core, coordinator.id)[0]
    assert child.settings.yolo is True
    assert child.settings.clean_context is True
    await _wait_state(child, "succeeded")


@pytest.mark.asyncio
async def test_child_completion_to_failed_parent_parks_without_reopening():
    """A2 不复活纪律：failed 父不被子的完成回传自动 reopen；报告照常投递
    信箱驻留（parked），用户显式消息仍可复活（既有行为保留）。"""
    from cloudra.runtime_v2.schemas import AgentState
    from cloudra.runtime_v2.subagent_bridge import deliver_child_completion_to_parent

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "park-failed"}))
    project = next(iter(core.projects.values()))
    parent = (
        await bus.execute(
            Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
        )
    ).data
    child = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "explorer", "parent_session_id": parent.id, "query": "q"},
            )
        )
    ).data
    run_id = await core.agent_host.start_run(child)
    core.event_log.append(
        "agent.message_emitted",
        stream="agent",
        project_id=project.id,
        session_id=child.id,
        run_id=run_id,
        data={"sender": "explorer", "content": "explored everything"},
    )
    await core.agent_host.finish_run(child, outcome="succeeded")
    await core.agent_host.start_run(parent)
    await core.agent_host.finish_run(
        parent,
        outcome="failed",
        error="parent boom",
        failure_kind=RunFailureKind.PIPELINE_INTERNAL,
    )
    assert parent.state is AgentState.FAILED
    runs_before = len([e for e in core.event_log.query_session(parent.id) if e.type == "run.started"])

    await deliver_child_completion_to_parent(core, child)

    assert parent.state is AgentState.FAILED  # 不 reopen
    assert len([e for e in core.event_log.query_session(parent.id) if e.type == "run.started"]) == runs_before
    inbox = core.mailbox.inbox(parent.id)
    assert inbox is not None and inbox.qsize() == 1
    parked = inbox.get_nowait()
    assert "[Sub-agent finished]" in parked["content"]
    assert "explored everything" in parked["content"]

    # 用户显式消息仍复活终态 agent（既有行为，不受影响）。
    await bus.execute(
        Command(type="agent.message", target={"session_id": parent.id}, payload={"content": "revive"})
    )
    assert parent.state is AgentState.RUNNING


@pytest.mark.asyncio
async def test_child_completion_to_cancelled_parent_parks_without_reopening():
    """A2：cancelled 父同样 parked 不唤醒——旧实现对 cancelled 父连投递都
    跳过（子的终态通知直接丢失），新纪律是投递驻留但不唤醒。"""
    from cloudra.runtime_v2.schemas import AgentState
    from cloudra.runtime_v2.subagent_bridge import deliver_child_completion_to_parent

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "park-cancelled"}))
    project = next(iter(core.projects.values()))
    parent = (
        await bus.execute(
            Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
        )
    ).data
    child = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "explorer", "parent_session_id": parent.id, "query": "q"},
            )
        )
    ).data
    run_id = await core.agent_host.start_run(child)
    core.event_log.append(
        "agent.message_emitted",
        stream="agent",
        project_id=project.id,
        session_id=child.id,
        run_id=run_id,
        data={"sender": "explorer", "content": "explored everything"},
    )
    await core.agent_host.finish_run(child, outcome="succeeded")
    await bus.execute(Command(type="agent.cancel", target={"session_id": parent.id}, payload={}))
    assert parent.state is AgentState.CANCELLED
    runs_before = len([e for e in core.event_log.query_session(parent.id) if e.type == "run.started"])

    await deliver_child_completion_to_parent(core, child)

    assert parent.state is AgentState.CANCELLED  # 不复活
    assert len([e for e in core.event_log.query_session(parent.id) if e.type == "run.started"]) == runs_before
    inbox = core.mailbox.inbox(parent.id)
    assert inbox is not None and inbox.qsize() == 1
    assert "[Sub-agent finished]" in inbox.get_nowait()["content"]


@pytest.mark.asyncio
async def test_final_text_surfaces_recorded_failure_reason():
    """A4：崩溃子 agent 无最终消息时，回传文本必须带 run.finished 记录的
    真实失败原因，而不是 'see events' 死信息。"""
    from cloudra.runtime_v2.child_manifest import build_child_manifest

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "fail-text"}))
    project = next(iter(core.projects.values()))
    child = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "explorer", "query": "q"},
            )
        )
    ).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(
        child,
        outcome="failed",
        error="kaplam: ts_opt diverged at step 7",
        failure_kind=RunFailureKind.PIPELINE_INTERNAL,
    )

    manifest = build_child_manifest(core, child)
    text = manifest["final_summary"]
    # 失败原因来自 run.finished 的结构化字段，且来源可解释。
    assert manifest["final_summary_source"] == "run_error"
    assert "kaplam: ts_opt diverged at step 7" in text
    assert "see events" not in text


@pytest.mark.asyncio
async def test_child_report_waits_for_first_final_run_and_is_delivered_once(tmp_path):
    """A parked compute run is not a result; later runs cannot report twice."""
    from cloudra.runtime_v2.effects import EventDraft
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
    from cloudra.runtime_v2.subagent_bridge import deliver_child_completion_to_parent

    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "child-final"}))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"},
    ))).data
    child = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "explorer", "parent_session_id": parent.id},
    ))).data

    async def finish(text: str, action: str):
        run_id = await core.agent_host.start_run(child)
        await core.event_writer.commit(EventDraft(
            "agent.message_emitted", stream="agent", project_id=project.id,
            session_id=child.id, run_id=run_id,
            data={"sender": child.role_id, "content": text},
        ))
        await core.event_writer.commit(EventDraft(
            "agent.completion_gate", stream="agent", project_id=project.id,
            session_id=child.id, run_id=run_id,
            data={"action": action, "reason": "test", "source": "test"},
        ))
        await core.agent_host.finish_run(child, outcome="succeeded")
        await deliver_child_completion_to_parent(core, child, wake=False)

    def reports(kernel):
        return [
            e for e in kernel.event_log
            if e.type == "agent.message_injected" and e.session_id == parent.id
            and (e.data.get("manifest") or {}).get("kind") == "child_completion"
        ]

    await finish("still computing", "wait_background")
    assert reports(core) == []

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    assert reports(restored) == []

    core = restored
    child = core.agents[child.id]
    await finish("verified result", "allow_final")
    await deliver_child_completion_to_parent(core, child, wake=False)
    assert len(reports(core)) == 1
    assert reports(core)[0].data["manifest"]["final_summary"] == "verified result"

    await finish("unrelated follow-up", "allow_final")
    assert len(reports(core)) == 1

    again = RuntimeCore(strict_events=True)
    again.store = store
    restore_core(again, store)
    assert len(reports(again)) == 1


@pytest.mark.asyncio
async def test_restore_repairs_unreported_final_child_without_waking_parent(tmp_path):
    from cloudra.runtime_v2.persistence import RuntimeStore, restore_core

    store = RuntimeStore(tmp_path / "runtime.db")
    core = RuntimeCore(strict_events=True)
    core.store = store
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "child-repair"}))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"},
    ))).data
    child = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "explorer", "parent_session_id": parent.id},
    ))).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome="succeeded")

    restored = RuntimeCore(strict_events=True)
    restored.store = store
    restore_core(restored, store)
    reports = [
        e for e in restored.event_log
        if e.type == "agent.message_injected" and e.session_id == parent.id
        and (e.data.get("manifest") or {}).get("kind") == "child_completion"
    ]
    assert len(reports) == 1
    assert restored.agents[parent.id].state.value == "queued"
    assert restored.mailbox.inbox(parent.id).qsize() == 1

    again = RuntimeCore(strict_events=True)
    again.store = store
    restore_core(again, store)
    assert len([
        e for e in again.event_log
        if e.type == "agent.message_injected" and e.session_id == parent.id
        and (e.data.get("manifest") or {}).get("kind") == "child_completion"
    ]) == 1


@pytest.mark.asyncio
async def test_waiting_launcher_ignores_parked_child_run():
    from cloudra.runtime_v2.effects import EventDraft
    from cloudra.runtime_v2.subagent_bridge import _await_terminal

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "wait-child"}))).data
    parent = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"},
    ))).data
    child = (await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "explorer", "parent_session_id": parent.id},
    ))).data
    waiter = asyncio.create_task(_await_terminal(core, child.id))
    await asyncio.sleep(0)

    async def finish(action):
        run_id = await core.agent_host.start_run(child)
        await core.event_writer.commit(EventDraft(
            "agent.completion_gate", stream="agent", project_id=project.id,
            session_id=child.id, run_id=run_id,
            data={"action": action, "reason": "test", "source": "test"},
        ))
        await core.agent_host.finish_run(child, outcome="succeeded")

    await finish("wait_background")
    assert not waiter.done()
    await finish("allow_final")
    await asyncio.wait_for(waiter, timeout=1.0)


def test_managetool_schemas_match_bridge_returns():
    """A3 schema 诚实：report 不再有被忽略的 detail_level 参数、描述不再
    承诺完整推理/工具日志；swarm 输出 schema 删掉永不返回的 task_ids，
    补上 grouped-async 实际返回的 group_id/pending_count。"""
    from cloudra.tools.Managetool.get_subagent_report import (
        GetSubAgentReport_input_schema,
    )
    from cloudra.tools.Managetool.subagent_swarm import (
        SubAgentSwarm_output_schema,
    )

    assert "detail_level" not in GetSubAgentReport_input_schema.model_fields
    swarm_fields = SubAgentSwarm_output_schema.model_fields
    assert "task_ids" not in swarm_fields
    assert "group_id" in swarm_fields
    assert "session_ids" in swarm_fields
    assert "pending_count" in swarm_fields


@pytest.mark.asyncio
async def test_swarm_grouped_async_returns_group_handle_and_unique_ids():
    """grouped-async（is_wait=False + max_concurrency>0）：返回 group_id +
    pending_count，session_ids 为空（capped 组惰性 spawn，逐项 child id 经
    group 报告查询）；两次派发的 group_id 绝不相同（A5：无 loop.time() 碰撞）。
    """
    llm = RoleRoutedLLM([LLMResponse(content="x", stop_requested=True)])
    core, _, coordinator = await _setup(llm)
    await _wait_state(coordinator, "succeeded")

    args = {
        "agent_id": "a-1",
        "prompt_template": "scan {{item}}",
        "items": ["alpha", "beta", "gamma"],
        "is_wait": False,
        "max_concurrency": 2,
    }
    first = await handle_native_tool(
        core, coordinator, ToolCall(id="t1", name="subagent_swarm", arguments=args)
    )
    assert first.is_success is True
    gid = first.data["group_id"]
    assert gid.startswith("grp_")
    assert first.data["session_ids"] == []
    assert first.data["pending_count"] == 3

    second = await handle_native_tool(
        core, coordinator, ToolCall(id="t2", name="subagent_swarm", arguments=args)
    )
    assert second.is_success is True
    assert second.data["group_id"] != gid, "group_id must be unique per dispatch"

    # 组跑完后：报告给状态计数 + 逐项真实 child_session_id。
    group = core.launch_groups.get(gid)
    deadline = asyncio.get_running_loop().time() + 15.0
    while group.state != "finished":
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"launch group stuck: {group.summary()}")
        await asyncio.sleep(0.01)
    report = await handle_native_tool(
        core, coordinator, ToolCall(id="t3", name="get_subagent_report", arguments={"group_id": gid})
    )
    assert report.is_success is True
    assert report.data["state"] == "finished"
    assert {item["state"] for item in report.data["items"]} == {"succeeded"}
    child_ids = [item["child_session_id"] for item in report.data["items"]]
    assert all(child_ids) and len(set(child_ids)) == 3
    # 等第二组也落地，避免悬挂任务泄漏到后续用例。
    group2 = core.launch_groups.get(second.data["group_id"])
    while group2.state != "finished":
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"second launch group stuck: {group2.summary()}")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_swarm_and_launcher_spawn_share_legacy_identity():
    """D13 回归：swarm 与 launcher 派生的子 agent 走同一条身份映射——
    DAG 侧的 legacy id 由 role_id 经 legacy_agent_id_for_role 推出，
    绝不退回 session uuid（首个 swarm 曾以 session id 当 actor 的 bug）。"""
    from cloudra.base.role_identity import legacy_agent_id_for_role
    from cloudra.runtime_v2.policies.dag_stage import DagPolicyStage

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
            arguments={"agent_id": "a-4", "query": "rerun P", "is_wait": False},
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
