import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    AddNode,
    CoverageContract,
    GraphActor,
    MutationBatch,
    OccurrenceNode,
    PlannedNode,
    SetCoverageContract,
)
from cloudra.dag.store import DagStore
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store


def _api():
    try:
        from cloudra.core.supervisor import GraphSupervisor, GraphSupervisorResult
        from cloudra.dag.controller import DagController
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"DAG Supervisor API is missing: {exc}")
    return DagController, GraphSupervisor, GraphSupervisorResult


def _db(tmp_path, name, mode):
    db = ConversationDB(name, data_dir=tmp_path).init()
    session_store.create_session_record(
        db,
        session_id="s1",
        agent_id="a-0",
        agent_type="coordinator",
        parent_session_id=None,
        query="mechanism",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode=mode,
    )
    return db


class FakeSupervisor:
    """记录触发并返回空结果的 GraphSupervisor 替身。"""

    def __init__(self, report: str = ""):
        self.calls = []
        self.report = report

    async def run(
        self,
        trigger,
        coordinator_request=None,
        session_id=None,
        event_sink=None,
        **_kwargs,
    ):
        from cloudra.core.supervisor import GraphSupervisorResult

        self.calls.append(
            {
                "trigger": trigger,
                "coordinator_request": coordinator_request,
                "session_id": session_id,
                "event_sink": event_sink,
            }
        )
        return GraphSupervisorResult(trigger=trigger, report=self.report)


def _seed_delivery_hypothesis(store):
    engine = DagEngine(store)
    result = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="coordinator",
            base_revisions=store.load_bundle().revisions,
            rationale="Claisen hypothesis",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="r",
                        label="reactant",
                        evidence_level="proposed",
                    ),
                ),
            ],
        )
    )
    assert result.accepted


def _seed_ready_work(store, tool_name="ts_guess"):
    engine = DagEngine(store)
    result = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.SUPERVISOR,
            actor_id="supervisor",
            base_revisions=store.load_bundle().revisions,
            rationale="schedule work",
            operations=[
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id=f"work-{tool_name}",
                        label=tool_name,
                        status="ready",
                        priority=1,
                        tool_name=tool_name,
                    ),
                )
            ],
        )
    )
    assert result.accepted


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["standard", "dag_record"])
async def test_non_guided_modes_never_call_supervisor(tmp_path, mode):
    DagController, _, _ = _api()
    db = _db(tmp_path, f"supervisor-{mode}", mode)
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", mode, supervisor=supervisor)

    await controller.initialize()
    result = await controller.maybe_supervise("tool_call_review")

    assert result is None
    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_fresh_initialization_does_not_wake_supervisor(tmp_path):
    """fresh 会话两张图为空，初始化时不白白唤醒 Supervisor。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-fresh-init", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.initialize()

    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_initialize_does_not_auto_supervise_when_delivery_exists(tmp_path):
    """唤醒/续跑只加载图与契约，不在 initialize 时自动 graph_initialization。

    用户追加要求会再起 Coordinator；若此处拉 Supervisor 会与首轮指令抢拍，
    且模型常在 goal/stop 复核提示下空转。需要排产时走 delivery_updated /
    user_replan / pre_delivery。
    """
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-resume-init", "dag_guided")
    store = DagStore(db)
    store.ensure_bundle("s1")
    _seed_delivery_hypothesis(store)
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.initialize()

    assert supervisor.calls == []
    assert controller._initialized is True
    assert controller.contract is not None


@pytest.mark.asyncio
async def test_delivery_updated_passes_coordinator_request(tmp_path):
    """Coordinator 的 dag_add_species 被接受 → delivery_updated + rationale 传递。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-delivery-updated", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-dag-1",
        "dag_add_species",
        {
            "node_id": "r",
            "label": "reactant",
            "role": "reactant",
            "rationale": "Claisen chair pathway hypothesis",
        },
        {"is_success": True, "accepted": True},
    )

    assert [call["trigger"] for call in supervisor.calls] == ["delivery_updated"]
    request = supervisor.calls[0]["coordinator_request"]
    assert "Claisen chair pathway hypothesis" in request
    assert "dag_add_species" in request


