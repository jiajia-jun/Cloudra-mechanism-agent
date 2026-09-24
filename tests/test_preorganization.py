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


@pytest.mark.parametrize("filter_row, pair", [
    ({"atoms": [3, 10], "min_ang": 0.1, "max_ang": 0.2}, "3-10"),
    ({"atoms": [1, 2], "min_ang": 5.0, "max_ang": 6.0}, "1-2"),
])
def test_multicomponent_impossible_windows_fail_before_assembly(tmp_path, monkeypatch, filter_row, pair):
    import cloudra.tools.core.preorganization as preorganization

    original = preorganization.prepare_structure
    embedded = []

    def capture(request):
        if request.strategy.embed:
            embedded.append(request)
        return original(request)

    monkeypatch.setattr(preorganization, "prepare_structure", capture)
    with pytest.raises(ValueError, match=pair):
        search_guided(
            structure=StructureInput(kind="smiles", value="CCO.O"),
            output_dir=str(tmp_path / pair), ring_order=[1, 2, 3, 10],
            distance_filters=[filter_row],
        )
    assert embedded == []


def test_guided_multicomponent_search_qualifies_all_ring_and_extra_distances(tmp_path):
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCO.O"),
        output_dir=str(tmp_path / "complex"),
        ring_order=[1, 2, 3, 10],
        distance_filters=[
            {"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [10, 1], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [2, 10], "min_ang": 2.5, "max_ang": 3.8},
        ],
        random_seed=42,
    )
    assert result.status == "ok" and result.candidates
    atoms = read_xyz_atoms(result.candidates[0].xyz_path)
    positions = [position for _symbol, position in atoms]
    assert 2.5 <= math.dist(positions[2], positions[9]) <= 3.8
    assert 2.5 <= math.dist(positions[9], positions[0]) <= 3.8
    assert 2.5 <= math.dist(positions[1], positions[9]) <= 3.8
    assert len(result.candidates[0].achieved_distances) == 3


def test_guided_complex_qualifies_before_heavy_atom_clustering(tmp_path, monkeypatch):
    import cloudra.tools.core.preorganization as preorganization

    calls = 0

    def only_fourth(plan, _graph, _symbols, positions):
        nonlocal calls
        calls += 1
        distances = preorganization.measure_windows(plan, positions)
        return calls == 4, ([] if calls == 4 else ["simulated topology rejection"]), distances

    monkeypatch.setattr(preorganization, "qualify_geometry", only_fourth)
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCO.O"),
        output_dir=str(tmp_path / "late_qualifier"), ring_order=[1, 2, 3, 10],
        distance_filters=[
            {"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [1, 10], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [2, 10], "min_ang": 2.5, "max_ang": 3.8},
        ],
    )
    assert calls >= 4
    assert result.status == "ok" and len(result.candidates) == 1
    assert result.counts["qualified"] == 1


