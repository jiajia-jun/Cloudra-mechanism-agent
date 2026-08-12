import pytest

from cloudra.base.session_class import Session
from cloudra.core.agent import Coordinator
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB


def _agent(conversation_id, mode):
    return Coordinator(
        query="study a mechanism",
        conversation_id=conversation_id,
        orchestration_mode=mode,
    )


def test_dag_tool_hidden_in_standard_and_visible_in_dag_modes():
    standard = _agent("tool-standard-visible", "standard")
    record = _agent("tool-record-visible", "dag_record")

    assert "dag_graph" not in {
        entry.tool_name for entry in standard.get_available_tools()
    }
    assert "dag_graph" in {entry.tool_name for entry in record.get_available_tools()}


@pytest.mark.asyncio
async def test_direct_standard_tool_call_fails_without_initializing_graphs(tmp_path):
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-standard-direct", "standard")
    db = ConversationDB(agent.conversation_id).init()

    output = await DagGraph(subagent=agent).tool_call(
        DagGraphInput(action="view"),
        Session("s1", str(tmp_path / "session.json")),
    )

    assert not output.success
    assert "standard" in output.error
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_dag_record_agent_can_mutate_and_view(tmp_path):
    """Coordinator（actor=agent）设计 delivery/机理图，不能写 process 图。"""
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ElementaryStepEdge,
        OccurrenceNode,
    )
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-record-mutate", "dag_record")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    mutated = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions={"process": 0, "delivery": 0},
            rationale="Claisen pathway hypothesis",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="r", label="C=COCC=C", evidence_level="proposed"
                    ),
                ),
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="p", label="C=CCCC=O", evidence_level="proposed"
                    ),
                ),
                AddEdge(
                    op="add_edge",
                    graph="delivery",
                    edge=ElementaryStepEdge(
                        edge_id="chair",
                        source_node_id="r",
                        target_node_id="p",
                        label="chair [3,3]",
                        evidence_level="proposed",
                    ),
                ),
            ],
        ),
        session,
    )
    viewed = await tool.tool_call(DagGraphInput(action="view"), session)

    assert mutated.success
    assert mutated.accepted is True
    assert mutated.result["revisions"] == {"process": 0, "delivery": 1}
    assert viewed.success
    assert viewed.result["revisions"] == {"process": 0, "delivery": 1}
    with ConversationDB(agent.conversation_id).connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone() == (2,)


@pytest.mark.asyncio
async def test_mutate_without_base_revisions_pins_current(tmp_path):
    """不传 base_revisions：harness 固定当前版本直接应用，模型不再搬版本号。"""
    from cloudra.dag.models import AddNode, OccurrenceNode
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-no-revisions", "dag_record")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    mutated = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            rationale="no revisions needed",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="r", label="CCO"),
                ),
            ],
        ),
        session,
    )

    assert mutated.success
    assert mutated.accepted is True
    assert mutated.result["revisions"] == {"process": 0, "delivery": 1}


@pytest.mark.asyncio
async def test_mutate_without_revisions_retries_stale(tmp_path, monkeypatch):
    """未显式提供 revision 时 stale 自动重试一次（与 harness 自身写入同待遇）。"""
    from cloudra.dag.models import AddNode, OccurrenceNode
    from cloudra.dag.store import DagStore
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-stale-retry", "dag_record")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    real_load_bundle = DagStore.load_bundle
    calls = {"n": 0}

    def stale_first_pin(self):
        # mutate 内第一次 pin 返回过期版本，模拟 pin 与 apply 之间图被推进；
        # 重试时返回真实版本
        bundle = real_load_bundle(self)
        calls["n"] += 1
        if calls["n"] == 1:
            return type(bundle)(
                process_graph_id=bundle.process_graph_id,
                delivery_graph_id=bundle.delivery_graph_id,
                revisions={"process": 99, "delivery": 99},
            )
        return bundle

    monkeypatch.setattr(DagStore, "load_bundle", stale_first_pin)

    mutated = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            rationale="stale retry",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="r", label="CCO"),
                ),
            ],
        ),
        session,
    )

    assert mutated.success
    assert mutated.accepted is True
    # pin 一次（过期）+ 重试一次（最新）；引擎拒绝簿记自身也会读版本，不精确断言次数
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_explicit_wrong_base_revisions_fails_without_retry(tmp_path):
    """显式提供错误 revision：保留旧语义，报 stale_revision 且不自动重试。"""
    from cloudra.dag.models import AddNode, OccurrenceNode
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-explicit-stale", "dag_record")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    mutated = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions={"process": 0, "delivery": 42},
            rationale="explicit stale",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="r", label="CCO"),
                ),
            ],
        ),
        session,
    )

    assert not mutated.success
    assert mutated.rejection_code == "stale_revision"
    assert "base_revisions" in mutated.error


