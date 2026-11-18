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
        'hybridization': 'sp3', 'hybridization_override': None, 'lone_pairs': 0,
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
    assert restored['atoms'][0] == {**first['atoms'][0], 'formal_charge': 1, 'target_valence': 1,
                                   'hybridization': None, 'lone_pairs': None}
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


@pytest.mark.parametrize('element,charge,count,lone_pairs', [('O', 0, 2, 2), ('N', 0, 3, 1), ('C', 0, 4, 0), ('N', 1, 4, 0), ('O', 1, 3, 1)])
@pytest.mark.parametrize('action', ['add_atom', 'fill_valence'])
def test_builder_uses_electron_domains_for_both_atom_placement_paths(element, charge, count, lone_pairs, action):
    view = edit_geometry({'action': 'add_atom', 'element': element})
    view = edit_geometry({'molecule': view['molecule'], 'action': 'atom_state', 'atoms': [1],
                          'formal_charge': charge, 'valence': count})
    if action == 'fill_valence':
        view = edit_geometry({'molecule': view['molecule'], 'action': action, 'atoms': [1]})
    else:
        for _ in range(count):
            view = edit_geometry({'molecule': view['molecule'], 'action': action, 'atoms': [1], 'element': 'H'})
    positions = _copy_molecule(view['molecule']).GetConformer().GetPositions()
    directions = positions[1:] - positions[0]
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    np.testing.assert_allclose((directions @ directions.T)[np.triu_indices(count, k=1)], -1 / 3, atol=1e-7)
    assert view['atoms'][0]['hybridization'] == 'sp3'
    assert view['atoms'][0]['lone_pairs'] == lone_pairs
    assert len(view['atoms']) == count + 1


