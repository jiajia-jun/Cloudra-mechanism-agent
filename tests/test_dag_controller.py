
import pytest

from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store


def _controller_api():
    try:
        from cloudra.dag.controller import DagController
        from cloudra.dag.models import OrchestrationMode
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"DAG controller API is missing: {exc}")
    return DagController, OrchestrationMode


def _db_with_session(tmp_path, conversation_id, mode):
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
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


@pytest.mark.asyncio
async def test_standard_controller_does_not_initialize_or_record_graph(tmp_path):
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-standard", "standard")
    controller = DagController(db, "s1", OrchestrationMode.STANDARD)

    await controller.initialize()
    await controller.on_tool_started(
        "tc1", "reaction_mapping", {"reactant_smiles": "C=COCC=C"}
    )
    ref = await controller.on_tool_finished(
        "tc1",
        "reaction_mapping",
        {"reactant_smiles": "C=COCC=C"},
        {"mapping_status": "unique", "heavy_atom_map": [1, 2, 3, 4, 5, 6]},
    )

    assert ref is None
    assert await controller.prompt_projection() == ""
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM dag_evidence").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_record_mode_persists_full_result_before_context_truncation(tmp_path):
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-record", "dag_record")
    controller = DagController(db, "s1", OrchestrationMode.DAG_RECORD)
    await controller.initialize()
    arguments = {"reactant_smiles": "C=COCC=C", "product_smiles": "C=CCCC=O"}
    result = {
        "mapping_status": "unique",
        "heavy_atom_map": [1, 2, 3, 4, 5, 6],
        "large_body": "x" * 2_000,
    }

    await controller.on_tool_started("tc1", "reaction_mapping", arguments)
    ref = await controller.on_tool_finished(
        "tc1", "reaction_mapping", arguments, result
    )

    persisted = controller.store.resolve_evidence(ref)
    node = next(
        node
        for node in controller.engine.snapshot().process.nodes
        if node.payload.get("tool_call_id") == "tc1"
    )
    assert persisted["result"] == result
    assert node.payload["status"] == "succeeded"
    assert ref in node.refs


@pytest.mark.asyncio
async def test_output_file_is_snapshotted_as_artifact_pointer(tmp_path):
    from cloudra.infra.config import get_config

    DagController, OrchestrationMode = _controller_api()
    get_config().data_dir = tmp_path
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    xyz = workspace / "ts.xyz"
    xyz.write_text("1\nTS\nH 0 0 0\n", encoding="utf-8")
    db = _db_with_session(tmp_path, "controller-artifact", "dag_record")
    controller = DagController(
        db,
        "s1",
        OrchestrationMode.DAG_RECORD,
        working_directory=workspace,
        artifact_data_dir=tmp_path,
    )
    await controller.initialize()

    await controller.on_tool_started("tc2", "ts_guess", {"mode": "scan_parse"})
    await controller.on_tool_finished(
        "tc2",
        "ts_guess",
        {"mode": "scan_parse"},
        {"is_success": True, "ts_candidate_path": str(xyz)},
    )

    node = next(
        node
        for node in controller.engine.snapshot().process.nodes
        if node.payload.get("tool_call_id") == "tc2"
    )
    artifact_refs = [ref for ref in node.refs if ref.ref_type == "artifact"]
    assert len(artifact_refs) == 1
    assert artifact_refs[0].content_hash.startswith("sha256:")
    assert all(ref.ref_id != str(xyz) for ref in node.refs)
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_ts_guess_remains_advisory_for_delivery_edge(tmp_path):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ElementaryStepEdge,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        PlannedNode,
    )
    from cloudra.dag.store import DagStore

    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-advisory", "dag_record")
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="seed",
            base_revisions=store.load_bundle().revisions,
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
                        edge_id="claisen",
                        source_node_id="r",
                        target_node_id="p",
                        evidence_level="proposed",
                    ),
                ),
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="guess",
                        label="TS guess",
                        status="ready",
                        tool_name="ts_guess",
                        delivery_target_type="edge",
                        delivery_target_id="claisen",
                        evidence_role="endpoint_direction_check",
                    ),
                ),
            ],
        )
    )
    assert seeded.accepted
    controller = DagController(db, "s1", OrchestrationMode.DAG_RECORD)
    await controller.initialize()

    arguments = {"mode": "verify", "strict": True}
    await controller.on_tool_started("tc3", "ts_guess", arguments)
    await controller.on_tool_finished(
        "tc3",
        "ts_guess",
        arguments,
        {
            "is_success": True,
            "verdict": (
                "pass：部分 IRC 的双向路径与两个优化中间体一致；"
                "该结论只证明路径方向，不代表 TS 在所有化学意义上绝对正确。"
            ),
            "n_imag": 1,
        },
    )

    edge = controller.engine.snapshot().delivery.edges[0]
    assert edge.evidence_level == "proposed"
    assert edge.endpoint_direction_consistent is True
    assert edge.refs


