"""Native dependencies retain their syntax and execution-time ownership."""

import json
import os
from pathlib import Path

import pytest

from cloudra.infra.compute_utils import _orca_file_references
from cloudra.infra.ssh_transport import SshError
from cloudra.runtime.remote_compute import (
    _pull_remote_artifacts,
    _stage_and_submit,
    _stage_native_paths,
    run_remote_compute,
)
from cloudra.services.compute_admission import _read_declared_requirements
from cloudra.services.compute_store import aget_compute_job
from tests.test_compute_transport_paths import DirectoryTransport
from tests.test_remote_compute import FakeTransport, _fast_sleep, _insert_running


@pytest.mark.parametrize('line,path,raw_path', [
    ('  @ ../basis.gbs/N ! note\r\n', '../basis.gbs', '../basis.gbs'),
    ('@"../basis #1.gbs"/n\n', '../basis #1.gbs', '"../basis #1.gbs"'),
    ("@'basis!1.gbs' /N ! note\n", 'basis!1.gbs', "'basis!1.gbs'"),
    ('@basis.gbs ! note\n', 'basis.gbs', 'basis.gbs'),
])
def test_gaussian_include_reference_preserves_native_path_span(line, path, raw_path):
    from cloudra.infra.compute_utils import _gaussian_include_reference

    actual, start, end = _gaussian_include_reference(line)
    assert actual == path
    assert line[start:end] == raw_path


@pytest.mark.parametrize('line', ['# HF/STO-3G\n', '! @not-an-include\n', 'He 0 0 0\n'])
def test_gaussian_include_reference_ignores_ordinary_input(line):
    from cloudra.infra.compute_utils import _gaussian_include_reference

    assert _gaussian_include_reference(line) is None


@pytest.mark.parametrize('line', ['@\n', '@ /N\n', '@"unclosed\n', '@basis.gbs extra\n'])
def test_gaussian_include_reference_rejects_ambiguous_paths(line):
    from cloudra.infra.compute_utils import _gaussian_include_reference

    with pytest.raises(ValueError, match='Gaussian include'):
        _gaussian_include_reference(line)


@pytest.mark.parametrize('statement,keyword', [
    ('%geom # native comment # InHessName "../seed #1.hess" end', 'inhessname'),
    ('%irc # native comment # Hess_Filename "../seed #1.hess" end', 'hess_filename'),
    ('# leading comment # %moinp "../seed #1.hess"', '%moinp'),
    ('%scf # native comment # MOInp "../seed #1.hess" end', 'moinp'),
])
def test_orca_closed_comments_preserve_dependency_spans(tmp_path, statement, keyword):
    local = tmp_path / 'local'
    local.mkdir()
    dependency = tmp_path / 'seed #1.hess'
    dependency.write_bytes(b'MOCK native dependency')
    source = local / 'run.inp'
    original = '! HF STO-3G\r\n' + statement + '\r\n* xyz 0 1\r\nHe 0 0 0\r\n*\r\n'
    source.write_bytes(original.encode())

    references = _orca_file_references(original)
    assert len(references) == 1
    actual_keyword, path, start, end = references[0]
    assert actual_keyword == keyword
    assert path == '../seed #1.hess'
    assert original[start:end] == '"../seed #1.hess"'
    stage = _stage_native_paths(source, local, 7, 'orca')
    manifest = json.loads((local / '.cloudra/remote-7/path-map.json').read_text())
    mapped = manifest['files'][0]['staged_path']
    assert (stage / mapped).read_bytes() == dependency.read_bytes()
    expected = original[:start] + '"' + mapped + '"' + original[end:]
    assert (stage / source.name).read_bytes() == expected.encode()
    assert source.read_bytes() == original.encode()


