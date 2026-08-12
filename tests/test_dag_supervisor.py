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

    def __init__(self):
        self.calls = []

    async def run(self, trigger, coordinator_request=None, session_id=None, event_sink=None):
        from cloudra.core.supervisor import GraphSupervisorResult

        self.calls.append(
            {
                "trigger": trigger,
                "coordinator_request": coordinator_request,
                "session_id": session_id,
                "event_sink": event_sink,
            }
        )
        return GraphSupervisorResult(trigger=trigger)


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
    result = await controller.maybe_supervise("new_evidence")

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
    """Coordinator 的 delivery mutate 被接受 → delivery_updated + rationale 传递。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-delivery-updated", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)
    arguments = {
        "action": "mutate",
        "base_revisions": {"process": 0, "delivery": 0},
        "rationale": "Claisen chair pathway hypothesis",
        "operations": [
            {
                "op": "add_node",
                "graph": "delivery",
                "data": {
                    "node_id": "r",
                    "node_type": "intermediate_occurrence",
                    "label": "reactant",
                    "payload": {"evidence_level": "proposed"},
                },
            }
        ],
    }

    await controller.on_tool_finished(
        "tc-dag-1", "dag_graph", arguments, {"success": True, "accepted": True}
    )

    assert [call["trigger"] for call in supervisor.calls] == ["delivery_updated"]
    request = supervisor.calls[0]["coordinator_request"]
    assert "Claisen chair pathway hypothesis" in request
    assert "add_node:delivery" in request


@pytest.mark.asyncio
async def test_process_only_or_read_dag_tool_calls_do_not_trigger(tmp_path):
    """dag_graph 的 view / 仅触及 process 的 mutate 不触发 delivery_updated。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-dag-no-trigger", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-dag-view", "dag_graph", {"action": "view"}, {"success": True}
    )
    await controller.on_tool_finished(
        "tc-dag-process",
        "dag_graph",
        {
            "action": "mutate",
            "rationale": "harness-side process note",
            "operations": [
                {
                    "op": "update_node",
                    "graph": "process",
                    "data": {"node_id": "x", "changes": {"priority": 1}},
                }
            ],
        },
        {"success": True, "accepted": True},
    )

    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_ordinary_tool_success_does_not_trigger(tmp_path):
    """普通工具成功（即使是空前沿）不再触发 Supervisor——触发口只有 log_parser 与图修改。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-ordinary-quiet", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-1",
        "reaction_mapping",
        {"reactant_smiles": "C=COCC=C"},
        {"is_success": True, "mapping_status": "unique"},
    )

    assert supervisor.calls == []


@pytest.mark.asyncio
async def test_log_parser_success_triggers_new_evidence(tmp_path):
    """gaussian_log_parser 成功落地新证据 → new_evidence。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-new-evidence", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-2",
        "gaussian_log_parser",
        {"log_path": "ts1.log"},
        {"success": True, "normal_termination": True, "scf_energy": -303.65},
    )

    assert [call["trigger"] for call in supervisor.calls] == ["new_evidence"]


