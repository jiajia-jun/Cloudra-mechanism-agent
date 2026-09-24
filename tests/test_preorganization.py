"""Prospective-cycle guidance uses the resolved full-atom builder order."""

import math

import pytest

pytest.importorskip("rdkit", reason="preorganization requires RDKit (chem extra)")

from cloudra.tools.core.complex_assembly import AssemblyParameters
from cloudra.tools.core.preorganization import (
    effective_window_rows,
    load_resolved_graph,
    resolve_guidance,
)
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
