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
    from cloudra.dag.models import GraphOperation
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
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": "r",
                        "node_type": "intermediate_occurrence",
                        "label": "C=COCC=C",
                        "payload": {"evidence_level": "proposed"},
                    },
                ),
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": "p",
                        "node_type": "intermediate_occurrence",
                        "label": "C=CCCC=O",
                        "payload": {"evidence_level": "proposed"},
                    },
                ),
                GraphOperation(
                    op="add_edge",
                    graph="delivery",
                    data={
                        "edge_id": "chair",
                        "source_node_id": "r",
                        "target_node_id": "p",
                        "edge_type": "elementary_step",
                        "label": "chair [3,3]",
                        "payload": {"evidence_level": "proposed"},
                    },
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
async def test_coordinator_cannot_mutate_process_graph(tmp_path):
    """process DAG 由 Supervisor/harness 维护，Coordinator 写它会被拒绝。"""
    from cloudra.dag.models import GraphOperation
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
                GraphOperation(
                    op="add_node",
                    graph="process",
                    data={
                        "node_id": "ts-search",
                        "node_type": "calculation",
                        "label": "TS search",
                        "payload": {"status": "ready"},
                    },
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
    from cloudra.dag.models import GraphOperation
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
                GraphOperation(
                    op="add_node",
                    graph="process",
                    data={
                        "node_id": "endpoint-opt",
                        "node_type": "calculation",
                        "label": "endpoint optimization",
                        "payload": {"status": "ready", "priority": 20},
                    },
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
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": "r",
                        "node_type": "intermediate_occurrence",
                        "label": "reactant",
                        "payload": {"evidence_level": "proposed"},
                    },
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
        CoverageContract,
        GraphActor,
        GraphOperation,
        MutationBatch,
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
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": "reactant",
                        "node_type": "intermediate_occurrence",
                        "label": "reactant",
                        "payload": {"evidence_level": "structure_supported"},
                    },
                ),
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": "product",
                        "node_type": "intermediate_occurrence",
                        "label": "product",
                        "payload": {"evidence_level": "structure_supported"},
                    },
                ),
                GraphOperation(
                    op="add_edge",
                    graph="delivery",
                    data={
                        "edge_id": "claisen",
                        "source_node_id": "reactant",
                        "target_node_id": "product",
                        "edge_type": "elementary_step",
                        "label": "Claisen rearrangement",
                        "payload": {"evidence_level": "endpoint_supported"},
                    },
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
                GraphOperation(
                    op="set_coverage_contract",
                    data={
                        "contract": CoverageContract.mechanism_default(
                            require_thermochemistry=True
                        ).model_dump(mode="json")
                    },
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
async def test_retro_attach_with_role_rederives_evidence_level(tmp_path):
    """先算后建图：补挂已登记证据并带 evidence_role 时，等级确定性重算。"""
    from cloudra.dag.models import GraphOperation
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
            "result": {"imaginary_frequencies": [], "normal_termination": True},
        },
    )

    out = await tool.tool_call(
        DagGraphInput(
            action="mutate",
            base_revisions={"process": 0, "delivery": 0},
            rationale="late-built graph claims the earlier optimization",
            operations=[
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": "poz",
                        "node_type": "occurrence",
                        "label": "POZ",
                        "payload": {"role": "intermediate", "evidence_level": "proposed"},
                    },
                ),
                GraphOperation(
                    op="attach_ref",
                    graph="delivery",
                    data={
                        "target_type": "node",
                        "target_id": "poz",
                        "ref": ref.model_dump(mode="json"),
                        "evidence_role": "intermediate_optimization",
                    },
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
            "result": {"imaginary_frequencies": [], "normal_termination": True},
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
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": "soz",
                        "node_type": "occurrence",
                        "label": "SOZ",
                        "payload": {"role": "product", "evidence_level": "proposed"},
                    },
                ),
                GraphOperation(
                    op="attach_ref",
                    graph="delivery",
                    data={
                        "target_type": "node",
                        "target_id": "soz",
                        "ref": ref2.model_dump(mode="json"),
                    },
                ),
            ],
        ),
        session,
    )
    assert plain.accepted
    assert "derived" not in plain.result


@pytest.mark.asyncio
async def test_view_pagination_reports_total_and_offset(tmp_path):
    from cloudra.dag.models import GraphOperation
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
                GraphOperation(
                    op="add_node",
                    graph="delivery",
                    data={
                        "node_id": f"n{i}",
                        "node_type": "occurrence",
                        "label": f"candidate {i}",
                        "payload": {"role": "intermediate", "evidence_level": "proposed"},
                    },
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
