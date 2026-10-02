"""dag_propose_mechanism / dag_accept_mechanism（Phase 3：草稿 → 接受 → 解锁计算）。"""

from types import SimpleNamespace

import pytest

from cloudra.base.session_class import Session
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_accept_mechanism import DagAcceptMechanism
from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanism
from tests.dag_identity import call_dag_tool, make_coordinator, make_supervisor

_SPECIES = [
    {"name": "R", "smiles": "C=C"},
    {"name": "P", "smiles": "CC"},
]
_STEPS = [
    {"name": "step1", "from": "R", "to": "P"},
]


def _schema(cls):
    return cls.model_fields["input_schema"].default


async def _call(cls, agent, session, **kwargs):
    return await call_dag_tool(cls, agent, session, **kwargs)


def _agent(conversation_id, mode):
    return make_coordinator(conversation_id, orchestration_mode=mode)


def _setup(tmp_path, conversation_id, mode):
    get_config().data_dir = tmp_path
    agent = _agent(conversation_id, mode)
    session = Session("s1", str(tmp_path / "session.json"))
    db = ConversationDB(conversation_id).init()
    return agent, session, db


def _graph(db):
    from cloudra.dag.store import DagStore

    return DagStore(db).load_snapshot()


async def _propose(agent, session, species=None, steps=None, rationale="Claisen [3,3] chair pathway hypothesis"):
    return await _call(
        DagProposeMechanism,
        agent,
        session,
        species=_SPECIES if species is None else species,
        steps=_STEPS if steps is None else steps,
        rationale=rationale,
    )


@pytest.mark.asyncio
async def test_record_proposal_auto_accepts(tmp_path):
    """D1：record 无 Supervisor——提案即 harness 自动接受（harness:auto）。"""
    agent, session, db = _setup(tmp_path, "propose-record", "dag_record")

    out = await _propose(agent, session)

    assert out.is_success
    assert out.result["state"] == "accepted"
    from cloudra.dag.store import DagStore

    store = DagStore(db)
    assert store.has_accepted_draft()
    with db.connect() as con:
        row = con.execute(
            "SELECT state, actor_id FROM dag_drafts"
        ).fetchone()
    assert row == ("accepted", "harness:auto")
    edge = _graph(db).delivery.edges[0]
    assert [(s.kind.value, s.status.value) for s in edge.stages] == [
        ("ts_guess", "pending"),
        ("ts_opt", "pending"),
        ("frequency", "pending"),
        ("short_irc", "pending"),
    ]


@pytest.mark.asyncio
async def test_proposal_and_graph_are_one_durable_change(tmp_path):
    """Draft write failure must roll back the graph and its accepted journal."""
    agent, session, db = _setup(tmp_path, "propose-atomic", "dag_guided")
    from cloudra.dag.controller import DagController

    await DagController(db, "s1", "dag_guided").initialize()
    with db.connect() as con:
        con.execute("""
            CREATE TRIGGER fail_draft_insert BEFORE INSERT ON dag_drafts
            BEGIN SELECT RAISE(FAIL, 'draft insert failed'); END
        """)

    result = await _propose(agent, session)

    assert result.is_success is False
    assert _graph(db).delivery.nodes == []
    assert _graph(db).delivery.edges == []
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM dag_drafts").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM dag_mutations WHERE accepted = 1").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_public_proposal_selects_delivery_step_without_exploration_debt(tmp_path):
    agent, session, db = _setup(tmp_path, "propose-scope", "dag_guided")
    proposed = await _call(
        DagProposeMechanism, agent, session,
        rationale="R to P is the result under study",
        species=_SPECIES, steps=_STEPS, delivery_targets=["step1"],
    )
    assert proposed.is_success
    from cloudra.dag.controller import DagController
    from cloudra.dag.store import DagStore

    store = DagStore(db)
    first_graph = store.load_snapshot().delivery
    step_id = first_graph.edges[0].edge_id
    supervisor = make_supervisor(db.conversation_id)
    accepted = await _call(
        DagAcceptMechanism, supervisor, session,
        verdict="accept", draft_id=proposed.result["draft_id"],
    )
    assert accepted.is_success
    assert store.accepted_claim_spec().scope["targets"] == [step_id]

    exploration = await _call(
        DagProposeMechanism, agent, session,
        rationale="Explore a possible competing branch",
        species=[{"name": "X"}, {"name": "Y"}],
        steps=[{"name": "side_step", "from": "X", "to": "Y"}],
    )
    assert exploration.is_success and exploration.result["state"] == "open"
    side_ids = {
        *(node.node_id for node in store.load_snapshot().delivery.nodes if node.name in {"X", "Y"}),
        *(edge.edge_id for edge in store.load_snapshot().delivery.edges if edge.name == "side_step"),
    }
    assert len(side_ids) == 3
    report = DagController(db, "s1", "dag_guided").delivery_report()
    assert not ({gate.target_id for gate in report.unresolved} & side_ids)


