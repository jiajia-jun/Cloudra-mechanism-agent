from pathlib import Path
from shutil import copyfile

import ase
import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import read

from cloudra.tools.core import periodic_neb_vasp


@pytest.fixture
def images():
    return [
        Atoms(
            'CuOCu', positions=[[1, 1, 1], [x, 2, 2], [4, 4, 4]],
            cell=[8, 8, -12], pbc=[True, True, False], constraint=FixAtoms([2]),
        )
        for x in (2.0, 2.5, 3.0, 3.5)
    ]


def _write_outcar(
    directory, energy, *, steps=(None,), stop=False, finish=True, force=0.02, spring=-5, nsw=20,
    electronic_failed=False, band_images=None, vtst=False,
):
    # OUTCAR layout from ASE's OUTCAR_example_1. The stock VASP NEB force table
    # is documented at https://vasp.at/forum/viewtopic.php?p=28366.
    native = read(directory / 'POSCAR')
    band_images = band_images if band_images is not None else (2 if len(steps) > 1 else 0)
    text = [' vasp.6.5.1']
    for _ in range(2):
        text.extend((' POTCAR:    PAW_PBE Cu 06Sep2000', ' POTCAR:    PAW_PBE O 08Apr2002'))
    text.extend([
        '   ions per type = 2 1',
        '   ENCUT  =  400.0 eV',
        '   ISMEAR =     0;   SIGMA  =   0.10  broadening in eV',
        ' generate k-points for:    3    3    1',
        '  Shift w.r.t. Gamma in fractional coordinates (k-lattice)',
        '     0.000000000  0.000000000  0.000000000',
        '   EDIFFG = -.05   stopping-criterion for IOM',
        f'   NSW    =     {nsw}   number of steps for IOM',
    ])
    if band_images:
        text.extend([f'   IMAGES = {band_images}', f'   SPRING = {spring}'])
    for step, oxygen_x in enumerate(steps, 1):
        native_positions = native.positions.copy()
        if oxygen_x is not None:
            native_positions[2, 0] = oxygen_x
        value = energy if step == len(steps) else energy + 0.1
        text.extend([
            f'------------------------------------- Iteration   {step}(   1)  -------------------------------------',
            '     direct lattice vectors                 reciprocal lattice vectors',
            '  8.000000000  0.000000000  0.000000000     0.125000000  0.000000000  0.000000000',
            '  0.000000000  8.000000000  0.000000000     0.000000000  0.125000000  0.000000000',
            '  0.000000000  0.000000000 12.000000000     0.000000000  0.000000000  0.083333333',
            ' POSITION                                       TOTAL-FORCE (eV/Angst)',
            ' -----------------------------------------------------------------------------------',
            *(f'{x:13.5f}{y:13.5f}{z:13.5f}     0.500000  0.000000  0.000000' for x, y, z in native_positions),
            ' -----------------------------------------------------------------------------------',
            '    total drift:                                 0.000000  0.000000  0.000000',
        ])
        if vtst:
            text.append(' NEB: forces: par spring, perp REAL, dneb     0.006448    0.010138    0.000000')
        elif band_images:
            text.extend([
                ' CHAIN + TOTAL  (eV/Angst)',
                ' ---------------------------------------------------',
                '   0.000000  0.000000  0.000000',
                '   0.000000  0.000000  0.000000',
                f'   {force:.6f}  0.000000  0.000000',
                ' ---------------------------------------------------',
            ])
        text.extend([
            '  FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)',
            '  ---------------------------------------------------',
            f'  free  energy   TOTEN  =  {value - 0.2:.8f} eV',
            '',
            f'  energy  without entropy= {value - 0.1:.8f}  energy(sigma->0) = {value:.8f}',
        ])
    if electronic_failed:
        text.append(' | The electronic self-consistency was not achieved in the given |')
    if stop:
        if vtst:
            text.append(' OPT: skip step - force has converged')
        text.append(' reached required accuracy - stopping structural energy minimisation')
    if finish:
        text.append(' General timing and accounting informations for this job:')
    outcar = directory / 'OUTCAR'
    outcar.write_text('\n'.join([*text, '']), encoding='utf-8')
    return outcar


def test_prepare_writes_native_image_count_order_and_flags(tmp_path, images):
    names, warnings = periodic_neb_vasp.write_vasp_neb(tmp_path, images)

    assert set(names) == {'INCAR.neb', '00/POSCAR', '01/POSCAR', '02/POSCAR', '03/POSCAR'}
    assert (tmp_path / 'INCAR.neb').read_text().split() == ['IMAGES', '=', '2']
    for i, expected in enumerate(images):
        native = read(tmp_path / f'{i:02d}' / 'POSCAR')
        assert native.get_chemical_symbols() == ['Cu', 'Cu', 'O']
        assert native.constraints[0].get_indices().tolist() == [1]
        np.testing.assert_allclose(native.positions, expected.positions[[0, 2, 1]])
        assert native.pbc.tolist() == [True, True, True]
        assert native.cell.handedness == 1
    assert any('periodic axes' in warning for warning in warnings)


