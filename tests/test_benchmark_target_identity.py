"""Match the requested channel, electronic state, and barrier reference.

The fixtures retain the original three deliveries' final claims. No task ID is
passed to the matcher, and evidence values below are the original native energy
differences rather than values selected for their agreement with Gold.
"""

import json
from pathlib import Path

import pytest

from cloudra.benchmark.accuracy import gaussian_barrier_score, score_accuracy
from cloudra.benchmark.barrier_evidence import (
    HARTREE_TO_KCAL_MOL,
    BarrierEvidence,
    StepBarrier,
)
from cloudra.benchmark.graph_similarity import mechanism_similarity
from cloudra.benchmark.integrity import parse_delivered_graph
from cloudra.benchmark.schema import GoldMechanismGraph, GoldSpec, TaskSpec
from cloudra.benchmark.selfconsistency import (
    ElementCheck,
    SelfConsistencyReport,
    gold_subgraph_selfconsistency,
)

FIXTURES = Path(__file__).parent / "fixtures" / "benchmark_target_identity"
TASKS = Path(__file__).resolve().parents[1] / "ideapool" / "tasks"


def _delivery(case):
    return parse_delivered_graph(json.loads((FIXTURES / f"{case}.json").read_text()))


def _gold(case):
    tier, task_id = {
        "ia5_record": ("impossible", "IA5"),
        "ic3_brief": ("impossible", "IC3"),
        "l2_standard": ("easy", "L2"),
    }[case]
    return TaskSpec.model_validate_json((TASKS / tier / f"{task_id}.json").read_text()).gold


def _rename(graph):
    """IDs and graph order cannot convey the requested chemical identity."""
    nodes = {node.id: f"unrelated_node_{len(graph.nodes) - index}"
             for index, node in enumerate(graph.nodes)}
    edges = {edge.id: f"unrelated_step_{len(graph.edges) - index}"
             for index, edge in enumerate(graph.edges)}
    return graph.model_copy(update={
        "nodes": [node.model_copy(update={"id": nodes[node.id]}) for node in reversed(graph.nodes)],
        "edges": [edge.model_copy(update={
            "id": edges[edge.id], "from_node": nodes[edge.from_node],
            "to_node": nodes[edge.to_node], "via": nodes.get(edge.via),
        }) for edge in reversed(graph.edges)],
    })


@pytest.mark.parametrize("case", ["ia5_record", "ic3_brief"])
@pytest.mark.parametrize("renamed", [False, True])
def test_original_negative_target_excludes_the_other_channel_or_state(case, renamed):
    graph = _delivery(case)
    if renamed:
        graph = _rename(graph)
    report = score_accuracy(evidence=BarrierEvidence(), gold=_gold(case), delivered_graph=graph)
    assert report.final_score == 1.0
    assert not report.fail_loud


@pytest.mark.parametrize("case, target_id", [
    ("ia5_record", "e_dis"), ("ic3_brief", "e2_T1_to_S2"),
])
def test_same_target_cannot_hide_a_positive_claim_behind_a_negative_claim(case, target_id):
    graph = _delivery(case)
    edge = next(edge for edge in graph.edges if edge.id == target_id)
    node_id = edge.via or edge.to_node
    node = next(node for node in graph.nodes if node.id == node_id)
    positive_node = node.model_copy(update={"id": "contradictory_species", "accessible": True})
    positive_edge = edge.model_copy(update={
        "id": "contradictory_step", "accessible": True,
        "via" if edge.via else "to_node": positive_node.id,
    })
    graph = graph.model_copy(update={
        "nodes": [*graph.nodes, positive_node], "edges": [*graph.edges, positive_edge],
    })
    report = score_accuracy(evidence=BarrierEvidence(), gold=_gold(case), delivered_graph=graph)
    assert report.final_score == 0.0


@pytest.mark.parametrize("case, target_id", [
    ("ia5_record", "e_dis"), ("ic3_brief", "e2_T1_to_S2"),
])
@pytest.mark.parametrize("positive", [False, True])
def test_missing_identity_keeps_existing_claim_policy(case, target_id, positive):
    graph = _delivery(case)
    target = next(edge for edge in graph.edges if edge.id == target_id)
    needed = {target.from_node, target.to_node, target.via}
    nodes = [node.model_copy(update={
        "properties": {}, "accessible": True if positive else node.accessible,
    }) for node in graph.nodes if node.id in needed]
    target = target.model_copy(update={"channel": None, "accessible": positive})
    graph = GoldMechanismGraph(nodes=nodes, edges=[target])
    report = score_accuracy(evidence=BarrierEvidence(), gold=_gold(case), delivered_graph=graph)
    assert report.final_score == (0.0 if positive else 1.0)