def test_endpoint_support_requires_identity_matching_after_direction_check():
    DagController, _OrchestrationMode = _controller_api()
    path_evidence = {
        "evidence_level": "saddle_supported",
        "saddle_supported": True,
        "short_irc_supported": True,
        "endpoint_a_minimum_supported": True,
        "endpoint_direction_consistent": True,
    }

    endpoint_b = DagController._derive_delivery_changes(
        path_evidence,
        "endpoint_b_optimization",
        "gaussian_log_parser",
        {},
        {
            "normal_termination": True,
            "frequencies_cm": [500.0, 1600.0, 3700.0],
            "imaginary_frequencies": [],
        },
    )

    assert endpoint_b["endpoint_b_minimum_supported"] is True
    assert endpoint_b.get("evidence_level") != "endpoint_supported"

    identity_match = DagController._derive_delivery_changes(
        {**path_evidence, **endpoint_b},
        "endpoint_identity_match",
        "reaction_mapping",
        {},
        {
            "is_success": True,
            "binding_status": "complete",
            "reactant_identity": "match",
            "product_identity": "match",
        },
    )

    assert identity_match["endpoint_identity_matched"] is True
    assert identity_match["evidence_level"] == "endpoint_supported"


def test_endpoint_direction_accepts_real_ts_guess_pass_verdict_prefix():
    """ts_guess strict 的 verdict 是「pass：……」长串，不能用 == \"pass\"。"""
    DagController, _ = _controller_api()
    changes = DagController._derive_delivery_changes(
        {},
        "endpoint_direction_check",
        "ts_guess",
        {"strict": True},
        {
            "is_success": True,
            "verdict": (
                "pass：部分 IRC 的双向路径与两个优化中间体一致；"
                "该结论只证明路径方向，不代表 TS 在所有化学意义上绝对正确。"
            ),
            "n_imag": 1,
        },
    )
    assert changes.get("endpoint_direction_consistent") is True


def test_endpoint_direction_rejects_non_pass_verdict_prefix():
    DagController, _ = _controller_api()
    for verdict in (
        "fail：部分 IRC 的路径方向与两个优化中间体不一致。",
        "inconclusive：缺少两个端点优化中间体。",
        "candidate：一个虚频",
    ):
        changes = DagController._derive_delivery_changes(
            {},
            "endpoint_direction_check",
            "ts_guess",
            {"strict": True},
            {"is_success": True, "verdict": verdict},
        )
        assert "endpoint_direction_consistent" not in changes, verdict


def test_short_irc_requires_fifty_points_per_direction_or_both_converged():
    """short_irc：双向各 ≥50 点，或 irc_both_directions_converged。"""
    DagController, _ = _controller_api()

    weak = DagController._derive_delivery_changes(
        {},
        "short_irc",
        "gaussian_log_parser",
        {},
        {
            "is_success": True,
            "irc_num_points_forward": 1,
            "irc_num_points_backward": 1,
            "irc_both_directions_converged": False,
        },
    )
    assert "short_irc_supported" not in weak

    almost = DagController._derive_delivery_changes(
        {},
        "short_irc",
        "gaussian_log_parser",
        {},
        {
            "is_success": True,
            "irc_num_points_forward": 50,
            "irc_num_points_backward": 49,
            "irc_both_directions_converged": False,
        },
    )
    assert "short_irc_supported" not in almost

    enough_points = DagController._derive_delivery_changes(
        {},
        "short_irc",
        "gaussian_log_parser",
        {},
        {
            "is_success": True,
            "irc_num_points_forward": 50,
            "irc_num_points_backward": 50,
            "irc_both_directions_converged": False,
        },
    )
    assert enough_points.get("short_irc_supported") is True

    converged = DagController._derive_delivery_changes(
        {},
        "short_irc",
        "gaussian_log_parser",
        {},
        {
            "is_success": True,
            "irc_num_points_forward": 3,
            "irc_num_points_backward": 3,
            "irc_both_directions_converged": True,
        },
    )
    assert converged.get("short_irc_supported") is True


