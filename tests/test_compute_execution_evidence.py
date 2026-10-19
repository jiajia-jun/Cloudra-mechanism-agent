"""Current-execution evidence through real guard/finalization and Slurm boundaries."""

import asyncio
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cloudra.infra import slurm
from cloudra.infra.compute_utils import (
    calc_lock_path,
    complete_execution_evidence,
    prepare_execution_evidence,
    resolve_log_path,
)
from cloudra.infra.flocks import try_acquire_lock
from cloudra.persistence.database import ComputeDB
from cloudra.runtime import monitor
from cloudra.services.compute_store import afinalize_compute_job, aget_compute_job, ainsert_compute_job

NORMAL = {'gaussian': 'Normal termination of Gaussian 16\n', 'orca': 'ORCA TERMINATED NORMALLY\n'}


async def _running(tmp_path, engine, *, scheduler='local'):
    db = await ComputeDB().ainit()
    source = tmp_path / ('mol.gjf' if engine == 'gaussian' else 'mol.inp')
    source.write_text('# HF/STO-3G\n' if engine == 'gaussian' else '! HF STO-3G\n')
    job = await ainsert_compute_job(db, conversation_id='evidence', session_id=None,
                                  path=str(source), state='running', jobtype=engine,
                                  node_id='test', scheduler=scheduler)
    return db, job, source


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
@pytest.mark.parametrize('new_output', ['launch_failure', 'same_native', 'stdout_only', 'native_with_wrapper'])
async def test_guard_binds_current_execution_and_preserves_previous_log(tmp_path, monkeypatch, engine, new_output):
    db, job, source = await _running(tmp_path, engine)
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    old = NORMAL[engine]
    native.write_text(old)
    original_input = source.read_bytes()
    monkeypatch.setattr(monitor, 'check_job_type', lambda *_: (True, ''))
    monkeypatch.setattr(monitor, 'build_calculator_cmd', lambda *_args, **_kwargs: (True, ['unused'], ''))
    monkeypatch.setattr(monitor, '_cclib_parse', AsyncMock(return_value=None))
    monkeypatch.setattr('cloudra.dag.controller.enqueue_compute_review', AsyncMock())

    async def spawn(*_args, **kwargs):
        if new_output in {'same_native', 'native_with_wrapper'}:
            native.write_text(old)
        capture = NORMAL[engine] if new_output == 'stdout_only' else 'wrapper diagnostic\n'
        if new_output == 'launch_failure':
            capture = 'engine launch failed: command not found\n'
        os.write(kwargs['stdout'], capture.encode())
        status = 127 if new_output == 'launch_failure' else 0
        return SimpleNamespace(pid=999999, returncode=status, wait=AsyncMock(return_value=status))

    monkeypatch.setattr(monitor.asyncio, 'create_subprocess_exec', spawn)
    await monitor.run_guard(job, str(source), 'evidence', 0, db.path, engine)
    row = await aget_compute_job(db, job)
    assert row['state'] == ('failed' if new_output == 'launch_failure' else 'done')
    selected = Path(resolve_log_path(str(source), engine, job))
    assert selected.is_relative_to(tmp_path / '.cloudra' / f'execution-{job}')
    assert selected.read_text() == ('engine launch failed: command not found\n'
                                    if new_output == 'launch_failure' else NORMAL[engine])
    assert json.loads((tmp_path / f'state_{job}.json').read_text())['log_file'] == str(selected)
    assert (tmp_path / '.cloudra' / f'execution-{job}' / 'previous' / native.name).read_text() == old
    assert source.read_bytes() == original_input
    # Another execution can replace the conventional output without changing this job.
    native.write_text('a later calculation\n')
    assert Path(resolve_log_path(str(source), engine, job)).read_text() == selected.read_text()


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_slurm_failed_scheduler_still_checks_current_native_success(tmp_path, monkeypatch, engine):
    db, job, source = await _running(tmp_path, engine, scheduler='slurm')
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    # Slurm's actual submission boundary creates the current native output.
    def submit(_script):
        native.write_text(NORMAL[engine])
        return '123'

    monkeypatch.setattr(slurm, 'submit_batch', submit)
    monkeypatch.setattr(slurm, 'query_job', lambda _: ('FAILED', '1:0'))
    monkeypatch.setattr(slurm, 'build_calculator_cmd', lambda *_args, **_kwargs: (True, ['unused'], ''))
    assert await slurm.run_slurm_compute(job, db.path, scheduler={}) == 0
    assert (await aget_compute_job(db, job))['state'] == 'done'
    assert Path(resolve_log_path(str(source), engine, job)).read_text() == NORMAL[engine]


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_slurm_both_engines_capture_stdout_at_the_query_path(tmp_path, engine):
    script = slurm.build_batch_script(tmp_path / 'mol.inp', engine, 7, {}, calculator_cmd=['native-engine'])
    assert 'native-engine > .cloudra/calc-7.out.log 2>&1' in script


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_guard_does_not_archive_another_live_jobs_native_output(tmp_path, monkeypatch, engine):
    db, live_job, source = await _running(tmp_path, engine)
    _, new_job, _ = await _running(tmp_path, engine)
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    native.write_text('the other calculator is still writing\n')
    held = try_acquire_lock(calc_lock_path(str(tmp_path), live_job))
    assert held is not None
    spawn = AsyncMock()
    monkeypatch.setattr(monitor, 'check_job_type', lambda *_: (True, ''))
    monkeypatch.setattr(monitor, 'build_calculator_cmd', lambda *_args, **_kwargs: (True, ['unused'], ''))
    monkeypatch.setattr(monitor.asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr('cloudra.dag.controller.enqueue_compute_review', AsyncMock())
    try:
        await monitor.run_guard(new_job, str(source), 'evidence', 0, db.path, engine)
        spawn.assert_not_called()
        assert (await aget_compute_job(db, live_job))['state'] == 'running'
        own = await aget_compute_job(db, new_job)
        assert own['state'] == 'failed'
        assert str(live_job) in own['last_error']
        assert native.read_text() == 'the other calculator is still writing\n'
        assert resolve_log_path(str(source), engine, new_job) != str(native)
    finally:
        os.close(held)


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
@pytest.mark.parametrize('output', ['launch_failure', 'stdout_only'])
async def test_slurm_uses_only_its_new_execution_log(tmp_path, monkeypatch, engine, output):
    db, job, source = await _running(tmp_path, engine, scheduler='slurm')
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    native.write_text(NORMAL[engine])

    def submit(_script):
        capture = tmp_path / '.cloudra' / f'calc-{job}.out.log'
        capture.write_text(NORMAL[engine] if output == 'stdout_only' else 'command not found\n')
        return '123'

    monkeypatch.setattr(slurm, 'submit_batch', submit)
    monkeypatch.setattr(slurm, 'query_job', lambda _: ('COMPLETED', '0:0') if output == 'stdout_only' else ('FAILED', '127:0'))
    monkeypatch.setattr(slurm, 'build_calculator_cmd', lambda *_args, **_kwargs: (True, ['unused'], ''))
    await slurm.run_slurm_compute(job, db.path, scheduler={})
    assert (await aget_compute_job(db, job))['state'] == ('done' if output == 'stdout_only' else 'failed')
    assert Path(resolve_log_path(str(source), engine, job)).read_text() == (
        NORMAL[engine] if output == 'stdout_only' else 'command not found\n')


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_adopt_uses_durable_prelaunch_receipt_and_keeps_historical_query(tmp_path, monkeypatch, engine):
    db, previous, source = await _running(tmp_path, engine)
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    native.write_text('old bytes\n' + NORMAL[engine])
    await afinalize_compute_job(db, previous, 'done')
    (tmp_path / f'state_{previous}.json').write_text(json.dumps({'log_file': str(native)}))
    _, job, _ = await _running(tmp_path, engine)
    prepare_execution_evidence(str(source), engine, job, db)
    assert Path(resolve_log_path(str(source), engine, previous)).read_text() == 'old bytes\n' + NORMAL[engine]
    assert json.loads((tmp_path / f'state_{previous}.json').read_text())['log_file'] == resolve_log_path(str(source), engine, previous)
    native.write_text('current bytes\n' + NORMAL[engine])
    monkeypatch.setattr(monitor, '_cclib_parse', AsyncMock(return_value=None))
    monkeypatch.setattr('cloudra.dag.controller.enqueue_compute_review', AsyncMock())
    await monitor.run_adopt(job, str(source), 'evidence', 0, db.path, engine)
    assert (await aget_compute_job(db, job))['state'] == 'done'
    selected = Path(resolve_log_path(str(source), engine, job))
    assert selected.read_text() == 'current bytes\n' + NORMAL[engine]
    native.write_text('future bytes\n')
    assert Path(resolve_log_path(str(source), engine, previous)).read_text() == 'old bytes\n' + NORMAL[engine]
    assert selected.read_text() == 'current bytes\n' + NORMAL[engine]


@pytest.mark.asyncio
async def test_frozen_orca_irc_keeps_full_endpoint_trajectory_and_archive_binding(tmp_path):
    from cloudra.tools.core import orca_frames
    from tests.test_orca_frames import _IRC_ENDPOINT_XYZ, _write_synthetic_irc_log

    db, job, source = await _running(tmp_path, 'orca')
    prepare_execution_evidence(str(source), 'orca', job, db)
    native = source.with_suffix('.out')
    native.write_text(_write_synthetic_irc_log(tmp_path, 'mol').read_text() + NORMAL['orca'])
    forward = tmp_path / 'mol_IRC_F.xyz'
    backward = tmp_path / 'mol_IRC_B_trj.xyz'
    forward.write_text(_IRC_ENDPOINT_XYZ)
    backward.write_text(_IRC_ENDPOINT_XYZ.replace('endpoint frame', 'first frame') + _IRC_ENDPOINT_XYZ)
    selected = Path(complete_execution_evidence(str(source), 'orca', job))
    forward.unlink()
    backward.unlink()
    native.write_text('overwritten later\n')
    endpoints = orca_frames.extract_irc_endpoints(str(selected))
    assert orca_frames.read_endpoint_geometry(endpoints['forward']) == _IRC_ENDPOINT_XYZ
    assert orca_frames.read_endpoint_geometry(endpoints['backward']) == _IRC_ENDPOINT_XYZ
    archived = Path(endpoints['backward']['geometry_ref'])
    assert 'first frame' in archived.read_text()  # full native trajectory, not a fabricated final frame
    archived.write_text('tampered\n')
    with pytest.raises(ValueError, match='hash mismatch'):
        orca_frames.extract_irc_endpoints(str(selected))


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_completed_irc_exports_canonical_endpoints_and_repairs_old_receipt(tmp_path, engine):
    from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts

    db, job, source = await _running(tmp_path, engine)
    prepare_execution_evidence(str(source), engine, job, db)
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    fixtures = Path(__file__).parent / 'fixtures'
    fixture = fixtures / ('gaussian/hcn_ts_irc_g16.log' if engine == 'gaussian' else 'benchmark_nu3/ts2_irc/irc.out')
    native.write_bytes(fixture.read_bytes())
    if engine == 'orca':
        for suffix in ('_IRC_F.xyz', '_IRC_B.xyz'):
            (tmp_path / ('mol' + suffix)).write_bytes((fixture.parent / ('irc' + suffix)).read_bytes())
    original = {path: path.read_bytes() for path in (source, native)}

    selected = complete_execution_evidence(str(source), engine, job)
    exported = read_irc_endpoint_artifacts(selected)

    assert set(exported) == {'irc_end_a_path', 'irc_end_b_path'}
    assert all(Path(path).parent == Path(selected).parent for path in exported.values())
    # An execution frozen by an older version can be upgraded without replacing its log.
    for path in exported.values():
        Path(path).unlink()
    assert complete_execution_evidence(str(source), engine, job) == selected
    assert read_irc_endpoint_artifacts(selected) == exported
    assert all(path.read_bytes() == contents for path, contents in original.items())


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
@pytest.mark.parametrize('capture_only', [False, True])
def test_remote_completed_irc_exports_inside_receipt_without_touching_input(tmp_path, engine, capture_only):
    from cloudra.runtime.remote_compute import _pull_remote_artifacts, _stage_and_submit
    from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts
    from tests.test_compute_transport_paths import DirectoryTransport

    local = tmp_path / 'local'
    local.mkdir()
    source = local / ('mol.gjf' if engine == 'gaussian' else 'mol.inp')
    source.write_text('# IRC HF/STO-3G\n' if engine == 'gaussian' else '! IRC HF STO-3G\n')
    original = source.read_bytes()
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 7, source, local, '/remote/job', engine, {}, {})
    output = remote / '.cloudra/calc-7.out.log' if capture_only else remote / ('mol.log' if engine == 'gaussian' else 'mol.out')
    output.parent.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).parent / 'fixtures'
    fixture = fixtures / ('gaussian/hcn_ts_irc_g16.log' if engine == 'gaussian' else 'benchmark_nu3/ts2_irc/irc.out')
    output.write_bytes(fixture.read_bytes())
    if engine == 'orca':
        for suffix in ('_IRC_F.xyz', '_IRC_B.xyz'):
            (remote / ('mol' + suffix)).write_bytes((fixture.parent / ('irc' + suffix)).read_bytes())

    _pull_remote_artifacts(transport, '/remote/job', local, source, 7, engine)

    selected = resolve_log_path(str(source), engine, 7)
    exported = read_irc_endpoint_artifacts(selected)
    assert set(exported) == {'irc_end_a_path', 'irc_end_b_path'}
    assert all(Path(path).is_relative_to(local / '.cloudra/remote-7/results') for path in exported.values())
    assert source.read_bytes() == original
    assert not list(local.glob('*end-a.xyz'))


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,fixture', [
    ('gaussian', 'gaussian/water_opt_freq_g16.out'), ('orca', 'orca/co2_freq_orca42.out'),
])
async def test_frozen_log_query_and_science_keep_real_frequency_geometry(tmp_path, engine, fixture):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.tools.Chemtool.query_compute_job import _row_to_dict
    from cloudra.tools.core.irc_evidence import probe_log

    db, job, source = await _running(tmp_path, engine)
    prepare_execution_evidence(str(source), engine, job, db)
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    native.write_bytes((Path(__file__).parent / 'fixtures' / fixture).read_bytes())
    before = probe_log(native)
    selected = Path(complete_execution_evidence(str(source), engine, job))
    await afinalize_compute_job(db, job, 'done')
    native.write_text('different later output\n')
    row = _row_to_dict(await aget_compute_job(db, job))
    assert row['log_path'] == str(selected)
    assert probe_log(selected) == before
    assert before[0] == 0 and before[1] is not None
    snapshot = snapshot_evidence_file(selected, tmp_path)
    assert snapshot.is_qm_log is True


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,suffix', [('gaussian', '.log'), ('orca', '.out')])
async def test_preparation_never_archives_the_submitted_input(tmp_path, engine, suffix):
    db, job, _ = await _running(tmp_path, engine)
    source = tmp_path / ('raw_input' + suffix)
    source.write_text('user input bytes\n')
    with pytest.raises(ValueError, match='submitted input'):
        prepare_execution_evidence(str(source), engine, job, db)
    assert source.read_text() == 'user input bytes\n'


