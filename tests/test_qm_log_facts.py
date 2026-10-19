"""Native Gaussian/ORCA facts survive failure of the optional library."""
from pathlib import Path

import pytest

from cloudra.dag.evidence_ingest import _extract_qm_log
from cloudra.tools.Chemtool.log_parser import LogParser, LogParser_input_schema
from cloudra.tools.core import gaussian_frames
from cloudra.tools.core.qm_log_facts import parse_qm_log_text, read_qm_log

FIXTURES = Path(__file__).parent / 'fixtures'
CASES = [('gaussian', 'gaussian/water_opt_freq_g16.out', -74.9659011806),
         ('orca', 'orca/co2_freq_orca42.out', -184.757766163554)]


@pytest.mark.parametrize('failure', [None, ValueError('optional parser unavailable')])
@pytest.mark.parametrize('engine,fixture,energy', CASES)
@pytest.mark.asyncio
async def test_native_facts_are_the_same_for_tool_and_file_evidence(monkeypatch, failure, engine, fixture, energy):
    def optional_parser(*_args, **_kwargs):
        if failure:
            raise failure
        return None
    monkeypatch.setattr('cclib.io.ccread', optional_parser)
    path = FIXTURES / fixture
    facts = read_qm_log(path)
    result = await LogParser().tool_call(LogParser_input_schema(log_path=str(path)), session=None)
    evidence = _extract_qm_log(path)
    assert facts.engine == result.engine == evidence[1] == engine
    assert facts.normal_termination is result.normal_termination is True
    assert facts.opt_converged is result.opt_converged is True
    assert facts.geometry is not None
    assert facts.frequencies_cm == evidence[2]
    assert result.frequencies_cm == [f for f in facts.frequencies_cm if f >= 0]
    assert result.imaginary_frequencies == evidence[3] == []
    assert result.is_success is True
    assert facts.electronic_energy_hartree == pytest.approx(energy, abs=1e-10)
    assert result.electronic_energy_hartree == evidence[4] == facts.electronic_energy_hartree


@pytest.mark.parametrize('engine,banner,terminal', [
    ('gaussian', 'Gaussian 16', 'Normal termination'),
    ('orca', 'ORCA VERSION 6', 'ORCA TERMINATED NORMALLY'),
])
def test_no_frequency_or_optimization_is_unknown(monkeypatch, engine, banner, terminal):
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    facts = parse_qm_log_text(f'{banner}\n{terminal}\n')
    assert facts.engine == engine
    assert facts.normal_termination is True
    assert facts.frequencies_cm is None
    assert facts.opt_converged is None
    assert facts.geometry is None


def test_gaussian_frame_export_survives_optional_parser_failure(monkeypatch):
    def failed(*_args, **_kwargs):
        raise IndexError('optional parser bug')
    monkeypatch.setattr('cclib.io.ccread', failed)
    frames = gaussian_frames.extract_frames(str(FIXTURES / 'gaussian/water_opt_freq_g16.out'))
    assert frames[-1].electronic_energy_hartree == pytest.approx(-74.9659011806, abs=1e-10)
    assert frames[-1].frequencies_cm == [2169.7613, 4141.3837, 4392.5759]
    assert frames[-1].converged is True
    assert frames[-1].xyz.splitlines()[0] == '3'


def test_gaussian_correlated_energy_does_not_replace_scf(monkeypatch):
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    facts = parse_qm_log_text('Gaussian 16\nSCF Done:  E(RHF) = -75.00000000 A.U.\n'
                              ' E2 = -0.1D+00 EUMP2 = -0.7510000000D+02\nNormal termination\n')
    assert facts.scf_energy_hartree == -75.0
    assert facts.electronic_energy_hartree == -75.1


def test_orca_correlated_energy_does_not_replace_scf(monkeypatch):
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    facts = parse_qm_log_text('ORCA VERSION 6\nTotal Energy       : -75.00000000 Eh\n'
                              'FINAL SINGLE POINT ENERGY -75.10000000\nORCA TERMINATED NORMALLY\n')
    assert facts.scf_energy_hartree == -75.0
    assert facts.electronic_energy_hartree == -75.1


def test_gaussian_frame_native_convergence_overrides_optional_parser(monkeypatch):
    from types import SimpleNamespace

    import numpy as np
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: SimpleNamespace(
        scfenergies=np.array([-75.0 * 27.21138505]), atomnos=np.array([1, 1]),
        atomcoords=np.array([[[0., 0., 0.], [0., 0., 0.74]]]), optdone=True))
    frames = gaussian_frames.extract_frames_from_text('Gaussian 16\n # opt hf/sto-3g\nOptimization stopped.\nNormal termination\n')
    assert frames[-1].converged is False


