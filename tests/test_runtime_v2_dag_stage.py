"""DAG harness as a policy stage: gate blocks before graph exists."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
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
    return project, result.data


@pytest.mark.asyncio
async def test_dag_stage_blocks_compute_before_mechanism_accepted(tmp_path):
    """机理草稿未被接受前，计算入口（submit_compute_job）被 dag 门槛拦截。"""
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
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        workspace_dir=str(tmp_path),
    )
    assert outcome.message.startswith("blocked by dag")
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "dag.gate_blocked" in types


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
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
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


@pytest.mark.asyncio
async def test_stop_complete_blocked_on_empty_delivery_graph(tmp_path):
    """dag 模式下声明 complete 但机理图是空的 → 交付审计拦截 stop。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _agent(core)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_RECORD
    outcome = await _run_stop(core, agent, tmp_path, stages=default_stages(core))
    assert outcome.decision == "continue"
    assert "coverage audit" in outcome.content
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "dag.gate_blocked" in types


@pytest.mark.asyncio
async def test_stop_partial_allowed_with_gaps_recorded(tmp_path):
    """partial 是合法的最终交付声明：放行且审计落库。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _agent(core)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_RECORD
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=StopLLM("partial"),
        tools=FakeTools(),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_stop_partial",
        settings=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        workspace_dir=str(tmp_path),
    )
    assert outcome.decision == "stop"
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(agent.project_id).init()
    with db.connect() as con:
        rows = con.execute(
            "SELECT disposition FROM dag_delivery_dispositions ORDER BY rowid"
        ).fetchall()
    assert rows and rows[-1][0] == "partial"


@pytest.mark.asyncio
async def test_stop_suspends_without_audit_while_siblings_run(tmp_path):
    """项目里还有未终态的兄弟 agent：stop 是挂起等唤醒，不做交付审计。"""
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    core = RuntimeCore(strict_events=True)
    project, agent = await _agent(core)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_RECORD
    bus = CommandBus(core)
    await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "explorer"},  # no query → stays queued (non-terminal)
        )
    )
    outcome = await _run_stop(core, agent, tmp_path, stages=default_stages(core))
    assert outcome.decision == "stop"
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "dag.gate_blocked" not in types


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
    from cloudra.subagents.registry import legacy_agent_id_for_role

    assert legacy_agent_id_for_role("a-4") == "a-4"


@pytest.mark.asyncio
async def test_supervision_shell_agent_lifecycle(tmp_path):
    """督导运行投影为壳 agent：start→running，finish→succeeded + 摘要消息；
    下一次督导复用同一个 shell（restart 而非新建）。"""
    from cloudra.runtime_v2.policies.dag_stage import _SupervisionShell
    from cloudra.runtime_v2.schemas import AgentState

    class FakeResult:
        rounds = 1
        note = "plan ok"
        report = "reviewed the hypothesis"
        mutations = [{"accepted": True}, {"accepted": False}]

    core = RuntimeCore(strict_events=True)
    _, parent = await _agent(core)
    shell = _SupervisionShell(core, parent)

    await shell("start", "new_evidence", None, None)
    sup = shell.shell
    assert sup is not None
    assert sup.role_id == "supervisor"
    assert sup.parent_session_id == parent.id
    assert sup.state is AgentState.RUNNING

    await shell("finish", "new_evidence", FakeResult(), None)
    assert sup.state is AgentState.SUCCEEDED
    emitted = core.event_log.query_session(sup.id, types={"agent.message_emitted"})
    assert "mutations=1/2" in emitted[-1].data["content"]

    # 第二次督导复用同一 shell（restart 路径），不新增 agent
    await shell("start", "delivery_updated", None, None)
    assert shell.shell.id == sup.id
    assert sup.state is AgentState.RUNNING
    await shell("finish", "delivery_updated", None, "supervisor boom")
    assert sup.state is AgentState.FAILED
    emitted = core.event_log.query_session(sup.id, types={"agent.message_emitted"})
    assert "supervisor boom" in emitted[-1].data["content"]

    supervisors = [a for a in core.agents.values() if a.role_id == "supervisor"]
    assert len(supervisors) == 1


@pytest.mark.asyncio
async def test_supervision_shell_survives_spawn_rejection(tmp_path):
    """shell spawn 被拒（如旧快照缺 supervisor 角色）时督导本体照常运行，
    只是没有 UI 投影——不能把父 agent 的 turn 打崩。"""
    from cloudra.runtime_v2.policies.dag_stage import _SupervisionShell

    core = RuntimeCore(strict_events=True)
    _, parent = await _agent(core)
    # 模拟旧快照恢复后注册表缺 supervisor 角色
    core.roles._roles.pop("supervisor")
    shell = _SupervisionShell(core, parent)

    await shell("start", "coordinator_message", None, None)
    assert shell.shell is None
    # finish 也必须是 no-op，不能崩
    await shell("finish", "coordinator_message", None, None)
    rejected = [e for e in list(core.event_log) if e.type == "agent.spawn_rejected"]
    assert rejected and "unknown role" in rejected[-1].data["message"]


class StopNoDispositionLLM:
    """stop 不带 delivery_disposition——D8.1 前会缺省成 complete。"""

    async def complete(self, agent, messages, tools, **_kwargs):
        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="tc1",
                    name="stop",
                    arguments={"reason": "done", "final_answer": "x"},
                )
            ],
        )


@pytest.mark.asyncio
async def test_stop_without_disposition_defaults_to_partial(tmp_path):
    """D8.1：缺省 delivery_disposition 是 partial——不再默认声称 complete，
    空图上也能放行并按 partial 落库。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _agent(core)
    agent.settings.orchestration_mode = OrchestrationMode.DAG_RECORD
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=StopNoDispositionLLM(),
        tools=FakeTools(),
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="run_stop_default",
        settings=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        workspace_dir=str(tmp_path),
    )
    assert outcome.decision == "stop"
    assert "dag.gate_blocked" not in [
        e.type for e in core.event_log.query_session(agent.id)
    ]
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(agent.project_id).init()
    with db.connect() as con:
        rows = con.execute(
            "SELECT disposition FROM dag_delivery_dispositions ORDER BY rowid"
        ).fetchall()
    assert rows and rows[-1][0] == "partial"