@pytest.mark.parametrize('order,hybridization,cosine', [(2, 'sp2', -.5), (3, 'sp', -1.)])
def test_multiple_bonds_set_geometry_before_placing_new_atom(order, hybridization, cosine):
    view = edit_geometry({'action': 'add_atom', 'element': 'C'})
    view = edit_geometry({'molecule': view['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'N', 'order': order})
    view = edit_geometry({'molecule': view['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'H'})
    positions = _copy_molecule(view['molecule']).GetConformer().GetPositions()
    vectors = positions[1:] - positions[0]
    vectors /= np.linalg.norm(vectors, axis=1)[:, None]
    assert vectors[0] @ vectors[1] == pytest.approx(cosine)
    assert view['atoms'][0]['hybridization'] == hybridization


def test_changed_hybridization_keeps_existing_geometry_and_explicitly_warns():
    view = edit_geometry({'action': 'add_atom', 'element': 'C'})
    for _ in range(2):
        view = edit_geometry({'molecule': view['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'H'})
    before = _copy_molecule(view['molecule']).GetConformer().GetPositions()
    changed = edit_geometry({'molecule': view['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'O', 'order': 2})
    assert changed['atoms'][0]['hybridization'] == 'sp2'
    np.testing.assert_array_equal(_copy_molecule(changed['molecule']).GetConformer().GetPositions()[:3], before)
    assert any('existing atom coordinates and bond angles are unchanged' in warning for warning in changed['warnings'])


@pytest.mark.parametrize('action', ['add_atom', 'fill_valence'])
def test_incompatible_fixed_neighbors_keep_new_bond_at_reference_length(action):
    view = edit_geometry({'action': 'add_atom', 'element': 'C'})
    for _ in range(3):
        view = edit_geometry({'molecule': view['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'H'})
    mol = _copy_molecule(view['molecule'])
    for index, position in enumerate([(1.09, 0, 0), (0, 1.09, 0), (0, 0, 1.09)], start=1):
        mol.GetConformer().SetAtomPosition(index, position)
    before = mol.GetConformer().GetPositions()
    state = edit_geometry({'molecule': mol, 'action': 'atom_state', 'atoms': [1], 'valence': 4})
    body = {'molecule': state['molecule'], 'action': action, 'atoms': [1]}
    if action == 'add_atom':
        body['element'] = 'H'
    result = edit_geometry(body)
    positions = _copy_molecule(result['molecule']).GetConformer().GetPositions()
    np.testing.assert_array_equal(positions[:4], before)
    assert np.isfinite(positions).all()
    assert np.linalg.norm(positions[4] - positions[0]) == pytest.approx(1.09)


@pytest.mark.parametrize('action', ['add_atom', 'fill_valence', 'atom_state', 'delete_atom', 'bond'])
def test_builder_edits_do_not_certify_distance_inferred_bond_orders(action):
    view = edit_geometry({'action': 'add_atom', 'element': 'C'})
    view = edit_geometry({'molecule': view['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'H'})
    mol = _copy_molecule(view['molecule'])
    mol.SetProp('cloudra_graph_status', 'distance-inferred')
    mol.GetAtomWithIdx(0).SetIntProp('cloudra_target_valence', 4)
    assert geometry_view(mol)['atoms'][0]['hybridization'] is None
    body = {'molecule': mol, 'action': action, 'atoms': [1]}
    if action == 'add_atom':
        body['element'] = 'H'
    elif action == 'delete_atom':
        body['atoms'] = [2]
    elif action == 'bond':
        body['atoms'] = [1, 2]
    result = edit_geometry(body)
    assert result['graph_status'] == 'distance-inferred'
    assert result['atoms'][0]['hybridization'] is None
    assert result['atoms'][0]['lone_pairs'] is None
    with pytest.raises(ValueError, match='resolved'):
        edit_geometry({'molecule': result['molecule'], 'action': 'preoptimize'})


def test_manual_geometry_override_does_not_certify_distance_inferred_graph():
    view = edit_geometry({'action': 'add_atom', 'element': 'N'})
    view = edit_geometry({'molecule': view['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'H'})
    mol = _copy_molecule(view['molecule'])
    mol.SetProp('cloudra_graph_status', 'distance-inferred')
    state = edit_geometry({'molecule': mol, 'action': 'atom_state', 'atoms': [1], 'hybridization': 'sp2'})
    result = edit_geometry({'molecule': state['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'H'})
    assert result['graph_status'] == 'distance-inferred'
    assert result['atoms'][0]['hybridization'] == result['atoms'][0]['hybridization_override'] == 'sp2'
    assert result['atoms'][0]['lone_pairs'] is None
    assert rdMolTransforms.GetAngleDeg(_copy_molecule(result['molecule']).GetConformer(), 1, 0, 2) == pytest.approx(120)


def test_shared_bond_editor_preserves_distance_inferred_provenance():
    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    mol = chain()
    mol.SetProp('cloudra_graph_status', 'distance-inferred')
    result, _ = InternalCoordinates._transform_molecule(mol, {'type': 'bond', 'atoms': [1, 2], 'order': 2})
    assert result.GetProp('cloudra_graph_status') == 'distance-inferred'


def test_explicit_resolution_retries_inferred_graph_without_duplicate_bonds(monkeypatch):
    from rdkit.Chem import rdDetermineBonds

    determine = rdDetermineBonds.DetermineBonds

    def unavailable(*args, **kwargs):
        raise ValueError('perception unavailable')

    monkeypatch.setattr(rdDetermineBonds, 'DetermineBonds', unavailable)
    initial = create_geometry('3\n\nO 0 0 0\nH .957 0 0\nH -.239 .927 0\n', 'xyz')
    inferred = edit_geometry({'molecule': initial['molecule'], 'action': 'resolve_bonds'})
    repeated = edit_geometry({'molecule': inferred['molecule'], 'action': 'resolve_bonds'})
    assert inferred['graph_status'] == repeated['graph_status'] == 'distance-inferred'
    assert inferred['bonds'] == repeated['bonds']
    monkeypatch.setattr(rdDetermineBonds, 'DetermineBonds', determine)
    resolved = edit_geometry({'molecule': inferred['molecule'], 'action': 'resolve_bonds'})
    assert resolved['graph_status'] == 'perceived'
    assert resolved['atoms'][0]['hybridization'] == 'sp3'
    assert [atom['atom_id'] for atom in resolved['atoms']] == [atom['atom_id'] for atom in inferred['atoms']]


def test_internal_coordinate_forwarding_excludes_editor_only_fields(monkeypatch):
    from cloudra.tools.Chemtool.internal_coordinates import InternalCoordinates

    transform = InternalCoordinates._transform_molecule
    forwarded = []

    def capture(mol, operation):
        forwarded.append(operation)
        return transform(mol, operation)

    monkeypatch.setattr(InternalCoordinates, '_transform_molecule', capture)
    edit_geometry({'molecule': chain(), 'action': 'coordinate', 'atoms': [1, 2], 'value': 1.5})
    assert not {'force_field', 'hybridization'} & forwarded[0].keys()


@pytest.mark.parametrize('smiles,index,hybridization,lone_pairs', [
    ('CC(=O)N', 3, 'sp2', 1), ('c1ccncc1', 3, 'sp2', 1), ('c1cc[nH]c1', 3, 'sp2', 1),
    ('[NH4+]', 0, 'sp3', 0), ('[OH-]', 0, 'sp3', 3), ('N#C', 0, 'sp', 1),
])
def test_local_geometry_reads_conjugation_aromaticity_and_charge(smiles, index, hybridization, lone_pairs):
    mol = Chem.MolFromSmiles(smiles)
    mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()))
    atom = geometry_view(mol)['atoms'][index]
    assert atom['hybridization'] == hybridization
    assert atom['lone_pairs'] == lone_pairs


def test_aromatic_atom_with_unsupported_target_has_no_automatic_geometry():
    mol = Chem.MolFromSmiles('c1ccccc1')
    mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()))
    state = edit_geometry({'molecule': mol, 'action': 'atom_state', 'atoms': [1], 'valence': 7})
    assert state['atoms'][0]['hybridization'] is None
    assert state['atoms'][0]['lone_pairs'] is None
    manual = edit_geometry({'molecule': state['molecule'], 'action': 'atom_state', 'atoms': [1], 'hybridization': 'sp2'})
    assert manual['atoms'][0]['hybridization'] == 'sp2'
    assert manual['atoms'][0]['lone_pairs'] is None


def test_fill_imported_implicit_hydrogens_uses_same_planar_amide_geometry():
    mol = Chem.MolFromSmiles('CC(=O)N')
    conf = Chem.Conformer(4)
    for index, position in enumerate([(-1, 1, 0), (0, 0, 0), (0, -1.2, 0), (1.4, 0, 0)]):
        conf.SetAtomPosition(index, position)
    mol.AddConformer(conf)
    before = mol.GetConformer().GetPositions()
    state = edit_geometry({'molecule': mol, 'action': 'atom_state', 'atoms': [4], 'valence': 3})
    filled = edit_geometry({'molecule': state['molecule'], 'action': 'fill_valence', 'atoms': [4]})
    result = _copy_molecule(filled['molecule'])
    assert result.GetNumAtoms() == 6
    assert result.GetAtomWithIdx(3).GetNumImplicitHs() == 0
    assert result.GetAtomWithIdx(3).GetNumExplicitHs() == 0
    np.testing.assert_array_equal(result.GetConformer().GetPositions()[:4], before)
    vectors = result.GetConformer().GetPositions()[[1, 4, 5]] - before[3]
    vectors /= np.linalg.norm(vectors, axis=1)[:, None]
    np.testing.assert_allclose((vectors @ vectors.T)[np.triu_indices(3, k=1)], -.5, atol=1e-7)
    assert mol.GetNumAtoms() == 4 and mol.GetAtomWithIdx(3).GetNumImplicitHs() == 2


def test_manual_hybridization_roundtrip_clear_and_placement_on_existing_graph():
    original = edit_geometry({'action': 'add_atom', 'element': 'N'})
    original = edit_geometry({'molecule': original['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'H'})
    state = edit_geometry({'molecule': original['molecule'], 'action': 'atom_state', 'atoms': [1], 'hybridization': 'sp2'})
    restored = geometry_view(_copy_molecule(state['molecule']))
    assert restored['atoms'][0]['hybridization_override'] == 'sp2'
    assert restored['atoms'][0]['hybridization'] == 'sp2'
    np.testing.assert_array_equal(_copy_molecule(state['molecule']).GetConformer().GetPositions(),
                                  _copy_molecule(original['molecule']).GetConformer().GetPositions())
    attached = edit_geometry({'molecule': state['molecule'], 'action': 'add_atom', 'atoms': [1], 'element': 'H'})
    assert rdMolTransforms.GetAngleDeg(_copy_molecule(attached['molecule']).GetConformer(), 1, 0, 2) == pytest.approx(120)
    cleared = edit_geometry({'molecule': attached['molecule'], 'action': 'atom_state', 'atoms': [1], 'hybridization': None})
    assert cleared['atoms'][0]['hybridization_override'] is None
    assert cleared['atoms'][0]['hybridization'] == 'sp3'


@pytest.mark.parametrize('smiles', ['[Fe+2]', '[CH3]'])
def test_unsupported_or_radical_geometry_is_unknown(smiles):
    mol = Chem.MolFromSmiles(smiles)
    mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()))
    atom = geometry_view(mol)['atoms'][0]
    assert atom['hybridization'] is None and atom['lone_pairs'] is None


def _explicit_ethanol():
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles('CCO'))
    assert AllChem.EmbedMolecule(mol, randomSeed=5) == 0
    position = mol.GetConformer().GetAtomPosition(0)
    mol.GetConformer().SetAtomPosition(0, (position.x + .35, position.y, position.z))
    return mol


@pytest.mark.parametrize('engine', ['MMFF94', 'UFF'])
def test_preoptimization_uses_current_coordinates_and_preserves_graph_identity_and_other_conformers(engine):
    from cloudra.tools.core.structure_builder import _make_force_field

    mol = _explicit_ethanol()
    mol.AddConformer(Chem.Conformer(mol.GetConformer()), assignId=True)
    original = geometry_view(mol)
    before = serialize_molecule(mol)
    expected_mol = Chem.Mol(mol)
    expected_force_field = _make_force_field(expected_mol, 0, engine)
    expected_force_field.Initialize()
    expected_energy = expected_force_field.CalcEnergy()
    optimized = edit_geometry({'molecule': original['molecule'], 'action': 'preoptimize', 'force_field': engine})
    report = optimized['optimization']
    assert report['force_field'] == engine and report['energy_unit'] == 'kcal/mol'
    assert report['converged'] is True and report['initial_energy'] > report['final_energy']
    assert report['initial_energy'] == pytest.approx(expected_energy)
    assert [atom['atom_id'] for atom in optimized['atoms']] == [atom['atom_id'] for atom in original['atoms']]
    assert optimized['bonds'] == original['bonds']
    assert optimized['changes']['deleted_atoms'] == [] and optimized['changes']['moved_atoms']
    result = _copy_molecule(optimized['molecule'])
    assert result.GetNumConformers() == 2
    np.testing.assert_array_equal(result.GetConformer(1).GetPositions(), mol.GetConformer(1).GetPositions())
    assert serialize_molecule(mol) == before


def test_preoptimization_retains_exact_aromatic_bonds_and_atom_properties():
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles('c1cc[nH]c1'))
    assert AllChem.EmbedMolecule(mol, randomSeed=2) == 0
    mol.GetAtomWithIdx(0).SetProp('cloudra_hybridization', 'sp2')
    mol.GetAtomWithIdx(0).SetIsotope(13)
    before = geometry_view(mol)
    result = edit_geometry({'molecule': before['molecule'], 'action': 'preoptimize'})
    restored = _copy_molecule(result['molecule'])
    assert result['bonds'] == before['bonds']
    assert restored.GetAtomWithIdx(0).GetIsotope() == 13
    assert restored.GetAtomWithIdx(0).GetProp('cloudra_hybridization') == 'sp2'
    assert [bond.GetIsAromatic() for bond in restored.GetBonds()] == [bond.GetIsAromatic() for bond in mol.GetBonds()]


def test_preoptimization_refuses_sanitization_that_changes_declared_charges():
    mol = Chem.MolFromSmiles('CN(=O)=O', sanitize=False)
    mol.UpdatePropertyCache(strict=False)
    mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()))
    with pytest.raises(ValueError, match='repair formal charges'):
        edit_geometry({'molecule': mol, 'action': 'preoptimize'})


def test_add_atom_keeps_all_conformer_ids_and_coordinates():
    original = chain()
    second = Chem.Conformer(original.GetConformer())
    second.SetId(7)
    second.SetAtomPosition(0, (0, 0, 3))
    original.AddConformer(second, assignId=False)
    result = _copy_molecule(edit_geometry({'molecule': original, 'action': 'add_atom', 'atoms': [1], 'element': 'H'})['molecule'])
    assert [conf.GetId() for conf in result.GetConformers()] == [0, 7]
    for before, after in zip(original.GetConformers(), result.GetConformers(), strict=True):
        np.testing.assert_array_equal(after.GetPositions()[:4], before.GetPositions())
        assert np.linalg.norm(after.GetPositions()[4] - after.GetPositions()[0]) == pytest.approx(1.09)


@pytest.mark.parametrize('smiles,reason', [('C', 'explicit atom'), ('[CH3]', 'radical'), ('[Fe]', 'parameters')])
def test_preoptimization_refuses_incomplete_radical_or_unsupported_graphs(smiles, reason):
    mol = Chem.MolFromSmiles(smiles)
    mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()))
    with pytest.raises(ValueError, match=reason):
        edit_geometry({'molecule': mol, 'action': 'preoptimize'})


def test_preoptimization_rejects_unresolved_graph_and_invalid_requests():
    draft = create_geometry('2\n\nH 0 0 0\nH .74 0 0\n', 'xyz')
    with pytest.raises(ValueError, match='resolved'):
        edit_geometry({'molecule': draft['molecule'], 'action': 'preoptimize'})
    for request in [{'action': 'atom_state', 'atoms': [1], 'hybridization': 'sp3d'},
                    {'action': 'fill_valence', 'atoms': [1], 'hybridization': 'sp2'},
                    {'action': 'atom_state', 'atoms': [1], 'force_field': 'UFF'},
                    {'action': 'preoptimize', 'atoms': [1]},
                    {'action': 'preoptimize', 'force_field': 'automatic'}]:
        with pytest.raises(ValueError):
            edit_geometry({'molecule': draft['molecule'], **request})


def test_preoptimization_has_no_silent_force_field_fallback(monkeypatch):
    from rdkit.Chem import AllChem

    calls = []
    monkeypatch.setattr(AllChem, 'MMFFHasAllMoleculeParams', lambda mol: False)
    monkeypatch.setattr(AllChem, 'UFFGetMoleculeForceField', lambda *args, **kwargs: calls.append('UFF'))
    with pytest.raises(ValueError, match='MMFF94.*no fallback'):
        edit_geometry({'molecule': _explicit_ethanol(), 'action': 'preoptimize'})
    assert not calls


def test_preoptimization_reports_iteration_limit_without_claiming_convergence(monkeypatch):
    from cloudra.tools.core import structure_builder

    make = structure_builder._make_force_field

    class LimitedForceField:
        def __init__(self, force_field):
            self.force_field = force_field

        def Initialize(self):
            self.force_field.Initialize()

        def CalcEnergy(self):
            return self.force_field.CalcEnergy()

        def Minimize(self, **kwargs):
            return self.force_field.Minimize(maxIts=1)

    monkeypatch.setattr(structure_builder, '_make_force_field', lambda *args: LimitedForceField(make(*args)))
    result = edit_geometry({'molecule': _explicit_ethanol(), 'action': 'preoptimize'})
    assert result['optimization']['converged'] is False
    assert any('without convergence' in warning for warning in result['warnings'])


def test_canvas_placement_and_terminal_element_replacement_preserve_the_existing_structure():
    seed = edit_geometry(dict(action='add_atom', element='C', position=(2.5, -1.5, 1)))
    grown = edit_geometry(dict(action='add_group', molecule=seed['molecule'], atoms=[1], smiles='[*]O'))
    assert [a['symbol'] for a in grown['atoms']] == ['C', 'O', 'H']
    assert grown['atoms'][0]['atom_id'] == seed['atoms'][0]['atom_id']
    assert [grown['atoms'][0][axis] for axis in 'xyz'] == [2.5, -1.5, 1]
    assert sorted((b['atom1'], b['atom2'], b['order']) for b in grown['bonds']) == [(1, 2, 1), (2, 3, 1)]
    replaced = edit_geometry(dict(action='atom_state', molecule=grown['molecule'], atoms=[3], element='F'))
    assert [a['symbol'] for a in replaced['atoms']] == ['C', 'O', 'F']
    assert replaced['bonds'] == grown['bonds']
    assert [[a[k] for k in ('atom_id', 'x', 'y', 'z')] for a in replaced['atoms']] == [
        [a[k] for k in ('atom_id', 'x', 'y', 'z')] for a in grown['atoms']]


@pytest.mark.parametrize('fragment,expected', [('[*]C', ['C', 'H', 'H', 'H']), ('[*]N', ['N', 'H', 'H'])])
def test_canvas_blank_places_a_whole_group_at_its_connection_atom(fragment, expected):
    point = (3., -2., 0.5)
    first = edit_geometry(dict(action='add_group', smiles=fragment, position=point))
    assert [a['symbol'] for a in first['atoms']] == expected
    assert tuple(first['atoms'][0][axis] for axis in 'xyz') == point
    other = edit_geometry(dict(action='add_atom', molecule=first['molecule'], element='He', position=(-3, 2, 1)))
    assert other['bonds'] == first['bonds']
    assert [other['atoms'][-1][axis] for axis in 'xyz'] == [-3, 2, 1]


def test_canvas_does_not_use_a_pointer_position_for_bonded_placement_or_attach_a_double_bond_group():
    seed = edit_geometry(dict(action='add_atom', element='C'))['molecule']
    with pytest.raises(ValueError, match='position'):
        edit_geometry(dict(action='add_atom', molecule=seed, element='O', atoms=[1], position=(0, 0, 0)))
    with pytest.raises(ValueError, match='单键'):
        edit_geometry(dict(action='add_group', molecule=seed, smiles='[*]=O', atoms=[1]))


@pytest.mark.parametrize('smiles', ['[*][C@](F)(Cl)Br', 'F[C@]([*])(Cl)Br', '[*]/C=C/F',
                                    r'[*]/C=C\F', '[*]/N=C/F', '[*]C[C@H](Cl)F'])
def test_attaching_a_group_preserves_declared_stereochemistry(smiles):
    seed = edit_geometry(dict(action='add_atom', element='I'))
    grown = edit_geometry(dict(action='add_group', smiles=smiles, molecule=seed['molecule'], atoms=[1]))
    mol = Chem.RemoveHs(_copy_molecule(grown['molecule']))
    expected = Chem.MolToSmiles(Chem.MolFromSmiles(smiles.replace('[*]', 'I')))
    assert Chem.MolToSmiles(mol) == expected
    Chem.AssignStereochemistryFrom3D(mol, replaceExistingTags=True)
    assert Chem.MolToSmiles(mol) == expected


def test_disconnected_imine_reports_when_its_declared_stereo_requires_the_anchor():
    with pytest.raises(ValueError, match='点击已有原子'):
        edit_geometry(dict(action='add_group', smiles='[*]/N=C/F'))
