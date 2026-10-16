"""Molecule geometry views preserve the source graph when replacing coordinates."""

import numpy as np
import pytest

pytest.importorskip("rdkit")
pytest.importorskip("ase")

from ase import Atoms  # noqa: E402
from rdkit import Chem  # noqa: E402

from cloudra.tools.core.molecule import from_ase, to_ase, to_xyz, with_positions  # noqa: E402


def test_with_positions_copies_chemistry_properties_and_other_conformers():
    mol = Chem.MolFromSmiles("[13CH3:7]/C=C(/[O-])[C@H](F)c1ccccc1")
    mol.SetProp("_Name", "original molecule")
    mol.SetProp("source", "declared graph")
    mol.GetAtomWithIdx(0).SetIntProp("input_atom_index", 12)
    mol.GetBondWithIdx(0).SetProp("source", "declared bond")
    conf = Chem.Conformer(mol.GetNumAtoms())
    conf.SetId(3)
    conf.Set3D(False)
    conf.SetProp("source", "original geometry")
    original_positions = np.arange(mol.GetNumAtoms() * 3).reshape(-1, 3) / 10
    for index, position in enumerate(original_positions):
        conf.SetAtomPosition(index, position)
    mol.AddConformer(conf, assignId=False)
    other = Chem.Conformer(conf)
    other.SetId(7)
    mol.AddConformer(other, assignId=False)
    positions = original_positions + [1.23456789, -2.34567891, 3.45678912]

    updated = with_positions(mol, positions)

    assert updated is not mol
    assert Chem.MolToSmiles(updated) == Chem.MolToSmiles(mol)
    assert Chem.GetFormalCharge(updated) == -1
    assert updated.GetAtomWithIdx(0).GetIsotope() == 13
    assert updated.GetAtomWithIdx(0).GetAtomMapNum() == 7
    assert updated.GetProp("_Name") == "original molecule"
    assert updated.GetProp("source") == "declared graph"
    assert updated.GetAtomWithIdx(0).GetIntProp("input_atom_index") == 12
    assert updated.GetBondWithIdx(0).GetProp("source") == "declared bond"
    assert updated.GetConformer().GetId() == 3
    assert updated.GetConformer().Is3D() is False
    assert updated.GetConformer().GetProp("source") == "original geometry"
    np.testing.assert_array_equal(updated.GetConformer().GetPositions(), positions)
    np.testing.assert_array_equal(mol.GetConformer().GetPositions(), original_positions)
    np.testing.assert_array_equal(updated.GetConformer(7).GetPositions(), original_positions)
    updated.GetAtomWithIdx(0).SetIntProp("input_atom_index", 99)
    assert mol.GetAtomWithIdx(0).GetIntProp("input_atom_index") == 12


def test_ase_views_keep_geometry_without_inventing_bonds_or_formal_charge():
    atoms = Atoms("OH2", positions=[[0, 0, 0], [0.957, 0, 0], [-0.239, 0.927, 0]])
    atoms.set_initial_charges([-1, 0, 0])

    mol = from_ase(atoms)
    view = to_ase(mol)

    assert mol.GetNumAtoms() == 3
    assert mol.GetNumBonds() == 0
    assert Chem.GetFormalCharge(mol) == 0
    assert view.get_chemical_symbols() == ["O", "H", "H"]
    np.testing.assert_array_equal(view.get_positions(), atoms.get_positions())
    view.positions[0, 0] = 9
    assert mol.GetConformer().GetAtomPosition(0).x == 0
    assert atoms.positions[0, 0] == 0


def test_to_xyz_uses_ordered_coordinates_and_eight_decimal_places():
    mol = from_ase(Atoms("CH", positions=[[1.123456789, -2.25, 0], [0, 1.5, 2]]))

    assert to_xyz(mol) == (
        "2\n\n"
        "C        1.12345679    -2.25000000     0.00000000\n"
        "H        0.00000000     1.50000000     2.00000000\n"
    )


