"""Direction evidence follows actual IRC → Opt → Freq geometries."""

from pathlib import Path

import pytest

from cloudra.tools.core import irc_evidence
from cloudra.tools.core.irc_path import prove_irc_endpoint_direction, xyz_block


def write_lineage_bundle(directory):
    """Native-shaped ORCA evidence with real lineage and non-monotone bond lengths."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    symbols = ['C', 'N', 'H']
    ts = [[0., 0., 0.], [1.16, 0., 0.], [.5, .8, 0.]]
    reactant = [[0., 0., 0.], [1.16, 0., 0.], [-1.06, 0., 0.]]
    product = [[0., 0., 0.], [1.16, 0., 0.], [2.17, 0., 0.]]
    end_a = [[0., 0., 0.], [1.16, 0., 0.], [-1.25, 0., 0.]]
    end_b = [[0., 0., 0.], [1.16, 0., 0.], [2.35, 0., 0.]]

    def coordinates(positions):
        return 'CARTESIAN COORDINATES (ANGSTROEM)\n---------------------------------\n' + ''.join(
            f'{symbol} {x:.8f} {y:.8f} {z:.8f}\n'
            for symbol, (x, y, z) in zip(symbols, positions, strict=True)) + '\n'

    def log(name, initial, final, *, optimize=False, imaginary=None):
        text = '* O   R   C   A *\nProgram Version 6.1.1\n'
        text += coordinates(initial)
        if optimize:
            # Native ORCA prints this stationary-point header before the final geometry.
            text += ('THE OPTIMIZATION HAS CONVERGED\n'
                     'FINAL ENERGY EVALUATION AT THE STATIONARY POINT\n' + coordinates(final))
        text += 'FINAL SINGLE POINT ENERGY -92.0\n'
        if imaginary is not None:
            text += 'VIBRATIONAL FREQUENCIES\n-----------------------\n\n'
            frequencies = [0.] * 6 + ([-100.] if imaginary else [100.]) + [200., 300.]
            text += ''.join(f'{index}: {frequency:.2f} cm**-1\n' for index, frequency in enumerate(frequencies))
        path = directory / name
        path.write_text(text + '\n****ORCA TERMINATED NORMALLY****\n')
        return path

    paths = {
        'ts': log('ts.out', ts, ts, optimize=True, imaginary=True),
        'reactant_opt': log('reactant_opt.out', end_a, reactant, optimize=True),
        'reactant_freq': log('reactant_freq.out', reactant, reactant, imaginary=False),
        'product_opt': log('product_opt.out', end_b, product, optimize=True),
        'product_freq': log('product_freq.out', product, product, imaginary=False),
        'reactant_smiles': 'C#N',
        'product_smiles': '[C-]#[NH+]',
    }
    irc = directory / 'irc.out'
    irc.write_text('* O   R   C   A *\n' + coordinates(ts)
        + 'Intrinsic Reaction Coordinate Calculation\n'
        + '* FORWARD IRC *\n0 -92.0 -1.0 0.1 0.1\n'
        + '* BACKWARD IRC *\n0 -92.0 -1.0 0.1 0.1\n'
        + '****ORCA TERMINATED NORMALLY****\n')
    (directory / 'irc_IRC_F.xyz').write_text(xyz_block(symbols, end_a))
    (directory / 'irc_IRC_B.xyz').write_text(xyz_block(symbols, end_b))
    paths['irc'] = irc
    return paths


def check_bundle(paths, *, paired=False):
    arguments = ([paths['ts']], [paths['product_opt'], paths['product_freq']],
                 [paths['reactant_opt'], paths['reactant_freq']])
    keywords = dict(reactant_smiles=paths['reactant_smiles'], product_smiles=paths['product_smiles'])
    if paired:
        return irc_evidence.verify_short_irc_pair(paths['irc'], paths['irc'], *arguments, **keywords)
    return irc_evidence.verify_short_irc_direction(paths['irc'], *arguments, **keywords)


@pytest.mark.parametrize('paired', [False, True])
def test_actual_endpoint_optimizations_override_interval_with_warning(tmp_path, paired, rdkit_chemistry):
    paths = write_lineage_bundle(tmp_path)
    ends = irc_evidence.irc_endpoint_geometries(paths['irc'])
    ts = irc_evidence.probe_log(paths['ts'])[1]
    reactant = irc_evidence.probe_log(paths['reactant_freq'])[1]
    product = irc_evidence.probe_log(paths['product_freq'])[1]
    interval = prove_irc_endpoint_direction(*ts, *ends, reactant, product, [])
    assert not interval['is_match']

    passed, details = check_bundle(paths, paired=paired)

    assert passed, details
    assert any('warning' in detail.lower() and 'interval' in detail.lower() for detail in details)


@pytest.mark.parametrize('broken', ['wrong_start', 'unconverged', 'missing_opt', 'imaginary', 'wrong_species', 'wrong_ts'])
def test_endpoint_optimization_requires_real_chain(tmp_path, broken, rdkit_chemistry):
    paths = write_lineage_bundle(tmp_path)
    path = paths['reactant_opt']
    if broken == 'wrong_start':
        path.write_text(path.read_text().replace('-1.25000000', '-1.65000000', 1))
    elif broken == 'unconverged':
        path.write_text(path.read_text().replace('THE OPTIMIZATION HAS CONVERGED', 'The optimization did not converge'))
    elif broken == 'missing_opt':
        path.unlink()
    elif broken == 'imaginary':
        path = paths['reactant_freq']
        path.write_text(path.read_text().replace('6: 100.00', '6: -100.00'))
    elif broken == 'wrong_species':
        paths['reactant_smiles'] = 'N#N'
    elif broken == 'wrong_ts':
        path = paths['ts']
        path.write_text(path.read_text().replace('0.50000000', '0.70000000'))

    assert not check_bundle(paths)[0]


def test_minimum_reference_without_optimization_cannot_prove_direction(tmp_path, rdkit_chemistry):
    paths = write_lineage_bundle(tmp_path)
    paths['reactant_opt'] = paths['reactant_freq']
    paths['product_opt'] = paths['product_freq']
    assert not check_bundle(paths)[0]


def test_converged_opt_without_frequency_is_not_a_verified_minimum(tmp_path, rdkit_chemistry):
    paths = write_lineage_bundle(tmp_path)
    paths['reactant_freq'] = paths['reactant_opt']
    assert not check_bundle(paths)[0]


def test_gaussian_checkpoint_irc_exposes_its_native_starting_saddle():
    path = Path(__file__).parent / 'fixtures' / 'gaussian' / 'hcn_ts_irc_g16.log'
    geometry = irc_evidence.irc_start_geometry(path)
    expected = (['C', 'N', 'H'], [[.427601046333, -.595124818941, 0.],
        [-.354873742408, .327913217079, 0.], [-.680027213924, -1.045649718138, 0.]])
    from cloudra.tools.core.irc_path import same_geometry
    assert same_geometry(geometry, expected)
