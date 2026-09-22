import pytest
from pydantic import ValidationError

from cloudra.base.session_class import Session
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_add_species import DagAddSpecies, DagAddSpeciesInput
from cloudra.tools.Plantool.dag_tools.dag_add_step import DagAddStep
from cloudra.tools.Plantool.dag_tools.dag_bind_evidence import DagBindEvidence
from cloudra.tools.Plantool.dag_tools.dag_delivery_report import DagDeliveryReport
from cloudra.tools.Plantool.dag_tools.dag_message_supervisor import DagMessageSupervisor
from cloudra.tools.Plantool.dag_tools.dag_remove_edge import DagRemoveEdge, DagRemoveEdgeInput
from cloudra.tools.Plantool.dag_tools.dag_set_coverage_contract import DagSetCoverageContract
from cloudra.tools.Plantool.dag_tools.dag_update_delivery_element import DagUpdateDeliveryElement
from cloudra.tools.Plantool.dag_tools.dag_view import DagView
from tests.dag_identity import (
    call_dag_tool,
    make_coordinator,
    make_session,
    make_subagent,
    make_supervisor,
    projected_tool_names,
)


def _agent(conversation_id, mode):
    return make_coordinator(conversation_id, orchestration_mode=mode)


async def _call(cls, agent, session, **kwargs):
    return await call_dag_tool(cls, agent, session, **kwargs)


_DAG_TOOL_NAMES = {
    "dag_view",
    "dag_delivery_report",
    "dag_add_species",
    "dag_add_step",
    "dag_update_delivery_element",
    "dag_remove_edge",
    "dag_propose_mechanism",
    "dag_submit_step_evidence",
    "dag_submit_species_evidence",
}


def test_dag_tools_hidden_in_standard_and_visible_in_dag_modes():
    # 业务工具只在 traditional 协议上线缆；默认 javascript 下它们走 JS 程序
    # （guest_tool_names），这里断言的是业务工具面的模式门控。
    standard_names = projected_tool_names(
        make_session(
            "tool-standard-visible",
            "coordinator",
            orchestration_mode="standard",
            protocol="traditional",
        )
    )
    record_names = projected_tool_names(
        make_session(
            "tool-record-visible",
            "coordinator",
            orchestration_mode="dag_record",
            protocol="traditional",
        )
    )
    assert not (_DAG_TOOL_NAMES & standard_names)
    assert _DAG_TOOL_NAMES <= record_names
    assert "dag_graph" not in record_names


def test_add_species_schema_requires_core_fields():
    with pytest.raises(ValidationError):
        DagAddSpeciesInput()
    with pytest.raises(ValidationError):
        DagRemoveEdgeInput(name="step1", reason="")


def test_review_and_deletion_tools_register_with_real_schemas():
    """六个送审/裁决工具与两个删除工具从真实工具类加载，schema 来自类本身。"""
    from cloudra.tools import get_tools_lst

    entries = {entry.tool_name: entry for entry in get_tools_lst()}
    expected = {
        "dag_bind_evidence": "DagBindEvidence",
        "dag_review_call": "DagReviewCall",
        "dag_review_evidence": "DagReviewEvidence",
        "dag_view_evidence": "DagViewEvidence",
        "dag_set_coverage_contract": "DagSetCoverageContract",
        "dag_message_supervisor": "DagMessageSupervisor",
        "dag_remove_node": "DagRemoveNode",
        "dag_remove_edge": "DagRemoveEdge",
    }
    for name, class_name in expected.items():
        assert name in entries, name
        entry = entries[name]
        assert entry.cls.__name__ == class_name, name
        assert entry.input_schema is not None, name
        assert entry.input_schema is entry.cls.model_fields["input_schema"].default, name
        # schema 是真实 pydantic 模型（有 model_fields 可供 JSON schema 投影）
        assert hasattr(entry.input_schema, "model_fields"), name


@pytest.mark.asyncio
async def test_direct_standard_tool_call_fails_without_initializing_graphs(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-standard-direct", "standard")
    db = ConversationDB(agent.conversation_id).init()

    output = await _call(DagView, agent, Session("s1", str(tmp_path / "session.json")))

    assert not output.is_success
    assert "standard" in output.error
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_dag_record_agent_can_add_delivery_and_view(tmp_path):
    """Coordinator（actor=agent）设计 delivery/机理图，不能写 process 图。"""
    get_config().data_dir = tmp_path
    agent = _agent("tool-record-mutate", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))

    added_r = await _call(
        DagAddSpecies, agent, session, name="r", smiles="C=COCC=C"
    )
    added_p = await _call(
        DagAddSpecies, agent, session, name="p", smiles="C=CCCC=O"
    )
    added_step = await _call(
        DagAddStep,
        agent,
        session,
        name="chair [3,3]",
        from_="r",
        to="p",
    )
    viewed = await _call(DagView, agent, session)

    assert added_r.accepted is True
    assert added_p.accepted is True
    assert added_step.accepted is True
    assert added_step.result["revisions"] == {"process": 0, "delivery": 3}
    assert viewed.is_success
    assert viewed.result["revisions"] == {"process": 0, "delivery": 3}
    with ConversationDB(agent.conversation_id).connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone() == (2,)


@pytest.mark.asyncio
async def test_add_species_without_revisions_retries_stale(tmp_path, monkeypatch):
    """未显式提供 revision 时 stale 自动重试一次（与 harness 自身写入同待遇）。"""
    from cloudra.dag.store import DagStore

    get_config().data_dir = tmp_path
    agent = _agent("tool-stale-retry", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))

    real_load_bundle = DagStore.load_bundle
    calls = {"n": 0}

    def stale_first_pin(self):
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

    mutated = await _call(
        DagAddSpecies, agent, session, name="r", smiles="CCO"
    )

    assert mutated.is_success
    assert mutated.accepted is True
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_deleted_process_tools_are_unregistered(tmp_path):
    """Phase 4：四个 process 时代工具已从注册表移除。"""
    record_names = projected_tool_names(
        make_session(
            "tool-deleted",
            "coordinator",
            orchestration_mode="dag_record",
            protocol="traditional",
        )
    )
    for name in (
        "dag_schedule_work",
        "dag_update_process_node",
        "dag_init_from_template",
    ):
        assert name not in record_names
    # Task 6 reintroduces dag_review_evidence for v2 structured review requests：
    # 它按模式只在 dag_guided 上线缆（dag_record 下 Supervisor 离线），故这里
    # 断言的是**注册表**里有它，而不是 record 模式的工具面。
    from cloudra.tools import get_tools_lst

    assert "dag_review_evidence" in {entry.tool_name for entry in get_tools_lst()}


@pytest.mark.asyncio
async def test_supervisor_actor_cannot_design_delivery(tmp_path):
    """type=supervisor 的调用者被派生为 actor=SUPERVISOR：delivery 只读。"""
    get_config().data_dir = tmp_path
    agent = make_supervisor("tool-supervisor-actor", workspace_dir=str(tmp_path))
    session = Session("s1", str(tmp_path / "session.json"))

    designed = await _call(
        DagAddSpecies, agent, session, name="reactant"
    )
    assert not designed.accepted
    assert designed.rejection_code == "actor_forbidden"