@pytest.mark.asyncio
async def test_public_scope_can_change_after_graph_grows_without_new_species(tmp_path):
    agent, session, db = _setup(tmp_path, "propose-scope-update", "dag_record")
    first = await _propose(agent, session)
    assert first.is_success
    updated = await _call(
        DagProposeMechanism, agent, session,
        rationale="Deliver only the established transformation",
        delivery_targets=["step1"],
    )
    assert updated.is_success
    from cloudra.dag.store import DagStore

    store = DagStore(db)
    assert len(store.load_snapshot().delivery.edges) == 1
    assert store.accepted_claim_spec().scope["targets"] == [
        store.load_snapshot().delivery.edges[0].edge_id
    ]


@pytest.mark.asyncio
async def test_public_proposal_extends_existing_pathway_by_species_name(tmp_path):
    agent, session, db = _setup(tmp_path, "propose-growing-pathway", "dag_record")
    first = await _call(
        DagProposeMechanism, agent, session,
        rationale="initial A to B pathway",
        species=[{"name": "A"}, {"name": "B"}],
        steps=[{"name": "A_to_B", "from": "A", "to": "B"}],
    )
    assert first.is_success
    second = await _call(
        DagProposeMechanism, agent, session,
        rationale="extend the pathway to C",
        species=[{"name": "C"}],
        steps=[{"name": "B_to_C", "from": "B", "to": "C"}],
        delivery_targets=["A_to_B", "B_to_C"],
    )
    assert second.is_success

    from cloudra.dag.store import DagStore

    store = DagStore(db)
    delivery = store.load_snapshot().delivery
    ids = {node.name: node.node_id for node in delivery.nodes}
    edges = {edge.name: edge for edge in delivery.edges}
    assert set(ids) == {"A", "B", "C"}
    assert edges["B_to_C"].source_node_id == ids["B"]
    assert edges["B_to_C"].target_node_id == ids["C"]
    assert set(store.accepted_claim_spec().scope["targets"]) == {
        edges["A_to_B"].edge_id, edges["B_to_C"].edge_id,
    }


@pytest.mark.asyncio
async def test_public_delivery_target_rejects_unknown_or_ambiguous_name(tmp_path):
    agent, session, db = _setup(tmp_path, "propose-target-ambiguity", "dag_record")
    assert (await _propose(agent, session)).is_success
    unknown = await _call(
        DagProposeMechanism, agent, session,
        rationale="scope an existing object", delivery_targets=["missing"],
    )
    assert not unknown.is_success and "unknown delivery target" in unknown.error
    ambiguous = await _call(
        DagProposeMechanism, agent, session,
        rationale="same name can denote a species and a step",
        species=[{"name": "shared"}, {"name": "Q"}],
        steps=[{"name": "shared", "from": "shared", "to": "Q"}],
        delivery_targets=["shared"],
    )
    assert not ambiguous.is_success and "ambiguous delivery target" in ambiguous.error
    assert len(_graph(db).delivery.nodes) == 2


