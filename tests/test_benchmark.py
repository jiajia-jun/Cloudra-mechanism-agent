"""Anchor tests for the benchmark module.

Covers:
- schema round-trip (TaskSpec dump -> validate), including alias keys.
- easy task generation count and field correctness.
- GED cost ordering anchors (identical > similar > far).
- accuracy Gaussian scoring + penalty cap.
- method-policy interception verdicts.
- integrity audit on a synthetic sandbox.

No LLM, no network. RDKit/networkx required (already deps).
"""

from __future__ import annotations

import json

import pytest

from cloudra.benchmark import gen_easy_tasks
from cloudra.benchmark.accuracy import score_accuracy
from cloudra.benchmark.graph_similarity import GedConfig, mechanism_similarity
from cloudra.benchmark.integrity import audit_integrity
from cloudra.benchmark.method_policy import intercept
from cloudra.benchmark.schema import (
    AccuracyRubric,
    BondChangeSet,
    GoldMechanismGraph,
    MechanismEdge,
    MechanismNode,
    MethodPolicy,
    NodeRole,
    ReferenceComputation,
    TaskSpec,
)


def _graph(r, p, bc=None, with_ts=True):
    nodes = [
        MechanismNode(id="R", role=NodeRole.REACTANT, smiles=r),
        MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=p),
    ]
    via = None
    if with_ts:
        nodes.insert(1, MechanismNode(id="TS", role=NodeRole.TRANSITION_STATE, smiles=[]))
        via = "TS"
    e = MechanismEdge(id="E", **{"from": "R", "to": "P"}, via=via, bond_changes=bc or BondChangeSet())
    return GoldMechanismGraph(nodes=nodes, edges=[e])


# --- schema / generation ---


def test_easy_generation_count_and_roundtrip(tmp_path):
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)
    assert len(tasks) == 30
    for t in tasks:
        dumped = t.model_dump(mode="json", by_alias=True)
        rt = TaskSpec.model_validate(dumped)
        assert rt.task_id == t.task_id


def test_easy_charge_and_smiles():
    tasks = {t.task_id: t for t in gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)}
    assert tasks["C1"].system.charge == -1
    assert tasks["M12"].system.charge == 1
    assert tasks["D1"].system.reactants == ["C=CC=C", "C=C"]
    # degenerate M-group process: product falls back to reactant
    assert tasks["M6"].system.products == ["CC"]


# --- GED anchors ---


def test_ged_cost_ordering():
    bc = BondChangeSet(**{"break": []}, form=[[1, 2], [3, 4]])
    gold = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], bc)
    same = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], BondChangeSet(**{"break": []}, form=[[1, 2], [3, 4]]))
    similar = _graph(["C=CC=C", "C=C"], ["C1CCCC1"], BondChangeSet(**{"break": []}, form=[[1, 2]]))
    far = _graph(["CC"], ["CC"], BondChangeSet(**{"break": [[1, 2]]}))
    cfg = GedConfig()
    s_same = mechanism_similarity(same, gold, cfg).score
    s_sim = mechanism_similarity(similar, gold, cfg).score
    s_far = mechanism_similarity(far, gold, cfg).score
    assert s_same == pytest.approx(1.0)
    assert s_same > s_sim > s_far
    assert s_far < 0.2


def test_ged_missing_ts_lowers_score():
    gold = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], with_ts=True)
    no_ts = _graph(["C=CC=C", "C=C"], ["C1CC=CCC1"], with_ts=False)
    cfg = GedConfig()
    assert mechanism_similarity(no_ts, gold, cfg).score < 1.0


# --- accuracy ---


def test_accuracy_gaussian_and_cap():
    gold = ReferenceComputation(barrier_kcal_mol=27.5)
    r = AccuracyRubric(sigma_kcal_mol=3.0, max_penalty_fraction=0.3)
    assert score_accuracy(27.5, gold, r).gaussian_score == pytest.approx(1.0)
    near = score_accuracy(28.0, gold, r)
    assert near.gaussian_score > 0.95
    far = score_accuracy(100.0, gold, r)
    assert far.capped_penalty == pytest.approx(0.3)  # capped
    assert far.final_score == pytest.approx(0.7)
    missing = score_accuracy(None, gold, r)
    assert missing.final_score == pytest.approx(0.7)


def test_accuracy_disabled_passthrough():
    gold = ReferenceComputation(barrier_kcal_mol=27.5)
    r = AccuracyRubric(enabled=False)
    assert score_accuracy(None, gold, r).final_score == 1.0


# --- method policy ---


@pytest.mark.parametrize(
    "tool,args,allowed",
    [
        ("submit_compute_job", {"method": "mace-omol25"}, True),
        ("submit_compute_job", {"method": "xtb"}, True),
        ("submit_compute_job", {"method": "wb97m-v", "basis": "def2-tzvpd"}, False),
        ("qm_input_writer", {"method": "ccsd(t)", "basis": "cc-pvtz"}, False),
        ("bash", {"command": "xtb ts.xyz --opt"}, True),
        ("bash", {"command": "cat > t.gjf <<EOF\n# wb97m-v/def2-tzvpd opt\nEOF"}, False),
        ("read_file", {"path": "x"}, True),
    ],
)
def test_method_policy(tool, args, allowed):
    assert intercept(tool, args, MethodPolicy()).allowed is allowed


# --- integrity ---


def test_integrity_audit_binds_evidence(tmp_path):
    g = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": ["C=CC=C", "C=C"], "accessible": True, "label": "r"},
            {"id": "TS", "role": "transition_state", "smiles": [], "accessible": True, "label": "ts"},
            {"id": "P", "role": "product", "smiles": ["C1CC=CCC1"], "accessible": True, "label": "p"},
        ],
        "edges": [{"id": "E1", "from": "R", "to": "P", "via": "TS", "step_type": "da",
                    "bond_changes": {"break": [], "form": [[1, 2]]}, "accessible": True}],
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(g))
    (tmp_path / "r.log").write_text("smiles: C=CC=C\nsmiles: C=C\n")
    (tmp_path / "p.log").write_text("smiles: C1CC=CCC1\n")
    rep = audit_integrity(tmp_path)
    assert rep.graph_found and rep.graph_parseable
    assert rep.fraction_bound == 1.0
    assert rep.passed


def test_integrity_missing_graph_fails(tmp_path):
    rep = audit_integrity(tmp_path)
    assert not rep.graph_found
    assert not rep.passed
