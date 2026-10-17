"""Revisions own imported molecule state without rewriting caller files."""

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.services.ts_pipeline_store import create_process, get_process, save_process_record
from cloudra.tools.core.ts_inputs import TsInput, TsResumeRequest
from cloudra.tools.core.ts_process import TsProcessRecord


def state_fixture(tmp_path):
    inputs = TsInput.model_validate({
        'reaction': {'reactant_smiles': 'O', 'product_smiles': 'O', 'charge': 0, 'multiplicity': 1},
        'ts_optimization': {'engine': 'orca', 'method': 'HF', 'basis_set': 'STO-3G'},
    })
    db = ComputeDB(data_dir=tmp_path / 'ledger').init()
    process = create_process(db, request_key='prepare', payload={
        'project_id': 'project', 'owner_id': 'owner', 'workspace_dir': str(tmp_path),
        'input': inputs.model_dump(mode='json'),
    })
    record = TsProcessRecord(run_id='revision', pipeline_id=process['process_id'],
        run_dir=str(tmp_path / 'run'), workspace_dir=str(tmp_path),
        owner_conversation_id='project', owner_session_id='owner', input=inputs,
        stage='refine')
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode='json'))
    record.revision = get_process(db, record.pipeline_id)['revision']
    return db, record


def revision_request(record, changes, **updates):
    return TsResumeRequest(changes=changes, reason='Revise the current molecular state',
        request_key='revision', expected_revision=record.revision, **updates)


def test_commit_constructs_revision_from_request_and_replays_without_reimport(tmp_path):
    from cloudra.services.ts_pipeline_store import commit_input_revision

    db, record = state_fixture(tmp_path)
    request = revision_request(record, {'ts_optimization': {'keywords': 'TightSCF'}})
    accepted = commit_input_revision(db, process_id=record.pipeline_id, request=request)
    first = get_process(db, record.pipeline_id)
    assert first['declaration_revision'] == 2
    assert first['record']['input']['ts_optimization']['keywords'] == 'TightSCF'
    assert first['record']['attempt_history'][0]['input'] == record.input.model_dump(mode='json')
    assert commit_input_revision(db, process_id=record.pipeline_id, request=request) == accepted
    assert get_process(db, record.pipeline_id) == first


@pytest.mark.parametrize('job_state', ['running', 'cancel_requested'])
def test_started_job_rejects_revision_before_structure_changes(tmp_path, job_state):
    from cloudra.services.ts_pipeline_store import bind_stage_job, commit_input_revision

    db, record = state_fixture(tmp_path)
    input_path = tmp_path / 'job.inp'
    input_path.write_text('! HF STO-3G Opt\n* xyz 0 1\nO 0 0 0\n*\n')
    job = bind_stage_job(db, process_id=record.pipeline_id, declaration_revision=1,
        stage_key='ts_opt', attempt=1, job_payload={
            'conversation_id': 'project', 'session_id': 'owner', 'path': str(input_path),
            'jobtype': 'orca', 'node_id': 'fixture',
        })
    with db.connect() as con:
        con.execute('UPDATE compute_jobs SET state=? WHERE id=?', (job_state, job))
    before = get_process(db, record.pipeline_id)
    request = revision_request(record, {'ts_optimization': {'keywords': 'TightSCF'}})
    request.expected_revision = before['revision']
    with pytest.raises(ValueError, match='active'):
        commit_input_revision(db, process_id=record.pipeline_id, request=request)
    assert get_process(db, record.pipeline_id) == before
    assert input_path.read_text() == '! HF STO-3G Opt\n* xyz 0 1\nO 0 0 0\n*\n'
