"""Workbench documents retain native point identity and read geometry on demand."""

import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cloudra.tools.core import gaussian_frames, orca_frames
from cloudra.tools.core.workbench_results import document_csv, document_frame, open_document

FIXTURES = Path(__file__).parent / 'fixtures'


def test_multiframe_xyz_defaults_latest_and_caches_only_scalars(tmp_path):
    source = tmp_path / 'frames.xyz'
    source.write_text('1\nfirst\nH 0 0 0\n1\nsecond\nH 2 0 0\n')
    cache = tmp_path / 'cache'
    view = open_document(source, cache)
    assert len(view['frames']) == 2
    assert view['selected_frame'] == 1
    assert view['geometry']['atoms'][0]['x'] == 2
    assert document_frame(cache, view['document_id'], 0)['atoms'][0]['x'] == 0
    assert all('xyz' not in frame and 'molecule' not in frame for frame in view['frames'])
    assert open_document(source, cache, frame_index=0)['selected_frame'] == 0
    source.write_text('1\nchanged\nH 5 0 0\n')
    updated = open_document(source, cache)
    assert len(updated['frames']) == 1
    assert updated['geometry']['atoms'][0]['x'] == 5
    with pytest.raises(ValueError, match='frame'):
        document_frame(cache, updated['document_id'], -1)
    with pytest.raises(ValueError, match='document'):
        document_frame(cache, '../outside', 0)


@pytest.mark.parametrize(('engine', 'filename', 'count', 'first_energy'), [
    ('gaussian', 'water_opt_freq_g16.out', 5, -74.9643287914),
    ('orca', 'dvb_opt_orca42.out', 4, -382.050758129878),
])
def test_native_optimization_frame_energy_and_force_facts(tmp_path, engine, filename, count, first_energy):
    view = open_document(FIXTURES / engine / filename, tmp_path / 'cache')
    assert len(view['frames']) == count
    assert view['frames'][0]['energy_hartree'] == pytest.approx(first_energy, abs=1e-6)
    force_frames = [frame for frame in view['frames'] if frame.get('rms_force') is not None]
    assert force_frames
    assert all(frame['rms_force'] != frame['max_force'] for frame in force_frames)
    assert all(frame['force_unit'] == 'Eh/Bohr' for frame in force_frames)
    assert view['frames'][-1]['converged'] is True
    rows = list(csv.DictReader(io.StringIO(document_csv(tmp_path / 'cache', view['document_id']))))
    assert len(rows) == count
    assert rows[0]['rms_force'] == str(view['frames'][0]['rms_force'])


@pytest.mark.parametrize(('engine', 'filename'), [
    ('gaussian', 'water_opt_freq_g16.out'), ('orca', 'co2_freq_orca42.out'),
])
def test_real_modes_have_native_reference_geometry(tmp_path, engine, filename):
    view = open_document(FIXTURES / engine / filename, tmp_path / 'cache')
    assert view['modes']
    reference = view['modes_reference_geometry']
    assert reference is not None
    assert all(len(mode['displacements']) == len(reference['atoms']) for mode in view['modes'])
    assert any(any(abs(value) > 0 for row in mode['displacements'] for value in row) for mode in view['modes'])


def test_scan_preserves_every_coordinate_dimension(monkeypatch):
    data = SimpleNamespace(scanenergies=np.array([-27.211386245988, -54.422772491976]),
                           scanparm=[[1.0, 1.1], [90.0, 100.0]],
                           scancoords=np.array([[[0, 0, 0]], [[1, 0, 0]]]), atomnos=[1])
    monkeypatch.setattr(gaussian_frames, '_ccread_from_text', lambda _: data)
    frames = gaussian_frames._extract_scan_frames('native scan')
    assert frames[0].scan_coordinates == [1.0, 90.0]
    assert frames[1].scan_coordinates == [1.1, 100.0]
    assert frames[0].reaction_coordinate is None  # multidimensional PES is not one scalar path


def test_optimization_never_zips_unrelated_energy_and_geometry_arrays(monkeypatch):
    data = SimpleNamespace(scfenergies=[-27.2, -54.4], atomcoords=[[[0, 0, 0]]], atomnos=[1])
    monkeypatch.setattr(gaussian_frames, '_ccread_from_text', lambda _: data)
    assert gaussian_frames._extract_opt_frames('no native geometries') == []
    monkeypatch.setattr(orca_frames, '_ccread_from_text', lambda _: data)
    assert orca_frames._extract_opt_frames('no native geometries') == []