def test_orca_scf_moinp_and_top_level_stage_the_same_file(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    dependency = tmp_path / 'seed.gbw'
    dependency.write_bytes(b'MOCK orbitals')
    mappings = []
    for number, statement in enumerate(('%moinp "../seed.gbw"', '%scf MOInp "../seed.gbw" end'), 1):
        source = local / f'run{number}.inp'
        source.write_text('! HF STO-3G MOREAD\n' + statement + '\n* xyz 0 1\nHe 0 0 0\n*\n')
        stage = _stage_native_paths(source, local, number, 'orca')
        manifest = json.loads((local / f'.cloudra/remote-{number}/path-map.json').read_text())
        item = manifest['files'][0]
        mappings.append((item['local_path'], item['role'], item['source_sha256']))
        assert (stage / item['staged_path']).read_bytes() == dependency.read_bytes()
    assert mappings[0] == mappings[1]


@pytest.mark.parametrize('noecho', ['', '/N'])
def test_gaussian_external_include_stages_exact_leaf_bytes(tmp_path, noecho):
    local = tmp_path / 'local'
    local.mkdir()
    basis = tmp_path / 'basis.gbs'
    body = b'He 0\r\nSTO-3G\r\n****\r\n! literal scientific text\r\n'
    basis.write_bytes(body)
    source = local / 'run.gjf'
    original = ('# HF/Gen\r\n\r\nHe\r\n\r\n0 1\r\nHe 0 0 0\r\n\r\n'
                f'@../basis.gbs{noecho}\r\n\r\n').encode()
    source.write_bytes(original)
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 7, source, local, '/remote/job', 'gaussian', {}, {})
    manifest = json.loads((local / '.cloudra/remote-7/path-map.json').read_text())
    assert len(manifest['files']) == 1
    item = manifest['files'][0]
    assert item['local_path'] == str(basis)
    assert item['role'] == 'dependency'
    assert (remote / item['staged_path']).read_bytes() == body
    assert (remote / source.name).read_bytes() == original.replace(b'../basis.gbs', item['staged_path'].encode())
    assert source.read_bytes() == original
    assert basis.read_bytes() == body


