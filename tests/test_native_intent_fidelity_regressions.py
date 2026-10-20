"""Native declarations survive inspection; trusted file values stay case-sensitive."""

from pathlib import Path

import pytest

from cloudra.tools.core.calculation_intent import (
    declared_native_tasks,
    inspect_input,
    intent_from_writer,
    native_tokens,
    validate_writer_request,
)


@pytest.mark.parametrize('quote', ['"', "'"])
def test_native_tokens_preserve_quoted_values_while_normalizing_directives(quote):
    text = f'SCF=Tight External={quote}/CaseSensitive/Run!QM{quote} Ext_Params {quote}--Model /Models/Native.HESS{quote}'

    assert native_tokens(text) == [
        'scf=tight', f'external={quote}/CaseSensitive/Run!QM{quote}',
        'ext_params', f'{quote}--Model /Models/Native.HESS{quote}',
    ]


@pytest.mark.parametrize('candidate_name,rejected', [('mixedcase.hess', True), ('MixedCase.HESS', False)])
def test_trusted_irc_hessian_path_is_checked_before_compute_admission(tmp_path, monkeypatch, candidate_name, rejected):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.qm_calculation import QmCalculation
    from cloudra.tools.core.ts_process import _submit_step
    from tests.test_ts_stage_inputs import record_fixture

    # These files are distinct audit dependencies, never scientific evidence.
    declared = tmp_path / 'MixedCase.HESS'
    candidate = tmp_path / 'mixedcase.hess'
    declared.write_text('declared dependency')
    candidate.write_text('different dependency')
    assert declared.read_bytes() != candidate.read_bytes()
    blocks = f'%irc\n InitHess read\n Hess_Filename "{declared}"\nend'
    calculation = QmCalculation(engine='orca', method='HF', basis_set='STO-3G',
        keywords='IRC', orca_blocks=blocks)
    record = record_fixture(tmp_path)
    record.input.verification.irc = calculation
    source = tmp_path / 'irc.inp'
    source.write_text('! IRC HF STO-3G\n' + blocks.replace(str(declared), str(tmp_path / candidate_name))
        + '\n* xyz 0 1\nO 0 0 0\n*\n')
    before = source.read_bytes()
    policy = MethodPolicy(allowed_methods=['hf/sto3g'],
        calculation_contracts={'irc': calculation.model_dump()})

    # The actual contract gate runs; stop before scheduler or ledger mutation.
    def stop_before_admission(**_):
        return AdmissionOutcome(ok=False, message='test stops before compute admission')

    monkeypatch.setattr('cloudra.services.compute_admission.admit_job', stop_before_admission)
    with use_pipeline_authority(lambda *_: (True, policy)):
        error, job_id = _submit_step(record, 'irc', str(source), 'orca')

    assert job_id == -1 and source.read_bytes() == before
    if rejected:
        assert 'trusted irc calculation contract' in error
        assert 'orca_blocks' in error
        assert not record.method_checks[str(source)]['matched']
    else:
        assert error == 'test stops before compute admission'
        assert record.method_checks[str(source)]['matched']


@pytest.mark.asyncio
@pytest.mark.parametrize('comment', ['native route comment', 'Freq=(Numer)', 'unmatched ( "'])
async def test_gaussian_comments_do_not_change_requested_tasks_or_frequency(tmp_path, mock_session, comment):
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema

    source = tmp_path / 'source.xyz'
    source.write_text('1\nexplicit source\nHe 0 0 0\n')
    keywords = f'Opt=(TS,CalcFC) ! {comment}'
    request = QmInputWriter_input_schema(engine='gaussian', method='HF', basis_set='STO-3G',
        task_type=[], charge=0, source_type='xyz_file', source_value=str(source),
        output_path=str(tmp_path / 'job.gjf'), keywords=keywords)

    declared = intent_from_writer(request.model_dump())
    assert declared.tasks == {'ts_opt'}
    assert declared.frequency_mode == 'auto'
    advice = validate_writer_request(request.model_dump())
    assert not any(item['code'] in {'malformed_native_keywords', 'conflicting_frequency_mode'} for item in advice)
    result = await QmInputWriter().tool_call(request, mock_session)

    assert result.is_success, result.message
    assert keywords in Path(result.input_path).read_text()
    assert result.interpreted_intent['tasks'] == ['ts_opt']
    assert result.calculation.keywords == keywords


@pytest.mark.parametrize('quote', ['"', "'"])
def test_gaussian_comment_interpretation_preserves_bang_inside_quoted_value(quote):
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    keywords = f'External={quote}/CaseSensitive/Driver!Native{quote} ! Freq=(Numer)'
    request = dict(engine='gaussian', method='HF', basis_set='STO-3G',
        task_type=[], keywords=keywords)
    text = f'#p HF/STO-3G {keywords}\n\nTitle\n\n0 1\nHe 0 0 0\n\n'

    assert intent_from_writer(request).frequency_mode == 'auto'
    assert declared_native_tasks(request)[0] == set()
    assert compare_calculation_input(text, request, charge=0, multiplicity=1) == []
    changed = text.replace('Driver!Native', 'driver!native')
    assert any(item.field == 'keywords' for item in
        compare_calculation_input(changed, request, charge=0, multiplicity=1))


