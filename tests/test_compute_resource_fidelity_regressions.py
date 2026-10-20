"""Native resource/engine declarations survive the real submit/admission boundary."""

import importlib
import json
from types import SimpleNamespace

import pytest

from cloudra.infra.slurm import build_batch_script
from cloudra.services.compute_admission import admit_job

submit = importlib.import_module('cloudra.tools.Chemtool.submit_compute_job')


@pytest.fixture
def submission(tmp_path, monkeypatch):
    """Keep parsing/admission real; replace storage, capacity and executable probes."""
    records = []
    resources = {'cpus': 64, 'memory_mb': 65536, 'max_concurrent': 16}
    node = SimpleNamespace(node_id='fidelity-node', scheduler={'type': 'local'}, connection={})

    class Ledger:
        async def ainit(self):
            return self

    async def insert(_db, **record):
        records.append(record)
        return len(records)

    async def progress(_event):
        pass

    monkeypatch.setattr(submit, 'ComputeDB', Ledger)
    monkeypatch.setattr(submit, 'ainsert_compute_job', insert)
    monkeypatch.setattr('cloudra.runtime_v2.invocation_context.report_tool_progress', progress)
    monkeypatch.setattr('cloudra.services.compute_admission._route_node', lambda _path: (node, ''))
    monkeypatch.setattr('cloudra.services.compute_admission.check_job_type', lambda *_args: (True, ''))
    monkeypatch.setattr('cloudra.services.host_capacity.effective_node_resources', lambda _node: dict(resources))
    monkeypatch.setattr('cloudra.infra.slurm.check_slurm_tools', lambda: (True, ''))
    tool = submit.SubmitComputeJob(subagent=SimpleNamespace(
        working_directory=str(tmp_path), conversation_id='fidelity-regression',
    ))
    return tool, records, resources, node


def gaussian(declarations):
    return declarations + '\n# FutureMethod/FutureBasis FutureTask\n\nHe\n\n0 1\nHe 0 0 0\n\n'


@pytest.mark.asyncio
@pytest.mark.parametrize('declarations', [
    '! HF STO-3G # native comment # PAL8\n%maxcore 1000\n',
    '! HF STO-3G\n%pal # native comment # nprocs 8 end\n%maxcore 1000\n',
    '! HF STO-3G PAL8\n# native comment # %maxcore 1000\n',
    '! HF STO-3G\n%pal\n# native comment # nprocs 8\nend\n%maxcore 1000\n',
])
async def test_closed_orca_comment_keeps_active_resources(tmp_path, submission, declarations):
    tool, records, _resources, _node = submission
    source = tmp_path / 'native.inp'
    source.write_text(declarations)
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='orca', is_async=True,
    ), None)
    assert result.is_success, result.message
    assert (records[0]['req_cpus'], records[0]['req_memory_mb']) == (8, 8000)
    assert source.read_text() == declarations


@pytest.mark.asyncio
@pytest.mark.parametrize('allocation', [{'cpus': 4}, {'memory_mb': 4000}])
async def test_closed_orca_comment_cannot_hide_underreservation(tmp_path, submission, allocation):
    tool, records, _resources, _node = submission
    (tmp_path / 'native.inp').write_text('! HF # comment # PAL8\n%maxcore 1000\n')
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file='native.inp', job_type='orca', is_async=True, **allocation,
    ), None)
    assert not result.is_success
    assert 'under-provisioned' in result.message
    assert records == []


@pytest.mark.asyncio
async def test_closed_orca_comment_still_enforces_node_capacity(tmp_path, submission):
    tool, records, resources, _node = submission
    resources.update(cpus=4, memory_mb=5000)
    (tmp_path / 'native.inp').write_text('! HF # comment # PAL8\n%maxcore 1000\n')
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file='native.inp', job_type='orca', is_async=True,
    ), None)
    assert not result.is_success
    assert 'capacity' in result.message
    assert records == []