@pytest.mark.asyncio
async def test_process_only_or_read_dag_tool_calls_do_not_trigger(tmp_path):
    """dag_view / 仅触及 process 的 dag_update_process_node 不触发 delivery_updated。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-dag-no-trigger", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-dag-view", "dag_view", {"graph_kind": "both"}, {"is_success": True}
    )
    await controller.on_tool_finished(
        "tc-dag-process",
        "dag_update_process_node",
        {"node_id": "x", "priority": 1},
        {"is_success": True, "accepted": True},
    )

    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_init_from_template_accepted_does_not_wake_supervisor(tmp_path):
    """graph_initialization 触发口已随 process 排产一起移除（Phase 2 唤醒表）：
    dag_init_from_template accepted 不再唤醒 Supervisor。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-init-wake", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-init",
        "dag_init_from_template",
        {"rationale": "start Claisen study"},
        {"is_success": True, "accepted": True},
    )

    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_remove_edge_rejection_does_not_wake_supervisor(tmp_path):
    """process 删边已随图移除（process_graph_removed），不再是 Supervisor 复核口。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-edge-removal", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-rm",
        "dag_remove_edge",
        {"graph": "process", "edge_id": "dep_a_b", "rationale": "no longer needed"},
        {
            "is_success": False,
            "accepted": False,
            "rejection_code": "process_graph_removed",
        },
    )

    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_ordinary_tool_success_does_not_trigger(tmp_path):
    """D5 节流：非 dag_review 工具（bash/文件读）不入箱也不唤醒 Supervisor。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-ordinary-quiet", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-1",
        "bash",
        {"command": "cat ts1.log"},
        {"is_success": True, "output": "normal termination"},
    )

    assert supervisor.calls == []
    from cloudra.dag.store import DagStore

    assert DagStore(db).list_call_reviews() == []


@pytest.mark.asyncio
async def test_log_parser_success_triggers_tool_call_review(tmp_path):
    """log_parser 成功 → 入 CallReview 收件箱 + tool_call_review 唤醒。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-new-evidence", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-2",
        "log_parser",
        {"log_path": "ts1.log"},
        {"is_success": True, "normal_termination": True, "scf_energy": -303.65},
    )

    assert [call["trigger"] for call in supervisor.calls] == ["tool_call_review"]
    from cloudra.dag.store import DagStore

    inbox = DagStore(db).list_call_reviews()
    assert len(inbox) == 1
    assert inbox[0].tool_name == "log_parser"
    assert inbox[0].is_success is True
    assert inbox[0].state == "pending"


@pytest.mark.asyncio
async def test_review_tool_failure_enqueues_with_failed_state(tmp_path):
    """dag_review 工具的失败调用也入箱（is_success=False）并唤醒 Supervisor
    复核；非复核工具的失败既不入箱也不唤醒。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-failure-quiet", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-3", "log_parser", {"log_path": "bad.log"}, {"is_success": False, "error": "parse error"}
    )
    await controller.on_tool_finished(
        "tc-4", "bash", {"command": "false"}, {"is_success": False, "error": "exit 1"}
    )

    assert [call["trigger"] for call in supervisor.calls] == ["tool_call_review"]
    from cloudra.dag.store import DagStore

    inbox = DagStore(db).list_call_reviews()
    assert [(row.tool_name, row.is_success) for row in inbox] == [
        ("log_parser", False)
    ]


def test_supervisor_may_strengthen_but_not_lower_coverage(tmp_path):
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-coverage", "dag_guided")
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    stronger = CoverageContract.mechanism_default(require_thermochemistry=True)
    accepted = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.SUPERVISOR,
            actor_id="supervisor",
            base_revisions=store.load_bundle().revisions,
            operations=[
                SetCoverageContract(op="set_coverage_contract", contract=stronger)
            ],
        )
    )
    lowered = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.SUPERVISOR,
            actor_id="supervisor",
            base_revisions=store.load_bundle().revisions,
            operations=[
                SetCoverageContract(
                    op="set_coverage_contract",
                    contract=CoverageContract.mechanism_default(),
                )
            ],
        )
    )

    assert accepted.accepted
    assert not lowered.accepted
    assert lowered.rejection_code == "actor_forbidden"


# --- GraphSupervisor agent 循环（复用 Agent 类 + dag_* 工具族） ---