def test_orca_unrelaxed_scan_coordinates_and_geometry(tmp_path):
    view = open_document(FIXTURES / 'orca' / 'dvb_scan_unrelaxed_orca42.out', tmp_path / 'cache')
    assert len(view['frames']) == 12
    assert view['frames'][1]['scan_coordinates'] == pytest.approx([32.72727273])
    assert view['geometry']['atoms']
    assert view['frames'][0]['energy_hartree'] == pytest.approx(-375.825060199741)


def test_gaussian_irc_has_only_native_path_points(tmp_path):
    view = open_document(FIXTURES / 'gaussian' / 'hcn_ts_irc_g16.log', tmp_path / 'cache')
    assert len(view['frames']) == 21
    assert view['frames'][0]['reaction_coordinate'] == pytest.approx(-0.80848)
    assert view['frames'][0]['path_number'] == 2


def test_orca_irc_sidecar_uses_own_energies_without_fabricating_coordinate(tmp_path):
    source = tmp_path / 'job.out'
    source.write_text((FIXTURES / 'orca' / 'hcn_irc_orca60.out').read_text())
    sidecar = tmp_path / 'job_IRC_F_trj.xyz'
    sidecar.write_text('1\nCoordinates from ORCA-job job E -3.0\nH 0 0 0\n'
                       '1\nCoordinates from ORCA-job job E -4.0\nH 1 0 0\n')
    view = open_document(source, tmp_path / 'cache')
    assert len(view['frames']) == 2
    assert [frame['energy_hartree'] for frame in view['frames']] == [-3., -4.]
    assert all(frame['path_number'] == 1 for frame in view['frames'])
    assert all(frame.get('reaction_coordinate') is None for frame in view['frames'])
    sidecar.write_text('1\nCoordinates from ORCA-job job E -5.0\nH 2 0 0\n')
    assert open_document(source, tmp_path / 'cache')['frames'][0]['energy_hartree'] == -5.


def test_saved_native_molecule_reopens_bonds_and_settings(tmp_path):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.molecule import serialize_molecule

    mol = Chem.AddHs(Chem.MolFromSmiles('CO'))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    path = tmp_path / 'structure.cloudra'
    path.write_text(json.dumps({'title': 'Edited', 'molecule': serialize_molecule(mol),
                                'settings': {'method': 'HF', 'basis': 'STO-3G'},
                                'frozen_coordinates': [{'atoms': [1, 2], 'value': 1.4}]}))
    view = open_document(path, tmp_path / 'cache')
    assert view['title'] == 'Edited'
    assert len(view['geometry']['bonds']) == mol.GetNumBonds()
    assert view['settings']['method'] == 'HF'
    assert view['frozen_coordinates'][0]['value'] == 1.4
    assert view['frames'][0].get('energy_hartree') is None


@pytest.mark.parametrize('filename', ['trajectory.json', 'frames.xyz'])
def test_existing_forcefield_trajectory_preserves_units_and_max_gradient(tmp_path, filename):
    from cloudra.tools.core.structure_artifacts import TrajectoryWriter

    writer = TrajectoryWriter(str(tmp_path), 'test-MMFF94-attempt1', 'test', 1, 'MMFF94', ['H'], None)
    writer.append(0, [[0, 0, 0]], 2., .4)
    writer.append(1, [[1, 0, 0]], 1., .1)
    record = writer.finish(0, 'converged')
    view = open_document(Path(record.frames_path).with_name(filename), tmp_path / 'cache')
    assert len(view['frames']) == 2
    assert view['frames'][0]['energy'] == 2.
    assert view['frames'][0]['energy_unit'] == 'kcal/mol'
    assert view['frames'][0]['max_force'] == .4
    assert view['frames'][0].get('rms_force') is None
    assert view['frames'][0]['energy_hartree'] == pytest.approx(2. / 627.5095, rel=1e-5)


def test_frame_atom_identity_is_stable_across_geometry_fetch_and_modes(tmp_path):
    view = open_document(FIXTURES / 'gaussian' / 'water_opt_freq_g16.out', tmp_path / 'cache')
    first = document_frame(tmp_path / 'cache', view['document_id'], 0)
    last_ids = [atom['atom_id'] for atom in view['geometry']['atoms']]
    assert [atom['atom_id'] for atom in first['atoms']] == last_ids
    assert [atom['atom_id'] for atom in view['modes_reference_geometry']['atoms']] == last_ids


