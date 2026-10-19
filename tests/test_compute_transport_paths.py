"""File transport regressions; all engine and SSH boundaries are local substitutes."""

import fnmatch
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cloudra.infra.compute_utils import _default_calculator_path, resolve_log_path
from cloudra.runtime.remote_compute import _stage_and_submit, run_remote_compute
from cloudra.services.compute_store import aget_compute_job
from tests.test_remote_compute import FakeTransport, _fast_sleep, _insert_running


def test_gaussian_native_log_precedes_remote_runner_capture(tmp_path):
    source = tmp_path / 'he.gjf'
    source.write_text('# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n')
    native = source.with_suffix('.log')
    native.write_text('Normal termination of Gaussian 16\n')
    capture = tmp_path / '.cloudra' / 'calc-7.out.log'
    capture.parent.mkdir()
    capture.write_text('[calculator] isolated GAUSS_SCRDIR=/remote/scratch\n')
    assert resolve_log_path(str(source), 'gaussian', 7) == str(native)


@pytest.mark.parametrize('exit_status', [0, 23])
def test_orca_space_basename_returns_sidecars_even_after_engine_failure(tmp_path, monkeypatch, exit_status):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    binary = bindir / 'orca'
    binary.write_text(
        '#!/bin/bash\n'
        'stem="${1%.*}"\n'
        'printf "substitute hessian\\n" > "$stem.hess"\n'
        'mkdir "$stem.property"\n'
        'printf "substitute property\\n" > "$stem.property/data"\n'
        f'exit {exit_status}\n'
    )
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', str(bindir) + os.pathsep + os.environ['PATH'])
    source = tmp_path / 'my frequency.inp'
    original = '! HF STO-3G Freq\n* xyz 0 1\nHe 0 0 0\n*\n'
    source.write_text(original)
    result = subprocess.run(['bash', _default_calculator_path(), str(source), 'orca'], capture_output=True, text=True)
    assert result.returncode == exit_status, result.stderr
    assert source.with_suffix('.hess').read_text() == 'substitute hessian\n'
    assert (tmp_path / 'my frequency.property/data').read_text() == 'substitute property\n'
    assert source.read_text() == original
    assert 'artifact mapped' in result.stderr
    assert not list(tmp_path.glob('.cloudra_orasafe_*'))


class DirectoryTransport(FakeTransport):
    """Copy bytes across separate local roots, with rsync's exclude/merge behavior."""

    def __init__(self, remote, *, finish=None):
        super().__init__(poll_tokens=['EXIT:0'])
        self.remote = remote
        self.finish = finish

    def push_dir(self, local_dir, remote_dir, *, excludes=(), **kwargs):
        super().push_dir(local_dir, remote_dir, excludes=excludes, **kwargs)
        excluded = tuple(pattern.rstrip('/') for pattern in excludes)
        shutil.copytree(local_dir, self.remote, dirs_exist_ok=True,
            ignore=lambda _directory, names: [name for name in names if any(fnmatch.fnmatch(name, pattern) for pattern in excluded)])

    def push_files(self, local_paths, remote_dir, **kwargs):
        super().push_files(local_paths, remote_dir, **kwargs)
        self.remote.mkdir(exist_ok=True, parents=True)
        for source in local_paths:
            shutil.copy2(source, self.remote / Path(source).name)

    def pull_dir(self, remote_dir, local_dir, **_kwargs):
        self.pulls += 1
        if self.finish:
            self.finish(self.remote)
        shutil.copytree(self.remote, local_dir, dirs_exist_ok=True)