def test_missing_frequency_fields_do_not_imply_zero_imaginary():
    """未做频率计算时 imaginary_frequencies 缺省不得当成零虚频极小点。"""
    DagController, _ = _controller_api()
    no_freq = DagController._derive_delivery_changes(
        {},
        "intermediate_optimization",
        "gaussian_log_parser",
        {},
        {"is_success": True, "normal_termination": True},
    )
    assert no_freq.get("evidence_level") != "structure_supported"
    assert "evidence_level" not in no_freq

    empty_imag_without_lists = DagController._derive_delivery_changes(
        {},
        "endpoint_a_optimization",
        "gaussian_log_parser",
        {},
        {"is_success": True, "normal_termination": True},
    )
    assert "endpoint_a_minimum_supported" not in empty_imag_without_lists

    with_freq_minimum = DagController._derive_delivery_changes(
        {},
        "intermediate_optimization",
        "gaussian_log_parser",
        {},
        {
            "is_success": True,
            "normal_termination": True,
            "frequencies_cm": [500.0, 1600.0, 3700.0],
            "imaginary_frequencies": [],
        },
    )
    assert with_freq_minimum.get("evidence_level") == "structure_supported"

    saddle_without_freq = DagController._derive_delivery_changes(
        {},
        "ts_optimization_frequency",
        "gaussian_log_parser",
        {},
        {"is_success": True, "normal_termination": True},
    )
    assert "saddle_supported" not in saddle_without_freq

    saddle_with_one_imag = DagController._derive_delivery_changes(
        {},
        "ts_optimization_frequency",
        "gaussian_log_parser",
        {},
        {
            "is_success": True,
            "normal_termination": True,
            "frequencies_cm": [1200.0, 1300.0],
            "imaginary_frequencies": [915.3],
        },
    )
    assert saddle_with_one_imag.get("saddle_supported") is True
    assert saddle_with_one_imag.get("evidence_level") == "saddle_supported"


@pytest.mark.asyncio
async def test_dag_storage_failure_is_not_silently_downgraded(tmp_path, monkeypatch):
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-fail-closed", "dag_record")
    controller = DagController(db, "s1", OrchestrationMode.DAG_RECORD)
    monkeypatch.setattr(
        controller.store,
        "ensure_bundle",
        lambda _session_id: (_ for _ in ()).throw(RuntimeError("corrupt graph store")),
    )

    with pytest.raises(RuntimeError, match="corrupt graph store"):
        await controller.initialize()


@pytest.mark.asyncio
async def test_react_sends_full_result_to_controller_in_execution_order(
    tmp_path,
    monkeypatch,
):
    from typing import Any

    from cloudra.base.tools_class import Tool, input_schema, output_schema
    from cloudra.core.agent import Follower
    from cloudra.core.react import reAct
    from cloudra.infra.config import get_config
    from cloudra.tools import ToolEntry

    events = []

    class ProbeInput(input_schema):
        text: str

    class ProbeOutput(output_schema):
        is_success: bool = True
        full_body: str

    class ProbeTool(Tool):
        tool_id: str = "t-dag-probe"
        tool_name: str = "dag_probe"
        input_schema: Any = ProbeInput
        output_schema: Any = ProbeOutput

        async def tool_call(self, user_input, session):
            events.append("executed")
            return ProbeOutput(full_body=user_input.text * 2_000)

    class FakeController:
        async def initialize(self):
            return None

        def check_substantive_gate(self, tool_name, arguments=None, **_kwargs):
            return None

        async def on_tool_started(self, call_id, name, arguments):
            events.append("started")

        async def on_tool_finished(self, call_id, name, arguments, result):
            events.append("finished")
            assert call_id == "tc-full"
            assert arguments == {"text": "z"}
            assert len(result["full_body"]) == 2_000

    db_path = str(tmp_path / "react.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.core.react.get_database_path", lambda _cid: db_path)
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    entry = ToolEntry(
        cls=ProbeTool,
        tool_name="dag_probe",
        tool_id="t-dag-probe",
        input_schema=ProbeInput,
    )
    monkeypatch.setattr("cloudra.core.react.get_tools_lst", lambda: [entry])
    agent = Follower(
        id="a-probe",
        name="probe",
        prompt="probe",
        query="probe",
        conversation_id="controller-react",
        orchestration_mode="dag_record",
    )
    react = reAct(agent, session_id="s-probe")
    react.dag_controller = FakeController()

    await react.act_result(
        [
            {
                "id": "tc-full",
                "type": "function",
                "function": {
                    "name": "dag_probe",
                    "arguments": '{"text":"z"}',
                },
            }
        ]
    )

    assert events == ["started", "executed", "finished"]