class _FakeToolCall:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self, exclude_none=False):
        return self._payload


def _tool_call(call_id, arguments: dict, name: str = "dag_view"):
    return _FakeToolCall(
        {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }
    )


def _response(tool_calls=None, content=""):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    tool_calls=tool_calls or None,
                )
            )
        ]
    )


@pytest.mark.asyncio
async def test_graph_supervisor_agent_loop_accepts_mechanism_draft(tmp_path):
    """Supervisor 用 dag_view 自助读图后接受机理草稿，草稿落库为 accepted。"""
    _, GraphSupervisor, _ = _api()
    from cloudra.core.supervisor import SupervisorAgent
    from cloudra.dag.models import MechanismDraft

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-loop", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    from cloudra.dag.models import AddNode, OccurrenceNode

    store.save_draft(
        MechanismDraft(
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="r", label="reactant", role="reactant"),
                )
            ],
            rationale="Claisen hypothesis",
        ),
        actor_id="a-0",
    )

    supervisor = GraphSupervisor(conversation_id="supervisor-loop")
    agent = supervisor._ensure_agent()
    assert isinstance(agent, SupervisorAgent)
    view_then_accept = [
        _response([_tool_call("c-view", {})]),
        _response(
            [
                _tool_call(
                    "c-accept",
                    {"verdict": "accept"},
                    name="dag_accept_mechanism",
                )
            ]
        ),
        _response(content="草稿合理，已接受。"),
    ]
    object.__setattr__(agent, "llm_call", AsyncMock(side_effect=view_then_accept))

    result = await supervisor.run(
        "mechanism_proposed",
        coordinator_request="rationale: Claisen hypothesis",
        session_id="s1",
    )

    assert result.rounds == 2
    assert result.mutations[0]["accepted"] is True
    assert store.has_accepted_draft()
    engine = DagEngine(DagStore(ConversationDB("supervisor-loop", data_dir=tmp_path)))
    nodes = engine.snapshot().delivery.nodes
    assert [node.node_id for node in nodes] == ["r"]
    with db.connect() as con:
        actors = con.execute(
            "SELECT actor_type FROM dag_mutations WHERE accepted = 1"
        ).fetchall()
    assert [row[0] for row in actors] == ["harness"]

    # 上下文跨触发不清空：第二次触发后消息只增不减，且含首次触发内容。
    # 注意 get_context 返回的是 message_history 的活缓存列表，必须先取长度快照。
    context_after_first = await agent.get_context()
    len_after_first = len(context_after_first)
    assert any(
        "mechanism_proposed" in str(block.get("content", ""))
        for block in context_after_first
    )
    object.__setattr__(agent, "llm_call", AsyncMock(side_effect=[_response(content="无需变更。")]))
    await supervisor.run("tool_call_review", session_id="s1")
    context_after_second = await agent.get_context()
    assert len(context_after_second) > len_after_first
    assert any(
        "tool_call_review" in str(block.get("content", ""))
        for block in context_after_second
    )


@pytest.mark.asyncio
async def test_graph_supervisor_delivery_mutation_is_rejected_in_loop(tmp_path):
    """Supervisor 试图改机理图 → actor_forbidden 回到其上下文，可同轮改提
    合规的契约变更。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-readonly-delivery", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id="supervisor-readonly-delivery")
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
            _response(
                [
                    _tool_call(
                        "c-bad",
                        {
                            "node_id": "r",
                            "label": "reactant",
                            "role": "reactant",
                        },
                        name="dag_add_species",
                    )
                ]
            ),
            _response(
                [
                    _tool_call(
                        "c-good",
                        {"require_thermochemistry": True},
                        name="dag_set_coverage_contract",
                    )
                ]
            ),
            _response(content="已加严契约。"),
            ]
        )
    )

    result = await supervisor.run("mechanism_proposed", session_id="s1")

    assert result.mutations[0]["accepted"] is False
    assert result.mutations[0]["rejection_code"] == "actor_forbidden"
    assert result.mutations[1]["accepted"] is True
    context = await agent.get_context()
    assert any(
        "actor_forbidden" in str(block.get("content", "")) for block in context
    )


@pytest.mark.asyncio
async def test_graph_supervisor_llm_failure_returns_no_change(tmp_path):
    """LLM 故障不炸任务：返回无变更结果。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    ConversationDB("supervisor-llm-down", data_dir=tmp_path).init()
    supervisor = GraphSupervisor(conversation_id="supervisor-llm-down")
    agent = supervisor._ensure_agent()
    object.__setattr__(agent, "llm_call", AsyncMock(side_effect=RuntimeError("provider down")))

    result = await supervisor.run("tool_call_review", session_id="s1")

    assert result.mutations == []
    assert "llm_call failed" in result.note