@pytest.mark.asyncio
async def test_coordinator_cannot_mutate_process_graph(tmp_path):
    """process DAG 由 Supervisor/harness 维护，Coordinator 写它会被拒绝。"""
    from cloudra.dag.models import AddNode, PlannedNode
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-agent-process-forbidden", "dag_guided")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    result = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions={"process": 0, "delivery": 0},
            rationale="try to schedule work directly",
            operations=[
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="ts-search", label="TS search", status="ready"
                    ),
                )
            ],
        ),
        session,
    )

    assert not result.accepted
    assert result.rejection_code == "actor_forbidden"
    with ConversationDB(agent.conversation_id).connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_nodes").fetchone() == (0,)


@pytest.mark.asyncio
async def test_supervisor_actor_can_mutate_process_but_not_delivery(tmp_path):
    """type=supervisor 的调用者被派生为 actor=SUPERVISOR：可写 process，delivery 只读。"""
    from cloudra.core.supervisor import SupervisorAgent
    from cloudra.dag.models import AddNode, OccurrenceNode, PlannedNode
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = SupervisorAgent(
        conversation_id="tool-supervisor-actor",
        orchestration_mode="dag_guided",
    )
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    scheduled = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions={"process": 0, "delivery": 0},
            rationale="schedule endpoint validation",
            operations=[
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="endpoint-opt",
                        label="endpoint optimization",
                        status="ready",
                        priority=20,
                    ),
                )
            ],
        ),
        session,
    )
    assert scheduled.accepted is True

    revisions = scheduled.result["revisions"]
    designed = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions=revisions,
            rationale="supervisor must not design the mechanism",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="r", label="reactant", evidence_level="proposed"
                    ),
                )
            ],
        ),
        session,
    )
    assert not designed.accepted
    assert designed.rejection_code == "actor_forbidden"

    with ConversationDB(agent.conversation_id).connect() as con:
        rows = con.execute(
            "SELECT actor_type FROM dag_mutations WHERE accepted = 1"
        ).fetchall()
    assert [row[0] for row in rows] == ["supervisor"]


@pytest.mark.asyncio
async def test_delivery_report_is_read_only_and_endpoint_aware(tmp_path):
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-delivery-report", "dag_guided")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    report = await tool.tool_call(DagGraphInput(action="delivery_report"), session)

    assert report.success
    assert report.result["complete"] is False
    assert report.result["unresolved"][0]["code"] == "empty_delivery_graph"


@pytest.mark.asyncio
async def test_delivery_report_uses_the_persisted_coverage_contract(tmp_path):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        CoverageContract,
        ElementaryStepEdge,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        SetCoverageContract,
    )
    from cloudra.dag.store import DagStore
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-persisted-coverage", "dag_record")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(agent.conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle(session.id)
    engine = DagEngine(store)

    graph_result = engine.apply_batch(
        MutationBatch(
            session_id=session.id,
            actor=GraphActor.HARNESS,
            actor_id="harness",
            base_revisions=store.load_bundle().revisions,
            rationale="seed one endpoint-supported elementary step",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="reactant",
                        label="reactant",
                        evidence_level="structure_supported",
                    ),
                ),
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="product",
                        label="product",
                        evidence_level="structure_supported",
                    ),
                ),
                AddEdge(
                    op="add_edge",
                    graph="delivery",
                    edge=ElementaryStepEdge(
                        edge_id="claisen",
                        source_node_id="reactant",
                        target_node_id="product",
                        label="Claisen rearrangement",
                        evidence_level="endpoint_supported",
                    ),
                ),
            ],
        )
    )
    assert graph_result.accepted
    coverage_result = engine.apply_batch(
        MutationBatch(
            session_id=session.id,
            actor=GraphActor.HARNESS,
            actor_id="harness",
            base_revisions=store.load_bundle().revisions,
            rationale="the user requested a free-energy profile",
            operations=[
                SetCoverageContract(
                    op="set_coverage_contract",
                    contract=CoverageContract.mechanism_default(
                        require_thermochemistry=True
                    ),
                )
            ],
        )
    )
    assert coverage_result.accepted

    report = await tool.tool_call(DagGraphInput(action="delivery_report"), session)

    assert not report.result["complete"]
    assert "missing_thermochemistry" in {
        gap["code"] for gap in report.result["unresolved"]
    }


