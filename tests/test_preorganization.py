"""Prospective-cycle guidance uses the resolved full-atom builder order."""

import json
import math
from pathlib import Path

import pytest

pytest.importorskip("rdkit", reason="preorganization requires RDKit (chem extra)")

from cloudra.tools.core.complex_assembly import AssemblyParameters
from cloudra.tools.core.preorganization import (
    effective_window_rows,
    load_resolved_graph,
    qualify_geometry,
    resolve_guidance,
    search_guided,
)
from cloudra.tools.core.structure_artifacts import read_xyz_atoms
from cloudra.tools.core.structure_builder import (
    BuildStrategy,
    PreparationRequest,
    StructureInput,
    prepare_structure,
)


def _graph_only(smiles, tmp_path):
    return prepare_structure(PreparationRequest(
        structure=StructureInput(kind="smiles", value=smiles),
        output_dir=str(tmp_path / "resolved"),
        strategy=BuildStrategy(embed=False, optimize=False),
    ))


def test_missing_ring_edge_uses_visible_single_source_fallback(tmp_path):
    prepared = _graph_only("CCO.O", tmp_path)
    assert prepared.status == "assembly_failed"  # graph-only, not a failed parse
    assert len(prepared.atom_identities) == 12

    plan = resolve_guidance(prepared, [1, 2, 3, 10], [
        {"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8},
    ])

    assert plan.forming_pairs == ((2, 9), (0, 9))
    assert [(w.atoms, w.source) for w in plan.windows] == [
        ((2, 9), "explicit"), ((0, 9), "fallback"),
    ]
    assert (plan.windows[1].min_ang, plan.windows[1].max_ang) == (
        AssemblyParameters().reaction_center_window
    )
    assert {"atoms": [1, 10], "min_ang": 1.8, "max_ang": 2.6,
            "source": "fallback"} in effective_window_rows(plan)


@pytest.mark.parametrize("bad_window", [
    {"atoms": [10, 1], "min_ang": 0, "max_ang": 2.6},
    {"atoms": [10, 1], "min_ang": 3.0, "max_ang": 2.6},
    {"atoms": [10, 1], "min_ang": math.nan, "max_ang": 2.6},
])
def test_invalid_explicit_ring_edge_fails_instead_of_using_fallback(tmp_path, bad_window):
    prepared = _graph_only("CCO.O", tmp_path)
    with pytest.raises(ValueError) as exc:
        resolve_guidance(prepared, [1, 2, 3, 10], [bad_window])
    assert "1" in str(exc.value) and "10" in str(exc.value)
    assert "1=C" in str(exc.value) and "10=O" in str(exc.value)


@pytest.mark.parametrize("smiles,ring", [
    ("CCO.O", [1, 2, 1]),
    ("CCO.O", [1, 2, 99]),
    ("C1CC1", [1, 2, 3]),
])
def test_invalid_ring_order_fails_with_numbered_atoms(tmp_path, smiles, ring):
    prepared = _graph_only(smiles, tmp_path)
    with pytest.raises(ValueError) as exc:
        resolve_guidance(prepared, ring, [])
    assert "1=C" in str(exc.value)


def test_conflicting_duplicate_windows_fail(tmp_path):
    prepared = _graph_only("CCO.O", tmp_path)
    with pytest.raises(ValueError, match="conflict") as exc:
        resolve_guidance(prepared, [1, 2, 3, 10], [
            {"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [10, 3], "min_ang": 2.6, "max_ang": 3.8},
        ])
    assert "3=O" in str(exc.value) and "10=O" in str(exc.value)


def test_builder_identity_mismatch_is_not_silently_reindexed(tmp_path):
    prepared = _graph_only("CCO.O", tmp_path)
    prepared.atom_identities[0].symbol = "F"
    with pytest.raises(ValueError, match="element"):
        load_resolved_graph(prepared)


def test_guided_rdkit_persists_qualified_intramolecular_seeds(tmp_path):
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCCCCC"),
        output_dir=str(tmp_path / "guided"),
        ring_order=[1, 2, 3, 4, 5, 6],
        distance_filters=[
            {"atoms": [1, 6], "min_ang": 3.5, "max_ang": 4.0},
            {"atoms": [2, 5], "min_ang": 3.2, "max_ang": 4.0},
        ],
        num_confs=50,
        random_seed=42,
    )
    assert result.status == "ok" and result.candidates
    assert all(candidate.seed_kind == "constrained_preorganization"
               for candidate in result.candidates)
    assert all(Path(candidate.xyz_path).is_file() and Path(candidate.mol_path).is_file()
               for candidate in result.candidates)

    atoms = read_xyz_atoms(result.candidates[0].xyz_path)
    positions = [position for _, position in atoms]
    assert 3.5 <= math.dist(positions[0], positions[5]) <= 4.0
    assert 3.2 <= math.dist(positions[1], positions[4]) <= 4.0
    prepared = _graph_only("CCCCCC", tmp_path / "independent")
    plan = resolve_guidance(prepared, [1, 2, 3, 4, 5, 6], [
        {"atoms": [1, 6], "min_ang": 3.5, "max_ang": 4.0},
        {"atoms": [2, 5], "min_ang": 3.2, "max_ang": 4.0},
    ])
    passed, reasons, _distances = qualify_geometry(
        plan, load_resolved_graph(prepared), [symbol for symbol, _ in atoms], positions,
    )
    assert passed, reasons

    manifest = json.loads(Path(result.manifest_path).read_text())
    assert {row["source"] for row in manifest["effective_windows"]} == {"explicit"}
    assert manifest["seed_kind"] == "constrained_preorganization"
    assert manifest["mmff_force_constant"] == 100.0
    assert "boltzmann_pct" not in manifest
    assert "rel_energy_kcal" not in manifest


def test_guided_search_with_zero_qualified_seeds_fails_with_nearest_geometry(
    tmp_path, monkeypatch,
):
    import cloudra.tools.core.preorganization as preorganization

    def reject_all(plan, graph, symbols, positions):
        _passed, _reasons, distances = qualify_geometry(plan, graph, symbols, positions)
        return False, ["first rejection", "second rejection"], distances

    monkeypatch.setattr(preorganization, "qualify_geometry", reject_all)
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCC"),
        output_dir=str(tmp_path / "no_match"),
        ring_order=[1, 2, 3], distance_filters=[], num_confs=12,
    )
    assert result.status == "no_candidate"
    assert result.candidates == []
    assert Path(result.closest_path).is_file()
    assert result.counts["rejected"] == result.counts["optimized"]
    assert any("first rejection" in diagnostic for diagnostic in result.diagnostics)
    assert any("second rejection" in diagnostic for diagnostic in result.diagnostics)
    assert result.diagnostics and "1-3" in result.message


def test_impossible_guided_bounds_fail_before_embedding(tmp_path, monkeypatch):
    from rdkit.Chem import AllChem

    def embedding_must_not_run(*_args, **_kwargs):
        raise AssertionError("impossible bounds reached EmbedMultipleConfs")

    monkeypatch.setattr(AllChem, "EmbedMultipleConfs", embedding_must_not_run)
    with pytest.raises(ValueError, match="1-2"):
        search_guided(
            structure=StructureInput(kind="smiles", value="CCC"),
            output_dir=str(tmp_path / "impossible"),
            ring_order=[1, 2, 3],
            distance_filters=[
                {"atoms": [1, 2], "min_ang": 5.0, "max_ang": 6.0},
                {"atoms": [2, 3], "min_ang": 1.4, "max_ang": 1.6},
                {"atoms": [1, 3], "min_ang": 1.8, "max_ang": 2.2},
            ],
        )
