"""Final negative IMP claims are graded; exploratory calculations are not claims."""

from pathlib import Path

import pytest

from cloudra.benchmark.accuracy import score_accuracy
from cloudra.benchmark.barrier_evidence import BarrierEvidence, StepBarrier
from cloudra.benchmark.schema import GoldMechanismGraph, GoldSpec, TaskSpec

TASKS = Path(__file__).resolve().parents[1] / "ideapool" / "tasks" / "impossible"


def _gold(task_id: str) -> GoldSpec:
    return TaskSpec.model_validate_json((TASKS / f"{task_id}.json").read_text()).gold


def _renamed(graph: GoldMechanismGraph) -> GoldMechanismGraph:
    data = graph.model_dump(by_alias=True)
    names = {node["id"]: f"delivered_{index}" for index, node in enumerate(data["nodes"])}
    for node in data["nodes"]:
        node["id"] = names[node["id"]]
    for index, edge in enumerate(data["edges"]):
        edge["id"] = f"step_{index}"
        edge["from"] = names[edge["from"]]
        edge["to"] = names[edge["to"]]
        if edge["via"] is not None:
            edge["via"] = names[edge["via"]]
    return GoldMechanismGraph.model_validate(data)


def _claim(graph: GoldMechanismGraph, index: int, accessible: bool) -> GoldMechanismGraph:
    edge = graph.edges[index]
    return graph.model_copy(update={
        "edges": [
            item.model_copy(update={"accessible": accessible}) if item.id == edge.id else item
            for item in graph.edges
        ],
        "nodes": [
            node.model_copy(update={"accessible": accessible}) if node.id == edge.via else node
            for node in graph.nodes
        ],
    })


@pytest.mark.parametrize("claim, expected", [(False, 1.0), (True, 0.0), (None, 0.0)])
def test_negative_reaction_requires_matching_final_negative_claim(claim, expected):
    gold = _gold("IA1")
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"edges": []}) if claim is None else _claim(graph, 0, claim)
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == expected
    assert report.edge_scores == {"IA1_E1": expected}
    assert not report.fail_loud


def test_negative_reaction_accepts_final_negative_via_ts_without_numeric_evidence():
    gold = _gold("IA1")
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"edges": [graph.edges[0].model_copy(update={"accessible": True})]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 1.0


def test_exploratory_barrier_evidence_does_not_override_final_negative_claim():
    gold = _gold("IA1")
    graph = _renamed(gold.mechanism_graph)
    # An exploratory collector result is evidence, not a final trusted declaration.
    evidence = BarrierEvidence(steps=[StepBarrier(
        edge_id="step_0", ts_path="exploratory_ts.out", base_path="exploratory_rc.out",
        base_node_id=graph.edges[0].from_node, barrier_kcal_mol=12.0,
    )])
    report = score_accuracy(evidence=evidence, gold=gold, delivered_graph=graph)
    assert report.final_score == 1.0
    assert not report.fail_loud


def test_negative_reaction_without_delivered_graph_scores_zero():
    report = score_accuracy(evidence=BarrierEvidence(), gold=_gold("IA1"))
    assert report.final_score == 0.0


def test_negative_reaction_cannot_hide_positive_duplicate_behind_negative_claim():
    gold = _gold("IA1")
    graph = _renamed(gold.mechanism_graph)
    positive = _claim(graph, 0, True)
    ts = next(node for node in positive.nodes if node.id == positive.edges[0].via)
    positive_ts = ts.model_copy(update={"id": "positive_ts"})
    positive_edge = positive.edges[0].model_copy(update={"id": "z_positive", "via": "positive_ts"})
    graph = graph.model_copy(update={
        "nodes": [*graph.nodes, positive_ts],
        "edges": [*graph.edges, positive_edge],
    })
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 0.0


def test_negative_edge_cannot_declare_a_trusted_barrier():
    gold = _gold("IA1")
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"edges": [graph.edges[0].model_copy(update={"barrier_kcal_mol": 12.0})]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 0.0


@pytest.mark.parametrize("task_id", ["IC3", "IE2", "IF3", "IG8"])
@pytest.mark.parametrize("claim, expected", [(False, 1.0), (True, 0.0), (None, 0.0)])
def test_negative_property_edges_grade_final_claim_without_ts(task_id, claim, expected):
    gold = _gold(task_id)
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"edges": []}) if claim is None else _claim(graph, 0, claim)
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == expected
    assert report.edge_scores == {f"{task_id}_E1": expected}
    assert not report.fail_loud


@pytest.mark.parametrize("task_id", ["IC3", "IE2", "IF3", "IG8"])
def test_negative_property_edge_cannot_hide_positive_target_species(task_id):
    gold = _gold(task_id)
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"nodes": [
        node.model_copy(update={"accessible": True}) for node in graph.nodes
    ]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 0.0