@pytest.mark.asyncio
async def test_init_from_template_seeds_skeleton_only_on_empty_graphs(tmp_path):
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-template", "dag_guided")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    seeded = await tool.tool_call(
        DagGraphInput(action="init_from_template", rationale="start Claisen study"),
        session,
    )
    assert seeded.success
    view = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="process"), session
    )
    node_ids = {node["node_id"] for node in view.result["nodes"]}
    assert {"p_analyze", "p_skill", "p_literature", "p_delivery_design"} <= node_ids
    delivery = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="delivery"), session
    )
    roles = {node["payload"]["role"] for node in delivery.result["nodes"]}
    assert roles == {"reactant", "product"}

    # 图已非空：再次初始化被拒绝，已有骨架不被覆盖
    again = await tool.tool_call(
        DagGraphInput(action="init_from_template"), session
    )
    assert not again.success
    assert "empty" in again.error


@pytest.mark.asyncio
async def test_init_from_template_allows_observed_only_process_pollution(tmp_path):
    """getskill/bashtools 的 harness 观察节点不应挡住模板初始化。"""
    from cloudra.dag.models import (
        AddNode,
        GraphActor,
        MutationBatch,
        ObservedNode,
    )
    from cloudra.dag.store import DagStore
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-template-observed", "dag_guided")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(agent.conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle(session.id)
    from cloudra.dag.engine import DagEngine

    engine = DagEngine(store)
    polluted = engine.apply_batch(
        MutationBatch(
            session_id=session.id,
            actor=GraphActor.HARNESS,
            actor_id="dag-controller",
            base_revisions=store.load_bundle().revisions,
            rationale="observe early getskill",
            operations=[
                AddNode(
                    op="add_node",
                    graph="process",
                    node=ObservedNode(
                        node_id="observed_abc",
                        label="getskill",
                        status="succeeded",
                        tool_name="getskill",
                        unplanned=True,
                    ),
                )
            ],
        )
    )
    assert polluted.accepted

    seeded = await tool.tool_call(
        DagGraphInput(action="init_from_template", rationale="start after skill load"),
        session,
    )
    assert seeded.success, seeded.error
    view = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="process", include_observed=True),
        session,
    )
    node_ids = {node["node_id"] for node in view.result["nodes"]}
    assert "p_analyze" in node_ids
    assert "observed_abc" in node_ids