@pytest.mark.asyncio
async def test_exploratory_draft_cannot_restore_an_older_accepted_scope(tmp_path):
    agent, session, db = _setup(tmp_path, "propose-no-scope-rollback", "dag_guided")
    supervisor = make_supervisor(db.conversation_id)
    first = await _call(
        DagProposeMechanism, agent, session,
        rationale="initial conclusion", species=[{"name": "A"}, {"name": "B"}],
        steps=[{"name": "AB", "from": "A", "to": "B"}],
        delivery_targets=["AB"],
    )
    assert first.is_success
    assert (await _call(DagAcceptMechanism, supervisor, session,
                        verdict="accept", draft_id=first.result["draft_id"])).is_success
    expanded = await _call(
        DagProposeMechanism, agent, session,
        rationale="include the next step", species=[{"name": "C"}],
        steps=[{"name": "BC", "from": "B", "to": "C"}],
        delivery_targets=["AB", "BC"],
    )
    exploratory = await _call(
        DagProposeMechanism, agent, session,
        rationale="optional side pathway", species=[{"name": "X"}, {"name": "Y"}],
        steps=[{"name": "XY", "from": "X", "to": "Y"}],
    )
    assert expanded.is_success and exploratory.is_success
    from cloudra.dag.store import DagStore

    store = DagStore(db)
    assert store.get_draft(exploratory.result["draft_id"]).claim_spec is None
    assert (await _call(DagAcceptMechanism, supervisor, session,
                        verdict="accept", draft_id=expanded.result["draft_id"])).is_success
    assert (await _call(DagAcceptMechanism, supervisor, session,
                        verdict="accept", draft_id=exploratory.result["draft_id"])).is_success
    selected = set(store.accepted_claim_spec().scope["targets"])
    edges = {edge.name: edge.edge_id for edge in store.load_snapshot().delivery.edges}
    assert selected == {edges["AB"], edges["BC"]}


@pytest.mark.asyncio
async def test_public_scope_replaces_reference_targets_without_losing_reference_details(tmp_path):
    agent, session, db = _setup(tmp_path, "propose-reference-targets", "dag_record")
    assert (await _propose(agent, session)).is_success
    from cloudra.dag.models import ClaimSpec, MechanismDraft
    from cloudra.dag.store import DagStore

    store = DagStore(db)
    first_edge = store.load_snapshot().delivery.edges[0].edge_id
    store.save_draft(
        MechanismDraft(
            operations=[], rationale="old reference scope", state="accepted",
            claim_spec=ClaimSpec(kind="mechanism", reference={
                "targets": [first_edge], "method": "initial calculation",
            }),
        ), actor_id="test-harness",
    )
    new = await _call(
        DagProposeMechanism, agent, session,
        rationale="select product species instead", delivery_targets=["P"],
    )
    assert new.is_success and new.result["state"] == "accepted"
    spec = store.accepted_claim_spec()
    assert spec.scope["targets"] == [
        next(node.node_id for node in store.load_snapshot().delivery.nodes if node.name == "P")
    ]
    assert spec.reference == {"method": "initial calculation"}


@pytest.mark.asyncio
async def test_guided_propose_then_supervisor_accept_unlocks_compute(tmp_path):
    """guided：提案落 open 草稿（计算仍被拦）；Supervisor 接受后落图并放行。"""
    agent, session, db = _setup(tmp_path, "propose-guided", "dag_guided")

    out = await _propose(agent, session)
    assert out.is_success
    assert out.result["state"] == "open"
    assert out.accepted is False
    assert out.result["accepted"] is False
    assert _graph(db).delivery.nodes

    from cloudra.dag.controller import DagController

    controller = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id)
    gate = await controller.check_substantive_gate("submit_compute_job", {})
    assert gate is None

    supervisor = make_supervisor(db.conversation_id)
    accepted = await _call(DagAcceptMechanism, supervisor, session, verdict="accept")
    assert accepted.is_success
    assert accepted.result["state"] == "accepted"

    edge = _graph(db).delivery.edges[0]
    assert [(s.kind.value, s.status.value) for s in edge.stages] == [
        ("ts_guess", "pending"),
        ("ts_opt", "pending"),
        ("frequency", "pending"),
        ("short_irc", "pending"),
    ]
    node = next(n for n in _graph(db).delivery.nodes if getattr(n, "name", "") == "R" or n.node_id == "r")
    assert [(s.kind.value, s.status.value) for s in node.stages] == [
        ("geometry", "pending")
    ]
    assert await controller.check_substantive_gate("submit_compute_job", {}) is None


