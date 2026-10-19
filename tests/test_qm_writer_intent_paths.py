"""Writer task intent and Gaussian output paths agree with the rendered input."""

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.calculation_intent import compare_calculation_input, intent_from_writer, validate_writer_request
from cloudra.tools.core.molecule import read_molecule

pytest.importorskip('rdkit')
H2 = '2\nhydrogen\nH 0 0 0\nH 0 0 .74\n'
PEROXIDE = '4\nperoxide\nO 0 0 0\nO 0 0 1.45\nH .9 0 -.3\nH 0 .9 1.75\n'


def _request(tmp_path, **changes):
    source = tmp_path / 'source.xyz'
    source.write_text(PEROXIDE)
    values = dict(engine='gaussian', method='HF', basis_set='STO-3G', charge=0,
        source_type='xyz_file', source_value='source.xyz', output_path='runs/input.gjf')
    values.update(changes)
    return QmInputWriter_input_schema(**values)


def _writer(tmp_path):
    return QmInputWriter(subagent=SimpleNamespace(working_directory=str(tmp_path)))


@pytest.mark.asyncio
@pytest.mark.parametrize('card', ['B 1 2 S 4 0.05', 'A 1 2 3 S 4 5.',
    'D 1 2 3 4 S 12 15.0', 'B 1 2 1.45 S 4 0.05'])
async def test_modredundant_scan_tail_normalizes_before_independent_round_trip(tmp_path, card):
    request = _request(tmp_path, task_type=[{'opt': 'modredundant'}], end_setting=card)

    result = await _writer(tmp_path).tool_call(request, None)

    assert result.is_success, result.message
    assert intent_from_writer(request.model_dump()).tasks == {'relaxed_scan'}
    assert result.interpreted_intent['tasks'] == ['relaxed_scan']
    assert card in Path(result.input_path).read_text()


@pytest.mark.asyncio
@pytest.mark.parametrize('tail,title', [('B 1 2 F', 'ordinary optimization'), ('', 'B 1 2 S 4 0.05')])
async def test_freeze_and_scan_words_in_title_do_not_turn_optimization_into_scan(tmp_path, tail, title):
    request = _request(tmp_path, task_type=[{'opt': 'modredundant'}], end_setting=tail, title=title)

    result = await _writer(tmp_path).tool_call(request, None)

    assert result.is_success, result.message
    assert result.interpreted_intent['tasks'] == ['minimum_opt']


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,task_type,keywords,tasks', [
    ('gaussian', [{'freq': None}], 'irc=(calcfc,stepsize=5,maxpoints=40)', {'frequency', 'irc'}),
    ('gaussian', [], 'opt=(modredundant) freq=numer', {'minimum_opt', 'frequency'}),
    ('orca', [{'opt': None}], 'NumFreq', {'minimum_opt', 'frequency'}),
    ('orca', [{'freq': None}], 'IRC', {'frequency', 'irc'}),
])
async def test_native_task_keywords_participate_in_request_intent(tmp_path, engine, task_type, keywords, tasks):
    request = _request(tmp_path, engine=engine, task_type=task_type, keywords=keywords)

    result = await _writer(tmp_path).tool_call(request, None)

    assert result.is_success, result.message
    assert intent_from_writer(request.model_dump()).tasks == tasks
    assert set(result.interpreted_intent['tasks']) == tasks
    assert keywords in Path(result.input_path).read_text()


@pytest.mark.asyncio
async def test_native_modredundant_keyword_uses_the_actual_scan_tail(tmp_path):
    request = _request(tmp_path, task_type=[], keywords='opt=(modredundant) freq',
        end_setting='B 1 2 S 4 0.05')

    result = await _writer(tmp_path).tool_call(request, None)

    assert result.is_success, result.message
    assert set(result.interpreted_intent['tasks']) == {'relaxed_scan', 'frequency'}


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,keyword', [('gaussian', 'irc=calcfc'), ('orca', 'IRC')])
async def test_written_native_task_keywords_survive_downstream_calculation_comparison(tmp_path, engine, keyword):
    request = _request(tmp_path, engine=engine, task_type=[{'freq': None}], keywords=keyword)
    result = await _writer(tmp_path).tool_call(request, None)
    assert result.is_success, result.message
    content = Path(result.input_path).read_text()
    expected = result.calculation.model_dump()

    differences = compare_calculation_input(content, expected, charge=0, multiplicity=1)

    assert not differences, differences
    # Accepting task keywords must not let their actual omission go unnoticed.
    dropped = compare_calculation_input(content.replace(keyword, ''), expected, charge=0, multiplicity=1)
    assert any(item.field == 'keywords' for item in dropped)


