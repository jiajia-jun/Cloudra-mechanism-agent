"""A frequency advisory wakes its owner while the accepted IRC keeps running."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.persistence import RuntimeStore, restore_core
from cloudra.runtime_v2.schemas import Command
from cloudra.services.ts_pipeline_store import (
    bind_stage_job,
    create_process,
    get_process,
    save_process_record,
)
from cloudra.tools.core.ts_process import TsJobStep, TsProcessRecord
from tests.test_runtime_v2_compute_notify import _notified_at, _setup_core
from tests.ts_fixtures import calculation_input


class RecordingRunner:
    def __init__(self):
        self.wakes = []

    def schedule(self, session_id):
        self.wakes.append(session_id)

    async def cancel(self, session_id):
        return None


async def setup_owner(tmp_path):
    core, project, coordinator = await _setup_core()
    core.store = await asyncio.to_thread(RuntimeStore, tmp_path / 'advisory-runtime.db')
    await core.event_writer.flush()
    project.workspace_dir = str(tmp_path)
    child = (await CommandBus(core).execute(Command(
        type='agent.spawn', target={'project_id': project.id},
        payload={'role_id': 'small_mol', 'parent_session_id': coordinator.id},
    ))).data
    await core.agent_host.start_run(child)
    await core.agent_host.finish_run(child, outcome='succeeded')
    core.runner = RecordingRunner()
    return core, project, coordinator, child


def waiting_irc(tmp_path, project_id, owner_id, *, alignment='misaligned', irc_state='running'):
    """Real ledger bindings; no engine or scientific decision runs in this fixture."""
    db = ComputeDB().init()
    value = calculation_input(reactant_smiles='O', product_smiles='O',
                              method='HF/STO-3G', engine='orca')
    process = create_process(db, request_key='mode-advisory', payload=dict(
        project_id=project_id, owner_id=owner_id, workspace_dir=str(tmp_path),
        input=value.model_dump(mode='json')))
    jobs = {}
    for purpose in ('frequency', 'irc'):
        source = tmp_path / f'{purpose}.inp'
        source.write_text(f'! {"Freq" if purpose == "frequency" else "IRC"} HF STO-3G\n'
                          '* xyz 0 1\nO 0 0 0\nH 1 0 0\nH 0 1 0\n*\n')
        jobs[purpose] = bind_stage_job(db, process_id=process['process_id'],
            declaration_revision=1, stage_key=purpose, attempt=1, job_payload=dict(
                conversation_id=project_id, session_id=owner_id, path=str(source),
                state='ready', jobtype='orca', node_id='fixture'))
    report = None if alignment is None else dict(
        log_path=str(tmp_path / 'frequency.out'), log_sha256='recorded-native-log',
        reaction_center_pairs=[[1, 2]], fraction_basis='unweighted_squared_displacement',
        modes=[], mode_alignment={'status': alignment},
    )
    record = TsProcessRecord(run_id='mode-advisory', run_dir=str(tmp_path / 'ts' / 'mode-advisory'),
        workspace_dir=str(tmp_path), owner_conversation_id=project_id, owner_session_id=owner_id,
        pipeline_id=process['process_id'], input=value, stage='refine',
        waiting_for=f'job:{jobs["irc"]}', job_steps=[
            TsJobStep(purpose='frequency', job_id=jobs['frequency'], state='done',
                input_path=str(tmp_path / 'frequency.inp'), actual_calculation=value.verification.frequency,
                frequency_analysis=report),
            TsJobStep(purpose='irc', job_id=jobs['irc'], state=irc_state,
                input_path=str(tmp_path / 'irc.inp'), actual_calculation=value.verification.irc),
        ])
    Path(record.run_dir).mkdir(parents=True)
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode='json'))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (jobs['frequency'],))
        con.execute('UPDATE compute_jobs SET state=? WHERE id=?', (irc_state, jobs['irc']))
    return db, record.pipeline_id, jobs


def notices(core, owner_id):
    return [event for event in core.event_log.query_session(owner_id, types={'agent.message_injected'})
            if (event.data.get('manifest') or {}).get('kind') == 'compute_completion']


def irc_checkpoint(db, process_id, jobs):
    state = get_process(db, process_id)
    with db.connect() as con:
        irc = con.execute('SELECT state FROM compute_jobs WHERE id=?', (jobs['irc'],)).fetchone()[0]
        count = con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]
    return state, irc, count


@pytest.mark.asyncio
@pytest.mark.parametrize('alignment', ['misaligned', 'undecidable'])
@pytest.mark.parametrize('irc_state', ['ready', 'running'])
async def test_frequency_advisory_wakes_only_owner_without_interrupting_irc(tmp_path, alignment, irc_state):
    core, project, coordinator, child = await setup_owner(tmp_path)
    db, process_id, jobs = await asyncio.to_thread(waiting_irc, tmp_path, project.id, child.id,
        alignment=alignment, irc_state=irc_state)
    before = await asyncio.to_thread(irc_checkpoint, db, process_id, jobs)
    broker = ComputeNotifyBroker(core)

    await broker._poll_project(project.id)

    assert len(notices(core, child.id)) == 1
    assert notices(core, child.id)[0].data['manifest'] == {
        'kind': 'compute_completion', 'task_ids': [jobs['frequency']],
    }
    assert core.runner.wakes == [child.id]
    assert child.state.value == 'running'
    assert notices(core, coordinator.id) == []
    assert await asyncio.to_thread(_notified_at, jobs['frequency']) is not None
    assert await asyncio.to_thread(irc_checkpoint, db, process_id, jobs) == before
    await broker._poll_project(project.id)
    assert len(notices(core, child.id)) == 1
    assert core.runner.wakes == [child.id]


@pytest.mark.asyncio
@pytest.mark.parametrize('alignment', ['aligned', 'missing', 'skipped', None])
async def test_other_frequency_reports_stay_silent(tmp_path, alignment):
    core, project, coordinator, child = await setup_owner(tmp_path)
    db, process_id, jobs = await asyncio.to_thread(waiting_irc, tmp_path, project.id, child.id,
                                                 alignment=alignment)
    before = await asyncio.to_thread(irc_checkpoint, db, process_id, jobs)
    await ComputeNotifyBroker(core)._poll_project(project.id)
    assert notices(core, child.id) == notices(core, coordinator.id) == []
    assert core.runner.wakes == []
    assert await asyncio.to_thread(_notified_at, jobs['frequency']) is not None
    assert await asyncio.to_thread(irc_checkpoint, db, process_id, jobs) == before


@pytest.mark.asyncio
async def test_old_frequency_advisory_does_not_turn_an_irc_event_into_an_alert(tmp_path):
    core, project, coordinator, child = await setup_owner(tmp_path)
    db, process_id, jobs = await asyncio.to_thread(waiting_irc, tmp_path, project.id, child.id)
    broker = ComputeNotifyBroker(core)
    await asyncio.to_thread(broker._mark_notified, jobs['frequency'])

    def finish_irc_and_wait_for_endpoint():
        state = get_process(db, process_id)
        record = TsProcessRecord.model_validate(state['record'])
        source = tmp_path / 'reactant_opt.inp'
        source.write_text((tmp_path / 'irc.inp').read_text())
        endpoint = bind_stage_job(db, process_id=process_id, declaration_revision=1,
            stage_key='reactant_opt', attempt=1, job_payload=dict(
                conversation_id=project.id, session_id=child.id, path=str(source),
                state='ready', jobtype='orca', node_id='fixture'))
        with db.connect() as con:
            con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (jobs['irc'],))
        record.job_steps[-1].state = 'done'
        record.job_steps.append(TsJobStep(purpose='reactant_opt', job_id=endpoint, state='ready',
            input_path=str(source), actual_calculation=record.input.verification.reactant_endpoint.optimization))
        record.waiting_for = f'job:{endpoint}'
        save_process_record(db, process_id=process_id, record=record.model_dump(mode='json'))

    await asyncio.to_thread(finish_irc_and_wait_for_endpoint)
    before = await asyncio.to_thread(irc_checkpoint, db, process_id, jobs)
    # A delayed IRC notification must not reuse the previous frequency's report.
    await broker._poll_project(project.id)
    assert notices(core, child.id) == notices(core, coordinator.id) == []
    assert core.runner.wakes == []
    assert await asyncio.to_thread(_notified_at, jobs['irc']) is not None
    assert await asyncio.to_thread(irc_checkpoint, db, process_id, jobs) == before


@pytest.mark.asyncio
async def test_advisory_message_persistence_failure_is_retried_before_ack_or_wake(tmp_path, monkeypatch):
    core, project, coordinator, child = await setup_owner(tmp_path)
    db, process_id, jobs = await asyncio.to_thread(waiting_irc, tmp_path, project.id, child.id)
    before = await asyncio.to_thread(irc_checkpoint, db, process_id, jobs)
    broker = ComputeNotifyBroker(core)

    async def unavailable(*args, **kwargs):
        raise OSError('notification persistence unavailable')

    with monkeypatch.context() as patcher:
        patcher.setattr(core.dispatcher, 'commit_and_deliver', unavailable)
        await broker._poll_project(project.id)
    assert await asyncio.to_thread(_notified_at, jobs['frequency']) is None
    assert notices(core, child.id) == []
    assert core.runner.wakes == []
    await broker._poll_project(project.id)
    assert len(notices(core, child.id)) == 1
    assert core.runner.wakes == [child.id]
    assert notices(core, coordinator.id) == []
    assert await asyncio.to_thread(irc_checkpoint, db, process_id, jobs) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('restart', [False, True])
async def test_unacked_advisory_receipt_survives_disappearing_report_without_duplicate(tmp_path, monkeypatch, restart):
    core, project, coordinator, child = await setup_owner(tmp_path)
    db, process_id, jobs = await asyncio.to_thread(waiting_irc, tmp_path, project.id, child.id)
    broker = ComputeNotifyBroker(core)

    def unavailable(_job_id):
        raise OSError('notification acknowledgement unavailable')

    with monkeypatch.context() as patcher:
        patcher.setattr(broker, '_mark_notified', unavailable)
        await broker._poll_project(project.id)
    assert await asyncio.to_thread(_notified_at, jobs['frequency']) is None
    assert len(notices(core, child.id)) == 1
    assert core.runner.wakes == []

    def remove_report():
        state = get_process(db, process_id)
        state['record']['job_steps'][0]['frequency_analysis'] = None
        save_process_record(db, process_id=process_id, record=state['record'])

    await asyncio.to_thread(remove_report)
    if restart:
        from cloudra.runtime_v2.core import RuntimeCore

        restored = RuntimeCore(strict_events=True)
        await asyncio.to_thread(restore_core, restored, core.store)
        core = restored
        core.runner = RecordingRunner()
    await ComputeNotifyBroker(core)._poll_project(project.id)
    assert await asyncio.to_thread(_notified_at, jobs['frequency']) is not None
    assert len(notices(core, child.id)) == 1
    assert notices(core, coordinator.id) == []
    assert core.runner.wakes == [child.id]
    assert core.agents[child.id].state.value == 'running'
    assert (await asyncio.to_thread(irc_checkpoint, db, process_id, jobs))[1:] == ('running', 2)


@pytest.mark.asyncio
async def test_cancelled_owner_receives_advisory_without_being_revived(tmp_path):
    core, project, coordinator, child = await setup_owner(tmp_path)
    await core.agent_host.start_run(child)
    await CommandBus(core).execute(Command(type='agent.cancel', target={'session_id': child.id}))
    assert child.state.value == 'cancelled'
    db, process_id, jobs = await asyncio.to_thread(waiting_irc, tmp_path, project.id, child.id)
    before = await asyncio.to_thread(irc_checkpoint, db, process_id, jobs)
    await ComputeNotifyBroker(core)._poll_project(project.id)
    assert len(notices(core, child.id)) == 1
    assert child.state.value == 'cancelled'
    assert core.runner.wakes == []
    assert notices(core, coordinator.id) == []
    assert await asyncio.to_thread(irc_checkpoint, db, process_id, jobs) == before