@pytest.mark.asyncio
async def test_slurm_submission_window_reserves_native_output_before_handle_is_saved(tmp_path):
    db, first, source = await _running(tmp_path, 'orca', scheduler='slurm')
    _, second, _ = await _running(tmp_path, 'orca', scheduler='slurm')
    prepare_execution_evidence(str(source), 'orca', first, db)
    native = source.with_suffix('.out')
    native.write_text('first calculator is writing\n')
    with pytest.raises(ValueError, match='active compute job'):
        prepare_execution_evidence(str(source), 'orca', second, db)
    assert native.read_text() == 'first calculator is writing\n'


@pytest.mark.asyncio
async def test_irc_snapshot_never_reuses_previous_backward_or_unrelated_neighbor(tmp_path):
    from cloudra.tools.core import orca_frames
    from tests.test_orca_frames import _IRC_ENDPOINT_XYZ, _write_synthetic_irc_log

    db, job, source = await _running(tmp_path, 'orca')
    old = tmp_path / 'mol_IRC_B.xyz'
    old.write_text(_IRC_ENDPOINT_XYZ.replace('endpoint frame', 'OLD BACKWARD'))
    (tmp_path / 'neighbor_IRC_B.xyz').write_text(_IRC_ENDPOINT_XYZ.replace('endpoint frame', 'NEIGHBOR'))
    prepare_execution_evidence(str(source), 'orca', job, db)
    native = source.with_suffix('.out')
    native.write_text(_write_synthetic_irc_log(tmp_path, 'mol').read_text() + NORMAL['orca'])
    (tmp_path / 'mol_IRC_F.xyz').write_text(_IRC_ENDPOINT_XYZ.replace('endpoint frame', 'NEW FORWARD'))
    selected = complete_execution_evidence(str(source), 'orca', job)
    endpoints = orca_frames.extract_irc_endpoints(selected)
    assert 'NEW FORWARD' in orca_frames.read_endpoint_geometry(endpoints['forward'])
    assert endpoints['backward']['availability'] == 'unavailable'
    assert (tmp_path / '.cloudra' / f'execution-{job}' / 'previous' / old.name).read_text().find('OLD BACKWARD') > 0


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_adopt_before_preparation_does_not_accept_older_native_success(tmp_path, monkeypatch, engine):
    db, job, source = await _running(tmp_path, engine)
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    native.write_text(NORMAL[engine])
    monkeypatch.setattr(monitor, '_cclib_parse', AsyncMock(return_value=None))
    monkeypatch.setattr('cloudra.dag.controller.enqueue_compute_review', AsyncMock())
    await monitor.run_adopt(job, str(source), 'evidence', 0, db.path, engine)
    assert (await aget_compute_job(db, job))['state'] == 'failed'


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_state_receipt_uses_native_unknown_convergence_and_scf_identity(tmp_path, monkeypatch, engine):
    import cclib

    db, job, source = await _running(tmp_path, engine)
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    text = ('Gaussian 16\n # opt hf/sto-3g\n' if engine == 'gaussian' else 'ORCA VERSION 6\n! Opt\nFINAL SINGLE POINT ENERGY -1.25\n') + NORMAL[engine]
    native.write_text(text)
    monkeypatch.setattr(cclib.io, 'ccread', lambda *_a, **_k: None)
    monkeypatch.setattr(monitor, '_cclib_parse', AsyncMock(return_value=({'optdone': True, 'scf_energy_hartree': -9.9}, True)))
    monkeypatch.setattr('cloudra.dag.controller.enqueue_compute_review', AsyncMock())
    await monitor._finalize(db, job, native, str(tmp_path), 0, engine, 0)
    state = json.loads((tmp_path / f'state_{job}.json').read_text())
    assert state['opt_converged'] is None
    assert state['scf_energy_hartree'] is None
    if engine == 'orca':
        assert state['electronic_energy_hartree'] == -1.25


