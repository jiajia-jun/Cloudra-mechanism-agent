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


def test_build_atom_draft_from_empty_and_delete_last_atom():
    first = edit_geometry({'action': 'add_atom', 'element': 'C'})
    assert first['atoms'][0] == {
        'index': 1, 'symbol': 'C', 'atom_id': first['atoms'][0]['atom_id'],
        'x': 0., 'y': 0., 'z': 0., 'formal_charge': 0, 'target_valence': None, 'bond_valence': 0.,
    }
    assert first['bonds'] == []
    atom = _copy_molecule(first['molecule']).GetAtomWithIdx(0)
    assert atom.GetNoImplicit()
    empty = edit_geometry({'molecule': first['molecule'], 'action': 'delete_atom', 'atoms': [1]})
    assert empty['atoms'] == empty['bonds'] == []
    assert empty['xyz'] == '0\n\n'
    assert empty['changes'] == {
        'deleted_atom_ids': [first['atoms'][0]['atom_id']], 'deleted_atoms': [1], 'index_map': {}, 'moved_atoms': [],
    }
    restarted = edit_geometry({'molecule': empty['molecule'], 'action': 'add_atom', 'element': ' Cl '})
    assert restarted['atoms'][0]['symbol'] == 'Cl'
    assert restarted['atoms'][0]['atom_id'] != first['atoms'][0]['atom_id']


def test_add_atom_retains_existing_coordinates_and_uses_reference_bond_length():
    first = edit_geometry({'action': 'add_atom', 'element': 'C'})
    request = {'molecule': first['molecule'], 'action': 'add_atom', 'element': 'O', 'atoms': [1], 'order': 2}
    attached = edit_geometry(request)
    replayed = edit_geometry(request)
    assert attached['bonds'] == [{'atom1': 1, 'atom2': 2, 'order': 2.0}]
    assert [atom['bond_valence'] for atom in attached['atoms']] == [2.0, 2.0]
    assert attached['atoms'][0]['atom_id'] == first['atoms'][0]['atom_id']
    assert attached['changes']['moved_atoms'] == []
    assert attached['changes']['index_map'] == {'1': 1}
    attached_coords = _copy_molecule(attached['molecule']).GetConformer().GetPositions()
    np.testing.assert_array_equal(attached_coords[0], [0, 0, 0])
    assert np.linalg.norm(attached_coords[1]) == pytest.approx(1.21)
    np.testing.assert_array_equal(attached_coords, _copy_molecule(replayed['molecule']).GetConformer().GetPositions())

    separate = edit_geometry({'molecule': attached['molecule'], 'action': 'add_atom', 'element': 'Na'})
    separate_coords = _copy_molecule(separate['molecule']).GetConformer().GetPositions()
    assert separate['bonds'] == attached['bonds']
    np.testing.assert_array_equal(separate_coords[:2], attached_coords)
    assert min(np.linalg.norm(separate_coords[:2] - separate_coords[2], axis=1)) > 2


def test_delete_atoms_removes_incident_bonds_and_remaps_survivors():
    original = geometry_view(chain())
    result = edit_geometry({'molecule': original['molecule'], 'action': 'delete_atom', 'atoms': [2, 1]})
    assert result['bonds'] == [{'atom1': 1, 'atom2': 2, 'order': 1.0}]
    assert result['changes']['deleted_atoms'] == [1, 2]
    assert result['changes']['deleted_atom_ids'] == [atom['atom_id'] for atom in original['atoms'][:2]]
    assert result['changes']['index_map'] == {'3': 1, '4': 2}
    assert [atom['atom_id'] for atom in result['atoms']] == [atom['atom_id'] for atom in original['atoms'][2:]]
    np.testing.assert_array_equal(_copy_molecule(result['molecule']).GetConformer().GetPositions(),
                                  chain().GetConformer().GetPositions()[2:])