@pytest.mark.parametrize("task_id, key", [
    ("IC3", "singlet_triplet_gap_kcal_mol"),
    ("IE2", "bond_dissociation_energy_kcal_mol"),
    ("IF3", "singlet_triplet_gap_kcal_mol"),
    ("IG8", "bond_dissociation_energy_kcal_mol"),
])
@pytest.mark.parametrize("node_index", [0, 1])
def test_negative_property_target_cannot_deliver_trusted_number_on_any_node(task_id, key, node_index):
    gold = _gold(task_id)
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"nodes": [
        node.model_copy(update={"properties": {key: 12.0}}) if index == node_index else node
        for index, node in enumerate(graph.nodes)
    ]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 0.0


def test_negative_property_target_may_keep_diagnostics_and_negative_explanation():
    gold = _gold("IC3")
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"nodes": [
        node.model_copy(update={"properties": {
            "energy_hartree": -12.0, "charge": 0.0, "n_imag": 2.0,
            "state_ordering": "Cannot determine a trustworthy ordering with the allowed methods.",
        }}) for node in graph.nodes
    ]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 1.0


@pytest.mark.parametrize("claim, expected", [(False, 1.0), (True, 0.0), (None, 0.0)])
def test_negative_species_without_edges_requires_same_species_negative_claim(claim, expected):
    gold = _gold("ID2")
    graph = _renamed(gold.mechanism_graph)
    nodes = [] if claim is None else [graph.nodes[0].model_copy(update={"accessible": claim})]
    report = score_accuracy(
        evidence=BarrierEvidence(), gold=gold, delivered_graph=graph.model_copy(update={"nodes": nodes})
    )
    assert report.final_score == expected
    assert not report.fail_loud


def test_negative_species_cannot_hide_positive_duplicate():
    gold = _gold("ID2")
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"nodes": [
        *graph.nodes, graph.nodes[0].model_copy(update={"id": "positive", "accessible": True})
    ]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 0.0


def test_negative_species_may_keep_numeric_diagnostics():
    gold = _gold("ID2")
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"nodes": [graph.nodes[0].model_copy(update={
        "properties": {"charge": 0.0, "n_imag": 2.0, "diagnostic_energy_hartree": -25.0}
    })]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 1.0


@pytest.mark.parametrize("key", [
    "f_o_bond_length_angstrom", "o_o_bond_length_angstrom", "f_o_bond_dissociation_energy_kcal_mol"
])
def test_negative_species_cannot_deliver_trusted_property_number(key):
    gold = _gold("ID2")
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"nodes": [graph.nodes[0].model_copy(update={"properties": {key: 1.5}})]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 0.0


@pytest.mark.parametrize("change", [{"smiles": ["C"]}, {"role": "product"}])
def test_negative_species_requires_species_and_role_match(change):
    gold = _gold("ID2")
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"nodes": [graph.nodes[0].model_copy(update=change)]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=gold, delivered_graph=graph)
    assert report.final_score == 0.0


@pytest.mark.parametrize("negative_claim, expected", [(False, 1.0), (True, 0.5), (None, 0.5)])
def test_ib9_grades_numeric_reference_and_negative_target_together(negative_claim, expected):
    gold = _gold("IB9")
    graph = _renamed(gold.mechanism_graph)
    graph = graph.model_copy(update={"edges": [graph.edges[0]]}) if negative_claim is None else _claim(
        graph, 1, negative_claim
    )
    # Controlled collector output for this unit test; no logs or scientific results are generated.
    evidence = BarrierEvidence(steps=[StepBarrier(
        edge_id="step_0", ts_path="unit_ts.out", base_path="unit_rc.out", base_node_id=graph.edges[0].from_node,
        barrier_kcal_mol=5.65, declared_kcal_mol=5.65,
    )])
    report = score_accuracy(evidence=evidence, gold=gold, delivered_graph=graph)
    assert report.final_score == expected
    assert report.edge_scores["IB9_E1"] == 1.0


def test_ib9_missing_numeric_reference_does_not_receive_negative_target_credit_twice():
    gold = _gold("IB9")
    report = score_accuracy(
        evidence=BarrierEvidence(), gold=gold, delivered_graph=_renamed(gold.mechanism_graph)
    )
    assert report.final_score == 0.5
    assert report.edge_scores == {"IB9_E1": 0.0, "IB9_E2": 1.0}


def test_accessible_null_reference_keeps_existing_ungraded_policy():
    graph = _claim(_gold("IA1").mechanism_graph, 0, True)
    graph = graph.model_copy(update={"nodes": [
        node.model_copy(update={"properties": {"bond_dissociation_energy_kcal_mol": 10.0}})
        for node in graph.nodes
    ]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=GoldSpec(mechanism_graph=graph))
    assert report.final_score == 1.0


def test_no_targets_keeps_existing_ungraded_policy():
    report = score_accuracy(
        evidence=BarrierEvidence(), gold=GoldSpec(mechanism_graph=GoldMechanismGraph(nodes=[]))
    )
    assert report.final_score == 1.0