@pytest.mark.asyncio
async def test_supervisor_run_registers_session_record(tmp_path):
    """guided 下每次触发登记一条 supervisor 子 Agent 会话并流转到 finished。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-session-record", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    result = await controller.maybe_supervise("tool_call_review")

    assert result is not None
    with db.connect() as con:
        rows = con.execute(
            "SELECT session_id, agent_id, agent_type, parent_session_id, state, query, result"
            " FROM session WHERE agent_id = 'supervisor'"
        ).fetchall()
    assert len(rows) == 1
    session_id, agent_id, agent_type, parent, state, query, summary = rows[0]
    assert session_id.startswith("supervisor_")
    assert agent_type == "supervisor"
    assert parent == "s1"
    assert state == "finished"
    assert "tool_call_review" in query
    assert "trigger=tool_call_review" in summary


@pytest.mark.asyncio
async def test_supervisor_exception_finalizes_failed_without_propagating(tmp_path):
    """Supervisor 是顾问角色：run 抛错不炸 Coordinator，会话落 failed。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-run-crash", "dag_guided")

    class CrashingSupervisor:
        async def run(self, trigger, coordinator_request=None, session_id=None, **_kwargs):
            raise RuntimeError("boom")

    controller = DagController(db, "s1", "dag_guided", supervisor=CrashingSupervisor())

    result = await controller.maybe_supervise("tool_call_review")

    assert result is None
    with db.connect() as con:
        rows = con.execute(
            "SELECT state, error FROM session WHERE agent_id = 'supervisor'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "failed"
    assert "boom" in rows[0][1]



@pytest.mark.asyncio
async def test_graph_view_result_not_truncated(tmp_path):
    """delivery 视图必须完整进入 Supervisor 上下文（可解析 JSON），写入时不再截断。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-view-truncation", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="harness",
            base_revisions=store.load_bundle().revisions,
            rationale="seed many occurrence nodes",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id=f"int-{i:02d}",
                        label=f"intermediate {i} " + "x" * 100,
                        role="intermediate",
                    ),
                )
                for i in range(30)
            ],
        )
    )
    assert seeded.accepted

    supervisor = GraphSupervisor(conversation_id="supervisor-view-truncation")
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
                _response([_tool_call("c-view", {"action": "view", "graph_kind": "delivery"})]),
                _response(content="看完了。"),
            ]
        ),
    )

    await supervisor.run("tool_call_review", session_id="s1")

    tool_contents = [
        str(b.get("content", "")) for b in await agent.get_context() if b.get("role") == "tool"
    ]
    assert tool_contents
    assert not any("结果过长被截断" in c for c in tool_contents)
    payload = json.loads(tool_contents[-1])
    assert payload["is_success"] is True
    assert payload["result"]["total_nodes"] == 30
    assert len(payload["result"]["nodes"]) == 30
    # 一页装得下时不重复附 index
    assert "index" not in payload["result"]
    # 摘要视图：无完整 refs 列表，只有计数
    assert "refs" not in payload["result"]["nodes"][0]
    assert "n_refs" in payload["result"]["nodes"][0]
    rendered = await agent.message_history.build_messages(
        identity_messages=[{"role": "system", "content": "supervisor"}],
    )
    rendered_tool = next(m for m in rendered if m.get("role") == "tool")
    assert "已截断" not in str(rendered_tool["content"])
    assert json.loads(rendered_tool["content"])["result"]["total_nodes"] == 30



@pytest.mark.asyncio
async def test_maybe_supervise_passes_event_sink(tmp_path):
    """session 登记成功时，controller 必须给 supervisor.run 带上事件出口。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-event-sink", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.maybe_supervise("tool_call_review")

    assert supervisor.calls[0]["event_sink"] is not None


@pytest.mark.asyncio
async def test_graph_supervisor_emits_render_events(tmp_path):
    """Supervisor 的运行过程经 event_sink 发出渲染事件：
    触发消息、推理正文、dag_view 调用与结果——TUI 窗口据此可见。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-render-events", data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id="supervisor-render-events")
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
                _response(
                    [_tool_call("c-view", {"action": "view"})],
                    content="先看看两张图的状态。",
                ),
                _response(content="前沿为空，需要安排构象搜索。"),
            ]
        ),
    )
    emitted = []

    async def sink(event_type, data):
        emitted.append((event_type, data))

    await supervisor.run("delivery_updated", session_id="s1", event_sink=sink)

    kinds = [k for k, _ in emitted]
    assert kinds[0] == "user_message"
    assert "delivery_updated" in emitted[0][1]["content"]
    assert "llm_chunk" in kinds
    chunk = next(d for k, d in emitted if k == "llm_chunk")
    assert chunk["delta"] == "先看看两张图的状态。"
    assert chunk["agent_name"] == "supervisor"
    assert "llm_stream_end" in kinds
    assert "tool_started" in kinds and "tool_finished" in kinds
    finished = next(d for k, d in emitted if k == "tool_finished")
    assert finished["tool"] == "dag_view"
    assert finished["result"]


@pytest.mark.asyncio
async def test_tool_crash_does_not_end_supervisor_run(tmp_path, monkeypatch):
    """回归：dag_view 工具内部异常必须以[System error]回喂 Supervisor 上下文，
    让它有机会调整，而不是把整个督导运行炸掉、session 落为 failed。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-tool-crash", data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    async def boom(self, user_input, session):
        raise RuntimeError("projection exploded")

    monkeypatch.setattr(
        "cloudra.tools.Plantool.dag_tools.dag_view.DagView.tool_call", boom
    )

    supervisor = GraphSupervisor(conversation_id="supervisor-tool-crash")
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
                _response([_tool_call("c-view", {"action": "view"})]),
                _response(content="工具异常，先结束本轮。"),
            ]
        ),
    )
    emitted = []

    async def sink(event_type, data):
        emitted.append((event_type, data))

    result = await supervisor.run("tool_call_review", session_id="s1", event_sink=sink)

    assert result.rounds == 1
    assert result.note == ""
    tool_contents = [
        str(b.get("content", "")) for b in await agent.get_context() if b.get("role") == "tool"
    ]
    assert any("[System error]" in c and "projection exploded" in c for c in tool_contents)
    # UI 事件流不悬空：tool_started 后必须跟 tool_finished
    kinds = [k for k, _ in emitted]
    assert "tool_started" in kinds and "tool_finished" in kinds