@pytest.mark.asyncio
async def test_supervisor_reject_returns_reason_and_keeps_gate(tmp_path):
    agent, session, db = _setup(tmp_path, "propose-reject", "dag_guided")
    await _propose(agent, session)
    supervisor = make_supervisor(db.conversation_id)

    no_reason = await _call(DagAcceptMechanism, supervisor, session, verdict="reject")
    assert not no_reason.is_success
    assert "rationale" in no_reason.error

    rejected = await _call(
        DagAcceptMechanism, supervisor, session,
        verdict="reject", rationale="missing the competing boat pathway",
    )
    assert rejected.is_success
    assert rejected.result["state"] == "rejected"
    assert "boat" in rejected.result["reason"]
    assert _graph(db).delivery.nodes

    from cloudra.dag.store import DagStore

    assert not DagStore(db).has_accepted_draft()


@pytest.mark.asyncio
async def test_draft_stages_must_be_pending():
    from cloudra.dag.controller import DagController

    ops = [
        {
            "op": "add_node",
            "graph": "delivery",
            "node": {
                "node_id": "r",
                "node_type": "species",
                "name": "R",
                "stages": [{"kind": "geometry", "status": "supported"}],
            },
        }
    ]
    with pytest.raises(RuntimeError, match="pending"):
        DagController._validate_draft(ops, {}, "hypothesis")


@pytest.mark.asyncio
async def test_propose_and_accept_actor_gates(tmp_path):
    agent, session, db = _setup(tmp_path, "propose-gates", "dag_guided")
    follower = SimpleNamespace(
        id="as_deadbeefcafebabe",
        name="small_mol",
        type="follower",
        conversation_id="propose-gates",
        orchestration_mode="dag_guided",
    )
    # subagent 字段有 pydantic 校验：绕过构造器直接赋 namespace（同
    # test_runtime_v2_dag_stage 的 bridge 写法）
    tool = DagProposeMechanism()
    object.__setattr__(tool, "subagent", follower)
    denied = await tool.tool_call(
        _schema(DagProposeMechanism)(
            species=_SPECIES,
            steps=_STEPS,
            rationale="follower should not propose",
        ),
        session,
    )
    assert not denied.is_success
    assert "Coordinator" in denied.error

    await _propose(agent, session)
    not_supervisor = await _call(DagAcceptMechanism, agent, session, verdict="accept")
    assert not not_supervisor.is_success
    assert "supervisor-only" in not_supervisor.error

    record_agent = _agent("propose-gates", "dag_record")
    record = await _call(DagAcceptMechanism, record_agent, session, verdict="accept")
    assert not record.is_success
    assert "dag_record" in record.error


@pytest.mark.asyncio
async def test_propose_in_guided_notifies_supervisor(tmp_path):
    """mechanism_proposed 通知（Task 3 事件驱动语义）：草稿落库后 spawn
    项目唯一 Supervisor agent 并投递信箱变更消息，不等待裁决。

    guided 模式提案的真实返回形状：草稿落 open 待 supervisor 裁决，
    accepted=False。通知判定必须认 draft_id，而不是只看 accepted。
    """
    from cloudra.dag.controller import DagController
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import Command
    from cloudra.runtime_v2.supervision import find_project_supervisor

    get_config().data_dir = tmp_path
    core = RuntimeCore(strict_events=True)
    project = (
        await CommandBus(core).execute(
            Command(type="project.create", payload={"name": "propose-notify"})
        )
    ).data
    db = ConversationDB(project.id).init()
    controller = DagController(
        db, "s1", "dag_guided", conversation_id=project.id, core=core
    )

    await controller.on_tool_finished(
        "tc-propose",
        "dag_propose_mechanism",
        {"rationale": "Claisen chair hypothesis"},
        {
            "is_success": True,
            "accepted": False,
            "result": {"draft_id": "draft_1", "state": "open", "accepted": False},
        },
    )

    assert find_project_supervisor(core, project.id) is not None


