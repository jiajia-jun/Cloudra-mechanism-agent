"""真实 dag_bind_evidence 工具入口的显式送审通知回归。

生产链路（2026-09-06-dag-guided-submission-notification 计划）：

    LLM traditional call / JS guest tools.dag_bind_evidence
      → InvocationService → LegacyToolExecutor → DagBindEvidence
      → submit_evidence_for_review → validate + atomic store.submit_call_reviews
      → DagToolOutput(result.attachments[].review_id/enqueued)
      → DagPolicyStage.after_tool → on_tool_finished
      → _trigger_supervisor_after_tool → notify_supervisor

送审方法只负责验证与原子持久化；通知的唯一所有权在运行时 DAG policy 的
完成钩子。本文件用生产同款装配（RuntimeCore + default_stages +
LegacyToolExecutor + InvocationService + TurnPipeline + AgentRunner）
锁定这条链，只有 LLM 是脚本替身。
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import cloudra.runtime_v2.supervision as supervision_mod
from cloudra.dag.controller import DagController
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentState,
    Command,
    InvocationProtocol,
    OrchestrationMode,
)
from cloudra.runtime_v2.supervision import reconcile_supervision
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

SUPERVISOR_ROLE_ID = "supervisor"
HOST_DIR = Path(__file__).resolve().parent.parent / "cloudra" / "runtime_v2" / "js_host"
HOST_AVAILABLE = (
    shutil.which("node") is not None
    and (HOST_DIR / "node_modules" / "quickjs-emscripten" / "package.json").is_file()
)

_TS_RESULT = {
    "is_success": True,
    "normal_termination": True,
    "imaginary_frequencies": [-518.3],
}

_BIND_CALL = ToolCall(
    id="submit-1",
    name="dag_bind_evidence",
    arguments={
        "attachments": [
            {
                "tool_call_id": "parse-1",
                "bind_target": "step1",
                "stage_kind": "ts_opt",
                "claim": "fixture evidence for the declared stage",
            }
        ]
    },
)


class _LatchedRoutingLLM:
    """按角色路由的脚本替身：coordinator 走脚本，supervisor 挂门闩。

    脚本耗尽后的 coordinator 轮次同样挂门闩——断言期间保持 run 打开，
    不触发 stop/退出审计等其它通知源（计划 Task 2.4 的隔离纪律）。
    带 **_kwargs 对齐真实 provider 签名。
    """

    def __init__(self, coordinator_responses: list[LLMResponse]) -> None:
        self.coordinator_responses = list(coordinator_responses)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.supervisor_calls = 0

    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id == SUPERVISOR_ROLE_ID:
            self.supervisor_calls += 1
            self.entered.set()
            await self.release.wait()
            return LLMResponse(content="mailbox drained; stop", stop_requested=True)
        if not self.coordinator_responses:
            await self.release.wait()
            return LLMResponse(content="done", stop_requested=True)
        return self.coordinator_responses.pop(0)


async def _stub_summarizer(messages):
    return "[RUN LOG]\nstub trajectory\n[HANDOVER]\nstub state"


async def _setup(
    llm, workspace, *, executor=None, project_settings: dict | None = None
) -> tuple[RuntimeCore, CommandBus, object, object, InvocationService]:
    """生产同款装配（对照 tests/test_runtime_v2_supervisor_tools.py::_setup）。"""
    core = RuntimeCore(strict_events=True)
    stages = default_stages(core)
    if executor is None:
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
        core, pipeline, retry_backoff=(0.01, 0.01), run_summarizer=_stub_summarizer
    )
    bus = CommandBus(core)
    settings = {"orchestration_mode": "dag_guided", **(project_settings or {})}
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={
                    "name": "dag-submission",
                    "workspace_dir": str(workspace),
                    "settings": settings,
                },
            )
        )
    ).data
    dag_stage = next(stage for stage in stages if stage.name == "dag")
    return core, bus, project, dag_stage, invocations


async def _spawn_coordinator(bus: CommandBus, project):
    """queued 启动（不带 query），先调协议/模式再由 agent.message 开跑。"""
    coordinator = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    coordinator.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    coordinator.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    return coordinator


async def _seed_staged_step_with_evidence(project_id: str, session_id: str) -> None:
    """建 r → step1 → p（ts_opt 契约，全 pending）并登记一条已完成证据。

    建图数据参考 tests/test_dag_tools.py::_seed_staged_step；同步准备集中
    在 worker 线程。证据登记走 DagController.on_tool_finished 的观察路径
    （无 core 只登记证据，不通知）。
    """

    def _graph() -> None:
        from cloudra.dag.engine import DagEngine
        from cloudra.dag.models import (
            AddEdge,
            AddNode,
            ElementaryStepEdge,
            GraphActor,
            MutationBatch,
            OccurrenceNode,
            StageState,
        )

        db = ConversationDB(project_id).init()
        store = DagStore(db)
        store.ensure_bundle(session_id)
        seeded = DagEngine(store).apply_batch(
            MutationBatch(
                session_id=session_id,
                actor=GraphActor.AGENT,
                actor_id="a-0",
                base_revisions=store.load_bundle().revisions,
                rationale="declare the stage contract for step1",
                operations=[
                    AddNode(
                        op="add_node",
                        graph="delivery",
                        node=OccurrenceNode(node_id="r", label="R", role="reactant"),
                    ),
                    AddNode(
                        op="add_node",
                        graph="delivery",
                        node=OccurrenceNode(node_id="p", label="P", role="product"),
                    ),
                    AddEdge(
                        op="add_edge",
                        graph="delivery",
                        edge=ElementaryStepEdge(
                            edge_id="step1",
                            source_node_id="r",
                            target_node_id="p",
                            stages=[StageState(kind="ts_opt")],
                        ),
                    ),
                ],
            )
        )
        assert seeded.accepted

    await asyncio.to_thread(_graph)
    from cloudra.dag.controller import DagController

    controller = DagController(
        ConversationDB(project_id),
        session_id,
        OrchestrationMode.DAG_GUIDED,
        conversation_id=project_id,
    )
    await controller.initialize()
    await controller.on_tool_finished(
        "parse-1", "log_parser", {"log_path": "ts.log"}, dict(_TS_RESULT)
    )


async def _wait_tool_finished(core, session_id: str, tool_call_id: str, timeout: float = 10.0):
    """事件等待点：轮询只作失败上限。after_tool 策略钩子（通知口）在
    tool.finished 落事件之前运行，观察到 finished 即保证通知窗口已关闭。"""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        events = [
            e
            for e in core.event_log.query_session(session_id)
            if e.type == "tool.finished" and e.data.get("tool_call_id") == tool_call_id
        ]
        if events:
            return events[0]
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"tool call {tool_call_id} never finished")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_real_bind_tool_notifies_after_persistence(tmp_path, monkeypatch):
    """真实 bind 工具送审成功入库后必须通知项目 Supervisor 恰好一次。

    红灯语义：送审持久化成功但通知次数为 0（工具内控制器无 core，内部
    通知静默跳过；运行时完成钩子不处理送审）。
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    llm = _LatchedRoutingLLM([LLMResponse(content="", tool_calls=[_BIND_CALL])])
    core, bus, project, _dag_stage, _invocations = await _setup(llm, workspace)
    coordinator = await _spawn_coordinator(bus, project)
    notified = asyncio.Event()

    def _pending_reviews():
        return DagStore(ConversationDB(project.id)).list_call_reviews("pending")

    real_notify = supervision_mod.notify_supervisor

    async def _wrapped_notify(core_, project_id_, *, reason=""):
        # 通知执行时，送审必须已经持久化（持久化先于通知的所有权边界）。
        pending = await asyncio.to_thread(_pending_reviews)
        assert any(review.source == "explicit" for review in pending), (
            "notification fired before the explicit review was persisted"
        )
        await real_notify(core_, project_id_, reason=reason)
        notified.set()

    notify = AsyncMock(side_effect=_wrapped_notify)
    monkeypatch.setattr(supervision_mod, "notify_supervisor", notify)
    try:
        await _seed_staged_step_with_evidence(project.id, coordinator.id)
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": coordinator.id},
                payload={"content": "submit the parsed evidence for review"},
            )
        )

        finished = await _wait_tool_finished(core, coordinator.id, "submit-1")
        assert finished.data["is_success"] is True
        # 断点断言：入库成功但通知未发生即为红灯。
        notify.assert_awaited_once()
        await asyncio.wait_for(notified.wait(), timeout=5)

        pending = await asyncio.to_thread(_pending_reviews)
        assert len(pending) == 1
        assert pending[0].source == "explicit"
        assert pending[0].tool_call_id == "parse-1"
        assert pending[0].claim == "fixture evidence for the declared stage"
        assert pending[0].suggested_target_id == "step1"
        assert pending[0].suggested_stage == "ts_opt"
        # 通知确实送达项目唯一 Supervisor（真实 notify 在包装内执行）。
        supervisor = supervision_mod.find_project_supervisor(core, project.id)
        assert supervisor is not None
        assert supervisor.role_id == SUPERVISOR_ROLE_ID
    finally:
        llm.release.set()
        await core.aclose()


