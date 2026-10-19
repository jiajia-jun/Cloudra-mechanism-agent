"""Native requests survive rendering; advice reaches the actual tool receipt."""

from pathlib import Path

import pytest

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.calculation_intent import compare_calculation_input, inspect_input, validate_writer_request


async def write(tmp_path, engine='orca', **settings):
    source = tmp_path / 'water.xyz'
    source.write_text('3\nwater\nO 0 0 0\nH 0 1 0\nH 1 0 0\n')
    arguments = dict(engine=engine, method='HF', basis_set='STO-3G',
        source_type='xyz_file', source_value=str(source), charge=0,
        output_path=str(tmp_path / ('job.gjf' if engine == 'gaussian' else 'job.inp')))
    request = QmInputWriter_input_schema(**{**arguments, **settings})
    result = await QmInputWriter().tool_call(request, None)
    assert result.is_success, result.message
    return result, Path(result.input_path).read_text()


@pytest.mark.asyncio
@pytest.mark.parametrize('task,value', [('opt', 'tight'), ('opt', 'maxcycles=2'), ('irc', 'forward')])
async def test_orca_task_parameters_are_preserved_and_warned(tmp_path, task, value):
    result, content = await write(tmp_path, task_type=[{task: value}])
    assert value in content
    assert result.warnings and all(entry['severity'] == 'warning' for entry in result.warnings)
    assert value in result.calculation.keywords
    assert not compare_calculation_input(content, result.calculation.model_dump(), charge=0, multiplicity=1)


@pytest.mark.asyncio
async def test_gaussian_analytic_mode_and_extra_frequency_options_round_trip(tmp_path):
    result, content = await write(tmp_path, engine='gaussian', task_type=[{'freq': 'NoRaman'}], frequency_mode='analytic')
    assert 'NoRaman' in content and 'analytic' in content
    assert result.interpreted_intent['frequency_mode'] == 'analytic'
    assert not compare_calculation_input(content, result.calculation.model_dump(), charge=0, multiplicity=1)


@pytest.mark.asyncio
async def test_gaussian_numeric_mode_keeps_native_frequency_options(tmp_path):
    result, content = await write(tmp_path, engine='gaussian', task_type=[{'freq': 'NoRaman'}], frequency_mode='numeric')
    assert 'NoRaman' in content and 'numer' in content
    assert result.interpreted_intent['frequency_mode'] == 'numeric'


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,task', [('orca', 'EnGrad'), ('orca', 'NativeFutureTask'), ('gaussian', 'Force')])
async def test_arbitrary_native_tasks_are_written_without_single_point_guess(tmp_path, engine, task):
    result, content = await write(tmp_path, engine=engine, task_type=[{task: None}])
    assert task.lower() in content.lower()
    assert result.warnings
    assert result.interpreted_intent['tasks'] == []
    assert result.interpreted_intent['certainty'] == 'unknown'
    assert not compare_calculation_input(content, result.calculation.model_dump(), charge=0, multiplicity=1)


@pytest.mark.parametrize('engine,content', [
    ('orca', '! EnGrad HF STO-3G\n* xyz 0 1\nH 0 0 0\n*\n'),
    ('gaussian', '#p Force HF/STO-3G\n\nt\n\n0 1\nH 0 0 0\n\n'),
])
def test_native_noncanonical_tasks_stay_unclassified(engine, content):
    actual = inspect_input(content, engine=engine)
    assert actual.tasks == set()
    assert actual.certainty == 'unknown'


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,field,value', [
    ('orca', 'end_setting', 'NativeTrailingSetting'),
    ('gaussian', 'orca_blocks', '%geom MaxIter 17 end'),
])
async def test_inapplicable_native_fields_are_visible_and_warned(tmp_path, engine, field, value):
    result, content = await write(tmp_path, engine=engine, **{field: value})
    assert value in content
    assert getattr(result.calculation, field) == value
    assert any(entry['field'] == field for entry in result.warnings)


@pytest.mark.asyncio
async def test_native_keywords_explicit_task_suppresses_implicit_opt_default(tmp_path):
    result, content = await write(tmp_path, keywords='EnGrad')
    assert 'EnGrad' in content.splitlines()[0] and ' Opt ' not in content.splitlines()[0]
    assert result.interpreted_intent['certainty'] == 'unknown'


@pytest.mark.asyncio
async def test_conflicting_frequency_settings_are_not_rewritten(tmp_path):
    result, content = await write(tmp_path, engine='gaussian', task_type=[{'freq': 'numer,NoRaman'}], frequency_mode='analytic')
    assert 'numer,NoRaman' in content
    assert any(entry['code'] == 'conflicting_frequency_mode' for entry in result.warnings)