@pytest.mark.asyncio
async def test_dag_graph_calls_not_observed_but_trigger_supervisor(tmp_path):
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-exempt", "dag_guided")
    calls = []

    class _MockSupervisor:
        async def run(self, trigger, coordinator_request=None, session_id=None, **_kwargs):
            calls.append({"trigger": trigger, "request": coordinator_request})
            return None

    controller = DagController(db, "s1", OrchestrationMode.DAG_GUIDED, supervisor=_MockSupervisor())
    await controller.initialize()

    view_args = {"action": "view"}
    await controller.on_tool_started("tc-view", "dag_graph", view_args)
    ref = await controller.on_tool_finished(
        "tc-view", "dag_graph", view_args, {"success": True, "action": "view", "result": {}}
    )
    assert ref is None
    assert controller.engine.snapshot().process.nodes == []
    assert calls == []  # view 不触发 Supervisor

    mutate_args = {
        "action": "mutate",
        "operations": [{"op": "add_node", "graph": "delivery"}],
        "rationale": "机理假设",
    }
    await controller.on_tool_finished("tc-mut", "dag_graph", mutate_args, {"success": True, "accepted": True})
    assert calls and calls[0]["trigger"] == "delivery_updated"


@pytest.mark.asyncio
async def test_getskill_not_observed_on_process_graph(tmp_path):
    """getskill 是元工具，写入 process 观察节点会污染空图并挡住 init_from_template。"""
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-getskill-exempt", "dag_guided")
    controller = DagController(db, "s1", OrchestrationMode.DAG_GUIDED)
    await controller.initialize()

    args = {"skill_name": "dft-calculation"}
    await controller.on_tool_started("tc-skill", "getskill", args)
    ref = await controller.on_tool_finished(
        "tc-skill",
        "getskill",
        args,
        {"content": "# skill body"},
    )
    assert ref is None
    assert controller.engine.snapshot().process.nodes == []


@pytest.mark.asyncio
async def test_bound_tool_outcomes_trigger_supervisor(tmp_path):
    """绑定到 delivery 目标的工具：成功 → new_evidence，失败 → process_node_failed；
    未绑定的普通工具不触发。"""
    DagController, OrchestrationMode = _controller_api()
    from cloudra.dag.models import (
        AddNode,
        GraphActor,
        MutationBatch,
        OccurrenceNode,
        PlannedNode,
    )
    from cloudra.dag.store import DagStore

    db = _db_with_session(tmp_path, "controller-bound-triggers", "dag_guided")
    calls = []

    class _MockSupervisor:
        async def run(self, trigger, coordinator_request=None, session_id=None, **_kwargs):
            calls.append(trigger)
            return None

    controller = DagController(
        db, "s1", OrchestrationMode.DAG_GUIDED, supervisor=_MockSupervisor()
    )
    await controller.initialize()
    store = DagStore(db)
    seeded = controller.engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="test",
            base_revisions=store.load_bundle().revisions,
            rationale="seed planned bound nodes",
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
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="plan-thermo",
                        label="thermo",
                        status="ready",
                        tool_name="thermo_analysis",
                        delivery_target_type="node",
                        delivery_target_id="poz",
                        evidence_role="thermochemistry",
                    ),
                ),
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="plan-parse",
                        label="parse",
                        status="ready",
                        tool_name="gaussian_log_parser",
                        delivery_target_type="node",
                        delivery_target_id="poz",
                        evidence_role="intermediate_optimization",
                    ),
                ),
            ],
        )
    )
    assert seeded.accepted

    # 绑定的 thermo_analysis 成功 → new_evidence（不再只认 gaussian_log_parser）
    await controller.on_tool_finished(
        "tc-thermo", "thermo_analysis", {"dir": "x"}, {"is_success": True}
    )
    assert calls == ["new_evidence"]

    # 绑定的调用失败 → process_node_failed
    await controller.on_tool_finished(
        "tc-parse", "gaussian_log_parser", {"file": "x.log"}, {"is_success": False}
    )
    assert calls == ["new_evidence", "process_node_failed"]

    # 未绑定的普通工具成功 → 不触发
    await controller.on_tool_finished(
        "tc-free", "thermo_analysis", {"dir": "y"}, {"is_success": True}
    )
    assert calls == ["new_evidence", "process_node_failed"]