def test_calculation_comparison_preserves_spaces_inside_quoted_paths():
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    keywords = 'External="/CaseSensitive/Driver With Space"'
    request = dict(engine='gaussian', method='HF', basis_set='STO-3G', keywords=keywords)
    text = f'#p HF/STO-3G {keywords}\n\nTitle\n\n0 1\nHe 0 0 0\n\n'

    assert compare_calculation_input(text, request, charge=0, multiplicity=1) == []
    changed = text.replace('Driver With Space', 'DriverWithSpace')
    assert any(item.field == 'keywords' for item in
        compare_calculation_input(changed, request, charge=0, multiplicity=1))


def test_orca_request_comments_use_the_same_native_interpretation_as_files():
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    keywords = '# Opt Freq are comments # TightSCF'
    request = dict(engine='orca', method='HF', basis_set='STO-3G',
        task_type=[{'opt': 'ts'}], keywords=keywords)
    text = f'! OptTS HF STO-3G {keywords}\n* xyz 0 1\nHe 0 0 0\n*\n'

    assert intent_from_writer(request).tasks == {'ts_opt'}
    assert intent_from_writer(request).frequency_mode == 'auto'
    advice = validate_writer_request(request)
    assert not any(item['code'] in {'conflicting_task', 'duplicate_task_sources'} for item in advice)
    written = QmInputWriter._written_calculation(QmInputWriter_input_schema(**request,
        source_type='xyz_file', source_value='unused.xyz', output_path='unused.inp'))
    assert compare_calculation_input(text, written.model_dump(), charge=0, multiplicity=1) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('keywords,blocks,tasks', [
    ('', '%neb\n NEB_TS true\nend', {'ts_opt'}),
    ('NEB-TS', '%neb NEB_TS=false end', set()),
])
async def test_orca_neb_override_has_same_declared_and_written_tasks(tmp_path, mock_session, keywords, blocks, tasks):
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema

    source = tmp_path / 'source.xyz'
    source.write_text('1\nexplicit source\nHe 0 0 0\n')
    request = QmInputWriter_input_schema(engine='orca', method='HF', basis_set='STO-3G',
        task_type=[], charge=0, source_type='xyz_file', source_value=str(source),
        output_path=str(tmp_path / 'job.inp'), keywords=keywords, orca_blocks=blocks)
    result = await QmInputWriter().tool_call(request, mock_session)

    assert result.is_success, result.message
    text = Path(result.input_path).read_text()
    assert blocks in text and keywords in text
    assert declared_native_tasks(request.model_dump())[0] == tasks
    assert inspect_input(text, engine='orca').tasks == tasks


@pytest.mark.parametrize('engine,task,keywords', [
    ('gaussian', {'opt': 'TS'}, 'Opt=(TS,CalcFC)'),
    ('gaussian', {'freq': None}, 'Freq=(Numer,NoRaman)'),
    ('gaussian', {'irc': None}, 'IRC=(CalcFC,Reverse)'),
    ('orca', {'opt': 'ts'}, 'OptTS'),
    ('orca', {'freq': None}, 'NumFreq'),
    ('orca', {'irc': None}, 'IRC'),
])
def test_overlapping_task_sources_warn_without_combining_options(engine, task, keywords):
    arguments = dict(engine=engine, method='HF', basis_set='STO-3G', task_type=[task], keywords=keywords)
    before = dict(arguments, task_type=[dict(task)])

    advice = validate_writer_request(arguments)

    overlap = [item for item in advice if item['code'] == 'duplicate_task_sources']
    assert overlap and all(item['severity'] == 'warning' for item in overlap)
    assert 'task_type' in overlap[0]['message'] and 'keywords' in overlap[0]['message']
    assert arguments == before
    if engine == 'gaussian' and ('CalcFC' in keywords):
        assert not any(item['code'] == 'initial_hessian_unspecified' for item in advice)


@pytest.mark.parametrize('engine,expected_keywords,actual_keywords', [
    ('gaussian', 'Opt=TS', 'Opt=TS Opt=(TS,CalcFC)'),
    ('gaussian', 'Opt=TS', 'Opt=TS Opt=TS'),
    ('gaussian', 'SCF=Tight', 'SCF=Tight Opt=TS'),
    ('orca', 'OptTS', 'OptTS OptTS'),
    ('orca', 'OptTS', 'OptTS Opt'),
    ('orca', 'OptTS', 'OptTS Freq'),
    ('orca', 'GOAT', 'GOAT Opt'),
])
def test_explicit_native_contract_cannot_hide_extra_task_tokens(engine, expected_keywords, actual_keywords):
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    expected = dict(engine=engine, method='HF', basis_set='STO-3G', keywords=expected_keywords)
    if engine == 'orca':
        text = f'! HF STO-3G {actual_keywords}\n* xyz 0 1\nHe 0 0 0\n*\n'
    else:
        text = f'#p HF/STO-3G {actual_keywords}\n\nTitle\n\n0 1\nHe 0 0 0\n\n'

    assert any(item.field == 'keywords' for item in
        compare_calculation_input(text, expected, charge=0, multiplicity=1))