def test_gaussian_staging_relocates_default_chk_without_changing_original_input(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'he.gjf'
    checkpoint = source.with_suffix('.chk')
    original = f'%chk={checkpoint}\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n'
    source.write_text(original)
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 7, source, local, '/remote/jobs/cloudra-7', 'gaussian', {}, {})
    staged = (remote / source.name).read_text()
    chk_value = next(line.split('=', 1)[1] for line in staged.splitlines() if line.startswith('%chk='))
    assert not Path(chk_value).is_absolute()
    assert (remote / chk_value).parent.is_dir()
    assert staged.replace(chk_value, str(checkpoint)) == original
    assert source.read_text() == original
    manifest = json.loads((local / '.cloudra/remote-7/path-map.json').read_text())
    assert any(item['local_path'] == str(checkpoint) and item['staged_path'] == chk_value for item in manifest['files'])


@pytest.mark.asyncio
async def test_gaussian_external_checkpoint_dependency_and_output_roundtrip_preserve_inputs(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    db, job_id, source = await _insert_running(local, jobtype='gaussian')
    dependency = tmp_path / 'previous' / 'read.chk'
    dependency.parent.mkdir()
    dependency.write_bytes(b'original checkpoint dependency')
    checkpoint = tmp_path / 'results' / 'he.chk'
    original = f'%oldchk={dependency}\n%chk={checkpoint}\n# HF/STO-3G guess=read\n\nHe\n\n0 1\nHe 0 0 0\n\n'
    source.write_text(original)

    def finish(remote):
        staged = (remote / source.name).read_text()
        directives = dict(line[1:].split('=', 1) for line in staged.splitlines() if line.startswith('%'))
        assert (remote / directives['oldchk']).read_bytes() == dependency.read_bytes()
        target = remote / directives['chk']
        assert not Path(directives['chk']).is_absolute()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'generated checkpoint')
        (remote / source.with_suffix('.log').name).write_text('Normal termination of Gaussian 16\n')
        (remote / '.cloudra').mkdir(exist_ok=True)
        (remote / '.cloudra' / f'calc-{job_id}.out.log').write_text('[calculator] isolated scratch\n')

    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote, finish=finish)
    assert await run_remote_compute(job_id, db.path, transport=transport, sleep=_fast_sleep) == 0
    assert (await aget_compute_job(db, job_id))['state'] == 'done'
    assert source.read_text() == original
    assert dependency.read_bytes() == b'original checkpoint dependency'
    assert checkpoint.read_bytes() == b'generated checkpoint'
    assert (local / f'.cloudra/remote-{job_id}/results' / source.name).read_text() != original