@pytest.mark.asyncio
async def test_delivery_report_is_read_only_and_endpoint_aware(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-delivery-report", "dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))

    report = await _call(DagDeliveryReport, agent, session)

    assert report.is_success
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

    get_config().data_dir = tmp_path
    agent = _agent("tool-persisted-coverage", "dag_record")
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

    report = await _call(DagDeliveryReport, agent, session)

    assert not report.result["complete"]
    assert "missing_thermochemistry" in {
        gap["code"] for gap in report.result["unresolved"]
    }


@pytest.mark.asyncio
async def test_view_pagination_reports_total_and_offset(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-view-pagination", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))

    for i in range(3):
        out = await _call(
            DagAddSpecies,
            agent,
            session,
            name=f"candidate {i}",
        )
        assert out.accepted

    first = await _call(DagView, agent, session, graph_kind="delivery")
    assert first.result["total_nodes"] == 3
    assert len(first.result["nodes"]) == 3

    tail = await _call(DagView, agent, session, graph_kind="delivery", offset=2)
    assert tail.result["total_nodes"] == 3
    assert tail.result["offset"] == 2
    assert len(tail.result["nodes"]) == 1


@pytest.mark.asyncio
async def test_view_filters_by_node_ids_and_status(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-view-filters", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))

    for i in range(4):
        out = await _call(
            DagAddSpecies,
            agent,
            session,
            name=f"candidate {i}",
        )
        assert out.accepted

    for i in (1, 3):
        await _call(DagUpdateDeliveryElement, agent, session, name=f"candidate {i}", status="ready")
    for i in (0, 2):
        await _call(DagUpdateDeliveryElement, agent, session, name=f"candidate {i}", status="proposed")

    view_all = await _call(DagView, agent, session, graph_kind="delivery")
    id_map = {n["label"]: n["node_id"] for n in view_all.result["nodes"]}
    n0, n1, n2, n3 = id_map["candidate 0"], id_map["candidate 1"], id_map["candidate 2"], id_map["candidate 3"]

    by_id = await _call(
        DagView, agent, session, graph_kind="delivery", node_ids=[n1, n3]
    )
    assert by_id.result["total_nodes"] == 2
    assert {node["node_id"] for node in by_id.result["nodes"]} == {n1, n3}
    assert by_id.result["filters"] == {"node_ids": [n1, n3]}

    by_status = await _call(
        DagView, agent, session, graph_kind="delivery", status_filter="proposed"
    )
    assert by_status.result["total_nodes"] == 2
    assert {node["node_id"] for node in by_status.result["nodes"]} == {n0, n2}

    combined = await _call(
        DagView,
        agent,
        session,
        graph_kind="delivery",
        node_ids=[n0, n1],
        status_filter="ready",
    )
    assert combined.result["total_nodes"] == 1
    assert combined.result["nodes"][0]["node_id"] == n1


@pytest.mark.asyncio
async def test_process_view_returns_deprecation_note(tmp_path):
    """Phase 4：graph_kind=process 不再返回子图，给出明确的弃用说明。"""
    get_config().data_dir = tmp_path
    agent = _agent("tool-view-compact", "dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))

    view = await _call(DagView, agent, session, graph_kind="process")

    assert view.is_success
    assert view.result["deprecated"] is True
    assert "removed" in view.result["note"]
    assert view.result["nodes"] == []


@pytest.mark.asyncio
async def test_update_delivery_element_status_by_name(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-upd-delivery", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    added = await _call(
        DagAddSpecies, agent, session, name="ethylene"
    )
    assert added.accepted
    updated = await _call(
        DagUpdateDeliveryElement, agent, session, name="ethylene", status="supported"
    )
    assert updated.accepted
    view = await _call(DagView, agent, session, graph_kind="delivery")
    node = next(n for n in view.result["nodes"] if (n.get("name") or n.get("label")) == "ethylene")
    assert node["payload"]["status"] == "supported"


@pytest.mark.asyncio
async def test_remove_edge_requires_rationale_and_process_is_gone(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-rm-edge", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    await _call(DagAddSpecies, agent, session, name="R")
    await _call(DagAddSpecies, agent, session, name="P")
    step = await _call(
        DagAddStep,
        agent,
        session,
        name="step1",
        from_="R",
        to="P",
    )
    assert step.accepted

    removed = await _call(
        DagRemoveEdge,
        agent,
        session,
        name="step1",
        reason="chair path ruled out by mapping",
    )
    assert removed.accepted is True


# ---------------------------------------------------------------------------
# Task 3: dag_remove_node（研究 agent 删节点 / 删边）
# ---------------------------------------------------------------------------

from cloudra.tools.Plantool.dag_tools.dag_remove_node import DagRemoveNode  # noqa: E402


def _follower(conversation_id, mode):
    return make_subagent(conversation_id, "small_mol", orchestration_mode=mode)


async def _seed_lone_species(agent, session, name="orphan"):
    added = await _call(DagAddSpecies, agent, session, name=name)
    assert added.accepted
    # 用 dag_view 取回 node_id（name→id 由工具内部解析，这里只为断言存在）。
    view = await _call(DagView, agent, session, graph_kind="delivery")
    node = next(n for n in view.result["nodes"] if n["label"] == name)
    return node["node_id"]


@pytest.mark.asyncio
async def test_remove_node_visible_and_executable_by_coordinator(tmp_path):
    """Coordinator 在 record/guided 下可见且能执行 dag_remove_node。"""
    get_config().data_dir = tmp_path
    for mode in ("dag_record", "dag_guided"):
        agent = _agent(f"rm-node-visible-{mode}", mode)
        names = projected_tool_names(
            make_session(
                f"rm-node-visible-{mode}",
                "coordinator",
                orchestration_mode=mode,
                protocol="traditional",
            )
        )
        assert "dag_remove_node" in names
        session = Session("s1", str(tmp_path / "session.json"))
        node_id = await _seed_lone_species(agent, session, f"orphan-{mode}")
        removed = await _call(
            DagRemoveNode, agent, session, name=node_id, reason="not on the path"
        )
        assert removed.accepted is True
        assert removed.result["target_id"] == node_id
        assert "delivery" in removed.result["revisions"]


@pytest.mark.asyncio
async def test_remove_node_executable_by_research_follower(tmp_path):
    """普通研究子 agent（type=follower, actor=AGENT）在 record/guided 可删节点。"""
    get_config().data_dir = tmp_path
    for mode in ("dag_record", "dag_guided"):
        follower = _follower(f"rm-node-follower-{mode}", mode)
        session = Session("s1", str(tmp_path / "session.json"))
        node_id = await _seed_lone_species(follower, session, f"orphan-f-{mode}")
        removed = await _call(
            DagRemoveNode, follower, session, name=node_id, reason="superseded"
        )
        assert removed.accepted is True


@pytest.mark.asyncio
async def test_remove_edge_executable_by_research_follower(tmp_path):
    """删边同样对研究子 agent 开放（与删节点同权限面）。"""
    get_config().data_dir = tmp_path
    follower = _follower("rm-edge-follower", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    await _call(DagAddSpecies, follower, session, name="R")
    await _call(DagAddSpecies, follower, session, name="P")
    await _call(DagAddStep, follower, session, name="step1", from_="R", to="P")
    removed = await _call(
        DagRemoveEdge, follower, session, name="step1", reason="not the path"
    )
    assert removed.accepted is True


@pytest.mark.asyncio
async def test_remove_node_rejected_in_standard_and_for_supervisor(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("rm-node-standard", "standard")
    session = Session("s1", str(tmp_path / "session.json"))
    denied = await _call(DagRemoveNode, agent, session, name="x", reason="cleanup")
    assert not denied.is_success
    assert "standard" in denied.error

    # 先由 Coordinator 在 guided 下种一个节点，再让同会话的 Supervisor 删除
    # → 解析命中后引擎按 actor=SUPERVISOR 拒绝。
    coordinator = _agent("rm-node-supervisor", "dag_guided")
    node_id = await _seed_lone_species(coordinator, session, "kept")
    supervisor = make_supervisor("rm-node-supervisor", workspace_dir=str(tmp_path))
    denied_sv = await _call(
        DagRemoveNode, supervisor, session, name=node_id, reason="cleanup"
    )
    assert not denied_sv.is_success
    assert denied_sv.rejection_code == "actor_forbidden"


@pytest.mark.asyncio
async def test_remove_node_resolves_by_name_and_id(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("rm-node-resolve", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    await _seed_lone_species(agent, session, "ethylene")

    # 名称解析
    by_name = await _call(
        DagRemoveNode, agent, session, name="ethylene", reason="stale"
    )
    assert by_name.accepted is True
    # ID 解析（重新种一个）
    node_id2 = await _seed_lone_species(agent, session, "propene")
    by_id = await _call(
        DagRemoveNode, agent, session, name=node_id2, reason="stale"
    )
    assert by_id.accepted is True


@pytest.mark.asyncio
async def test_remove_node_blank_inputs_rejected(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("rm-node-blank", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    await _seed_lone_species(agent, session, "blank-check")

    blank_name = await _call(DagRemoveNode, agent, session, name="   ", reason="cleanup")
    assert not blank_name.is_success
    assert "name" in blank_name.error

    blank_reason = await _call(DagRemoveNode, agent, session, name="blank-check", reason="  ")
    assert not blank_reason.is_success
    assert "reason" in blank_reason.error


@pytest.mark.asyncio
async def test_remove_node_missing_and_duplicate_delete(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("rm-node-missing-dup", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))

    missing = await _call(DagRemoveNode, agent, session, name="ghost", reason="cleanup")
    assert not missing.is_success
    assert "not found" in missing.error

    node_id = await _seed_lone_species(agent, session, "once")
    first = await _call(DagRemoveNode, agent, session, name=node_id, reason="cleanup")
    assert first.accepted is True
    second = await _call(DagRemoveNode, agent, session, name=node_id, reason="again")
    assert not second.is_success
    assert "not found" in second.error


@pytest.mark.asyncio
async def test_remove_node_with_edges_returns_actionable_error(tmp_path):
    """节点有连线时返回 node_has_edges 与关联边标识，可操作。"""
    get_config().data_dir = tmp_path
    agent = _agent("rm-node-linked", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    await _call(DagAddSpecies, agent, session, name="R")
    await _call(DagAddSpecies, agent, session, name="P")
    await _call(DagAddStep, agent, session, name="step1", from_="R", to="P")

    view = await _call(DagView, agent, session, graph_kind="delivery")
    r_id = next(n["node_id"] for n in view.result["nodes"] if n["label"] == "R")

    blocked = await _call(DagRemoveNode, agent, session, name=r_id, reason="cleanup")
    assert not blocked.is_success
    assert blocked.rejection_code == "node_has_edges"
    assert "step1" in blocked.error


@pytest.mark.asyncio
async def test_remove_node_cross_project_target_not_found(tmp_path):
    """跨项目目标：本会话图上不存在的名称/ID 解析为 not found。"""
    get_config().data_dir = tmp_path
    other = _agent("rm-node-other", "dag_record")
    other_session = Session("s1", str(tmp_path / "session.json"))
    other_id = await _seed_lone_species(other, other_session, "foreign")

    agent = _agent("rm-node-here", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    denied = await _call(DagRemoveNode, agent, session, name=other_id, reason="cleanup")
    assert not denied.is_success
    assert "not found" in denied.error


@pytest.mark.asyncio
async def test_remove_tools_share_resolution_rules(tmp_path):
    """删节点/删边使用一致解析规则：精确 ID 优先、名称兜底、歧义防护。"""
    get_config().data_dir = tmp_path
    agent = _agent("rm-resolve-shared", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    await _call(DagAddSpecies, agent, session, name="R")
    await _call(DagAddSpecies, agent, session, name="P")
    await _call(DagAddStep, agent, session, name="chair", from_="R", to="P")

    view = await _call(DagView, agent, session, graph_kind="delivery")
    edge_id = next(e["edge_id"] for e in view.result["edges"] if e["label"] == "chair")
    # 用 ID 删边成功
    by_id = await _call(DagRemoveEdge, agent, session, name=edge_id, reason="cleanup")
    assert by_id.accepted is True
    assert by_id.result["target_id"] == edge_id


# ---------------------------------------------------------------------------
# Task 5: issue #28 真实工具链（确定性 fixture / 阶段处置链）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_misbuilt_element_relieves_gap_keeps_others(tmp_path):
    """确定性交付图：额外节点缺 geometry 制造缺口；经 dag_remove_node 删除后
    该缺口消失，其余必需阶段缺口仍阻止完成。"""
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
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    get_config().data_dir = tmp_path
    agent = _agent("rm-gap-relief", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(agent.conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="harness",
            base_revisions=store.load_bundle().revisions,
            rationale="seed research target plus a misbuilt extra node",
            operations=[
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="r", label="R", evidence_level="structure_supported")),
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="p", label="P", evidence_level="structure_supported")),
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="extra", label="misbuilt extra",
                    stages=[StageState(kind="geometry")])),
                AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
                    edge_id="step1", source_node_id="r", target_node_id="p",
                    stages=[StageState(kind="ts_opt"), StageState(kind="frequency")])),
            ],
        )
    )
    assert seeded.accepted

    before = await _call(DagDeliveryReport, agent, session)
    assert before.result["complete"] is False
    before_targets = {g["target_id"] for g in before.result["unresolved"]}
    assert {"extra", "step1"} <= before_targets

    removed = await _call(
        DagRemoveNode, agent, session, name="extra", reason="not on the mechanism path"
    )
    assert removed.accepted is True

    after = await _call(DagDeliveryReport, agent, session)
    assert after.result["complete"] is False
    after_targets = {g["target_id"] for g in after.result["unresolved"]}
    assert "extra" not in after_targets
    assert "step1" in after_targets


@pytest.mark.asyncio
async def test_stage_disposition_chain_via_real_tools(tmp_path):
    """显式送审 → dag_view_evidence → dag_review_call(not_applicable) →
    dag_delivery_report：阶段处置链真实可调用，满足已有完成规则。"""
    from cloudra.dag.controller import DagController
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
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB
    from cloudra.tools.Plantool.dag_tools.dag_review_call import DagReviewCall
    from cloudra.tools.Plantool.dag_tools.dag_view_evidence import DagViewEvidence

    get_config().data_dir = tmp_path
    agent = _agent("chain-disposition", "dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(agent.conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    # 物种出现节点由 harness 落 structure_supported（模型不能伪造派生等级）。
    nodes_seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="harness",
            base_revisions=store.load_bundle().revisions,
            rationale="seed supported species occurrences",
            operations=[
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="r", label="R", evidence_level="structure_supported")),
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="p", label="P", evidence_level="structure_supported")),
            ],
        )
    )
    assert nodes_seeded.accepted
    # 阶段契约由 Coordinator（actor=AGENT）以全 pending 声明。
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="declare the stage contract for step1",
            operations=[
                AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
                    edge_id="step1", source_node_id="r", target_node_id="p",
                    stages=[StageState(kind="ts_opt"), StageState(kind="frequency")])),
            ],
        )
    )
    assert seeded.accepted
    controller = DagController(db, "s1", "dag_guided", conversation_id=agent.conversation_id)
    await controller.on_tool_finished(
        "tc-bind", "log_parser", {"log_path": "ts.log"}, _TS_FREQ_RESULT
    )
    submitted = await controller.submit_evidence_for_review([
        {"tool_call_id": "tc-bind", "bind_target": "step1", "stage_kind": "ts_opt",
         "claim": "the optimization converged"},
        {"tool_call_id": "tc-bind", "bind_target": "step1", "stage_kind": "frequency",
         "claim": "exactly one imaginary frequency"},
    ])
    assert all(a["enqueued"] for a in submitted["attachments"])

    reviews = DagStore(db).list_call_reviews("pending")
    assert len(reviews) == 2
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))

    # dag_view_evidence 读回送审快照（含 claim/arguments/result）
    view = await _call(
        DagViewEvidence, supervisor, session, review_id=reviews[0].review_id
    )
    assert view.is_success
    assert view.result["source_name"] == "log_parser"

    # dag_review_call not_applicable：无能垒步，无 TS 槽
    for review in reviews:
        out = await _call(
            DagReviewCall, supervisor, session,
            review_id=review.review_id, target_id="step1",
            stage_kind=review.suggested_stage, verdict="not_applicable",
            reason="barrierless association, no first-order saddle on this PES",
        )
        assert out.is_success and out.accepted is True

    report = await _call(DagDeliveryReport, agent, session)
    assert report.result["complete"] is True


