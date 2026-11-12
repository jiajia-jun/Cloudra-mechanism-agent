import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms, FixCartesian
from ase.io import read
from ase.units import Bohr, Hartree


@pytest.fixture
def images():
    return [
        Atoms('CuH', positions=[[0, 0, 0], [x, 1, 2]], cell=[8, 9, 20], pbc=[True, True, False],
              constraint=FixAtoms(indices=[0]))
        for x in (1, 2, 3)
    ]


def _native_band(step, energies=(-24.815, -24.80061, -24.815)):
    # CP2K v2025.2 src/motion/neb_io.F:270–337, also the v2026.2 compact format.
    return (
        ' *******************************************************************************\n'
        ' BAND TYPE                     =                                          CI-NEB\n'
        ' BAND TYPE OPTIMIZATION        =                                            DIIS\n'
        f' STEP NUMBER                   = {step:47d}\n'
        f' NUMBER OF NEB REPLICA         = {len(energies):47d}\n'
        ' DISTANCES REP =' + '        0.250000' * (len(energies) - 1) + '\n'
        +        ' ENERGIES [au] =' + ''.join(f'{value:16.6f}' for value in energies[:4]) + '\n'
        + (' ' * 16 + ''.join(f'{value:16.6f}' for value in energies[4:]) + '\n' if len(energies) > 4 else '')
        + ' BAND TOTAL ENERGY [au]        =                              -74.43060834560000\n'
        ' *******************************************************************************\n'
    )


_NATIVE_CONVERGENCE = (
    ' *******************************************************************************\n'
    ' RMS DISPLACEMENT =   0.00001      [ 0.00010]                                (YES)\n'
    ' MAX DISPLACEMENT =   0.00002      [ 0.00020]                                (YES)\n'
    ' RMS FORCE        =   0.00003      [ 0.00030]                                (YES)\n'
    ' MAX FORCE        =   0.00004      [ 0.00045]                                (YES)\n'
    ' *******************************************************************************\n'
)
_NATIVE_COMPLETED = ' ***                           BAND TASK COMPLETED                          ***\n'
_START = ' **** **** ******  **  PROGRAM STARTED AT               2026-04-20 14:42:34.001\n'
_END = ' **** **** ******  **  PROGRAM ENDED AT                 2026-04-20 14:43:23.115\n'
_ENER_STEP = '         3        -24.815000100        -24.800609995        -24.815000200          0.250000000          0.260000000\n'

_ENER_ZERO = '         0        -24.715000100        -24.700609995        -24.715000200          0.251000000          0.261000000\n'
_ZERO = (-24.7150001, -24.700609995, -24.7150002)
_STEP = (-24.8150001, -24.800609995, -24.8150002)


def _trajectory(step, energy, x, *, fixed_x=0):
    # CP2K v2025.2/v2026.2 dump_neb_info: XMOL title has an explicit step and energy in Hartree.
    return f'       2\n i ={step:8d}, E ={energy:20.10f}\n Cu {fixed_x:20.10f} 0.0 0.0\n H {x:20.10f} 1.0 2.0\n'