def test_gaussian_nested_includes_relocate_only_paths_and_keep_receipts(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    leaf = tmp_path / 'leaf.gbs'
    leaf.write_bytes(b'He 0\r\nSTO-3G\r\n****\r\n')
    include = tmp_path / 'basis.inc'
    body = b'! native include comment\r\n@../leaf.gbs/N\r\n'
    include.write_bytes(body)
    source = local / 'run.gjf'
    source.write_text('# HF/Gen\n\nHe\n\n0 1\nHe 0 0 0\n\n@../basis.inc\n\n')
    stage = _stage_native_paths(source, local, 8, 'gaussian')
    receipt = local / '.cloudra/remote-8'
    manifest = json.loads((receipt / 'path-map.json').read_text())
    by_local = {item['local_path']: item for item in manifest['files']}
    assert set(by_local) == {str(include), str(leaf)}
    nested = by_local[str(include)]['staged_path']
    mapped_leaf = by_local[str(leaf)]['staged_path']
    assert (stage / nested).read_bytes() == body.replace(b'../leaf.gbs', mapped_leaf.encode())
    assert (stage / mapped_leaf).read_bytes() == leaf.read_bytes()
    assert (receipt / 'original-files' / nested).read_bytes() == body
    assert include.read_bytes() == body


@pytest.mark.parametrize('kind', ['missing', 'cycle', 'input', 'runtime', 'calculator', 'output'])
@pytest.mark.parametrize('scheduler', ['ssh_local', 'ssh_slurm'])
def test_gaussian_unsafe_include_fails_before_transport(tmp_path, kind, scheduler):
    source = tmp_path / 'run.gjf'
    dependency = tmp_path / 'basis.gbs'
    prefix = ''
    if kind == 'missing':
        dependency = tmp_path / 'absent.gbs'
    elif kind == 'cycle':
        dependency.write_text('@basis.gbs\n')
    elif kind == 'input':
        dependency = source
    elif kind == 'runtime':
        dependency = tmp_path / '.cloudra/basis.gbs'
        dependency.parent.mkdir()
        dependency.write_text('He 0\nSTO-3G\n****\n')
    elif kind == 'calculator':
        dependency = tmp_path / 'calculator.sh'
        dependency.write_text('He 0\nSTO-3G\n****\n')
    else:
        dependency.write_text('He 0\nSTO-3G\n****\n')
        prefix = '%chk=basis.gbs\n'
    source.write_text(prefix + '# HF/Gen\n\nHe\n\n0 1\nHe 0 0 0\n\n@' + str(dependency) + '\n\n')
    transport = FakeTransport()
    with pytest.raises(ValueError, match='missing|cycle|input|runtime|collision|collid|output'):
        _stage_and_submit(transport, scheduler, 7, source, tmp_path, '/remote/job', 'gaussian', {}, {})
    assert not transport.pushes
    assert not transport.commands


def test_gaussian_later_link_can_read_prior_link_output(tmp_path):
    source = tmp_path / 'chain.gjf'
    original = ('%chk=first.chk\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n'
                '--Link1--\n%oldchk=first.chk\n%chk=second.chk\n# HF/STO-3G geom=allcheck guess=read\n\n')
    source.write_text(original)
    stage = _stage_native_paths(source, tmp_path, 9, 'gaussian')
    assert (stage / source.name).read_text() == original
    assert not (tmp_path / 'first.chk').exists()
    manifest = json.loads((tmp_path / '.cloudra/remote-9/path-map.json').read_text())
    first = next(item for item in manifest['files'] if Path(item['local_path']).name == 'first.chk')
    assert first['role'] == 'inout'


@pytest.mark.parametrize('text', [
    '%oldchk=first.chk\n%chk=first.chk\n# HF/STO-3G guess=read\n\n',
    '%oldchk=first.chk\n# HF/STO-3G guess=read\n\n--Link1--\n%chk=first.chk\n# HF/STO-3G\n\n',
])
def test_gaussian_current_or_future_output_does_not_supply_missing_oldchk(tmp_path, text):
    source = tmp_path / 'chain.gjf'
    source.write_text(text)
    with pytest.raises(ValueError, match='dependency.*missing'):
        _stage_native_paths(source, tmp_path, 9, 'gaussian')


def test_gaussian_replaced_chk_declaration_does_not_supply_later_oldchk(tmp_path):
    source = tmp_path / 'chain.gjf'
    source.write_text('%chk=unused.chk\n%chk=actual.chk\n# HF/STO-3G\n\n'
                      '--Link1--\n%oldchk=unused.chk\n# HF/STO-3G guess=read\n\n')
    with pytest.raises(ValueError, match='dependency.*missing'):
        _stage_native_paths(source, tmp_path, 9, 'gaussian')


def test_orca_later_job_reads_explicit_prior_base_output(tmp_path):
    source = tmp_path / 'chain.inp'
    text = ('! HF STO-3G\n%base "first"\n* xyz 0 1\nHe 0 0 0\n*\n'
            '$new_job\n! HF STO-3G MOREAD\n%base "second"\n%moinp "first.gbw"\n* xyz 0 1\nHe 0 0 0\n*\n')
    source.write_text(text)
    stage = _stage_native_paths(source, tmp_path, 10, 'orca')
    assert (stage / source.name).read_text() == text


def test_orca_future_base_output_does_not_supply_missing_dependency(tmp_path):
    source = tmp_path / 'chain.inp'
    source.write_text('! HF STO-3G MOREAD\n%moinp "later.gbw"\n$new_job\n%base "later"\n! HF STO-3G\n')
    with pytest.raises(ValueError, match='dependency.*missing'):
        _stage_native_paths(source, tmp_path, 10, 'orca')


@pytest.mark.asyncio
async def test_remote_symlink_input_keeps_submitted_directory_for_includes(tmp_path):
    alias = tmp_path / 'alias'
    actual = tmp_path / 'actual'
    alias.mkdir()
    actual.mkdir()
    (alias / 'resources.inc').write_text('%nprocshared=1\n%mem=1GB\n')
    (actual / 'resources.inc').write_text('%nprocshared=8\n%mem=8GB\n')
    native = actual / 'native.gjf'
    original = b'@resources.inc\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n'
    native.write_bytes(original)
    source = alias / 'native.gjf'
    source.symlink_to(native)
    db, job_id, _ = await _insert_running(alias, jobtype='gaussian')
    async with db.aconnect() as con:
        await con.execute('UPDATE compute_jobs SET path=? WHERE id=?', (str(source), job_id))
        await con.commit()

    def finish(remote):
        (remote / 'native.log').write_text('Normal termination of Gaussian 16\n')

    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote, finish=finish)
    assert _read_declared_requirements('gaussian', str(source)) == (1, 1024)
    assert await run_remote_compute(job_id, db.path, transport=transport, sleep=_fast_sleep) == 0
    assert (remote / 'resources.inc').read_bytes() == (alias / 'resources.inc').read_bytes()
    assert (alias / f'.cloudra/remote-{job_id}/path-map.json').is_file()
    assert not (actual / f'.cloudra/remote-{job_id}').exists()
    assert (await aget_compute_job(db, job_id))['path'] == str(source)
    assert source.is_symlink()
    assert native.read_bytes() == original


