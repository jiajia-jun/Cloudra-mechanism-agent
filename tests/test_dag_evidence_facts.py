"""Task 4：任务契约、事实存储与可靠来源。

覆盖：ClaimSpec/检查词表、EvidenceFact 幂等存储与归属、证据反查索引迁移、
Artifact 快照复用/覆盖/不可用、契约范围变更审批路由、property 契约不继承
机理空图判据。
"""

import json

import pytest

from cloudra.dag.drafts import classify_contract_change
from cloudra.dag.evidence_facts import EvidenceFact, FactSubject, fact_dedup_key
from cloudra.dag.models import (
    CHECK_VOCABULARY,
    ClaimSpec,
    GraphRef,
    StageContract,
)
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB


def _new_store(tmp_path, conversation_id="facts"):
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    return db, DagStore(db)


def _ref(ev_id="ev_1", hash_="sha256:aaa"):
    return GraphRef(ref_type="tool_result", ref_id=ev_id, content_hash=hash_)


def _fact(fact_id="fact_1", check="stationary_point", outcome="supports",
          ref=None, details=None, target_hint=""):
    return EvidenceFact(
        fact_id=fact_id,
        check=check,
        outcome=outcome,
        subject=FactSubject(target_hint=target_hint),
        source_refs=[ref or _ref()],
        details=details or {"opt_converged": True},
    )


# ---------------------------------------------------------------------------
# 词表与契约类型
# ---------------------------------------------------------------------------


def test_check_vocabulary_is_enforced_on_facts_and_claims():
    for check in sorted(CHECK_VOCABULARY):
        assert _fact(check=check).check == check
    with pytest.raises(ValueError, match="unknown check"):
        _fact(check="vibes")
    with pytest.raises(ValueError, match="unknown checks"):
        ClaimSpec(kind="mechanism", required_checks={"not_a_check"})


def test_stage_contract_keeps_legacy_shape_readable():
    legacy = StageContract.model_validate({"stages": [{"kind": "geometry"}]})
    assert legacy.contract_version == 1
    assert legacy.claim_spec is None
    v2 = StageContract.model_validate({
        "stages": [{"kind": "geometry"}],
        "contract_version": 2,
        "claim_spec": {"kind": "property", "required_checks": ["identity"]},
    })
    assert v2.contract_version == 2
    assert v2.claim_spec is not None and v2.claim_spec.kind.value == "property"


def test_classify_contract_change_scope_guards():
    old = ClaimSpec(
        kind="electronic_barrier",
        quantity="delta E",
        unit="kcal/mol",
        scope={"targets": ["ts1", "r1"]},
        required_checks={"stationary_point", "curvature"},
    )
    # 删除 required_checks / 改 kind / 移除目标都是 scope_change
    assert classify_contract_change(
        old, old.model_copy(update={"required_checks": {"stationary_point"}})
    ) == "scope_change"
    assert classify_contract_change(
        old, old.model_copy(update={"kind": "property"})
    ) == "scope_change"
    assert classify_contract_change(
        old, old.model_copy(update={"scope": {"targets": ["ts1"]}})
    ) == "scope_change"
    # 电子能垒改成结构展示之外的"所回答的量"变化同样是 scope_change
    assert classify_contract_change(
        old, old.model_copy(update={"quantity": "structure only"})
    ) == "scope_change"
    # 增加检查/补 optional 不缩小范围：compatible
    assert classify_contract_change(
        old,
        old.model_copy(update={"required_checks": {"stationary_point", "curvature", "energy"}}),
    ) == "compatible"
    assert classify_contract_change(None, old) == "compatible"


# ---------------------------------------------------------------------------
# 事实存储：幂等、反证保留、按 target 归属
# ---------------------------------------------------------------------------


def test_record_facts_idempotent_per_source_attempt_and_adapter(tmp_path):
    _db, store = _new_store(tmp_path)
    first = _fact(fact_id="fact_a")
    again = _fact(fact_id="fact_b")  # 同一来源同一内容，不同 fact_id
    ids = store.record_facts([first, again])
    assert ids == ["fact_a", "fact_a"]  # 重复解析命中同一行

    # 独立 attempt（同名文件被覆盖 → 新 hash）绝不合并
    new_attempt = _fact(fact_id="fact_c", ref=_ref("ev_1", "sha256:bbb"))
    (ids2,) = store.record_facts([new_attempt])
    assert ids2 == "fact_c"
    # 不同作业重复失败：两条 refutes 都保留
    fail1 = _fact(fact_id="fact_f1", outcome="refutes",
                  ref=_ref("ev_j1", "sha256:j1"), details={"opt_converged": False})
    fail2 = _fact(fact_id="fact_f2", outcome="refutes",
                  ref=_ref("ev_j2", "sha256:j2"), details={"opt_converged": False})
    assert store.record_facts([fail1, fail2]) == ["fact_f1", "fact_f2"]
    assert fact_dedup_key(fail1) != fact_dedup_key(fail2)