@pytest.mark.parametrize("case, unknown_id", [
    ("ia5_record", "e_con"), ("ic3_brief", "e1_T1_to_S1"),
])
def test_unlabelled_positive_candidate_is_not_assumed_to_be_another_target(case, unknown_id):
    graph = _delivery(case)
    unknown = next(edge for edge in graph.edges if edge.id == unknown_id)
    graph = graph.model_copy(update={
        "edges": [edge.model_copy(update={"channel": None}) if edge.id == unknown_id else edge
                  for edge in graph.edges],
        "nodes": [node.model_copy(update={"properties": {}}) if node.id == unknown.to_node else node
                  for node in graph.nodes],
    })
    report = score_accuracy(evidence=BarrierEvidence(), gold=_gold(case), delivered_graph=graph)
    assert report.final_score == 0.0


def _l2_evidence(graph, *, same_ts=True):
    nodes = {node.id: node for node in graph.nodes}
    return BarrierEvidence(steps=[StepBarrier(
        edge_id=edge.id,
        ts_path="same_native_ts.log" if same_ts else f"{edge.id}_native_ts.log",
        base_path=f"{edge.from_node}_minimum.log", base_node_id=edge.from_node,
        barrier_kcal_mol=(nodes[edge.via].properties["energy_hartree"]
                          - nodes[edge.from_node].properties["energy_hartree"])
                         * HARTREE_TO_KCAL_MOL,
        declared_kcal_mol=edge.barrier_kcal_mol,
    ) for edge in graph.edges])


@pytest.mark.parametrize("renamed", [False, True])
def test_same_native_ts_uses_the_stable_reference_already_delivered(renamed):
    graph = _delivery("l2_standard")
    if renamed:
        graph = _rename(graph)
    report = score_accuracy(
        evidence=_l2_evidence(graph), gold=_gold("l2_standard"), delivered_graph=graph,
    )
    expected_barrier = (-233.203414229 - (-233.248473327)) * HARTREE_TO_KCAL_MOL
    assert report.final_score == pytest.approx(gaussian_barrier_score(expected_barrier, 29.77, 3.0))
    assert report.final_score == pytest.approx(0.883232993851)
    assert not report.fail_loud


def test_stable_reference_selection_does_not_use_agreement_with_the_gold_number():
    graph = _delivery("l2_standard")
    gold = _gold("l2_standard")
    edge = gold.mechanism_graph.edges[0].model_copy(update={"barrier_kcal_mol": 18.99})
    gold = gold.model_copy(update={
        "mechanism_graph": gold.mechanism_graph.model_copy(update={"edges": [edge]}),
    })
    report = score_accuracy(evidence=_l2_evidence(graph), gold=gold, delivered_graph=graph)
    assert report.final_score == pytest.approx(0.7)


def test_stable_reference_does_not_pool_different_native_transition_states():
    graph = _delivery("l2_standard")
    report = score_accuracy(
        evidence=_l2_evidence(graph, same_ts=False), gold=_gold("l2_standard"), delivered_graph=graph,
    )
    # Different TS groups retain the existing deterministic edge ordering.
    assert report.final_score == pytest.approx(0.7)


def test_unspecified_reference_keeps_existing_edge_order():
    graph = _delivery("l2_standard")
    gold = _gold("l2_standard")
    edge = gold.mechanism_graph.edges[0].model_copy(update={"barrier_reference_policy": None})
    gold = gold.model_copy(update={
        "mechanism_graph": gold.mechanism_graph.model_copy(update={"edges": [edge]}),
    })
    report = score_accuracy(evidence=_l2_evidence(graph), gold=gold, delivered_graph=graph)
    assert report.final_score == pytest.approx(0.7)


def test_reference_strategy_survives_task_json_round_trip():
    gold = _gold("l2_standard")
    reloaded = GoldSpec.model_validate_json(gold.model_dump_json(by_alias=True))
    assert reloaded.mechanism_graph.edges[0].barrier_reference_policy == "lowest_verified_minimum"