@pytest.mark.parametrize('protected_kind', ['input', 'oldchk', 'include'])
def test_native_output_hardlink_to_input_or_dependency_fails_before_submit(tmp_path, protected_kind):
    source = tmp_path / 'run.gjf'
    dependency = tmp_path / 'seed.chk'
    dependency.write_bytes(b'MOCK checkpoint')
    prefix = '%oldchk=seed.chk\n' if protected_kind == 'oldchk' else ''
    suffix = '@basis.gbs\n' if protected_kind == 'include' else ''
    basis = tmp_path / 'basis.gbs'
    basis.write_bytes(b'He 0\nSTO-3G\n****\n')
    original = (prefix + '%chk=restart.chk\n# HF/Gen\n\nHe\n\n0 1\nHe 0 0 0\n\n' + suffix).encode()
    source.write_bytes(original)
    protected = {'input': source, 'oldchk': dependency, 'include': basis}[protected_kind]
    before = protected.read_bytes()
    os.link(protected, tmp_path / 'restart.chk')
    transport = FakeTransport()
    with pytest.raises(ValueError, match='alias|input|collid|hard.link'):
        _stage_and_submit(transport, 'ssh_local', 7, source, tmp_path, '/remote/job', 'gaussian', {}, {})
    assert not transport.pushes
    assert protected.read_bytes() == before
    assert source.read_bytes() == original


def test_orca_base_sidecar_cannot_alias_submitted_input_inode(tmp_path):
    source = tmp_path / 'run.inp'
    original = b'! HF STO-3G\n%base "restart"\n* xyz 0 1\nHe 0 0 0\n*\n'
    source.write_bytes(original)
    os.link(source, tmp_path / 'restart.gbw')
    with pytest.raises(ValueError, match='alias|input|collid|hard.link'):
        _stage_native_paths(source, tmp_path, 7, 'orca')
    assert source.read_bytes() == original


@pytest.mark.parametrize('protected_kind', ['input', 'include', 'receipt', 'results'])
def test_remote_pull_rejects_hardlink_aliases_of_protected_sources(tmp_path, protected_kind):
    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'run.gjf'
    original = b'%chk=restart.chk\n# HF/Gen\n\nHe\n\n0 1\nHe 0 0 0\n\n@basis.gbs\n'
    source.write_bytes(original)
    basis = local / 'basis.gbs'
    basis.write_bytes(b'He 0\nSTO-3G\n****\n')
    expected = basis.read_bytes() if protected_kind == 'include' else original
    target = local / 'restart.chk'
    target.write_bytes(expected)
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 7, source, local, '/remote/job', 'gaussian', {}, {})
    receipt = local / '.cloudra/remote-7'
    protected = {'input': source, 'include': basis, 'receipt': receipt / 'original/run.gjf',
                 'results': source}[protected_kind]
    if protected_kind == 'results':
        results = receipt / 'results'
        results.mkdir()
        os.link(source, results / 'restart.chk')
    else:
        target.unlink()
        os.link(protected, target)
    (remote / 'restart.chk').write_bytes(b'MOCK generated checkpoint')
    with pytest.raises(SshError, match='hard.link|alias|protected'):
        _pull_remote_artifacts(transport, '/remote/job', local, source, 7, 'gaussian')
    assert protected.read_bytes() == expected
    assert source.read_bytes() == original


@pytest.mark.parametrize('link_kind', ['symlink', 'hardlink'])
@pytest.mark.parametrize('relative', ['stage/run.gjf', 'original/run.gjf',
                                      'original-files/seed.chk', 'results/run.gjf'])
def test_staging_rejects_receipt_file_aliases_before_any_write(tmp_path, relative, link_kind):
    source = tmp_path / 'run.gjf'
    original = ('%oldchk=seed.chk\n%chk=' + str(tmp_path.parent / 'external.chk')
                + '\n# HF/STO-3G guess=read\n\nHe\n\n0 1\nHe 0 0 0\n\n').encode()
    source.write_bytes(original)
    (tmp_path / 'seed.chk').write_bytes(b'MOCK checkpoint')
    entry = tmp_path / '.cloudra/remote-7' / relative
    entry.parent.mkdir(parents=True)
    if link_kind == 'symlink':
        entry.symlink_to(source)
    else:
        os.link(source, entry)
    transport = FakeTransport()
    with pytest.raises(ValueError, match='receipt|symlink|hard.link|alias'):
        _stage_and_submit(transport, 'ssh_local', 7, source, tmp_path, '/remote/job', 'gaussian', {}, {})
    assert not transport.pushes
    assert source.read_bytes() == original


@pytest.mark.parametrize('relative', ['.cloudra', '.cloudra/remote-7', '.cloudra/remote-7/stage',
                                      '.cloudra/remote-7/original', '.cloudra/remote-7/original-files',
                                      '.cloudra/remote-7/results'])
def test_staging_rejects_receipt_directory_symlinks_before_any_write(tmp_path, relative):
    source = tmp_path / 'run.gjf'
    original = b'# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n'
    source.write_bytes(original)
    destination = tmp_path / 'receipt-target'
    destination.mkdir()
    entry = tmp_path / relative
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match='receipt|symlink|alias'):
        _stage_native_paths(source, tmp_path, 7, 'gaussian')
    assert not list(destination.iterdir())
    assert source.read_bytes() == original


