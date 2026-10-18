"""Stable-reference selection on an already bound conformational graph."""

import json

import pytest

from cloudra.benchmark import barrier_evidence, integrity
from cloudra.benchmark.integrity import EvidenceFile, NodeBinding


def _node(node_id, smiles="CCO", **properties):
    return {"id": node_id, "role": "intermediate", "smiles": [smiles], "properties": properties}


def _edge(edge_id, source, target, *, conformational=False):
    return {
        "id": edge_id, "from": source, "to": target,
        "via": None if conformational else "TS",
        "bond_changes": {"break": [], "form": [] if conformational else [[1, 2]]},
    }


def _collect(tmp_path, monkeypatch, nodes, edges, bound, energies):
    graph = {
        "nodes": [*nodes, {"id": "TS", "role": "transition_state", "smiles": []}],
        "edges": edges,
    }
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(graph))
    paths = sorted({path for files in bound.values() for path in files} | {"ts.out"})
    monkeypatch.setattr(barrier_evidence, "scan_evidence_files", lambda *a, **kw: [
        EvidenceFile(path=path, kind="orca") for path in paths
    ])
    monkeypatch.setattr(integrity, "bind_graph_to_evidence", lambda *a, **kw: [
        NodeBinding(node_id=node_id, bound_files=files, matched=True, quality=1.0)
        for node_id, files in {**bound, "TS": ["ts.out"]}.items()
    ])
    monkeypatch.setattr(barrier_evidence, "_frequency_supported", lambda sb, p, files, expected:
                        expected == (1 if p == "ts.out" else 0))
    monkeypatch.setattr(barrier_evidence, "_engine_energy_kcal", lambda sb, p: (energies[p], ""))
    monkeypatch.setattr(barrier_evidence, "_identify_by_declared_energy", lambda sb, paths, declared:
                        next((path for path in paths if declared is not None and
                              energies[path] / barrier_evidence.HARTREE_TO_KCAL_MOL == declared), None))
    return barrier_evidence.collect_barrier_evidence(tmp_path)


def test_stable_minimum_cannot_be_overridden_by_declared_higher_conformer(tmp_path, monkeypatch):
    report = _collect(
        tmp_path, monkeypatch,
        [_node("R", energy_hartree=-10.0 / barrier_evidence.HARTREE_TO_KCAL_MOL), _node("P", "CC=O")],
        [_edge("reaction", "R", "P")],
        {"R": ["deep.out", "shallow.out"]},
        {"deep.out": -30.0, "shallow.out": -10.0, "ts.out": 5.0},
    )
    assert report.steps[0].base_path == "deep.out"
    assert report.steps[0].barrier_kcal_mol == 35.0
    assert {step.base_path for step in report.alternatives["reaction"]} == {"deep.out", "shallow.out"}


def test_reaction_uses_stable_intermediate_across_explicit_conformational_path(tmp_path, monkeypatch):
    pytest.importorskip("rdkit")
    report = _collect(
        tmp_path, monkeypatch,
        [_node("stable"), _node("middle", "OCC"), _node("local"), _node("P", "CC=O")],
        [_edge("rotate1", "stable", "middle", conformational=True),
         _edge("rotate2", "middle", "local", conformational=True),
         _edge("reaction", "local", "P")],
        {"stable": ["stable.out"], "middle": ["middle.out"], "local": ["local.out"]},
        {"stable.out": -30.0, "middle.out": -20.0, "local.out": -10.0, "ts.out": 5.0},
    )
    assert report.steps[0].base_path == "stable.out"
    assert report.steps[0].base_node_id == "stable"
    assert report.steps[0].barrier_kcal_mol == 35.0


def test_separate_channel_contacts_are_not_pooled_by_identical_smiles(tmp_path, monkeypatch):
    report = _collect(
        tmp_path, monkeypatch,
        [_node("exo"), _node("endo"), _node("P", "CC=O")],
        [_edge("reaction", "endo", "P")],
        {"exo": ["exo.out"], "endo": ["endo.out"]},
        {"exo.out": -30.0, "endo.out": -10.0, "ts.out": 5.0},
    )
    assert report.steps[0].base_path == "endo.out"
    assert report.steps[0].barrier_kcal_mol == 15.0


def test_a_conformational_step_keeps_its_local_source_reference(tmp_path, monkeypatch):
    reaction = _edge("rotation", "local", "stable", conformational=True)
    reaction["via"] = "TS"
    report = _collect(
        tmp_path, monkeypatch,
        [_node("stable"), _node("local")], [reaction],
        {"stable": ["stable.out"], "local": ["local.out"]},
        {"stable.out": -30.0, "local.out": -10.0, "ts.out": 5.0},
    )
    assert report.steps[0].base_path == "local.out"
    assert report.steps[0].barrier_kcal_mol == 15.0


def test_conformational_link_cannot_pool_distinct_stereochemical_substrates(tmp_path, monkeypatch):
    pytest.importorskip("rdkit")
    report = _collect(
        tmp_path, monkeypatch,
        [_node("other", "C[C@H](O)N"), _node("source", "C[C@@H](O)N"), _node("P", "CC=O")],
        [_edge("invalid_rotation", "other", "source", conformational=True),
         _edge("reaction", "source", "P")],
        {"other": ["other.out"], "source": ["source.out"]},
        {"other.out": -30.0, "source.out": -10.0, "ts.out": 5.0},
    )
    assert report.steps[0].base_path == "source.out"
    assert report.steps[0].barrier_kcal_mol == 15.0
