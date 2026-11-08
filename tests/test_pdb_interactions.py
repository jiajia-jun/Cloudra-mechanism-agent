"""Interaction evidence is reported without promoting contacts to chemical bonds."""

import importlib
import math

import pytest


def _module():
    return importlib.import_module('cloudra.tools.core.pdb_interactions')


def _structure(residues):
    gemmi = pytest.importorskip('gemmi')
    structure = gemmi.Structure()
    structure.add_model(gemmi.Model('1'))
    keys = {}
    for index, (chain_name, residue_name, atoms) in enumerate(residues):
        chain = gemmi.Chain(chain_name)
        residue = gemmi.Residue()
        residue.name = residue_name
        residue.seqid = gemmi.SeqId(index + 1, ' ')
        residue.het_flag = 'A' if residue_name in {'LYS', 'ASP', 'HIS'} else 'H'
        for item in atoms:
            name, element, position, *altloc = item
            atom = gemmi.Atom()
            atom.name = name
            atom.element = gemmi.Element(element)
            atom.pos = gemmi.Position(*position)
            atom.occ = 0.6
            atom.b_iso = 12.5
            if altloc:
                atom.altloc = altloc[0]
            residue.add_atom(atom)
        chain.add_residue(residue)
        structure[0].add_chain(chain)
        keys[index, 0] = f'opaque/residue/{index}'
    structure.assign_serial_numbers()
    return structure, keys


def _backend():
    pytest.importorskip('plip.basic.config')
    pytest.importorskip('plip.structure.preparation', exc_type=ImportError)


def _bridge_structure():
    # A deliberately small, local coordinate fixture, not a fitted biological model.
    return _structure([
        ('protein_author_chain', 'LYS', [('NZ', 'N', (-3, 0, 0)),
                                       ('HZ1', 'H', (-2, 0, 0)),
                                       ('CE', 'C', (-4.3, 0, 0))]),
        ('ligand_author_chain', 'LIG', [('O1', 'O', (0, 3, 0)),
                                      ('C1', 'C', (0, 4.2, 0)),
                                      ('C2', 'C', (1.3, 4.9, 0)),
                                      ('C3', 'C', (-1.3, 4.9, 0))]),
        ('water_author_chain', 'HOH', [('O', 'O', (0, 0, 0))]),
    ])


@pytest.mark.parametrize('overrides', [
    {'distance': 3.0}, {'METAL_DIST_MAX': math.nan}, {'METAL_DIST_MAX': math.inf},
    {'METAL_DIST_MAX': 0}, {'WATER_BRIDGE_THETA_MIN': 181},
    {'WATER_BRIDGE_OMEGA_MIN': -1}, {'WATER_BRIDGE_MAXDIST': True},
    {'WATER_BRIDGE_MINDIST': 4, 'WATER_BRIDGE_MAXDIST': 3},
    {'WATER_BRIDGE_OMEGA_MIN': 140, 'WATER_BRIDGE_OMEGA_MAX': 100},
])
def test_override_validation_rejects_unknown_nonfinite_and_invalid_ranges(overrides):
    with pytest.raises(ValueError):
        _module().validate_interaction_overrides(overrides)


def test_override_validation_does_not_load_optional_libraries(monkeypatch):
    module = _module()
    def forbidden_import(name):
        raise AssertionError(f'validation imported {name}')
    monkeypatch.setattr(module.importlib, 'import_module', forbidden_import)
    module.validate_interaction_overrides({'METAL_DIST_MAX': 3.2})


def test_real_plip_water_bridge_maps_original_atoms_and_rules_without_mutating_input():
    _backend()
    module = _module()
    structure, keys = _bridge_structure()
    before = structure.make_mmcif_document().as_string()
    result = module.analyze_interactions(structure, keys, {})
    assert result['analysis_status']['plip']['status'] == 'completed'
    assert result['backend_versions']['plip']
    assert result['backend_versions']['openbabel']
    water = result['water_candidates'][0]
    assert water['residue_key'] == keys[2, 0]
    assert 'plip_water_bridge' in water['reasons']
    bridge = next(bridge for bridge in water['plip_water_bridges'] if bridge['protein_is_donor'])
    assert bridge['acceptor']['chain'] == 'ligand_author_chain'
    assert bridge['acceptor']['atom_name'] == 'O1'
    assert bridge['donor']['residue_key'] == keys[0, 0]
    assert bridge['distance_aw'] == pytest.approx(3)
    assert bridge['donor_angle'] == pytest.approx(180)
    assert bridge['water_angle'] == pytest.approx(90)
    assert water['water']['occupancy'] == pytest.approx(0.6)
    assert water['water']['b_factor'] == pytest.approx(12.5)
    from plip.basic import config
    assert result['effective_rules']['parameters']['WATER_BRIDGE_MAXDIST']['value'] == config.WATER_BRIDGE_MAXDIST
    assert structure.make_mmcif_document().as_string() == before


