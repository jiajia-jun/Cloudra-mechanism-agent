"""Species evidence identity: stereochemistry, coordinate frames and xTB."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.dag.evidence_ingest import snapshot_evidence_file
from cloudra.dag.file_science import (
    _geometry_species,
    file_scientific_checks,
    validate_frequency_geometry,
)
from cloudra.dag.models import GraphData, GraphRef, SpeciesNode

np = pytest.importorskip("numpy")
Chem = pytest.importorskip("rdkit.Chem")
AllChem = pytest.importorskip("rdkit.Chem.AllChem")


def _chiral_geometry(smiles="C[C@H](O)C(=O)O"):
    molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(molecule, randomSeed=7) == 0
    AllChem.MMFFOptimizeMolecule(molecule)
    return (
        [atom.GetSymbol() for atom in molecule.GetAtoms()],
        np.asarray(molecule.GetConformer().GetPositions()),
    )


@pytest.mark.parametrize("actual,declared,want", [
    ("C[C@H](O)C(=O)O", "CC(O)C(=O)O", True),
    ("C[C@@H](O)C(=O)O", "CC(O)C(=O)O", True),
    ("C[C@H](O)C(=O)O", "C[C@H](O)C(=O)O", True),
    ("C[C@@H](O)C(=O)O", "C[C@@H](O)C(=O)O", True),
    ("C[C@H](O)C(=O)O", "C[C@@H](O)C(=O)O", False),
    ("C[C@@H](O)C(=O)O", "C[C@H](O)C(=O)O", False),
], ids=["unspecified-a", "unspecified-b", "matching-a", "matching-b", "wrong-a", "wrong-b"])
def test_species_geometry_enforces_only_declared_stereochemistry(monkeypatch, actual, declared, want):
    geometry = _chiral_geometry(actual)
    monkeypatch.setattr("cloudra.dag.file_science.frames_for", lambda _path: ([], None))
    monkeypatch.setattr("cloudra.dag.file_science.last_geometry", lambda _path, _frames: geometry)

    assert _geometry_species("unused.log", declared) is want


@pytest.mark.parametrize("change", ["rigid-motion", "atom-order", "distortion", "reflection"])
def test_frequency_identity_is_invariant_only_to_rigid_motion_and_atom_order(monkeypatch, change):
    symbols, positions = _chiral_geometry()
    mobile_symbols = list(symbols)
    mobile = positions.copy()
    if change == "rigid-motion":
        rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
        mobile = mobile @ rotation + [1., 2., 3.]
    elif change == "atom-order":
        mobile_symbols = list(reversed(mobile_symbols))
        mobile = mobile[::-1]
    elif change == "distortion":
        mobile[0, 0] += 0.2
    else:
        mobile[:, 0] *= -1
    geometries = {"opt": (symbols, positions), "freq": (mobile_symbols, mobile)}
    monkeypatch.setattr("cloudra.dag.file_science.frames_for", lambda _path: ([], None))
    monkeypatch.setattr("cloudra.dag.file_science.last_geometry", lambda path, _frames: geometries[path])
    opt = SimpleNamespace(snapshot_path="opt", sha256="opt")
    freq = SimpleNamespace(snapshot_path="freq", sha256="freq")

    if change in {"rigid-motion", "atom-order"}:
        validate_frequency_geometry(opt, freq)
    else:
        with pytest.raises(ValueError):
            validate_frequency_geometry(opt, freq)


@pytest.mark.parametrize("smiles,want", [("O", "passed"), ("C#N", "incomplete")])
def test_native_xtb_minimum_geometry_matches_the_declared_species(tmp_path, smiles, want):
    fixture = Path(__file__).parent / "fixtures" / "xtb" / "water_opt_xtb.out"
    text = fixture.read_text()
    # Extend the native optimization fixture with a minimum's frequency block;
    # its original final-structure coordinates and termination marker are kept.
    text = text.replace(
        "normal termination of xtb",
        "projected vibrational frequencies\n"
        "eigval : 0.00 0.00 0.00 0.00 0.00 0.00\n"
        "eigval : 1600.00 3700.00 3800.00\n\nnormal termination of xtb",
    )
    path = tmp_path / "minimum.out"
    path.write_text(text)
    snapshot = snapshot_evidence_file(path, tmp_path)
    assert snapshot.engine == "xtb"
    assert snapshot.imaginary_frequencies == []
    ref = GraphRef(ref_type="file", ref_id="water")
    store = SimpleNamespace(resolve_evidence=lambda _ref: snapshot.model_dump(mode="json"))
    graph = GraphData(graph_id="delivery", graph_kind="delivery", revision=0, nodes=[
        SpeciesNode(node_id="r", smiles=smiles, refs=[ref]),
    ])

    check = file_scientific_checks(store, graph, "r")["geometry"]

    assert check["status"] == want, check