@pytest.mark.asyncio
async def test_supervisor_continues_past_old_round_cap(tmp_path):
    """完整排产常超过旧 16 轮预算；无 tool_calls 才结束，不被切断。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-no-cap", data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id="supervisor-no-cap")
    agent = supervisor._ensure_agent()
    n_views = 20
    responses = [
        _response([_tool_call(f"c-view-{i}", {"action": "view"})]) for i in range(n_views)
    ]
    responses.append(_response(content="已写入非模板 planned，请派 a-4。"))
    llm = AsyncMock(side_effect=responses)
    object.__setattr__(agent, "llm_call", llm)
    emitted = []

    async def sink(event_type, data):
        emitted.append((event_type, data))

    result = await supervisor.run("delivery_updated", session_id="s1", event_sink=sink)

    assert result.rounds == n_views
    assert result.note == ""
    assert "已写入非模板 planned" in result.report
    assert llm.await_count == n_views + 1
    started = [d for k, d in emitted if k == "tool_started"]
    assert len(started) == n_views


@pytest.mark.asyncio
async def test_wrapup_llm_failure_does_not_break_run(tmp_path):
    """空结束时的强制收尾 LLM 失败不影响运行：用兜底文案，异常被吞。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-wrapup-fail", data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id="supervisor-wrapup-fail")
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
                _response(content=""),
                RuntimeError("provider down at wrap-up"),
            ]
        ),
    )

    result = await supervisor.run("tool_call_review", session_id="s1")

    assert result.rounds == 0
    assert "llm_call failed" in result.note
    assert "Supervisor conclusion this turn" in result.report
    assert "tool_call_review" in result.report