def test_signed_modes_do_not_follow_later_linked_geometry(tmp_path):
    source = tmp_path / 'linked.log'
    text = (FIXTURES / 'gaussian' / 'water_opt_freq_g16.out').read_text()
    text = text.replace('Frequencies --   2169.7613', 'Frequencies --  -2169.7613')
    orientation = ''' Standard orientation:
 ---------------------------------------------------------------------
 Center     Atomic      Atomic             Coordinates (Angstroms)
 Number     Number       Type             X           Y           Z
 ---------------------------------------------------------------------
      1          1           0        10.000000    0.000000    0.000000
 ---------------------------------------------------------------------
 SCF Done:  E(RHF) = -0.5 A.U. after 1 cycles
'''
    source.write_text(text + '\n' + orientation)
    view = open_document(source, tmp_path / 'cache')
    assert view['geometry']['atoms'][0]['x'] == 10
    assert len(view['modes_reference_geometry']['atoms']) == 3
    assert view['modes'][0]['frequency_cm'] == pytest.approx(-2169.7613)


def test_orca_missing_mode_columns_remain_unavailable():
    text = ('VIBRATIONAL FREQUENCIES\n0: -1.0 cm**-1\n1: 0.0 cm**-1\n2: 1.0 cm**-1\n'
            'NORMAL MODES\n0\n0 0.2\n1 0.3\n2 0.4\n')
    assert orca_frames.vibdisps_from_text(text, 3, 1) is None


def test_orca_multidimensional_scan_binds_energy_before_unevaluated_geometry():
    text = '''TRAJECTORY STEP 1
 B1 : 1.2
 D2 : 180.0
 CARTESIAN COORDINATES (ANGSTROEM)
 ---------------------------------
 H 0.0 0.0 0.0

 FINAL SINGLE POINT ENERGY -1.0
 CARTESIAN COORDINATES (ANGSTROEM)
 ---------------------------------
 H 7.0 0.0 0.0

 TRAJECTORY STEP 2
 B1 : 1.4
 D2 : 190.0
 CARTESIAN COORDINATES (ANGSTROEM)
 ---------------------------------
 H 2.0 0.0 0.0

 FINAL SINGLE POINT ENERGY -2.0
'''
    frames = orca_frames._extract_scan_frames(text)
    assert frames[0].scan_coordinates == [1.2, 180.]
    assert frames[0].reaction_coordinate is None
    assert float(frames[0].xyz.splitlines()[2].split()[1]) == 0.
    assert frames[0].electronic_energy_hartree == -1.
    assert float(frames[1].xyz.splitlines()[2].split()[1]) == 2.


def test_orca_relaxed_pes_heading_keeps_all_native_dimensions():
    text = '''* RELAXED SURFACE SCAN STEP 12 *
 * *
 * Dihedral (11, 10, 3, 4) : 180.00000000 *
 * Bond (1, 2) : 1.40000000 *
 CARTESIAN COORDINATES (ANGSTROEM)
 ---------------------------------
 H 0.0 0.0 0.0

 FINAL SINGLE POINT ENERGY -1.0
'''
    frame = orca_frames._extract_scan_frames(text)[0]
    assert frame.scan_coordinates == [180., 1.4]
    assert frame.reaction_coordinate is None


def test_orca_unevaluated_final_optimization_geometry_has_no_inherited_energy():
    text = '''GEOMETRY OPTIMIZATION CYCLE 1
 CARTESIAN COORDINATES (ANGSTROEM)
 ---------------------------------
 H 0.0 0.0 0.0

 Current Energy .... -1.0 Eh
 CARTESIAN COORDINATES (ANGSTROEM)
 ---------------------------------
 H 7.0 0.0 0.0

'''
    frames = orca_frames._extract_opt_frames(text)
    assert frames[0].electronic_energy_hartree == -1.
    assert frames[-1].electronic_energy_hartree is None


@pytest.mark.parametrize(('engine', 'filename'), [('gaussian', 'he.gjf'), ('orca', 'he.inp')])
def test_native_inputs_open_their_actual_geometry(tmp_path, engine, filename):
    source = FIXTURES / 'compute_backends' / engine / filename
    view = open_document(source, tmp_path / 'cache')
    assert view['task_type'] == 'structure'
    assert [atom['symbol'] for atom in view['geometry']['atoms']] == ['He']
    assert view['frames'][0].get('energy_hartree') is None