def test_explicit_native_block_cannot_hide_added_task():
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    expected = dict(engine='orca', method='HF', basis_set='STO-3G',
        keywords='', orca_blocks='%geom MaxIter 20 end')
    text = '! HF STO-3G OptTS\n%geom MaxIter 20 end\n* xyz 0 1\nHe 0 0 0\n*\n'

    assert any(item.field == 'keywords' for item in
        compare_calculation_input(text, expected, charge=0, multiplicity=1))


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_empty_native_contract_allows_basic_stage_tasks(engine):
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    expected = dict(engine=engine, method='HF', basis_set='STO-3G', keywords='')
    text = ('! HF STO-3G OptTS Freq\n* xyz 0 1\nHe 0 0 0\n*\n' if engine == 'orca'
        else '#p HF/STO-3G Opt=TS Freq\n\nTitle\n\n0 1\nHe 0 0 0\n\n')

    assert compare_calculation_input(text, expected, charge=0, multiplicity=1) == []


@pytest.mark.parametrize('engine,declared,extra', [
    ('gaussian', 'Opt=TS', 'Opt=(TS,CalcFC)'),
    ('orca', 'OptTS', 'Freq'),
])
def test_trusted_native_task_contract_rejects_extra_tasks_before_admission(tmp_path, monkeypatch, engine, declared, extra):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core.qm_calculation import QmCalculation
    from cloudra.tools.core.ts_process import _submit_step
    from tests.test_ts_stage_inputs import record_fixture

    calculation = QmCalculation(engine=engine, method='HF', basis_set='STO-3G', keywords=declared)
    record = record_fixture(tmp_path)
    record.input.ts_optimization = calculation
    source = tmp_path / ('native.inp' if engine == 'orca' else 'native.gjf')
    text = (f'! HF STO-3G {declared} {extra}\n* xyz 0 1\nHe 0 0 0\n*\n' if engine == 'orca'
        else f'#p HF/STO-3G {declared} {extra}\n\nTitle\n\n0 1\nHe 0 0 0\n\n')
    source.write_text(text)
    policy = MethodPolicy(allowed_methods=['hf/sto3g'],
        calculation_contracts={'ts_opt': calculation.model_dump()})
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=False, message='test stops before compute admission'))

    with use_pipeline_authority(lambda *_: (True, policy)):
        error, job_id = _submit_step(record, 'ts_opt', str(source), engine)

    assert job_id == -1 and 'trusted ts_opt calculation contract' in error
    assert source.read_text() == text


@pytest.mark.parametrize('engine,native_tasks', [
    ('gaussian', 'Opt=(TS,CalcFC)'),
    ('gaussian', 'IRC=(ReadFC,Reverse)'),
    ('orca', 'TightOpt'),
    ('orca', 'NumFreq'),
])
def test_empty_native_contract_does_not_authorize_solver_or_direction_options(engine, native_tasks):
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    expected = dict(engine=engine, method='HF', basis_set='STO-3G', keywords='')
    text = (f'! HF STO-3G {native_tasks}\n* xyz 0 1\nHe 0 0 0\n*\n' if engine == 'orca'
        else f'#p HF/STO-3G {native_tasks}\n\nTitle\n\n0 1\nHe 0 0 0\n\n')

    assert any(item.field == 'keywords' for item in
        compare_calculation_input(text, expected, charge=0, multiplicity=1))


@pytest.mark.parametrize('engine,mode,native_task', [
    ('gaussian', 'numeric', 'Freq=Numer'),
    ('gaussian', 'analytic', 'Freq=Analytic'),
    ('orca', 'numeric', 'NumFreq'),
    ('orca', 'analytic', 'Freq'),
])
def test_empty_native_contract_accepts_frequency_control_for_its_declared_mode(engine, mode, native_task):
    from cloudra.tools.core.calculation_intent import compare_calculation_input

    expected = dict(engine=engine, method='HF', basis_set='STO-3G', keywords='', frequency_mode=mode)
    text = (f'! HF STO-3G {native_task}\n* xyz 0 1\nHe 0 0 0\n*\n' if engine == 'orca'
        else f'#p HF/STO-3G {native_task}\n\nTitle\n\n0 1\nHe 0 0 0\n\n')

    assert compare_calculation_input(text, expected, charge=0, multiplicity=1) == []