@pytest.mark.asyncio
async def test_numeric_mode_accepts_a_frequency_task_declared_in_native_keywords(tmp_path):
    request = _request(tmp_path, task_type=[{'opt': None}], keywords='freq=numer', frequency_mode='numeric')

    result = await _writer(tmp_path).tool_call(request, None)

    assert result.is_success, result.message
    assert result.interpreted_intent['frequency_mode'] == 'numeric'


@pytest.mark.parametrize('values,fields', [
    ({'task_type': [{'opt': 'ts'}], 'keywords': 'opt'}, ['task_type', 'keywords']),
    ({'task_type': [{'freq': None}], 'frequency_mode': 'analytic', 'keywords': 'freq=numer'}, ['frequency_mode', 'keywords']),
])
def test_conflicting_native_task_settings_report_the_actual_fields(values, fields):
    entries = validate_writer_request(dict(engine='gaussian', **values))

    assert entries
    combined = ' '.join(entry['field'] + ' ' + entry['message'] for entry in entries)
    assert all(field in combined for field in fields)


def test_unbalanced_native_keyword_reports_its_field():
    entries = validate_writer_request(dict(engine='gaussian', task_type=[{'freq': None}], keywords='irc=(calcfc'))

    assert any(entry['field'] == 'keywords' and 'parentheses' in entry['message'] for entry in entries)


@pytest.mark.asyncio
@pytest.mark.parametrize('extra', [False, True], ids=['dropped-requested-irc', 'injected-unrequested-irc'])
async def test_independent_inspection_still_rejects_renderer_task_mismatch(tmp_path, monkeypatch, extra):
    request = _request(tmp_path, task_type=[{'freq': None}], keywords='' if extra else 'irc=calcfc')
    original = QmInputWriter.render_input

    def faulty_render(declaration, molecule):
        content = original(declaration, molecule)
        return content.replace('#p freq', '#p freq irc', 1) if extra else content.replace('irc=calcfc', '')

    monkeypatch.setattr(QmInputWriter, 'render_input', staticmethod(faulty_render))

    result = await _writer(tmp_path).tool_call(request, None)

    assert not result.is_success
    assert 'internal mismatch' in result.message
    assert 'irc' in result.unapplied_options
    assert not (tmp_path / 'runs/input.gjf').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('checkpoint', ['nested', 'basename', 'omitted', 'absolute'])
async def test_gaussian_checkpoint_paths_follow_agent_working_directory(tmp_path, checkpoint):
    values = {
        'nested': ('runs/input.chk', tmp_path / 'runs/input.chk'),
        'basename': ('restart.chk', tmp_path / 'restart.chk'),
        'omitted': (None, tmp_path / 'runs/input.chk'),
        'absolute': (str(tmp_path / 'elsewhere/deep/restart.chk'), tmp_path / 'elsewhere/deep/restart.chk'),
    }
    name, expected = values[checkpoint]
    request = _request(tmp_path, chk_name=name)

    result = await _writer(tmp_path).tool_call(request, None)

    assert result.is_success, result.message
    assert f'%chk={expected}\n' in Path(result.input_path).read_text()
    assert expected.parent.is_dir()
    assert not expected.exists()  # Input writing does not create a checkpoint.