@pytest.mark.asyncio
async def test_retro_attach_with_role_rederives_evidence_level(tmp_path):
    """先算后建图：补挂已登记证据并带 evidence_role 时，等级确定性重算。"""
    from cloudra.dag.models import AddNode, AttachRef, OccurrenceNode
    from cloudra.dag.store import DagStore
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-retro-derive", "dag_record")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(agent.conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle(session.id)

    # 模拟一次先于计划完成的中间体优化解析（未绑定任何 planned node）
    ref = store.register_evidence(
        session.id,
        "gaussian_log_parser",
        {
            "tool_call_id": "call-early",
            "arguments": {"file": "poz_optfreq.log"},
            "result": {
                "imaginary_frequencies": [],
                "frequencies_cm": [500.0, 1600.0, 3700.0],
                "normal_termination": True,
            },
        },
    )

    out = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions={"process": 0, "delivery": 0},
            rationale="late-built graph claims the earlier optimization",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="poz",
                        label="POZ",
                        role="intermediate",
                        evidence_level="proposed",
                    ),
                ),
                AttachRef(
                    op="attach_ref",
                    graph="delivery",
                    target_type="node",
                    target_id="poz",
                    ref=ref,
                    evidence_role="intermediate_optimization",
                ),
            ],
        ),
        session,
    )

    assert out.accepted
    assert out.result["derived"] == [
        {
            "target_type": "node",
            "target_id": "poz",
            "changes": {"evidence_level": "structure_supported"},
        }
    ]
    view = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="delivery"), session
    )
    poz = next(n for n in view.result["nodes"] if n["node_id"] == "poz")
    assert poz["payload"]["evidence_level"] == "structure_supported"

    # 不带 evidence_role 的补挂：只挂引用，不重算
    ref2 = store.register_evidence(
        session.id,
        "gaussian_log_parser",
        {
            "tool_call_id": "call-early-2",
            "arguments": {"file": "soz_optfreq.log"},
            "result": {
                "imaginary_frequencies": [],
                "frequencies_cm": [400.0, 1500.0, 3600.0],
                "normal_termination": True,
            },
        },
    )
    # 第一次 mutate 后 harness 的派生批次把 delivery revision 又推进了一位，
    # 重新读最新版本再提交。
    revisions = store.load_bundle().revisions
    plain = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions=revisions,
            rationale="attach raw evidence without claiming a role",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="soz",
                        label="SOZ",
                        role="product",
                        evidence_level="proposed",
                    ),
                ),
                AttachRef(
                    op="attach_ref",
                    graph="delivery",
                    target_type="node",
                    target_id="soz",
                    ref=ref2,
                ),
            ],
        ),
        session,
    )
    assert plain.accepted
    assert "derived" not in plain.result


@pytest.mark.asyncio
async def test_view_pagination_reports_total_and_offset(tmp_path):
    from cloudra.dag.models import AddNode, OccurrenceNode
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-view-pagination", "dag_record")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions={"process": 0, "delivery": 0},
            rationale="three candidates",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id=f"n{i}",
                        label=f"candidate {i}",
                        role="intermediate",
                        evidence_level="proposed",
                    ),
                )
                for i in range(3)
            ],
        ),
        session,
    )

    first = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="delivery"), session
    )
    assert first.result["total_nodes"] == 3
    assert len(first.result["nodes"]) == 3

    tail = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="delivery", offset=2), session
    )
    assert tail.result["total_nodes"] == 3
    assert tail.result["offset"] == 2
    assert len(tail.result["nodes"]) == 1


@pytest.mark.asyncio
async def test_view_filters_by_node_ids_and_status(tmp_path):
    """回归：Supervisor 为找几个节点翻整页烧轮次——view 支持 node_ids/status_filter
    精确取节点，total_nodes 报告过滤后的匹配数。"""
    from cloudra.dag.models import AddNode, OccurrenceNode
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-view-filters", "dag_record")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions={"process": 0, "delivery": 0},
            rationale="mixed statuses",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id=f"n{i}",
                        label=f"candidate {i}",
                        role="intermediate",
                        evidence_level="proposed",
                        # occurrence 节点无 status 字段；status_filter 读视图 payload，
                        # 自定义键经 metadata 并入投影
                        metadata={"status": "ready" if i % 2 else "proposed"},
                    ),
                )
                for i in range(4)
            ],
        ),
        session,
    )

    by_id = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="delivery", node_ids=["n1", "n3"]),
        session,
    )
    assert by_id.result["total_nodes"] == 2
    assert {node["node_id"] for node in by_id.result["nodes"]} == {"n1", "n3"}
    assert by_id.result["filters"] == {"node_ids": ["n1", "n3"]}

    by_status = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="delivery", status_filter="proposed"),
        session,
    )
    assert by_status.result["total_nodes"] == 2
    assert {node["node_id"] for node in by_status.result["nodes"]} == {"n0", "n2"}

    combined = await tool.tool_call(
        DagGraphInput(
            action="view",
            graph_kind="delivery",
            node_ids=["n0", "n1"],
            status_filter="ready",
        ),
        session,
    )
    assert combined.result["total_nodes"] == 1
    assert combined.result["nodes"][0]["node_id"] == "n1"