def test_geometry_keeps_altlocs_separate_and_ignores_crystal_images():
    _backend()
    gemmi = pytest.importorskip('gemmi')
    structure, keys = _structure([
        ('W', 'HOH', [('O', 'O', (0, 0, 0), 'A')]),
        ('P', 'ASP', [('OD1', 'O', (3, 0, 0), 'A'),
                      ('OD1', 'O', (0, 3, 0), 'B'),
                      ('OD2', 'O', (9, 0, 0))]),
        ('Z', 'ZN', [('ZN', 'Zn', (2, 0, 0))]),
        ('Q', 'HOH', [('O', 'O', (0, 0, 3), 'A')]),
    ])
    structure.cell = gemmi.UnitCell(10, 10, 10, 90, 90, 90)
    structure.spacegroup_hm = 'P 1'
    structure.setup_cell_images()
    result = _module().analyze_interactions(structure, keys, {})
    water = next(w for w in result['water_candidates'] if w['residue_key'] == keys[0, 0])
    assert [(a['atom_name'], a['altloc']) for a in water['polar_contacts']] == [('OD1', 'A')]
    assert 'metal_related_water' in water['reasons']
    assert result['analysis_status']['plip']['status'] == 'completed'
    assert result['analysis_status']['water_candidates']['status'] == 'completed'
    assert result['metal_sites'][0]['candidates']


def test_actual_overrides_change_geometry_and_restore_plip_global_config():
    _backend()
    from plip.basic import config
    structure, keys = _bridge_structure()
    previous = config.WATER_BRIDGE_MAXDIST
    result = _module().analyze_interactions(structure, keys, {'WATER_BRIDGE_MAXDIST': 2.9})
    assert not result['water_candidates']
    assert config.WATER_BRIDGE_MAXDIST == previous
    assert result['effective_rules']['parameters']['WATER_BRIDGE_MAXDIST']['source'] == 'override'
    with pytest.raises(ValueError, match='MINDIST'):
        _module().analyze_interactions(structure, keys, {'WATER_BRIDGE_MAXDIST': 2.0})


def test_no_ligand_does_not_create_a_plip_bridge():
    _backend()
    structure, keys = _structure([
        ('P', 'ASP', [('OD1', 'O', (3, 0, 0))]),
        ('W', 'HOH', [('O', 'O', (0, 0, 0))]),
    ])
    result = _module().analyze_interactions(structure, keys, {})
    assert result['analysis_status']['plip']['status'] == 'completed'
    assert result['water_candidates'][0]['reasons'] == ['polar_contact_candidate']
    assert not result['water_candidates'][0]['plip_water_bridges']


def test_missing_plip_does_not_invent_thresholds_and_keeps_metal_inventory(monkeypatch):
    module = _module()
    structure, keys = _structure([('Z', 'ZN', [('ZN', 'Zn', (0, 0, 0))])])
    original_import = module.importlib.import_module
    def import_without_plip(name, *args, **kwargs):
        if name.startswith('plip'):
            raise ModuleNotFoundError('PLIP intentionally absent')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(module.importlib, 'import_module', import_without_plip)
    result = module.analyze_interactions(structure, keys, {})
    assert result['analysis_status']['water_candidates']['status'] == 'unavailable'
    assert result['analysis_status']['metal_sites']['status'] == 'unavailable'
    assert result['effective_rules']['parameters'] == {}
    assert result['metal_sites'][0]['element'] == 'Zn'
    assert result['metal_sites'][0]['candidates'] == []