@pytest.mark.asyncio
async def test_frozen_neb_keeps_only_current_named_image_files(tmp_path):
    from cloudra.tools.core import orca_frames

    db, job, source = await _running(tmp_path, 'orca')
    fixture = Path(__file__).parent / 'fixtures' / 'orca' / 'neb_hcn'
    source = source.rename(tmp_path / 'neb.inp')
    source.write_text('! NEB HF STO-3G\n')
    (tmp_path / 'neb_im7.xyz').write_text('1\nOLD\nH 0 0 0\n')
    prepare_execution_evidence(str(source), 'orca', job, db)
    native = source.with_suffix('.out')
    native.write_bytes((fixture / 'neb.out').read_bytes())
    for name in ('neb_im0.xyz', 'neb_im4.xyz', 'neb_im8.xyz'):
        (tmp_path / name).write_bytes((fixture / name).read_bytes())
    before = orca_frames.extract_frames(str(native))
    selected = complete_execution_evidence(str(source), 'orca', job)
    assert [frame.frame for frame in before] == [0, 4, 8]
    for path in tmp_path.glob('neb_im*.xyz'):
        path.unlink()
    after = orca_frames.extract_frames(selected)
    assert [(frame.frame, frame.xyz) for frame in after] == [(frame.frame, frame.xyz) for frame in before]


