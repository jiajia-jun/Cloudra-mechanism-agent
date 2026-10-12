"""Old TS state stays readable without recovering its unsupported source rewrites."""
import asyncio
import json
from copy import deepcopy

import pytest

from cloudra.infra.flocks import is_lock_held, locked
from cloudra.persistence.database import ComputeDB
from cloudra.services.ts_pipeline_store import (
    TsRevisionReceipt,
    bind_stage_job,
    create_process,
    get_process,
    read_process_snapshot,
)
from cloudra.tools.core.ts_inputs import TsInput
from cloudra.tools.core.ts_process import TsProcessRecord
from tests.test_ts_inputs import input_payload
from tests.test_ts_pipeline_store import job_payload


def _old_pending_rewrite(tmp_path, format_version=4):
    db = ComputeDB(data_dir=tmp_path / 'data').init()
    workspace = tmp_path / 'workspace'
    run_dir = workspace / 'ts' / 'old'
    run_dir.mkdir(parents=True)
    inputs = TsInput.model_validate(input_payload())
    process = create_process(db, request_key='old-pending', payload=dict(project_id='project', owner_id='owner',
        workspace_dir=str(workspace), input=inputs.model_dump(mode='json')))
    original_qm = run_dir / 'job.inp'
    original_qm.write_text('Original immutable quantum input fixture\n')
    native_job = job_payload()
    native_job['path'] = str(original_qm)
    jid = bind_stage_job(db, process_id=process['process_id'], declaration_revision=1, stage_key='ts_opt',
                         attempt=1, job_payload=native_job)
    revision = get_process(db, process['process_id'])['revision']
    state = TsProcessRecord(run_id='old', run_dir=str(run_dir), workspace_dir=str(workspace),
        owner_conversation_id='project', owner_session_id='owner', pipeline_id=process['process_id'],
        input=inputs, revision=revision, stage='refine', waiting_for=f'job:{jid}').model_dump(mode='json')
    legacy = dict(engine='orca', method='b3lyp/def2svp', keywords='D3BJ')
    state.update(format_version=format_version, job_steps=[dict(purpose='ts_opt', job_id=jid, state='ready',
        input_path=str(original_qm), actual_calculation=legacy, source_input_revision=1)])
    state['input']['ts_optimization'] = legacy
    source = workspace / 'reactant.xyz'
    source.write_text('2\nold source\nH 0 0 0\nH 0 0 1\n')
    changed = '2\npending canonical source\nH 0 0 1\nH 0 0 0\n'
    pending = deepcopy(state)
    pending.update(revision=revision + 1, declaration_revision=2, waiting_for='', job_steps=[],
        structures={'reactant': {'normalization': {'input_revision': 2}}})
    receipt = TsRevisionReceipt(request_key='old-rewrite', request_digest='old-digest', reason='Previously accepted source rewrite',
        previous_revision=revision, revision=revision + 1, previous_input_revision=1, input_revision=2,
        changes=['conformers.reactant'], retained=[], invalidated=[])
    intent = dict(record=pending, receipt=receipt.model_dump(mode='json'),
                  files=[dict(path=str(source), before=source.read_text(), after=changed)])
    with db.connect() as con:
        con.execute('UPDATE ts_pipeline_processes SET record=?,status=? WHERE process_id=?',
                    (json.dumps(state), 'waiting', process['process_id']))
        con.execute('INSERT INTO ts_pipeline_source_rewrites (process_id,request_key,payload) VALUES (?,?,?)',
                    (process['process_id'], receipt.request_key, json.dumps(intent)))
    return db, process['process_id'], workspace, state, jid, source, original_qm