def test_native_molecule_serialization_preserves_structure_and_properties():
    from pydantic import BaseModel

    from cloudra.tools.core.molecule import Molecule, copy_conformer

    class Record(BaseModel):
        mol: Molecule

    mol = Chem.MolFromSmiles("[13CH3:7][O-]")
    mol.SetProp("source", "declared molecule")
    mol.GetAtomWithIdx(0).SetProp("origin", "input carbon")
    mol.GetBondWithIdx(0).SetProp("origin", "input bond")
    conf = Chem.Conformer(2)
    conf.SetId(5)
    conf.SetProp("origin", "input geometry")
    conf.SetAtomPosition(0, [0.123456789012345, 0, 0])
    conf.SetAtomPosition(1, [1.45, 0, 0])
    mol.AddConformer(conf, assignId=False)
    selected = copy_conformer(mol, 5)
    record = Record(mol=selected)
    restored = Record.model_validate_json(record.model_dump_json()).mol
    assert restored.GetProp("source") == "declared molecule"
    assert restored.GetAtomWithIdx(0).GetProp("origin") == "input carbon"
    assert restored.GetBondWithIdx(0).GetProp("origin") == "input bond"
    assert restored.GetConformer().GetProp("origin") == "input geometry"
    assert Chem.MolToSmiles(restored) == Chem.MolToSmiles(mol)
    np.testing.assert_array_equal(restored.GetConformer().GetPositions(), mol.GetConformer(5).GetPositions())
    restored.GetAtomWithIdx(0).SetProp("origin", "changed")
    assert mol.GetAtomWithIdx(0).GetProp("origin") == "input carbon"
    record.mol.GetAtomWithIdx(0).SetProp("origin", "record changed")
    assert selected.GetAtomWithIdx(0).GetProp("origin") == "input carbon"


def test_read_molecule_keeps_declared_graph_and_coordinate_only_total_charge(tmp_path):
    from cloudra.tools.core.molecule import read_molecule, total_charge

    source = Chem.MolFromSmiles("[Na+].[O-][13CH3:7]")
    source.AddConformer(Chem.Conformer(source.GetNumAtoms()))
    mol_path = tmp_path / "source.mol"
    mol_path.write_text(Chem.MolToMolBlock(source))
    restored = read_molecule(input_path=str(mol_path))
    assert restored.GetNumBonds() == 1
    assert restored.GetAtomWithIdx(1).GetFormalCharge() == -1
    assert restored.GetAtomWithIdx(2).GetIsotope() == 13
    assert restored.GetAtomWithIdx(2).GetAtomMapNum() == 7
    assert total_charge(restored) == 0
    xyz = read_molecule(input_text="2\n\nN 0 0 0\nO 1.5 0 0\n", charge=1)
    assert xyz.GetNumBonds() == 0
    assert total_charge(xyz) == 1
    assert [a.GetFormalCharge() for a in xyz.GetAtoms()] == [0, 0]


@pytest.mark.parametrize("fmt", ["mol", "mol_v3000", "sdf"])
def test_auto_text_reads_native_graph_without_a_coordinate_roundtrip(fmt):
    from cloudra.tools.core.molecule import read_molecule

    source = Chem.MolFromSmiles("[13CH3:7][O-]")
    source.AddConformer(Chem.Conformer(source.GetNumAtoms()))
    text = Chem.MolToMolBlock(source, forceV3000=fmt == "mol_v3000")
    if fmt == "sdf":
        text += "\n>  <source>\ncharged input\n\n$$$$\n"

    mol = read_molecule(input_text=text)

    assert Chem.GetFormalCharge(mol) == -1
    assert mol.GetNumBonds() == 1
    assert mol.GetAtomWithIdx(0).GetIsotope() == 13
    assert mol.GetAtomWithIdx(0).GetAtomMapNum() == 7
    if fmt == "sdf":
        assert mol.GetProp("source") == "charged input"


def test_internal_coordinate_auto_text_keeps_known_charge_and_graph():
    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    source = Chem.MolFromSmiles("[13CH3:7][O-]")
    source.AddConformer(Chem.Conformer(source.GetNumAtoms()))
    text = Chem.MolToMolBlock(source)

    mol, bond_source, notes = InternalCoordinates._load_molecule(None, text, "auto", 0)

    assert Chem.GetFormalCharge(mol) == -1
    assert mol.GetNumBonds() == 1
    assert mol.GetAtomWithIdx(0).GetIsotope() == 13
    assert mol.GetAtomWithIdx(0).GetAtomMapNum() == 7
    assert bond_source == "input"
    assert notes == []