@pytest.mark.asyncio
@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
async def test_running_query_notify_and_cancel_keep_current_native_receipt(tmp_path, monkeypatch, engine):
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from cloudra.tools.Chemtool.query_compute_job import QueryComputeJob, QueryComputeJob_input_schema

    db, job, source = await _running(tmp_path, engine, scheduler='slurm')
    prepare_execution_evidence(str(source), engine, job, db)
    native = source.with_suffix('.log' if engine == 'gaussian' else '.out')
    native.write_text('current partial output\n')
    query = QueryComputeJob()
    query.subagent = SimpleNamespace(conversation_id='evidence')
    running = await query.tool_call(QueryComputeJob_input_schema(job_id=job), None)
    assert running.jobs[0]['log_path'] == str(native)
    # Actual Slurm cancellation acknowledgement freezes output after terminal accounting.
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET scheduler_job_id='123',state='cancel_requested' WHERE id=?", (job,))
        con.commit()
    monkeypatch.setattr(slurm, 'query_job', lambda _: ('CANCELLED', '0:15'))
    monkeypatch.setattr(slurm, 'cancel_job', lambda _: None)
    await slurm.run_slurm_compute(job, db.path, scheduler={})
    assert (await aget_compute_job(db, job))['state'] == 'cancelled'
    files, missing = await ComputeNotifyBroker(SimpleNamespace())._core_files_for(job)
    selected = resolve_log_path(str(source), engine, job)
    assert selected in files and not missing
    assert Path(selected).read_text() == 'current partial output\n'
    native.write_text('a future calculation\n')
    cancelled = await query.tool_call(QueryComputeJob_input_schema(job_id=job), None)
    assert Path(cancelled.jobs[0]['log_path']).read_text() == 'current partial output\n'