def test_missing_plip_engine_preserves_real_config_distance_results(monkeypatch):
    _backend()
    module = _module()
    structure, keys = _bridge_structure()
    original_import = module.importlib.import_module
    def import_without_engine(name, *args, **kwargs):
        if name == 'plip.structure.preparation':
            raise ModuleNotFoundError('OpenBabel intentionally absent')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(module.importlib, 'import_module', import_without_engine)
    result = module.analyze_interactions(structure, keys, {})
    assert result['water_candidates'][0]['polar_contacts']
    assert result['analysis_status']['plip']['status'] == 'unavailable'
    assert result['analysis_status']['water_candidates']['status'] == 'unavailable'


def test_real_metal_candidates_cover_protein_water_and_cofactor_metal_and_links():
    _backend()
    gemmi = pytest.importorskip('gemmi')
    structure, keys = _structure([
        ('protein_chain', 'ASP', [('OD1', 'O', (2.2, 0, 0)), ('CG', 'C', (3.5, 0, 0))]),
        ('cofactor_chain', 'HEM', [('FE', 'Fe', (0, 0, 0)), ('NA', 'N', (-2.1, 0, 0)),
                                 ('C1', 'C', (-3.3, 0.8, 0)), ('C2', 'C', (-3.3, -0.8, 0))]),
        ('water_chain', 'HOH', [('O', 'O', (0, 2.3, 0))]),
    ])
    connection = gemmi.Connection()
    connection.name = 'input_metal_link'
    connection.type = gemmi.ConnectionType.MetalC
    connection.partner1 = gemmi.AtomAddress('cofactor_chain', gemmi.SeqId(2, ' '), 'HEM', 'FE')
    connection.partner2 = gemmi.AtomAddress('protein_chain', gemmi.SeqId(1, ' '), 'ASP', 'OD1')
    connection.reported_distance = 2.2
    structure.connections.append(connection)
    result = _module().analyze_interactions(structure, keys, {})
    site = result['metal_sites'][0]
    assert site['element'] == 'Fe'
    assert {a['residue_key'] for a in site['candidates']} == set(keys.values())
    assert site['explicit_connections'][0]['connection_name'] == 'input_metal_link'
    assert site['explicit_connections'][0]['atom']['atom_name'] == 'OD1'
    assert site['plip_interactions']
    assert any(i['location'] == 'water' for i in site['plip_interactions'])
    assert any(i['donor_type'] == 'O' for i in site['plip_interactions'])
    assert all('geometry' in i for i in site['plip_interactions'])
    assert 'metal_related_water' in result['water_candidates'][0]['reasons']


def test_temporary_serialization_failure_preserves_geometry_results(monkeypatch):
    _backend()
    module = _module()
    structure, keys = _bridge_structure()
    def broken_temporary_copy(*args):
        raise OSError('temporary write failed')
    monkeypatch.setattr(module, '_plip_input', broken_temporary_copy)
    result = module.analyze_interactions(structure, keys, {})
    assert result['analysis_status']['plip']['status'] == 'failed'
    assert 'temporary write failed' in result['analysis_status']['plip']['reason']
    assert result['water_candidates'][0]['polar_contacts']


def test_one_failed_plip_ligand_does_not_erase_other_completed_sites(monkeypatch):
    _backend()
    from plip.basic import config
    from plip.structure import preparation
    structure, keys = _bridge_structure()
    chain = structure[0][1].clone()
    chain.name = 'failed_ligand_author_chain'
    chain[0].name = 'BAD'
    for atom in chain[0]:
        atom.pos.x += 20
    structure[0].add_chain(chain)
    keys[3, 0] = 'opaque/residue/failed'
    original = preparation.PDBComplex.characterize_complex
    def fail_one_ligand(self, ligand):
        if ligand.hetid == 'BAD':
            raise RuntimeError('one ligand failed')
        return original(self, ligand)
    previous = config.METAL_DIST_MAX
    monkeypatch.setattr(preparation.PDBComplex, 'characterize_complex', fail_one_ligand)
    result = _module().analyze_interactions(structure, keys, {'METAL_DIST_MAX': 3.2})
    assert result['analysis_status']['plip']['status'] == 'failed'
    assert 'one ligand failed' in result['analysis_status']['plip']['reason']
    assert result['water_candidates'][0]['plip_water_bridges']
    assert config.METAL_DIST_MAX == previous