@pytest.mark.asyncio
async def test_explicit_rwf_and_fchk_paths_are_normalized_and_their_parents_created(tmp_path):
    request = _request(tmp_path, rwf_name='scratch/nested/job.rwf', fchk_name='exports/nested/job.fchk')

    result = await _writer(tmp_path).tool_call(request, None)

    assert result.is_success, result.message
    text = Path(result.input_path).read_text()
    assert f'%rwf={tmp_path / "scratch/nested/job.rwf"}\n' in text
    assert f'%fchk={tmp_path / "exports/nested/job.fchk"}\n' in text
    assert (tmp_path / 'scratch/nested').is_dir()
    assert (tmp_path / 'exports/nested').is_dir()


@pytest.mark.asyncio
async def test_writer_does_not_open_or_replace_an_existing_checkpoint(tmp_path):
    checkpoint = tmp_path / 'restart.chk'
    checkpoint.write_bytes(b'existing native checkpoint')
    request = _request(tmp_path, chk_name='restart.chk')

    result = await _writer(tmp_path).tool_call(request, None)

    assert result.is_success, result.message
    assert checkpoint.read_bytes() == b'existing native checkpoint'


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['chk_name', 'rwf_name', 'fchk_name'])
@pytest.mark.parametrize('bad_target', ['parent_is_file', 'target_is_directory'])
async def test_gaussian_explicit_file_path_errors_name_the_field_before_input_write(tmp_path, field, bad_target):
    if bad_target == 'parent_is_file':
        (tmp_path / 'blocked').write_text('regular file')
        target = 'blocked/file.dat'
    else:
        (tmp_path / 'blocked').mkdir()
        target = 'blocked'
    request = _request(tmp_path, **{field: target})

    result = await _writer(tmp_path).tool_call(request, None)

    assert not result.is_success
    assert field in result.message
    assert str(tmp_path / target) in result.message
    assert not (tmp_path / 'runs/input.gjf').exists()


@pytest.mark.asyncio
async def test_checkpoint_parent_without_write_access_is_reported_before_input_write(tmp_path, monkeypatch):
    request = _request(tmp_path, chk_name='checkpoint/restart.chk')
    original = os.access
    parent = tmp_path / 'checkpoint'
    monkeypatch.setattr(os, 'access', lambda path, mode: False if Path(path) == parent else original(path, mode))

    result = await _writer(tmp_path).tool_call(request, None)

    assert not result.is_success
    assert 'chk_name' in result.message and 'not writable' in result.message
    assert not (tmp_path / 'runs/input.gjf').exists()


def test_rendering_gaussian_input_does_not_create_directories(tmp_path):
    request = _request(tmp_path, output_path=str(tmp_path / 'missing/input.gjf'),
        chk_name=str(tmp_path / 'checkpoint/deep/file.chk'))

    native = QmInputWriter.render_input(request, read_molecule(input_text=H2, charge=0))

    assert '%chk=' in native
    assert not (tmp_path / 'missing').exists()
    assert not (tmp_path / 'checkpoint').exists()


@pytest.mark.asyncio
async def test_normalized_checkpoint_opens_from_the_real_calculator_working_directory(tmp_path):
    request = _request(tmp_path, chk_name='runs/input.chk')
    result = await _writer(tmp_path).tool_call(request, None)
    assert result.is_success, result.message
    fakebin = tmp_path / 'bin'
    fakebin.mkdir()
    executable = fakebin / 'g16'
    executable.write_text('#!' + sys.executable + '\n'
        'import sys\nfrom pathlib import Path\n'
        'text = Path(sys.argv[1]).read_text()\n'
        'name = next(line.partition("=")[2] for line in text.splitlines() if line.startswith("%chk="))\n'
        'Path(name).write_bytes(b"checkpoint open probe; no QM")\n')
    executable.chmod(0o755)
    environment = dict(os.environ, PATH=str(fakebin) + os.pathsep + os.defpath)
    environment.pop('GAUSS_SCRDIR', None)
    calculator = Path(__file__).resolve().parents[1] / 'cloudra/calculator.sh'

    process = await asyncio.create_subprocess_exec('bash', str(calculator), result.input_path, 'gaussian',
        cwd=tmp_path, env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    output, errors = await process.communicate()

    assert process.returncode == 0, (output, errors)
    assert (tmp_path / 'runs/input.chk').is_file()
    assert not (tmp_path / 'runs/runs').exists()
