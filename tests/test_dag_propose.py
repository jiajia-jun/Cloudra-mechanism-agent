"""dag_propose_mechanism / dag_accept_mechanism（Phase 3：草稿 → 接受 → 解锁计算）。"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from cloudra.base.session_class import Session
from cloudra.core.agent import Coordinator
from cloudra.core.supervisor import SupervisorAgent
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_accept_mechanism import DagAcceptMechanism
from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanism

_OPS = [
    {
        "op": "add_node",
        "graph": "delivery",
        "node": {"node_id": "r", "node_type": "occurrence", "label": "R", "role": "reactant"},
    },
    {
        "op": "add_node",
        "graph": "delivery",
        "node": {"node_id": "p", "node_type": "occurrence", "label": "P", "role": "product"},
    },
    {
        "op": "add_edge",
        "graph": "delivery",
        "edge": {
            "edge_id": "step1",
            "edge_type": "elementary_step",
            "source_node_id": "r",
            "target_node_id": "p",
        },
    },
]
_CONTRACTS = {
    "r": ["geometry"],
    "p": ["geometry"],
    "step1": ["ts_guess", "ts_opt", "frequency"],
}


def _schema(cls):
    return cls.model_fields["input_schema"].default


async def _call(cls, agent, session, **kwargs):
    return await cls(subagent=agent).tool_call(_schema(cls)(**kwargs), session)


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


async def _propose(agent, session, operations=None, contracts=None):
    return await _call(
        DagProposeMechanism,
        agent,
        session,
        operations=operations or _OPS,
        stage_contracts=_CONTRACTS if contracts is None else contracts,
        rationale="Claisen [3,3] chair pathway hypothesis",
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

    supervisor = SupervisorAgent(
        conversation_id=db.conversation_id, orchestration_mode="dag_guided"
    )
    accepted = await _call(DagAcceptMechanism, supervisor, session, verdict="accept")
    assert accepted.is_success
    assert accepted.result["state"] == "accepted"

    edge = _graph(db).delivery.edges[0]
    assert [(s.kind.value, s.status.value) for s in edge.stages] == [
        ("ts_guess", "pending"),
        ("ts_opt", "pending"),
        ("frequency", "pending"),
    ]
    node = next(n for n in _graph(db).delivery.nodes if n.node_id == "r")
    assert [(s.kind.value, s.status.value) for s in node.stages] == [
        ("geometry", "pending")
    ]
    assert await controller.check_substantive_gate("submit_compute_job", {}) is None


@pytest.mark.asyncio
async def test_supervisor_reject_returns_reason_and_keeps_gate(tmp_path):
    agent, session, db = _setup(tmp_path, "propose-reject", "dag_guided")
    await _propose(agent, session)
    supervisor = SupervisorAgent(
        conversation_id=db.conversation_id, orchestration_mode="dag_guided"
    )

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
async def test_contract_must_resolve_within_the_draft(tmp_path):
    agent, session, _db = _setup(tmp_path, "propose-dangling", "dag_record")

    out = await _propose(agent, session, contracts={"ghost": ["geometry"]})

    assert not out.is_success
    assert "does not resolve" in out.error


@pytest.mark.asyncio
async def test_stage_kind_must_match_element_kind(tmp_path):
    agent, session, _db = _setup(tmp_path, "propose-kind", "dag_record")

    edge_bad = await _propose(agent, session, contracts={**_CONTRACTS, "step1": ["geometry"]})
    assert not edge_bad.is_success
    assert "does not apply" in edge_bad.error

    node_bad = await _propose(agent, session, contracts={"r": ["ts_opt"], "p": ["geometry"]})
    assert not node_bad.is_success
    assert "does not apply" in node_bad.error


@pytest.mark.asyncio
async def test_draft_stages_must_be_pending(tmp_path):
    agent, session, _db = _setup(tmp_path, "propose-pending", "dag_record")
    ops = [
        {
            "op": "add_node",
            "graph": "delivery",
            "node": {
                "node_id": "r",
                "node_type": "occurrence",
                "label": "R",
                "role": "reactant",
                "stages": [{"kind": "geometry", "status": "supported"}],
            },
        }
    ]

    # Public proposals reject evidence states before entering the controller.
    with pytest.raises(ValidationError, match="stages"):
        await _propose(agent, session, operations=ops, contracts={})
    from cloudra.dag.controller import DagController

    # The engine guard still protects callers outside the public tool schema.
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
            operations=_OPS,
            stage_contracts=_CONTRACTS,
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
async def test_propose_in_guided_wakes_supervisor(tmp_path):
    """mechanism_proposed 唤醒（D14 合并由 maybe_supervise 保证）。"""
    from cloudra.dag.controller import DagController

    class FakeSupervisor:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def run(self, trigger, coordinator_request=None, **_kwargs):
            self.calls.append(
                {"trigger": trigger, "coordinator_request": coordinator_request}
            )
            return None

    get_config().data_dir = tmp_path
    db = ConversationDB("propose-wake").init()
    supervisor = FakeSupervisor()
    controller = DagController(db, "s1", "dag_guided", supervisor=supervisor)

    await controller.on_tool_finished(
        "tc-propose",
        "dag_propose_mechanism",
        {"rationale": "Claisen chair hypothesis"},
        {"is_success": True, "accepted": True},
    )

    assert [call["trigger"] for call in supervisor.calls] == ["mechanism_proposed"]
    assert "Claisen" in supervisor.calls[0]["coordinator_request"]
