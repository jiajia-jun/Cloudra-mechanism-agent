"""Task 5：按类型验证（evaluate_claim）、反应映射/解析事实适配器，以及 v2
已接受契约下的证据乱序绑定。
"""

import pytest

from cloudra.dag.evidence_facts import EvidenceFact, FactSubject
from cloudra.dag.models import ClaimSpec, GraphRef
from cloudra.dag.requirements import evaluate_claim


def _ref(ref_id="ev_1", hash_="sha256:aaa"):
    return GraphRef(ref_type="tool_result", ref_id=ref_id, content_hash=hash_)


def _fact(check, outcome, *, details=None, target_hint=""):
    return EvidenceFact(
        fact_id=f"fact_{check}_{outcome}_{len(details or {})}",
        check=check,
        outcome=outcome,
        subject=FactSubject(target_hint=target_hint),
        source_refs=[_ref()],
        details=details or {},
    )


def test_evaluate_claim_supported():
    claim = ClaimSpec(
        kind="mechanism",
        required_checks={"stationary_point", "curvature", "identity"},
    )
    facts = [
        _fact("stationary_point", "supports"),
        _fact("curvature", "supports"),
        _fact("identity", "supports"),
    ]
    out = evaluate_claim(claim, facts)
    assert out["scientific_status"] == "supported"
    assert out["missing"] == []


def test_evaluate_claim_missing_is_unresolved():
    claim = ClaimSpec(
        kind="mechanism",
        required_checks={"stationary_point", "curvature", "identity"},
    )
    facts = [
        _fact("stationary_point", "supports"),
        _fact("identity", "supports"),
        _fact("identity", "inconclusive"),
    ]
    out = evaluate_claim(claim, facts)
    assert out["scientific_status"] == "unresolved"
    assert out["missing"] == ["curvature"]


def test_evaluate_claim_contradiction_is_unresolved_even_when_all_required_support_exists():
    claim = ClaimSpec(
        kind="mechanism",
        required_checks={"stationary_point", "identity"},
    )
    facts = [
        _fact("stationary_point", "supports"),
        _fact("identity", "supports"),
        _fact("identity", "refutes"),
    ]
    out = evaluate_claim(claim, facts)
    assert out["scientific_status"] == "unresolved"
    assert out["contradictions"]
    assert out["missing"] == []


def test_evaluate_claim_no_required_checks_is_out_of_scope():
    claim = ClaimSpec(kind="property", required_checks=set())
    out = evaluate_claim(claim, [_fact("identity", "supports")])
    assert out["scientific_status"] == "out_of_scope"


# ---------------------------------------------------------------------------
# 适配器：身份与映射分离
# ---------------------------------------------------------------------------


def test_reaction_mapping_facts_separate_identity_and_mapping():
    from cloudra.dag.fact_adapters import reaction_mapping_facts

    payload = {
        "result": {
            "is_success": True,
            "reactant_identity": "match",
            "product_identity": "match",
            "binding_status": "inconclusive",
            "mapping_status": "ambiguous",
            "binding_source": "not_available",
            "binding_diagnostics": ["symmetric heavy-atom binding not unique"],
            "atom_map": [],
        },
        "arguments": {
            "reactant_smiles": "CCO",
            "product_smiles": "C(C)O",
            "reactant_charge": 0,
            "product_charge": 0,
        },
    }
    facts = reaction_mapping_facts(payload, _ref())
    identity_facts = [f for f in facts if f.check == "identity"]
    mapping_facts = [f for f in facts if f.check == "mapping"]
    assert len(identity_facts) == 2
    assert {f.details["endpoint_role"] for f in identity_facts} == {
        "reactant", "product",
    }
    assert all(f.outcome == "supports" for f in identity_facts)
    # Symmetry ambiguity is inconclusive mapping, not identity mismatch.
    assert mapping_facts[0].outcome == "inconclusive"


def test_reaction_mapping_facts_identity_mismatch_is_refutes():
    from cloudra.dag.fact_adapters import reaction_mapping_facts

    payload = {
        "result": {
            "is_success": True,
            "reactant_identity": "match",
            "product_identity": "mismatch",
            "binding_status": "inconclusive",
            "mapping_status": "inconclusive",
        },
    }
    facts = reaction_mapping_facts(payload, _ref())
    product_identity = next(
        f for f in facts
        if f.check == "identity" and f.details["endpoint_role"] == "product"
    )
    assert product_identity.outcome == "refutes"


