"""dag_evidence_bindings 关联表：双写、读路径切换与 v11 内联 refs 迁移。"""

from datetime import datetime, timezone

import pytest

from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    AddEdge,
    AddNode,
    AttachRef,
    CallReview,
    ElementaryStepEdge,
    GraphActor,
    GraphRef,
    MutationBatch,
    OccurrenceNode,
    RemoveEdge,
)
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB


def _new_engine(tmp_path, conversation_id="dag-bindings"):
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    return db, store, DagEngine(store)


def _batch(store, operations, rationale="focused test"):
    return MutationBatch(
        session_id="s1",
        actor=GraphActor.HARNESS,
        actor_id="test-harness",
        base_revisions=store.load_bundle().revisions,
        operations=operations,
        rationale=rationale,
    )


def _bindings(db):
    with db.connect() as con:
        return con.execute(
            """
            SELECT graph_id, target_type, target_id, evidence_id,
                   evidence_role, derived_level, created_revision
            FROM dag_evidence_bindings ORDER BY rowid
            """
        ).fetchall()


def _delivery_graph_id(db):
    with db.connect() as con:
        return con.execute(
            "SELECT graph_id FROM dag_graphs WHERE graph_kind = 'delivery'"
        ).fetchone()[0]


def _seed_delivery_graph(store, engine, evidence, extra_evidence=None):
    """建两个 occurrence + 一条 elementary_step，refs 直接随 add 内联写入。"""
    node_a = OccurrenceNode(
        node_id="int1",
        label="INT1",
        role="intermediate",
        evidence_level="structure_supported",
        refs=[evidence],
    )
    node_b = OccurrenceNode(node_id="int2", label="INT2", role="intermediate")
    edge_refs = [extra_evidence] if extra_evidence is not None else []
    edge = ElementaryStepEdge(
        edge_id="step1",
        source_node_id="int1",
        target_node_id="int2",
        evidence_level="endpoint_supported",
        refs=edge_refs,
    )
    result = engine.apply_batch(
        _batch(
            store,
            [
                AddNode(op="add_node", graph="delivery", node=node_a),
                AddNode(op="add_node", graph="delivery", node=node_b),
                AddEdge(op="add_edge", graph="delivery", edge=edge),
            ],
        )
    )
    assert result.accepted
    return result


def test_attach_ref_double_writes_binding_and_read_prefers_it(tmp_path):
    db, store, engine = _new_engine(tmp_path)
    evidence = store.register_evidence("s1", "ts_guess", {"verdict": "pass: ok"})
    _seed_delivery_graph(store, engine, evidence)
    graph_id = _delivery_graph_id(db)

    attached = engine.apply_batch(
        _batch(
            store,
            [
                AttachRef(
                    op="attach_ref",
                    graph="delivery",
                    target_type="edge",
                    target_id="step1",
                    ref=evidence,
                    evidence_role="irc_parse",
                )
            ],
        )
    )
    assert attached.accepted

    rows = _bindings(db)
    # add_edge 对账写入一行，attach_ref 写入一行（带 role 与挂载后的等级）。
    assert (
        graph_id,
        "edge",
        "step1",
        evidence.ref_id,
        "irc_parse",
        "endpoint_supported",
        attached.revisions["delivery"],
    ) in rows

    # 读路径以关联表为准：擦掉内联 refs 列后 snapshot 仍能重建引用。
    with db.connect() as con:
        con.execute("UPDATE dag_edges SET refs = '[]' WHERE edge_id = 'step1'")
    edge = next(e for e in engine.snapshot().delivery.edges if e.edge_id == "step1")
    assert edge.refs == [evidence]


def test_add_inline_refs_are_reconciled_into_bindings(tmp_path):
    db, store, engine = _new_engine(tmp_path)
    evidence = store.register_evidence("s1", "reaction_mapping", {"mapping_status": "unique"})
    created = _seed_delivery_graph(store, engine, evidence, extra_evidence=evidence)
    graph_id = _delivery_graph_id(db)

    rows = _bindings(db)
    # add_node/add_edge 携带的内联 refs 由 _write_graph 对账进关联表，
    # 没有 op 语境，evidence_role 为 NULL，created_revision 即创建版本。
    assert rows == [
        (graph_id, "node", "int1", evidence.ref_id, None, "structure_supported",
         created.revisions["delivery"]),
        (graph_id, "edge", "step1", evidence.ref_id, None, "endpoint_supported",
         created.revisions["delivery"]),
    ]


