"""Fairness regression tests for the D1/D2/D3 scoring fixes (2026-10-29).

These tests are cheap (no QM): geometries are generated with RDKit embedding,
graphs are hand-built, and no benchmark campaign data is read.

D1  node/edge ``accessible`` written inside ``properties`` must be honoured
    (previously read as accessible=true -> zero-evidence penalty -1).
D2  species identity for open-shell / non-Kekule / metal geometries must fall
    back to element+connectivity matching when RDKit bond-order perception
    fails or mis-perceives, while still rejecting genuinely different species.
D3  the gold-subgraph self-consistency variant must ignore extra delivered
    edges beyond the reference and must not change the current rubric score.
"""
from __future__ import annotations

import json

import pytest

from cloudra.benchmark.graph_similarity import mechanism_similarity
from cloudra.benchmark.integrity import audit_integrity, load_delivered_graph
from cloudra.benchmark.selfconsistency import (
    ElementCheck,
    SelfConsistencyReport,
    audit_self_consistency,
    gold_subgraph_selfconsistency,
)
from cloudra.dag.file_science import _geometry_species

pytest.importorskip("rdkit")
from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem  # noqa: E402


# ---------------------------------------------------------------------------
# D1: nested accessible flag is hoisted and flagged
# ---------------------------------------------------------------------------
def _chromium_graph(accessible_inside_properties: bool) -> dict:
    def node(node_id: str, role: str, smiles: str) -> dict:
        if accessible_inside_properties:
            return {"id": node_id, "role": role, "smiles": [smiles],
                    "properties": {"accessible": False}}
        return {"id": node_id, "role": role, "smiles": [smiles],
                "accessible": False}

    edge: dict = {"id": "e1", "from": "R", "to": "P"}
    if accessible_inside_properties:
        edge["properties"] = {"accessible": False}
    else:
        edge["accessible"] = False
    return {
        "nodes": [
            node("R", "reactant", "[Cr][Cr]"),
            node("P", "product", "[Cr].[Cr]"),
        ],
        "edges": [edge],
    }


def test_nested_accessible_flag_is_hoisted_and_scored_as_declared(tmp_path):
    (tmp_path / "mechanism_graph.json").write_text(
        json.dumps(_chromium_graph(accessible_inside_properties=True)))
    delivered = load_delivered_graph(tmp_path / "mechanism_graph.json")
    assert delivered is not None
    assert all(node.accessible is False for node in delivered.nodes)
    assert all(node.accessible_source == "properties" for node in delivered.nodes)
    assert delivered.edges[0].accessible is False
    assert delivered.edges[0].accessible_source == "properties"

    report = audit_integrity(tmp_path)
    assert report.graph_parseable
    assert report.accessible_sources["nodes"] == {"R": False, "P": False}
    assert report.accessible_sources["edges"] == {"e1": False}
    assert any("accessible flag read from nested properties" in note
               for note in report.notes)

    from cloudra.benchmark.schema import GoldMechanismGraph

    gold = GoldMechanismGraph.model_validate(_chromium_graph(accessible_inside_properties=False))
    assert mechanism_similarity(delivered, gold).score == pytest.approx(1.0)


def test_absent_accessible_flag_defaults_to_accessible(tmp_path):
    graph = {"nodes": [{"id": "R", "role": "reactant", "smiles": ["C=O"]}],
             "edges": []}
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(graph))
    delivered = load_delivered_graph(tmp_path / "mechanism_graph.json")
    assert delivered is not None
    assert delivered.nodes[0].accessible is True
    assert delivered.nodes[0].accessible_source == "default"


# ---------------------------------------------------------------------------
# D2: open-shell / non-Kekule geometry identity fallback
# ---------------------------------------------------------------------------
def _embed_xyz(smiles: str, *, seed: int = 42) -> str:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    assert AllChem.EmbedMolecule(mol, params) == 0
    conformer = mol.GetConformer()
    lines = [str(mol.GetNumAtoms()), smiles]
    for atom in mol.GetAtoms():
        pos = conformer.GetAtomPosition(atom.GetIdx())
        lines.append(f"{atom.GetSymbol()} {pos.x:.6f} {pos.y:.6f} {pos.z:.6f}")
    return "\n".join(lines) + "\n"


def _write_xyz(tmp_path, name: str, smiles: str) -> str:
    path = tmp_path / name
    path.write_text(_embed_xyz(smiles))
    return str(path)


def test_radical_nitrene_geometry_identity_via_connectivity_fallback(tmp_path):
    """RDKit DetermineBonds raises for the nitrene N (valence) on real logs too."""
    smiles = "[N]c1ccccc1"
    xyz = _write_xyz(tmp_path, "nitrene.xyz", smiles)
    diagnostics: list[str] = []
    assert _geometry_species(xyz, smiles, diagnostics=diagnostics) is True
    assert any("connectivity fallback" in note for note in diagnostics)


def test_non_kekule_triangulene_geometry_identity_via_connectivity_fallback(tmp_path):
    """Non-Kekule PAH: bond-order perception yields a wrong Kekule structure."""
    smiles = "[CH]1C2=C3C(=CC=C2)[CH]C4=CC=CC5=C4C3=C6C1=CC=CC6=C5"
    xyz = _write_xyz(tmp_path, "triangulene.xyz", smiles)
    diagnostics: list[str] = []
    assert _geometry_species(xyz, smiles, diagnostics=diagnostics) is True


