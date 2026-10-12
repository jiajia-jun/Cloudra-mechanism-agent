"""Task 2：真实 Supervisor agent 接入普通推理与工具生命周期。

Supervisor（role_id="supervisor"）由 AgentRunner / TurnPipeline /
InvocationService 驱动，与普通 agent 同一条生命周期；工具面由
registry/capabilities 的 supervisor_access 投影收窄（线缆隐藏 +
PermissionStage 拒绝 + SupervisorToolExecutor 执行层硬拒三层），
路径/动作守卫保留，且督导自身读证据不产生自我复核循环。

对照组：tests/test_dag_supervisor_tools.py 直接测 SupervisorToolExecutor
执行层；本文件测它作为 runtime_v2 普通 agent 的端到端行为。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.adapters import LegacyToolExecutor, _LegacyAgentBridge
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command, InvocationProtocol
from cloudra.runtime_v2.tool_catalog import (
    guest_tool_names,
    tool_declarations,
    wire_tool_schemas,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline
from cloudra.tools import capabilities

SUPERVISOR_ROLE_ID = "supervisor"
HOST_DIR = Path(__file__).resolve().parent.parent / "cloudra" / "runtime_v2" / "js_host"
HOST_AVAILABLE = (
    shutil.which("node") is not None
    and (HOST_DIR / "node_modules" / "quickjs-emscripten" / "package.json").is_file()
)
ORCA_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "orca" / "co2_freq_orca42.out"


class ScriptedLLM:
    """顺序弹出脚本的 fake LLM（签名对齐真实 provider，带 **_kwargs）。"""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)

    async def complete(self, agent, messages, tools, **_kwargs):
        assert self.responses, "no scripted LLM response left"
        return self.responses.pop(0)


async def _setup(llm, workspace: Path) -> tuple[RuntimeCore, CommandBus, object, object]:
    """生产同款装配（LegacyToolExecutor + 全量策略阶段），工作区指向 tmp。"""
    core = RuntimeCore(strict_events=True)
    stages = default_stages(core)
    executor = LegacyToolExecutor(core)
    invocations = InvocationService(
        event_writer=core.event_writer, stages=stages, tools=executor, agents=core.agents
    )
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=stages,
        llm=llm,
        tools=executor,
        notices=core.notices,
        invocations=invocations,
    )
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=(0.01, 0.01)
    )
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={"name": "sup-tools", "workspace_dir": str(workspace)},
            )
        )
    ).data
    dag_stage = next(stage for stage in stages if stage.name == "dag")
    return core, bus, project, dag_stage


async def _spawn_supervisor(
    bus: CommandBus, project, *, query: str | None = "review the supervision mailbox",
    protocol: InvocationProtocol | None = None,
):
    payload: dict = {"role_id": SUPERVISOR_ROLE_ID}
    if query:
        payload["query"] = query
    if protocol is not None:
        payload["settings"] = {"invocation_protocol": protocol.value}
    return (
        await bus.execute(
            Command(type="agent.spawn", target={"project_id": project.id}, payload=payload)
        )
    ).data


async def _wait_state(agent, state: str, timeout: float = 10.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


async def _pending_counts(project_id: str) -> dict[str, int]:
    """持久化督导待办（pending reviews / queued requests）计数；无库记零。"""

    def _read() -> dict[str, int]:
        db = ConversationDB(project_id)
        if not os.path.isfile(db.path):
            return {"call_reviews": 0, "review_requests": 0}
        db.migrate_if_needed()
        store = DagStore(db)
        return {
            "call_reviews": len(store.list_call_reviews("pending")),
            "review_requests": len(store.list_review_requests("queued")),
        }

    return await asyncio.to_thread(_read)


async def _teardown(core, *agents) -> None:
    bus = CommandBus(core)
    for agent in agents:
        if agent is None:
            continue
        if agent.state.value in {"queued", "running", "waiting_input", "waiting_approval"}:
            await bus.execute(
                Command(type="agent.cancel", target={"session_id": agent.id}, payload={})
            )
    tasks = [t for t in core.runner._tasks.values() if not t.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(0.05)  # detached run finalize（stub summarizer）收尾拍


def _tool_events(core, session_id: str, tool_call_id: str) -> list[str]:
    return [
        e.type
        for e in core.event_log.query_session(session_id)
        if e.type.startswith("tool.") and e.data.get("tool_call_id") == tool_call_id
    ]


# --- 身份与能力投影（无 LLM） ---


def test_supervisor_legacy_id_is_explicit_and_distinct():
    """supervisor 的 legacy id 是显式映射的可识别值，不是未知角色裸透传。"""
    from cloudra.base.role_identity import legacy_agent_id_for_role

    supervisor_id = legacy_agent_id_for_role("supervisor")
    assert supervisor_id != "supervisor", "bare passthrough collides with research roles"
    assert supervisor_id == "a-supervisor"
    research_ids = {
        legacy_agent_id_for_role(role)
        for role in (
            "coordinator", "explorer", "writer", "researcher",
            "small_mol", "md", "dft", "experiment", "env",
        )
    }
    assert supervisor_id not in research_ids


@pytest.mark.asyncio
async def test_supervisor_capabilities_and_wire_projection(tmp_path):
    """capabilities.tools 收窄到 supervisor_access 投影 + stop 直接控制类；
    两种协议的线缆投影一致地只暴露这套面。"""
    core, bus, project, _ = await _setup(ScriptedLLM([]), tmp_path)
    supervisor = await _spawn_supervisor(bus, project, query=None, protocol=None)
    try:
        expected = set(capabilities.supervisor_allowed_tools()) | {"stop"}
        assert set(supervisor.capabilities.tools) == expected
        for name in ("dag_review_step", "dag_accept_mechanism", "log_parser", "read", "write", "edit", "stop"):
            assert name in supervisor.capabilities.tools
        for name in ("bash", "submit_compute_job", "qm_input_writer"):
            assert name not in supervisor.capabilities.tools
        # 裁决工具需要 guided 模式上下文（dag_review_step 在 record/standard 拒绝）。
        assert supervisor.settings.orchestration_mode.value == "dag_guided"

        # javascript（默认协议）：js_exec + stop 直接控制类，业务工具只进 guest 声明。
        js_names = {
            (schema.get("function") or {}).get("name")
            for schema in wire_tool_schemas(supervisor, supervisor.capabilities.tools)
        }
        assert js_names == {"js_exec", "stop"}
        guest = guest_tool_names(
            supervisor.capabilities.tools,
            orchestration_mode=supervisor.settings.orchestration_mode,
        )
        assert "log_parser" in guest and "dag_review_step" in guest
        assert "stop" not in guest and "bash" not in guest
        declarations = tool_declarations(
            supervisor.capabilities.tools,
            orchestration_mode=supervisor.settings.orchestration_mode,
        )
        assert "log_parser(args:" in declarations
        assert "bash(args:" not in declarations  # 工具描述文本里可出现 "bash" 字样

        # traditional：投影即收窄后的全集（含 stop），文档写限定 PROCESS.md。
        supervisor.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
        traditional_names = {
            (schema.get("function") or {}).get("name")
            for schema in wire_tool_schemas(supervisor, supervisor.capabilities.tools)
        }
        assert traditional_names == expected
    finally:
        await _teardown(core, supervisor)


@pytest.mark.asyncio
async def test_supervisor_bridge_identity(tmp_path):
    """_LegacyAgentBridge 对 supervisor 不再落 follower：type/orchestration_mode
    决定 dag 裁决工具的 actor=SUPERVISOR 与 guided 模式门。"""
    core, bus, project, _ = await _setup(ScriptedLLM([]), tmp_path)
    supervisor = await _spawn_supervisor(bus, project, query=None)
    try:
        bridge = _LegacyAgentBridge(supervisor, str(tmp_path))
        assert bridge.type == "supervisor"
        assert bridge.orchestration_mode == "dag_guided"
        assert bridge.name == "supervisor"
    finally:
        await _teardown(core, supervisor)


# --- 端到端：runner 驱动的真实督导工具生命周期 ---


@pytest.mark.asyncio
async def test_supervisor_reads_evidence_without_self_review_loop(tmp_path):
    """traditional 协议：两次 log_parser 读证据走完整 InvocationService 生命周期，
    事件挂在 supervisor 自己的 session 流上；pending review/queued request 数
    不增长（不产生自我复核）；正常 stop 落 succeeded，无 delivery 门禁痕迹。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copy(ORCA_FIXTURE, workspace / "co2_freq.out")
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="log_parser", arguments={"log_path": "co2_freq.out"})],
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc2", name="log_parser", arguments={"log_path": "co2_freq.out"})],
            ),
            LLMResponse(
                content="mailbox drained; nothing to adjudicate",
                tool_calls=[ToolCall(id="tc3", name="stop", arguments={"reason": "mailbox empty"})],
            ),
        ]
    )
    core, bus, project, dag_stage = await _setup(llm, workspace)
    supervisor = await _spawn_supervisor(
        bus, project, protocol=InvocationProtocol.TRADITIONAL
    )
    try:
        await _wait_state(supervisor, "succeeded")

        # Supervisor business reads use the restricted executor; only the
        # direct stop control reports validated inputs via LegacyToolExecutor.
        for call_id in ("tc1", "tc2", "tc3"):
            assert _tool_events(core, supervisor.id, call_id) == [
                "tool.requested",
                "tool.started",
                *(["tool.progress"] if call_id == "tc3" else []),
                "tool.result_recorded",
                "tool.finished",
            ]
        finished = {
            e.data["tool_call_id"]: e
            for e in core.event_log.query_session(supervisor.id)
            if e.type == "tool.finished"
        }
        assert finished["tc1"].data["is_success"] is True
        assert finished["tc1"].data["status"] == "completed"
        assert '"engine": "orca"' in finished["tc1"].data["result_summary"]

        # 不产生自我复核：督导的读不创建 review，也不产生退出审批请求。
        assert await _pending_counts(project.id) == {"call_reviews": 0, "review_requests": 0}
        types = [e.type for e in core.event_log.query_session(supervisor.id)]
        assert "tool.blocked" not in types
        assert not any(e.type == "dag.gate_blocked" for e in core.event_log)
        # 督导不经 DagController 观察链。
        assert supervisor.id not in dag_stage._controllers
    finally:
        await _teardown(core, supervisor)