def test_species_ref_reads_back_through_inline_supplement(tmp_path):
    db, store, engine = _new_engine(tmp_path, "dag-bindings-species")
    species = store.upsert_species(
        canonical_key="smiles:[Pd]|charge:0|multiplicity:1",
        identifiers={"smiles": "[Pd]"},
        charge=0,
        multiplicity=1,
    )
    species_ref = GraphRef(ref_type="species", ref_id=species.species_id)
    node = OccurrenceNode(node_id="cat1", label="cat", role="intermediate")
    created = engine.apply_batch(
        _batch(store, [AddNode(op="add_node", graph="delivery", node=node)])
    )
    assert created.accepted
    attached = engine.apply_batch(
        _batch(
            store,
            [
                AttachRef(
                    op="attach_ref",
                    graph="delivery",
                    target_type="node",
                    target_id="cat1",
                    ref=species_ref,
                )
            ],
        )
    )
    assert attached.accepted

    # species 引用不在 dag_evidence 里：关联表记账仍在，
    # 重建 GraphRef 时回退取内联列的同 id 条目。
    rows = _bindings(db)
    assert [row[3] for row in rows] == [species.species_id]
    node_view = next(
        n for n in engine.snapshot().delivery.nodes if n.node_id == "cat1"
    )
    assert node_view.refs == [species_ref]


def test_remove_edge_cleans_orphan_bindings(tmp_path):
    db, store, engine = _new_engine(tmp_path, "dag-bindings-remove")
    evidence = store.register_evidence("s1", "reaction_mapping", {"mapping_status": "unique"})
    _seed_delivery_graph(store, engine, evidence, extra_evidence=evidence)
    assert len(_bindings(db)) == 2

    removed = engine.apply_batch(
        _batch(
            store,
            [RemoveEdge(op="remove_edge", graph="delivery", edge_id="step1")],
            rationale="edge no longer needed",
        )
    )
    assert removed.accepted

    rows = _bindings(db)
    assert [(row[1], row[2]) for row in rows] == [("node", "int1")]


def test_v11_inline_refs_migrate_into_bindings(tmp_path):
    db, store, engine = _new_engine(tmp_path, "dag-bindings-v11")
    evidence = store.register_evidence("s1", "reaction_mapping", {"mapping_status": "unique"})
    edge_evidence = store.register_evidence("s1", "irc_parse", {"converged": True})
    _seed_delivery_graph(store, engine, evidence, extra_evidence=edge_evidence)
    before = engine.snapshot()
    graph_id = _delivery_graph_id(db)

    # 回滚到 v11 形状：无关联表、schema 版本 11，refs 只在内联列里。
    with db.connect() as con:
        con.execute("DROP TABLE dag_evidence_bindings")
        con.execute("DELETE FROM schema_migrations")
        con.execute(
            "INSERT INTO schema_migrations (version, applied_at) "
            "VALUES (11, datetime('now'))"
        )

    # 模拟 migrate_if_needed() 触发的升级：建表 + 一次性展开内联 refs。
    db.init()

    rows = _bindings(db)
    assert sorted(rows) == sorted([
        (graph_id, "node", "int1", evidence.ref_id, None, "structure_supported", 1),
        (graph_id, "edge", "step1", edge_evidence.ref_id, None, "endpoint_supported", 1),
    ])
    # 迁移后图加载结果与迁移前一致。
    assert engine.snapshot() == before

    # 幂等：重复 init 不重复插、不改写已有行。
    db.init()
    db.init()
    assert _bindings(db) == rows or sorted(_bindings(db)) == sorted(rows)
    assert engine.snapshot() == before


def test_unmigrated_inline_refs_fall_back_to_inline_column(tmp_path):
    """边界兜底：关联表无记录而内联列非空时，读路径回退内联列。"""
    db, store, engine = _new_engine(tmp_path, "dag-bindings-fallback")
    evidence = store.register_evidence("s1", "reaction_mapping", {"mapping_status": "unique"})
    _seed_delivery_graph(store, engine, evidence)
    with db.connect() as con:
        con.execute("DELETE FROM dag_evidence_bindings")

    node = next(n for n in engine.snapshot().delivery.nodes if n.node_id == "int1")
    assert node.refs == [evidence]


def _rollback_to_v11(db):
    with db.connect() as con:
        con.execute("DROP TABLE dag_evidence_bindings")
        con.execute("DELETE FROM schema_migrations")
        con.execute(
            "INSERT INTO schema_migrations (version, applied_at) "
            "VALUES (11, datetime('now'))"
        )


@pytest.mark.asyncio
async def test_async_init_migrates_inline_refs(tmp_path):
    """异步 ainit 走同一套一次性迁移（aiosqlite 游标）。"""
    db, store, engine = _new_engine(tmp_path, "dag-bindings-av11")
    evidence = store.register_evidence("s1", "reaction_mapping", {"mapping_status": "unique"})
    _seed_delivery_graph(store, engine, evidence, extra_evidence=evidence)
    before = engine.snapshot()
    _rollback_to_v11(db)

    await db.ainit()

    assert len(_bindings(db)) == 2
    assert engine.snapshot() == before