def test_remote_staging_excludes_prior_geometry_at_both_push_layers_and_keeps_restart(tmp_path):
    from cloudra.runtime.remote_compute import _stage_and_submit
    from tests.test_compute_transport_paths import DirectoryTransport

    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'mol.inp'
    source.write_text('! IRC\n%base "native"\n')
    for name in ('native_IRC_B.xyz', 'native_im1.xyz', 'mol_IRC_F.xyz'):
        (local / name).write_text('old geometry\n')
    (local / 'native.gbw').write_bytes(b'needed restart orbitals')
    remote = tmp_path / 'remote'
    _stage_and_submit(DirectoryTransport(remote), 'ssh_local', 1, source, local, '/remote/job', 'orca', {}, {})
    for name in ('native_IRC_B.xyz', 'native_im1.xyz', 'mol_IRC_F.xyz'):
        assert not (remote / name).exists()
        assert (local / name).read_text() == 'old geometry\n'
    assert (remote / 'native.gbw').read_bytes() == b'needed restart orbitals'


@pytest.mark.asyncio
async def test_local_preparation_protects_explicit_geometry_input_dependency(tmp_path):
    db, job, source = await _running(tmp_path, 'orca')
    xyz = tmp_path / 'mol_IRC_F.xyz'
    xyz.write_text('1\nrequired input\nH 0 0 0\n')
    source.write_text('! IRC\n* xyzfile 0 1 mol_IRC_F.xyz\n')
    with pytest.raises(ValueError, match='input dependency'):
        prepare_execution_evidence(str(source), 'orca', job, db)
    assert xyz.read_text() == '1\nrequired input\nH 0 0 0\n'