@pytest.mark.asyncio
async def test_rejected_remove_edge_wakes_supervisor_for_review(tmp_path):
    """agent 的删边请求被转交时，Supervisor 收到 edge_removal_requested 与理由。"""
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-removal-review", "dag_guided")
    calls = []

    class _MockSupervisor:
        async def run(self, trigger, coordinator_request=None, session_id=None, **_kwargs):
            calls.append({"trigger": trigger, "request": coordinator_request})
            return None

    controller = DagController(
        db, "s1", OrchestrationMode.DAG_GUIDED, supervisor=_MockSupervisor()
    )
    await controller.initialize()

    await controller.on_tool_finished(
        "tc-rm",
        "dag_graph",
        {
            "action": "mutate",
            "operations": [
                {"op": "remove_edge", "graph": "process", "edge_id": "dep_ab"}
            ],
            "rationale": "dep_ab 已被人工合并",
        },
        {
            "success": False,
            "accepted": False,
            "rejection_code": "edge_removal_requires_supervisor",
        },
    )

    assert calls == [
        {
            "trigger": "edge_removal_requested",
            "request": (
                "edge removal requested — rationale: dep_ab 已被人工合并\n"
                "operations: remove_edge:process:dep_ab"
            ),
        }
    ]


# ---------------------------------------------------------------------------
# review_evidence 等级下调 / executor 终态补写
# ---------------------------------------------------------------------------


