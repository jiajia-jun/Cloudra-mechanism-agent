"""The workbench and Agent must edit the same graph/coordinates."""
import numpy as np
import pytest

pytest.importorskip('rdkit')
from rdkit import Chem
from rdkit.Chem import rdMolTransforms

from cloudra.tools.core.molecule import _copy_molecule, serialize_molecule
from cloudra.tools.core.workbench_geometry import EditRequest, create_geometry, edit_geometry, geometry_view


def chain():
    mol = Chem.MolFromSmiles('CCCC')
    conf = Chem.Conformer(4)
    for i, p in enumerate([(0, 1, 0), (0, 0, 0), (1, 0, 0), (1, 1, 1)]):
        conf.SetAtomPosition(i, p)
    mol.AddConformer(conf)
    return mol


@pytest.mark.parametrize('atoms,target,reader', [
    ([1, 2], 2.3, rdMolTransforms.GetBondLength),
    ([1, 2, 3], 115, rdMolTransforms.GetAngleDeg),
    ([1, 2, 3, 4], -110, rdMolTransforms.GetDihedralDeg),
])
@pytest.mark.parametrize('fixed_side', ['first', 'last'])
def test_absolute_ordered_coordinate_keeps_fixed_endpoint(atoms, target, reader, fixed_side):
    mol = chain()
    original = mol.GetConformer().GetPositions()
    result = edit_geometry(EditRequest(molecule=mol, action='coordinate', atoms=atoms,
                                       value=target, fixed_side=fixed_side))
    edited = _copy_molecule(result['molecule'])
    assert reader(edited.GetConformer(), *[i-1 for i in atoms]) == pytest.approx(target)
    fixed = atoms[0 if fixed_side == 'first' else -1] - 1
    assert edited.GetConformer().GetAtomPosition(fixed) == pytest.approx(original[fixed])
    np.testing.assert_array_equal(mol.GetConformer().GetPositions(), original)


def test_native_roundtrip_stable_identity_and_graph():
    view = geometry_view(chain())
    restored = geometry_view(_copy_molecule(view['molecule']))
    assert restored == view
    assert len({a['atom_id'] for a in view['atoms']}) == 4
    assert view['bonds'][0] == {'atom1': 1, 'atom2': 2, 'order': 1.0}


def test_xyz_does_not_silently_declare_graph_and_manual_distance_works():
    view = create_geometry('2\n\nH 0 0 0\nH 1 0 0\n', 'xyz')
    assert view['bonds'] == [] and view['graph_status'] == 'unresolved'
    with pytest.raises(ValueError, match='moving_atoms|resolve'):
        edit_geometry(EditRequest(molecule=view['molecule'], action='coordinate', atoms=[1, 2], value=2))
    edited = edit_geometry(EditRequest(molecule=view['molecule'], action='coordinate',
                                       atoms=[1, 2], value=2, moving_atoms=[2]))
    assert edited['atoms'][1]['x'] == pytest.approx(2)
    assert edited['graph_status'] == 'unresolved'


def test_ring_requires_manual_group():
    mol = chain()
    rw = Chem.RWMol(mol)
    rw.AddBond(0, 3, Chem.BondType.SINGLE)
    with pytest.raises(ValueError, match='moving_atoms'):
        edit_geometry(EditRequest(molecule=rw.GetMol(), action='coordinate', atoms=[1, 2], value=2))
    result = edit_geometry(EditRequest(molecule=rw.GetMol(), action='coordinate', atoms=[1, 2],
                                       value=2, moving_atoms=[2]))
    assert result['changes']['moved_atoms'] == [2]


@pytest.mark.parametrize('order', [0, 1, 1.5, 2, 3])
def test_bond_edit_preserves_exact_coordinates(order):
    mol = chain()
    result = edit_geometry(EditRequest(molecule=mol, action='bond', atoms=[1, 2], order=order))
    edited = _copy_molecule(result['molecule'])
    bond = edited.GetBondBetweenAtoms(0, 1)
    assert (bond.GetBondTypeAsDouble() if bond else 0) == order
    np.testing.assert_array_equal(edited.GetConformer().GetPositions(), mol.GetConformer().GetPositions())


