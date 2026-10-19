"""Observe TS intent across tool paths without executing the inspected operation."""

import pytest


def _inspect(tool_name, arguments, workspace):
    from cloudra.tools.core.ts_workflow_guard import inspect_ts_operation

    return inspect_ts_operation(tool_name, arguments, str(workspace))


def test_writer_reports_structured_ts_intent(tmp_path):
    result = _inspect('qm_input_writer', {
        'engine': 'orca', 'output_path': 'trial.inp', 'method': 'HF',
        'basis_set': 'STO-3G', 'task_type': [{'opt': 'ts'}, {'freq': None}],
    }, tmp_path)

    assert result == {'ts_inputs': [{
        'path': str(tmp_path / 'trial.inp'), 'engine': 'orca', 'tasks': ['ts_opt'],
    }]}


@pytest.mark.parametrize('tool_name', ['write', 'submit_compute_job'])
@pytest.mark.parametrize('engine,filename,content', [
    ('orca', 'input.inp', '! HF STO-3G OptTS Freq\n'),
    ('gaussian', 'input.gjf', '#p HF/STO-3G IRC=(CalcFC,Forward)\n\n'),
])
def test_native_files_report_actual_ts_or_irc_task(tmp_path, tool_name, engine, filename, content):
    path = tmp_path / filename
    arguments = {'path': filename, 'content': content}
    if tool_name == 'submit_compute_job':
        path.write_text(content)
        arguments = {'input_file': filename, 'job_type': engine}

    result = _inspect(tool_name, arguments, tmp_path)

    assert result == {'ts_inputs': [{
        'path': str(path), 'engine': engine,
        'tasks': ['ts_opt' if engine == 'orca' else 'irc'],
    }]}
    if tool_name == 'write':
        assert not path.exists()


@pytest.mark.parametrize('old_key,new_key', [
    ('old_string', 'new_string'), ('old_text', 'new_text'), ('old_str', 'new_str'),
])
def test_edit_inspects_complete_candidate_with_real_edit_aliases(tmp_path, old_key, new_key):
    path = tmp_path / 'trial.gjf'
    original = '#p HF/STO-3G Opt=(CalcFC)\n\ntrial\n\n0 1\nH 0 0 0\n\n'
    path.write_text(original)

    result = _inspect('edit', {'path': path.name, 'edits': [
        {old_key: 'CalcFC', new_key: 'CalcFC,TS'},
    ]}, tmp_path)

    assert result == {'ts_inputs': [{
        'path': str(path), 'engine': 'gaussian', 'tasks': ['ts_opt'],
    }]}
    assert path.read_text() == original


def test_invalid_edit_does_not_invent_a_candidate(tmp_path):
    path = tmp_path / 'trial.gjf'
    path.write_text('#p HF/STO-3G Opt\n\nOpt\n\n')

    result = _inspect('edit', {'path': path.name, 'edits': [
        {'old_string': 'Opt', 'new_string': 'Opt=TS'},
    ]}, tmp_path)

    assert result == {}


@pytest.mark.parametrize('command,filename,content,engine,task', [
    ('/opt/orca/orca "trial input.inp" > trial.out', 'trial input.inp', '! HF STO-3G OptTS\n', 'orca', 'ts_opt'),
    ('g16 < trial.gjf > trial.log', 'trial.gjf', '#p HF/STO-3G IRC\n\n', 'gaussian', 'irc'),
    ('env OMP_NUM_THREADS=2 g16 trial.gjf', 'trial.gjf', '#p HF/STO-3G Opt=TS\n\n', 'gaussian', 'ts_opt'),
])
def test_bash_engine_reads_only_the_executed_input(tmp_path, command, filename, content, engine, task):
    path = tmp_path / filename
    path.write_text(content)

    result = _inspect('bash', {'command': command}, tmp_path)

    assert result == {'ts_inputs': [{
        'path': str(path), 'engine': engine, 'tasks': [task],
    }], 'direct_execution': True}


@pytest.mark.parametrize('tool_name,arguments', [
    ('submit_compute_job', {'input_file': 'run.sh', 'job_type': 'shell'}),
    ('bash', {'command': 'bash run.sh'}),
    ('bash', {'command': './run.sh'}),
])
def test_shell_script_exposes_content_and_its_direct_native_input(tmp_path, tool_name, arguments):
    script = tmp_path / 'run.sh'
    script.write_text('#!/bin/bash\norca trial.inp > trial.out\n')
    native = tmp_path / 'trial.inp'
    native.write_text('! HF STO-3G OptTS\n')

    result = _inspect(tool_name, arguments, tmp_path)

    assert result == {
        'scripts': [{'path': str(script), 'content': script.read_text()}],
        'ts_inputs': [{'path': str(native), 'engine': 'orca', 'tasks': ['ts_opt']}],
        'direct_execution': True,
    }


def test_shell_submission_reads_input_relative_to_script_directory(tmp_path):
    folder = tmp_path / 'jobs'
    folder.mkdir()
    script = folder / 'run.sh'
    script.write_text('orca input.inp\n')
    native = folder / 'input.inp'
    native.write_text('! HF STO-3G IRC\n')

    result = _inspect('submit_compute_job', {
        'job_type': 'shell', 'input_file': 'jobs/run.sh',
    }, tmp_path)

    assert result['ts_inputs'] == [{'path': str(native), 'engine': 'orca', 'tasks': ['irc']}]