@pytest.mark.asyncio
async def test_set_coverage_contract_is_supervisor_only(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-contract", "dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))

    denied = await _call(
        DagSetCoverageContract, agent, session, require_thermochemistry=True
    )
    assert not denied.is_success
    assert "supervisor-only" in denied.error

    supervisor = make_supervisor(agent.conversation_id, workspace_dir=str(tmp_path))
    tightened = await _call(
        DagSetCoverageContract, supervisor, session, require_thermochemistry=True
    )
    assert tightened.accepted is True


# ---------------------------------------------------------------------------
# bind_evidence / review_evidence
# ---------------------------------------------------------------------------

_TS_FREQ_RESULT = {
    "is_success": True,
    "normal_termination": True,
    "imaginary_frequencies": [-518.3],
}


async def _seed_staged_step(
    tmp_path,
    conversation_id,
    result,
    *,
    stage_kinds=("ts_opt", "frequency"),
    mode="dag_record",
):
    """种子：带阶段契约的 delivery 边 + 一次已完成的 log_parser 调用。

    阶段契约由 Coordinator（actor=agent, a-0）以全 pending 声明——引擎守卫
    只允许模型声明 pending 阶段。
    """
    from cloudra.dag.controller import DagController
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
    from cloudra.dag.store import DagStore

    get_config().data_dir = tmp_path
    agent = _agent(conversation_id, mode)
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(agent.conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
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
                        stages=[StageState(kind=kind) for kind in stage_kinds],
                    ),
                ),
            ],
        )
    )
    assert seeded.accepted
    controller = DagController(db, "s1", mode, conversation_id=agent.conversation_id)
    await controller.initialize()
    await controller.on_tool_finished(
        "tc-bind", "log_parser", {"log_path": "ts.log"}, result
    )
    return agent, session, db