def test_native_facts_do_not_require_cclib_import(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, 'cclib', None)
    facts = read_qm_log(FIXTURES / 'gaussian/water_opt_freq_g16.out')
    assert facts.normal_termination is True
    assert facts.geometry is not None
    assert facts.electronic_energy_hartree == pytest.approx(-74.9659011806, abs=1e-10)
    assert facts.frequencies_cm == [2169.7613, 4141.3837, 4392.5759]


def test_empty_optional_frequency_array_is_not_a_minimum(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: SimpleNamespace(vibfreqs=[]))
    facts = parse_qm_log_text('Gaussian 16\nNormal termination\n')
    assert facts.frequencies_cm is None


def test_shared_reader_opens_native_file_once(monkeypatch):
    import builtins

    original = builtins.open
    path = FIXTURES / 'gaussian/water_opt_freq_g16.out'
    reads = []

    def counting_open(file, *args, **kwargs):
        if str(file) == str(path):
            reads.append(file)
        return original(file, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', counting_open)
    facts = read_qm_log(path)
    assert facts.parser_data is not None
    assert len(reads) == 1


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_later_single_point_geometry_cannot_inherit_old_optimization_or_frequency(monkeypatch, engine):
    from tests.ts_fixtures import native_qm_log

    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    initial = native_qm_log(engine, ['O', 'H', 'H'],
        [[0., 0., 0.], [.96, 0., 0.], [-.24, .93, 0.]],
        optimization=True, frequencies=[-350., 1000., 2000.])
    later = native_qm_log(engine, ['O', 'H', 'H'],
        [[0., 0., 0.], [5., 0., 0.], [-.24, .93, 0.]],
        optimization=None, frequencies=None)
    facts = parse_qm_log_text(initial + later)
    assert facts.geometry[1][1][0] == 5.0
    assert facts.opt_converged is None
    assert facts.frequencies_cm is None


@pytest.mark.parametrize('energy_line,expected', [
    ('UMP4(DQ)= -0.752D+02', -75.2),
    ('UMP4(SDQ)= -0.753D+02', -75.3),
    ('UMP4(SDTQ)= -0.754D+02', -75.4),
    ('MP5 = -0.755D+02', -75.5),
    ('E(CORR)= -0.756D+02', -75.6),
    ('CCSD(T)= -0.757D+02', -75.7),
])
def test_gaussian_native_final_method_energy_is_not_an_intermediate_mp2(monkeypatch, energy_line, expected):
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    text = f'Gaussian 16\nSCF Done: E(RHF) = -75.0 A.U.\nEUMP2 = -75.1\n{energy_line}\nNormal termination\n'
    facts = parse_qm_log_text(text)
    assert facts.scf_energy_hartree == -75.0
    assert facts.electronic_energy_hartree == expected


@pytest.mark.parametrize('fixture', ['ch2oo_optts_gfn2_orca611.out', 'co2_freq_orca42.out', 'dvb_opt_orca42.out'])
def test_real_orca_final_energy_evaluation_keeps_optimization_identity(monkeypatch, fixture):
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    facts = read_qm_log(FIXTURES / 'orca' / fixture)
    assert facts.opt_converged is True


def test_truncated_last_gaussian_link1_cannot_borrow_previous_normal_termination(monkeypatch):
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    text = (FIXTURES / 'gaussian/water_opt_freq_g16.out').read_text()
    assert gaussian_frames.normal_termination(text) is True
    partial = text[:text.rfind(' Normal termination')]
    assert gaussian_frames.normal_termination(partial) is False
    assert parse_qm_log_text(partial).normal_termination is False


@pytest.mark.parametrize('suffix,expected', [
    ('\n| 2> $new_job\n', True),
    ('\n| 2> JOB NUMBER 2\n', True),
    ('\nJOB NUMBER 2\n', False),
])
def test_orca_native_start_is_distinct_from_an_echoed_future_job(monkeypatch, suffix, expected):
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    text = (FIXTURES / 'orca/co2_freq_orca42.out').read_text() + suffix
    facts = parse_qm_log_text(text)
    assert facts.normal_termination is expected


def test_untyped_gaussian_energy_is_not_scf_even_when_cclib_calls_it_scf():
    # Controlled transformation of a captured log, not a claimed ExtOpt run.
    # Actual cclib accepts its generic Energy= line as SCF without method context.
    text = (FIXTURES / 'gaussian/water_opt_freq_g16.out').read_text()
    text = '\n'.join(line for line in text.splitlines() if 'SCF Done:' not in line)
    text = text.replace(' Normal termination of Gaussian',
        ' Energy=   -75.100000000000 NIter=  0.\n Normal termination of Gaussian')
    facts = parse_qm_log_text(text)
    assert facts.parser_data.scfenergies[-1] < 0
    assert facts.scf_energy_hartree is None
    assert facts.electronic_energy_hartree is None


def test_real_external_potential_log_has_total_electronic_energy_without_scf():
    facts = read_qm_log(FIXTURES / 'orca/cope_irc_extopt_mace_orca611.out')
    assert facts.scf_energy_hartree is None
    assert facts.electronic_energy_hartree == pytest.approx(-234.5062951055, abs=1e-10)


def test_extopt_frames_and_csv_report_electronic_energy_without_scf_alias(tmp_path, monkeypatch):
    import csv

    from cloudra.tools.core import orca_frames

    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: None)
    # Native external-potential output, with explicit coordinates for frame export.
    text = ('O   R   C   A\n! ExtOpt\n'
        'CARTESIAN COORDINATES (ANGSTROEM)\n-----\nH 0.0 0.0 0.0\nH 0.0 0.0 0.74\n\n'
        'FINAL SINGLE POINT ENERGY (From external program) -1.23456789\n'
        'ORCA TERMINATED NORMALLY\n')
    frames = orca_frames.extract_frames_from_text(text)
    assert len(frames) == 1
    assert frames[0].electronic_energy_hartree == -1.23456789
    assert not hasattr(frames[0], 'scf_energy_hartree')
    path = tmp_path / 'frames.csv'
    gaussian_frames.frames_to_csv(frames, str(path))
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    assert float(rows[0]['electronic_energy_hartree']) == -1.23456789
    assert float(rows[0]['electronic_energy_ev']) == pytest.approx(-1.23456789 * 27.211386245988)
    assert 'scf_energy_hartree' not in rows[0]
    assert 'scf_energy_ev' not in rows[0]


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
@pytest.mark.parametrize('parser_success', [False, True])
@pytest.mark.asyncio
async def test_single_point_frame_uses_explicit_total_energy_instead_of_scf(tmp_path, monkeypatch, engine, parser_success):
    import csv
    from types import SimpleNamespace

    from cloudra.tools.Chemtool.format_converter import FormatConverter, FormatConverter_input_schema
    from cloudra.tools.core import orca_frames
    from tests.ts_fixtures import native_qm_log

    data = SimpleNamespace(atomnos=[1, 1], atomcoords=[[[0., 0., 0.], [0., 0., .74]]],
        scfenergies=[-75. * 27.21138505]) if parser_success else None
    monkeypatch.setattr('cclib.io.ccread', lambda *_a, **_k: data)
    text = native_qm_log(engine, ['H', 'H'], [[0., 0., 0.], [0., 0., .74]], optimization=None)
    if engine == 'gaussian':
        text = text.replace(' # freq', ' # mp2/sto-3g').replace('Normal termination',
            'SCF Done: E(RHF) = -75.0 A.U.\nEUMP2 = -75.1\nNormal termination')
        frames = gaussian_frames.extract_frames_from_text(text)
    else:
        text = text.replace('! Freq', '! MP2').replace('ORCA TERMINATED NORMALLY',
            'Total Energy       : -75.0 Eh\nFINAL SINGLE POINT ENERGY -75.1\nORCA TERMINATED NORMALLY')
        frames = orca_frames.extract_frames_from_text(text)
    assert len(frames) == 1
    assert frames[0].electronic_energy_hartree == -75.1
    path = tmp_path / 'single_point.out'
    path.write_text(text)
    csv_path = tmp_path / 'frames.csv'
    result = await FormatConverter().tool_call(FormatConverter_input_schema(
        input_path=str(path), input_format='log', output_path=str(csv_path), output_format='csv'), session=None)
    assert result.is_success, result.message
    with csv_path.open() as handle:
        rows = list(csv.DictReader(handle))
    assert float(rows[0]['electronic_energy_hartree']) == -75.1
    assert 'scf_energy_hartree' not in rows[0]