@pytest.mark.asyncio
async def test_supervisor_folds_stale_view_results(tmp_path):
    """回归：每次触发追加 view 会让 Supervisor 上下文线性膨胀。新 view 成功后
    更早的 view 工具结果应折叠成一行占位，保留决策/mutate 记录。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-fold-views", data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id="supervisor-fold-views")
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
                _response([_tool_call("c1", {"action": "view"})]),
                _response([_tool_call("c2", {"action": "view"})]),
                _response(content="两张视图都看过了。"),
            ]
        ),
    )

    await supervisor.run("tool_call_review", session_id="s1")

    tool_blocks = [b for b in await agent.get_context() if b.get("role") == "tool"]
    assert len(tool_blocks) == 2
    assert "[Stale view folded]" in str(tool_blocks[0].get("content", ""))
    assert "delivery_gaps" in str(tool_blocks[1].get("content", ""))
    assert "[Stale view folded]" not in str(tool_blocks[1].get("content", ""))


@pytest.mark.asyncio
async def test_bind_evidence_acceptance_does_not_wake_supervisor(tmp_path):
    """dag_guided 下 dag_bind_evidence 已禁用；其完成事件不再是唤醒口——
    复核唤醒只走收件箱（tool_call_review）。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-bind-trigger", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-bind-1",
        "dag_bind_evidence",
        {
            "action": "bind_evidence",
            "tool_call_id": "tc-x",
            "bind_target": "step1",
            "stage_kind": "ts_opt",
        },
        {"is_success": True, "accepted": True},
    )

    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_failed_bind_and_review_evidence_do_not_trigger(tmp_path):
    """bind_evidence 被拒不触发；Supervisor 自己的 review_evidence 也不应唤醒自己。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-bind-quiet", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-bind-2",
        "dag_bind_evidence",
        {"action": "bind_evidence", "tool_call_id": "tc-x", "bind_target": "step1"},
        {"is_success": False, "accepted": False, "error": "did not succeed"},
    )
    await controller.on_tool_finished(
        "tc-review-1",
        "dag_review_evidence",
        {
            "action": "review_evidence",
            "bind_target": "step1",
            "verdict": "rejected",
            "rationale": "证据不成立",
        },
        {"is_success": True, "accepted": True},
    )

    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_empty_closing_forces_wrapup(tmp_path):
    """只 view 后空 content 结束 → 强制收尾，结论文本随 result.report 返回。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    conv = "supervisor-empty-report"
    db = ConversationDB(conv, data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id=conv)
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
                _response([_tool_call("c-view", {"action": "view"})]),
                _response(content=""),  # 空结束
                _response(content="未新增 planned：frontier 已覆盖 TS 优化缺口。"),
            ]
        ),
    )

    result = await supervisor.run("delivery_updated", session_id="s1")

    assert "未新增 planned" in result.report
    assert result.note == ""


@pytest.mark.asyncio
async def test_empty_turn_continues_and_can_mutate(tmp_path):
    """view 后空回复不得收尾禁工具；下一轮裁决必须真正落图。"""
    _, GraphSupervisor, _ = _api()
    from cloudra.dag.models import AddNode, MechanismDraft, OccurrenceNode

    get_config().data_dir = tmp_path
    conv = "supervisor-empty-then-mutate"
    db = ConversationDB(conv, data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    store.save_draft(
        MechanismDraft(
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="r", label="R", role="reactant"),
                )
            ],
            rationale="hypothesis",
        ),
        actor_id="a-0",
    )

    supervisor = GraphSupervisor(conversation_id=conv)
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
                _response([_tool_call("c-view", {"action": "view"})]),
                _response(content=""),
                _response([
                    _tool_call(
                        "c-mut",
                        {"verdict": "accept"},
                        name="dag_accept_mechanism",
                    )
                ]),
                _response(content="草稿已接受。"),
            ]
        ),
    )

    result = await supervisor.run("mechanism_proposed", session_id="s1")

    assert any(m.get("accepted") for m in result.mutations)
    assert "已接受" in result.report
    snapshot = DagEngine(DagStore(db)).snapshot()
    assert any(n.node_id == "r" for n in snapshot.delivery.nodes)
    context = await agent.get_context()
    assert any(
        "empty reply does not end" in str(b.get("content", ""))
        for b in context
        if b.get("role") == "user"
    )