@pytest.mark.asyncio
async def test_failed_proposal_does_not_notify_supervisor(tmp_path):
    """校验失败/被拒的提案不落草稿，不通知 supervisor。"""
    from cloudra.dag.controller import DagController
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import Command
    from cloudra.runtime_v2.supervision import find_project_supervisor

    get_config().data_dir = tmp_path
    core = RuntimeCore(strict_events=True)
    project = (
        await CommandBus(core).execute(
            Command(type="project.create", payload={"name": "propose-no-notify"})
        )
    ).data
    db = ConversationDB(project.id).init()
    controller = DagController(
        db, "s1", "dag_guided", conversation_id=project.id, core=core
    )

    await controller.on_tool_finished(
        "tc-propose-bad",
        "dag_propose_mechanism",
        {"rationale": "invalid"},
        {
            "is_success": False,
            "accepted": False,
            "error": "a mechanism proposal requires a non-empty rationale",
        },
    )

    assert find_project_supervisor(core, project.id) is None


@pytest.mark.asyncio
async def test_declarative_proposal_no_ids_or_roles_succeeds(tmp_path):
    """Task 1: 无 ID/role/type 提案成功；内部装配为 SpeciesNode 与 ElementaryStepEdge。"""
    agent, session, db = _setup(tmp_path, "propose-decl", "dag_record")

    out = await _call(
        DagProposeMechanism,
        agent,
        session,
        rationale="Claisen rearrangement pathway",
        species=[
            {"name": "初始络合物体系", "smiles": "C=CCOCC=C"},
            {"name": "产物络合物体系", "smiles": "O=CCCCCC"},
        ],
        steps=[
            {"name": "关键转化", "from": "初始络合物体系", "to": "产物络合物体系"},
        ],
    )

    assert out.is_success
    assert out.result["state"] == "accepted"
    snapshot = _graph(db)
    nodes = snapshot.delivery.nodes
    edges = snapshot.delivery.edges
    assert len(nodes) == 2
    assert len(edges) == 1
    # 节点无 role 字段，内部为 SpeciesNode
    node_names = {getattr(n, "name", getattr(n, "label", None)) for n in nodes}
    assert node_names == {"初始络合物体系", "产物络合物体系"}
    for n in nodes:
        assert getattr(n, "node_type", None) == "species"
        assert not hasattr(n, "role") or getattr(n, "role") is None
    # 边名称与端点正确绑定
    edge = edges[0]
    assert getattr(edge, "name", getattr(edge, "label", None)) == "关键转化"
    source_node = next(n for n in nodes if n.node_id == edge.source_node_id)
    target_node = next(n for n in nodes if n.node_id == edge.target_node_id)
    assert getattr(source_node, "name", getattr(source_node, "label", None)) == "初始络合物体系"
    assert getattr(target_node, "name", getattr(target_node, "label", None)) == "产物络合物体系"


@pytest.mark.asyncio
async def test_proposal_same_smiles_different_names_not_merged(tmp_path):
    """Task 1: 相同 SMILES 不自动合并对象，按名称创建不同体系节点。"""
    agent, session, db = _setup(tmp_path, "propose-same-smiles", "dag_record")

    out = await _call(
        DagProposeMechanism,
        agent,
        session,
        rationale="Isomerization pathway",
        species=[
            {"name": "体系状态A", "smiles": "CCO"},
            {"name": "体系状态B", "smiles": "CCO"},
        ],
        steps=[
            {"name": "异构转化", "from": "体系状态A", "to": "体系状态B"},
        ],
    )

    assert out.is_success
    snapshot = _graph(db)
    nodes = snapshot.delivery.nodes
    assert len(nodes) == 2
    assert len({n.node_id for n in nodes}) == 2


@pytest.mark.asyncio
async def test_proposal_duplicate_species_name_rejected(tmp_path):
    """Task 1: 同批同名写入拒绝（精确字符串比较，去空白）。"""
    agent, session, db = _setup(tmp_path, "propose-dup-species", "dag_record")

    out = await _call(
        DagProposeMechanism,
        agent,
        session,
        rationale="Duplicate test",
        species=[
            {"name": "体系状态A", "smiles": "CCO"},
            {"name": " 体系状态A ", "smiles": "CCN"},
        ],
        steps=[],
    )

    assert not out.is_success
    assert "duplicate" in (out.error or "").lower() or "unique" in (out.error or "").lower()