def _delivery_edge(db, edge_id="step1"):
    from cloudra.dag.store import DagStore

    graph = DagStore(db).load_snapshot().delivery
    return next(e for e in graph.edges if e.edge_id == edge_id)


@pytest.mark.asyncio
async def test_stage_bind_makes_stages_supported_in_order(tmp_path):
    agent, session, db = await _seed_staged_step(
        tmp_path, "tool-stage-bind", _TS_FREQ_RESULT
    )

    first = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-bind", bind_target="step1", stage_kind="ts_opt",
    )
    assert first.is_success
    assert first.accepted is True
    second = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-bind", bind_target="step1", stage_kind="frequency",
    )
    assert second.is_success
    assert second.accepted is True

    edge = _delivery_edge(db)
    assert [(s.kind.value, s.status.value) for s in edge.stages] == [
        ("ts_opt", "supported"),
        ("frequency", "supported"),
    ]
    # 派生 evidence_level 只由阶段决定（D7）：ts_opt+frequency ⇒ saddle_supported
    assert edge.evidence_level == "saddle_supported"


@pytest.mark.asyncio
async def test_stage_bind_out_of_order_rejected(tmp_path):
    """frequency 先于 ts_opt 绑定 ⇒ stage_out_of_order，阶段保持 pending。"""
    agent, session, db = await _seed_staged_step(
        tmp_path, "tool-stage-order", _TS_FREQ_RESULT
    )

    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-bind", bind_target="step1", stage_kind="frequency",
    )

    assert not bound.is_success
    assert bound.accepted is False
    assert bound.rejection_code == "stage_out_of_order"
    edge = _delivery_edge(db)
    assert all(s.status.value == "pending" for s in edge.stages)
    assert edge.evidence_level == "proposed"


@pytest.mark.asyncio
async def test_ts_guess_agree_never_supports_saddle_stages(tmp_path):
    """ts_guess 是建议性阶段：agree 它绝不能充抵 ts_opt/frequency。"""
    from cloudra.dag.controller import DagController

    agent, session, db = await _seed_staged_step(
        tmp_path,
        "tool-stage-guess",
        _TS_FREQ_RESULT,
        stage_kinds=("ts_guess", "ts_opt", "frequency"),
    )
    controller = DagController(db, "s1", "dag_record", conversation_id=db.conversation_id)
    await controller.on_tool_finished(
        "tc-guess", "ts_guess", {"smiles": "C=COCC=C"},
        {"is_success": True, "verdict": "pass: ts-like"},
    )

    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-guess", bind_target="step1", stage_kind="ts_guess",
    )

    assert bound.is_success
    assert bound.accepted is True
    edge = _delivery_edge(db)
    by_kind = {s.kind.value: s.status.value for s in edge.stages}
    assert by_kind == {
        "ts_guess": "supported",
        "ts_opt": "pending",
        "frequency": "pending",
    }
    assert edge.evidence_level != "saddle_supported"