@pytest.mark.asyncio
async def test_log_parser_failure_and_tool_failure_do_not_trigger(tmp_path):
    """log_parser 失败、任意工具失败都不触发 Supervisor。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-failure-quiet", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-3", "gaussian_log_parser", {"log_path": "bad.log"}, {"success": False, "error": "parse error"}
    )
    await controller.on_tool_finished(
        "tc-4", "ts_guess", {}, {"is_success": False, "error": "scf failed"}
    )

    assert supervisor.calls == []


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


# --- GraphSupervisor agent 循环（复用 Agent 类 + dag_graph 工具） ---


class _FakeToolCall:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self, exclude_none=False):
        return self._payload


def _tool_call(call_id, arguments: dict):
    return _FakeToolCall(
        {
            "id": call_id,
            "type": "function",
            "function": {"name": "dag_graph", "arguments": json.dumps(arguments)},
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
async def test_graph_supervisor_agent_loop_schedules_process_work(tmp_path):
    """Supervisor 用 dag_graph 自助读图后提交 process 变更，actor=supervisor 落库。"""
    _, GraphSupervisor, _ = _api()
    from cloudra.core.supervisor import SupervisorAgent

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-loop", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    _seed_delivery_hypothesis(store)

    supervisor = GraphSupervisor(conversation_id="supervisor-loop")
    agent = supervisor._ensure_agent()
    assert isinstance(agent, SupervisorAgent)
    view_then_mutate = [
        _response([_tool_call("c-view", {"action": "view"})]),
        _response(
            [
                _tool_call(
                    "c-mutate",
                    {
                        "action": "mutate",
                        "base_revisions": {"process": 0, "delivery": 1},
                        "rationale": "schedule endpoint validation",
                        "operations": [
                            {
                                "op": "add_node",
                                "graph": "process",
                                "data": {
                                    "node_id": "endpoint-opt",
                                    "node_type": "calculation",
                                    "label": "endpoint optimization",
                                    "payload": {"status": "ready", "priority": 20},
                                },
                            }
                        ],
                    },
                )
            ]
        ),
        _response(content="已安排好端点优化工作。"),
    ]
    object.__setattr__(agent, "llm_call", AsyncMock(side_effect=view_then_mutate))

    result = await supervisor.run(
        "delivery_updated",
        coordinator_request="rationale: Claisen hypothesis",
        session_id="s1",
    )

    assert result.rounds == 2
    assert result.mutations[0]["accepted"] is True
    engine = DagEngine(DagStore(ConversationDB("supervisor-loop", data_dir=tmp_path)))
    nodes = engine.snapshot().process.nodes
    assert [node.node_id for node in nodes] == ["endpoint-opt"]
    with db.connect() as con:
        actors = con.execute(
            "SELECT actor_type FROM dag_mutations WHERE accepted = 1"
        ).fetchall()
    assert [row[0] for row in actors] == ["agent", "supervisor"]

    # 上下文跨触发不清空：第二次触发后消息只增不减，且含首次触发内容。
    # 注意 get_context 返回的是 ContextManager 的活缓存列表，必须先取长度快照。
    context_after_first = await agent.get_context()
    len_after_first = len(context_after_first)
    assert any(
        "delivery_updated" in str(block.get("content", ""))
        for block in context_after_first
    )
    object.__setattr__(agent, "llm_call", AsyncMock(side_effect=[_response(content="无需变更。")]))
    await supervisor.run("new_evidence", session_id="s1")
    context_after_second = await agent.get_context()
    assert len(context_after_second) > len_after_first
    assert any(
        "new_evidence" in str(block.get("content", ""))
        for block in context_after_second
    )


@pytest.mark.asyncio
async def test_graph_supervisor_delivery_mutation_is_rejected_in_loop(tmp_path):
    """Supervisor 试图改机理图 → actor_forbidden 回到其上下文，可同轮改提 process 变更。"""
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
                            "action": "mutate",
                            "base_revisions": {"process": 0, "delivery": 0},
                            "rationale": "try to design the mechanism",
                            "operations": [
                                {
                                    "op": "add_node",
                                    "graph": "delivery",
                                    "data": {
                                        "node_id": "r",
                                        "node_type": "intermediate_occurrence",
                                        "label": "reactant",
                                        "payload": {"evidence_level": "proposed"},
                                    },
                                }
                            ],
                        },
                    )
                ]
            ),
            _response(
                [
                    _tool_call(
                        "c-good",
                        {
                            "action": "mutate",
                            "base_revisions": {"process": 0, "delivery": 0},
                            "rationale": "schedule a conformer search instead",
                            "operations": [
                                {
                                    "op": "add_node",
                                    "graph": "process",
                                    "data": {
                                        "node_id": "conformer",
                                        "node_type": "calculation",
                                        "label": "conformer search",
                                        "payload": {"status": "ready"},
                                    },
                                }
                            ],
                        },
                    )
                ]
            ),
            _response(content="已改为安排计算。"),
            ]
        )
    )

    result = await supervisor.run("graph_initialization", session_id="s1")

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

    result = await supervisor.run("new_evidence", session_id="s1")

    assert result.mutations == []
    assert "llm_call failed" in result.note



@pytest.mark.asyncio
async def test_supervisor_run_registers_session_record(tmp_path):
    """guided 下每次触发登记一条 supervisor 子 Agent 会话并流转到 finished。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-session-record", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    result = await controller.maybe_supervise("new_evidence")

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
    assert "new_evidence" in query
    assert "trigger=new_evidence" in summary