def test_collect_pairs_actual_coordinates_with_zero_smearing_energy(tmp_path, images):
    periodic_neb_vasp.write_vasp_neb(tmp_path, images)
    _write_outcar(tmp_path / '00', -10.0)
    _write_outcar(tmp_path / '01', -8.5, steps=(None, 2.7), stop=True)
    _write_outcar(tmp_path / '02', -9.5, steps=(None, 3.1), stop=True)
    _write_outcar(tmp_path / '03', -9.7)
    (tmp_path / '01' / 'CONTCAR').write_text('unfinished CONTCAR', encoding='utf-8')

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, images)

    assert result['energies_ev'] == [-10.0, -8.5, -9.5, -9.7]
    assert result['band_complete'] is True
    assert result['profile_comparable'] is True
    assert result['native_converged'] is True
    assert 'sigma' in result['energy_convention']
    assert result['metrics']['max_chain_force_ev_per_angstrom'] == pytest.approx(0.02)
    geometry = result['geometries'][1]
    assert geometry.get_chemical_symbols() == ['Cu', 'O', 'Cu']
    assert geometry.constraints[0].get_indices().tolist() == [2]
    assert geometry.pbc.tolist() == [True, True, True]
    assert geometry.cell.handedness == 1
    np.testing.assert_allclose(geometry.positions, [[1, 1, 1], [2.7, 2, 2], [4, 4, 4]])
    assert str((tmp_path / '01' / 'OUTCAR').resolve()) in result['evidence_paths']


@pytest.mark.parametrize(
    ('mode', 'native_converged'),
    [
        ('normal-only', None),
        ('different-step', None),
        ('over-threshold', None),
        ('elastic-band', None),
        ('stale-stdout', None),
        ('bound-stdout', True),
        ('step-limit', False),
    ],
)
def test_native_stop_needs_coherent_neb_evidence(tmp_path, images, mode, native_converged):
    periodic_neb_vasp.write_vasp_neb(tmp_path, images)
    stop = mode in ('different-step', 'over-threshold', 'elastic-band')
    nsw = 2 if mode == 'step-limit' else 20
    options = {'steps': (None, 3.1), 'stop': stop, 'nsw': nsw}
    if mode == 'different-step':
        options['steps'] = (None, 3.05, 3.1)
    if mode == 'over-threshold':
        options['force'] = 0.2
    if mode == 'elastic-band':
        options['spring'] = 5
    _write_outcar(tmp_path / '01', -8.5, steps=(None, 2.7), stop=stop, nsw=nsw)
    _write_outcar(tmp_path / '02', -9.5, **options)
    output_log = tmp_path / 'vasp.out'
    energy_text = '-.85000000E+01' if mode == 'bound-stdout' else '-.53000000E+01'
    stop_line = (
        ' reached required accuracy - stopping structural energy minimisation\n'
        if mode in ('stale-stdout', 'bound-stdout') else ''
    )
    output_log.write_text(
        f'   2 F= -.87000000E+01 E0= {energy_text}  d E =-.100000E+00\n{stop_line}',
        encoding='utf-8',
    )

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, images, output_log)

    assert result['energies_ev'] == [None, -8.5, -9.5, None]
    assert result['native_converged'] is native_converged
    assert result['band_complete'] is (mode not in ('different-step', 'elastic-band'))


def test_native_ionic_stop_remains_evidence_at_printed_force_precision(tmp_path, images):
    periodic_neb_vasp.write_vasp_neb(tmp_path, images)
    _write_outcar(tmp_path / '01', -8.5, steps=(None, 2.7), stop=True, force=0.05)
    _write_outcar(tmp_path / '02', -9.5, steps=(None, 3.1), stop=True)

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, images)

    assert result['native_converged'] is True


def test_complete_band_convergence_keeps_missing_endpoints_unknown(tmp_path, images):
    periodic_neb_vasp.write_vasp_neb(tmp_path, images)
    _write_outcar(tmp_path / '01', -8.5, steps=(None, 2.7), stop=True)
    _write_outcar(tmp_path / '02', -9.5, steps=(None, 3.1), stop=True)
    (tmp_path / '00' / 'OSZICAR').write_text('   1 F= -10.2 E0= -10.0\n', encoding='utf-8')

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, images)

    assert result['native_converged'] is True
    assert result['energies_ev'] == [None, -8.5, -9.5, None]
    assert result['geometries'][0] is None
    assert result['geometries'][3] is None


@pytest.mark.parametrize('last_summary_present', [True, False])
def test_vtst_band_requires_native_neb_summary_at_each_final_ionic_step(tmp_path, images, last_summary_present):
    periodic_neb_vasp.write_vasp_neb(tmp_path, images)
    _write_outcar(tmp_path / '00', -10.0)
    _write_outcar(tmp_path / '01', -8.5, steps=(None, 2.7), stop=True, vtst=True)
    outcar = _write_outcar(tmp_path / '02', -9.5, steps=(None, 3.1), stop=True, vtst=True)
    _write_outcar(tmp_path / '03', -9.7)
    if not last_summary_present:
        # Keep the previous iteration's native summary and the final raw forces.
        before, after = outcar.read_text().rsplit(' NEB: forces:', maxsplit=1)
        outcar.write_text(before + after.partition('\n')[2], encoding='utf-8')

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, images)

    assert result['energies_ev'] == [-10.0, -8.5, -9.5, -9.7]
    assert result['band_complete'] is last_summary_present
    assert result['native_converged'] is None
    assert 'max_chain_force_ev_per_angstrom' not in result['metrics']