def test_cp2k_prepare_writes_explicit_replicas_and_fixed_atom_include(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import write_cp2k_neb

    files, warnings = write_cp2k_neb(tmp_path, images)

    assert {'band.inc', 'geometry.inc', 'trajectory.inc', 'fixed-atoms.inc'}.issubset(files)
    assert all((tmp_path / filename).is_file() for filename in files)
    assert 'PERIODIC XY' in (tmp_path / 'geometry.inc').read_text()
    band = (tmp_path / 'band.inc').read_text()
    assert 'NUMBER_OF_REPLICA 3' in band
    assert 'ALIGN_FRAMES FALSE' in band
    assert 'ROTATE_FRAMES FALSE' in band
    assert 'FILENAME =band.ener' in band
    assert band.count('FILENAME __STD_OUT__') == 2
    replica_names = [line.split()[1] for line in band.splitlines() if line.strip().startswith('COORD_FILE_NAME ')]
    assert len(replica_names) == 3
    for index, filename in enumerate(replica_names):
        replica_path = tmp_path / filename
        assert replica_path.read_text().splitlines()[1].strip()
        np.testing.assert_allclose(read(replica_path, format='xyz').positions, images[index].positions)
    fixed = (tmp_path / 'fixed-atoms.inc').read_text()
    assert '&FIXED_ATOMS' in fixed
    assert 'COMPONENTS_TO_FIX XYZ' in fixed
    assert 'LIST 1\n' in fixed
    assert any('MD' in warning and 'DIIS' in warning for warning in warnings)
    assert 'FORMAT XMOL' in (tmp_path / 'trajectory.inc').read_text()


def test_cp2k_prepare_rejects_unsupported_constraints_before_writing(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import write_cp2k_neb

    for image in images:
        image.set_constraint(FixCartesian(0, mask=[True, False, False]))

    with pytest.raises(ValueError, match='partial constraints'):
        write_cp2k_neb(tmp_path, images)

    assert list(tmp_path.iterdir()) == []


def test_cp2k_reads_native_row_without_treating_distance_columns_as_energy(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    energy = tmp_path / 'band.ener'
    energy.write_text(_ENER_ZERO + _ENER_STEP)
    log = tmp_path / 'band.nebLog'
    log.write_text(_native_band(0, _ZERO) + _native_band(3) + _NATIVE_CONVERGENCE + _NATIVE_COMPLETED)
    names = []
    for replica, value in enumerate(_STEP, 1):
        path = tmp_path / f'cloudra-neb-pos-Replica_nr_{replica}-1.xyz'
        path.write_text(_trajectory(0, _ZERO[replica - 1], replica) + _trajectory(3, value, 2.25 if replica == 2 else replica))
        names.append(str(path.resolve()))

    result = read_cp2k_neb(tmp_path, images)

    assert result['energies_ev'] == pytest.approx([-24.8150001 * Hartree, -24.800609995 * Hartree, -24.8150002 * Hartree])
    assert result['native_converged'] is True
    assert result['band_complete'] is True
    assert result['metrics']['max_force_ev_per_angstrom'] == pytest.approx(0.00004 * Hartree / Bohr)
    assert result['metrics']['rms_displacement_angstrom'] == pytest.approx(0.00001 * Bohr)
    assert [frame.positions[1, 0] for frame in result['geometries']] == [1, 2.25, 3]
    assert np.array_equal(result['geometries'][1].pbc, images[1].pbc)
    assert np.array_equal(result['geometries'][1].cell, images[1].cell)
    assert set(result['evidence_paths']) == {str(energy.resolve()), str(log.resolve()), *names}


@pytest.mark.parametrize('row', [
    '3 -24.81 -24.80 -24.82\n',
    '3 -24.81 -24.80 -24.82 0.20 0.21 0.22\n',
    '3 -24.81 nan -24.82 0.20 0.21\n',
    '3 -24.81 -24.80 -24.82 0.20 -0.21\n',
    '# Step Nr. Time[fs] Kin.[a.u.] Temp[K] Pot.[a.u.]\n3 -24.81 -24.80 -24.82 0.20 0.21\n',
])
def test_cp2k_rejects_malformed_or_ambiguous_native_energy_rows(tmp_path, images, row):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    (tmp_path / 'band.ener').write_text(row)

    result = read_cp2k_neb(tmp_path, images)

    assert result['energies_ev'] == [None, None, None]
    assert result['geometries'] == [None, None, None]
    assert result['native_converged'] is None
    assert any('band.ener' in warning for warning in result['warnings'])


def test_cp2k_reads_wrapped_native_stdout_without_energy_file(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    images += [images[1].copy(), images[2].copy()]
    log = tmp_path / 'cp2k.out'
    log.write_text(_native_band(3, (-26.2, -26.1, -26, -26.2, -26.3)) + _NATIVE_COMPLETED)

    result = read_cp2k_neb(tmp_path, images, log)

    assert result['energies_ev'] == pytest.approx(np.array([-26.2, -26.1, -26, -26.2, -26.3]) * Hartree)
    assert result['geometries'] == [None] * 5
    assert result['native_converged'] is True


@pytest.mark.parametrize('footer, expected', [(_END, True), ('', None), (_END + _START, None)])
def test_cp2k_2025_requires_native_checks_and_clean_termination_in_same_run(tmp_path, images, footer, expected):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    (tmp_path / 'band.ener').write_text(_ENER_STEP)
    log = tmp_path / 'cp2k.out'
    log.write_text(
        _START + ' CP2K| version string:                                       CP2K version 2025.2\n'
        + _native_band(3) + _NATIVE_CONVERGENCE + footer
    )

    assert read_cp2k_neb(tmp_path, images, log)['native_converged'] is expected


def test_cp2k_unmatched_stdout_and_input_images_cannot_verify_new_band(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb, write_cp2k_neb

    write_cp2k_neb(tmp_path, images)
    (tmp_path / 'band.ener').write_text(_ENER_STEP)
    (tmp_path / 'band.nebLog').write_text(_native_band(3, (-21, -20, -21)) + _NATIVE_COMPLETED)
    (tmp_path / 'cloudra-neb-pos-Replica_nr_1-1.xyz').write_text(_trajectory(2, -24.8150001, 1.25))
    (tmp_path / 'cloudra-neb-pos-Replica_nr_2-1.xyz').write_text(_trajectory(3, -24.1, 2.25))

    result = read_cp2k_neb(tmp_path, images)

    assert all(value is not None for value in result['energies_ev'])
    assert result['geometries'] == [None, None, None]
    assert result['native_converged'] is None
    assert result['warnings']


def test_cp2k_moved_fixed_atoms_are_reported_without_exporting_that_geometry(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    (tmp_path / 'band.ener').write_text(_ENER_ZERO + _ENER_STEP)
    (tmp_path / 'sample-pos-Replica_nr_1-1.xyz').write_text(_trajectory(0, _ZERO[0], 1) + _trajectory(3, _STEP[0], 1, fixed_x=8))
    (tmp_path / 'sample-pos-Replica_nr_2-1.xyz').write_text(
        _trajectory(0, _ZERO[1], 2) + _trajectory(3, _STEP[1], 2.25, fixed_x=0.1),
    )

    result = read_cp2k_neb(tmp_path, images)

    assert result['geometries'][0] is not None
    assert result['geometries'][1:] == [None, None]
    assert any('fixed' in warning.lower() and '2' in warning for warning in result['warnings'])


@pytest.mark.parametrize('zero_energy, zero_position', [(_ZERO[1] + 0.001, 2), (_ZERO[1], 2.5), (_ZERO[1], 10)])
def test_cp2k_rejects_geometry_from_an_unrelated_step_zero(tmp_path, images, zero_energy, zero_position):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    (tmp_path / 'band.ener').write_text(_ENER_ZERO + _ENER_STEP)
    (tmp_path / 'sample-pos-Replica_nr_2-1.xyz').write_text(
        _trajectory(0, zero_energy, zero_position) + _trajectory(3, _STEP[1], 2.25),
    )

    result = read_cp2k_neb(tmp_path, images)

    assert result['geometries'][1] is None
    assert result['band_complete'] is False
    assert any('step zero' in warning for warning in result['warnings'])


def test_cp2k_rejects_endpoint_motion_before_the_selected_step(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    (tmp_path / 'band.ener').write_text(_ENER_ZERO + _ENER_STEP)
    (tmp_path / 'sample-pos-Replica_nr_1-1.xyz').write_text(
        _trajectory(0, _ZERO[0], 1) + _trajectory(2, -24.8, 1.1) + _trajectory(3, _STEP[0], 1),
    )

    result = read_cp2k_neb(tmp_path, images)

    assert result['geometries'][0] is None
    assert result['band_complete'] is False
    assert any('endpoint' in warning for warning in result['warnings'])


def _replica_evaluation(replica, step, energy, *, failed=False):
    # v2025.2/v2026.2 neb_io.F:handle_band_file_names and the QS SCF warning/energy print.
    return (
        ' *******************************************************************************\n'
        ' **                 BAND EVALUATION OF ENERGIES AND FORCES                    **\n'
        f' ** Replica Env Nr. :    0             Replica Band Nr. :{replica:5d}                  **\n'
        f' ** Band  Step  Nr. :{step:5d}                                                      **\n'
        ' *******************************************************************************\n'
        + (' *** WARNING in qs_scf.F:1075 :: SCF run NOT converged ***\n' if failed else '')
        + f' ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: {energy:25.14f}\n'
    )


@pytest.mark.parametrize('final_scf_failed', [False, True])
def test_cp2k_uses_selected_replica_evaluation_for_scf_status(tmp_path, images, final_scf_failed):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    (tmp_path / 'band.ener').write_text(_ENER_ZERO + _ENER_STEP)
    (tmp_path / 'input.out').write_text(
        ' GLOBAL| Project name                                                        sample\n'
        + _native_band(0, _ZERO) + _native_band(3) + _NATIVE_COMPLETED,
    )
    for index in range(3):
        (tmp_path / f'cloudra-neb-pos-Replica_nr_{index + 1}-1.xyz').write_text(
            _trajectory(0, _ZERO[index], index + 1) + _trajectory(3, _STEP[index], index + 1),
        )
    (tmp_path / 'sample-BAND2.out').write_text(
        _replica_evaluation(2, 0, _ZERO[1])
        + _replica_evaluation(2, 3, -24.82, failed=True)
        + _replica_evaluation(2, 3, _STEP[1], failed=final_scf_failed),
    )

    result = read_cp2k_neb(tmp_path, images)

    assert result['band_complete'] is not final_scf_failed
    assert any('SCF' in warning for warning in result['warnings']) is final_scf_failed


@pytest.mark.parametrize('vector, periodicity', [(' 8.000 0.000 0.000', 'XYZ'), (' 8.010 0.000 0.000', 'XY')])
def test_cp2k_rejects_explicit_native_cell_or_periodicity_mismatch(tmp_path, images, vector, periodicity):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    (tmp_path / 'band.ener').write_text(_ENER_ZERO + _ENER_STEP)
    (tmp_path / 'input.out').write_text(
        f' CELL| Vector a [angstrom]: {vector}  |a| = 8.000000\n'
        ' CELL| Vector b [angstrom]: 0.000 9.000 0.000  |b| = 9.000000\n'
        ' CELL| Vector c [angstrom]: 0.000 0.000 20.000  |c| = 20.000000\n'
        f' CELL| Periodicity                                                           {periodicity}\n'
        + _native_band(0, _ZERO) + _native_band(3) + _NATIVE_COMPLETED,
    )
    for index in range(3):
        (tmp_path / f'cloudra-neb-pos-Replica_nr_{index + 1}-1.xyz').write_text(
            _trajectory(0, _ZERO[index], index + 1) + _trajectory(3, _STEP[index], index + 1),
        )

    result = read_cp2k_neb(tmp_path, images)

    assert result['band_complete'] is False
    assert result['geometries'] == [None, None, None]
    assert result['native_converged'] is True
    assert any('cell' in warning or 'periodicity' in warning for warning in result['warnings'])


def test_cp2k_checks_unique_replica_logs_when_main_stdout_is_unavailable(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    (tmp_path / 'band.ener').write_text(_ENER_ZERO + _ENER_STEP)
    for index in range(3):
        (tmp_path / f'cloudra-neb-pos-Replica_nr_{index + 1}-1.xyz').write_text(
            _trajectory(0, _ZERO[index], index + 1) + _trajectory(3, _STEP[index], index + 1),
        )
    (tmp_path / 'sample-BAND2.out').write_text(
        _replica_evaluation(2, 0, _ZERO[1]) + _replica_evaluation(2, 3, _STEP[1], failed=True),
    )

    result = read_cp2k_neb(tmp_path, images)

    assert result['band_complete'] is False
    assert any('SCF' in warning for warning in result['warnings'])


def test_cp2k_2026_reads_native_vertical_energy_table(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    log = tmp_path / 'input.out'
    beginning, _, _ = _native_band(3).partition(' DISTANCES REP =')
    log.write_text(
        beginning + ' REPLICA             ENERGY [au]   TEMPERATURE [K]   o-------------------------> E\n'
        '       1      -24.81500010 (**)        0.000000   |O\n'
        ' DISTANCE =         0.250000                      |\n'
        '       2      -24.80060999 (++)        0.000000   |                         X\n'
        ' DISTANCE =         0.260000                      |\n'
        '       3      -24.81500020 (-*)        0.000000   |O\n'
        '                                                   v Nr.\n'
        ' NUMBER OF LOCAL MAXIMA (X) and MINIMA (x):    1    0\n'
        ' BAND TOTAL ENERGY [au]        =                              -74.43060834560000\n'
        ' *******************************************************************************\n' + _NATIVE_COMPLETED,
    )

    result = read_cp2k_neb(tmp_path, images, log)

    assert result['energies_ev'] == pytest.approx(np.array(_STEP) * Hartree)
    assert result['native_converged'] is True


def test_cp2k_ignores_identical_final_energies_in_a_log_with_different_seed_step(tmp_path, images):
    from cloudra.tools.core.periodic_neb_cp2k import read_cp2k_neb

    (tmp_path / 'band.ener').write_text(_ENER_ZERO + _ENER_STEP)
    (tmp_path / 'band.nebLog').write_text(_native_band(0, (-25.1, -25, -25.1)) + _native_band(3) + _NATIVE_COMPLETED)
    for index in range(3):
        (tmp_path / f'cloudra-neb-pos-Replica_nr_{index + 1}-1.xyz').write_text(
            _trajectory(0, _ZERO[index], index + 1) + _trajectory(3, _STEP[index], index + 1),
        )

    result = read_cp2k_neb(tmp_path, images)

    assert result['native_converged'] is None
    assert result['band_complete'] is False
    assert result['energies_ev'] == pytest.approx(np.array(_STEP) * Hartree)