def test_metal_dimer_geometry_identity_via_connectivity_fallback(tmp_path):
    """Cr has no RDKit valence table entry: DetermineBonds raises."""
    smiles = "[Cr][Cr]"
    xyz = _write_xyz(tmp_path, "cr2.xyz", smiles)
    diagnostics: list[str] = []
    assert _geometry_species(xyz, smiles, diagnostics=diagnostics) is True


def test_connectivity_fallback_still_rejects_different_species(tmp_path):
    """Same formula, different connectivity must stay rejected."""
    cyclohexane = "C1CCCCC1"
    hexene = "C=CCCCC"
    from rdkit.Chem import rdMolDescriptors
    assert (rdMolDescriptors.CalcMolFormula(Chem.MolFromSmiles(cyclohexane))
            == rdMolDescriptors.CalcMolFormula(Chem.MolFromSmiles(hexene)))
    xyz = _write_xyz(tmp_path, "cyclohexane.xyz", cyclohexane)
    assert _geometry_species(xyz, hexene) is False


def test_closed_shell_species_path_unchanged(tmp_path):
    smiles = "O"
    xyz = _write_xyz(tmp_path, "water.xyz", smiles)
    assert _geometry_species(xyz, smiles) is True


# ---------------------------------------------------------------------------
# D3: gold-subgraph self-consistency variant
# ---------------------------------------------------------------------------
def _edge_species_graph(extra_edge: bool):
    nodes = [
        {"id": "R", "role": "reactant", "smiles": ["C=O"]},
        {"id": "P", "role": "product", "smiles": ["CO"]},
    ]
    edges = [{"id": "e1", "from": "R", "to": "P",
              "bond_changes": {"break": [[1, 2]], "form": [[1, 3]]}}]
    if extra_edge:
        nodes.append({"id": "Q", "role": "product", "smiles": ["CC"]})
        edges.append({"id": "e2", "from": "R", "to": "Q", "bond_changes": {}})
    return {"nodes": nodes, "edges": edges}


def test_gold_subgraph_selfc_ignores_extra_edges():
    from cloudra.benchmark.schema import GoldMechanismGraph

    gold = GoldMechanismGraph.model_validate(_edge_species_graph(extra_edge=False))
    delivered = GoldMechanismGraph.model_validate(_edge_species_graph(extra_edge=True))
    report = SelfConsistencyReport(
        checks=[
            ElementCheck(element_id="e1", kind="edge", covered=True, score=1.0),
            ElementCheck(element_id="e2", kind="edge", covered=False, score=0.0),
        ],
        score=0.5,
    )
    # extras beyond the reference are not graded -> 1.0 (not the 0.5 all-edges mean)
    assert gold_subgraph_selfconsistency(report, delivered, gold) == pytest.approx(1.0)
    # the current rubric is untouched
    assert report.score == 0.5


def test_gold_subgraph_selfc_vacuous_when_reference_has_no_edges():
    from cloudra.benchmark.schema import GoldMechanismGraph

    gold = GoldMechanismGraph.model_validate(
        {"nodes": [{"id": "R", "role": "reactant", "smiles": ["C=O"]}], "edges": []})
    delivered = GoldMechanismGraph.model_validate(_edge_species_graph(extra_edge=True))
    report = SelfConsistencyReport(
        checks=[ElementCheck(element_id="e2", kind="edge", covered=False, score=0.0)],
        score=0.0,
    )
    assert gold_subgraph_selfconsistency(report, delivered, gold) == pytest.approx(1.0)


def test_gold_subgraph_selfc_zero_when_no_gold_edge_is_covered():
    from cloudra.benchmark.schema import GoldMechanismGraph

    gold = GoldMechanismGraph.model_validate(_edge_species_graph(extra_edge=False))
    delivered = GoldMechanismGraph.model_validate(
        {"nodes": [{"id": "R", "role": "reactant", "smiles": ["C=O"]},
                   {"id": "Q", "role": "product", "smiles": ["CC"]}],
         "edges": [{"id": "e9", "from": "R", "to": "Q", "bond_changes": {}}]})
    report = SelfConsistencyReport(
        checks=[ElementCheck(element_id="e9", kind="edge", covered=False, score=0.0)],
        score=0.0,
    )
    assert gold_subgraph_selfconsistency(report, delivered, gold) == pytest.approx(0.0)


def test_audit_self_consistency_records_gold_subgraph_variant(tmp_path):
    from cloudra.benchmark.schema import GoldMechanismGraph

    delivered = GoldMechanismGraph.model_validate(_edge_species_graph(extra_edge=True))
    gold = GoldMechanismGraph.model_validate(_edge_species_graph(extra_edge=False))
    report = audit_self_consistency(
        delivered, [], [], tmp_path, charge=0,
        integrity_rubric=None, ged_config=None, gold_graph=gold,
    )
    assert report.gold_subgraph_score is not None
    # current rubric behaviour unchanged: no evidence -> score 0
    assert report.score == 0.0