@pytest.mark.parametrize('tool_name,arguments', [
    ('bash', {'command': 'cd jobs && orca input.inp'}),
    ('submit_compute_job', {'job_type': 'shell', 'input_file': 'run.sh'}),
])
def test_changed_directory_selects_the_executed_native_input(tmp_path, tool_name, arguments):
    folder = tmp_path / 'jobs'
    folder.mkdir()
    native = folder / 'input.inp'
    native.write_text('! HF STO-3G OptTS\n')
    (tmp_path / 'input.inp').write_text('! HF STO-3G Opt\n')
    (tmp_path / 'run.sh').write_text('cd jobs && orca input.inp\n')

    result = _inspect(tool_name, arguments, tmp_path)

    assert result['ts_inputs'] == [{'path': str(native), 'engine': 'orca', 'tasks': ['ts_opt']}]


def test_python_script_stays_opaque_data_for_semantic_review(tmp_path):
    script = tmp_path / 'trial.py'
    content = 'from subprocess import run\nrun(["orca", "trial.inp"])\n'
    script.write_text(content)

    result = _inspect('bash', {'command': 'python3 trial.py'}, tmp_path)

    assert result == {'scripts': [{'path': str(script), 'content': content}], 'direct_execution': True}


def test_inline_python_and_ssh_commands_are_review_data(tmp_path):
    python = 'python3 -c \'print("OptTS")\''
    ssh = 'ssh cluster "orca /jobs/trial.inp > /jobs/trial.out"'

    assert _inspect('bash', {'command': python}, tmp_path) == {
        'scripts': [{'path': 'python3 -c', 'content': 'print("OptTS")'}], 'direct_execution': True,
    }
    assert _inspect('bash', {'command': ssh}, tmp_path) == {
        'scripts': [{'path': 'ssh', 'content': ssh}], 'direct_execution': True,
    }


def test_script_expansion_stops_after_one_level(tmp_path):
    first = tmp_path / 'first.sh'
    second = tmp_path / 'second.sh'
    first.write_text('bash second.sh\n')
    second.write_text('orca trial.inp\n')
    (tmp_path / 'trial.inp').write_text('! HF STO-3G OptTS\n')

    result = _inspect('bash', {'command': 'bash first.sh'}, tmp_path)

    assert result == {'scripts': [{'path': str(first), 'content': first.read_text()}], 'direct_execution': True}


@pytest.mark.parametrize('command', [
    'cat trial.inp', 'grep OptTS trial.inp', 'tail -50 trial.inp',
    'echo "orca trial.inp"', 'cat run.sh',
])
def test_read_only_arguments_do_not_become_executed_inputs(tmp_path, command):
    (tmp_path / 'trial.inp').write_text('! HF STO-3G OptTS\n')
    (tmp_path / 'run.sh').write_text('orca trial.inp\n')

    assert _inspect('bash', {'command': command}, tmp_path) == {}


@pytest.mark.parametrize('filename,content', [
    ('trial.inp', '# IRC OptTS are comments\n! HF STO-3G Opt Freq\n'),
    ('trial.inp', '! HF STO-3G\n%geom Scan\nB 0 1 = 1, 2, 5\nend\nend\n'),
    ('trial.gjf', '#p HF/STO-3G Opt Freq\n\nIRC OptTS are title text\n\n'),
    ('trial.gjf', '#p HF/STO-3G Opt=(ModRedundant)\n\nscan\n\n'),
])
def test_native_titles_comments_and_exploratory_scans_are_not_ts(tmp_path, filename, content):
    assert _inspect('write', {'path': filename, 'content': content}, tmp_path) == {}


def test_relative_inputs_prefer_the_agent_workspace(tmp_path, monkeypatch):
    other = tmp_path / 'other'
    other.mkdir()
    (tmp_path / 'trial.inp').write_text('! HF STO-3G IRC\n')
    (other / 'trial.inp').write_text('! HF STO-3G Opt\n')
    monkeypatch.chdir(other)

    result = _inspect('submit_compute_job', {'input_file': 'trial.inp', 'job_type': 'orca'}, tmp_path)

    assert result['ts_inputs'] == [{'path': str(tmp_path / 'trial.inp'), 'engine': 'orca', 'tasks': ['irc']}]


def test_unavailable_inputs_and_unrelated_tools_have_no_findings(tmp_path):
    assert _inspect('submit_compute_job', {'input_file': 'missing.inp', 'job_type': 'orca'}, tmp_path) == {}
    assert _inspect('read', {'path': 'trial.inp'}, tmp_path) == {}


def test_native_submission_parses_the_input_once(tmp_path, monkeypatch):
    from cloudra.tools.core import ts_workflow_guard

    source = tmp_path / 'trial.inp'
    source.write_text('! HF STO-3G OptTS\n')
    parse = ts_workflow_guard.inspect_input
    calls = []

    def counted(text, *, engine):
        calls.append(engine)
        return parse(text, engine=engine)

    monkeypatch.setattr(ts_workflow_guard, 'inspect_input', counted)
    result = _inspect('submit_compute_job', {'input_file': source.name, 'job_type': 'orca'}, tmp_path)

    assert result['ts_inputs'][0]['tasks'] == ['ts_opt']
    assert calls == ['orca']


def test_document_with_example_input_is_not_a_ts_operation(tmp_path):
    assert _inspect('write', {'path': 'README.md', 'content': 'Example:\n! HF STO-3G OptTS\n'}, tmp_path) == {}