def test_mirror_whole_or_selected_atoms():
    mol = chain()
    result = edit_geometry(EditRequest(molecule=mol, action='mirror', plane='xz', moving_atoms=[1]))
    assert result['atoms'][0]['y'] == -1
    assert result['atoms'][3]['y'] == 1


def test_fragment_replacement_preserves_survivors_and_reports_deleted_ids():
    view = geometry_view(chain())
    result = edit_geometry(EditRequest(molecule=view['molecule'], action='replace_group', atoms=[2, 3],
                                       smiles='F', attachment_atom=1))
    assert result['changes']['deleted_atoms'] == [3, 4]
    assert result['changes']['deleted_atom_ids'] == [a['atom_id'] for a in view['atoms'][2:]]
    assert result['changes']['index_map'] == {'1': 1, '2': 2}
    assert result['changes']['fragment_smiles'] in ('*F', '[*]F')
    assert [a['atom_id'] for a in result['atoms'][:2]] == [a['atom_id'] for a in view['atoms'][:2]]
    assert result['atoms'][2]['symbol'] == 'F'


def test_agent_and_workbench_coordinate_authority_matches():
    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates
    mol = chain()
    direct, _ = InternalCoordinates._transform_molecule(mol, {
        'type': 'coordinate', 'atoms': [1, 2, 3], 'value': 120,
    })
    web = edit_geometry(EditRequest(molecule=mol, action='coordinate', atoms=[1, 2, 3], value=120))
    np.testing.assert_allclose(direct.GetConformer().GetPositions(),
                               _copy_molecule(web['molecule']).GetConformer().GetPositions())


def test_unmarked_fragment_requires_explicit_connection_selection():
    with pytest.raises(ValueError, match='attachment_atom'):
        edit_geometry(EditRequest(molecule=serialize_molecule(chain()), action='replace_group',
                                  atoms=[2, 3], smiles='CO'))


def test_create_smiles_uses_authoritative_builder_seed():
    view = create_geometry('CO', 'smiles')
    assert [a['symbol'] for a in view['atoms'][:2]] == ['C', 'O']
    assert len(view['atoms']) == 6
    assert view['bonds'] and 'seed' in view['warnings'][0]


def test_explicit_bond_resolution_keeps_native_atom_identity():
    view = create_geometry('2\n\nH 0 0 0\nH 0.74 0 0\n', 'xyz')
    result = edit_geometry(EditRequest(molecule=view['molecule'], action='resolve_bonds'))
    assert result['graph_status'] == 'perceived'
    assert result['bonds'] == [{'atom1': 2, 'atom2': 1, 'order': 1.0}]
    assert [a['atom_id'] for a in result['atoms']] == [a['atom_id'] for a in view['atoms']]


def test_nonbonded_disconnected_group_moves_as_rigid_body():
    mol = chain()
    rw = Chem.RWMol(mol)
    rw.RemoveBond(1, 2)
    mol = rw.GetMol()
    old = mol.GetConformer().GetPositions()
    result = edit_geometry(EditRequest(molecule=mol, action='coordinate', atoms=[1, 4], value=4))
    new = _copy_molecule(result['molecule']).GetConformer().GetPositions()
    np.testing.assert_array_equal(new[:2], old[:2])
    np.testing.assert_allclose(new[2] - old[2], new[3] - old[3])
    assert np.linalg.norm(new[3] - new[0]) == pytest.approx(4)


def test_add_bond_and_measure_coordinate_without_mutating_geometry():
    from cloudra.tools.core.workbench_geometry import coordinate_value
    mol = chain()
    before = mol.GetConformer().GetPositions().copy()
    result = edit_geometry(EditRequest(molecule=mol, action='bond', atoms=[1, 4], order=1))
    assert len(result['bonds']) == 4
    assert coordinate_value(mol, [1, 2, 3, 4]) == pytest.approx(45)
    np.testing.assert_array_equal(mol.GetConformer().GetPositions(), before)
