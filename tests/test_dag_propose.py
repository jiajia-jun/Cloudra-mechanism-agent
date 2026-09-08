"""dag_propose_mechanism / dag_accept_mechanism（Phase 3：草稿 → 接受 → 解锁计算）。"""

from types import SimpleNamespace

import pytest

from cloudra.base.session_class import Session
from cloudra.core.agent import Coordinator
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_accept_mechanism import DagAcceptMechanism
from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanism
from tests.dag_identity import call_dag_tool, make_supervisor

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
    return Coordinator(
        query="study a mechanism",
        conversation_id=conversation_id,
        orchestration_mode=mode,
    )


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
    ]


@pytest.mark.asyncio
async def test_guided_propose_then_supervisor_accept_unlocks_compute(tmp_path):
    """guided：提案落 open 草稿（计算仍被拦）；Supervisor 接受后落图并放行。"""
    agent, session, db = _setup(tmp_path, "propose-guided", "dag_guided")

    out = await _propose(agent, session)
    assert out.is_success
    assert out.result["state"] == "open"
    assert out.accepted is False
    assert out.result["accepted"] is False
    assert _graph(db).delivery.nodes == []

    from cloudra.dag.controller import DagController

    controller = DagController(db, "s1", "dag_guided", conversation_id=db.conversation_id)
    gate = await controller.check_substantive_gate("submit_compute_job", {})
    assert gate is not None and gate[0] == "block"

    supervisor = make_supervisor(db.conversation_id)
    accepted = await _call(DagAcceptMechanism, supervisor, session, verdict="accept")
    assert accepted.is_success
    assert accepted.result["state"] == "accepted"

    edge = _graph(db).delivery.edges[0]
    assert [(s.kind.value, s.status.value) for s in edge.stages] == [
        ("ts_guess", "pending"),
        ("ts_opt", "pending"),
        ("frequency", "pending"),
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
    assert _graph(db).delivery.nodes == []

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