def test_multicomponent_fallback_is_visible_even_when_no_seed_qualifies(tmp_path):
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCO.O"),
        output_dir=str(tmp_path / "fallback"),
        ring_order=[1, 2, 3, 10],
        distance_filters=[{"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8}],
        random_seed=42,
    )
    assert result.status in ("ok", "no_candidate")
    assert {"atoms": [1, 10], "min_ang": 1.8, "max_ang": 2.6,
            "source": "fallback"} in result.effective_windows
    assert "1-10" in result.message and "1.8" in result.message
    if result.status == "no_candidate":
        assert result.diagnostics


def test_failed_multicomponent_search_keeps_closest_attempt_and_distances(tmp_path, monkeypatch):
    import cloudra.tools.core.preorganization as preorganization

    def reject_all(plan, _graph, _symbols, positions):
        return False, ["simulated topology rejection"], preorganization.measure_windows(plan, positions)

    monkeypatch.setattr(preorganization, "qualify_geometry", reject_all)
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCO.O"),
        output_dir=str(tmp_path / "impossible_complex"),
        ring_order=[1, 2, 3, 10],
        distance_filters=[
            {"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [1, 10], "min_ang": 2.5, "max_ang": 3.8},
        ],
    )
    assert result.status == "no_candidate"
    assert Path(result.closest_path).is_file()
    assert any("closest achieved distances" in item and "3-10" in item
               for item in result.diagnostics)


def test_guided_assembly_failure_reads_closest_persisted_trajectory(tmp_path, monkeypatch):
    import cloudra.tools.core.complex_assembly as assembly

    def unconverged(mol, conf_id, writer, _parameters, **_kwargs):
        writer.append(0, assembly._positions(mol, conf_id), 0.0, None)
        return False, False, ""

    monkeypatch.setattr(assembly, "_relax_with_trajectory", unconverged)
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCO.O"),
        output_dir=str(tmp_path / "all_unconverged"), ring_order=[1, 2, 3, 10],
        distance_filters=[{"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8}],
    )
    assert result.status == "no_candidate"
    assert Path(result.closest_path).is_file()
    assert any("closest achieved distances" in item for item in result.diagnostics)


def test_failed_single_component_relaxation_keeps_closest_embedding(tmp_path, monkeypatch):
    from rdkit.Chem import AllChem

    monkeypatch.setattr(AllChem, "MMFFGetMoleculeForceField", lambda *_a, **_k: None)
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCC"),
        output_dir=str(tmp_path / "failed_relaxation"),
        ring_order=[1, 2, 3], distance_filters=[], num_confs=6,
    )
    assert result.status == "no_candidate"
    assert Path(result.closest_path).is_file()
    assert any("closest achieved distances" in item for item in result.diagnostics)


@pytest.mark.parametrize("variant", ["ok", "wrong_symbol", "out_of_window", "engine_failed"])
def test_guided_crest_keeps_constraints_and_qualifies_every_frame(tmp_path, monkeypatch, variant):
    import cloudra.tools.core.preorganization as preorganization
    from cloudra.tools.core.crest_runner import CrestConformer, CrestRunResult

    observed = {}

    def fake_run(request):
        observed["constraint_text"] = request.constraint_text
        observed["runtype"] = request.runtype
        rows = [line.split() for line in request.xyz_text.splitlines()[2:]]
        symbols = [row[0] for row in rows]
        positions = [[float(value) for value in row[1:4]] for row in rows]
        if variant == "wrong_symbol":
            symbols[0] = "F"
        if variant == "out_of_window":
            positions[5][0] += 20.0
        return CrestRunResult(
            run_dir=str(tmp_path / "fake_crest"), scientific_success=variant != "engine_failed",
            termination_reason="unknown_failure" if variant == "engine_failed" else "completed",
            conformers=[CrestConformer(frame_index=0, energy_eh=-1.0,
                                       positions=positions, symbols=symbols)],
        )

    monkeypatch.setattr(preorganization, "run_crest", fake_run)
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCCCCC"),
        output_dir=str(tmp_path / variant), ring_order=[1, 2, 3, 4, 5, 6],
        distance_filters=[
            {"atoms": [1, 6], "min_ang": 3.5, "max_ang": 4.0},
            {"atoms": [2, 5], "min_ang": 3.2, "max_ang": 4.0},
        ], backend="crest", mode="conformers", num_confs=50,
    )
    assert observed["runtype"] == "default"
    assert "force constant=0.02" in observed["constraint_text"]
    assert "distance: 1, 6" in observed["constraint_text"]
    assert any(row["source"] == "bonded_ring_edge" for row in result.constraint_targets)
    assert result.status == ("ok" if variant == "ok" else
                             "engine_failed" if variant == "engine_failed" else "no_candidate")
    assert bool(result.candidates) is (variant == "ok")
    assert Path(result.manifest_path).is_file()


def test_guided_crest_nci_uses_qualified_multicomponent_seed(tmp_path, monkeypatch):
    import cloudra.tools.core.preorganization as preorganization
    from cloudra.tools.core.crest_runner import CrestConformer, CrestRunResult

    def fake_run(request):
        assert request.runtype == "nci" and request.noreftopo
        assert "distance: 3, 10" in request.constraint_text
        rows = [line.split() for line in request.xyz_text.splitlines()[2:]]
        return CrestRunResult(
            run_dir=str(tmp_path / "fake_nci"), scientific_success=True,
            termination_reason="completed",
            conformers=[CrestConformer(frame_index=0, energy_eh=-1.0,
                                       symbols=[row[0] for row in rows],
                                       positions=[[float(v) for v in row[1:4]] for row in rows])],
        )

    monkeypatch.setattr(preorganization, "run_crest", fake_run)
    result = search_guided(
        structure=StructureInput(kind="smiles", value="CCO.O"),
        output_dir=str(tmp_path / "nci"), ring_order=[1, 2, 3, 10],
        distance_filters=[
            {"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [1, 10], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [2, 10], "min_ang": 2.5, "max_ang": 3.8},
        ], backend="crest", mode="nci",
    )
    assert result.status == "ok" and result.candidates