@pytest.mark.asyncio
async def test_supervisor_forbidden_and_out_of_bounds_calls_rejected(tmp_path):
    """双保险：bash 在 PermissionStage 被拒（wire 层本就不出现，见投影测试），
    越界 read 在执行层硬拒；两者都不打断 run 的正常结束。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret\n")
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="bash", arguments={"command": "echo hi"})],
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc2", name="read", arguments={"path": str(outside)})],
            ),
            LLMResponse(
                content="staying in my lane",
                tool_calls=[ToolCall(id="tc3", name="stop", arguments={"reason": "done"})],
            ),
        ]
    )
    core, bus, project, _ = await _setup(llm, workspace)
    supervisor = await _spawn_supervisor(
        bus, project, protocol=InvocationProtocol.TRADITIONAL
    )
    try:
        await _wait_state(supervisor, "succeeded")
        events = list(core.event_log.query_session(supervisor.id))

        # bash：capabilities 收窄 → PermissionStage block，绝不进入执行器。
        assert _tool_events(core, supervisor.id, "tc1") == ["tool.requested", "tool.blocked", "tool.finished"]
        blocked = next(e for e in events if e.type == "tool.blocked")
        assert blocked.data["tool_name"] == "bash"
        assert "capabilities" in blocked.data["message"]

        # 越界 read：read 在能力面内、过策略层，执行层路径守卫硬拒。
        assert _tool_events(core, supervisor.id, "tc2") == [
            "tool.requested",
            "tool.started",
            "tool.result_recorded",
            "tool.finished",
        ]
        denied = next(
            e for e in events if e.type == "tool.finished" and e.data["tool_call_id"] == "tc2"
        )
        assert denied.data["is_success"] is False
        assert "permission denied" in denied.data["result_summary"]
    finally:
        await _teardown(core, supervisor)


# --- javascript 协议 ---


@pytest.mark.asyncio
async def test_supervisor_js_mode_rejects_top_level_business_call(tmp_path):
    """JS 协议下顶层业务调用是协议错误，不执行（wire 路由层拒绝）。"""
    core, bus, project, _ = await _setup(
        ScriptedLLM(
            [
                LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="tc1",
                            name="dag_review_step",
                            arguments={"review_id": "rev_x", "target_id": "n1",
                                       "stage_kind": "geometry", "verdict": "agree"},
                        )
                    ],
                ),
                LLMResponse(
                    content="noted",
                    tool_calls=[ToolCall(id="tc2", name="stop", arguments={"reason": "done"})],
                ),
            ]
        ),
        tmp_path,
    )
    supervisor = await _spawn_supervisor(bus, project)  # 默认 javascript 协议
    try:
        await _wait_state(supervisor, "succeeded")
        # 顶层业务调用被路由层拒为普通反馈，不产生任何 tool.* 生命周期事件。
        assert _tool_events(core, supervisor.id, "tc1") == []
        assert _tool_events(core, supervisor.id, "tc2") == [
            "tool.requested",
            "tool.started",
            "tool.progress",
            "tool.result_recorded",
            "tool.finished",
        ]
        assert await _pending_counts(project.id) == {"call_reviews": 0, "review_requests": 0}
    finally:
        await _teardown(core, supervisor)


@pytest.mark.skipif(not HOST_AVAILABLE, reason="node>=22 + quickjs-emscripten required")
@pytest.mark.asyncio
async def test_supervisor_js_program_executes_allowed_guest_calls(tmp_path):
    """真实 JS 宿主：guest 程序里的 log_parser 经 InvocationService 串行执行，
    stop 作为顶层直接控制类结束 run；仍不产生自我复核。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copy(ORCA_FIXTURE, workspace / "co2_freq.out")
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc1",
                        name="js_exec",
                        arguments={
                            "code": (
                                'const r = await tools.log_parser({log_path: "co2_freq.out"});'
                                " text(r.data.engine);"
                            )
                        },
                    )
                ],
            ),
            LLMResponse(
                content="reviewed via guest program",
                tool_calls=[ToolCall(id="tc2", name="stop", arguments={"reason": "done"})],
            ),
        ]
    )
    core, bus, project, _ = await _setup(llm, workspace)
    supervisor = await _spawn_supervisor(bus, project)
    try:
        await _wait_state(supervisor, "succeeded")
        types = [e.type for e in core.event_log.query_session(supervisor.id)]
        assert "program.submitted" in types and "program.finished" in types
        child_calls = [
            e
            for e in core.event_log.query_session(supervisor.id)
            if e.type == "tool.started" and e.data.get("tool_name") == "log_parser"
        ]
        assert len(child_calls) == 1
        child_id = child_calls[0].data["tool_call_id"]
        assert _tool_events(core, supervisor.id, child_id) == [
            "tool.requested",
            "tool.started",
            "tool.result_recorded",
            "tool.finished",
        ]
        assert await _pending_counts(project.id) == {"call_reviews": 0, "review_requests": 0}
    finally:
        await _teardown(core, supervisor)