@pytest.mark.asyncio
async def test_pending_ts_guess_never_blocks_ts_opt_bind(tmp_path):
    """ts_guess 是 advisory 阶段：即使存量 v1 契约把它落库为 required=True，
    顺序门禁也不把它算作 blocker（生产 bug：stage_out_of_order 误拒合格的
    ts_opt 绑定）；ts_guess 自己仍可带理由跳过。"""
    from cloudra.dag.controller import DagController

    agent, session, db = await _seed_staged_step(
        tmp_path, "tool-stage-advisory", _TS_FREQ_RESULT,
        stage_kinds=("ts_guess", "ts_opt"),
    )

    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-bind", bind_target="step1", stage_kind="ts_opt",
    )
    assert bound.is_success
    assert bound.accepted is True
    by_kind = {s.kind.value: s.status.value for s in _delivery_edge(db).stages}
    assert by_kind == {"ts_guess": "pending", "ts_opt": "supported"}

    controller = DagController(db, "s1", "dag_record", conversation_id=db.conversation_id)
    skipped = await controller.apply_stage_bind(
        element_id="step1", stage_kind="ts_guess", ref=None,
        verdict="skip", reason="ts_opt already converged to the saddle",
        tool_succeeded=True,
    )
    assert skipped.accepted
    by_kind = {s.kind.value: s.status.value for s in _delivery_edge(db).stages}
    assert by_kind["ts_guess"] == "skipped"


@pytest.mark.asyncio
async def test_ts_guess_advisory_keeps_other_order_gates(tmp_path):
    """顺序门禁对其他阶段保持：frequency 仍要求 ts_opt 先 supported，
    且 blocker 列表只含 ts_opt，不含 advisory 的 ts_guess。"""
    agent, session, db = await _seed_staged_step(
        tmp_path, "tool-stage-order-kept", _TS_FREQ_RESULT,
        stage_kinds=("ts_guess", "ts_opt", "frequency"),
    )

    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-bind", bind_target="step1", stage_kind="frequency",
    )

    assert not bound.is_success
    assert bound.rejection_code == "stage_out_of_order"
    assert "ts_opt" in bound.error
    assert "ts_guess" not in bound.error
    assert all(s.status.value == "pending" for s in _delivery_edge(db).stages)


@pytest.mark.asyncio
async def test_agree_with_failed_call_is_a_rejected_bind(tmp_path):
    """tool_succeeded=False 的 agree 直接被拒，阶段保持 pending。"""
    from cloudra.dag.controller import DagController

    _agent, _session, db = await _seed_staged_step(
        tmp_path, "tool-stage-unsuccessful", _TS_FREQ_RESULT
    )
    controller = DagController(db, "s1", "dag_record", conversation_id=db.conversation_id)

    mutation = await controller.apply_stage_bind(
        element_id="step1",
        stage_kind="ts_opt",
        ref=None,
        verdict="agree",
        tool_succeeded=False,
    )

    assert not mutation.accepted
    assert mutation.rejection_code == "tool_not_succeeded"
    assert all(s.status.value == "pending" for s in _delivery_edge(db).stages)


@pytest.mark.asyncio
async def test_rejected_stage_blocks_later_stages_until_rebound(tmp_path):
    """D2：rejected 的前置阶段堵住后续阶段，直到它自己被重绑或带理由跳过。"""
    from cloudra.dag.controller import DagController
    from cloudra.dag.store import DagStore

    agent, session, db = await _seed_staged_step(
        tmp_path, "tool-stage-rebind", _TS_FREQ_RESULT
    )
    controller = DagController(db, "s1", "dag_record", conversation_id=db.conversation_id)
    await controller.initialize()

    no_reason = await controller.apply_stage_bind(
        element_id="step1", stage_kind="ts_opt", ref=None,
        verdict="skip", reason="  ", tool_succeeded=True,
    )
    assert not no_reason.accepted
    assert no_reason.rejection_code == "reason_required"

    rejected = await controller.apply_stage_bind(
        element_id="step1", stage_kind="ts_opt", ref=None,
        verdict="disagree",
        reason="optimization collapsed back to the reactant minimum",
        tool_succeeded=True,
    )
    assert rejected.accepted

    ref = DagStore(db).register_evidence(
        "s1", "log_parser", {"tool_call_id": "tc-bind", "result": _TS_FREQ_RESULT}
    )
    blocked = await controller.apply_stage_bind(
        element_id="step1", stage_kind="frequency", ref=ref,
        verdict="agree", tool_succeeded=True,
    )
    assert not blocked.accepted
    assert blocked.rejection_code == "stage_out_of_order"

    rebound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-bind", bind_target="step1", stage_kind="ts_opt",
    )
    assert rebound.is_success
    assert rebound.accepted is True
    by_kind = {s.kind.value: s.status.value for s in _delivery_edge(db).stages}
    assert by_kind["ts_opt"] == "supported"
    assert by_kind["frequency"] == "pending"


@pytest.mark.asyncio
async def test_bind_evidence_without_registered_evidence_rejected(tmp_path):
    agent, session, db = await _seed_staged_step(
        tmp_path, "tool-bind-noev", _TS_FREQ_RESULT
    )

    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-running", bind_target="step1", stage_kind="ts_opt",
    )

    assert not bound.is_success
    assert "no registered evidence" in bound.error
    assert all(s.status.value == "pending" for s in _delivery_edge(db).stages)


@pytest.mark.asyncio
async def test_bind_evidence_failed_call_rejected(tmp_path):
    agent, session, db = await _seed_staged_step(
        tmp_path,
        "tool-bind-failed",
        {"is_success": False, "error": "SCF not converged"},
    )

    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-bind", bind_target="step1", stage_kind="ts_opt",
    )

    assert not bound.is_success
    assert "did not succeed" in bound.error
    assert all(s.status.value == "pending" for s in _delivery_edge(db).stages)


@pytest.mark.asyncio
async def test_bind_evidence_rejected_in_standard_mode(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-bind-standard", "standard")
    session = Session("s1", str(tmp_path / "session.json"))

    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-x", bind_target="step1", stage_kind="ts_opt",
    )

    assert not bound.is_success
    assert "standard" in bound.error


@pytest.mark.asyncio
async def test_geometry_bind_requires_verified_minimum(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddNode,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        StageState,
    )
    from cloudra.dag.store import DagStore

    get_config().data_dir = tmp_path
    conversation_id = "geom-min-check"
    db = ConversationDB(conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="declare geometry contract",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="int1",
                        label="Int1",
                        role="intermediate",
                        stages=[StageState(kind="geometry")],
                    ),
                ),
            ],
        )
    )
    assert seeded.accepted
    controller = DagController(db, "s1", "dag_record", conversation_id=conversation_id)
    await controller.initialize()

    ts_ref = store.register_evidence(
        "s1",
        "log_parser",
        {
            "tool_call_id": "tc-ts",
            "result": {
                "is_success": True,
                "normal_termination": True,
                "imaginary_frequencies": [-400.0],
            },
        },
    )
    rejected = await controller.apply_stage_bind(
        element_id="int1",
        stage_kind="geometry",
        ref=ts_ref,
        verdict="agree",
        tool_succeeded=True,
    )
    assert not rejected.accepted
    assert rejected.rejection_code == "minimum_check_failed"

    min_ref = store.register_evidence(
        "s1",
        "log_parser",
        {
            "tool_call_id": "tc-min",
            "result": {
                "is_success": True,
                "normal_termination": True,
                "frequencies": [100.0, 200.0, 1500.0],
                "imaginary_frequencies": [],
            },
        },
    )
    accepted = await controller.apply_stage_bind(
        element_id="int1",
        stage_kind="geometry",
        ref=min_ref,
        verdict="agree",
        tool_succeeded=True,
    )
    assert accepted.accepted is True