@pytest.mark.parametrize("explanation", [
    "chan_syn/rc/rc_cand01.log",
    {
        "TS": -233.203414267, "RC": -233.233672607,
        "log_TS": "ts/ts_0001/jobs/declaration_0003/frequency/.cloudra/execution-457/results/frequency.log",
        "log_RC": "endpoint_combined/.cloudra/execution-510/results/reactant_optfreq.log",
    },
])
def test_historical_reference_explanation_does_not_become_a_scoring_policy(explanation):
    # These free-form values appeared in Guided HF1/L2. They are delivery
    # explanations, while the reference policy is a separate Gold field.
    raw = json.loads((FIXTURES / "l2_standard.json").read_text())
    for edge in raw["edges"]:
        edge["barrier_reference"] = explanation
    graph = parse_delivered_graph(raw)
    assert all(edge.barrier_reference_policy is None for edge in graph.edges)
    report = score_accuracy(
        evidence=_l2_evidence(graph), gold=_gold("l2_standard"), delivered_graph=graph,
    )
    assert report.final_score == pytest.approx(0.883232993851)


def _positive_identity_pair(case, matching):
    """Isolate identity from accessibility, bindings, and scientific evidence.

    Both compared claims are made positive in this controlled matching test;
    this does not revise the original fixtures' actual negative conclusions.
    """
    graph = _delivery(case)
    target, alternative = {
        "ia5_record": ("e_dis", "e_con"),
        "ic3_brief": ("e2_T1_to_S2", "e1_T1_to_S1"),
    }[case]
    selected = next(edge for edge in graph.edges if edge.id == (target if matching else alternative))
    needed = {selected.from_node, selected.to_node, selected.via}
    delivered = GoldMechanismGraph(
        nodes=[node.model_copy(update={"accessible": True})
               for node in graph.nodes if node.id in needed],
        edges=[selected.model_copy(update={"accessible": True})],
    )
    gold = _gold(case).mechanism_graph
    gold = gold.model_copy(update={
        "nodes": [node.model_copy(update={"accessible": True}) for node in gold.nodes],
        "edges": [edge.model_copy(update={"accessible": True}) for edge in gold.edges],
    })
    return gold, _rename(delivered)


@pytest.mark.parametrize("case", ["ia5_record", "ic3_brief"])
@pytest.mark.parametrize("matching", [True, False])
def test_graph_coverage_requires_the_requested_positive_channel_or_state(case, matching):
    gold, delivered = _positive_identity_pair(case, matching)
    result = mechanism_similarity(delivered, gold)
    if matching:
        assert result.score == 1.0
    else:
        assert result.score < 1.0
        assert result.distance > 0.0


@pytest.mark.parametrize("case", ["ia5_record", "ic3_brief"])
@pytest.mark.parametrize("matching", [True, False])
def test_gold_subgraph_sc_does_not_substitute_a_different_positive_target(case, matching):
    gold, delivered = _positive_identity_pair(case, matching)
    # A controlled edge score isolates which edge the variant includes; it does
    # not manufacture a TS/IRC or minimum-evidence result.
    report = SelfConsistencyReport(checks=[ElementCheck(
        element_id=delivered.edges[0].id, kind="edge", score=1.0, covered=True,
    )])
    assert gold_subgraph_selfconsistency(report, delivered, gold) == (1.0 if matching else 0.0)


def test_negative_state_does_not_reject_a_number_explicitly_on_another_state():
    graph = _delivery("ic3_brief")
    graph = graph.model_copy(update={"nodes": [
        node.model_copy(update={"properties": {
            **node.properties, "singlet_triplet_gap_kcal_mol": 45.9,
        }}) if node.id == "S1_1A1" else node for node in graph.nodes
    ]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=_gold("ic3_brief"), delivered_graph=graph)
    assert report.final_score == 1.0


@pytest.mark.parametrize("node_id", ["T1_3A2", "S2_1A2"])
def test_negative_state_rejects_a_trusted_target_gap_on_either_endpoint(node_id):
    graph = _delivery("ic3_brief")
    graph = graph.model_copy(update={"nodes": [
        node.model_copy(update={"properties": {
            **node.properties, "singlet_triplet_gap_kcal_mol": 12.0,
        }}) if node.id == node_id else node for node in graph.nodes
    ]})
    report = score_accuracy(evidence=BarrierEvidence(), gold=_gold("ic3_brief"), delivered_graph=graph)
    assert report.final_score == 0.0