@pytest.mark.skipif(not HOST_AVAILABLE, reason="node>=22 + quickjs-emscripten required")
@pytest.mark.asyncio
async def test_research_agent_js_program_removes_node(tmp_path):
    """真实 JS 宿主：研究 agent（dag_record）的 guest 程序调用新删节点工具
    dag_remove_node，经 InvocationService 串行执行、不被误拦截；节点被真实
    删除。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import AddNode, GraphActor, MutationBatch, OccurrenceNode
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc1",
                        name="js_exec",
                        arguments={
                            "code": (
                                'const r = await tools.dag_remove_node({name: "orphan", '
                                'reason: "misbuilt element"});\n'
                                "const report = await tools.dag_delivery_report({});\n"
                                "text(r.is_success ? 'removed' : 'rejected');"
                            )
                        },
                    )
                ],
            ),
            LLMResponse(
                content="done",
                tool_calls=[
                    ToolCall(
                        id="tc2",
                        name="stop",
                        arguments={"reason": "done", "delivery_disposition": "partial"},
                    )
                ],
            ),
        ]
    )
    core, bus, project, _ = await _setup(llm, workspace)

    def _seed():
        db = ConversationDB(project.id)
        db.init()
        store = DagStore(db)
        store.ensure_bundle("seed")
        result = DagEngine(store).apply_batch(
            MutationBatch(
                session_id="seed",
                actor=GraphActor.AGENT,
                actor_id="a-0",
                base_revisions=store.load_bundle().revisions,
                rationale="seed a misbuilt node",
                operations=[
                    AddNode(
                        op="add_node",
                        graph="delivery",
                        node=OccurrenceNode(node_id="orphan", label="orphan"),
                    )
                ],
            )
        )
        assert result.accepted

    await asyncio.to_thread(_seed)
    coordinator = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={
                    "role_id": "coordinator",
                    "query": "remove the misbuilt node",
                    "settings": {"orchestration_mode": "dag_record"},
                },
            )
        )
    ).data
    try:
        await _wait_state(coordinator, "succeeded")
        child_calls = [
            e
            for e in core.event_log.query_session(coordinator.id)
            if e.type == "tool.started" and e.data.get("tool_name") == "dag_remove_node"
        ]
        assert len(child_calls) == 1
        child_id = child_calls[0].data["tool_call_id"]
        assert _tool_events(core, coordinator.id, child_id) == [
            "tool.requested",
            "tool.started",
            "tool.progress",
            "tool.result_recorded",
            "tool.finished",
        ]
        # 节点被真实删除
        snapshot = DagStore(ConversationDB(project.id)).load_snapshot()
        assert snapshot.delivery.nodes == []
    finally:
        await _teardown(core, coordinator)
