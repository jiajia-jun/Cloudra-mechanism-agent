"""Declared open-shell states produce seeds without closed-shell force fields."""

import json
from pathlib import Path

import pytest

pytest.importorskip("rdkit", reason="open-shell structure seeds require RDKit")

from rdkit import Chem  # noqa: E402

import cloudra.tools.Chemtool.conformer_search as conformer_mod  # noqa: E402
import cloudra.tools.core.preorganization as preorganization_mod  # noqa: E402
import cloudra.tools.core.structure_builder as builder_mod  # noqa: E402
from cloudra.tools.Chemtool.conformer_search import (  # noqa: E402
    ConformerSearch,
    ConformerSearch_input_schema,
)
from cloudra.tools.Chemtool.qm_input_writer import (  # noqa: E402
    QmInputWriter,
    QmInputWriter_input_schema,
)
from cloudra.tools.Chemtool.smiles_to_mol import (  # noqa: E402
    SmilesToMol,
    SmilesToMol_input_schema,
)
from cloudra.tools.core.crest_runner import (  # noqa: E402
    CrestConformer,
    CrestRunResult,
    build_crest_command,
)
from cloudra.tools.core.structure_builder import (  # noqa: E402
    BuildStrategy,
    PreparationRequest,
    StructureInput,
    prepare_structure,
)


def _prepare(tmp_path, smiles, multiplicity, *, embed=True, kind="smiles", character=None):
    value = Chem.MolToMolBlock(Chem.MolFromSmiles(smiles)) if kind == "mol_block" else smiles
    return prepare_structure(PreparationRequest(
        structure=StructureInput(kind=kind, value=value), output_dir=str(tmp_path),
        multiplicity=multiplicity, electronic_character=character, strategy=BuildStrategy(embed=embed),
    ))


def _forbidden_force_field(*_args, **_kwargs):
    raise AssertionError("an open-shell seed must not use a closed-shell force field")


@pytest.mark.parametrize("smiles,multiplicity,radicals", [
    ("[CH3]", 2, 1), ("[CH2]", 3, 2), ("[CH2][CH2]", 1, 2),
    ("[CH2][CH2]", 3, 2), ("O=O", 3, 0),
])
def test_declared_open_shell_graphs_resolve_without_force_fields(tmp_path, smiles, multiplicity, radicals):
    prepared = _prepare(tmp_path, smiles, multiplicity, embed=False)
    assert prepared.status == "ok", prepared.message
    assert prepared.has_coordinates is False
    molecule = Chem.MolFromMolFile(prepared.components[0].mol_path, removeHs=False)
    assert sum(atom.GetNumRadicalElectrons() for atom in molecule.GetAtoms()) == radicals
    assert prepared.trajectory_ids == []
    assert prepared.electronic_state["is_open_shell"] is True
    assert prepared.electronic_state["localized_radical_electrons"] == radicals