# ---------------------------------------------------------------------------
# v2 乱序绑定：纯 StageContract 与 controller 级验证
# ---------------------------------------------------------------------------


def test_apply_stage_verdict_v2_allows_out_of_order():
    from cloudra.dag.engine import apply_stage_verdict
    from cloudra.dag.models import StageKind, StageState

    stages = [
        StageState(kind=StageKind.TS_OPT, status="pending"),
        StageState(kind=StageKind.FREQUENCY, status="pending"),
        StageState(kind=StageKind.IDENTITY, status="pending"),
    ]
    ref = _ref("ev_freq")
    updated = apply_stage_verdict(
        stages,
        stage_kind=StageKind.FREQUENCY,
        verdict="agree",
        ref=ref,
        tool_succeeded=True,
        allow_out_of_order=True,
    )
    assert updated[1].status.value == "supported"


@pytest.mark.asyncio
async def test_controller_v2_out_of_order_bind_after_accepted_claim(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import (
        AddEdge,
        AddNode,
        ClaimSpec,
        ElementaryStepEdge,
        GraphActor,
        MechanismDraft,
        MutationBatch,
        OccurrenceNode,
        StageState,
    )
    from cloudra.dag.store import DagStore
    from cloudra.infra.config import get_config
    from cloudra.persistence.database import ConversationDB

    get_config().data_dir = tmp_path
    db = ConversationDB("v2-order", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    engine = DagEngine(store)
    # Stage contract is seeded the same way real Coordinator proposals do.
    seeded = engine.apply_batch(
        MutationBatch(
            session_id="s1",
            actor=GraphActor.AGENT,
            actor_id="a-0",
            base_revisions=store.load_bundle().revisions,
            rationale="v2 edge contract",
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
                        stages=[
                            StageState(kind=k)
                            for k in ("ts_opt", "frequency", "identity")
                        ],
                    ),
                ),
            ],
        )
    )
    assert seeded.accepted
    # Simulate the project having an accepted v2 claim.
    draft = MechanismDraft(
        operations=[
            AddNode(
                op="add_node",
                graph="delivery",
                node=OccurrenceNode(node_id="r", label="R", role="reactant"),
            )
        ],
        rationale="accepted v2",
        state="accepted",
        contract_version=2,
        claim_spec=ClaimSpec(
            kind="mechanism",
            required_checks={"stationary_point", "curvature", "identity"},
        ),
    )
    store.save_draft(draft, actor_id="a-0")

    controller = DagController(db, "s1", "dag_record")
    # frequency arrives before ts_opt. v2 must accept it.
    await controller.on_tool_finished(
        "tc-freq", "log_parser", {"log_path": "ts.log"}, {
            "is_success": True,
            "normal_termination": True,
            "imaginary_frequencies": [-518.3],
        }
    )
    bound = await controller.bind_stage_for_call(
        "tc-freq", "step1", "frequency"
    )
    assert bound["accepted"] is True
    edge = next(e for e in controller.engine.snapshot().delivery.edges
                if e.edge_id == "step1")
    by_kind = {s.kind.value: s.status.value for s in edge.stages}
    assert by_kind["frequency"] == "supported"
    assert by_kind["ts_opt"] == "pending"


def test_derive_does_not_promote_thermo_alone_to_thermo_annotated():
    from cloudra.dag.models import StageKind, StageState, derive_evidence_level

    only_thermo = [StageState(kind=StageKind.THERMOCHEMISTRY, status="supported")]
    assert derive_evidence_level(only_thermo, is_edge=True) == "proposed"

    # A full legacy thermo_annotated stage set still maps correctly.
    full = [
        StageState(kind=StageKind.TS_OPT, status="supported"),
        StageState(kind=StageKind.FREQUENCY, status="supported"),
        StageState(kind=StageKind.SHORT_IRC, status="supported"),
        StageState(kind=StageKind.ENDPOINT_A, status="supported"),
        StageState(kind=StageKind.ENDPOINT_B, status="supported"),
        StageState(kind=StageKind.DIRECTION, status="supported"),
        StageState(kind=StageKind.IDENTITY, status="supported"),
        StageState(kind=StageKind.THERMOCHEMISTRY, status="supported"),
    ]
    assert derive_evidence_level(full, is_edge=True) == "thermo_annotated"