@pytest.mark.parametrize(
    ('image_index', 'tag', 'original', 'replacement'),
    [
        (0, 'ENCUT', '400.0 eV', '500.0 eV'),
        (2, 'ENCUT', '400.0 eV', '500.0 eV'),
        (0, 'SIGMA', '0.10  broadening', '0.20  broadening'),
        (3, 'k-point grid shift', '0.000000000  0.000000000  0.000000000', '0.500000000  0.000000000  0.000000000'),
        (3, 'POTCAR', 'Cu 06Sep2000', 'Cu 08Apr2002'),
    ],
)
def test_different_native_electronic_settings_disqualify_energy_comparisons(
    tmp_path, images, image_index, tag, original, replacement,
):
    periodic_neb_vasp.write_vasp_neb(tmp_path, images)
    paths = [
        _write_outcar(tmp_path / '00', -10.0),
        _write_outcar(tmp_path / '01', -8.5, steps=(None, 2.7), stop=True),
        _write_outcar(tmp_path / '02', -9.5, steps=(None, 3.1), stop=True),
        _write_outcar(tmp_path / '03', -9.7),
    ]
    path = paths[image_index]
    path.write_text(path.read_text().replace(original, replacement), encoding='utf-8')

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, images)

    assert result['energies_ev'] == [-10.0, -8.5, -9.5, -9.7]
    assert result['profile_comparable'] is False
    assert result['band_complete'] is (image_index in (0, 3))
    assert any(tag in warning for warning in result['warnings'])


def test_failed_endpoint_scf_excludes_its_energy_without_affecting_band(tmp_path, images):
    periodic_neb_vasp.write_vasp_neb(tmp_path, images)
    _write_outcar(tmp_path / '00', -10.0, electronic_failed=True)
    _write_outcar(tmp_path / '01', -8.5, steps=(None, 2.7), stop=True)
    _write_outcar(tmp_path / '02', -9.5, steps=(None, 3.1), stop=True)
    _write_outcar(tmp_path / '03', -9.7)

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, images)

    assert result['energies_ev'] == [None, -8.5, -9.5, -9.7]
    assert result['native_converged'] is True
    assert result['band_complete'] is True


def test_rejects_poscar_or_outcar_from_wrong_image(tmp_path, images):
    periodic_neb_vasp.write_vasp_neb(tmp_path, images)
    _write_outcar(tmp_path / '01', -8.5, steps=(None, 2.7), stop=True)
    copyfile(tmp_path / '01' / 'OUTCAR', tmp_path / '02' / 'OUTCAR')
    _write_outcar(tmp_path / '00', -10.0)
    copyfile(tmp_path / '01' / 'POSCAR', tmp_path / '00' / 'POSCAR')

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, images)

    assert result['energies_ev'] == [None, -8.5, None, None]
    assert result['geometries'][0] is None
    assert result['geometries'][2] is None
    assert result['native_converged'] is not True


def test_truncated_latest_step_keeps_last_evaluated_pair(tmp_path, images):
    periodic_neb_vasp.write_vasp_neb(tmp_path, images)
    outcar = _write_outcar(tmp_path / '01', -8.5, steps=(None, 2.7), finish=False)
    with outcar.open('a', encoding='utf-8') as stream:
        stream.write('------------------------------------- Iteration   3(   1)  -------------------------------------\n')
        stream.write('  FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)\n')

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, images)

    assert result['energies_ev'][1] == -8.5
    assert result['geometries'][1].positions[1, 0] == 2.7
    assert result['native_converged'] is not True


def test_single_interior_image_may_converge_at_first_ionic_step(tmp_path, images):
    expected = images[:3]
    periodic_neb_vasp.write_vasp_neb(tmp_path, expected)
    _write_outcar(tmp_path / '01', -8.5, stop=True, band_images=1)

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, expected)

    assert result['energies_ev'] == [None, -8.5, None]
    assert result['band_complete'] is True
    assert result['native_converged'] is True


def test_reads_real_vasp_outcar_from_ase_fixture(tmp_path):
    sample = Path(ase.__file__).parent / 'test' / 'testdata' / 'vasp' / 'OUTCAR_example_1'
    if not sample.is_file():
        pytest.skip('ASE distribution omits VASP test data')
    endpoint = read(sample, format='vasp-out')
    expected = [endpoint.copy() for _ in range(3)]
    periodic_neb_vasp.write_vasp_neb(tmp_path, expected)
    copyfile(sample, tmp_path / '00' / 'OUTCAR')

    result = periodic_neb_vasp.read_vasp_neb(tmp_path, expected)

    assert result['energies_ev'] == [-68.23102426, None, None]
    np.testing.assert_allclose(result['geometries'][0].positions[1], [16.82152, 15.71963, 17.66895])
    assert result['native_converged'] is not True