@pytest.mark.asyncio
async def test_stop_suspends_while_reminder_pending(tmp_path):
    """D8.2：ReminderBroker 事件投影里还有 pending 提醒时 stop 是挂起——
    不审计、不落 disposition（旧实现读 legacy 表，对 v2 提醒失明）。"""
    core = RuntimeCore(strict_events=True)
    _, agent = await _agent(core)
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
        outcome = await _run_stop(core, agent, tmp_path, stages=default_stages(core))
        assert outcome.decision == "stop"
        assert "dag.gate_blocked" not in [
            e.type for e in core.event_log.query_session(agent.id)
        ]
        from cloudra.persistence.database import ConversationDB

        db = ConversationDB(agent.project_id).init()
        with db.connect() as con:
            count = con.execute(
                "SELECT COUNT(*) FROM dag_delivery_dispositions"
            ).fetchone()[0]
        assert count == 0
    finally:
        await core.reminders.close()


async def _stub_summarizer(messages):
    # Tests never hit the network; run-end summarization is covered in
    # test_runtime_v2_context_tree.py with dedicated fakes.
    return "[RUN LOG]\nstub trajectory\n[HANDOVER]\nstub state"


@pytest.mark.asyncio
async def test_non_stop_run_end_records_partial(tmp_path):
    """D8.3：未调用 stop 的运行结束（最终消息路径）在 dag 模式下自动落
    partial——complete 只能来自被审计的显式 stop。"""
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
    core.runner = AgentRunner(core, pipeline, run_summarizer=_stub_summarizer)
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
    """显式 stop（已走审计落库）不会被 on_run_end 再补一条 partial。"""
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
    core.runner = AgentRunner(core, pipeline, run_summarizer=_stub_summarizer)
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