def test_facts_for_target_via_hint_and_bindings(tmp_path):
    db, store = _new_store(tmp_path)
    store.ensure_bundle(session_id="s1")
    hinted = _fact(fact_id="fact_h", target_hint="ts1")
    bound_ref = _ref("ev_bound", "sha256:bound")
    bound = _fact(fact_id="fact_b", ref=bound_ref)
    other = _fact(fact_id="fact_o", ref=_ref("ev_other", "sha256:other"))
    store.record_facts([hinted, bound, other])

    with db.connect() as con:
        graph_id = con.execute(
            "SELECT graph_id FROM dag_graphs WHERE graph_kind='delivery'"
        ).fetchone()[0]
        con.execute(
            "INSERT INTO dag_evidence_bindings(graph_id, target_type, target_id, "
            "evidence_id, created_revision) VALUES (?, 'edge', 'ts1', ?, 1)",
            (graph_id, "ev_bound"),
        )

    found = {f.fact_id for f in store.facts_for_target("ts1")}
    assert found == {"fact_h", "fact_b"}


# ---------------------------------------------------------------------------
# 证据登记反查索引与迁移回填
# ---------------------------------------------------------------------------


def test_register_evidence_indexes_tool_call_and_resolve_uses_index(tmp_path):
    _db, store = _new_store(tmp_path)
    ref = store.register_evidence("s1", "log_parser", {
        "tool_call_id": "call-1",
        "arguments": {},
        "result": {"is_success": True},
    })
    found = store.resolve_evidence_for_call("call-1")
    assert found is not None and found.ref_id == ref.ref_id


def test_legacy_rows_backfill_and_unparseable_stays_legacy(tmp_path):
    db = ConversationDB("legacy", data_dir=tmp_path).init()
    store = DagStore(db)
    # 模拟迁移前旧行：直接 INSERT，反查列为 NULL
    payload = json.dumps({"tool_call_id": "legacy-call", "result": {}})
    with db.connect() as con:
        con.execute(
            "INSERT INTO dag_evidence(evidence_id, session_id, source_type, "
            "source_name, content_hash, payload, created_at) "
            "VALUES ('ev_legacy', 's1', 'tool_result', 'log_parser', "
            "'sha256:x', ?, '2026-01-01')",
            (payload,),
        )
        con.execute(
            "INSERT INTO dag_evidence(evidence_id, session_id, source_type, "
            "source_name, content_hash, payload, created_at) "
            "VALUES ('ev_broken', 's1', 'tool_result', 'log_parser', "
            "'sha256:y', 'not-json{', '2026-01-01')"
        )
        # 清除迁移已填的值，模拟真正的旧库状态
        con.execute("UPDATE dag_evidence SET tool_call_id=NULL, compute_job_id=NULL")

    # 重新初始化触发回填
    ConversationDB("legacy", data_dir=tmp_path).init()
    with db.connect() as con:
        rows = dict(con.execute(
            "SELECT evidence_id, tool_call_id FROM dag_evidence"
        ).fetchall())
    assert rows["ev_legacy"] == "legacy-call"  # 可解析 → 回填
    assert rows["ev_broken"] is None  # 不可解析 → 保持 legacy NULL

    # 两条路径都能反查：索引命中 + NULL 行回退扫描
    assert store.resolve_evidence_for_call("legacy-call").ref_id == "ev_legacy"
    with db.connect() as con:
        con.execute(
            "INSERT INTO dag_evidence(evidence_id, session_id, source_type, "
            "source_name, content_hash, payload, created_at) "
            "VALUES ('ev_null', 's1', 'tool_result', 'log_parser', "
            "'sha256:z', ?, '2026-01-01')",
            (json.dumps({"tool_call_id": "null-row-call"}),),
        )
        con.execute(
            "UPDATE dag_evidence SET tool_call_id=NULL WHERE evidence_id='ev_null'"
        )
    assert store.resolve_evidence_for_call("null-row-call").ref_id == "ev_null"


# ---------------------------------------------------------------------------
# Artifact 快照：重复解析复用、同名覆盖不合并
# ---------------------------------------------------------------------------