@pytest.mark.asyncio
async def test_supervisor_exception_finalizes_failed_without_propagating(tmp_path):
    """Supervisor 是顾问角色：run 抛错不炸 Coordinator，会话落 failed。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-run-crash", "dag_guided")

    class CrashingSupervisor:
        async def run(self, trigger, coordinator_request=None, session_id=None, **_kwargs):
            raise RuntimeError("boom")

    controller = DagController(db, "s1", "dag_guided", supervisor=CrashingSupervisor())

    result = await controller.maybe_supervise("new_evidence")

    assert result is None
    with db.connect() as con:
        rows = con.execute(
            "SELECT state, error FROM session WHERE agent_id = 'supervisor'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "failed"
    assert "boom" in rows[0][1]



@pytest.mark.asyncio
async def test_graph_view_result_not_truncated_at_4000(tmp_path):
    """回归：process 视图必须完整进入 Supervisor 上下文（可解析 JSON），
    不得在结构中间被 MAX_TOOL_RESULT_CHARS 截断。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-view-truncation", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.SUPERVISOR,
            actor_id="supervisor",
            base_revisions=store.load_bundle().revisions,
            rationale="seed many work nodes",
            operations=[
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id=f"work-{i:02d}",
                        label=f"calculation {i} " + "x" * 100,
                        status="ready",
                        priority=i,
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
                _response([_tool_call("c-view", {"action": "view", "graph_kind": "process"})]),
                _response(content="看完了。"),
            ]
        ),
    )

    await supervisor.run("new_evidence", session_id="s1")

    tool_contents = [
        str(b.get("content", "")) for b in await agent.get_context() if b.get("role") == "tool"
    ]
    assert tool_contents
    assert not any("结果过长被截断" in c for c in tool_contents)
    payload = json.loads(tool_contents[-1])
    assert payload["success"] is True
    assert payload["result"]["total_nodes"] == 30
    assert len(payload["result"]["nodes"]) == 30
    # 一页装得下时不重复附 index
    assert "index" not in payload["result"]
    # 摘要视图：无完整 refs 列表，只有计数
    assert "refs" not in payload["result"]["nodes"][0]
    assert "n_refs" in payload["result"]["nodes"][0]



@pytest.mark.asyncio
async def test_maybe_supervise_passes_event_sink(tmp_path):
    """session 登记成功时，controller 必须给 supervisor.run 带上事件出口。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-event-sink", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.maybe_supervise("new_evidence")

    assert supervisor.calls[0]["event_sink"] is not None


@pytest.mark.asyncio
async def test_graph_supervisor_emits_render_events(tmp_path):
    """Supervisor 的运行过程经 event_sink 发出渲染事件：
    触发消息、推理正文、dag_graph 调用与结果——TUI 窗口据此可见。"""
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
    assert finished["tool"] == "dag_graph"
    assert finished["result"]


@pytest.mark.asyncio
async def test_view_survives_malformed_priority_payload(tmp_path):
    """回归：模型往 process 节点写了非数字 priority（如 "high"）后，
    view 的投影派生不得崩溃——否则 Supervisor 的运行会被一次 view 直接终结。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-bad-priority", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.SUPERVISOR,
            actor_id="supervisor",
            base_revisions=store.load_bundle().revisions,
            rationale="seed work with malformed priority",
            operations=[
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="work-bad",
                        label="poisoned priority",
                        status="ready",
                        priority="high",
                    ),
                ),
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="work-ok",
                        label="normal priority",
                        status="ready",
                        priority=5,
                    ),
                ),
            ],
        )
    )
    assert seeded.accepted

    supervisor = GraphSupervisor(conversation_id="supervisor-bad-priority")
    agent = supervisor._ensure_agent()
    object.__setattr__(
        agent,
        "llm_call",
        AsyncMock(
            side_effect=[
                _response([_tool_call("c-view", {"action": "view"})]),
                _response(content="看完了。"),
            ]
        ),
    )

    result = await supervisor.run("new_evidence", session_id="s1")

    assert result.rounds == 1
    tool_contents = [
        str(b.get("content", "")) for b in await agent.get_context() if b.get("role") == "tool"
    ]
    view_content = next(c for c in tool_contents if "frontier" in c)
    assert "【系统错误】" not in view_content
    payload = json.loads(view_content)
    frontier = payload["result"]["frontier"]
    # 脏 priority 按 0 处理：正常节点排前面，脏节点仍在 frontier 里可见
    assert [n["node_id"] for n in frontier] == ["work-ok", "work-bad"]
    assert frontier[1]["priority"] == 0