def test_orca_staging_copies_explicit_hessian_and_xyzfile_paths(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    hessian = tmp_path / 'frequency.hess'
    hessian.write_bytes(b'explicit Hessian')
    geometry = tmp_path / 'geometry.xyz'
    geometry.write_text('1\n\nHe 0 0 0\n')
    source = local / 'irc.inp'
    original = f'! HF STO-3G IRC\n%irc InitHess read Hess_Filename "{hessian}" end\n* xyzfile 0 1 "{geometry}"\n'
    source.write_text(original)
    remote = tmp_path / 'remote'
    _stage_and_submit(DirectoryTransport(remote), 'ssh_slurm', 8, source, local, '/remote/job', 'orca', {}, {})
    staged = (remote / source.name).read_text()
    assert str(hessian) not in staged
    assert str(geometry) not in staged
    assert source.read_text() == original
    manifest = json.loads((local / '.cloudra/remote-8/path-map.json').read_text())
    for item in manifest['files']:
        assert (remote / item['staged_path']).read_bytes() == Path(item['local_path']).read_bytes()


def test_orca_space_basename_stages_existing_same_stem_restart_sidecar(tmp_path, monkeypatch):
    binary = tmp_path / 'orca'
    binary.write_text(
        '#!/bin/bash\n'
        'stem="${1%.*}"\n'
        'test "$(cat "$stem.gbw")" = "previous orbitals" || exit 31\n'
        'printf "updated orbitals\\n" > "$stem.gbw"\n'
    )
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ['PATH'])
    source = tmp_path / 'my restart.inp'
    source.write_text('! HF STO-3G\n* xyz 0 1\nHe 0 0 0\n*\n')
    old_sidecar = source.with_suffix('.gbw')
    old_sidecar.write_text('previous orbitals\n')
    completed = subprocess.run(['bash', _default_calculator_path(), str(source), 'orca'], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert old_sidecar.read_text() == 'updated orbitals\n'
    backups = list((tmp_path / '.cloudra').glob('orca-name-map-*/my restart.gbw'))
    assert len(backups) == 1
    assert backups[0].read_text() == 'previous orbitals\n'


def test_remote_artifact_cannot_overwrite_file_through_local_symlink(tmp_path):
    from cloudra.infra.ssh_transport import SshError
    from cloudra.runtime.remote_compute import _pull_remote_artifacts

    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'he.gjf'
    source.write_text('original input')
    external = tmp_path / 'unrelated.txt'
    external.write_text('must survive')
    (local / 'result.chk').symlink_to(external)
    remote = tmp_path / 'remote'
    remote.mkdir()
    (remote / 'result.chk').write_text('new checkpoint')
    with pytest.raises(SshError, match='symlink'):
        _pull_remote_artifacts(DirectoryTransport(remote), '/remote/job', local, source, 5)
    assert external.read_text() == 'must survive'
    assert (local / '.cloudra/remote-5/results/result.chk').read_text() == 'new checkpoint'


def test_gaussian_split_scratch_and_explicit_fchk_return_after_reattach(tmp_path):
    from cloudra.runtime.remote_compute import _pull_remote_artifacts

    local = tmp_path / 'local'
    local.mkdir()
    output = tmp_path / 'outputs' / 'he.fchk'
    scratch = tmp_path / 'scratch'
    source = local / 'he.gjf'
    original = f'%rwf={scratch}/,4GB,{tmp_path}/extra.rwf,-1\n%fchk={output}\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n'
    source.write_text(original)
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 9, source, local, '/remote/job', 'gaussian', {}, {})
    staged = (remote / source.name).read_text()
    directives = dict(line[1:].split('=', 1) for line in staged.splitlines() if line.startswith('%'))
    parts = directives['rwf'].split(',')
    assert parts[1::2] == ['4GB', '-1']
    assert not Path(parts[0]).is_absolute()
    (remote / parts[0] / 'Gau-123.rwf').write_bytes(b'scratch artifact')
    (remote / parts[2]).write_bytes(b'second scratch artifact')
    (remote / directives['fchk']).write_bytes(b'formatted checkpoint')
    # Reload only the durable receipt, as after a scheduler restart.
    _pull_remote_artifacts(DirectoryTransport(remote), '/remote/job', local, source, 9)
    assert source.read_text() == original
    assert (scratch / 'Gau-123.rwf').read_bytes() == b'scratch artifact'
    assert (tmp_path / 'extra.rwf').read_bytes() == b'second scratch artifact'
    assert output.read_bytes() == b'formatted checkpoint'


def test_missing_native_dependency_fails_before_remote_submit(tmp_path):
    source = tmp_path / 'irc.inp'
    source.write_text('! HF STO-3G IRC\n%irc Hess_Filename "../missing.hess" end\n* xyz 0 1\nHe 0 0 0\n*\n')
    transport = FakeTransport()
    with pytest.raises(ValueError, match='dependency.*missing'):
        _stage_and_submit(transport, 'ssh_local', 1, source, tmp_path, '/remote/job', 'orca', {}, {})
    assert not transport.pushes
    assert not any('nohup' in command for command in transport.commands)