@pytest.mark.asyncio
@pytest.mark.parametrize('quoted', ['"# PAL64 #"', r'"note \" # PAL64 #"'])
async def test_quoted_orca_comment_marker_does_not_activate_fake_resources(tmp_path, submission, quoted):
    tool, records, _resources, _node = submission
    source = tmp_path / 'native.inp'
    source.write_text(f'! HF STO-3G PAL8 {quoted} # comment #\n%maxcore 1000\n')
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='orca', is_async=True,
    ), None)
    assert result.is_success, result.message
    assert (records[0]['req_cpus'], records[0]['req_memory_mb']) == (8, 8000)


@pytest.mark.asyncio
@pytest.mark.parametrize(('cpu_list', 'count'), [('0-3,8,10-12', 8), ('4', 1), ('0, 2-4, 7', 5)])
async def test_gaussian_cpu_list_reservation_reaches_ledger_and_slurm(tmp_path, submission, cpu_list, count):
    tool, records, _resources, node = submission
    node.scheduler = {'type': 'slurm'}
    source = tmp_path / 'native.gjf'
    content = gaussian(f'%CPU={cpu_list}\n%mem=4GB')
    source.write_text(content)
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='gaussian', is_async=True,
    ), None)
    assert result.is_success, result.message
    record = records[0]
    options = json.loads(record['scheduler_options'])
    assert options['cpus'] == record['req_cpus'] == count
    assert options['memory'] == f"{record['req_memory_mb']}M" == '4096M'
    script = build_batch_script(source, 'gaussian', 1, options, calculator_cmd=['mock-calculator'])
    assert f'#SBATCH --cpus-per-task={count}\n' in script
    assert '#SBATCH --mem=4096M\n' in script
    assert source.read_text() == content


@pytest.mark.asyncio
@pytest.mark.parametrize('nproc', ['%nproc=8', '%nprocshared=8'])
async def test_gaussian_matching_cpu_and_nproc_declarations_are_accepted(tmp_path, submission, nproc):
    tool, records, _resources, _node = submission
    (tmp_path / 'native.gjf').write_text(gaussian(f'%CPU=0-3,8-11\n{nproc}'))
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file='native.gjf', job_type='gaussian', is_async=True,
    ), None)
    assert result.is_success, result.message
    assert records[0]['req_cpus'] == 8


@pytest.mark.asyncio
@pytest.mark.parametrize('nproc', ['%nproc=4', '%nprocshared=4'])
async def test_gaussian_cpu_and_nproc_conflict_is_not_hidden_by_large_allocation(tmp_path, submission, nproc):
    tool, records, _resources, _node = submission
    (tmp_path / 'native.gjf').write_text(gaussian(f'%CPU=0-7\n{nproc}'))
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file='native.gjf', job_type='gaussian', cpus=64, is_async=True,
    ), None)
    assert not result.is_success
    assert 'Conflicting resource' in result.message
    assert records == []


@pytest.mark.asyncio
@pytest.mark.parametrize('cpu_list', ['', '0--3', '3-1', '-1', 'one', '1,1', '0-3,2-5', '0-3,', '0.1'])
async def test_invalid_gaussian_cpu_list_fails_before_ledger(tmp_path, submission, cpu_list):
    tool, records, _resources, _node = submission
    (tmp_path / 'native.gjf').write_text(gaussian(f'%CPU={cpu_list}'))
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file='native.gjf', job_type='gaussian', is_async=True,
    ), None)
    assert not result.is_success
    assert '%cpu' in result.message.lower()
    assert records == []


@pytest.mark.asyncio
async def test_gaussian_cpu_list_cannot_exceed_explicit_reservation(tmp_path, submission):
    tool, records, _resources, _node = submission
    (tmp_path / 'native.gjf').write_text(gaussian('%CPU=0-7'))
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file='native.gjf', job_type='gaussian', cpus=4, is_async=True,
    ), None)
    assert not result.is_success
    assert '8 cores' in result.message
    assert records == []


@pytest.mark.asyncio
async def test_gaussian_cpu_list_checks_each_link1_peak(tmp_path, submission):
    tool, records, resources, _node = submission
    resources['cpus'] = 4
    (tmp_path / 'native.gjf').write_text(gaussian('%CPU=0-1') + '--Link1--\n' + gaussian('%CPU=0-7'))
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file='native.gjf', job_type='gaussian', is_async=True,
    ), None)
    assert not result.is_success
    assert 'capacity' in result.message
    assert records == []


