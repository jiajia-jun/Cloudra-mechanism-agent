"""The ledger accepts one internally constructed molecular revision."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cloudra.services.ts_pipeline_store import (
    bind_stage_job,
    commit_input_revision,
    commit_stage_result,
    get_process,
    get_revision_receipt,
    save_process_record,
)
from cloudra.tools.core.ts_process import TsJobStep, TsProcessRecord
from tests.test_ts_revision_state import revision_request, state_fixture


def bind(record, db, tmp_path, purpose):
    path = tmp_path / (purpose + '.inp')
    path.write_text('! HF STO-3G Opt\n* xyz 0 1\nO 0 0 0\n*\n')
    job = bind_stage_job(db, process_id=record.pipeline_id, declaration_revision=1,
        stage_key=purpose, attempt=1, job_payload={
            'conversation_id': 'project', 'session_id': 'owner', 'path': str(path),
            'jobtype': 'orca', 'node_id': 'fixture',
        })
    record.job_steps.append(TsJobStep(purpose=purpose, stage_key=purpose, job_id=job,
        state='ready', input_path=str(path), source_input_revision=1))
    return job


def checkpoint(record, db):
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode='json'))
    record.revision = get_process(db, record.pipeline_id)['revision']


def test_conflicting_key_and_stale_revision_do_not_mutate(tmp_path):
    db, record = state_fixture(tmp_path)
    request = revision_request(record, {'ts_optimization': {'keywords': 'TightSCF'}})
    accepted = commit_input_revision(db, process_id=record.pipeline_id, request=request)
    before = get_process(db, record.pipeline_id)
    with pytest.raises(ValueError, match='conflict'):
        commit_input_revision(db, process_id=record.pipeline_id,
            request=request.model_copy(update={'reason': 'different content'}))
    with pytest.raises(ValueError, match='stale'):
        commit_input_revision(db, process_id=record.pipeline_id,
            request=request.model_copy(update={'request_key': 'new stale request'}))
    assert get_process(db, record.pipeline_id) == before
    assert get_revision_receipt(db, process_id=record.pipeline_id, request_key=request.request_key) == accepted


def test_revision_withdraws_only_affected_ready_and_keeps_old_declaration_completion(tmp_path):
    db, record = state_fixture(tmp_path)
    affected = bind(record, db, tmp_path, 'reactant_opt')
    retained = bind(record, db, tmp_path, 'product_opt')
    record.waiting_for = f'job:{retained}'
    checkpoint(record, db)
    with db.connect() as con:
        stages_before = con.execute('SELECT * FROM ts_pipeline_stages ORDER BY job_id').fetchall()
        declaration_before = con.execute('SELECT payload FROM ts_pipeline_declarations WHERE declaration_revision=1').fetchone()[0]
    request = revision_request(record, {'verification': {'reactant_endpoint': {'optimization': {
        'replace': {'engine': 'orca', 'method': 'HF', 'basis_set': 'STO-3G'},
    }}}})
    accepted = commit_input_revision(db, process_id=record.pipeline_id, request=request)
    state = get_process(db, record.pipeline_id)
    assert [ref.job_id for ref in accepted.invalidated] == [affected]
    assert [ref.job_id for ref in accepted.retained] == [retained]
    assert [step['job_id'] for step in state['record']['job_steps']] == [retained]
    assert state['record']['waiting_for'] == f'job:{retained}'
    with db.connect() as con:
        assert dict(con.execute('SELECT id,state FROM compute_jobs')) == {affected: 'cancelled', retained: 'ready'}
        assert con.execute('SELECT * FROM ts_pipeline_stages ORDER BY job_id').fetchall() == stages_before
        assert con.execute('SELECT payload FROM ts_pipeline_declarations WHERE declaration_revision=1').fetchone()[0] == declaration_before
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (retained,))
    assert commit_stage_result(db, process_id=record.pipeline_id, expected_revision=state['revision'],
        declaration_revision=1, stage_key='product_opt', attempt=1,
        evidence={'status': 'done', 'artifacts': [], 'input_hash': 'fixture'})
    with db.connect() as con:
        assert con.execute('SELECT evidence FROM ts_pipeline_stages WHERE job_id=?', (retained,)).fetchone()[0] is not None
    assert Path(record.job_steps[0].input_path).read_text().startswith('! HF STO-3G')


def test_queued_claim_between_preparation_and_commit_rejects_atomically(tmp_path, monkeypatch):
    from cloudra.tools.core import ts_revision
    db, record = state_fixture(tmp_path)
    job = bind(record, db, tmp_path, 'ts_opt')
    checkpoint(record, db)
    before = get_process(db, record.pipeline_id)
    original = ts_revision.revise_record

    def claimed(*args):
        prepared = original(*args)
        with db.connect() as con:
            con.execute("UPDATE compute_jobs SET state='running' WHERE id=?", (job,))
        return prepared

    monkeypatch.setattr(ts_revision, 'revise_record', claimed)
    with pytest.raises(ValueError, match='active'):
        commit_input_revision(db, process_id=record.pipeline_id,
            request=revision_request(record, {'ts_optimization': {'keywords': 'TightSCF'}}))
    assert get_process(db, record.pipeline_id) == before
    assert get_revision_receipt(db, process_id=record.pipeline_id, request_key='revision') is None
    with db.connect() as con:
        assert con.execute('SELECT state FROM compute_jobs WHERE id=?', (job,)).fetchone()[0] == 'running'


def test_simultaneous_replay_commits_once(tmp_path):
    from cloudra.persistence.database import ComputeDB
    db, record = state_fixture(tmp_path)
    request = revision_request(record, {'ts_optimization': {'keywords': 'TightSCF'}})
    def accept(_):
        return commit_input_revision(ComputeDB.from_path(db.path), process_id=record.pipeline_id, request=request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, range(2)))
    assert results[0] == results[1]
    assert get_process(db, record.pipeline_id)['revision'] == record.revision + 1
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM ts_pipeline_revision_receipts').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 0


@pytest.mark.usefixtures("rdkit_chemistry")
def test_file_import_happens_once_and_response_loss_replay_does_not_read_changed_source(tmp_path, monkeypatch):
    from cloudra.tools.core import reaction_state
    from cloudra.tools.core.molecule import serialize_molecule
    from tests.test_ts_revision_identity import molecular_fixture, write_source

    db, record = state_fixture(tmp_path)
    molecular, mol = molecular_fixture(tmp_path / 'molecules')
    record.input = molecular.input
    record.structures = molecular.structures
    # Initial imported declaration and checkpoint are accepted together for this fixture.
    with db.connect() as con:
        con.execute('UPDATE ts_pipeline_declarations SET payload=? WHERE process_id=? AND declaration_revision=1',
            (record.input.model_dump_json(), record.pipeline_id))
    checkpoint(record, db)
    source = write_source(tmp_path / 'incoming', 'reactant', mol)
    imports = []
    original = reaction_state.import_file_structure
    def import_once(*args):
        imports.append(args[1])
        return original(*args)
    monkeypatch.setattr(reaction_state, 'import_file_structure', import_once)
    request = revision_request(record, {'conformers': {'reactant': source}})
    accepted = commit_input_revision(db, process_id=record.pipeline_id, request=request)
    first = TsProcessRecord.model_validate(get_process(db, record.pipeline_id)['record'])
    Path(source['xyz_path']).write_text('later unrelated caller bytes')
    assert commit_input_revision(db, process_id=record.pipeline_id, request=request) == accepted
    second = TsProcessRecord.model_validate(get_process(db, record.pipeline_id)['record'])
    assert imports == ['reactant']
    assert serialize_molecule(second.structures.reactant) == serialize_molecule(first.structures.reactant)
    assert accepted.source_hashes['reactant']['xyz']