@pytest.mark.asyncio
async def test_nonempty_closing_returns_content_directly(tmp_path):
    """有 content 结束 → 直接作为 report 返回，不再强制二次收尾。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    conv = "supervisor-direct-report"
    db = ConversationDB(conv, data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id=conv)
    agent = supervisor._ensure_agent()
    llm = AsyncMock(
        side_effect=[
            _response(content="已排产 work-ts-opt；请派 a-4。"),
        ]
    )
    object.__setattr__(agent, "llm_call", llm)

    result = await supervisor.run("delivery_updated", session_id="s1")

    assert result.report == "已排产 work-ts-opt；请派 a-4。"
    assert llm.await_count == 1


@pytest.mark.asyncio
async def test_empty_closing_wrapup_failure_uses_fallback_report(tmp_path):
    """强制收尾 LLM 失败时仍用确定性兜底文案钉住 Coordinator。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    conv = "supervisor-fallback-report"
    db = ConversationDB(conv, data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id=conv)
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
                _response(content=""),
                RuntimeError("provider down"),
            ]
        ),
    )

    result = await supervisor.run("delivery_updated", session_id="s1")

    assert "Supervisor conclusion this turn" in result.report
    assert "delivery_updated" in result.report
    assert "dag_message_supervisor" in result.report


def test_trigger_message_review_discipline_and_no_empty_end():
    """触发文案：草稿裁决 / 调用复核的纪律 + 禁止空结束。"""
    _, GraphSupervisor, _ = _api()
    draft = GraphSupervisor._trigger_message("mechanism_proposed", "rationale: add TS")
    assert "[Mechanism proposal rationale]" in draft
    assert "dag_accept_mechanism" in draft
    assert "empty replies are forbidden" in draft

    review = GraphSupervisor._trigger_message("tool_call_review", "rev_1: ts_guess")
    assert "[Pending call reviews]" in review
    assert "never supports ts_opt/frequency" in review
    assert "NOT a disposal" in review

    msg = GraphSupervisor._trigger_message("coordinator_message", "请复核")
    assert "[Coordinator message]请复核" in msg
    assert "empty replies are forbidden" in msg


@pytest.mark.asyncio
async def test_message_supervisor_triggers_coordinator_message(tmp_path):
    """Coordinator 的 message_supervisor → coordinator_message + 原文。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-coord-msg", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-msg-1",
        "dag_message_supervisor",
        {"message": "frontier 空，请补 TS 排产"},
        {"is_success": True, "accepted": True, "result": {"delivered": True}},
    )

    assert [call["trigger"] for call in supervisor.calls] == ["coordinator_message"]
    assert supervisor.calls[0]["coordinator_request"] == "frontier 空，请补 TS 排产"


@pytest.mark.asyncio
async def test_message_supervisor_empty_or_failed_does_not_trigger(tmp_path):
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-coord-msg-quiet", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-msg-2",
        "dag_message_supervisor",
        {"message": ""},
        {"is_success": True},
    )
    await controller.on_tool_finished(
        "tc-msg-3",
        "dag_message_supervisor",
        {"message": "hello"},
        {"is_success": False, "error": "oops"},
    )

    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_supervision_projection_failure_does_not_kill_run(tmp_path):
    """on_supervision 是 UI 投影回调：抛错（如壳会话 spawn 被拒）必须
    best-effort 降级——督导照常跑完，父 turn 不受连累。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervision-projection-crash", "dag_guided")
    supervisor = FakeSupervisor()

    async def exploding_projection(phase, trigger, result, error_note):
        raise RuntimeError("projection boom")

    controller = DagController(
        db, "s1", "dag_guided", supervisor=supervisor, on_supervision=exploding_projection
    )

    result = await controller.maybe_supervise("tool_call_review")

    assert result is not None
    assert [c["trigger"] for c in supervisor.calls] == ["tool_call_review"]
