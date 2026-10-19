"""The same native task and independent log facts drive both TS engines."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema, _parse_freq_log
from cloudra.tools.core import ts_process
from cloudra.tools.core.calculation_intent import (
    declared_native_tasks,
    inspect_input,
    intent_from_writer,
    validate_writer_request,
)
from tests.test_ts_native_option_intent import native_record
from tests.ts_fixtures import native_qm_log


@pytest.mark.parametrize('declaration', [
    {'keywords': 'AnFreq'},
    {'task_type': [{'AnFreq': None}]},
])
def test_orca_analytic_frequency_alias_has_one_input_intent(declaration):
    request = dict(engine='orca', method='HF', basis_set='STO-3G', **declaration)
    assert declared_native_tasks(request) == ({'frequency'}, [])
    intent = intent_from_writer(request)
    assert intent.tasks == {'frequency'}
    assert intent.frequency_mode == 'analytic'
    assert not validate_writer_request(request)
    native = inspect_input('! HF STO-3G AnFreq\n* xyz 0 1\nO 0 0 0\n*\n', engine='orca')
    assert native.tasks == {'frequency'}
    assert native.frequency_mode == 'analytic'


def test_orca_analytic_frequency_alias_detects_conflicting_numeric_request():
    advice = validate_writer_request(dict(engine='orca', method='HF', basis_set='STO-3G',
        keywords='AnFreq', frequency_mode='numeric'))
    assert any(item['code'] == 'conflicting_frequency_mode' for item in advice)


@pytest.mark.usefixtures('rdkit_chemistry')
def test_ts_preserves_explicit_anfreq_without_adding_optimization(tmp_path):
    record = native_record(tmp_path, 'orca', 'AnFreq')
    directory = tmp_path / 'refine'
    directory.mkdir()
    error, path = ts_process._write_refinement_input(record, str(directory))
    assert not error, error
    content = Path(path).read_text()
    assert '! HF STO-3G AnFreq' in content
    assert 'optts' not in content.lower()


def test_written_calculation_retains_native_analytic_frequency_mode(tmp_path):
    request = QmInputWriter_input_schema(engine='orca', method='HF', basis_set='STO-3G',
        keywords='AnFreq', task_type=[], source_type='xyz_file', source_value='geometry.xyz',
        output_path=str(tmp_path / 'freq.inp'), charge=0)
    written = QmInputWriter._written_calculation(request)
    assert written.keywords == 'AnFreq'
    assert written.frequency_mode == 'analytic'


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('alias', ['AnFreq', 'NumFreq'])
@pytest.mark.parametrize('native_keywords', [False, True])
def test_native_frequency_alias_parameters_remain_advisory(tmp_path, alias, native_keywords):
    record = native_record(tmp_path, 'orca')
    declaration = {'task_type': [], 'keywords': alias + '=not_an_option'} if native_keywords else {
        'task_type': [{alias: 'not_an_option'}], 'keywords': ''}
    request = QmInputWriter_input_schema(engine='orca', method='HF', basis_set='STO-3G',
        **declaration, source_type='xyz_file', source_value='geometry.xyz',
        output_path=str(tmp_path / 'freq.inp'), charge=0)
    advice = validate_writer_request(request.model_dump())
    assert any(item['code'] == 'native_task_parameters' and item['severity'] == 'warning' for item in advice)
    content = QmInputWriter.render_input(request, record.structures.candidate)
    assert alias + '=not_an_option' in content
    assert not QmInputWriter.validate_rendered_input(request, content, charge=0)
    assert inspect_input(content, engine='orca').tasks == {'frequency'}


def native_frequency_text(engine, *, normal=True, opt_converged=True):
    return native_qm_log(engine, ['O', 'H', 'H'],
        [[0., 0., 0.], [.96, 0., 0.], [-.24, .93, 0.]],
        optimization=opt_converged, normal=normal, frequencies=[-350.0, 1000.0, 2000.0])


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
@pytest.mark.parametrize('parser_success', [False, True])
@pytest.mark.parametrize('strict', [False, True])
def test_failed_frequency_never_becomes_a_candidate_from_earlier_opt(
    tmp_path, monkeypatch, engine, parser_success, strict,
):
    import cclib

    path = tmp_path / f'{engine}.out'
    path.write_text(native_frequency_text(engine, normal=False))
    data = SimpleNamespace(optdone=True, vibfreqs=[-350.0, 1000.0, 2000.0]) if parser_success else None
    monkeypatch.setattr(cclib.io, 'ccread', lambda *_a, **_k: data)
    parsed = _parse_freq_log(str(path), engine)
    assert parsed['normal_termination'] is False
    assert parsed['opt_converged'] is True
    result = TsGuess()._verify(TsGuess_input_schema(mode='verify', engine=engine,
        freq_log=str(path), strict=strict))
    assert result.is_success
    assert result.verification_status == 'inconclusive'


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_native_nonconvergence_overrides_cclib_optdone_in_frequency_analysis(tmp_path, monkeypatch, engine):
    import cclib

    path = tmp_path / f'{engine}.out'
    path.write_text(native_frequency_text(engine, opt_converged=False))
    monkeypatch.setattr(cclib.io, 'ccread', lambda *_a, **_k:
        SimpleNamespace(optdone=True, vibfreqs=[-350.0, 1000.0, 2000.0]))
    parsed = _parse_freq_log(str(path), engine)
    assert parsed['normal_termination'] is True
    assert parsed['opt_converged'] is False
    result = TsGuess()._verify(TsGuess_input_schema(mode='verify', engine=engine, freq_log=str(path)))
    assert result.verification_status == 'inconclusive'


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_ts_frequency_followup_uses_native_geometry_when_cclib_cannot_read(tmp_path, monkeypatch, engine):
    import cclib

    monkeypatch.setattr(cclib.io, 'ccread', lambda *_a, **_k: None)
    record = native_record(tmp_path, engine)
    log = tmp_path / 'native-opt.out'
    log.write_text(native_frequency_text(engine))
    step = ts_process.TsJobStep(purpose='ts_opt', state='done', input_path=str(tmp_path / 'opt.inp'),
        actual_calculation=record.input.ts_optimization, external_source={'log_path': str(log)})
    record.job_steps = [step]
    target = tmp_path / 'next-frequency'
    target.mkdir()
    error, path = ts_process._write_frequency_input(record, str(target))
    assert not error, error
    assert Path(path).is_file()
    geometry = inspect_input(Path(path).read_text(), engine=engine)
    assert geometry.tasks == {'frequency'}
    assert (target / 'optimized.xyz').read_text().splitlines()[0] == '3'


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
@pytest.mark.parametrize('opt_state', [False, None])
def test_ts_frequency_followup_requires_proven_native_opt_convergence(tmp_path, engine, opt_state):
    record = native_record(tmp_path, engine)
    log = tmp_path / 'native-opt.out'
    log.write_text(native_frequency_text(engine, opt_converged=opt_state))
    step = ts_process.TsJobStep(purpose='ts_opt', state='done', input_path=str(tmp_path / 'opt.inp'),
        actual_calculation=record.input.ts_optimization, external_source={'log_path': str(log)})
    record.job_steps = [step]
    target = tmp_path / 'next-frequency'
    target.mkdir()
    error, path = ts_process._write_frequency_input(record, str(target))
    assert not path
    assert 'convergence' in error
    assert not (target / 'optimized.xyz').exists()


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_endpoint_optimization_requires_native_convergence_despite_cclib_optdone(tmp_path, monkeypatch, engine):
    import cclib
    import numpy as np

    record = native_record(tmp_path, engine)
    log = tmp_path / 'native-opt.out'
    log.write_text(native_frequency_text(engine, opt_converged=False))
    monkeypatch.setattr(cclib.io, 'ccread', lambda *_a, **_k: SimpleNamespace(optdone=True,
        atomnos=np.array([8, 1, 1]), atomcoords=np.array([[[0., 0., 0.], [.96, 0., 0.], [-.24, .93, 0.]]]),
        scfenergies=[-27.2], vibfreqs=[]))
    step = ts_process.TsJobStep(purpose='reactant_opt', state='done',
        actual_calculation=record.input.verification.reactant_endpoint.optimization,
        external_source={'log_path': str(log)})
    xyz, error = ts_process._endpoint_opt_frame(record, step)
    assert not xyz
    assert 'convergence' in error


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_later_different_geometry_cannot_reuse_earlier_frequency_qualification(
    tmp_path, monkeypatch, mock_session, engine,
):
    import cclib

    path = tmp_path / f'{engine}.out'
    second = native_qm_log(engine, ['O', 'H', 'H'],
        [[0., 0., 0.], [5., 0., 0.], [-.24, .93, 0.]], optimization=None)
    second = second.replace('! Freq', '! SP').replace(' # freq', ' # sp')
    path.write_text(native_frequency_text(engine) + second)
    monkeypatch.setattr(cclib.io, 'ccread', lambda *_a, **_k: None)
    result = await TsGuess().safe_call(TsGuess_input_schema(mode='verify', engine=engine,
        freq_log=str(path)), mock_session)
    assert result.verification_status not in {'candidate', 'pass'}
    xyz, reason = ts_process._native_optimization_xyz(str(path), engine)
    assert not xyz
    assert 'convergence' in reason


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_unreadable_endpoint_frequency_geometry_cannot_crash_minimum_validation(tmp_path, engine):
    record = native_record(tmp_path, engine)
    opt_log = tmp_path / 'opt.out'
    freq_log = tmp_path / 'freq.out'
    opt_log.write_text(native_frequency_text(engine))
    freq_log.write_text(native_qm_log(engine, ['O', 'H', 'H'],
        [[0., 0., 0.], [.96, 0., 0.], [-.24, .93, 0.]],
        optimization=None, frequencies=[100., 200., 300.]).replace('0.96000000', 'unreadable'))
    (tmp_path / 'optimized.xyz').write_text('3\noptimized\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n')
    record.job_steps = [ts_process.TsJobStep(purpose=purpose, state='done',
        input_path=str(tmp_path / (purpose + '.inp')), actual_calculation=calculation,
        external_source={'log_path': str(log)})
        for purpose, calculation, log in [
            ('reactant_opt', record.input.verification.reactant_endpoint.optimization, opt_log),
            ('reactant_frequency', record.input.verification.reactant_endpoint.frequency, freq_log),
        ]]
    minimum, reason = ts_process._validated_endpoint_minimum(record, 'reactant')
    assert minimum is None
    assert 'geometry' in reason
