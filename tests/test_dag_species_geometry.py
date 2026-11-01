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


@pytest.mark.parametrize("declared,want", [("C1CO[PH3]1", True), ("[PH3+]CC[O-]", False)])
def test_phosphorus_ring_identity_handles_explicit_hydrogens_without_accepting_open_chain(monkeypatch, declared, want):
    from cloudra.tools.core.irc_path import parse_xyz

    geometry = parse_xyz((Path(__file__).parent / "fixtures/dag_nu3/oxa_minimum.xyz").read_text())
    monkeypatch.setattr("cloudra.dag.file_science._final_geometry", lambda _path: geometry)

    assert _geometry_species("unused.log", declared) is want


def test_identity_rejection_reports_the_perceived_graph(monkeypatch):
    from cloudra.tools.core.irc_path import parse_xyz

    geometry = parse_xyz((Path(__file__).parent / "fixtures/dag_nu3/oxa_minimum.xyz").read_text())
    monkeypatch.setattr("cloudra.dag.file_science._final_geometry", lambda _path: geometry)
    diagnostics = []

    assert not _geometry_species("unused.log", "[PH3+]CC[O-]", diagnostics=diagnostics)
    assert "[PH3+]CC[O-]" in diagnostics[0]
    assert "perceived" in diagnostics[0]


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
@pytest.mark.parametrize("perception", ["bond-orders", "connectivity-fallback"])
@pytest.mark.parametrize("reverse_atoms", [False, True], ids=["original-order", "reversed-order"])
def test_species_geometry_enforces_only_declared_stereochemistry(
        monkeypatch, actual, declared, want, perception, reverse_atoms):
    geometry = _chiral_geometry(actual)
    if reverse_atoms:
        geometry = (geometry[0][::-1], geometry[1][::-1])
    monkeypatch.setattr("cloudra.dag.file_science._final_geometry", lambda _path: geometry)
    if perception == "connectivity-fallback":
        def fail_bond_orders(*_args, **_kwargs):
            raise ValueError("could not find valid bond ordering")

        monkeypatch.setattr("rdkit.Chem.rdDetermineBonds.DetermineBonds", fail_bond_orders)

    assert _geometry_species("unused.log", declared) is want


def test_wrong_stereochemistry_does_not_enumerate_equivalent_hydrogen_orders(monkeypatch):
    from cloudra.tools.core.preorganization import geometry_stereochemistry_errors

    geometry = _chiral_geometry("CCCC[C@H](O)C(=O)O")
    monkeypatch.setattr("cloudra.dag.file_science._final_geometry", lambda _path: geometry)
    comparisons = []

    def compare_stereochemistry(graph, positions):
        comparisons.append(None)
        return geometry_stereochemistry_errors(graph, positions)

    monkeypatch.setattr(
        "cloudra.tools.core.preorganization.geometry_stereochemistry_errors", compare_stereochemistry)
    diagnostics = []

    assert not _geometry_species("unused.log", "CCCC[C@@H](O)C(=O)O", diagnostics=diagnostics)
    assert len(comparisons) == 1
    assert "connectivity or declared stereochemistry mismatch" in diagnostics[-1]


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
    monkeypatch.setattr("cloudra.dag.file_science._final_geometry", lambda path: geometries[path])
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
