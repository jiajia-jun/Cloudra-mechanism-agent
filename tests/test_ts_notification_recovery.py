"""Recover known TS references without scanning persisted pipeline records."""
import asyncio
import json
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.events import EventLog
from cloudra.services.ts_pipeline_store import bind_stage_job, create_process, get_process, save_process_record
from cloudra.tools.core.ts_inputs import TsInput
from cloudra.tools.core.ts_process import TsJobStep, TsProcessRecord


def make_acknowledged_wait(tmp_path, monkeypatch, *, project_id='project', owner_id='owner'):
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.compute_store import mark_notified

    inputs = TsInput.model_validate({
        'reaction': {'reactant_smiles': 'O', 'product_smiles': 'O', 'charge': 0, 'multiplicity': 1},
        'ts_optimization': {'engine': 'orca', 'method': 'HF', 'basis_set': 'STO-3G'},
        'verification': {'frequency': {'engine': 'orca', 'method': 'HF', 'basis_set': 'STO-3G'}},
    })
    db = ComputeDB(data_dir=tmp_path / 'ledger').init()
    process = create_process(db, request_key='recovery', payload={
        'project_id': project_id, 'owner_id': owner_id, 'workspace_dir': str(tmp_path),
        'input': inputs.model_dump(mode='json')})
    directory = tmp_path / 'ts' / 'ts_0015'
    directory.mkdir(parents=True)
    source = directory / 'ts-opt.inp'
    source.write_text('! OptTS HF STO-3G\n* xyz 0 1\nO 0 0 0\n*\n')
    job = bind_stage_job(db, process_id=process['process_id'], declaration_revision=1,
        stage_key='ts_opt', attempt=1, job_payload={
            'conversation_id': project_id, 'session_id': owner_id, 'path': str(source),
            'jobtype': 'orca', 'node_id': 'fixture'})
    record = TsProcessRecord(run_id='ts_0015', pipeline_id=process['process_id'], run_dir=str(directory),
        workspace_dir=str(tmp_path), owner_conversation_id=project_id, owner_session_id=owner_id,
        input=inputs, stage='refine', waiting_for=f'job:{job}', job_steps=[TsJobStep(
            purpose='ts_opt', stage_key='ts_opt', job_id=job, input_path=str(source),
            state='ready', actual_calculation=inputs.ts_optimization)])
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode='json'))
    record.revision = get_process(db, record.pipeline_id)['revision']
    export = directory / 'process.json'
    export.write_text(record.model_dump_json())
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done',end_timestamp=? WHERE id=?", (time.time(), job))
    mark_notified(db, job)

    def writer(record, directory):
        path = Path(directory) / 'frequency.inp'
        path.write_text('! Freq HF STO-3G\n* xyz 0 1\nO 0 0 0\n*\n')
        return '', str(path)
    monkeypatch.setattr('cloudra.tools.core.ts_process._write_frequency_input', writer)
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True, node_id='fixture', scheduler='local'))
    monkeypatch.setattr('cloudra.runtime_v2.compute_notify.ComputeDB', lambda: db)
    project = SimpleNamespace(id=project_id, workspace_dir=str(tmp_path), archived=False,
        settings=SimpleNamespace(benchmark_task_id=None))
    owner = SimpleNamespace(project_id=project_id, capabilities=SimpleNamespace(
        permissions=SimpleNamespace(write=True)))
    core = SimpleNamespace(projects={project_id: project}, agents={owner_id: owner},
        runner=SimpleNamespace(), deleted_project_ids=set(), store=None, event_log=EventLog(strict=True))
    return db, record, job, export, core, ComputeNotifyBroker(core)



@pytest.fixture
def acknowledged_wait(tmp_path, monkeypatch):
    return make_acknowledged_wait(tmp_path, monkeypatch)


def assert_one_frequency(db, record, old_job, *, total_jobs=2):
    state = TsProcessRecord.model_validate(get_process(db, record.pipeline_id)['record'])
    assert [(step.purpose, step.job_id) for step in state.job_steps[:-1]] == [('ts_opt', old_job)]
    assert state.job_steps[-1].purpose == 'frequency'
    assert state.waiting_for == f'job:{state.job_steps[-1].job_id}'
    assert state.declaration_revision == 1 and state.intervention_count == 0
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == total_jobs
        assert con.execute('SELECT COUNT(*) FROM ts_pipeline_declarations').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM ts_pipeline_revision_receipts').fetchone()[0] == 0
        assert con.execute('SELECT state,notified_at FROM compute_jobs WHERE id=?', (old_job,)).fetchone()[1] is not None
    return state


def job_count(db):
    with db.connect() as con:
        return con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]