@pytest.mark.asyncio
@pytest.mark.parametrize(('filename', 'content', 'engine'), [
    ('misleading.gjf', '# ORCA comment\n! FutureTask FutureMethod FutureBasis\n* xyz 0 1\nHe 0 0 0\n*\n', 'gaussian'),
    ('misleading.inp', gaussian('%CPU=0-1'), 'orca'),
])
async def test_native_content_engine_conflict_fails_for_submit_and_shared_admission(
    tmp_path, submission, filename, content, engine,
):
    tool, records, _resources, _node = submission
    source = tmp_path / filename
    source.write_text(content)
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type=engine, cpus=2, memory_mb=100, is_async=True,
    ), None)
    assert not result.is_success
    assert 'engine' in result.message.lower() and 'job_type' in result.message
    assert records == []
    outcome = admit_job(input_file=str(source), job_type=engine, cpus=2, memory_mb=100)
    assert not outcome.ok
    assert 'engine' in outcome.message.lower() and 'job_type' in outcome.message
    assert source.read_text() == content


@pytest.mark.asyncio
async def test_omitted_job_type_cannot_misroute_orca_to_gaussian(tmp_path, submission):
    tool, records, _resources, _node = submission
    (tmp_path / 'native.inp').write_text('! FutureMethod FutureTask\n* xyz 0 1\nHe 0 0 0\n*\n')
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file='native.inp', is_async=True,
    ), None)
    assert not result.is_success
    assert 'job_type' in result.message
    assert records == []


@pytest.mark.asyncio
@pytest.mark.parametrize(('engine', 'filename', 'content'), [
    ('orca', 'native.gjf', '# comment\n! FutureTask FutureMethod FutureBasis\n* xyz 0 1\nHe 0 0 0\n*\n'),
    ('gaussian', 'native.inp', gaussian('%mem=1MB')),
    ('orca', 'unclassified.inp', '%native_setting FutureOption\n'),
])
async def test_matching_or_unclassified_native_content_is_not_method_whitelisted(
    tmp_path, submission, engine, filename, content,
):
    tool, records, _resources, _node = submission
    source = tmp_path / filename
    source.write_text(content)
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type=engine, is_async=True,
    ), None)
    assert result.is_success, result.message
    assert records[0]['jobtype'] == engine
    assert source.read_text() == content


@pytest.mark.asyncio
@pytest.mark.parametrize('reference', ['@resources.inc', '@"resources.inc"/N ! native comment', "@ 'resources.inc' /n"])
async def test_gaussian_include_resources_reach_ledger_and_slurm(tmp_path, submission, reference):
    tool, records, _resources, node = submission
    node.scheduler = {'type': 'slurm'}
    source = tmp_path / 'native.gjf'
    source.write_text(gaussian(reference))
    included = tmp_path / 'resources.inc'
    included.write_bytes(b'%CPU=0-3,8-11\r\n%mem=8GB\r\n')
    originals = {path: path.read_bytes() for path in (source, included)}
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='gaussian', is_async=True,
    ), None)
    assert result.is_success, result.message
    record = records[0]
    options = json.loads(record['scheduler_options'])
    assert options['cpus'] == record['req_cpus'] == 8
    assert options['memory'] == f"{record['req_memory_mb']}M" == '8192M'
    assert {path: path.read_bytes() for path in originals} == originals


@pytest.mark.asyncio
async def test_nested_gaussian_includes_use_job_workdir_and_preserve_line_boundaries(tmp_path, submission):
    tool, records, _resources, _node = submission
    (tmp_path / 'nested').mkdir()
    source = tmp_path / 'native.gjf'
    source.write_text(gaussian('@nested/outer.inc'))
    outer = tmp_path / 'nested' / 'outer.inc'
    outer.write_text('@inner.inc/N\n%mem=8GB\n')
    inner = tmp_path / 'inner.inc'
    inner.write_text('%CPU=0-7')
    originals = {path: path.read_bytes() for path in (source, outer, inner)}
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='gaussian', is_async=True,
    ), None)
    assert result.is_success, result.message
    assert (records[0]['req_cpus'], records[0]['req_memory_mb']) == (8, 8192)
    assert {path: path.read_bytes() for path in originals} == originals