# --- §5 显式送审：幂等键与批量原子性（store 层） ---
#
# 幂等键 = (evidence_id, suggested_target_id, suggested_stage, 规范化 claim)。
# 同一证据的 geometry/frequency/single_point 三条声明是三个不同键，都不能丢；
# 相同 pending 声明重发返回既有 review_id（幂等成功）；已裁决的同构重提保留
# "生成新 review" 的既有产品语义。

def _claim_review(evidence_id, target, stage, claim, review_id=None, **kwargs):
    import uuid

    return CallReview(
        review_id=review_id or ("rev_" + uuid.uuid4().hex),
        tool_call_id=kwargs.pop("tool_call_id", "tc_1"),
        tool_name="log_parser",
        is_success=True,
        caller_session_id="s1",
        caller_role_id="coordinator",
        caller_legacy_id="a-0",
        arguments_digest="sha256:demo",
        result_summary="{}",
        suggested_target_id=target,
        suggested_stage=stage,
        claim=claim,
        rationale=kwargs.pop("rationale", ""),
        submitter="a-0",
        evidence_id=evidence_id,
        source="explicit",
        state="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
        **kwargs,
    )


def test_same_evidence_three_stage_claims_are_all_kept(tmp_path):
    """同一日志的三条阶段声明（geometry/frequency/single_point）全部保存不丢。"""
    _db, store, _engine = _new_engine(tmp_path, "dag-bindings-claims")
    evidence = store.register_evidence(
        "s1", "log_parser", {"tool_call_id": "tc_1", "arguments": {}, "result": {}}
    )
    reviews = [
        _claim_review(evidence.ref_id, "int1", stage, f"{stage} claim")
        for stage in ("geometry", "frequency", "single_point")
    ]
    outcomes = store.submit_call_reviews(reviews)
    assert [created for _rid, created in outcomes] == [True, True, True]
    pending = store.list_call_reviews("pending")
    assert len(pending) == 3
    assert {row.suggested_stage for row in pending} == {
        "geometry",
        "frequency",
        "single_point",
    }
    assert all(row.source == "explicit" for row in pending)


def test_identical_pending_claim_resubmission_is_idempotent(tmp_path):
    """相同声明（同证据+目标+阶段+claim）重发返回既有 review_id，不入新箱。"""
    _db, store, _engine = _new_engine(tmp_path, "dag-bindings-idem")
    evidence = store.register_evidence(
        "s1", "log_parser", {"tool_call_id": "tc_1", "arguments": {}, "result": {}}
    )
    first = store.submit_call_reviews(
        [_claim_review(evidence.ref_id, "int1", "geometry", "geometry is converged")]
    )
    assert first[0][1] is True
    # claim 规范化：大小写与多余空白不改变幂等键。
    second = store.submit_call_reviews(
        [_claim_review(evidence.ref_id, "int1", "geometry", "  Geometry IS converged ")]
    )
    assert second == [(first[0][0], False)]
    # 批量内重复同样幂等：第二条命中第一条。
    third = store.submit_call_reviews(
        [
            _claim_review(evidence.ref_id, "int1", "geometry", "geometry is converged"),
            _claim_review(evidence.ref_id, "int1", "frequency", "one imaginary mode"),
        ]
    )
    assert third[0] == (first[0][0], False)
    assert third[1][1] is True
    assert len(store.list_call_reviews("pending")) == 2


def test_different_claim_same_stage_is_independent(tmp_path):
    """同证据同阶段不同 claim 是独立声明，各自保存。"""
    _db, store, _engine = _new_engine(tmp_path, "dag-bindings-claims2")
    evidence = store.register_evidence(
        "s1", "log_parser", {"tool_call_id": "tc_1", "arguments": {}, "result": {}}
    )
    outcomes = store.submit_call_reviews(
        [
            _claim_review(evidence.ref_id, "int1", "geometry", "claim A"),
            _claim_review(evidence.ref_id, "int1", "geometry", "claim B"),
        ]
    )
    assert [created for _rid, created in outcomes] == [True, True]
    assert outcomes[0][0] != outcomes[1][0]
    assert len(store.list_call_reviews("pending")) == 2


def test_decided_resubmission_starts_a_new_review(tmp_path):
    """已裁决的同构重提生成新 review（既有产品语义保留，不跨历史去重）。"""
    _db, store, _engine = _new_engine(tmp_path, "dag-bindings-decided")
    evidence = store.register_evidence(
        "s1", "log_parser", {"tool_call_id": "tc_1", "arguments": {}, "result": {}}
    )
    first = store.submit_call_reviews(
        [_claim_review(evidence.ref_id, "int1", "geometry", "geometry is converged")]
    )
    store.mark_call_review(first[0][0], "reviewed")
    second = store.submit_call_reviews(
        [_claim_review(evidence.ref_id, "int1", "geometry", "geometry is converged")]
    )
    assert second[0][1] is True
    assert second[0][0] != first[0][0]
    assert len(store.list_call_reviews("pending")) == 1
