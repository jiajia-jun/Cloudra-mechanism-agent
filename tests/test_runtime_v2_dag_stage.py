"""DAG harness as a policy stage: gate blocks before graph exists."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    InvocationProtocol,
    OrchestrationMode,
    PermissionSet,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline


class FakeLLM:
    async def complete(self, agent, messages, tools, **_kwargs):
        return LLMResponse(
            content="",
            tool_calls=[ToolCall(id="tc1", name="submit_compute_job", arguments={"input_file": "ts.gjf"})],
        )


class FakeTools:
    async def execute(self, agent, call: ToolCall) -> ToolResult:
        return ToolResult(is_success=True, summary="written")


async def _agent(core):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    await CommandBus(core).execute(
        Command(
            type="project.create",
            payload={"name": "dag project", "settings": {"orchestration_mode": "dag_guided"}},
        )
    )
    project = next(iter(core.projects.values()))
    result = await CommandBus(core).execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    agent = result.data
    # 本文件测试用 FakeLLM 直接发业务工具调用，走传统协议；
    # 默认 javascript 协议只放 js_exec + 直接控制类，与 DAG 门槛无关。
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    return project, agent


@pytest.mark.asyncio
async def test_dag_stage_allows_compute_before_mechanism_accepted(tmp_path):
    """初始假设尚未被 Supervisor 接受时，计算入口仍可探索。"""
    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    project.workspace_dir = str(tmp_path)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(),
        tools=FakeTools(),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_dag",
        settings=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(write=True), tools=["*"]),
        inbox_messages=[],
        workspace_dir=str(tmp_path),
    )
    assert outcome.message == ""
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "dag.gate_blocked" not in types


@pytest.mark.asyncio
async def test_dag_stage_noop_in_standard_mode(tmp_path):
    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    agent.settings.orchestration_mode = OrchestrationMode.STANDARD
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=FakeLLM(),
        tools=FakeTools(),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_std",
        settings=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(write=True), tools=["*"]),
        inbox_messages=[],
        workspace_dir=str(tmp_path),
    )
    assert outcome.decision == "continue"
    assert "dag.gate_blocked" not in [e.type for e in core.event_log.query_session(agent.id)]


class StopLLM:
    def __init__(self, disposition: str = "complete") -> None:
        self.disposition = disposition

    async def complete(self, agent, messages, tools, **_kwargs):
        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="tc1",
                    name="stop",
                    arguments={
                        "reason": "done",
                        "final_answer": "x",
                        "delivery_disposition": self.disposition,
                    },
                )
            ],
        )


async def _run_stop(core, agent, tmp_path, stages=None):
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages or default_stages(),
        llm=StopLLM(),
        tools=FakeTools(),
    )
    return await pipeline.run_turn(
        agent=agent,
        run_id="run_stop",
        settings=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        workspace_dir=str(tmp_path),
    )


async def _drive_with_runner(core, agent, llm, tmp_path):
    """runner 级驱动：真实 AgentRunner + 脚本化 LLM，发消息开跑。

    Task 4A 后 stop 的交付审计统一在 runner 收尾前的结束门禁（不再发生在
    before_tool），凡涉及交付处置/门禁判定的用例都必须在这一层断言。
    """
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=llm,
        tools=FakeTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    await CommandBus(core).execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "go"},
        )
    )


async def _wait_terminal(agent, states=("succeeded", "failed"), timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value not in states:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected one of {states}")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_stop_complete_on_empty_delivery_graph_rejected_by_unified_gate(tmp_path):
    """Task 4A：声明 complete 但覆盖不完整时，显式 stop 不再在 before_tool
    被拦截，而是与纯文本最终回复一样到达 runner 收尾前的统一结束门禁——
    门禁判 continue_work 并把缺口清单反馈给下一轮；不落 succeeded、不登记
    交付处置；同一缺口反复无进展退出耗尽上限后 run 落 failed 并提示用户。"""
    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    project.workspace_dir = str(tmp_path)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_RECORD

    class AlwaysStopComplete:
        def __init__(self) -> None:
            self.calls = 0
            self.seen: list[list[dict]] = []

        async def complete(self, agent, messages, tools, **_kwargs):
            self.calls += 1
            self.seen.append(list(messages))
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id=f"tc{self.calls}",
                        name="stop",
                        arguments={
                            "reason": "done",
                            "final_answer": "x",
                            "delivery_disposition": "complete",
                        },
                    )
                ],
            )

    llm = AlwaysStopComplete()
    await _drive_with_runner(core, agent, llm, tmp_path)
    await _wait_terminal(agent, states=("failed",))
    # 无进展退出有界：恰好 3 次 continue_work 判定后耗尽。
    gates = [
        e
        for e in core.event_log.query_session(agent.id, types={"agent.completion_gate"})
    ]
    assert [e.data["action"] for e in gates] == ["continue_work"] * 3
    assert llm.calls == 3
    # 缺口清单反馈进了下一轮上下文（覆盖审计理由 + 空图缺口代码）。
    texts = [str(m.get("content")) for messages in llm.seen for m in messages]
    assert any("required coverage is missing" in text for text in texts)
    assert any("empty_delivery_graph" in text for text in texts)
    # 不登记交付处置；耗尽终态是 failed（可恢复），不伪报完成。
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(agent.project_id).init()
    with db.connect() as con:
        count = con.execute("SELECT COUNT(*) FROM dag_delivery_dispositions").fetchone()[0]
    assert count == 0
    emitted = [
        e for e in core.event_log.query_session(agent.id) if e.type == "agent.message_emitted"
    ]
    assert [e.data["content"] for e in emitted] == ["x"] * llm.calls
    warnings = core.event_log.query_session(agent.id, types={"agent.warning"})
    assert any("Completion gate" in str(e.data["message"]) for e in warnings)


@pytest.mark.asyncio
async def test_stop_partial_allowed_with_gaps_recorded(tmp_path):
    """partial 是合法的最终交付声明：统一结束门禁放行且审计落库一次。
    （Task 4A 迁移：记录发生在 runner 收尾边界，不再是 before_tool 预检的
    副作用，因此用 runner 级驱动断言。）"""
    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    project.workspace_dir = str(tmp_path)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_RECORD
    await _drive_with_runner(core, agent, StopLLM("partial"), tmp_path)
    await _wait_terminal(agent)
    assert agent.state.value == "succeeded"
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(agent.project_id).init()
    with db.connect() as con:
        rows = con.execute(
            "SELECT disposition FROM dag_delivery_dispositions ORDER BY rowid"
        ).fetchall()
    assert rows == [("partial",)]


@pytest.mark.asyncio
async def test_stop_suspends_without_audit_while_siblings_run(tmp_path):
    """项目里还有未终态的兄弟 agent：统一结束门禁判 wait_background——
    stop 是挂起等唤醒（run 收尾为 succeeded），不做交付审计、不落处置。
    （Task 4A 迁移：挂起判定从 before_tool 移到 runner 收尾边界。）"""
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    project.workspace_dir = str(tmp_path)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_RECORD
    bus = CommandBus(core)
    await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "explorer"},  # no query → stays queued (non-terminal)
        )
    )
    await _drive_with_runner(core, agent, StopLLM("complete"), tmp_path)
    await _wait_terminal(agent)
    assert agent.state.value == "succeeded"
    gates = [
        e
        for e in core.event_log.query_session(agent.id, types={"agent.completion_gate"})
    ]
    assert [e.data["action"] for e in gates] == ["wait_background"]
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(agent.project_id).init()
    with db.connect() as con:
        count = con.execute("SELECT COUNT(*) FROM dag_delivery_dispositions").fetchone()[0]
    assert count == 0


@pytest.mark.asyncio
async def test_stop_untouched_in_standard_mode(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _agent(core)
    agent.settings.orchestration_mode = OrchestrationMode.STANDARD
    outcome = await _run_stop(core, agent, tmp_path)
    assert outcome.decision == "stop"
    assert "dag.gate_blocked" not in [e.type for e in core.event_log.query_session(agent.id)]


def test_legacy_agent_id_mapping():
    """v2 role_id 映射到 DAG 图的 legacy assignee 词表（a-0..a-8）。"""
    from cloudra.runtime_v2.policies.dag_stage import DagPolicyStage

    assert DagPolicyStage._legacy_agent_id("coordinator") == "a-0"
    assert DagPolicyStage._legacy_agent_id("small_mol") == "a-4"
    assert DagPolicyStage._legacy_agent_id("dft") == "a-6"
    # 未知角色原样透传（不落错映射）
    assert DagPolicyStage._legacy_agent_id("custom_role") == "custom_role"
    from cloudra.base.role_identity import legacy_agent_id_for_role

    assert legacy_agent_id_for_role("a-4") == "a-4"


class StopNoDispositionLLM:
    """stop 不带 delivery_disposition——schema 缺省是 complete，运行时必须对齐。"""

    def __init__(self) -> None:
        self.calls = 0
        self.seen: list[list[dict]] = []

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls += 1
        self.seen.append(list(messages))
        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id=f"tc{self.calls}",
                    name="stop",
                    arguments={"reason": "done", "final_answer": "x"},
                )
            ],
        )


@pytest.mark.asyncio
async def test_stop_without_disposition_is_audited_as_complete(tmp_path):
    """缺省 delivery_disposition 与 schema 一致（complete）：guided 空图上缺省
    stop 按 complete 审计——判 continue_work（complete 被确定性拦截，绝不走
    partial 的 wait_review 审批路径），反馈点名 complete 声明，缺口无进展
    反复退出耗尽后落 failed，不登记任何交付处置。"""
    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    project.workspace_dir = str(tmp_path)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    llm = StopNoDispositionLLM()
    await _drive_with_runner(core, agent, llm, tmp_path)
    await _wait_terminal(agent, states=("failed",))
    gates = [
        e
        for e in core.event_log.query_session(agent.id, types={"agent.completion_gate"})
    ]
    assert [e.data["action"] for e in gates] == ["continue_work"] * 3
    assert all("complete was declared" in e.data["reason"] for e in gates)
    texts = [str(m.get("content")) for messages in llm.seen for m in messages]
    assert any("required coverage is missing" in text for text in texts)
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(agent.project_id).init()
    with db.connect() as con:
        count = con.execute("SELECT COUNT(*) FROM dag_delivery_dispositions").fetchone()[0]
    assert count == 0


@pytest.mark.asyncio
async def test_stop_suspends_while_reminder_pending(tmp_path):
    """D8.2：ReminderBroker 事件投影里还有 pending 提醒时，统一结束门禁判
    wait_background——stop 是挂起（succeeded），不审计、不落 disposition。
    （Task 4A 迁移：挂起判定在 runner 收尾边界；reminder 到点仍会唤醒。）"""
    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    project.workspace_dir = str(tmp_path)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_RECORD
    reminder = await core.reminders.handle(
        agent,
        ToolCall(
            id="t-rem",
            name="schedule",
            arguments={
                "action": "create",
                "message": "check the compute job",
                "delay_seconds": 3600,
            },
        ),
    )
    assert reminder.is_success
    try:
        # 空图上 complete 本来必被审计拦截；挂起优先于审计 ⇒ 放行且无记录
        await _drive_with_runner(core, agent, StopLLM("complete"), tmp_path)
        await _wait_terminal(agent)
        assert agent.state.value == "succeeded"
        gates = [
            e
            for e in core.event_log.query_session(agent.id, types={"agent.completion_gate"})
        ]
        assert [e.data["action"] for e in gates] == ["wait_background"]
        from cloudra.persistence.database import ConversationDB

        db = ConversationDB(agent.project_id).init()
        with db.connect() as con:
            count = con.execute(
                "SELECT COUNT(*) FROM dag_delivery_dispositions"
            ).fetchone()[0]
        assert count == 0
    finally:
        await core.reminders.close()


@pytest.mark.asyncio
async def test_non_stop_run_end_records_partial(tmp_path):
    """Task 4A：未调用 stop 的运行结束（纯文本最终回复）与显式 stop 到达同一
    结束门禁——隐式 disposition 由覆盖率推导（空图 → partial），dag_record
    下经审计明确记录后放行。旧的"未审计自动落 partial"捷径已删除。"""
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    class FinalMessageLLM:
        async def complete(self, agent, messages, tools, **_kwargs):
            return LLMResponse(content="final answer, no stop call")

    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=FinalMessageLLM(),
        tools=FakeTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(
        Command(
            type="project.create",
            payload={
                "name": "dag non-stop",
                "settings": {"orchestration_mode": "dag_record"},
            },
        )
    )
    project = next(iter(core.projects.values()))
    project.workspace_dir = str(tmp_path)
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={
                "role_id": "coordinator",
                "query": "run the mechanism",
                "settings": {"orchestration_mode": "dag_record"},
            },
        )
    )
    agent = result.data
    deadline = asyncio.get_running_loop().time() + 5.0
    while agent.state.value != "succeeded":
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}")
        await asyncio.sleep(0.01)

    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(project.id).init()
    with db.connect() as con:
        rows = con.execute(
            "SELECT disposition FROM dag_delivery_dispositions"
        ).fetchall()
    assert rows == [("partial",)]


@pytest.mark.asyncio
async def test_explicit_stop_does_not_double_record_partial(tmp_path):
    """显式 stop 的交付处置只在统一结束门禁记录一次（Task 4A 前由
    before_tool 审计 + on_run_end 补记两处分担，现已收口到单一边界）。"""
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=StopLLM("partial"),
        tools=FakeTools(),
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    await bus.execute(
        Command(
            type="project.create",
            payload={
                "name": "dag explicit stop",
                "settings": {"orchestration_mode": "dag_record"},
            },
        )
    )
    project = next(iter(core.projects.values()))
    project.workspace_dir = str(tmp_path)
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={
                "role_id": "coordinator",
                "query": "run it",
                "settings": {"orchestration_mode": "dag_record"},
            },
        )
    )
    agent = result.data
    deadline = asyncio.get_running_loop().time() + 5.0
    while agent.state.value != "succeeded":
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}")
        await asyncio.sleep(0.01)

    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(project.id).init()
    with db.connect() as con:
        rows = con.execute(
            "SELECT disposition FROM dag_delivery_dispositions"
        ).fetchall()
    assert rows == [("partial",)]