@pytest.mark.parametrize('reader', ['get', 'snapshot', 'advance', 'inspect'])
@pytest.mark.parametrize('format_version', [4, 5])
def test_old_format_pending_rewrite_does_not_change_sources_jobs_or_locks(tmp_path, reader, format_version):
    db, pid, workspace, state, jid, source, original_qm = _old_pending_rewrite(tmp_path, format_version)
    with db.connect() as con:
        before_process = con.execute('SELECT * FROM ts_pipeline_processes WHERE process_id=?', (pid,)).fetchone()
        before_intent = con.execute('SELECT * FROM ts_pipeline_source_rewrites WHERE process_id=?', (pid,)).fetchone()
        before_job = con.execute('SELECT * FROM compute_jobs WHERE id=?', (jid,)).fetchone()
    before_source, before_qm = source.read_bytes(), original_qm.read_bytes()
    lock = tmp_path / 'qm-process.lock'
    with locked(str(lock)):
        if reader == 'get':
            result = get_process(db, pid)
            assert result['record'] == state
        elif reader == 'snapshot':
            result, jobs = read_process_snapshot(db, project_id='project', run_id='old', workspace_dir=str(workspace))
            assert result == state
            assert jobs[0]['job_id'] == jid and jobs[0]['state'] == 'ready'
        elif reader == 'advance':
            from cloudra.tools.core.ts_pipeline_driver import advance_process
            result = advance_process(db, pid)
            assert result['status'] == 'isolated'
            assert result['record'] == state
        else:
            from cloudra.tools.core.ts_state_view import inspect_process
            result = inspect_process(db, project_id='project', run_id='old', workspace_dir=str(workspace), can_write=True)
            assert result.status == 'isolated'
            assert result.next['action'] == 'inspect'
            assert next(entry for entry in result.methods if entry['purpose'] == 'ts_opt')['actual'] == state['job_steps'][0]['actual_calculation']
        assert is_lock_held(str(lock))
        assert source.read_bytes() == before_source
        assert original_qm.read_bytes() == before_qm
    with db.connect() as con:
        assert con.execute('SELECT * FROM ts_pipeline_processes WHERE process_id=?', (pid,)).fetchone() == before_process
        assert con.execute('SELECT * FROM ts_pipeline_source_rewrites WHERE process_id=?', (pid,)).fetchone() == before_intent
        assert con.execute('SELECT * FROM compute_jobs WHERE id=?', (jid,)).fetchone() == before_job


def test_old_checkpoint_does_not_parse_an_opaque_legacy_rewrite_intent(tmp_path):
    db, pid, _, state, _, source, _ = _old_pending_rewrite(tmp_path)
    payload = json.dumps({'opaque_legacy_intent': True})
    with db.connect() as con:
        con.execute('UPDATE ts_pipeline_source_rewrites SET payload=? WHERE process_id=?', (payload, pid))
    before = source.read_bytes()
    assert get_process(db, pid)['record'] == state
    assert source.read_bytes() == before
    with db.connect() as con:
        assert con.execute('SELECT payload FROM ts_pipeline_source_rewrites WHERE process_id=?', (pid,)).fetchone()[0] == payload


@pytest.mark.asyncio
async def test_format_five_public_resume_cannot_mutate_its_archived_run(tmp_path):
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.tools.Chemtool.ts_search_process import TsResume, TsResume_input_schema
    from tests.test_ts_search_process_tools import invoke, owned_tool

    db, pid, workspace, _, jid, source, original_qm = await asyncio.to_thread(_old_pending_rewrite, tmp_path, 5)

    def archive_snapshot():
        with db.connect() as con:
            return (con.execute('SELECT * FROM ts_pipeline_processes WHERE process_id=?', (pid,)).fetchone(),
                    con.execute('SELECT * FROM ts_pipeline_source_rewrites WHERE process_id=?', (pid,)).fetchone(),
                    con.execute('SELECT * FROM compute_jobs WHERE id=?', (jid,)).fetchone(),
                    source.read_bytes(), original_qm.read_bytes())

    before = await asyncio.to_thread(archive_snapshot)
    with use_pipeline_database(db):
        result = await invoke(owned_tool(TsResume, workspace=workspace), TsResume_input_schema(
            run_id='old', reason='Attempt to revise an archived source',
            changes={'reaction': {'reaction_center': [[1, 2]]}},
        ), call_id='attempt-format-five-resume')
        assert not result.is_success
        assert 'Unsupported TS input format' in result.message
    assert await asyncio.to_thread(archive_snapshot) == before
