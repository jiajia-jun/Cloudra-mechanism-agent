import pytest
from pydantic import ValidationError

from cloudra.base.session_class import Session
from cloudra.core.agent import Coordinator
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


def _agent(conversation_id, mode):
    return Coordinator(
        query="study a mechanism",
        conversation_id=conversation_id,
        orchestration_mode=mode,
    )


def _schema(cls):
    return cls.model_fields["input_schema"].default


async def _call(cls, agent, session, **kwargs):
    return await cls(subagent=agent).tool_call(_schema(cls)(**kwargs), session)


_DAG_TOOL_NAMES = {
    "dag_view",
    "dag_delivery_report",
    "dag_add_species",
    "dag_add_step",
    "dag_update_delivery_element",
    "dag_remove_edge",
    "dag_bind_evidence",
    "dag_propose_mechanism",
    "dag_accept_mechanism",
    "dag_review_call",
    "dag_set_coverage_contract",
    "dag_message_supervisor",
}


def test_dag_tools_hidden_in_standard_and_visible_in_dag_modes():
    standard = _agent("tool-standard-visible", "standard")
    record = _agent("tool-record-visible", "dag_record")

    standard_names = {entry.tool_name for entry in standard.get_available_tools()}
    record_names = {entry.tool_name for entry in record.get_available_tools()}
    assert not (_DAG_TOOL_NAMES & standard_names)
    assert _DAG_TOOL_NAMES <= record_names
    assert "dag_graph" not in record_names


def test_add_species_schema_requires_core_fields():
    with pytest.raises(ValidationError):
        DagAddSpeciesInput(label="R", role="reactant")
    with pytest.raises(ValidationError):
        DagAddSpeciesInput(node_id="r", role="reactant")
    with pytest.raises(ValidationError):
        DagRemoveEdgeInput(graph="process", edge_id="e1", rationale="")


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
        DagAddSpecies, agent, session, node_id="r", label="C=COCC=C", role="reactant"
    )
    added_p = await _call(
        DagAddSpecies, agent, session, node_id="p", label="C=CCCC=O", role="product"
    )
    added_step = await _call(
        DagAddStep,
        agent,
        session,
        edge_id="chair",
        source_node_id="r",
        target_node_id="p",
        label="chair [3,3]",
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
        DagAddSpecies, agent, session, node_id="r", label="CCO", role="reactant"
    )

    assert mutated.is_success
    assert mutated.accepted is True
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_deleted_process_tools_are_unregistered(tmp_path):
    """Phase 4：四个 process 时代工具已从注册表移除。"""
    record = _agent("tool-deleted", "dag_record")
    record_names = {entry.tool_name for entry in record.get_available_tools()}
    for name in (
        "dag_schedule_work",
        "dag_update_process_node",
        "dag_init_from_template",
    ):
        assert name not in record_names
    # Task 6 reintroduces dag_review_evidence for v2 structured review requests.
    assert "dag_review_evidence" in record_names


@pytest.mark.asyncio
async def test_supervisor_actor_cannot_design_delivery(tmp_path):
    """type=supervisor 的调用者被派生为 actor=SUPERVISOR：delivery 只读。"""
    from cloudra.core.supervisor import SupervisorAgent

    get_config().data_dir = tmp_path
    agent = SupervisorAgent(
        conversation_id="tool-supervisor-actor",
        orchestration_mode="dag_guided",
    )
    session = Session("s1", str(tmp_path / "session.json"))

    designed = await _call(
        DagAddSpecies, agent, session, node_id="r", label="reactant", role="reactant"
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
            node_id=f"n{i}",
            label=f"candidate {i}",
            role="intermediate",
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
            node_id=f"n{i}",
            label=f"candidate {i}",
            role="intermediate",
            metadata={"status": "ready" if i % 2 else "proposed"},
        )
        assert out.accepted

    by_id = await _call(
        DagView, agent, session, graph_kind="delivery", node_ids=["n1", "n3"]
    )
    assert by_id.result["total_nodes"] == 2
    assert {node["node_id"] for node in by_id.result["nodes"]} == {"n1", "n3"}
    assert by_id.result["filters"] == {"node_ids": ["n1", "n3"]}

    by_status = await _call(
        DagView, agent, session, graph_kind="delivery", status_filter="proposed"
    )
    assert by_status.result["total_nodes"] == 2
    assert {node["node_id"] for node in by_status.result["nodes"]} == {"n0", "n2"}

    combined = await _call(
        DagView,
        agent,
        session,
        graph_kind="delivery",
        node_ids=["n0", "n1"],
        status_filter="ready",
    )
    assert combined.result["total_nodes"] == 1
    assert combined.result["nodes"][0]["node_id"] == "n1"


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
async def test_update_delivery_element_relabels_by_id_lookup(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-upd-delivery", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    added = await _call(
        DagAddSpecies, agent, session, node_id="r", label="old", role="reactant"
    )
    assert added.accepted
    updated = await _call(
        DagUpdateDeliveryElement, agent, session, element_id="r", label="ethylene"
    )
    assert updated.accepted
    view = await _call(DagView, agent, session, graph_kind="delivery")
    node = next(n for n in view.result["nodes"] if n["node_id"] == "r")
    assert node["label"] == "ethylene"