@pytest.mark.asyncio
async def test_tool_crash_does_not_end_supervisor_run(tmp_path, monkeypatch):
    """回归：dag_graph 工具内部异常必须以【系统错误】回喂 Supervisor 上下文，
    让它有机会调整，而不是把整个督导运行炸掉、session 落为 failed。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-tool-crash", data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    async def boom(self, user_input, session):
        raise RuntimeError("projection exploded")

    monkeypatch.setattr(
        "cloudra.tools.Plantool.dag_graph.DagGraph.tool_call", boom
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

    result = await supervisor.run("new_evidence", session_id="s1", event_sink=sink)

    assert result.rounds == 1
    assert result.note == ""
    tool_contents = [
        str(b.get("content", "")) for b in await agent.get_context() if b.get("role") == "tool"
    ]
    assert any("【系统错误】" in c and "projection exploded" in c for c in tool_contents)
    # UI 事件流不悬空：tool_started 后必须跟 tool_finished
    kinds = [k for k, _ in emitted]
    assert "tool_started" in kinds and "tool_finished" in kinds


@pytest.mark.asyncio
async def test_max_rounds_ends_with_wrapup_instead_of_cutoff(tmp_path):
    """回归：真实运行中 Supervisor 常在排障中途撞上轮次预算，被无声切断
    （"view 之后被迫结束"）。预算用尽后必须给一次不执行工具的收尾调用，
    session 以正常总结结束；收尾回复里的 tool_calls 被丢弃、不落上下文。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-wrapup", data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id="supervisor-wrapup")
    agent = supervisor._ensure_agent()
    budget = supervisor.MAX_ROUNDS
    responses = [
        _response([_tool_call(f"c-view-{i}", {"action": "view"})]) for i in range(budget)
    ]
    # 收尾回复带文本 + 一个不该被执行的 tool_call：文本保留，调用丢弃。
    responses.append(
        _response(
            [_tool_call("c-late", {"action": "view"})],
            content="预算用尽：optfreq 系列仍 pending，待下次触发继续。",
        )
    )
    llm = AsyncMock(side_effect=responses)
    object.__setattr__(agent, "llm_call", llm)
    emitted = []

    async def sink(event_type, data):
        emitted.append((event_type, data))

    result = await supervisor.run("new_evidence", session_id="s1", event_sink=sink)

    assert result.rounds == budget
    assert f"reached MAX_ROUNDS ({budget})" in result.note
    # 收尾恰好多一次 llm 调用
    assert llm.await_count == budget + 1
    context = await agent.get_context()
    closing = context[-1]
    assert closing["role"] == "assistant"
    assert "预算用尽" in str(closing["content"])
    assert "tool_calls" not in closing
    # 收尾内容进了事件流（TUI 可见），且没有多余的 tool_started
    started = [d for k, d in emitted if k == "tool_started"]
    assert len(started) == budget
    assert any(
        "预算用尽" in d.get("delta", "") for k, d in emitted if k == "llm_chunk"
    )


@pytest.mark.asyncio
async def test_wrapup_llm_failure_does_not_break_run(tmp_path):
    """收尾调用失败不影响运行结果：note 仍是 MAX_ROUNDS，异常被吞。"""
    _, GraphSupervisor, _ = _api()

    get_config().data_dir = tmp_path
    db = ConversationDB("supervisor-wrapup-fail", data_dir=tmp_path).init()
    DagStore(db).ensure_bundle("s1")

    supervisor = GraphSupervisor(conversation_id="supervisor-wrapup-fail")
    agent = supervisor._ensure_agent()
    budget = supervisor.MAX_ROUNDS
    responses = [
        _response([_tool_call(f"c-view-{i}", {"action": "view"})]) for i in range(budget)
    ]
    responses.append(RuntimeError("provider down at wrap-up"))
    object.__setattr__(agent, "llm_call", AsyncMock(side_effect=responses))

    result = await supervisor.run("new_evidence", session_id="s1")

    assert result.rounds == budget
    assert f"reached MAX_ROUNDS ({budget})" in result.note


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
                _response([_tool_call("c1", {"action": "view", "graph_kind": "process"})]),
                _response([_tool_call("c2", {"action": "view"})]),
                _response(content="两张视图都看过了。"),
            ]
        ),
    )

    await supervisor.run("new_evidence", session_id="s1")

    tool_blocks = [b for b in await agent.get_context() if b.get("role") == "tool"]
    assert len(tool_blocks) == 2
    assert "【过时视图已折叠】" in str(tool_blocks[0].get("content", ""))
    assert "frontier" in str(tool_blocks[1].get("content", ""))
    assert "【过时视图已折叠】" not in str(tool_blocks[1].get("content", ""))


@pytest.mark.asyncio
async def test_bind_evidence_acceptance_triggers_new_evidence(tmp_path):
    """agent 的 bind_evidence 挂载成功 → new_evidence 复核（证据等级已被 harness 派生）。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-bind-trigger", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-bind-1",
        "dag_graph",
        {
            "action": "bind_evidence",
            "tool_call_id": "tc-x",
            "bind_target": "step1",
            "evidence_role": "ts_optimization_frequency",
        },
        {"success": True, "accepted": True},
    )

    assert [call["trigger"] for call in supervisor.calls] == ["new_evidence"]


@pytest.mark.asyncio
async def test_failed_bind_and_review_evidence_do_not_trigger(tmp_path):
    """bind_evidence 被拒不触发；Supervisor 自己的 review_evidence 也不应唤醒自己。"""
    DagController, _, _ = _api()
    db = _db(tmp_path, "supervisor-bind-quiet", "dag_guided")
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-bind-2",
        "dag_graph",
        {"action": "bind_evidence", "tool_call_id": "tc-x", "bind_target": "step1"},
        {"success": False, "accepted": False, "error": "did not succeed"},
    )
    await controller.on_tool_finished(
        "tc-review-1",
        "dag_graph",
        {
            "action": "review_evidence",
            "bind_target": "step1",
            "verdict": "rejected",
            "rationale": "证据不成立",
        },
        {"success": True, "accepted": True},
    )

    assert supervisor.calls == []