# ---------------------------------------------------------------------------
# 通知矩阵（计划 Task 1.5）
# ---------------------------------------------------------------------------


def _attachment(claim: str, *, tool_call_id: str = "parse-1") -> dict:
    return {
        "tool_call_id": tool_call_id,
        "bind_target": "step1",
        "stage_kind": "ts_opt",
        "claim": claim,
    }


async def _invoke_bind(core, invocations, agent, project, call_id: str, attachments: list[dict]):
    """真实入口送审：InvocationService → LegacyToolExecutor → DagBindEvidence。"""
    ctx = PipelineContext(
        agent=agent,
        run_id=f"run-{call_id}",
        settings_snapshot=agent.settings.model_copy(deep=True),
        capabilities=agent.capabilities,
        inbox_messages=[],
        emit=lambda *args: None,
        workspace_dir=project.workspace_dir,
        notices=core.notices,
    )
    return await invocations.invoke(
        ctx,
        ToolCall(id=call_id, name="dag_bind_evidence", arguments={"attachments": attachments}),
    )


async def _counting_notify(monkeypatch):
    """包装真实 notify_supervisor 计数；真实逻辑照跑（spawn/状态表不变）。"""
    real_notify = supervision_mod.notify_supervisor
    notify = AsyncMock(side_effect=real_notify)
    monkeypatch.setattr(supervision_mod, "notify_supervisor", notify)
    return notify