@pytest.mark.asyncio
async def test_geometry_bind_requires_normal_termination(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddNode,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        StageState,
    )
    from cloudra.dag.store import DagStore
    from cloudra.infra.config import get_config
    from cloudra.persistence.database import ConversationDB

    get_config().data_dir = tmp_path
    conversation_id = "geom-term-check"
    db = ConversationDB(conversation_id).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="declare geometry contract",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id="int1",
                        label="Int1",
                        role="intermediate",
                        stages=[StageState(kind="geometry")],
                    ),
                ),
            ],
        )
    )
    assert seeded.accepted
    controller = DagController(db, "s1", "dag_record", conversation_id=conversation_id)
    await controller.initialize()
    unfinished = store.register_evidence(
        "s1",
        "log_parser",
        {
            "tool_call_id": "tc-unfinished",
            "result": {
                "is_success": True,
                "frequencies": [100.0, 200.0, 1500.0],
                "imaginary_frequencies": [],
            },
        },
    )
    rejected = await controller.apply_stage_bind(
        element_id="int1",
        stage_kind="geometry",
        ref=unfinished,
        verdict="agree",
        tool_succeeded=True,
    )
    assert not rejected.accepted
    assert rejected.rejection_code == "minimum_check_failed"


@pytest.mark.asyncio
async def test_ts_opt_bind_requires_normal_termination(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.store import DagStore

    agent, _session, db = await _seed_staged_step(
        tmp_path, "ts-opt-term", {"is_success": True}, mode="dag_record"
    )
    store = DagStore(db)
    unfinished = store.register_evidence(
        "s1",
        "log_parser",
        {
            "tool_call_id": "tc-opt-bad",
            "result": {"is_success": True, "normal_termination": False},
        },
    )
    controller = DagController(db, "s1", "dag_record", conversation_id=agent.conversation_id)
    await controller.initialize()
    rejected = await controller.apply_stage_bind(
        element_id="step1",
        stage_kind="ts_opt",
        ref=unfinished,
        verdict="agree",
        tool_succeeded=True,
    )
    assert not rejected.accepted
    assert rejected.rejection_code == "ts_opt_check_failed"

    ok_ref = store.register_evidence(
        "s1",
        "log_parser",
        {
            "tool_call_id": "tc-opt-ok",
            "result": {"is_success": True, "normal_termination": True},
        },
    )
    accepted = await controller.apply_stage_bind(
        element_id="step1",
        stage_kind="ts_opt",
        ref=ok_ref,
        verdict="agree",
        tool_succeeded=True,
    )
    assert accepted.accepted is True


@pytest.mark.asyncio
async def test_short_irc_bind_requires_path_evidence(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.store import DagStore

    agent, _session, db = await _seed_staged_step(
        tmp_path,
        "short-irc-guard",
        {"is_success": True, "normal_termination": True},
        stage_kinds=("short_irc",),
        mode="dag_record",
    )
    store = DagStore(db)
    thin = store.register_evidence(
        "s1",
        "log_parser",
        {
            "tool_call_id": "tc-irc-thin",
            "result": {"is_success": True, "normal_termination": True},
        },
    )
    controller = DagController(db, "s1", "dag_record", conversation_id=agent.conversation_id)
    await controller.initialize()
    rejected = await controller.apply_stage_bind(
        element_id="step1",
        stage_kind="short_irc",
        ref=thin,
        verdict="agree",
        tool_succeeded=True,
    )
    assert not rejected.accepted
    assert rejected.rejection_code == "short_irc_check_failed"

    ok_ref = store.register_evidence(
        "s1",
        "log_parser",
        {
            "tool_call_id": "tc-irc-ok",
            "result": {
                "is_success": True,
                "normal_termination": True,
                "irc_both_directions_converged": True,
            },
        },
    )
    accepted = await controller.apply_stage_bind(
        element_id="step1",
        stage_kind="short_irc",
        ref=ok_ref,
        verdict="agree",
        tool_succeeded=True,
    )
    assert accepted.accepted is True


@pytest.mark.asyncio
async def test_thermochemistry_bind_requires_complete_status(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.store import DagStore

    agent, _session, db = await _seed_staged_step(
        tmp_path,
        "thermo-guard",
        {"is_success": True, "status": "inconclusive"},
        stage_kinds=("thermochemistry",),
        mode="dag_record",
    )
    store = DagStore(db)
    incomplete = store.register_evidence(
        "s1",
        "thermo_analysis",
        {
            "tool_call_id": "tc-thermo-bad",
            "result": {"is_success": True, "status": "inconclusive"},
        },
    )
    controller = DagController(db, "s1", "dag_record", conversation_id=agent.conversation_id)
    await controller.initialize()
    rejected = await controller.apply_stage_bind(
        element_id="step1",
        stage_kind="thermochemistry",
        ref=incomplete,
        verdict="agree",
        tool_succeeded=True,
    )
    assert not rejected.accepted
    assert rejected.rejection_code == "thermochemistry_check_failed"

    ok_ref = store.register_evidence(
        "s1",
        "thermo_analysis",
        {
            "tool_call_id": "tc-thermo-ok",
            "result": {"is_success": True, "status": "complete"},
        },
    )
    accepted = await controller.apply_stage_bind(
        element_id="step1",
        stage_kind="thermochemistry",
        ref=ok_ref,
        verdict="agree",
        tool_succeeded=True,
    )
    assert accepted.accepted is True


@pytest.mark.asyncio
async def test_batch_ts_opt_bind_requires_normal_termination(tmp_path):
    from cloudra.dag.controller import DagController

    agent, _session, db = await _seed_staged_step(
        tmp_path, "ts-opt-batch", {"is_success": True}, mode="dag_record"
    )
    controller = DagController(db, "s1", "dag_record", conversation_id=agent.conversation_id)
    await controller.initialize()
    await controller.on_tool_finished(
        "tc-opt-bad",
        "log_parser",
        {"log_path": "opt.log"},
        {"is_success": True, "normal_termination": False},
    )
    await controller.on_tool_finished(
        "tc-freq-ok",
        "log_parser",
        {"log_path": "freq.log"},
        _TS_FREQ_RESULT,
    )
    rejected = await controller.bind_stage_attachments(
        [
            {
                "tool_call_id": "tc-opt-bad",
                "bind_target": "step1",
                "stage_kind": "ts_opt",
            },
            {
                "tool_call_id": "tc-freq-ok",
                "bind_target": "step1",
                "stage_kind": "frequency",
            },
        ]
    )
    assert rejected["accepted"] is False
    assert rejected["rejection_code"] == "ts_opt_check_failed"


@pytest.mark.asyncio
async def test_stage_bind_recomputes_stages_after_stale_revision(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import MutationResult
    from cloudra.dag.store import DagStore

    agent, _session, db = await _seed_staged_step(
        tmp_path, "stale-recompute", _TS_FREQ_RESULT, mode="dag_record"
    )
    store = DagStore(db)
    controller = DagController(db, "s1", "dag_record", conversation_id=agent.conversation_id)
    await controller.initialize()
    opt_ref = store.register_evidence(
        "s1",
        "log_parser",
        {
            "tool_call_id": "tc-opt-conc",
            "result": {"is_success": True, "normal_termination": True},
        },
    )
    original = controller._apply_with_revisions
    calls: list[list[dict]] = []

    def _stale_then_apply(operations, rationale, revisions):
        from cloudra.dag.engine import DagEngine, apply_stage_verdict
        from cloudra.dag.models import (
            GraphActor,
            MutationBatch,
            StageKind,
            UpdateEdge,
        )

        stages = operations[-1].changes["stages"]
        calls.append(stages)
        if len(calls) == 1:
            snapshot = store.load_snapshot()
            edge = next(e for e in snapshot.delivery.edges if e.edge_id == "step1")
            concurrent_stages = apply_stage_verdict(
                list(edge.stages),
                stage_kind=StageKind.FREQUENCY,
                verdict="skip",
                reason="no isolated hessian on this path",
                ref=None,
                tool_succeeded=False,
            )
            bumped = DagEngine(store).apply_batch(
                MutationBatch(
                    session_id="s1",
                    actor=GraphActor.HARNESS,
                    actor_id="concurrent",
                    base_revisions=dict(snapshot.bundle.revisions),
                    operations=[
                        UpdateEdge(
                            op="update_edge",
                            graph="delivery",
                            edge_id="step1",
                            changes={
                                "stages": [
                                    stage.model_dump(mode="json")
                                    for stage in concurrent_stages
                                ],
                            },
                        )
                    ],
                    rationale="concurrent skip frequency",
                )
            )
            assert bumped.accepted is True
            return MutationResult(
                accepted=False,
                mutation_id="mut_stale",
                revisions=dict(store.load_bundle().revisions),
                rejection_code="stale_revision",
                rejection_reason="injected concurrent skip",
            )
        assert any(
            stage.get("kind") == "frequency" and stage.get("status") == "skipped"
            for stage in stages
        )
        return original(operations, rationale, revisions)

    controller._apply_with_revisions = _stale_then_apply
    accepted = await controller.apply_stage_bind(
        element_id="step1",
        stage_kind="ts_opt",
        ref=opt_ref,
        verdict="agree",
        tool_succeeded=True,
    )
    assert accepted.accepted is True
    edge = next(e for e in store.load_snapshot().delivery.edges if e.edge_id == "step1")
    by_kind = {stage.kind.value: stage.status.value for stage in edge.stages}
    assert by_kind["frequency"] == "skipped"
    assert by_kind["ts_opt"] == "supported"


@pytest.mark.asyncio
async def test_batch_bind_recomputes_stages_after_stale_revision(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import MutationResult
    from cloudra.dag.store import DagStore

    agent, _session, db = await _seed_staged_step(
        tmp_path, "stale-batch", _TS_FREQ_RESULT, mode="dag_record"
    )
    store = DagStore(db)
    controller = DagController(db, "s1", "dag_record", conversation_id=agent.conversation_id)
    await controller.initialize()
    await controller.on_tool_finished(
        "tc-opt-batch",
        "log_parser",
        {"log_path": "opt.log"},
        {"is_success": True, "normal_termination": True},
    )
    original = controller._apply_with_revisions
    calls: list[list[dict]] = []

    def _stale_then_apply(operations, rationale, revisions):
        from cloudra.dag.engine import DagEngine, apply_stage_verdict
        from cloudra.dag.models import (
            GraphActor,
            MutationBatch,
            StageKind,
            UpdateEdge,
        )

        stages = operations[-1].changes["stages"]
        calls.append(stages)
        if len(calls) == 1:
            snapshot = store.load_snapshot()
            edge = next(e for e in snapshot.delivery.edges if e.edge_id == "step1")
            concurrent_stages = apply_stage_verdict(
                list(edge.stages),
                stage_kind=StageKind.FREQUENCY,
                verdict="skip",
                reason="no isolated hessian on this path",
                ref=None,
                tool_succeeded=False,
            )
            bumped = DagEngine(store).apply_batch(
                MutationBatch(
                    session_id="s1",
                    actor=GraphActor.HARNESS,
                    actor_id="concurrent",
                    base_revisions=dict(snapshot.bundle.revisions),
                    operations=[
                        UpdateEdge(
                            op="update_edge",
                            graph="delivery",
                            edge_id="step1",
                            changes={
                                "stages": [
                                    stage.model_dump(mode="json")
                                    for stage in concurrent_stages
                                ],
                            },
                        )
                    ],
                    rationale="concurrent skip frequency",
                )
            )
            assert bumped.accepted is True
            return MutationResult(
                accepted=False,
                mutation_id="mut_stale_batch",
                revisions=dict(store.load_bundle().revisions),
                rejection_code="stale_revision",
                rejection_reason="injected concurrent skip",
            )
        assert any(
            stage.get("kind") == "frequency" and stage.get("status") == "skipped"
            for stage in stages
        )
        return original(operations, rationale, revisions)

    controller._apply_with_revisions = _stale_then_apply
    accepted = await controller.bind_stage_attachments(
        [
            {
                "tool_call_id": "tc-opt-batch",
                "bind_target": "step1",
                "stage_kind": "ts_opt",
            }
        ]
    )
    assert accepted["accepted"] is True
    edge = next(e for e in store.load_snapshot().delivery.edges if e.edge_id == "step1")
    by_kind = {stage.kind.value: stage.status.value for stage in edge.stages}
    assert by_kind["frequency"] == "skipped"
    assert by_kind["ts_opt"] == "supported"


@pytest.mark.asyncio
async def test_bind_evidence_submits_for_review_in_guided_mode(tmp_path):
    """dag_guided 下 dag_bind_evidence 是显式送审口：带 claim 把任意已完成
    调用的产物提交进 review 收件箱（§5 起唯一入箱路径，无白名单自动入箱）。"""
    from cloudra.dag.controller import DagController
    from cloudra.dag.store import DagStore

    agent, session, db = await _seed_staged_step(
        tmp_path, "tool-bind-guided", _TS_FREQ_RESULT, mode="dag_guided"
    )
    controller = DagController(db, "s1", "dag_guided", conversation_id=agent.conversation_id)
    # format_converter 只登记证据（§5 起任何工具完成都不自动入箱）。
    await controller.on_tool_finished(
        "tc-conv", "format_converter", {"input_path": "irc.log"}, {"is_success": True, "output_path": "irc.csv"}
    )
    assert all(r.tool_name != "format_converter" for r in DagStore(db).list_call_reviews())

    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-conv", bind_target="step1", stage_kind="ts_opt",
        claim="the converted IRC CSV anchors the TS optimization stage",
    )
    assert bound.is_success is True
    assert bound.accepted is True

    submitted = next(
        r for r in DagStore(db).list_call_reviews() if r.tool_name == "format_converter"
    )
    assert submitted.suggested_target_id == "step1"
    assert submitted.suggested_stage == "ts_opt"
    assert submitted.claim == "the converted IRC CSV anchors the TS optimization stage"
    assert submitted.source == "explicit"
    assert submitted.state == "pending"


@pytest.mark.asyncio
async def test_message_supervisor_persists_request_without_graph_change(tmp_path):
    """§4：纯文本督导消息落持久化 ReviewRequest（kind=exception），返回
    queued 语义（request_id），不是"已送达/已裁决"。"""

    get_config().data_dir = tmp_path
    agent = _agent("tool-msg-supervisor", "dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))

    out = await _call(
        DagMessageSupervisor, agent, session, message="请为 TS 补排产"
    )
    assert out.is_success
    assert out.accepted is True
    assert out.result["enqueued"] is True
    assert out.result["kind"] == "exception"
    assert "请为 TS 补排产" in out.result["question"]

    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    request = DagStore(ConversationDB("tool-msg-supervisor")).get_review_request(
        out.result["request_id"]
    )
    assert request is not None
    assert request.state == "queued"
    assert request.question == "请为 TS 补排产"
    assert request.requester == "s1"

    empty = await _call(DagMessageSupervisor, agent, session, message="  ")
    assert empty.is_success is False
    assert "non-empty" in empty.error

    supervisor = make_supervisor("tool-msg-supervisor-sv", workspace_dir=str(tmp_path))
    blocked = await _call(
        DagMessageSupervisor, supervisor, session, message="nope"
    )
    assert blocked.is_success is False
    assert "Coordinator" in blocked.error

    follower = make_subagent(
        "tool-msg-supervisor-f", "small_mol", orchestration_mode="dag_guided"
    )
    from_follower = await _call(
        DagMessageSupervisor, follower, session, message="请排产"
    )
    assert from_follower.is_success is False
    assert "Coordinator-only" in from_follower.error


@pytest.mark.asyncio
async def test_tool_finish_writes_no_graph_telemetry(tmp_path):
    """证据 b/i-1 回归：工具完成只登记证据（§5 起不再收件箱 enqueue），
    不写任何 process 遥测节点（observed_<hex> 洪泛与 stale_revision 风暴
    的根因）。"""
    from cloudra.dag.store import DagStore

    _agent, _session, db = await _seed_staged_step(
        tmp_path, "tool-no-telemetry", _TS_FREQ_RESULT
    )
    snapshot = DagStore(db).load_snapshot()
    assert snapshot.process.nodes == []
    assert snapshot.process.edges == []


@pytest.mark.asyncio
async def test_submit_compute_job_call_is_never_stage_evidence(tmp_path):
    """D11：submit_compute_job 的调用不是计算完成的证据——绑定被拒
    （bind_target_is_submit），阶段保持 pending。"""
    from cloudra.dag.controller import DagController
    from cloudra.dag.store import DagStore

    agent, session, db = await _seed_staged_step(
        tmp_path, "tool-bind-submit", _TS_FREQ_RESULT
    )
    submit_ref = DagStore(db).register_evidence(
        "s1",
        "submit_compute_job",
        {
            "tool_call_id": "tc-submit",
            "arguments": {"input_file": "ts.gjf"},
            "result": {"is_success": True, "job_id": 4},
        },
    )
    controller = DagController(db, "s1", "dag_record", conversation_id=db.conversation_id)

    mutation = await controller.apply_stage_bind(
        element_id="step1", stage_kind="ts_opt", ref=submit_ref,
        verdict="agree", tool_succeeded=True,
    )

    assert not mutation.accepted
    assert mutation.rejection_code == "bind_target_is_submit"
    assert all(s.status.value == "pending" for s in _delivery_edge(db).stages)

    # 同一工具调用走 dag_bind_evidence 高层入口同样被拒
    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-submit", bind_target="step1", stage_kind="ts_opt",
    )
    assert not bound.is_success
    assert bound.rejection_code == "bind_target_is_submit"


@pytest.mark.asyncio
async def test_supervisor_view_reads_persisted_drafts_and_explicit_reviews(tmp_path):
    import asyncio

    from cloudra.dag.controller import DagController
    from cloudra.dag.models import CallReview
    from tests.test_dag_supervisor_feedback import _OPS

    agent = make_supervisor(conversation_id="view-inbox", orchestration_mode="dag_guided")
    session = Session("supervisor-view", str(tmp_path / "session.json"))
    db = await asyncio.to_thread(ConversationDB("view-inbox").init)
    controller = DagController(db, "coordinator", "dag_guided")
    await controller.initialize()
    drafts = []
    revision_ops = [{
        "op": "update_edge", "graph": "delivery", "edge_id": "step1",
        "changes": {"label": "revised step1"},
    }]
    for rationale, operations in (("first hypothesis", _OPS), ("revised hypothesis", revision_ops)):
        drafts.append(await controller.propose_mechanism(
            operations=operations,
            stage_contracts={"step1": ["ts_guess"]} if operations is _OPS else {},
            rationale=rationale, actor_id="a-0",
        ))
    for source in ("explicit", "legacy_auto"):
        await asyncio.to_thread(controller.store.enqueue_call_review, CallReview(
            review_id=source, tool_call_id=source, tool_name="read_file",
            is_success=True, source=source, claim="Evidence supports step1",
        ))

    viewed = await _call(DagView, agent, session)

    assert {d["draft_id"] for d in viewed.result["open_drafts"]} == {
        d["draft_id"] for d in drafts
    }
    assert [r["review_id"] for r in viewed.result["pending_reviews"]] == ["explicit"]
    assert viewed.result["pending_reviews"][0]["claim"] == "Evidence supports step1"
    await asyncio.to_thread(controller.store.set_draft_state, drafts[0]["draft_id"], "rejected")
    await asyncio.to_thread(controller.store.mark_call_review, "explicit", "reviewed")
    refreshed = await _call(DagView, agent, session)
    assert [d["draft_id"] for d in refreshed.result["open_drafts"]] == [drafts[1]["draft_id"]]
    assert refreshed.result["pending_reviews"] == []


@pytest.mark.asyncio
async def test_dag_view_lists_queued_structured_requests(tmp_path):
    """dag_message_supervisor 入箱的结构化请求必须能在 dag_view 读到——
    supervision 唤醒通知点名"queued review requests"，视图不投影的话被唤醒的
    Supervisor 在 store 里找不到待裁决请求（benchmark C1 实测死循环根因）。"""
    get_config().data_dir = tmp_path
    agent = _agent("tool-view-queued-requests", "dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))

    sent = await _call(
        DagMessageSupervisor, agent, session,
        kind="exception",
        question="dispose barrierless step TS stages as not_applicable?",
    )
    assert sent.is_success

    view = await _call(DagView, agent, session, graph_kind="both")
    queued = view.result["queued_requests"]
    assert len(queued) == 1
    assert queued[0]["kind"] == "exception"
    assert "not_applicable" in queued[0]["question"]
    assert queued[0]["request_id"]