@pytest.mark.asyncio
async def test_remove_edge_requires_rationale_and_process_is_gone(tmp_path):
    get_config().data_dir = tmp_path
    agent = _agent("tool-rm-edge", "dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    await _call(DagAddSpecies, agent, session, node_id="r", label="R", role="reactant")
    await _call(DagAddSpecies, agent, session, node_id="p", label="P", role="product")
    step = await _call(
        DagAddStep,
        agent,
        session,
        edge_id="step1",
        source_node_id="r",
        target_node_id="p",
    )
    assert step.accepted

    removed = await _call(
        DagRemoveEdge,
        agent,
        session,
        graph="delivery",
        edge_id="step1",
        rationale="chair path ruled out by mapping",
    )
    assert removed.accepted is True

    blocked = await _call(
        DagRemoveEdge,
        agent,
        session,
        graph="process",
        edge_id="dep_a_b",
        rationale="no longer needed",
    )
    assert not blocked.accepted
    assert blocked.rejection_code == "process_graph_removed"


@pytest.mark.asyncio
async def test_set_coverage_contract_is_supervisor_only(tmp_path):
    from cloudra.core.supervisor import SupervisorAgent

    get_config().data_dir = tmp_path
    agent = _agent("tool-contract", "dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))

    denied = await _call(
        DagSetCoverageContract, agent, session, require_thermochemistry=True
    )
    assert not denied.is_success
    assert "supervisor-only" in denied.error

    supervisor = SupervisorAgent(
        conversation_id=agent.conversation_id, orchestration_mode="dag_guided"
    )
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
async def test_bind_evidence_submits_for_review_in_guided_mode(tmp_path):
    """dag_guided 下 dag_bind_evidence 是证据通交通道：把白名单外工具的
    产物提交进 review 收件箱（不再 disabled）。"""
    from cloudra.dag.controller import DagController
    from cloudra.dag.store import DagStore

    agent, session, db = await _seed_staged_step(
        tmp_path, "tool-bind-guided", _TS_FREQ_RESULT, mode="dag_guided"
    )
    controller = DagController(db, "s1", "dag_guided", conversation_id=agent.conversation_id)
    # format_converter 只登记证据、不入箱（非 dag_review 白名单）。
    await controller.on_tool_finished(
        "tc-conv", "format_converter", {"input_path": "irc.log"}, {"is_success": True, "output_path": "irc.csv"}
    )
    assert all(r.tool_name != "format_converter" for r in DagStore(db).list_call_reviews())

    bound = await _call(
        DagBindEvidence, agent, session,
        tool_call_id="tc-conv", bind_target="step1", stage_kind="short_irc",
    )
    assert bound.is_success is True
    assert bound.accepted is True

    submitted = next(
        r for r in DagStore(db).list_call_reviews() if r.tool_name == "format_converter"
    )
    assert submitted.suggested_target_id == "step1"
    assert submitted.suggested_stage == "short_irc"
    assert submitted.state == "pending"


@pytest.mark.asyncio
async def test_message_supervisor_delivers_without_graph_change(tmp_path):
    from cloudra.core.supervisor import SupervisorAgent

    get_config().data_dir = tmp_path
    agent = _agent("tool-msg-supervisor", "dag_guided")
    session = Session("s1", str(tmp_path / "session.json"))

    out = await _call(
        DagMessageSupervisor, agent, session, message="请为 TS 补排产"
    )
    assert out.is_success
    assert out.accepted is True
    assert out.result["delivered"] is True
    assert "请为 TS 补排产" in out.result["message"]

    empty = await _call(DagMessageSupervisor, agent, session, message="  ")
    assert empty.is_success is False
    assert "non-empty" in empty.error

    supervisor = SupervisorAgent(
        conversation_id="tool-msg-supervisor-sv",
        orchestration_mode="dag_guided",
    )
    blocked = await _call(
        DagMessageSupervisor, supervisor, session, message="nope"
    )
    assert blocked.is_success is False
    assert "Coordinator" in blocked.error

    from cloudra.core.agent import Follower

    follower = Follower(
        id="a-4",
        name="small_mol",
        query="opt",
        conversation_id="tool-msg-supervisor-f",
        orchestration_mode="dag_guided",
    )
    from_follower = await _call(
        DagMessageSupervisor, follower, session, message="请排产"
    )
    assert from_follower.is_success is False
    assert "Coordinator-only" in from_follower.error


@pytest.mark.asyncio
async def test_tool_finish_writes_no_graph_telemetry(tmp_path):
    """证据 b/i-1 回归：工具完成只登记证据 + 收件箱 enqueue，不再写任何
    process 遥测节点（observed_<hex> 洪泛与 stale_revision 风暴的根因）。"""
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