@pytest.mark.asyncio
@pytest.mark.parametrize('allocation', [{'cpus': 4}, {'memory_mb': 4096}])
async def test_gaussian_include_cannot_hide_explicit_underreservation(tmp_path, submission, allocation):
    tool, records, _resources, _node = submission
    source = tmp_path / 'native.gjf'
    source.write_text(gaussian('@resources.inc'))
    (tmp_path / 'resources.inc').write_text('%CPU=0-7\n%mem=8GB\n')
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='gaussian', is_async=True, **allocation,
    ), None)
    assert not result.is_success
    assert 'under-provisioned' in result.message
    assert records == []


@pytest.mark.asyncio
async def test_gaussian_include_resources_cannot_exceed_node_capacity(tmp_path, submission):
    tool, records, resources, _node = submission
    resources.update(cpus=4, memory_mb=5000)
    source = tmp_path / 'native.gjf'
    source.write_text(gaussian('@resources.inc'))
    (tmp_path / 'resources.inc').write_text('%CPU=0-63\n%mem=64GB\n')
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='gaussian', is_async=True,
    ), None)
    assert not result.is_success
    assert 'capacity' in result.message
    assert records == []


@pytest.mark.asyncio
async def test_gaussian_include_conflicts_remain_errors_with_explicit_allocation(tmp_path, submission):
    tool, records, _resources, _node = submission
    source = tmp_path / 'native.gjf'
    source.write_text(gaussian('@resources.inc\n%nprocshared=4'))
    (tmp_path / 'resources.inc').write_text('%CPU=0-7\n')
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='gaussian', cpus=64, memory_mb=65536, is_async=True,
    ), None)
    assert not result.is_success
    assert 'Conflicting resource' in result.message
    assert records == []


@pytest.mark.asyncio
@pytest.mark.parametrize('link1', [False, True])
async def test_gaussian_trailing_include_respects_link1_resource_order(tmp_path, submission, link1):
    tool, records, _resources, _node = submission
    source = tmp_path / 'native.gjf'
    source.write_text(gaussian('%CPU=0-1\n%mem=1GB') + '@tail.inc/N\n')
    tail = tmp_path / 'tail.inc'
    tail.write_text(('--Link1--\n' if link1 else '') + '%CPU=0-7\n%mem=8GB\n# FutureMethod/FutureBasis Geom=AllCheck\n\n')
    originals = {path: path.read_bytes() for path in (source, tail)}
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='gaussian', is_async=True,
    ), None)
    assert result.is_success, result.message
    assert (records[0]['req_cpus'], records[0]['req_memory_mb']) == ((8, 8192) if link1 else (2, 1024))
    assert {path: path.read_bytes() for path in originals} == originals


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['missing', 'cycle', 'input_cycle', 'invalid_suffix', 'empty', 'directory', 'invalid_resource'])
async def test_invalid_gaussian_include_fails_before_ledger(tmp_path, submission, kind):
    tool, records, _resources, _node = submission
    source = tmp_path / 'native.gjf'
    reference = '@resources.inc'
    included = tmp_path / 'resources.inc'
    if kind == 'cycle':
        included.write_text('@nested.inc\n')
        (tmp_path / 'nested.inc').write_text('@resources.inc\n')
    elif kind == 'input_cycle':
        included.write_text('@native.gjf\n')
    elif kind == 'invalid_suffix':
        included.write_text('%CPU=0-7\n')
        reference += ' unexpected'
    elif kind == 'empty':
        reference = '@'
    elif kind == 'directory':
        included.mkdir()
    elif kind == 'invalid_resource':
        included.write_text('%CPU=invalid\n')
    source.write_text(gaussian(reference))
    original = source.read_bytes()
    result = await tool.tool_call(submit.SubmitComputeJob_input_schema(
        input_file=source.name, job_type='gaussian', cpus=64, memory_mb=65536, is_async=True,
    ), None)
    assert not result.is_success
    assert ('include' in result.message.lower() if kind != 'invalid_resource' else '%cpu' in result.message.lower())
    assert records == []
    assert source.read_bytes() == original