@pytest.mark.parametrize('position', ['root', 'directory', 'file'])
def test_remote_pull_rejects_receipt_symlinks_before_transport(tmp_path, position):
    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'run.gjf'
    original = b'%chk=restart.chk\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n'
    source.write_bytes(original)
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 7, source, local, '/remote/job', 'gaussian', {}, {})
    results = local / '.cloudra/remote-7/results'
    if position == 'root':
        results.symlink_to(local, target_is_directory=True)
        (remote / source.name).write_bytes(b'MOCK execution input')
    elif position == 'directory':
        results.mkdir()
        (results / 'nested').symlink_to(local, target_is_directory=True)
        (remote / 'nested').mkdir()
        (remote / 'nested' / source.name).write_bytes(b'MOCK nested artifact')
    else:
        results.mkdir()
        (results / 'restart.chk').symlink_to(source)
        (remote / 'restart.chk').write_bytes(b'MOCK checkpoint')
    with pytest.raises(SshError, match='receipt|symlink|alias'):
        _pull_remote_artifacts(transport, '/remote/job', local, source, 7, 'gaussian')
    assert transport.pulls == 0
    assert source.read_bytes() == original


@pytest.mark.parametrize('kind,prefix', [('ssh_local', '.cloudra-run-'), ('ssh_slurm', '.cloudra-slurm-')])
@pytest.mark.parametrize('link_kind', ['symlink', 'hardlink'])
def test_runtime_script_alias_does_not_modify_native_dependency(tmp_path, kind, prefix, link_kind):
    source = tmp_path / 'run.gjf'
    original = b'%oldchk=seed.chk\n%chk=next.chk\n# HF/STO-3G guess=read\n\nHe\n\n0 1\nHe 0 0 0\n\n'
    source.write_bytes(original)
    dependency = tmp_path / 'seed.chk'
    dependency.write_bytes(b'MOCK original checkpoint')
    script = tmp_path / f'{prefix}7.sh'
    if link_kind == 'symlink':
        script.symlink_to(dependency)
    else:
        os.link(dependency, script)
    _stage_and_submit(FakeTransport(), kind, 7, source, tmp_path, '/remote/job', 'gaussian', {}, {})
    assert dependency.read_bytes() == b'MOCK original checkpoint'
    assert source.read_bytes() == original
    assert script.read_bytes().startswith(b'#!/bin/bash')
    assert not script.samefile(dependency)


@pytest.mark.parametrize('kind,prefix', [('ssh_local', '.cloudra-run-'), ('ssh_slurm', '.cloudra-slurm-')])
@pytest.mark.parametrize('symlink_input', [False, True])
def test_runtime_script_cannot_replace_submitted_input(tmp_path, kind, prefix, symlink_input):
    script = tmp_path / f'{prefix}7.sh'
    original = b'# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n'
    script.write_bytes(original)
    source = tmp_path / 'run.gjf' if symlink_input else script
    if symlink_input:
        source.symlink_to(script)
    transport = FakeTransport()
    with pytest.raises(ValueError, match='script|input|collid|alias'):
        _stage_and_submit(transport, kind, 7, source, tmp_path, '/remote/job', 'gaussian', {}, {})
    assert source.read_bytes() == original
    assert script.read_bytes() == original
    assert not transport.pushes


@pytest.mark.parametrize('dependency_kind', ['oldchk', 'include'])
def test_native_dependency_at_runtime_script_name_is_preserved_on_rejection(tmp_path, dependency_kind):
    script = tmp_path / '.cloudra-run-7.sh'
    before = b'MOCK checkpoint' if dependency_kind == 'oldchk' else b'He 0\nSTO-3G\n****\n'
    script.write_bytes(before)
    source = tmp_path / 'run.gjf'
    prefix = '%oldchk=.cloudra-run-7.sh\n' if dependency_kind == 'oldchk' else ''
    suffix = '@.cloudra-run-7.sh\n' if dependency_kind == 'include' else ''
    original = (prefix + '%chk=next.chk\n# HF/Gen\n\nHe\n\n0 1\nHe 0 0 0\n\n' + suffix).encode()
    source.write_bytes(original)
    transport = FakeTransport()
    with pytest.raises(ValueError, match='runtime|collid|script'):
        _stage_and_submit(transport, 'ssh_local', 7, source, tmp_path, '/remote/job', 'gaussian', {}, {})
    assert script.read_bytes() == before
    assert source.read_bytes() == original
    assert not transport.pushes