@pytest.mark.asyncio
async def test_distinct_inputs_with_shared_base_do_not_move_a_live_jobs_geometry(tmp_path):
    db, live, source = await _running(tmp_path, 'orca')
    source.write_text('! IRC\n%base "shared"\n')
    other_source = tmp_path / 'another.inp'
    other_source.write_text(source.read_text())
    other = await ainsert_compute_job(db, conversation_id='evidence', session_id=None,
                                    path=str(other_source), state='running', jobtype='orca',
                                    node_id='test', scheduler='local')
    geometry = tmp_path / 'shared_IRC_F.xyz'
    geometry.write_text('live sidecar\n')
    held = try_acquire_lock(calc_lock_path(str(tmp_path), live))
    try:
        with pytest.raises(ValueError, match='active compute job'):
            prepare_execution_evidence(str(other_source), 'orca', other, db)
        assert geometry.read_text() == 'live sidecar\n'
    finally:
        os.close(held)


@pytest.mark.asyncio
async def test_simultaneous_slurm_preparations_reserve_one_shared_output_namespace(tmp_path):
    db, first, source = await _running(tmp_path, 'orca', scheduler='slurm')
    source.write_text('! IRC\n%base "shared"\n')
    other_source = tmp_path / 'another.inp'
    other_source.write_text(source.read_text())
    second = await ainsert_compute_job(db, conversation_id='evidence', session_id=None,
                                     path=str(other_source), state='running', jobtype='orca',
                                     node_id='test', scheduler='slurm')
    ready = threading.Barrier(2)

    def prepare(path, job):
        ready.wait(timeout=5)
        prepare_execution_evidence(str(path), 'orca', job, db)

    outcomes = await asyncio.gather(asyncio.to_thread(prepare, source, first),
                                    asyncio.to_thread(prepare, other_source, second), return_exceptions=True)
    assert sum(outcome is None for outcome in outcomes) == 1
    rejected = next(outcome for outcome in outcomes if outcome is not None)
    assert isinstance(rejected, ValueError) and 'active compute job' in str(rejected)