def test_atom_state_roundtrips_and_caps_only_explicit_targets():
    first = edit_geometry({'action': 'add_atom', 'element': 'N'})
    state = edit_geometry({'molecule': first['molecule'], 'action': 'atom_state', 'atoms': [1],
                           'formal_charge': 1, 'valence': 1})
    restored = geometry_view(_copy_molecule(state['molecule']))
    assert restored['atoms'][0] == {**first['atoms'][0], 'formal_charge': 1, 'target_valence': 1}
    attached = edit_geometry({'molecule': restored['molecule'], 'action': 'add_atom', 'element': 'H', 'atoms': [1]})
    with pytest.raises(ValueError, match='target valence'):
        edit_geometry({'molecule': attached['molecule'], 'action': 'bond', 'atoms': [1, 2], 'order': 2})
    with pytest.raises(ValueError, match='target valence'):
        edit_geometry({'molecule': attached['molecule'], 'action': 'add_atom', 'element': 'F', 'atoms': [1]})
    with pytest.raises(ValueError, match='target valence'):
        edit_geometry({'molecule': attached['molecule'], 'action': 'atom_state', 'atoms': [1], 'valence': 0})
    neutral = edit_geometry({'molecule': attached['molecule'], 'action': 'atom_state', 'atoms': [1], 'formal_charge': 0})
    assert neutral['atoms'][0]['target_valence'] == 1
    cleared = edit_geometry({'molecule': neutral['molecule'], 'action': 'atom_state', 'atoms': [1], 'valence': None})
    assert cleared['atoms'][0]['target_valence'] is None
    permissive = edit_geometry({'molecule': cleared['molecule'], 'action': 'bond', 'atoms': [1, 2], 'order': 3})
    assert permissive['atoms'][0]['bond_valence'] == 3


def test_fill_valence_adds_only_the_requested_explicit_hydrogens():
    first = edit_geometry({'action': 'add_atom', 'element': 'N'})
    state = edit_geometry({'molecule': first['molecule'], 'action': 'atom_state', 'atoms': [1], 'formal_charge': 1, 'valence': 4})
    request = {'molecule': state['molecule'], 'action': 'fill_valence', 'atoms': [1]}
    filled = edit_geometry(request)
    repeated = edit_geometry(request)
    assert [atom['symbol'] for atom in filled['atoms']] == ['N', 'H', 'H', 'H', 'H']
    assert filled['atoms'][0]['formal_charge'] == 1
    assert [atom['bond_valence'] for atom in filled['atoms']] == [4., 1., 1., 1., 1.]
    assert filled['atoms'][0]['atom_id'] == first['atoms'][0]['atom_id']
    coords = _copy_molecule(filled['molecule']).GetConformer().GetPositions()
    assert coords[0].tolist() == [0, 0, 0]
    np.testing.assert_allclose(np.linalg.norm(coords[1:] - coords[0], axis=1), 1.01)
    np.testing.assert_array_equal(coords, _copy_molecule(repeated['molecule']).GetConformer().GetPositions())
    distances = np.linalg.norm(coords[1:, None] - coords[None, 1:], axis=-1)
    pairs = np.triu_indices(4, k=1)
    assert np.min(distances[pairs]) > .74
    directions = coords[1:] / 1.01
    np.testing.assert_allclose((directions @ directions.T)[pairs], -1 / 3, rtol=0, atol=0.18)
    with pytest.raises(ValueError, match='positive whole'):
        edit_geometry({**request, 'molecule': filled['molecule']})


def test_fill_valence_requires_explicit_target_and_integral_gap():
    carbon = edit_geometry({'action': 'add_atom', 'element': 'C'})
    with pytest.raises(ValueError, match='target valence'):
        edit_geometry({'molecule': carbon['molecule'], 'action': 'fill_valence', 'atoms': [1]})
    aromatic = edit_geometry({'molecule': carbon['molecule'], 'action': 'add_atom',
                              'element': 'C', 'atoms': [1], 'order': 1.5})
    state = edit_geometry({'molecule': aromatic['molecule'], 'action': 'atom_state', 'atoms': [1], 'valence': 4})
    with pytest.raises(ValueError, match='positive whole'):
        edit_geometry({'molecule': state['molecule'], 'action': 'fill_valence', 'atoms': [1]})


def test_unresolved_coordinates_keep_total_charge_and_explicit_bond_display_state():
    from cloudra.tools.core.molecule import total_charge

    draft = create_geometry('2\n\nH 0 0 0\nH 0.74 0 0\n', 'xyz')
    assert draft.get('manual_bonds', False) is False
    charged = edit_geometry({'molecule': draft['molecule'], 'action': 'atom_state', 'atoms': [1],
                             'formal_charge': 1, 'valence': 1})
    assert total_charge(_copy_molecule(charged['molecule'])) == 0
    assert charged['graph_status'] == 'unresolved'
    assert charged['atoms'][0]['formal_charge'] == 1
    with pytest.raises(ValueError, match='resolve'):
        edit_geometry({'molecule': charged['molecule'], 'action': 'fill_valence', 'atoms': [1]})
    bonded = edit_geometry({'molecule': charged['molecule'], 'action': 'bond', 'atoms': [1, 2]})
    unbonded = edit_geometry({'molecule': bonded['molecule'], 'action': 'bond', 'atoms': [1, 2], 'order': 0})
    assert unbonded['bonds'] == [] and unbonded['graph_status'] == 'unresolved'
    assert geometry_view(_copy_molecule(unbonded['molecule']))['manual_bonds'] is True
    appended = edit_geometry({'molecule': draft['molecule'], 'action': 'add_atom', 'element': 'H', 'atoms': [1]})
    assert appended['graph_status'] == 'unresolved' and appended['manual_bonds'] is True