@pytest.mark.parametrize('through_alias', [False, True])
def test_native_output_cannot_target_runtime_receipt_or_its_symlink_alias(tmp_path, through_alias):
    runtime = tmp_path / '.cloudra'
    runtime.mkdir()
    destination = runtime / 'state.chk'
    if through_alias:
        alias = tmp_path / 'receipt-alias'
        alias.symlink_to(runtime, target_is_directory=True)
        destination = alias / 'state.chk'
    source = tmp_path / 'he.gjf'
    source.write_text(f'%chk={destination}\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n')
    transport = FakeTransport()
    with pytest.raises(ValueError, match='runtime receipt'):
        _stage_and_submit(transport, 'ssh_local', 2, source, tmp_path, '/remote/job', 'gaussian', {}, {})
    assert not transport.pushes


@pytest.mark.parametrize('remote_changes', [False, True])
def test_remote_return_preserves_concurrent_local_neighbor_edits(tmp_path, remote_changes):
    from cloudra.infra.ssh_transport import SshError
    from cloudra.runtime.remote_compute import _pull_remote_artifacts

    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'he.gjf'
    source.write_text('# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n')
    neighbor = local / 'notes.txt'
    neighbor.write_text('submitted notes')
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 4, source, local, '/remote/job', 'gaussian', {}, {})
    neighbor.write_text('new local notes')
    if remote_changes:
        (remote / neighbor.name).write_text('new remote notes')
        with pytest.raises(SshError, match='conflict'):
            _pull_remote_artifacts(transport, '/remote/job', local, source, 4)
    else:
        _pull_remote_artifacts(transport, '/remote/job', local, source, 4)
    assert neighbor.read_text() == 'new local notes'
    assert (local / '.cloudra/remote-4/results' / neighbor.name).is_file()


def test_remote_return_does_not_replace_new_external_checkpoint_created_during_job(tmp_path):
    from cloudra.infra.ssh_transport import SshError
    from cloudra.runtime.remote_compute import _pull_remote_artifacts

    local = tmp_path / 'local'
    local.mkdir()
    checkpoint = tmp_path / 'external.chk'
    source = local / 'he.gjf'
    source.write_text(f'%chk={checkpoint}\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n')
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 3, source, local, '/remote/job', 'gaussian', {}, {})
    staged_checkpoint = next(line.partition('=')[2] for line in (remote / source.name).read_text().splitlines() if line.startswith('%chk='))
    (remote / staged_checkpoint).write_bytes(b'remote checkpoint')
    checkpoint.write_bytes(b'new local checkpoint')
    with pytest.raises(SshError, match='conflict'):
        _pull_remote_artifacts(transport, '/remote/job', local, source, 3)
    assert checkpoint.read_bytes() == b'new local checkpoint'