@pytest.mark.asyncio
async def test_missing_unrelated_historical_input_does_not_block_new_preparation(tmp_path):
    db, old, source = await _running(tmp_path, 'orca')
    await afinalize_compute_job(db, old, 'done')
    source.unlink()
    other_source = tmp_path / 'other.inp'
    other_source.write_text('! HF STO-3G\n')
    new = await ainsert_compute_job(db, conversation_id='evidence', session_id=None,
                                  path=str(other_source), state='running', jobtype='orca',
                                  node_id='test', scheduler='local')
    await asyncio.to_thread(prepare_execution_evidence, str(other_source), 'orca', new, db)


@pytest.mark.asyncio
@pytest.mark.parametrize('directive', ['NEB_END_XYZFILE', 'NEB_TS_XYZFILE'])
@pytest.mark.parametrize('equals', ['', '= '])
async def test_preparation_protects_explicit_neb_geometry_inputs(tmp_path, directive, equals):
    db, job, source = await _running(tmp_path, 'orca')
    xyz = tmp_path / 'mol_IRC_B.xyz'
    xyz.write_text('1\nNEB input must remain\nH 0 0 0\n')
    source.write_text(f'! NEB\n%neb\n {directive} {equals}"{xyz.name}"\nend\n')
    with pytest.raises(ValueError, match='input dependency'):
        prepare_execution_evidence(str(source), 'orca', job, db)
    assert xyz.read_text() == '1\nNEB input must remain\nH 0 0 0\n'