def _seed_delivery_element(db, node_id="n1", level="thermo_annotated"):
    """harness 身份在 delivery 播一个带等级的中间体节点，供复核下调。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import AddNode, GraphActor, MutationBatch, OccurrenceNode
    from cloudra.dag.store import DagStore

    store = DagStore(db)
    store.ensure_bundle("s1")
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="seed",
            base_revisions=store.load_bundle().revisions,
            rationale="seed delivery element",
            operations=[
                AddNode(
                    op="add_node",
                    graph="delivery",
                    node=OccurrenceNode(
                        node_id=node_id,
                        label="INT",
                        evidence_level=level,
                    ),
                )
            ],
        )
    )
    assert seeded.accepted
    return store


@pytest.mark.asyncio
async def test_review_evidence_downgraded_lowers_one_level(tmp_path):
    """downgraded 沿证据阶梯降一级；proposed 已到底则落 inconclusive。"""
    DagController, OrchestrationMode = _controller_api()
    db = _db_with_session(tmp_path, "controller-review-down", "dag_guided")
    store = _seed_delivery_element(db)
    controller = DagController(db, "s1", OrchestrationMode.DAG_GUIDED)

    reviewed = await controller.review_evidence(
        "n1", "downgraded", "频率数据不足以支撑热化学标注"
    )

    assert reviewed["changed"] is True
    assert reviewed["previous_evidence_level"] == "thermo_annotated"
    assert reviewed["evidence_level"] == "endpoint_supported"
    node = next(
        n for n in store.load_snapshot().delivery.nodes if n.node_id == "n1"
    )
    assert node.evidence_level == "endpoint_supported"
    assert "频率数据" in node.reason

    # confirmed 不改图
    confirmed = await controller.review_evidence("n1", "confirmed", "复核通过")
    assert confirmed["changed"] is False
    node = next(
        n for n in store.load_snapshot().delivery.nodes if n.node_id == "n1"
    )
    assert node.evidence_level == "endpoint_supported"

    # 再降三级到底后继续 downgraded → inconclusive
    for _ in range(3):
        await controller.review_evidence("n1", "downgraded", "继续下调")
    last = await controller.review_evidence("n1", "downgraded", "已到底")
    assert last["evidence_level"] == "inconclusive"


@pytest.mark.asyncio
async def test_executor_backfill_marks_failed_assignee_nodes(tmp_path):
    """子 agent failed → 指派给它的 ready/running planned 节点补写 failed，
    blocked_reason 取 error 截断 200 字符；他人节点与已终态节点不动。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddNode,
        GraphActor,
        MutationBatch,
        ObservedNode,
        PlannedNode,
    )
    from cloudra.dag.store import DagStore
    from cloudra.runtime.executor import _backfill_dag_assignee_nodes

    _controller_api()
    db = _db_with_session(tmp_path, "controller-backfill-fail", "dag_record")
    store = DagStore(db)
    store.ensure_bundle("s1")

    def _node(node_id, payload, observed=False):
        cls = ObservedNode if observed else PlannedNode
        return AddNode(
            op="add_node",
            graph="process",
            node=cls(node_id=node_id, label=node_id, **payload),
        )

    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="seed",
            base_revisions=store.load_bundle().revisions,
            rationale="seed assignee nodes",
            operations=[
                _node("n-run", {"status": "running", "assignee": "a-1"}),
                _node("n-ready", {"status": "ready", "assignee": "a-1"}),
                _node("n-other", {"status": "running", "assignee": "a-2"}),
                _node("n-done", {"status": "succeeded", "assignee": "a-1"}),
                _node(
                    "n-obs",
                    {"status": "running", "assignee": "a-1", "tool_call_id": "tc-1"},
                    observed=True,
                ),
            ],
        )
    )
    assert seeded.accepted

    await _backfill_dag_assignee_nodes(
        db, "sub-1", "a-1", "failed", error="x" * 500,
        orchestration_mode="dag_record",
    )

    nodes = {
        node.node_id: node for node in store.load_snapshot().process.nodes
    }
    assert nodes["n-run"].status == "failed"
    assert nodes["n-ready"].status == "failed"
    assert len(nodes["n-run"].blocked_reason) == 200
    assert nodes["n-other"].status == "running"  # 别的 assignee 不动
    assert nodes["n-done"].status == "succeeded"  # 已终态不动
    assert nodes["n-obs"].status == "running"  # observed 遥测不是排产工作


@pytest.mark.asyncio
async def test_executor_backfill_done_marks_succeeded(tmp_path):
    """子 agent done → 指派节点补写 succeeded，不写 blocked_reason。"""
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import AddNode, GraphActor, MutationBatch, PlannedNode
    from cloudra.dag.store import DagStore
    from cloudra.runtime.executor import _backfill_dag_assignee_nodes

    _controller_api()
    db = _db_with_session(tmp_path, "controller-backfill-done", "dag_guided")
    store = DagStore(db)
    store.ensure_bundle("s1")
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.HARNESS,
            actor_id="seed",
            base_revisions=store.load_bundle().revisions,
            rationale="seed assignee node",
            operations=[
                AddNode(
                    op="add_node",
                    graph="process",
                    node=PlannedNode(
                        node_id="n-run",
                        label="optfreq",
                        status="running",
                        assignee="a-3",
                    ),
                )
            ],
        )
    )
    assert seeded.accepted

    await _backfill_dag_assignee_nodes(
        db, "sub-3", "a-3", "done", orchestration_mode="dag_guided"
    )

    node = next(
        n for n in store.load_snapshot().process.nodes if n.node_id == "n-run"
    )
    assert node.status == "succeeded"
    assert node.blocked_reason == ""


@pytest.mark.asyncio
async def test_executor_backfill_skips_standard_mode(tmp_path):
    """standard 会话零图开销：不建图、不写任何节点。"""
    from cloudra.runtime.executor import _backfill_dag_assignee_nodes

    _controller_api()
    db = _db_with_session(tmp_path, "controller-backfill-standard", "standard")

    await _backfill_dag_assignee_nodes(
        db, "sub-1", "a-1", "failed", error="boom", orchestration_mode="standard"
    )

    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_graphs").fetchone()[0] == 0