async def _matrix_setup(tmp_path, monkeypatch):
    """queued coordinator + 种子图/证据 + notify 计数；不开任何 run。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    llm = _LatchedRoutingLLM([])
    core, bus, project, dag_stage, invocations = await _setup(llm, workspace)
    coordinator = await _spawn_coordinator(bus, project)
    await _seed_staged_step_with_evidence(project.id, coordinator.id)
    notify = await _counting_notify(monkeypatch)
    return core, bus, project, dag_stage, invocations, coordinator, notify, llm


def _review_rows(project_id: str):
    return DagStore(ConversationDB(project_id)).list_call_reviews(None)


@pytest.mark.asyncio
async def test_batch_of_new_attachments_notifies_once(tmp_path, monkeypatch):
    """新增多条一次：批量全部新建 pending review → 通知恰好一次。"""
    core, _bus, project, _stage, invocations, coordinator, notify, llm = await _matrix_setup(
        tmp_path, monkeypatch
    )
    try:
        outcome = await _invoke_bind(
            core, invocations, coordinator, project, "submit-batch",
            [_attachment("claim A"), _attachment("claim B")],
        )
        assert outcome.result is not None and outcome.result.is_success
        attachments = outcome.result.data["result"]["attachments"]
        assert [item["enqueued"] for item in attachments] == [True, True]
        assert attachments[0]["review_id"] != attachments[1]["review_id"]

        notify.assert_awaited_once()
        rows = await asyncio.to_thread(_review_rows, project.id)
        assert len(rows) == 2
    finally:
        llm.release.set()
        await core.aclose()


@pytest.mark.asyncio
async def test_mixed_new_and_duplicate_batch_notifies_once(tmp_path, monkeypatch):
    """新旧混合一次：批量内至少一条新建 → 通知一次；重复条目不另计。"""
    core, _bus, project, _stage, invocations, coordinator, notify, llm = await _matrix_setup(
        tmp_path, monkeypatch
    )
    try:
        first = await _invoke_bind(
            core, invocations, coordinator, project, "submit-a", [_attachment("claim A")]
        )
        first_id = first.result.data["result"]["attachments"][0]["review_id"]
        assert notify.await_count == 1

        mixed = await _invoke_bind(
            core, invocations, coordinator, project, "submit-mixed",
            [_attachment("claim A"), _attachment("claim B")],
        )
        attachments = mixed.result.data["result"]["attachments"]
        assert [item["enqueued"] for item in attachments] == [False, True]
        assert attachments[0]["review_id"] == first_id

        assert notify.await_count == 2
        rows = await asyncio.to_thread(_review_rows, project.id)
        assert len(rows) == 2
    finally:
        llm.release.set()
        await core.aclose()


@pytest.mark.asyncio
async def test_all_duplicate_batch_does_not_notify(tmp_path, monkeypatch):
    """全重复零次：同一 pending 声明幂等返回既有 review_id，不新增通知、
    DB 行数不增加。"""
    core, _bus, project, _stage, invocations, coordinator, notify, llm = await _matrix_setup(
        tmp_path, monkeypatch
    )
    try:
        first = await _invoke_bind(
            core, invocations, coordinator, project, "submit-a", [_attachment("claim A")]
        )
        first_id = first.result.data["result"]["attachments"][0]["review_id"]
        assert notify.await_count == 1

        dup = await _invoke_bind(
            core, invocations, coordinator, project, "submit-a2", [_attachment("claim A")]
        )
        assert dup.result is not None and dup.result.is_success
        [item] = dup.result.data["result"]["attachments"]
        assert item["enqueued"] is False
        assert item["review_id"] == first_id

        notify.assert_awaited_once()
        rows = await asyncio.to_thread(_review_rows, project.id)
        assert len(rows) == 1
    finally:
        llm.release.set()
        await core.aclose()


@pytest.mark.asyncio
async def test_failed_submission_does_not_notify(tmp_path, monkeypatch):
    """失败零次：送审校验拒绝（证据不可解析）→ 工具失败、无入库、不通知。"""
    core, _bus, project, _stage, invocations, coordinator, notify, llm = await _matrix_setup(
        tmp_path, monkeypatch
    )
    try:
        outcome = await _invoke_bind(
            core, invocations, coordinator, project, "submit-bad",
            [_attachment("claim X", tool_call_id="parse-missing")],
        )
        assert outcome.result is not None and outcome.result.is_success is False
        notify.assert_not_awaited()
        rows = await asyncio.to_thread(_review_rows, project.id)
        assert rows == []
    finally:
        llm.release.set()
        await core.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result_payload",
    [
        # 失败完成
        {"is_success": False, "accepted": False, "error": "stage not declared"},
        # 成功但回执缺 review_id
        {
            "is_success": True,
            "accepted": True,
            "result": {"attachments": [{"tool_call_id": "tc-x", "enqueued": True}]},
        },
        # 空回执
        {"is_success": True, "accepted": True, "result": {"attachments": []}},
        # 无内层 result（dag_record 直绑形态等）
        {"is_success": True, "accepted": True},
    ],
    ids=["failure", "no-review-id", "empty-attachments", "no-result"],
)
async def test_bind_completions_without_new_receipt_do_not_notify(
    tmp_path, result_payload
):
    """无新建回执的 bind 完成不通知（payload 形状矩阵）。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(type="project.create", payload={"name": "bind-quiet-matrix"})
        )
    ).data
    db = ConversationDB(project.id).init()
    controller = DagController(
        db, "s1", "dag_guided", conversation_id=project.id, core=core
    )
    try:
        await controller.on_tool_finished(
            "tc-bind", "dag_bind_evidence",
            {"attachments": [{"tool_call_id": "tc-x"}]}, result_payload,
        )
        assert supervision_mod.find_project_supervisor(core, project.id) is None
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_dag_record_bind_completion_does_not_notify(tmp_path):
    """dag_record 零次：模式门先于回执判据，record 模式的 bind 完成永不通知。"""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(type="project.create", payload={"name": "bind-record-quiet"})
        )
    ).data
    db = ConversationDB(project.id).init()
    controller = DagController(
        db, "s1", "dag_record", conversation_id=project.id, core=core
    )
    try:
        await controller.on_tool_finished(
            "tc-bind", "dag_bind_evidence",
            {"attachments": [{"tool_call_id": "tc-x"}]},
            {
                "is_success": True,
                "accepted": True,
                "result": {
                    "attachments": [{"review_id": "rev_1", "enqueued": True}]
                },
            },
        )
        assert supervision_mod.find_project_supervisor(core, project.id) is None
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_supervisor_own_tool_completions_do_not_notify(tmp_path, monkeypatch):
    """Supervisor 自身工具零次：督导的裁决完成经 DagPolicyStage.after_tool
    早退，不进完成钩子通知路径（无自我复核循环）。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    llm = _LatchedRoutingLLM([])
    core, bus, project, dag_stage, _invocations = await _setup(llm, workspace)
    supervisor = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": SUPERVISOR_ROLE_ID},
            )
        )
    ).data
    notify = await _counting_notify(monkeypatch)
    try:
        ctx = PipelineContext(
            agent=supervisor,
            run_id="sv-run",
            settings_snapshot=supervisor.settings.model_copy(deep=True),
            capabilities=supervisor.capabilities,
            inbox_messages=[],
            emit=lambda *args: None,
            workspace_dir=project.workspace_dir,
            notices=core.notices,
        )
        await dag_stage.after_tool(
            ctx,
            ToolCall(
                id="sv-review",
                name="dag_review_call",
                arguments={
                    "review_id": "rev_x", "target_id": "step1",
                    "stage_kind": "ts_opt", "verdict": "agree",
                },
            ),
            ToolResult(is_success=True, summary="ok", data={"accepted": True}),
        )
        notify.assert_not_awaited()
    finally:
        llm.release.set()
        await core.aclose()


# ---------------------------------------------------------------------------
# Task 2：跨协议真实 Supervisor 往返、状态表、恢复窗口
# ---------------------------------------------------------------------------


def _tool_events(core, session_id: str, tool_call_id: str) -> list[str]:
    return [
        e.type
        for e in core.event_log.query_session(session_id)
        if e.type.startswith("tool.") and e.data.get("tool_call_id") == tool_call_id
    ]


async def _wait_state(agent, state: str, timeout: float = 10.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


async def _wait_run_count(core, agent, count: int, timeout: float = 10.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        runs = [
            e for e in core.event_log.query_session(agent.id) if e.type == "run.started"
        ]
        if len(runs) >= count:
            return runs
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"expected {count} runs, got {len(runs)}")
        await asyncio.sleep(0.01)


async def _wait_child_tool_finished(core, session_id: str, tool_name: str, timeout: float = 15.0):
    """JS guest 子调用的完成事件等待点（轮询只作失败上限）。"""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        events = [
            e
            for e in core.event_log.query_session(session_id)
            if e.type == "tool.finished" and e.data.get("tool_name") == tool_name
        ]
        if events:
            return events[0]
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"guest tool {tool_name} never finished")
        await asyncio.sleep(0.01)


def _delivery_edge(project_id: str, edge_id: str = "step1"):
    graph = DagStore(ConversationDB(project_id)).load_snapshot().delivery
    return next(e for e in graph.edges if e.edge_id == edge_id)


_JS_BIND_CODE = (
    "const result = await tools.dag_bind_evidence({attachments: [{"
    'tool_call_id: "parse-1", bind_target: "step1", stage_kind: "ts_opt", '
    'claim: "fixture evidence for the declared stage"'
    "}]});"
    " text(result);"
)


class _AdjudicatingLLM:
    """真实 Supervisor 往返的脚本替身（带 **_kwargs 对齐真实 provider）。

    coordinator：走脚本；脚本耗尽后挂门闩——断言期间不触发 stop/退出审
    计、不发 dag_message_supervisor（计划 Task 2.4 的隔离纪律）。
    supervisor：dag_view 读取 → dag_review_call(agree) 裁决（review_id 从
    持久信箱读取）→ 纯文本收尾；javascript 分支经顶层 js_exec guest 程序。
    """

    def __init__(
        self,
        coordinator_responses: list[LLMResponse],
        *,
        supervisor_protocol: InvocationProtocol,
    ) -> None:
        self.coordinator_responses = list(coordinator_responses)
        self.supervisor_protocol = supervisor_protocol
        self.project_id: str | None = None
        self.release = asyncio.Event()
        self.supervisor_calls = 0

    def _pending_review_id(self) -> str:
        assert self.project_id is not None
        rows = DagStore(ConversationDB(self.project_id)).list_call_reviews("pending")
        assert len(rows) == 1, f"expected one pending review, got {len(rows)}"
        return rows[0].review_id

    async def _supervisor_turn(self) -> LLMResponse:
        self.supervisor_calls += 1
        turn = self.supervisor_calls
        if self.supervisor_protocol is InvocationProtocol.TRADITIONAL:
            if turn == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(id="sv-view", name="dag_view", arguments={})],
                )
            if turn == 2:
                review_id = await asyncio.to_thread(self._pending_review_id)
                return LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="sv-review",
                            name="dag_review_call",
                            arguments={
                                "review_id": review_id,
                                "target_id": "step1",
                                "stage_kind": "ts_opt",
                                "verdict": "agree",
                            },
                        )
                    ],
                )
            return LLMResponse(content="adjudicated; mailbox drained", stop_requested=True)
        if turn == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="sv-js-view",
                        name="js_exec",
                        arguments={
                            "code": "const view = await tools.dag_view({}); text(view);"
                        },
                    )
                ],
            )
        if turn == 2:
            review_id = await asyncio.to_thread(self._pending_review_id)
            code = (
                "const verdict = await tools.dag_review_call({"
                f"review_id: {json.dumps(review_id)}, "
                'target_id: "step1", stage_kind: "ts_opt", verdict: "agree"});'
                " text(verdict);"
            )
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="sv-js-review", name="js_exec", arguments={"code": code})],
            )
        return LLMResponse(content="adjudicated; mailbox drained", stop_requested=True)

    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id == SUPERVISOR_ROLE_ID:
            return await self._supervisor_turn()
        if not self.coordinator_responses:
            await self.release.wait()
            return LLMResponse(content="done", stop_requested=True)
        return self.coordinator_responses.pop(0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protocol",
    [
        InvocationProtocol.TRADITIONAL,
        pytest.param(
            InvocationProtocol.JAVASCRIPT,
            marks=pytest.mark.skipif(
                not HOST_AVAILABLE, reason="node>=22 + quickjs-emscripten required"
            ),
        ),
    ],
)
async def test_real_bind_notifies_supervisor_roundtrip(tmp_path, protocol):
    """端到端往返：真实 bind → 通知 → 真实 Supervisor 裁决 → 阶段绑定。

    端到端成功标准只看可观察结果（持久 review 状态、阶段绑定、事件生命
    周期、Supervisor 唯一性），不观察私有通知实现。
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    if protocol is InvocationProtocol.TRADITIONAL:
        bind_response = LLMResponse(content="", tool_calls=[_BIND_CALL])
    else:
        bind_response = LLMResponse(
            content="",
            tool_calls=[ToolCall(id="js-bind", name="js_exec", arguments={"code": _JS_BIND_CODE})],
        )
    llm = _AdjudicatingLLM([bind_response], supervisor_protocol=protocol)
    # 脚本 LLM 直接发业务工具调用：传统协议分支把项目默认协议固定为
    # traditional（默认 javascript 只放 js_exec + 直接控制类，顶层业务
    # 调用会被路由层拒绝）。
    project_settings = (
        {"defaults": {"invocation_protocol": "traditional"}}
        if protocol is InvocationProtocol.TRADITIONAL
        else None
    )
    core, bus, project, _dag_stage, _invocations = await _setup(
        llm, workspace, project_settings=project_settings
    )
    llm.project_id = project.id
    coordinator = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    coordinator.settings.invocation_protocol = protocol
    coordinator.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    supervisor = None
    try:
        await _seed_staged_step_with_evidence(project.id, coordinator.id)
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": coordinator.id},
                payload={"content": "submit the parsed evidence for review"},
            )
        )

        if protocol is InvocationProtocol.TRADITIONAL:
            finished = await _wait_tool_finished(core, coordinator.id, "submit-1")
            assert finished.data["is_success"] is True
            assert _tool_events(core, coordinator.id, "submit-1") == [
                "tool.requested",
                "tool.started",
                "tool.result_recorded",
                "tool.finished",
            ]
        else:
            finished = await _wait_child_tool_finished(
                core, coordinator.id, "dag_bind_evidence"
            )
            assert finished.data["is_success"] is True

        # 通知唤醒真实 Supervisor 完成裁决（不经私有通知实现观察）。
        deadline = asyncio.get_running_loop().time() + 15
        while supervisor is None:
            supervisor = supervision_mod.find_project_supervisor(core, project.id)
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("supervisor was never ensured after submission")
            await asyncio.sleep(0.01)
        await _wait_state(supervisor, "succeeded", timeout=20)

        # pending → 已裁决；目标阶段已绑定该证据。
        def _review_states() -> list[str]:
            return [row.state for row in _review_rows(project.id)]

        assert await asyncio.to_thread(_review_states) == ["reviewed"]
        edge = await asyncio.to_thread(_delivery_edge, project.id)
        stage = next(s for s in edge.stages if s.kind.value == "ts_opt")
        assert stage.status.value == "supported"
        assert edge.refs, "the adjudicated evidence ref must be attached to step1"

        # 项目内只有一个 Supervisor。
        supervisors = [
            a
            for a in core.agents.values()
            if a.project_id == project.id and a.role_id == SUPERVISOR_ROLE_ID
        ]
        assert len(supervisors) == 1

        if protocol is InvocationProtocol.TRADITIONAL:
            for call_id in ("sv-view", "sv-review"):
                assert _tool_events(core, supervisor.id, call_id) == [
                    "tool.requested",
                    "tool.started",
                    "tool.result_recorded",
                    "tool.finished",
                ]
        else:
            for session_id in (coordinator.id, supervisor.id):
                types = [e.type for e in core.event_log.query_session(session_id)]
                assert "program.submitted" in types
                assert "program.finished" in types
            for session_id, tool_name in (
                (coordinator.id, "dag_bind_evidence"),
                (supervisor.id, "dag_view"),
                (supervisor.id, "dag_review_call"),
            ):
                started = [
                    e
                    for e in core.event_log.query_session(session_id)
                    if e.type == "tool.started" and e.data.get("tool_name") == tool_name
                ]
                assert len(started) == 1
                child_id = started[0].data["tool_call_id"]
                assert _tool_events(core, session_id, child_id) == [
                    "tool.requested",
                    "tool.started",
                    "tool.result_recorded",
                    "tool.finished",
                ]
    finally:
        llm.release.set()
        await core.aclose()