@pytest.mark.asyncio
async def test_invalid_recovery_reference_does_not_block_pending_notifications(acknowledged_wait):
    db, record, job, export, _, broker = acknowledged_wait

    def invalid_export_with_pending_job():
        export.write_text('null')
        with db.connect() as con:
            con.execute('UPDATE compute_jobs SET notified_at=NULL WHERE id=?', (job,))

    await asyncio.to_thread(invalid_export_with_pending_job)
    await broker._poll_all()
    await asyncio.to_thread(assert_one_frequency, db, record, job)


@pytest.mark.asyncio
@pytest.mark.parametrize('already_acknowledged', [False, True])
async def test_poll_recovers_acknowledged_terminal_wait_once(acknowledged_wait, monkeypatch, already_acknowledged):
    from cloudra.tools.core import ts_pipeline_driver
    db, record, job, _, _, broker = acknowledged_wait
    if not already_acknowledged:
        def clear_ack():
            with db.connect() as con:
                con.execute('UPDATE compute_jobs SET notified_at=NULL WHERE id=?', (job,))
        await asyncio.to_thread(clear_ack)
    called = []
    original = ts_pipeline_driver.handle_process_job_terminal
    def observe(db, job_id):
        called.append(job_id)
        return original(db, job_id)
    monkeypatch.setattr(ts_pipeline_driver, 'handle_process_job_terminal', observe)
    await broker._poll_all()
    first = await asyncio.to_thread(assert_one_frequency, db, record, job)
    assert called == [job]  # A recovery reference and a pending notice are one delivery.
    await broker._poll_all()
    second = await asyncio.to_thread(assert_one_frequency, db, record, job)
    assert second.model_dump(mode='json') == first.model_dump(mode='json')
    assert called == [job]


@pytest.mark.asyncio
async def test_poll_recovers_project_loaded_after_broker_started(acknowledged_wait):
    db, record, job, _, core, broker = acknowledged_wait
    project = core.projects.pop('project')
    await broker._poll_all()
    assert await asyncio.to_thread(job_count, db) == 1
    core.projects['project'] = project
    await broker._poll_all()
    await asyncio.to_thread(assert_one_frequency, db, record, job)


@pytest.mark.asyncio
async def test_acknowledged_callback_failure_retries_known_job_without_export(acknowledged_wait, monkeypatch):
    from cloudra.tools.core import ts_pipeline_driver
    db, record, job, export, _, broker = acknowledged_wait
    original = ts_pipeline_driver.handle_process_job_terminal
    called = []
    def fail_once(db, job_id):
        called.append(job_id)
        if len(called) == 1:
            raise RuntimeError('Transient recovery callback failure')
        return original(db, job_id)
    monkeypatch.setattr(ts_pipeline_driver, 'handle_process_job_terminal', fail_once)
    await broker._poll_all()
    assert called == [job]
    # Recovery re-queued this known job; another filesystem pass is unnecessary.
    await asyncio.to_thread(export.unlink)
    await broker._poll_all()
    await asyncio.to_thread(assert_one_frequency, db, record, job)
    assert called == [job, job]
    await broker._poll_all()
    assert called == [job, job]


@pytest.mark.asyncio
@pytest.mark.parametrize('current_job_state', ['done', 'ready'])
async def test_export_is_only_a_process_reference_and_database_owns_waiting_job(
    acknowledged_wait, monkeypatch, current_job_state,
):
    from cloudra.services.compute_store import mark_notified
    from cloudra.tools.core import ts_pipeline_driver
    db, record, stale_job, export, _, broker = acknowledged_wait
    def replace_wait():
        current_input = export.parent / 'current-ts-opt.inp'
        current_input.write_text('! OptTS HF STO-3G\n* xyz 0 1\nO 0 0 0\n*\n')
        current_job = bind_stage_job(db, process_id=record.pipeline_id, declaration_revision=1,
            stage_key='current_ts_opt', attempt=1, job_payload={
                'conversation_id': 'project', 'session_id': 'owner', 'path': str(current_input),
                'jobtype': 'orca', 'node_id': 'fixture'})
        record.job_steps = [TsJobStep(purpose='ts_opt', stage_key='current_ts_opt', job_id=current_job,
            input_path=str(current_input), state='ready', actual_calculation=record.input.ts_optimization)]
        record.waiting_for = f'job:{current_job}'
        save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode='json'))
        if current_job_state == 'done':
            with db.connect() as con:
                con.execute("UPDATE compute_jobs SET state='done',end_timestamp=? WHERE id=?", (time.time(), current_job))
            mark_notified(db, current_job)
        # These obsolete fields are deliberately unsuitable for building a checkpoint.
        export.write_text(json.dumps({'pipeline_id': record.pipeline_id, 'waiting_for': f'job:{stale_job}',
            'stage': 'verdict', 'format_version': -1, 'terminal': 'verified'}))
        return current_job
    current_job = await asyncio.to_thread(replace_wait)
    called = []
    original = ts_pipeline_driver.handle_process_job_terminal
    def observe(db, job_id):
        called.append(job_id)
        return original(db, job_id)
    monkeypatch.setattr(ts_pipeline_driver, 'handle_process_job_terminal', observe)
    await broker._poll_all()
    if current_job_state == 'done':
        assert called == [current_job]
        await asyncio.to_thread(assert_one_frequency, db, record, current_job, total_jobs=3)
    else:
        assert called == []
        process = await asyncio.to_thread(get_process, db, record.pipeline_id)
        state = process['record']
        assert state['waiting_for'] == f'job:{current_job}' and state['terminal'] is None
        assert await asyncio.to_thread(job_count, db) == 2