def test_artifact_snapshot_reuse_and_overwrite(tmp_path):
    from cloudra.persistence.artifacts import ArtifactService

    data_dir = tmp_path / "data"
    db = ConversationDB("arts", data_dir=data_dir).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session(session_id, created_at) VALUES ('s1', '2026-01-01')"
        )
    work = tmp_path / "work"
    work.mkdir()
    source = work / "calc.out"
    source.write_text("result v1", encoding="utf-8")

    service = ArtifactService(data_dir=data_dir)
    art1, created1 = service.snapshot_file(
        conversation_id="arts", session_id="s1", source=source, allowed_root=work
    )
    assert created1
    # 同一文件重复收集：复用 hash，不重复拷贝
    art2, created2 = service.snapshot_file(
        conversation_id="arts", session_id="s1", source=source, allowed_root=work
    )
    assert not created2 and art2.artifact_id == art1.artifact_id

    # 同名文件被覆盖（独立 attempt）：hash 不同 → 新 artifact，不合并
    source.write_text("result v2", encoding="utf-8")
    art3, created3 = service.snapshot_file(
        conversation_id="arts", session_id="s1", source=source, allowed_root=work
    )
    assert created3 and art3.artifact_id != art1.artifact_id


# ---------------------------------------------------------------------------
# 契约路由与 property 空图判据
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_mode_scope_change_is_auto_accepted_without_supervisor(tmp_path):
    from cloudra.dag.controller import DagController

    db = ConversationDB("contracts", data_dir=tmp_path).init()
    controller = DagController(db, "s1", "dag_record")
    ops = [{
        "op": "add_node",
        "graph": "delivery",
        "node": {"node_id": "r", "node_type": "occurrence", "label": "R"},
    }]
    claim = {
        "kind": "electronic_barrier",
        "quantity": "delta E",
        "unit": "kcal/mol",
        "required_checks": ["stationary_point", "energy"],
    }
    first = await controller.propose_mechanism(
        operations=ops, stage_contracts={}, rationale="initial",
        actor_id="a-1", claim_spec=claim,
    )
    assert first["accepted"] is True  # 首次契约：record 自动接受

    # Record has no Supervisor, so the harness must settle a changed scope.
    # 图对象已由首份 proposal 落库；第二份 proposal 必须用 update_node，
    # 重复 add_node 会正确触发 duplicate_id。
    downgrade = dict(claim, required_checks=["stationary_point"])
    second = await controller.propose_mechanism(
        operations=[{
            "op": "update_node", "graph": "delivery", "node_id": "r",
            "changes": {"label": "R revised"},
        }], stage_contracts={}, rationale="downgrade",
        actor_id="a-1", claim_spec=downgrade,
    )
    assert second["accepted"] is True
    assert second["scope_change"] is True
    assert second.get("pending_approval") is None
    assert controller.store.accepted_claim_spec().required_checks == {"stationary_point"}


def test_property_claim_does_not_require_elementary_step_edge(tmp_path):
    from cloudra.dag.completion import evaluate_delivery
    from cloudra.dag.models import CoverageContract, GraphData

    graph = GraphData(graph_id="g", graph_kind="delivery", revision=0, nodes=[], edges=[])
    contract = CoverageContract()
    mechanism_report = evaluate_delivery(graph, contract)
    assert any(g.code == "empty_delivery_graph" for g in mechanism_report.unresolved)
    property_report = evaluate_delivery(graph, contract, claim_kind="property")
    # property 空图报"缺物种节点"，不报"缺 elementary-step 边"
    gate = next(g for g in property_report.unresolved if g.code == "empty_delivery_graph")
    assert "elementary step" not in gate.detail


@pytest.mark.asyncio
async def test_failed_result_can_be_submitted_for_review(tmp_path):
    """负结果可送审：失败结果不再因 is_success=false 被拒绝入箱；
    但 CallReview.is_success 如实记录 False（不能充作成功计算的支持）。"""
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

    db = ConversationDB("failed-review", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    seeded = DagEngine(store).apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="seed step1 with a stage contract",
            operations=[
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="r", label="R", role="reactant")),
                AddNode(op="add_node", graph="delivery", node=OccurrenceNode(
                    node_id="p", label="P", role="product")),
                AddEdge(op="add_edge", graph="delivery", edge=ElementaryStepEdge(
                    edge_id="step1", source_node_id="r", target_node_id="p",
                    stages=[StageState(kind="ts_opt")])),
            ],
        )
    )
    assert seeded.accepted
    controller = DagController(db, "s1", "dag_record")
    await controller.on_tool_finished(
        "tc-fail",
        "format_converter",
        {"input_path": "/work/bad.log"},
        {"is_success": False, "error": "SCF not converged"},
    )
    submitted = await controller.submit_evidence_for_review([{
        "tool_call_id": "tc-fail",
        "bind_target": "step1",
        "stage_kind": "ts_opt",
        "claim": "negative evidence: the SCF did not converge",
    }])
    assert submitted["attachments"][0]["enqueued"] is True
    pending = controller.store.list_call_reviews(state="pending")
    assert len(pending) == 1
    assert pending[0].is_success is False
    assert pending[0].suggested_target_id == "step1"