def test_nonfinite_coordinates_fail_before_optional_backend_lookup(monkeypatch):
    module = _module()
    gemmi = pytest.importorskip('gemmi')
    structure, keys = _bridge_structure()
    structure[0][0][0][0].pos.x = math.nan
    def no_optional_backend(name):
        if name == 'gemmi':
            return gemmi
        raise AssertionError('optional backend attempted before coordinate validation')
    monkeypatch.setattr(module.importlib, 'import_module', no_optional_backend)
    with pytest.raises(ValueError, match='finite'):
        module.analyze_interactions(structure, keys, {})


def test_real_plip_retained_conformers_map_original_indices_without_mixing():
    _backend()
    structure, keys = _bridge_structure()
    for chain in structure[0]:
        for residue in chain:
            count = len(residue)
            for ai in range(count):
                residue[ai].altloc = 'A'
                alternate = residue[ai].clone()
                alternate.altloc = 'B'
                alternate.pos.x += 20
                residue.add_atom(alternate)
    result = _module().analyze_interactions(structure, keys, {})
    assert result['analysis_status']['plip']['status'] == 'completed'
    assert {water['water']['altloc'] for water in result['water_candidates']} == {'A', 'B'}
    for water in result['water_candidates']:
        bridges = water['plip_water_bridges']
        assert bridges
        for bridge in bridges:
            assert bridge['donor']['altloc'] == water['water']['altloc']
            assert bridge['acceptor']['altloc'] == water['water']['altloc']
            assert bridge['donor']['residue_key'] in {keys[0, 0], keys[1, 0]}


def test_real_plip_never_bridges_incompatible_selected_protein_and_water():
    _backend()
    structure, keys = _bridge_structure()
    for atom in structure[0][0][0]:
        atom.altloc = 'A'
    structure[0][2][0][0].altloc = 'B'
    result = _module().analyze_interactions(structure, keys, {})
    assert result['analysis_status']['plip']['status'] == 'completed'
    water = result['water_candidates'][0]
    assert all(contact['residue_key'] != keys[0, 0] for contact in water['polar_contacts'])
    assert not water['plip_water_bridges']


def test_identical_shared_atom_plip_bridges_are_deduplicated_between_conformers():
    _backend()
    structure, keys = _bridge_structure()
    gemmi = pytest.importorskip('gemmi')
    chain = gemmi.Chain('remote_alternates')
    residue = gemmi.Residue()
    residue.name = 'ASP'
    residue.het_flag = 'A'
    residue.seqid = gemmi.SeqId(9, ' ')
    for label, x in [('A', 100), ('B', 110)]:
        atom = gemmi.Atom()
        atom.name = 'OD1'
        atom.element = gemmi.Element('O')
        atom.pos = gemmi.Position(x, 0, 0)
        atom.altloc = label
        residue.add_atom(atom)
    chain.add_residue(residue)
    structure[0].add_chain(chain)
    keys[3, 0] = 'opaque/remote'
    result = _module().analyze_interactions(structure, keys, {})
    assert result['analysis_status']['plip']['status'] == 'completed'
    bridges = result['water_candidates'][0]['plip_water_bridges']
    assert len([bridge for bridge in bridges if bridge['protein_is_donor']]) == 1


def test_same_conformer_duplicate_atom_names_remain_unsupported():
    _backend()
    structure, keys = _bridge_structure()
    duplicate = structure[0][0][0][0].clone()
    structure[0][0][0].add_atom(duplicate)
    result = _module().analyze_interactions(structure, keys, {})
    assert result['analysis_status']['plip']['status'] == 'unsupported'
    assert 'duplicate' in result['analysis_status']['plip']['reason'].lower()


def test_real_plip_first_does_not_break_later_optional_rdkit_import():
    """OpenBabel's native libraries must not poison the existing tool catalog."""
    import importlib.util
    import subprocess
    import sys

    if importlib.util.find_spec('rdkit') is None:
        pytest.skip('requires optional RDKit for native-library interoperability regression')
    pytest.importorskip('gemmi')
    pytest.importorskip('plip')
    code = '''
import gemmi
from cloudra.tools.core.pdb_interactions import analyze_interactions
structure = gemmi.read_pdb_string('ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 10.00           N  \\nEND\\n')
structure.setup_entities()
result = analyze_interactions(structure, {(0,0): 'A/ALA 1'}, {})
assert result['analysis_status']['plip']['status'] == 'completed', result
from rdkit import Chem
assert Chem.MolFromSmiles('CCO').GetNumAtoms() == 3
'''
    child = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert child.returncode == 0, f'Native interoperability child failed ({child.returncode}): {child.stderr}'