@pytest.mark.parametrize('capture_only', [False, True])
def test_remote_frozen_irc_never_promotes_an_explicit_geometry_input_to_backward_endpoint(tmp_path, capture_only):
    from cloudra.runtime.remote_compute import _pull_remote_artifacts, _stage_and_submit
    from cloudra.tools.core import orca_frames
    from tests.test_compute_transport_paths import DirectoryTransport
    from tests.test_orca_frames import _IRC_ENDPOINT_XYZ, _write_synthetic_irc_log

    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'mol.inp'
    source.write_text('! IRC\n* xyzfile 0 1 init_IRC_B.xyz\n')
    (local / 'init_IRC_B.xyz').write_text(_IRC_ENDPOINT_XYZ.replace('endpoint frame', 'OLD INPUT GEOMETRY'))
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 7, source, local, '/remote/job', 'orca', {}, {})
    output = remote / '.cloudra' / 'calc-7.out.log' if capture_only else remote / 'mol.out'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_write_synthetic_irc_log(remote, 'mol').read_text() + NORMAL['orca'])
    (remote / 'mol_IRC_F.xyz').write_text(_IRC_ENDPOINT_XYZ.replace('endpoint frame', 'NEW FORWARD'))
    _pull_remote_artifacts(transport, '/remote/job', local, source, 7)
    selected = resolve_log_path(str(source), 'orca', 7)
    endpoints = orca_frames.extract_irc_endpoints(selected)
    assert 'NEW FORWARD' in orca_frames.read_endpoint_geometry(endpoints['forward'])
    assert endpoints['backward']['availability'] == 'unavailable'
    assert 'OLD INPUT GEOMETRY' in (local / 'init_IRC_B.xyz').read_text()


def test_remote_frozen_neb_resolves_external_base_images_and_ignores_mutable_name(tmp_path):
    from cloudra.runtime.remote_compute import _pull_remote_artifacts, _stage_and_submit
    from cloudra.tools.core import orca_frames
    from tests.test_compute_transport_paths import DirectoryTransport

    local = tmp_path / 'local'
    local.mkdir()
    prefix = tmp_path / 'external' / 'actual'
    prefix.parent.mkdir()
    source = local / 'mol.inp'
    source.write_text(f'! NEB\n%base "{prefix}"\n')
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 7, source, local, '/remote/job', 'orca', {}, {})
    fixture = Path(__file__).parent / 'fixtures' / 'orca' / 'neb_hcn'
    # A stale NAME directory is deliberately readable, but cannot supply images.
    original = local / 'neb_im6.xyz'
    original.write_text('1\nSTALE NAME GEOMETRY\nH 0 0 0\n')
    (remote / 'mol.out').write_text((fixture / 'neb.out').read_text().replace('NAME = neb.inp', f'NAME = {local / "neb.inp"}'))
    mapping = json.loads((local / '.cloudra' / 'remote-7' / 'path-map.json').read_text())
    staged = next(item['staged_path'] for item in mapping['files'] if item.get('prefix'))
    for number in (0, 4, 8):
        image = (remote / staged).with_name(Path(staged).name + f'_im{number}.xyz')
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes((fixture / f'neb_im{number}.xyz').read_bytes())
    _pull_remote_artifacts(transport, '/remote/job', local, source, 7)
    selected = resolve_log_path(str(source), 'orca', 7)
    assert [frame.frame for frame in orca_frames.extract_frames(selected)] == [0, 4, 8]


def test_remote_prefix_restart_does_not_stage_an_old_endpoint_manifest(tmp_path):
    from cloudra.runtime.remote_compute import _pull_remote_artifacts, _stage_and_submit
    from tests.test_compute_transport_paths import DirectoryTransport
    from tests.test_orca_frames import _IRC_ENDPOINT_XYZ, _write_synthetic_irc_log

    local = tmp_path / 'local'
    local.mkdir()
    source = local / 'mol.inp'
    source.write_text('! IRC\n%base "irc"\n')
    (local / 'irc_endpoints.json').write_text('{"log_sha256":"old"}')
    remote = tmp_path / 'remote'
    transport = DirectoryTransport(remote)
    _stage_and_submit(transport, 'ssh_local', 7, source, local, '/remote/job', 'orca', {}, {})
    assert not (remote / 'irc_endpoints.json').exists()
    (remote / 'mol.out').write_text(_write_synthetic_irc_log(remote, 'irc').read_text() + NORMAL['orca'])
    (remote / 'irc_IRC_F.xyz').write_text(_IRC_ENDPOINT_XYZ)
    _pull_remote_artifacts(transport, '/remote/job', local, source, 7)
    assert (local / 'irc_endpoints.json').read_text() == '{"log_sha256":"old"}'