@pytest.mark.asyncio
async def test_recovery_reads_pipeline_records_only_by_known_process_id(acknowledged_wait, monkeypatch):
    db, record, job, _, _, broker = acknowledged_wait
    statements = []
    original = ComputeDB.connect
    @contextmanager
    def traced(self, *args, **kwargs):
        with original(self, *args, **kwargs) as con:
            con.set_trace_callback(statements.append)
            yield con
    monkeypatch.setattr(ComputeDB, 'connect', traced)
    await broker._poll_all()
    reads = [sql for sql in statements if sql.lstrip().upper().startswith('SELECT')
             and 'ts_pipeline_processes' in sql.lower()]
    # Schema initialization also visits payloads to remove an obsolete limit.
    # Keep that exact migration separate from the recovery record-read check.
    migrations = {f'SELECT rowid,{column} FROM ts_pipeline_processes WHERE instr({column},\'"max_interventions"\')>0'
        for column in ('payload', 'record')}
    reads = [sql for sql in reads if sql not in migrations]
    assert reads, 'Recovery must read the authoritative process identified by its saved reference'
    for sql in reads:
        where = ' '.join(sql.lower().split()).partition(' where ')[2]
        assert where.startswith('process_id=') or where.startswith('process_id ='), sql
        assert record.pipeline_id in sql, sql
    await asyncio.to_thread(assert_one_frequency, db, record, job)



@pytest.mark.asyncio
async def test_blocked_recovery_notice_survives_broker_restart_after_content_failure(tmp_path, monkeypatch):
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from tests.test_runtime_v2_compute_notify import _setup_core

    core, project, coordinator = await _setup_core()
    project.workspace_dir = str(tmp_path)
    db, record, job, export, _, _ = await asyncio.to_thread(
        make_acknowledged_wait, tmp_path, monkeypatch,
        project_id=project.id, owner_id=coordinator.id)
    monkeypatch.setattr('cloudra.tools.core.ts_process._write_frequency_input',
        lambda *_: ('Native optimized geometry unavailable', ''))

    async def unavailable_content(*args, **kwargs):
        raise RuntimeError('Transient content construction failure')

    async def evidence_not_needed(*args, **kwargs):
        return '', True

    first = ComputeNotifyBroker(core)
    monkeypatch.setattr(first, '_content_for', unavailable_content)
    monkeypatch.setattr(ComputeNotifyBroker, '_snapshot_core_evidence', evidence_not_needed)
    await first._poll_all()

    def failed_notice_state():
        checkpoint = get_process(db, record.pipeline_id)['record']
        with db.connect() as con:
            acknowledged = con.execute('SELECT notified_at FROM compute_jobs WHERE id=?', (job,)).fetchone()[0]
        return checkpoint, acknowledged

    checkpoint, acknowledged = await asyncio.to_thread(failed_notice_state)
    assert checkpoint['blocked']['failure_class'] == 'frequency_input_failed'
    assert checkpoint['waiting_for'] == ''
    assert acknowledged is None
    assert not core.event_log.query_session(coordinator.id, types={'agent.message_injected'})
    # The authoritative checkpoint no longer waits, and a fresh broker has no
    # prior in-memory references. The existing durable notice queue owns retry.
    await asyncio.to_thread(export.unlink)
    restarted = ComputeNotifyBroker(core)
    await restarted._poll_all()
    checkpoint_after, acknowledged = await asyncio.to_thread(failed_notice_state)
    assert checkpoint_after == checkpoint
    assert acknowledged is not None
    messages = core.event_log.query_session(coordinator.id, types={'agent.message_injected'})
    assert len(messages) == 1
    assert messages[0].data['manifest'] == {'kind': 'compute_completion', 'task_ids': [job]}
    await restarted._poll_all()
    assert len(core.event_log.query_session(coordinator.id, types={'agent.message_injected'})) == 1
    assert await asyncio.to_thread(job_count, db) == 1