class _SupervisorStateLLM:
    """状态表用例的脚本替身：supervisor 按 mode 行为，coordinator 挂门闩。

    mode：stop=每轮立即收尾；latch=首轮挂门闩直至释放；fail=持续抛错。
    """

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.release = asyncio.Event()
        self.entered = asyncio.Event()
        self.supervisor_calls = 0

    async def complete(self, agent, messages, tools, **_kwargs):
        if agent.role_id == SUPERVISOR_ROLE_ID:
            self.supervisor_calls += 1
            if self.mode == "fail":
                raise RuntimeError("supervisor LLM down")
            if self.mode == "latch" and not self.release.is_set():
                self.entered.set()
                await self.release.wait()
            return LLMResponse(content="mailbox drained; stop", stop_requested=True)
        await self.release.wait()
        return LLMResponse(content="done", stop_requested=True)


async def _spawn_project_supervisor(bus, project, *, query: str | None = "review the mailbox"):
    payload: dict = {"role_id": SUPERVISOR_ROLE_ID}
    if query:
        payload["query"] = query
    return (
        await bus.execute(
            Command(type="agent.spawn", target={"project_id": project.id}, payload=payload)
        )
    ).data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_state", ["succeeded", "running", "waiting", "failed", "cancelled"]
)
async def test_real_submission_respects_supervisor_state_table(tmp_path, target_state):
    """状态表在真实送审入口（不经 notify_supervisor 直调）：

    succeeded → wake 开新 run（run_id 更新）；running → 不 restart；
    waiting → 消息保留不绕过；failed/cancelled → 保留 pending 不新发 LLM。
    状态准备经 CommandBus/事件路径，不直接写 core 投影。
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    llm_mode = {
        "succeeded": "stop",
        "running": "latch",
        "waiting": "latch",
        "failed": "fail",
        "cancelled": "stop",
    }[target_state]
    llm = _SupervisorStateLLM(llm_mode)
    core, bus, project, _dag_stage, invocations = await _setup(llm, workspace)
    coordinator = await _spawn_coordinator(bus, project)
    supervisor = None
    try:
        await _seed_staged_step_with_evidence(project.id, coordinator.id)

        # 预置 Supervisor 到目标状态（全部经 CommandBus/事件路径）。
        if target_state == "cancelled":
            supervisor = await _spawn_project_supervisor(bus, project, query=None)
            await bus.execute(
                Command(type="agent.cancel", target={"session_id": supervisor.id}, payload={})
            )
            assert supervisor.state.value == "cancelled"
        else:
            supervisor = await _spawn_project_supervisor(bus, project)
            if target_state == "succeeded":
                await _wait_state(supervisor, "succeeded")
            elif target_state in {"running", "waiting"}:
                await asyncio.wait_for(llm.entered.wait(), timeout=5)
                assert supervisor.state.value == "running"
                if target_state == "waiting":
                    core.agent_host.transition(
                        supervisor,
                        AgentState.WAITING_APPROVAL,
                        reason="wait_approval",
                        run_id=supervisor.current_run.run_id,
                    )
            else:  # failed
                await _wait_state(supervisor, "failed")
        calls_before = llm.supervisor_calls

        # 真实送审入口：InvocationService → LegacyToolExecutor → after_tool 通知。
        outcome = await _invoke_bind(
            core, invocations, coordinator, project, "submit-state",
            [_attachment("state-table probe")],
        )
        assert outcome.result is not None and outcome.result.is_success

        # 各状态下待办都持久化保留。
        pending = await asyncio.to_thread(
            lambda: DagStore(ConversationDB(project.id)).list_call_reviews("pending")
        )
        assert len(pending) == 1 and pending[0].source == "explicit"

        if target_state == "succeeded":
            runs = await _wait_run_count(core, supervisor, 2)
            assert runs[1].run_id != runs[0].run_id
            await _wait_state(supervisor, "succeeded")
        elif target_state == "running":
            assert supervisor.state.value == "running"
            assert llm.supervisor_calls == calls_before
            runs = await _wait_run_count(core, supervisor, 1)
            assert len(runs) == 1
        elif target_state == "waiting":
            assert supervisor.state.value == "waiting_approval"
            inbox = core.mailbox.inbox(supervisor.id)
            assert inbox is not None and inbox.qsize() == 1
            runs = await _wait_run_count(core, supervisor, 1)
            assert len(runs) == 1
        else:  # failed / cancelled：保留 pending，不复活、不新发 LLM
            assert supervisor.state.value == target_state
            assert llm.supervisor_calls == calls_before
    finally:
        llm.release.set()
        await core.aclose()


class _CountingBindExecutor(LegacyToolExecutor):
    """统计 dag_bind_evidence 真实执行次数的 LegacyToolExecutor。"""

    def __init__(self, core) -> None:
        super().__init__(core)
        self.bind_calls = 0

    async def execute(self, agent, call, **kwargs):
        if call.name == "dag_bind_evidence":
            self.bind_calls += 1
        return await super().execute(agent, call, **kwargs)


@pytest.mark.asyncio
async def test_reconcile_recovers_submission_persisted_before_hook(tmp_path):
    """恢复窗口：真实 bind 工具单独入库（不经 after_tool，模拟"入库后、
    完成钩子前中断"），reconcile_supervision 补通知并处理 explicit pending；
    bind 绝不重新执行。
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    llm = _AdjudicatingLLM([], supervisor_protocol=InvocationProtocol.TRADITIONAL)
    executor = _CountingBindExecutor(None)
    core, bus, project, _dag_stage, _invocations = await _setup(
        llm,
        workspace,
        executor=executor,
        project_settings={"defaults": {"invocation_protocol": "traditional"}},
    )
    llm.project_id = project.id
    executor.core = core
    coordinator = await _spawn_coordinator(bus, project)
    supervisor = None
    try:
        await _seed_staged_step_with_evidence(project.id, coordinator.id)

        # 第一阶段：真实工具入口持久化，不运行 after_tool（直调 executor）。
        result = await executor.execute(
            coordinator,
            ToolCall(
                id="submit-crash",
                name="dag_bind_evidence",
                arguments={"attachments": [_attachment("persisted before the hook")]},
            ),
        )
        assert result.is_success
        assert executor.bind_calls == 1
        assert supervision_mod.find_project_supervisor(core, project.id) is None

        # 第二阶段：reconcile 扫描持久信箱补通知，Supervisor 裁决。
        await reconcile_supervision(core, project.id)
        deadline = asyncio.get_running_loop().time() + 15
        while supervisor is None:
            supervisor = supervision_mod.find_project_supervisor(core, project.id)
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("reconcile did not ensure the supervisor")
            await asyncio.sleep(0.01)
        await _wait_state(supervisor, "succeeded", timeout=20)

        states = await asyncio.to_thread(
            lambda: [row.state for row in _review_rows(project.id)]
        )
        assert states == ["reviewed"]
        edge = await asyncio.to_thread(_delivery_edge, project.id)
        stage = next(s for s in edge.stages if s.kind.value == "ts_opt")
        assert stage.status.value == "supported"
        assert executor.bind_calls == 1, "reconcile must not re-execute the bind"
    finally:
        llm.release.set()
        await core.aclose()