def test_atom_state_keeps_perceived_graph_total_in_sync():
    from cloudra.tools.core.molecule import total_charge

    draft = create_geometry('2\n\nH 0 0 0\nH 0.74 0 0\n', 'xyz')
    resolved = edit_geometry({'molecule': draft['molecule'], 'action': 'resolve_bonds'})
    charged = edit_geometry({'molecule': resolved['molecule'], 'action': 'atom_state', 'atoms': [1], 'formal_charge': -1})
    assert total_charge(_copy_molecule(charged['molecule'])) == -1
    deleted = edit_geometry({'molecule': charged['molecule'], 'action': 'delete_atom', 'atoms': [1]})
    assert total_charge(_copy_molecule(deleted['molecule'])) == 0


@pytest.mark.parametrize('action', [
    {'action': 'add_atom', 'element': 'Un'},
    {'action': 'add_atom', 'element': 'H', 'atoms': [1], 'order': 0},
    {'action': 'add_atom', 'element': 'H', 'atoms': [1, 2]},
    {'action': 'delete_atom'},
    {'action': 'atom_state', 'atoms': [1], 'formal_charge': True},
    {'action': 'atom_state', 'atoms': [1], 'formal_charge': None},
    {'action': 'atom_state', 'atoms': [1], 'formal_charge': 128},
    {'action': 'atom_state', 'atoms': [1], 'valence': 2.0},
    {'action': 'atom_state', 'atoms': [1], 'valence': -1},
    {'action': 'atom_state', 'atoms': [1], 'valence': 33},
    {'action': 'atom_state', 'atoms': [1, 2], 'valence': 4},
    {'action': 'fill_valence', 'atoms': [1, 2]},
])
def test_builder_rejects_invalid_requests(action):
    with pytest.raises(ValueError):
        edit_geometry({'molecule': serialize_molecule(chain()), **action})


def test_save_refuses_an_empty_draft_before_writing(tmp_path):
    from types import SimpleNamespace

    from cloudra.services.workbench import WorkbenchService

    first = edit_geometry({'action': 'add_atom', 'element': 'C'})
    empty = edit_geometry({'molecule': first['molecule'], 'action': 'delete_atom', 'atoms': [1]})
    service = WorkbenchService(SimpleNamespace(id='workbench-project', workspace_dir=str(tmp_path)))
    with pytest.raises(ValueError, match='至少一个原子'):
        service.save(SimpleNamespace(molecule=_copy_molecule(empty['molecule']), source_path=None))
    assert list(tmp_path.iterdir()) == []


def test_save_preserves_explicit_draft_bond_order_and_preview_flag(tmp_path):
    from pathlib import Path
    from types import SimpleNamespace

    from cloudra.services.api_v2.routers.workbench import OpenRequest, SaveRequest
    from cloudra.services.workbench import WorkbenchService

    draft = create_geometry('2\n\nC 0 0 0\nC 1.4 0 0\n', 'xyz')
    edited = edit_geometry({'molecule': draft['molecule'], 'action': 'bond', 'atoms': [1, 2], 'order': 1.5})
    service = WorkbenchService(SimpleNamespace(id='workbench-project', workspace_dir=str(tmp_path)))
    saved = service.save(SaveRequest(molecule=edited['molecule']))
    exported = Chem.MolFromMolBlock(Path(saved['files']['mol']).read_text(), sanitize=False, removeHs=False)
    assert exported.GetBondBetweenAtoms(0, 1).GetBondTypeAsDouble() == 1.5
    preview = service.preview(OpenRequest(path=saved['path']))
    assert preview['bonds'] == edited['bonds']
    assert preview['manual_bonds'] is True


def test_add_atom_allows_close_nonnumerical_contacts_in_a_manual_seed():
    from itertools import product

    shell = '\n'.join(f'C {x / 3**.5} {y / 3**.5} {z / 3**.5}' for x, y, z in product((-1, 1), repeat=3))
    draft = create_geometry(f'9\n\nC 0 0 0\n{shell}\n', 'xyz')
    attached = edit_geometry({'molecule': draft['molecule'], 'action': 'add_atom', 'element': 'H', 'atoms': [1]})
    positions = _copy_molecule(attached['molecule']).GetConformer().GetPositions()
    distances = np.linalg.norm(positions[:-1] - positions[-1], axis=1)
    assert distances[0] == pytest.approx(1.09)
    assert 1e-9 < min(distances[1:]) < 1.09
