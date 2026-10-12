"""Dependency failures must not be scored as missing molecular evidence."""

import builtins
from types import SimpleNamespace

import pytest

from cloudra.benchmark.integrity import EvidenceFile, bind_graph_to_evidence
from cloudra.benchmark.schema import GoldMechanismGraph, MechanismNode, NodeRole
from cloudra.dag import file_science

_WATER_COORDINATES = "O 0.0 0.0 0.0\nH 0.9572 0.0 0.0\nH -0.2390 0.9270 0.0\n"


def _binding_input(tmp_path, gate, *, smiles="O", coordinates=_WATER_COORDINATES):
    path = tmp_path / "species.out"
    path.write_text(
        "O   R   C   A\nCARTESIAN COORDINATES (ANGSTROEM)\n"
        "---------------------------------\n" + coordinates +
        "\nORCA TERMINATED NORMALLY\n"
    )
    explicit = gate == "explicit-reference"
    graph = GoldMechanismGraph(nodes=[MechanismNode(
        id="R", role=NodeRole.REACTANT, smiles=[smiles],
        properties={"evidence_log": path.name} if explicit else {},
    )], edges=[])
    files = [EvidenceFile(
        path=path.name, kind="orca", size=path.stat().st_size,
        smiles_found=[] if explicit else [smiles],
    )]
    return graph, files


@pytest.mark.parametrize("gate", ["annotation", "explicit-reference"])
@pytest.mark.parametrize("broken_import", ["rdkit", "rdkit.Chem"])
def test_rdkit_import_failure_escapes_both_binding_gates(tmp_path, monkeypatch, gate, broken_import):
    graph, files = _binding_input(tmp_path, gate)
    original_import = builtins.__import__
    import_error = (
        ModuleNotFoundError("No module named 'rdkit'", name="rdkit")
        if broken_import == "rdkit" else
        ImportError("Cannot load the RDKit bond-perception extension")
    )

    def broken_rdkit(name, *args, **kwargs):
        if name == broken_import:
            raise import_error
        if name == "rdkit":
            # Simulate a partially installed package even in a no-RDKit environment.
            return SimpleNamespace(Chem=object())
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_rdkit)
    with pytest.raises(RuntimeError) as raised:
        bind_graph_to_evidence(graph, files, sandbox=tmp_path)

    assert raised.value.__cause__ is import_error
    assert "RDKit" in str(raised.value)
    assert "cloudra[chem]" in str(raised.value)


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize("gate", ["annotation", "explicit-reference"])
@pytest.mark.parametrize("smiles,coordinates,matched", [
    ("O", _WATER_COORDINATES, True),
    ("C", _WATER_COORDINATES, False),
    ("invalid", _WATER_COORDINATES, False),
    ("O", "", False),
], ids=["valid", "composition-mismatch", "invalid-smiles", "missing-geometry"])
def test_geometry_binding_outcomes_are_preserved(tmp_path, gate, smiles, coordinates, matched):
    graph, files = _binding_input(tmp_path, gate, smiles=smiles, coordinates=coordinates)

    binding, = bind_graph_to_evidence(graph, files, sandbox=tmp_path)

    assert binding.matched is matched
    assert binding.quality == (1.0 if matched else 0.0)
    assert binding.bound_files == (["species.out"] if matched else [])


@pytest.mark.parametrize("gate", ["annotation", "explicit-reference"])
def test_geometry_runtime_error_still_rejects_evidence(tmp_path, monkeypatch, gate):
    graph, files = _binding_input(tmp_path, gate)

    def unusable_geometry(*args, **kwargs):
        raise RuntimeError("Bond perception failed for this geometry")

    monkeypatch.setattr(file_science, "_geometry_species", unusable_geometry)

    binding, = bind_graph_to_evidence(graph, files, sandbox=tmp_path)

    assert not binding.matched
    assert binding.quality == 0.0
    assert binding.bound_files == []
