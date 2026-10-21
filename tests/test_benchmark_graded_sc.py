"""Scorer-only tests for graded, discovery-based self-consistency."""

from __future__ import annotations

from pathlib import Path

import pytest

from cloudra.benchmark.accuracy import score_accuracy
from cloudra.benchmark.barrier_evidence import BarrierEvidence, StepBarrier
from cloudra.benchmark.evidence_search import LogFact, discover_edge_proof
from cloudra.benchmark.runner import HARTREE_TO_KCAL_MOL, derived_barrier_graph
from cloudra.benchmark.schema import (
    AccuracyRubric,
    GoldMechanismGraph,
    GoldSpec,
    MechanismEdge,
    MechanismNode,
    NodeRole,
    SelfConsistencyRubric,
)
from cloudra.benchmark.selfconsistency import audit_self_consistency


def _edge(edge_id: str, source: str, target: str, **kwargs) -> MechanismEdge:
    return MechanismEdge(id=edge_id, **{"from": source, "to": target}, **kwargs)


def _energy_node(node_id: str, role: NodeRole, energy: float) -> MechanismNode:
    return MechanismNode(id=node_id, role=role, smiles=[], properties={"energy_hartree": energy})


class _StubEvidence:
    """Duck-typed SandboxEvidence for discovery tests (no sandbox IO)."""

    def __init__(self, logs, ircs=()):
        self.logs = list(logs)
        self._ircs = list(ircs)
        self._opt = {}

    def by_energy(self, energy, tol: float = 1e-6):
        if energy is None:
            return []
        return [f for f in self.logs if f.energy is not None and abs(f.energy - energy) < tol]

    def irc_logs(self):
        return self._ircs

    def optimizations(self, fact):
        return self._opt.get(fact.path)


def test_derived_barrier_fills_missing_edge_from_node_energies():
    graph = GoldMechanismGraph(
        nodes=[
            _energy_node("R", NodeRole.REACTANT, -10.0),
            _energy_node("TS", NodeRole.TRANSITION_STATE, -9.9),
            _energy_node("P", NodeRole.PRODUCT, -10.2),
        ],
        edges=[_edge("e1", "R", "P", via="TS")],
    )
    derived = derived_barrier_graph(graph)
    assert derived.edges[0].barrier_kcal_mol == pytest.approx(
        0.1 * HARTREE_TO_KCAL_MOL, abs=1e-6)
    assert graph.edges[0].barrier_kcal_mol is None


def test_derived_barrier_keeps_declared_value():
    graph = GoldMechanismGraph(
        nodes=[
            _energy_node("R", NodeRole.REACTANT, -10.0),
            _energy_node("TS", NodeRole.TRANSITION_STATE, -9.9),
            _energy_node("P", NodeRole.PRODUCT, -10.2),
        ],
        edges=[_edge("e1", "R", "P", via="TS", barrier_kcal_mol=7.5)],
    )
    assert derived_barrier_graph(graph).edges[0].barrier_kcal_mol == pytest.approx(7.5)


def test_passthrough_self_consistency_scores_full(tmp_path):
    graph = GoldMechanismGraph(
        nodes=[_energy_node("R", NodeRole.REACTANT, -1.0),
               _energy_node("P", NodeRole.PRODUCT, -2.0)],
        edges=[_edge("e1", "R", "P")],
    )
    rubric = SelfConsistencyRubric(
        ts_first_order_saddle=False, irc_connects_endpoints=False)
    report = audit_self_consistency(graph, [], [], tmp_path, rubric, charge=0)
    assert report.passed is True
    assert report.score == pytest.approx(1.0)


def test_declared_inaccessible_edge_scores_full(tmp_path):
    graph = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=[], accessible=False),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=[], accessible=False),
        ],
        edges=[_edge("e1", "R", "P", accessible=False)],
    )
    report = audit_self_consistency(graph, [], [], tmp_path, SelfConsistencyRubric(), charge=0)
    edge_checks = [c for c in report.checks if c.kind == "edge"]
    assert edge_checks and edge_checks[0].score == pytest.approx(1.0)
    assert report.passed is True


def test_discovery_refuses_to_substitute_an_unrelated_saddle():
    graph = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C"]),
            _energy_node("TS", NodeRole.TRANSITION_STATE, -5.0),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["O"]),
        ],
        edges=[_edge("e1", "R", "P", via="TS")],
    )
    other_saddle = LogFact(
        path=Path("other_ts.log"), energy=-9.0, n_imag=1,
        geometry=(["C"], [(0.0, 0.0, 0.0)]), job_types={"freq"}, normal=True)
    result = discover_edge_proof(_StubEvidence([other_saddle]), graph, graph.edges[0])
    assert result.passed is False
    assert result.score == 0.0
    assert any("refusing to substitute" in note for note in result.notes)


def test_discovery_credit_is_saddle_plus_irc_start_only():
    frame = (["C"], [(0.0, 0.0, 0.0)])
    saddle = LogFact(path=Path("ts.log"), energy=-5.0, n_imag=1, geometry=frame,
                     job_types={"freq"}, normal=True)
    irc = LogFact(path=Path("irc.log"), energy=None, n_imag=None, geometry=frame,
                  job_types={"irc"}, normal=True)
    graph = GoldMechanismGraph(
        nodes=[
            MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C"]),
            _energy_node("TS", NodeRole.TRANSITION_STATE, -5.0),
            MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["O"]),
        ],
        edges=[_edge("e1", "R", "P", via="TS")],
    )
    result = discover_edge_proof(
        _StubEvidence([saddle], ircs=[(irc, frame, (frame, frame))]), graph, graph.edges[0])
    assert result.passed is False
    assert result.score == pytest.approx(0.35 + 0.15)


def test_one_delivered_step_cannot_cover_two_gold_edges():
    nodes = [
        MechanismNode(id="R", role=NodeRole.REACTANT, smiles=["C"]),
        MechanismNode(id="P", role=NodeRole.PRODUCT, smiles=["O"]),
    ]
    gold = GoldSpec(mechanism_graph=GoldMechanismGraph(
        nodes=nodes,
        edges=[
            _edge("G1", "R", "P", barrier_kcal_mol=23.0),
            _edge("G2", "R", "P", barrier_kcal_mol=30.0),
        ],
    ))
    delivered = GoldMechanismGraph(
        nodes=nodes,
        edges=[_edge("d1", "R", "P"), _edge("d2", "R", "P")],
    )
    evidence = BarrierEvidence(steps=[
        StepBarrier(edge_id="d1", ts_path="t1", base_path="b1", base_node_id="R",
                    barrier_kcal_mol=23.0, declared_kcal_mol=23.0),
        StepBarrier(edge_id="d2", ts_path="t2", base_path="b2", base_node_id="R",
                    barrier_kcal_mol=30.0, declared_kcal_mol=30.0),
    ])
    report = score_accuracy(
        evidence=evidence, gold=gold,
        rubric=AccuracyRubric(sigma_kcal_mol=2.0),
        delivered_graph=delivered,
    )
    assert report.edge_scores["G1"] == pytest.approx(1.0)
    assert report.edge_scores["G2"] == pytest.approx(1.0)
    assert report.final_score == pytest.approx(1.0)