def test_native_serialization_is_stable_across_repeated_model_roundtrips():
    from pydantic import BaseModel

    from cloudra.tools.core.molecule import Molecule

    class Record(BaseModel):
        mol: Molecule

    mol = Chem.MolFromSmiles("[13CH3:7]/C=C(/[O-])[C@H](F)c1ccccc1")
    mol.SetProp("source", "declared graph")
    mol.GetAtomWithIdx(0).SetIntProp("origin", 7)
    conf = Chem.Conformer(mol.GetNumAtoms())
    for index in range(mol.GetNumAtoms()):
        conf.SetAtomPosition(index, [index * 0.123456789012345, 0, 0])
    mol.AddConformer(conf)
    record = Record(mol=mol)
    serialized = record.model_dump_json()

    for _ in range(4):
        restored = Record.model_validate_json(serialized)
        Chem.MolToSmiles(restored.mol)
        assert restored.mol.GetProp("source") == "declared graph"
        assert restored.mol.GetAtomWithIdx(0).GetIntProp("origin") == 7
        np.testing.assert_array_equal(restored.mol.GetConformer().GetPositions(), mol.GetConformer().GetPositions())
        assert restored.model_dump_json() == serialized
        serialized = restored.model_dump_json()


def test_python_model_dump_keeps_native_molecule_until_json_boundary():
    from pydantic import BaseModel

    from cloudra.tools.core.molecule import Molecule

    class Record(BaseModel):
        mol: Molecule

    record = Record(mol=Chem.MolFromSmiles("[13CH3:7][O-]"))

    assert record.model_dump()["mol"] is record.mol
    assert isinstance(record.model_dump(mode="json")["mol"], str)


def test_to_xyz_keeps_an_explicit_export_comment():
    mol = from_ase(Atoms("H", positions=[[0, 0, 0]]))

    assert to_xyz(mol, comment="existing stage title").splitlines()[:2] == ["1", "existing stage title"]


def test_invalid_native_molecule_state_reports_a_validation_error():
    from pydantic import BaseModel, ValidationError

    from cloudra.tools.core.molecule import Molecule

    class Record(BaseModel):
        mol: Molecule

    with pytest.raises(ValidationError):
        Record(mol="CCCC")


def test_renumber_atoms_keeps_typed_molecule_state_and_input_unchanged():
    from cloudra.tools.core.molecule import renumber_atoms, total_charge

    mol = from_ase(Atoms("CO", positions=[[0.123456789, 0, 0], [1.45, 0, 0]]))
    mol.SetIntProp("cloudra_total_charge", 1)
    mol.SetProp("cloudra_graph_status", "unresolved")
    mol.SetBoolProp("custom_flag", True)
    mol.SetIntProp("custom_count", -7)
    mol.SetUnsignedProp("native_index", 3000000000)
    mol.SetDoubleProp("custom_value", 1.23456789)
    mol.SetProp("_private_numeric_text", "123")
    mol.GetAtomWithIdx(0).SetProp("identity", "original carbon")
    mol.GetConformer().SetProp("source", "input geometry")

    reordered = renumber_atoms(mol, [1, 0])

    assert total_charge(reordered) == 1
    assert reordered.GetProp("cloudra_graph_status") == "unresolved"
    assert reordered.GetBoolProp("custom_flag") is True
    assert reordered.GetIntProp("custom_count") == -7
    assert reordered.GetUnsignedProp("native_index") == 3000000000
    assert reordered.GetDoubleProp("custom_value") == 1.23456789
    assert reordered.GetProp("_private_numeric_text") == "123"
    props = reordered.GetPropsAsDict(includePrivate=True, includeComputed=False, autoConvertStrings=False)
    assert type(props["_private_numeric_text"]) is str
    assert reordered.GetAtomWithIdx(1).GetProp("identity") == "original carbon"
    assert reordered.GetConformer().GetProp("source") == "input geometry"
    assert [atom.GetSymbol() for atom in reordered.GetAtoms()] == ["O", "C"]
    np.testing.assert_array_equal(reordered.GetConformer().GetPositions(), [[1.45, 0, 0], [0.123456789, 0, 0]])
    assert [atom.GetSymbol() for atom in mol.GetAtoms()] == ["C", "O"]
    reordered.SetIntProp("cloudra_total_charge", -1)
    assert total_charge(mol) == 1


def test_auto_path_reads_xyz_with_an_unrelated_file_extension(tmp_path):
    from cloudra.tools.core.molecule import read_molecule

    source = tmp_path / "geometry.txt"
    source.write_text("2\nexisting geometry\nC 0.123456789 0 0\nO 1.45 0 0\n")

    mol = read_molecule(input_path=source)

    assert mol.GetNumAtoms() == 2
    assert mol.GetNumBonds() == 0
    assert [atom.GetSymbol() for atom in mol.GetAtoms()] == ["C", "O"]
    np.testing.assert_array_equal(mol.GetConformer().GetPositions(), [[0.123456789, 0, 0], [1.45, 0, 0]])