def test_orca_transport_preserves_unterminated_nonfile_native_option(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'he.inp'
    original = '! HF STO-3G\n%scf UserOption "unclosed\nend\n* xyz 0 1\nHe 0 0 0\n*\n'
    source.write_text(original)
    remote = tmp_path / 'remote'
    _stage_and_submit(DirectoryTransport(remote), 'ssh_local', 1, source, local,
        '/remote/job', 'orca', {}, {})
    assert (remote / source.name).read_text() == original
    assert source.read_text() == original


def test_orca_transport_rejects_unterminated_declared_file_path(tmp_path):
    source = tmp_path / 'irc.inp'
    source.write_text('! HF STO-3G IRC\n%irc Hess_Filename "unclosed\nend\n* xyz 0 1\nHe 0 0 0\n*\n')
    transport = FakeTransport()
    with pytest.raises(ValueError, match='unterminated.*file path'):
        _stage_and_submit(transport, 'ssh_local', 1, source, tmp_path, '/remote/job', 'orca', {}, {})
    assert not transport.pushes


def test_remote_artifact_cannot_follow_local_parent_symlink(tmp_path):
    from cloudra.infra.ssh_transport import SshError
    from cloudra.runtime.remote_compute import _pull_remote_artifacts

    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'he.gjf'
    source.write_text('original input')
    external = tmp_path / 'external'
    external.mkdir()
    artifact = external / 'checkpoint.chk'
    artifact.write_text('must survive')
    (local / 'output').symlink_to(external, target_is_directory=True)
    remote = tmp_path / 'remote'
    (remote / 'output').mkdir(parents=True)
    (remote / 'output/checkpoint.chk').write_text('new remote result')
    with pytest.raises(SshError, match='symlink'):
        _pull_remote_artifacts(DirectoryTransport(remote), '/remote/job', local, source, 6)
    assert artifact.read_text() == 'must survive'


@pytest.mark.parametrize('literal', ['Hess_Filename', 'InHessName', '%moinp', '%pointcharges', '%base', 'xyzfile'])
def test_orca_quoted_solver_string_is_never_a_file_directive(tmp_path, literal):
    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'he.inp'
    original = f'! ExtOpt\n%method Ext_Params "{literal}" end\n* xyz 0 1\nHe 0 0 0\n*\n'
    source.write_text(original)
    remote = tmp_path / 'remote'
    _stage_and_submit(DirectoryTransport(remote), 'ssh_local', 1, source, local, '/remote/job', 'orca', {}, {})
    assert (remote / source.name).read_text() == original


def test_orca_filename_word_in_unrelated_block_is_preserved(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'he.inp'
    original = '! HF STO-3G\n%method UserOption Hess_Filename end\n* xyz 0 1\nHe 0 0 0\n*\n'
    source.write_text(original)
    remote = tmp_path / 'remote'
    _stage_and_submit(DirectoryTransport(remote), 'ssh_local', 1, source, local, '/remote/job', 'orca', {}, {})
    assert (remote / source.name).read_text() == original


def test_orca_external_base_prefix_stages_existing_restart_sidecars(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    prefix = tmp_path / 'external' / 'restart'
    prefix.parent.mkdir()
    prefix.with_suffix('.gbw').write_bytes(b'previous orbitals')
    source = local / 'he.inp'
    source.write_text(f'! HF STO-3G\n%base "{prefix}"\n* xyz 0 1\nHe 0 0 0\n*\n')
    remote = tmp_path / 'remote'
    _stage_and_submit(DirectoryTransport(remote), 'ssh_local', 1, source, local, '/remote/job', 'orca', {}, {})
    manifest = json.loads((local / '.cloudra/remote-1/path-map.json').read_text())
    staged = remote / manifest['files'][0]['staged_path']
    assert staged.with_suffix('.gbw').read_bytes() == b'previous orbitals'


def test_orca_current_capture_precedes_old_native_output_without_state(tmp_path):
    source = tmp_path / 'retry.inp'
    source.write_text('! HF STO-3G\n* xyz 0 1\nHe 0 0 0\n*\n')
    source.with_suffix('.out').write_text('old output: ORCA TERMINATED NORMALLY\n')
    capture = tmp_path / '.cloudra/calc-72.out.log'
    capture.parent.mkdir()
    capture.write_text('current run: ORCA finished by error termination in orca_scf\n')
    assert resolve_log_path(str(source), 'orca', 72) == str(capture)


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_remote_old_success_log_and_state_do_not_certify_new_failure(tmp_path, engine):
    local = tmp_path / 'local'
    local.mkdir()
    db, job_id, source = await _insert_running(local, jobtype=engine)
    source.write_text('# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n' if engine == 'gaussian' else '! HF STO-3G\n* xyz 0 1\nHe 0 0 0\n*\n')
    old_log = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    old_log.write_text('Normal termination of Gaussian 16\n' if engine == 'gaussian' else 'ORCA TERMINATED NORMALLY\n')
    (local / f'state_{job_id}.json').write_text(json.dumps({'log_file': str(old_log)}))

    def finish(remote):
        assert not (remote / old_log.name).exists(), 'stale native logs are not execution inputs'
        assert not (remote / f'state_{job_id}.json').exists()
        (remote / '.cloudra').mkdir(exist_ok=True)
        (remote / '.cloudra' / f'calc-{job_id}.out.log').write_text('current engine start failed\n')

    remote = tmp_path / 'remote'
    assert await run_remote_compute(job_id, db.path, transport=DirectoryTransport(remote, finish=finish), sleep=_fast_sleep) == 1
    assert (await aget_compute_job(db, job_id))['state'] == 'failed'
    assert old_log.is_file()  # Old evidence remains available, but is not selected.


def test_remote_external_output_parent_cannot_be_redirected_to_runtime_after_stage(tmp_path):
    from cloudra.infra.ssh_transport import SshError
    from cloudra.runtime.remote_compute import _pull_remote_artifacts

    local = tmp_path / 'local'
    local.mkdir()
    external = tmp_path / 'external'
    external.mkdir()
    source = local / 'he.gjf'
    source.write_text(f'%chk={external / "output.chk"}\n# HF/STO-3G\n\nHe\n\n0 1\nHe 0 0 0\n\n')
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 1, source, local, '/remote/job', 'gaussian', {}, {})
    manifest = json.loads((local / '.cloudra/remote-1/path-map.json').read_text())
    (remote / manifest['files'][0]['staged_path']).write_bytes(b'remote checkpoint')
    external.rmdir()
    external.symlink_to(local / '.cloudra', target_is_directory=True)
    with pytest.raises(SshError, match='symlink'):
        _pull_remote_artifacts(transport, '/remote/job', local, source, 1)
    assert not (local / '.cloudra/output.chk').exists()


def test_orca_native_file_path_can_touch_comment_marker(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    hessian = local / 'previous.hess'
    hessian.write_bytes(b'Hessian dependency')
    source = local / 'irc.inp'
    original = '! HF STO-3G IRC\n%irc Hess_Filename previous.hess# native comment\nend\n* xyz 0 1\nHe 0 0 0\n*\n'
    source.write_text(original)
    remote = tmp_path / 'remote'
    _stage_and_submit(DirectoryTransport(remote), 'ssh_local', 1, source, local, '/remote/job', 'orca', {}, {})
    assert (remote / source.name).read_text() == original
    assert (remote / 'previous.hess').read_bytes() == b'Hessian dependency'


def test_orca_base_prefix_does_not_reintroduce_old_main_output(tmp_path):
    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'he.inp'
    source.write_text(f'! HF STO-3G\n%base "{source.with_suffix("")}"\n* xyz 0 1\nHe 0 0 0\n*\n')
    source.with_suffix('.out').write_text('ORCA TERMINATED NORMALLY\n')
    source.with_suffix('.gbw').write_bytes(b'existing orbitals')
    remote = tmp_path / 'remote'
    _stage_and_submit(DirectoryTransport(remote), 'ssh_local', 1, source, local, '/remote/job', 'orca', {}, {})
    assert not (remote / source.with_suffix('.out').name).exists()
    assert (remote / source.with_suffix('.gbw').name).read_bytes() == b'existing orbitals'


def test_orca_base_prefix_with_literal_brackets_returns_new_sidecar(tmp_path):
    from cloudra.runtime.remote_compute import _pull_remote_artifacts

    local = tmp_path / 'local'
    local.mkdir()
    prefix = tmp_path / 'external' / 'calc[1]'
    prefix.parent.mkdir()
    source = local / 'he.inp'
    source.write_text(f'! HF STO-3G\n%base "{prefix}"\n* xyz 0 1\nHe 0 0 0\n*\n')
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 1, source, local, '/remote/job', 'orca', {}, {})
    manifest = json.loads((local / '.cloudra/remote-1/path-map.json').read_text())
    staged = remote / manifest['files'][0]['staged_path']
    staged.with_name(staged.name + '.hess').write_bytes(b'new literal-prefix Hessian')
    _pull_remote_artifacts(transport, '/remote/job', local, source, 1)
    assert prefix.with_name(prefix.name + '.hess').read_bytes() == b'new literal-prefix Hessian'