def test_sdf_preserves_multiple_native_graphs_and_selects_last(tmp_path):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    path = tmp_path / 'structures.sdf'
    with Chem.SDWriter(str(path)) as writer:
        for smiles in ('C', 'CC'):
            mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
            AllChem.EmbedMolecule(mol, randomSeed=1)
            writer.write(mol)
    view = open_document(path, tmp_path / 'cache')
    assert len(view['frames']) == 2
    assert view['selected_frame'] == 1
    assert len(view['geometry']['bonds']) == 7
    assert len(document_frame(tmp_path / 'cache', view['document_id'], 0)['bonds']) == 4


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_single_point_never_inherits_energy_for_new_unevaluated_geometry(engine):
    if engine == 'gaussian':
        def geometry(x):
            return (f' Standard orientation:\n-----\n header\n-----\n'
                    f' 1 1 0 {x}.0 0.0 0.0\n-----\n')
        text = geometry(0) + ' SCF Done: E(RHF) = -1.0 A.U. after 1 cycles\n' + geometry(7)
        frame = gaussian_frames._extract_sp_frames(text)[0]
    else:
        def geometry(x):
            return f'CARTESIAN COORDINATES (ANGSTROEM)\n-----\nH {x}.0 0.0 0.0\n\n'
        text = geometry(0) + 'FINAL SINGLE POINT ENERGY -1.0\n' + geometry(7)
        frame = orca_frames._extract_sp_frames(text)[0]
    assert frame.electronic_energy_hartree is None
    assert float(frame.xyz.splitlines()[2].split()[1]) == 7.


def test_default_frame_is_latest_actual_geometry_with_scalar_tail_preserved(tmp_path, monkeypatch):
    source = FIXTURES / 'gaussian' / 'water_opt_freq_g16.out'
    monkeypatch.setattr(gaussian_frames, 'extract_frames_from_text', lambda _: [
        gaussian_frames.FrameRecord(frame=0, xyz='1\nfirst\nH 0 0 0\n', electronic_energy_hartree=-1.),
        gaussian_frames.FrameRecord(frame=1, electronic_energy_hartree=-2.),
    ])
    view = open_document(source, tmp_path / 'cache')
    assert view['selected_frame'] == 0
    assert [frame['has_geometry'] for frame in view['frames']] == [True, False]
    assert len(view['frames']) == 2 and view['warnings']
    assert open_document(source, tmp_path / 'cache', 1)['geometry'] is None


def test_scalar_only_document_stays_viewable_without_a_fake_geometry(tmp_path, monkeypatch):
    source = FIXTURES / 'gaussian' / 'water_opt_freq_g16.out'
    monkeypatch.setattr(gaussian_frames, 'extract_frames_from_text', lambda _: [
        gaussian_frames.FrameRecord(frame=0, electronic_energy_hartree=-1.),
    ])
    view = open_document(source, tmp_path / 'cache')
    assert view['geometry'] is None
    assert view['frames'][0]['has_geometry'] is False
    assert view['warnings']


@pytest.mark.parametrize('symlink', [False, True])
def test_workbench_orca_does_not_read_external_sidecars(tmp_path, symlink):
    project = tmp_path / 'project'
    project.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    source = project / 'job.out'
    source.write_text((FIXTURES / 'orca' / 'hcn_irc_orca60.out').read_text()
                      + f'\nNAME = {outside / "job.inp"}\n')
    secret = outside / 'job_IRC_F_trj.xyz'
    secret.write_text('1\nCoordinates from ORCA-job job E -4.0\nH 9 0 0\n')
    if symlink:
        (project / secret.name).symlink_to(secret)
    with pytest.raises(ValueError, match='IRC|frames'):
        open_document(source, project / 'cache')


def test_cache_fingerprint_excludes_other_job_prefixes(tmp_path):
    from cloudra.tools.core.workbench_results import _source_files

    source = tmp_path / 'job.out'
    source.write_text((FIXTURES / 'orca' / 'hcn_irc_orca60.out').read_text())
    unrelated = tmp_path / 'job2.xyz'
    unrelated.write_text('1\nother\nH 0 0 0\n')
    assert unrelated not in _source_files(source)


def test_old_document_cache_is_rebuilt_when_scalar_contract_changes(tmp_path):
    source = tmp_path / 'one.xyz'
    source.write_text('1\nstructure\nH 0 0 0\n')
    cache = tmp_path / 'cache'
    view = open_document(source, cache)
    metadata_file = cache / view['document_id'] / 'document.json'
    metadata = json.loads(metadata_file.read_text())
    metadata.pop('_format_version', None)
    metadata['frames'][0].pop('has_geometry')
    metadata_file.write_text(json.dumps(metadata))
    assert open_document(source, cache)['frames'][0]['has_geometry'] is True


def test_forcefield_manifest_symlink_cannot_read_an_external_document(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    source = project / 'frames.xyz'
    source.write_text('1\nstructure\nH 0 0 0\n')
    external = tmp_path / 'secret.json'
    external.write_text('{}')
    source.with_name('trajectory.json').symlink_to(external)
    from cloudra.tools.core import structure_artifacts

    def forbidden(_):
        pytest.fail('External trajectory manifest must never be read')
    monkeypatch.setattr(structure_artifacts, 'read_trajectory', forbidden)
    with pytest.raises(ValueError, match='source directory'):
        open_document(source, project / 'cache')
