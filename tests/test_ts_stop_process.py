import json
from pathlib import Path

import pytest

from cloudra.services.ts_pipeline_store import get_process
from cloudra.tools.core.ts_process import TsProcessRecord
from tests.test_ts_pipeline_driver import waiting_process

pytestmark = pytest.mark.usefixtures('ts_producer_authority')


@pytest.mark.parametrize(('initial', 'expected'), [('ready', 'cancelled'), ('running', 'cancel_requested')])
def test_stop_cancels_only_its_pipeline_and_preserves_inputs(tmp_path, initial, expected):
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process
    from cloudra.tools.core.ts_process import stop
    from tests.test_ts_pipeline_store import job_payload, payload

    db, pid, job = waiting_process(tmp_path)
    other = create_process(db, request_key='another-pipeline', payload=payload(workspace_dir=str(tmp_path)))
    other_job = bind_stage_job(db, process_id=other['process_id'], declaration_revision=1,
        stage_key='ts_opt', attempt=1, job_payload=job_payload(path='/fixture/other.inp'))
    with db.connect() as con:
        con.execute('UPDATE compute_jobs SET state=? WHERE id=?', (initial, job))
        path = Path(con.execute('SELECT path FROM compute_jobs WHERE id=?', (job,)).fetchone()[0])
    original = path.read_bytes()
    record = TsProcessRecord.model_validate(get_process(db, pid)['record'])

    stopped = stop(record, 'The declared candidate is not the intended reaction')

    assert stopped.stop_reason == 'The declared candidate is not the intended reaction'
    assert stopped.terminal is None and stopped.blocked is None
    assert stopped.input == record.input
    assert stopped.job_steps[0].state == expected
    assert path.read_bytes() == original
    assert get_process(db, pid)['status'] == 'stopped'
    with db.connect() as con:
        states = dict(con.execute('SELECT id,state FROM compute_jobs'))
    assert states[job] == expected
    assert states[other_job] == 'ready'
    again = stop(stopped, 'The declared candidate is not the intended reaction')
    assert again == stopped


def test_stopped_pipeline_records_cancelled_job_without_advancing(tmp_path):
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal, reconcile_processes
    from cloudra.tools.core.ts_process import advance, stop

    db, pid, job = waiting_process(tmp_path)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='running' WHERE id=?", (job,))
    stopped = stop(TsProcessRecord.model_validate(get_process(db, pid)['record']), 'Withdraw this hypothesis')
    assert advance(stopped) == stopped
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='cancelled' WHERE id=?", (job,))
    for _ in range(2):
        result = handle_process_job_terminal(db, job)
        reconcile_processes(db, 'project')
        assert result['status'] == 'stopped'
        assert result['record']['terminal'] is None
        assert result['record']['blocked'] is None
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 1
        evidence = con.execute('SELECT evidence FROM ts_pipeline_stages WHERE job_id=?', (job,)).fetchone()[0]
    assert json.loads(evidence)['status'] == 'cancelled'


def test_stopped_pipeline_cannot_bind_a_new_stage_job(tmp_path):
    from cloudra.services.ts_pipeline_store import bind_stage_job
    from cloudra.tools.core.ts_process import stop
    from tests.test_ts_pipeline_store import job_payload

    db, pid, _ = waiting_process(tmp_path)
    stop(TsProcessRecord.model_validate(get_process(db, pid)['record']), 'Stop submitting work')
    with pytest.raises(ValueError, match='stopped'):
        bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key='frequency',
                       attempt=1, job_payload=job_payload(path='/fixture/frequency.inp'))


def test_resume_clears_stop_and_keeps_its_reason_in_history(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    from cloudra.tools.core.ts_process import resume, stop

    db, pid, _ = waiting_process(tmp_path)
    stopped = stop(TsProcessRecord.model_validate(get_process(db, pid)['record']), 'Withdraw the old candidate')
    monkeypatch.setattr('cloudra.tools.core.ts_pipeline_driver.advance_process', get_process)
    resumed = resume(stopped, TsResumeRequest(changes={}, reason='Retry the stopped attempt',
        request_key='restart-stopped', expected_revision=stopped.revision))
    assert resumed.stop_reason is None
    assert resumed.declaration_revision == 2
    assert resumed.terminal is None
    assert resumed.attempt_history[-1].stop_reason == 'Withdraw the old candidate'
    assert resumed.attempt_history[-1].job_steps[0].state == 'cancelled'


def test_resume_waits_until_requested_cancellation_finishes(tmp_path):
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    from cloudra.tools.core.ts_process import resume, stop

    db, pid, job = waiting_process(tmp_path)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='running' WHERE id=?", (job,))
    stopped = stop(TsProcessRecord.model_validate(get_process(db, pid)['record']), 'Wrong candidate')
    before = get_process(db, pid)
    with pytest.raises(ValueError, match='active'):
        resume(stopped, TsResumeRequest(changes={}, reason='Retry', request_key='too-early',
                                       expected_revision=stopped.revision))
    assert get_process(db, pid) == before


def test_stop_does_not_revalidate_a_modified_current_structure(tmp_path):
    import hashlib

    from cloudra.services.ts_pipeline_store import save_process_record
    from cloudra.tools.core.ts_process import stop

    db, pid, job = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)['record'])
    source = tmp_path / 'current.xyz'
    source.write_text('2\naccepted\nH 0 0 0\nH 0 0 .74\n')
    from cloudra.tools.core.molecule import read_molecule
    record.structures.reactant = read_molecule(str(source), input_format='xyz')
    record.structures.reactant.SetProp('cloudra_import_source', json.dumps(dict(paths={'xyz':str(source)},
        hashes={'xyz':hashlib.sha256(source.read_bytes()).hexdigest()})))
    save_process_record(db, process_id=pid, record=record.model_dump(mode='json'))
    source.write_text('2\nreplacement\nH 0 0 0\nH 0 0 .80\n')
    replacement = source.read_bytes()

    stopped = stop(record, 'Current structure needs replacement')

    assert stopped.stop_reason == 'Current structure needs replacement'
    assert source.read_bytes() == replacement
    exported = json.loads((Path(record.run_dir) / 'process.json').read_text())
    assert exported['stop_reason'] == stopped.stop_reason
    assert exported['revision'] == get_process(db, pid)['revision']
    with db.connect() as con:
        assert con.execute('SELECT state FROM compute_jobs WHERE id=?', (job,)).fetchone()[0] == 'cancelled'