@pytest.mark.parametrize("kind", ["smiles", "mol_block"])
def test_open_shell_seed_is_embedded_and_explicitly_unoptimized(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(builder_mod, "_select_engine", _forbidden_force_field)
    prepared = _prepare(tmp_path, "[CH3]", 2, kind=kind)
    assert prepared.status == "ok", prepared.message
    assert prepared.has_coordinates is True
    assert prepared.components[0].optimization_status == "skipped_electronic_state"
    assert prepared.components[0].engine == ""
    assert prepared.components[0].final_energy is None
    assert prepared.trajectory_ids == []
    assert prepared.trajectory_manifest_path == ""
    assert "unoptimized" in prepared.message.lower()
    molecule = Chem.MolFromMolFile(prepared.candidate_path(".mol"), removeHs=False)
    assert [atom.GetNumRadicalElectrons() for atom in molecule.GetAtoms()] == [1, 0, 0, 0]
    assert prepared.symbols == ["C", "H", "H", "H"]
    assert len(prepared.atom_identities) == 4
    assert Path(prepared.candidate_path(".xyz")).is_file()
    assert json.loads(Path(prepared.artifact_path).read_text())["components"][0]["final_energy"] is None


@pytest.mark.parametrize("smiles,multiplicity,character", [
    ("[CH2][CH2]", 1, None), ("[CH2][CH2]", 3, None),
    ("O=O", 3, None), ("CC", 1, "open_shell"),
])
def test_open_shell_couplings_skip_force_fields_without_changing_multiplicity(
    tmp_path, monkeypatch, smiles, multiplicity, character,
):
    monkeypatch.setattr(builder_mod, "_select_engine", _forbidden_force_field)
    prepared = _prepare(tmp_path, smiles, multiplicity, character=character)
    assert prepared.status == "ok", prepared.message
    assert prepared.components[0].optimization_status == "skipped_electronic_state"
    assert prepared.electronic_state["multiplicity"] == multiplicity
    assert prepared.electronic_state["is_open_shell"] is True
    assert prepared.trajectory_ids == []


@pytest.mark.parametrize("smiles,multiplicity,character", [
    ("[CH3]", 1, None), ("[CH2][CH2]", 2, None),
    ("O=O", 3, "closed_shell"),
])
def test_invalid_electron_parity_and_contradictory_closed_shell_are_refused(
    tmp_path, smiles, multiplicity, character,
):
    prepared = _prepare(tmp_path, smiles, multiplicity, embed=False, character=character)
    assert prepared.status == "unsupported_spin"
    assert prepared.components == []
    assert prepared.candidate_paths == []


def test_explicit_closed_shell_carbene_is_not_reclassified_and_still_skips_force_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(builder_mod, "_select_engine", _forbidden_force_field)
    prepared = _prepare(tmp_path, "[CH2]", 1, character="closed_shell")
    assert prepared.status == "ok", prepared.message
    assert prepared.electronic_state["electronic_character"] == "closed_shell"
    assert prepared.electronic_state["is_open_shell"] is False
    assert prepared.electronic_state["requires_spin_aware_geometry"] is True
    assert prepared.electronic_state["localized_radical_electrons"] == 2
    assert prepared.components[0].optimization_status == "skipped_electronic_state"
    assert prepared.components[0].final_energy is None
    assert prepared.trajectory_ids == []


def test_radical_multicomponent_graph_resolves_but_force_field_assembly_is_refused(tmp_path, monkeypatch):
    graph = _prepare(tmp_path / "graph", "[CH3].O", 2, embed=False)
    assert graph.status == "assembly_failed"
    assert len(graph.components) == 2
    monkeypatch.setattr(builder_mod, "assemble", _forbidden_force_field)
    monkeypatch.setattr(builder_mod, "_select_engine", _forbidden_force_field)
    prepared = _prepare(tmp_path / "seed", "[CH3].O", 2)
    assert prepared.status == "unsupported_spin"
    assert prepared.has_coordinates is False
    assert prepared.candidate_paths == []
    assert prepared.assembly is None
    assert "MOL" in prepared.message and "XYZ" in prepared.message


@pytest.mark.parametrize("smiles,multiplicity,character", [
    ("[CH3]", 2, None), ("[CH2][CH2]", 1, None), ("CC", 1, "open_shell"),
    ("[CH2]", 1, "closed_shell"),
])
def test_rdkit_energized_ensemble_explicitly_refuses_open_shell(
    tmp_path, monkeypatch, smiles, multiplicity, character,
):
    monkeypatch.setattr(conformer_mod.AllChem, "MMFFOptimizeMoleculeConfs", _forbidden_force_field)
    result = ConformerSearch()._run_rdkit(
        ConformerSearch_input_schema(smiles=smiles, multiplicity=multiplicity, electronic_character=character),
        str(tmp_path),
    )
    assert result.is_success is False
    assert "crest" in result.message.lower()
    assert "force-field" in result.message.lower()
    if multiplicity == 1 and character != "closed_shell":
        assert "qm" in result.message.lower()


@pytest.mark.parametrize("backend", ["rdkit", "crest"])
@pytest.mark.parametrize("smiles,multiplicity,character", [
    ("C[CH]C", 2, None), ("[CH2][CH2]", 1, None), ("CC", 1, "open_shell"),
    ("[CH2]", 1, "closed_shell"),
])
def test_guided_force_field_seed_path_refuses_open_shell(
    tmp_path, monkeypatch, backend, smiles, multiplicity, character,
):
    monkeypatch.setattr(preorganization_mod.AllChem, "MMFFGetMoleculeProperties", _forbidden_force_field)
    result = preorganization_mod.search_guided(
        structure=StructureInput(kind="smiles", value=smiles), output_dir=str(tmp_path),
        ring_order=[], distance_filters=[{"atoms": [1, 3], "min_ang": 2.0, "max_ang": 4.0}],
        multiplicity=multiplicity, electronic_character=character, backend=backend, num_confs=1,
    )
    assert result.status == "build_failed"
    assert "mmff" in result.message.lower()
    assert "MOL" in result.message and "XYZ" in result.message


@pytest.mark.parametrize("smiles,multiplicity,character,uhf", [
    ("[CH3]", 2, None, "1"), ("O=O", 3, None, "2"),
    ("[CH2]", 1, "closed_shell", "0"),
    ("[CH3]", 2, "open_shell", "1"),
])
def test_crest_receives_unoptimized_radical_seed_and_explicit_uhf(
    tmp_path, monkeypatch, smiles, multiplicity, character, uhf,
):
    monkeypatch.setattr(builder_mod, "_select_engine", _forbidden_force_field)
    commands = []

    def external_crest(request):
        assert request.electronic_character == character
        command = build_crest_command(request)
        commands.append(command)
        rows = request.xyz_text.splitlines()[2:]
        symbols = [row.split()[0] for row in rows]
        positions = [[float(value) for value in row.split()[1:4]] for row in rows]
        return CrestRunResult(
            run_dir=str(tmp_path / "crest_run"), command=command, returncode=0,
            scientific_success=True, conformer_count=1,
            conformers=[CrestConformer(frame_index=0, energy_eh=-1.0, positions=positions, symbols=symbols)],
        )

    monkeypatch.setattr(conformer_mod, "run_crest", external_crest)
    result = ConformerSearch()._run_crest(
        ConformerSearch_input_schema(
            smiles=smiles, multiplicity=multiplicity, electronic_character=character, backend="crest",
        ), str(tmp_path),
    )
    assert result.is_success is True, result.message
    assert len(commands) == 1
    assert commands[0][commands[0].index("--uhf") + 1] == uhf
    prepared = json.loads((tmp_path / "structure_build" / "prepared_structure.json").read_text())
    assert prepared["components"][0]["optimization_status"] == "skipped_electronic_state"
    assert prepared["components"][0]["final_energy"] is None
    assert result.counts["generated"] == 1


@pytest.mark.parametrize("smiles,character", [
    ("[CH2][CH2]", None), ("CC", "open_shell"),
])
def test_crest_open_shell_singlet_is_refused_before_external_execution(tmp_path, monkeypatch, smiles, character):
    monkeypatch.setattr(builder_mod, "_select_engine", _forbidden_force_field)
    calls = []

    def forbidden_crest(request):
        calls.append(request)
        raise AssertionError("the CREST runner must not be called for an open-shell singlet")

    monkeypatch.setattr(conformer_mod, "run_crest", forbidden_crest)
    result = ConformerSearch()._run_crest(ConformerSearch_input_schema(
        smiles=smiles, multiplicity=1, electronic_character=character, backend="crest",
    ), str(tmp_path))
    assert result.is_success is False
    assert calls == []
    assert "open-shell singlet" in result.message.lower()
    assert "qm" in result.message.lower()
    prepared = json.loads((tmp_path / "structure_build" / "prepared_structure.json").read_text())
    assert prepared["components"][0]["optimization_status"] == "skipped_electronic_state"


@pytest.mark.parametrize("entrypoint", ["smiles_to_mol", "qm_input_writer"])
def test_public_smiles_seed_entrypoints_forward_explicit_open_shell_singlet(
    tmp_path, monkeypatch, entrypoint,
):
    monkeypatch.setattr(builder_mod, "_select_engine", _forbidden_force_field)
    if entrypoint == "smiles_to_mol":
        result = SmilesToMol()._build_3d(SmilesToMol_input_schema(
            smiles="CC", multiplicity=1, electronic_character="open_shell", generate_3d=True,
            artifact_dir=str(tmp_path),
        ))
        assert result.is_success is True, result.message
        assert result.xyz_path
    else:
        coordinates = QmInputWriter._smiles_coordinates(QmInputWriter_input_schema(
            source_type="smiles", source_value="CC", multiplicity=1,
            electronic_character="open_shell", output_path=str(tmp_path / "seed.inp"),
        ), str(tmp_path))
        assert [line.split()[0] for line in coordinates.splitlines()] == ["C", "C", "H", "H", "H", "H", "H", "H"]
    prepared = json.loads((tmp_path / "prepared_structure.json").read_text())
    assert prepared["electronic_state"]["electronic_character"] == "open_shell"
    assert prepared["components"][0]["optimization_status"] == "skipped_electronic_state"