@pytest.mark.asyncio
async def test_proposal_duplicate_step_name_rejected(tmp_path):
    """Task 1: 同批同名步骤拒绝。"""
    agent, session, db = _setup(tmp_path, "propose-dup-step", "dag_record")

    out = await _call(
        DagProposeMechanism,
        agent,
        session,
        rationale="Duplicate step test",
        species=[
            {"name": "体系A"},
            {"name": "体系B"},
            {"name": "体系C"},
        ],
        steps=[
            {"name": "转化1", "from": "体系A", "to": "体系B"},
            {"name": "转化1", "from": "体系B", "to": "体系C"},
        ],
    )

    assert not out.is_success
    assert "duplicate" in (out.error or "").lower() or "unique" in (out.error or "").lower()


@pytest.mark.asyncio
async def test_proposal_unknown_endpoint_rejected(tmp_path):
    """Task 1: 未知端点引用拒绝。"""
    agent, session, db = _setup(tmp_path, "propose-unknown-end", "dag_record")

    out = await _call(
        DagProposeMechanism,
        agent,
        session,
        rationale="Unknown endpoint test",
        species=[
            {"name": "体系A"},
        ],
        steps=[
            {"name": "转化1", "from": "体系A", "to": "不存在的体系"},
        ],
    )

    assert not out.is_success
    assert "unknown" in (out.error or "").lower() or "not found" in (out.error or "").lower() or "endpoint" in (out.error or "").lower()


@pytest.mark.asyncio
async def test_proposal_self_loop_rejected(tmp_path):
    """Task 1: 自环（from == to）拒绝。"""
    agent, session, db = _setup(tmp_path, "propose-self-loop", "dag_record")

    out = await _call(
        DagProposeMechanism,
        agent,
        session,
        rationale="Self loop test",
        species=[
            {"name": "体系A"},
        ],
        steps=[
            {"name": "自环步骤", "from": "体系A", "to": "体系A"},
        ],
    )

    assert not out.is_success


@pytest.mark.asyncio
async def test_proposal_cycle_rejected(tmp_path):
    """Task 1: 有环转化拒绝，保持 DAG 无环约束。"""
    agent, session, db = _setup(tmp_path, "propose-cycle", "dag_record")

    out = await _call(
        DagProposeMechanism,
        agent,
        session,
        rationale="Cycle test",
        species=[
            {"name": "体系A"},
            {"name": "体系B"},
            {"name": "体系C"},
        ],
        steps=[
            {"name": "步骤1", "from": "体系A", "to": "体系B"},
            {"name": "步骤2", "from": "体系B", "to": "体系C"},
            {"name": "步骤3", "from": "体系C", "to": "体系A"},
        ],
    )

    assert not out.is_success
    assert "cycle" in (out.error or "").lower()


@pytest.mark.asyncio
async def test_proposal_batch_failure_zero_partial_write(tmp_path):
    """Task 1: 批次失败零部分写入（原子事务保证）。"""
    agent, session, db = _setup(tmp_path, "propose-atomicity", "dag_record")

    out = await _call(
        DagProposeMechanism,
        agent,
        session,
        rationale="Atomic rollback test",
        species=[
            {"name": "有效体系A"},
            {"name": "有效体系B"},
        ],
        steps=[
            # 这一步是自环，导致整个批次失败
            {"name": "坏步骤", "from": "有效体系A", "to": "有效体系A"},
        ],
    )

    assert not out.is_success
    snapshot = _graph(db)
    assert len(snapshot.delivery.nodes) == 0
    assert len(snapshot.delivery.edges) == 0



@pytest.mark.asyncio
async def test_ts_guess_contract_normalized_to_advisory_on_accept(tmp_path):
    """ts_guess 按定义是 advisory 阶段：契约生效收口处一律规范化为
    required=False（required 的 ts_guess 会把合格的 ts_opt 绑定卡在
    stage_out_of_order），接受返回里带逐条规范化痕迹（fail-loud，不静默改写）。"""
    agent, session, db = _setup(tmp_path, "propose-advisory", "dag_record")

    out = await _propose(agent, session)

    assert out.is_success
    notes = out.result["normalized_advisory_stages"]
    assert any("ts_guess" in note for note in notes)
    edge = _graph(db).delivery.edges[0]
    assert {s.kind.value: s.required for s in edge.stages} == {
        "ts_guess": False,
        "ts_opt": True,
        "frequency": True,
        "short_irc": True,
    }