@pytest.mark.asyncio
async def test_notification_failure_keeps_backlog_for_reconcile(tmp_path, monkeypatch):
    """通知抛错：工具已持久化的送审记录仍在（工具成功、pending 保留），
    恢复 notify 后 reconcile 补通知并完成裁决。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    llm = _AdjudicatingLLM([], supervisor_protocol=InvocationProtocol.TRADITIONAL)
    core, bus, project, _dag_stage, invocations = await _setup(
        llm,
        workspace,
        project_settings={"defaults": {"invocation_protocol": "traditional"}},
    )
    llm.project_id = project.id
    coordinator = await _spawn_coordinator(bus, project)
    supervisor = None

    real_notify = supervision_mod.notify_supervisor
    channel = {"down": True}

    async def _flaky_notify(core_, project_id_, *, reason=""):
        if channel["down"]:
            raise RuntimeError("notification channel down")
        await real_notify(core_, project_id_, reason=reason)

    monkeypatch.setattr(supervision_mod, "notify_supervisor", _flaky_notify)
    try:
        await _seed_staged_step_with_evidence(project.id, coordinator.id)
        outcome = await _invoke_bind(
            core, invocations, coordinator, project, "submit-flaky",
            [_attachment("survives notification failure")],
        )
        # 通知失败不回滚：工具成功、送审已持久化、Supervisor 未启动。
        assert outcome.result is not None and outcome.result.is_success
        pending = await asyncio.to_thread(
            lambda: DagStore(ConversationDB(project.id)).list_call_reviews("pending")
        )
        assert len(pending) == 1
        assert supervision_mod.find_project_supervisor(core, project.id) is None

        channel["down"] = False
        await reconcile_supervision(core, project.id)
        deadline = asyncio.get_running_loop().time() + 15
        while supervisor is None:
            supervisor = supervision_mod.find_project_supervisor(core, project.id)
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("reconcile did not recover the notification")
            await asyncio.sleep(0.01)
        await _wait_state(supervisor, "succeeded", timeout=20)
        states = await asyncio.to_thread(
            lambda: [row.state for row in _review_rows(project.id)]
        )
        assert states == ["reviewed"]
    finally:
        llm.release.set()
        await core.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["failed", "cancelled"])
async def test_reconcile_does_not_resurrect_terminal_supervisor(tmp_path, target_state):
    """failed/cancelled 的恢复行为遵守状态表：reconcile 不复活终态
    Supervisor，持久 pending 保留，不新发 LLM、不开新 run。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    llm = _SupervisorStateLLM("fail" if target_state == "failed" else "stop")
    executor = _CountingBindExecutor(None)
    core, bus, project, _dag_stage, _invocations = await _setup(llm, workspace, executor=executor)
    executor.core = core
    coordinator = await _spawn_coordinator(bus, project)
    try:
        await _seed_staged_step_with_evidence(project.id, coordinator.id)
        if target_state == "cancelled":
            supervisor = await _spawn_project_supervisor(bus, project, query=None)
            await bus.execute(
                Command(type="agent.cancel", target={"session_id": supervisor.id}, payload={})
            )
        else:
            supervisor = await _spawn_project_supervisor(bus, project)
            await _wait_state(supervisor, "failed")
        calls_before = llm.supervisor_calls

        result = await executor.execute(
            coordinator,
            ToolCall(
                id="submit-terminal",
                name="dag_bind_evidence",
                arguments={"attachments": [_attachment("backlog for terminal supervisor")]},
            ),
        )
        assert result.is_success
        await reconcile_supervision(core, project.id)

        assert supervisor.state.value == target_state
        assert llm.supervisor_calls == calls_before
        pending = await asyncio.to_thread(
            lambda: DagStore(ConversationDB(project.id)).list_call_reviews("pending")
        )
        assert len(pending) == 1 and pending[0].source == "explicit"
    finally:
        llm.release.set()
        await core.aclose()