@pytest.mark.asyncio
async def test_process_view_omits_observed_and_compacts_by_default(tmp_path):
    """回归：process 全量 view 曾被 observed_tool_call + 完整 refs/hash 撑到 20k+
    字符。默认应剔除观察节点、压成摘要，并用 index 避免翻页找 id。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddNode,
        GraphActor,
        MutationBatch,
        ObservedNode,
        PlannedNode,
    )
    from cloudra.dag.store import DagStore
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-view-compact", "dag_guided")
    agent.type = "supervisor"
    agent.id = "supervisor"
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(agent.conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    ref = store.register_evidence(
        "s1",
        "bashtools",
        {"tool_call_id": "call-obs", "arguments": {"command": "ls"}, "result": {"ok": True}},
    )
    engine = DagEngine(store)
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="harness",
            base_revisions=store.load_bundle().revisions,
            rationale="seed planned + observed",
            operations=[
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="optfreq_R",
                        label="optfreq reactants",
                        status="ready",
                        tool_name="gaussian_log_parser",
                        arguments_hash="deadbeef" * 8,
                    ),
                ),
                AddNode(
                    op="add_node",
                    graph="process",
                    node=ObservedNode(
                        node_id="observed_abc",
                        label="unplanned bash",
                        status="succeeded",
                        tool_name="bashtools",
                        unplanned=True,
                        arguments_hash="cafebabe" * 8,
                        refs=[ref],
                    ),
                ),
            ],
        )
    )
    assert seeded.accepted

    default = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="process"), session
    )
    assert default.success
    assert default.result["total_nodes"] == 1
    assert default.result["omitted_observed_tool_calls"] == 1
    assert [n["node_id"] for n in default.result["nodes"]] == ["optfreq_R"]
    assert "index" not in default.result  # 单页装下，无需页外索引
    node = default.result["nodes"][0]
    assert node["n_refs"] == 0
    assert "refs" not in node
    assert "arguments_hash" not in node["payload"]
    assert node["payload"]["tool_name"] == "gaussian_log_parser"

    with_obs = await tool.tool_call(
        DagGraphInput(action="view", graph_kind="process", include_observed=True),
        session,
    )
    assert with_obs.result["total_nodes"] == 2
    assert with_obs.result["filters"]["include_observed"] is True
    ids = {n["node_id"] for n in with_obs.result["nodes"]}
    assert ids == {"optfreq_R", "observed_abc"}
    obs = next(n for n in with_obs.result["nodes"] if n["node_id"] == "observed_abc")
    assert obs["n_refs"] == 1
    assert "refs" not in obs


# ---------------------------------------------------------------------------
# bind_evidence / review_evidence 高层动作
# ---------------------------------------------------------------------------

_TS_FREQ_RESULT = {
    "is_success": True,
    "normal_termination": True,
    "imaginary_frequencies": [-518.3],
}


async def _seed_step_and_evidence(tmp_path, conversation_id, result, mode="dag_record"):
    """备好 bind 现场：delivery 上一条 r→p 基元步 + 一次已登记的 gaussian_log_parser 调用。

    返回 (agent, tool, session, db)。证据由 harness 通道登记（observed 节点 +
    tool_result ref），与运行时 on_tool_finished 的路径一致。
    """
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ElementaryStepEdge,
        OccurrenceNode,
    )
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent(conversation_id, mode)
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(agent.conversation_id).init()

    designed = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            rationale="Claisen pathway hypothesis",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="r", label="R"),
                ),
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(node_id="p", label="P"),
                ),
                AddEdge(
                    op="add_edge",
                    graph="delivery",
                    edge=ElementaryStepEdge(
                        edge_id="step1",
                        source_node_id="r",
                        target_node_id="p",
                        evidence_level="proposed",
                    ),
                ),
            ],
        ),
        session,
    )
    assert designed.accepted

    controller = DagController(db, "s1", mode, conversation_id=agent.conversation_id)
    await controller.initialize()
    await controller.on_tool_finished(
        "tc-bind", "gaussian_log_parser", {"log_path": "ts.log"}, result
    )
    return agent, tool, session, db


def _delivery_edge_level(db, edge_id="step1"):
    """返回边的证据相关显式字段字典（payload 投影只含非默认值，默认 level 不出现）。"""
    from cloudra.dag.store import DagStore

    graph = DagStore(db).load_snapshot().delivery
    edge = next(e for e in graph.edges if e.edge_id == edge_id)
    return {
        "evidence_level": edge.evidence_level,
        "saddle_supported": edge.saddle_supported,
        "evidence_vetoed": edge.evidence_vetoed,
        "reason": edge.reason,
    }


@pytest.mark.asyncio
async def test_bind_evidence_derives_level(tmp_path):
    """成功路径：tool_call_id 挂载已登记证据，harness 派生 saddle_supported。"""
    from cloudra.tools.Plantool.dag_graph import DagGraphInput

    _, tool, session, db = await _seed_step_and_evidence(
        tmp_path, "tool-bind-ok", _TS_FREQ_RESULT
    )

    bound = await tool.tool_call(
        DagGraphInput(
            action="bind_evidence",
            tool_call_id="tc-bind",
            bind_target="step1",
            evidence_role="ts_optimization_frequency",
        ),
        session,
    )

    assert bound.success
    assert bound.accepted is True
    assert bound.result["target_type"] == "edge"
    assert bound.result["derived"] is True
    assert bound.result["changes"]["evidence_level"] == "saddle_supported"
    payload = _delivery_edge_level(db)
    assert payload["evidence_level"] == "saddle_supported"
    assert payload["saddle_supported"] is True


@pytest.mark.asyncio
async def test_bind_evidence_accepts_observed_node_id_alias(tmp_path):
    """上下文压缩后 tool_call_id 丢失：observed_<hex> 节点 id 作为别名同样可挂。"""
    from cloudra.dag.store import DagStore
    from cloudra.tools.Plantool.dag_graph import DagGraphInput

    _, tool, session, db = await _seed_step_and_evidence(
        tmp_path, "tool-bind-alias", _TS_FREQ_RESULT
    )
    observed_id = next(
        node.node_id
        for node in DagStore(db).load_snapshot().process.nodes
        if node.payload.get("tool_call_id") == "tc-bind"
    )
    assert observed_id.startswith("observed_")

    bound = await tool.tool_call(
        DagGraphInput(
            action="bind_evidence",
            tool_call_id=observed_id,
            bind_target="step1",
            evidence_role="ts_optimization_frequency",
        ),
        session,
    )

    assert bound.success
    assert bound.accepted is True
    assert _delivery_edge_level(db)["evidence_level"] == "saddle_supported"


@pytest.mark.asyncio
async def test_bind_evidence_without_registered_evidence_rejected(tmp_path):
    """只 started 未 finished 的调用没有已登记证据 → 明确拒绝。"""
    from cloudra.dag.controller import DagController
    from cloudra.tools.Plantool.dag_graph import DagGraphInput

    _, tool, session, db = await _seed_step_and_evidence(
        tmp_path, "tool-bind-noev", _TS_FREQ_RESULT
    )
    controller = DagController(db, "s1", "dag_record", conversation_id=db.conversation_id)
    await controller.on_tool_started("tc-running", "gaussian_log_parser", {"log_path": "x.log"})

    bound = await tool.tool_call(
        DagGraphInput(
            action="bind_evidence",
            tool_call_id="tc-running",
            bind_target="step1",
            evidence_role="ts_optimization_frequency",
        ),
        session,
    )

    assert not bound.success
    assert "no registered evidence" in bound.error
    assert _delivery_edge_level(db)["evidence_level"] == "proposed"


@pytest.mark.asyncio
async def test_bind_evidence_failed_call_rejected(tmp_path):
    """失败/未成功的计算不能作为证据。"""
    from cloudra.tools.Plantool.dag_graph import DagGraphInput

    _, tool, session, db = await _seed_step_and_evidence(
        tmp_path,
        "tool-bind-failed",
        {"is_success": False, "error": "SCF not converged"},
    )

    bound = await tool.tool_call(
        DagGraphInput(
            action="bind_evidence",
            tool_call_id="tc-bind",
            bind_target="step1",
            evidence_role="ts_optimization_frequency",
        ),
        session,
    )

    assert not bound.success
    assert "did not succeed" in bound.error
    assert _delivery_edge_level(db)["evidence_level"] == "proposed"


@pytest.mark.asyncio
async def test_bind_evidence_rejected_in_standard_mode(tmp_path):
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    get_config().data_dir = tmp_path
    agent = _agent("tool-bind-standard", "standard")
    tool = DagGraph(subagent=agent)
    session = Session("s1", str(tmp_path / "session.json"))

    bound = await tool.tool_call(
        DagGraphInput(
            action="bind_evidence",
            tool_call_id="tc-x",
            bind_target="step1",
            evidence_role="ts_optimization_frequency",
        ),
        session,
    )

    assert not bound.success
    assert "standard" in bound.error


@pytest.mark.asyncio
async def test_review_evidence_requires_supervisor_actor(tmp_path):
    """Coordinator/子 agent 不能复核证据：review_evidence 仅 supervisor 可用。"""
    from cloudra.tools.Plantool.dag_graph import DagGraphInput

    _, tool, session, db = await _seed_step_and_evidence(
        tmp_path, "tool-review-forbidden", _TS_FREQ_RESULT
    )

    reviewed = await tool.tool_call(
        DagGraphInput(
            action="review_evidence",
            bind_target="step1",
            verdict="rejected",
            rationale="not my call",
        ),
        session,
    )

    assert not reviewed.success
    assert "supervisor-only" in reviewed.error
    assert _delivery_edge_level(db)["evidence_level"] == "proposed"


@pytest.mark.asyncio
async def test_review_evidence_rejected_downgrades_and_notifies(tmp_path):
    """Supervisor 否决：harness 落 inconclusive + 标记否决，journal 记录，
    context_events 各投一条给挂载者 session 与 Coordinator。"""
    from cloudra.core.supervisor import SupervisorAgent
    from cloudra.dag.controller import DagController
    from cloudra.services import session_store
    from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

    _, _, _, db = await _seed_step_and_evidence(
        tmp_path, "tool-review-veto", _TS_FREQ_RESULT, mode="dag_guided"
    )
    # 挂载者是一个子 agent：证据登记在它的 session 下
    session_store.create_session_record(
        db,
        session_id="sub-1",
        agent_id="a-1",
        agent_type="dft",
        parent_session_id="s1",
        query="TS optfreq",
        created_at="2026-08-10T00:00:00+00:00",
        orchestration_mode="dag_guided",
    )
    sub_controller = DagController(
        db, "sub-1", "dag_guided", conversation_id=db.conversation_id
    )
    await sub_controller.on_tool_finished(
        "tc-sub", "gaussian_log_parser", {"log_path": "ts.log"}, _TS_FREQ_RESULT
    )
    await sub_controller.bind_evidence_for_call(
        "tc-sub", "step1", "ts_optimization_frequency"
    )
    assert _delivery_edge_level(db)["evidence_level"] == "saddle_supported"

    supervisor = SupervisorAgent(
        conversation_id=db.conversation_id, orchestration_mode="dag_guided"
    )
    tool = DagGraph(subagent=supervisor)
    session = Session("s1", str(tmp_path / "session.json"))

    reviewed = await tool.tool_call(
        DagGraphInput(
            action="review_evidence",
            bind_target="step1",
            verdict="rejected",
            rationale="虚频归属与目标 TS 不符，证据不成立",
        ),
        session,
    )

    assert reviewed.success
    assert reviewed.accepted is True
    assert reviewed.result["previous_evidence_level"] == "saddle_supported"
    assert reviewed.result["evidence_level"] == "inconclusive"
    payload = _delivery_edge_level(db)
    assert payload["evidence_level"] == "inconclusive"
    assert payload["evidence_vetoed"] is True
    assert "虚频归属" in payload["reason"]

    with db.connect() as con:
        rationales = [
            row[0]
            for row in con.execute(
                "SELECT rationale FROM dag_mutations "
                "WHERE accepted = 1 AND actor_type = 'harness'"
            ).fetchall()
        ]
        assert any("rejected" in r and "虚频归属" in r for r in rationales)
        events = con.execute(
            "SELECT agent_id, session_id, content FROM context_events "
            "WHERE event_type = 'evidence_vetoed' ORDER BY rowid"
        ).fetchall()
    assert [(row[0], row[1]) for row in events] == [("a-1", "sub-1"), ("a-0", None)]
    assert "step1" in events[0][2]
    assert "saddle_supported → inconclusive" in events[0][2]
    assert "虚频归属" in events[0][2]