@pytest.mark.asyncio
async def test_renderer_parameter_loss_still_refuses_file(tmp_path, monkeypatch):
    original = QmInputWriter.render_input

    def drop_parameter(request, mol):
        return original(request, mol).replace('NoRaman', '')

    monkeypatch.setattr(QmInputWriter, 'render_input', staticmethod(drop_parameter))
    source = tmp_path / 'water.xyz'
    source.write_text('1\nwater\nO 0 0 0\n')
    request = QmInputWriter_input_schema(engine='gaussian', method='HF', basis_set='STO-3G',
        source_type='xyz_file', source_value=str(source), charge=0,
        task_type=[{'freq': 'NoRaman'}], output_path=str(tmp_path / 'broken.gjf'))
    result = await QmInputWriter().tool_call(request, None)
    assert not result.is_success
    assert 'internal mismatch' in result.message
    assert result.unapplied_options
    assert not (tmp_path / 'broken.gjf').exists()


@pytest.mark.asyncio
async def test_malformed_native_task_does_not_mask_renderer_data_loss(tmp_path, monkeypatch):
    original = QmInputWriter.render_input

    def drop_task(request, mol):
        return original(request, mol).replace('futuretask=native(', '')

    monkeypatch.setattr(QmInputWriter, 'render_input', staticmethod(drop_task))
    source = tmp_path / 'water.xyz'
    source.write_text('1\nwater\nO 0 0 0\n')
    request = QmInputWriter_input_schema(engine='gaussian', method='HF', basis_set='STO-3G',
        source_type='xyz_file', source_value=str(source), charge=0,
        task_type=[{'FutureTask': 'native('}], output_path=str(tmp_path / 'broken.gjf'))
    result = await QmInputWriter().tool_call(request, None)
    assert not result.is_success
    assert 'task_type token' in result.message
    assert not (tmp_path / 'broken.gjf').exists()


@pytest.mark.parametrize('block', ['%geom Calc_Hess true end', '%irc Direction both InitHess calc_numfreq end'])
def test_unrequested_solver_options_are_visible_comparison_differences(block):
    expected = dict(engine='orca', method='HF', basis_set='STO-3G', keywords='OptTS')
    content = f'! OptTS HF STO-3G\n{block}\n* xyz 0 1\nO 0 0 0\n*\n'
    assert any(item.field == 'orca_blocks' for item in compare_calculation_input(content, expected, charge=0, multiplicity=1))


def test_calculation_option_advice_has_severity_and_never_requires_solver_options():
    advice = validate_writer_request({'engine': 'orca', 'task_type': [{'opt': 'ts,calcfc,noeigen'}]})
    assert advice and all(entry['severity'] == 'warning' for entry in advice)
    assert not validate_writer_request({'engine': 'gaussian', 'task_type': [{'opt': 'ts,readfc'}]})


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,settings,raw', [
    ('orca', {'keywords': 'Opt=('}, 'Opt=('),
    ('gaussian', {'keywords': 'opt=('}, 'opt=('),
    ('orca', {'orca_blocks': '%geom\n MaxIter 50'}, '%geom\n MaxIter 50'),
    ('gaussian', {'task_type': [{'FutureTask': 'native('}]}, 'native('),
    ('gaussian', {'end_setting': 'NativeSetting('}, 'NativeSetting('),
    ('orca', {'end_setting': 'NativeSetting('}, 'NativeSetting('),
])
async def test_native_lexical_errors_are_preserved_with_visible_warning(tmp_path, engine, settings, raw):
    result, content = await write(tmp_path, engine=engine, **settings)
    assert raw in content
    assert any(entry['code'].startswith('malformed_native') for entry in result.warnings)


@pytest.mark.asyncio
async def test_bad_native_constraint_warns_without_erasing_known_task(tmp_path):
    block = '%geom\n Constraints\n {B x 1 1.0 C}\n end\nend'
    result, content = await write(tmp_path, keywords='OptTS', orca_blocks=block)
    assert block in content
    assert result.interpreted_intent['tasks'] == ['ts_opt']
    assert any(entry['code'] == 'native_constraint_parameters' for entry in result.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize('settings,original', [
    ({'method': 'HF TightSCF'}, 'HF TightSCF'),
    ({'method': 'HF/STO-3G'}, 'HF/STO-3G'),
    ({'basis_set': 'STO-3G ExtraBasisOption'}, 'STO-3G ExtraBasisOption'),
    ({'keywords': 'STO-3G'}, 'STO-3G'),
])
async def test_native_field_layout_errors_reach_tool_as_warnings(tmp_path, settings, original):
    result, content = await write(tmp_path, **settings)
    assert original in content
    assert result.warnings


@pytest.mark.asyncio
async def test_gaussian_both_native_tail_fields_survive(tmp_path):
    result, content = await write(tmp_path, engine='gaussian', end_setting='B 1 2 F',
        orca_blocks='%geom MaxIter 17 end')
    assert 'B 1 2 F' in content and '%geom MaxIter 17 end' in content
    assert any(entry['code'] == 'orca_only_field' for entry in result.warnings)


@pytest.mark.asyncio
async def test_orca_small_explicit_memory_is_not_increased_to_a_floor(tmp_path):
    _, content = await write(tmp_path, mem='512MB', nproc=4)
    assert '%maxcore 128\n' in content
