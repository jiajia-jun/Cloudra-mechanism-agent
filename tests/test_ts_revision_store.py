from copy import deepcopy

import pytest

from cloudra.persistence.database import ComputeDB
from tests.test_ts_pipeline_store import job_payload, payload


def revision_fixture(tmp_path):
    from cloudra.services.ts_pipeline_store import create_process, save_process_record
    from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges, TsResumeRequest, apply_input_changes

    db = ComputeDB(data_dir=tmp_path).init()
    process = create_process(db, request_key="prepare", payload=payload())
    value = TsInput.model_validate(payload()['input'])
    request = TsResumeRequest(
        changes=TsInputChanges.model_validate({"verification": {"irc": {"replace": {"engine": "orca", "method": "b97-3c", "basis_set": "", "keywords": ""}}}}),
        reason="supply IRC method", request_key="resume-1", expected_revision=1,
    )
    state = dict(run_id='revision', run_dir=str(tmp_path / 'run'), workspace_dir=payload()['workspace_dir'],
                 pipeline_id=process["process_id"], owner_conversation_id="project", owner_session_id="owner",
                 format_version=6, declaration_revision=2, input=apply_input_changes(value, request.changes).model_dump(mode="json"),
                 stage="refine", blocked=None, waiting_for='', terminal=None)
    save_process_record(db, process_id=process['process_id'], record=dict(
        state, declaration_revision=1, input=value.model_dump(mode='json')))
    return db, process["process_id"], request, state


def receipt(request, **overrides):
    from cloudra.services.ts_pipeline_store import TsRevisionReceipt, revision_request_digest

    data = dict(request_key=request.request_key, request_digest=revision_request_digest(request), reason=request.reason,
                previous_revision=request.expected_revision, revision=request.expected_revision + 1,
                previous_input_revision=1, input_revision=2,
                changes=["verification.irc"], retained=[], invalidated=[], released_action_keys=[])
    data.update(overrides)
    return TsRevisionReceipt.model_validate(data)


def test_replay_after_response_loss_reuses_revision_and_jobs(tmp_path):
    from cloudra.services.ts_pipeline_store import commit_input_revision, get_process, get_revision_receipt

    db, pid, request, state = revision_fixture(tmp_path)
    accepted = commit_input_revision(db, process_id=pid, request=request, record=state, receipt=receipt(request))
    assert get_revision_receipt(db, process_id=pid, request_key=request.request_key) == accepted
    before = get_process(db, pid)
    assert commit_input_revision(db, process_id=pid, request=request, record=state, receipt=receipt(request)) == accepted
    assert get_process(db, pid) == before
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM ts_pipeline_revision_receipts").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 0


def test_receipt_cannot_accept_an_undeclared_input_change(tmp_path):
    from cloudra.services.ts_pipeline_store import commit_input_revision, get_process
    db, pid, request, state = revision_fixture(tmp_path)
    state['input']['reaction']['charge'] += 1
    before = get_process(db, pid)
    with pytest.raises(ValueError,match='accepted request'):
        commit_input_revision(db,process_id=pid,request=request,record=state,receipt=receipt(request))
    assert get_process(db,pid) == before


def test_conflicting_key_and_stale_revision_do_not_mutate(tmp_path):
    from cloudra.services.ts_pipeline_store import commit_input_revision, get_process

    db, pid, request, state = revision_fixture(tmp_path)
    commit_input_revision(db, process_id=pid, request=request, record=state, receipt=receipt(request))
    before = deepcopy(get_process(db, pid))
    conflicting = request.model_copy(update={"reason": "different content"})
    with pytest.raises(ValueError, match="conflict"):
        commit_input_revision(db, process_id=pid, request=conflicting, record=state, receipt=receipt(conflicting))
    stale = request.model_copy(update={"request_key": "unseen-stale"})
    with pytest.raises(ValueError, match="stale"):
        commit_input_revision(db, process_id=pid, request=stale, record=state, receipt=receipt(stale))
    assert get_process(db, pid) == before


def test_revision_keeps_historical_inputs_and_reused_evidence(tmp_path):
    from cloudra.services.ts_pipeline_store import bind_stage_job, commit_input_revision, get_process

    db, pid, request, state = revision_fixture(tmp_path)
    job = bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key="ts_opt", attempt=1,
                         job_payload=job_payload())
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
        before = con.execute("SELECT * FROM ts_pipeline_stages").fetchall()
        original = con.execute("SELECT payload FROM ts_pipeline_declarations").fetchone()[0]
    request = request.model_copy(update={"expected_revision": get_process(db, pid)["revision"]})
    ref = dict(declaration_revision=1, stage_key="ts_opt", attempt=1, job_id=job)
    commit_input_revision(db, process_id=pid, request=request, record=state,
                          receipt=receipt(request, retained=[ref]))
    with db.connect() as con:
        assert con.execute("SELECT * FROM ts_pipeline_stages").fetchall() == before
        assert con.execute("SELECT payload FROM ts_pipeline_declarations WHERE declaration_revision=1").fetchone()[0] == original
        assert con.execute("SELECT COUNT(*) FROM ts_pipeline_declarations").fetchone()[0] == 2


def test_input_revision_withdraws_only_invalidated_queued_jobs(tmp_path):
    from cloudra.services.ts_pipeline_store import (
        bind_stage_job,
        commit_input_revision,
        get_process,
        get_revision_receipt,
    )
    from cloudra.tools.core.ts_inputs import TsInput, TsInputChanges, apply_input_changes

    db, pid, request, state = revision_fixture(tmp_path)
    request = request.model_copy(update={'changes': TsInputChanges.model_validate({
        'verification': {'reactant_endpoint': {'optimization': {'replace': {
            'engine': 'orca', 'method': 'b97-3c', 'basis_set': '', 'keywords': '',
        }}}},
    })})
    old_input = TsInput.model_validate(get_process(db, pid)['record']['input'])
    state['input'] = apply_input_changes(old_input, request.changes).model_dump(mode='json')
    affected = bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key='reactant_opt', attempt=1,
                              job_payload=job_payload(path='/fixture/reactant.inp'))
    retained = bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key='product_opt', attempt=1,
                              job_payload=job_payload(path='/fixture/product.inp'))
    state['job_steps'] = [dict(purpose='product_opt', job_id=retained, state='ready', source_input_revision=1)]
    request = request.model_copy(update={"expected_revision": get_process(db, pid)["revision"]})
    refs = receipt(request,
        changes=['verification.reactant_endpoint.optimization.method', 'verification.reactant_endpoint.optimization.basis_set'],
        invalidated=[dict(declaration_revision=1, stage_key='reactant_opt', attempt=1, job_id=affected)],
        retained=[dict(declaration_revision=1, stage_key='product_opt', attempt=1, job_id=retained)])
    with db.connect() as con:
        old_bindings = con.execute('SELECT * FROM ts_pipeline_stages ORDER BY job_id').fetchall()
        old_declaration = con.execute('SELECT payload FROM ts_pipeline_declarations WHERE declaration_revision=1').fetchone()[0]

    accepted = commit_input_revision(db, process_id=pid, request=request, record=state, receipt=refs)

    assert get_revision_receipt(db, process_id=pid, request_key=request.request_key) == accepted
    assert get_process(db, pid)['declaration_revision'] == 2
    assert [step['job_id'] for step in get_process(db, pid)['record']['job_steps']] == [retained]
    with db.connect() as con:
        jobs = con.execute('SELECT id,state,end_timestamp FROM compute_jobs ORDER BY id').fetchall()
        assert [(job[0], job[1]) for job in jobs] == [(affected, 'cancelled'), (retained, 'ready')]
        assert jobs[0][2] > 0
        assert con.execute('SELECT * FROM ts_pipeline_stages ORDER BY job_id').fetchall() == old_bindings
        assert con.execute('SELECT payload FROM ts_pipeline_declarations WHERE declaration_revision=1').fetchone()[0] == old_declaration


@pytest.mark.parametrize('job_state', ['running', 'cancel_requested'])
def test_started_compute_prevents_transactional_revision_without_mutation(tmp_path, job_state):
    from cloudra.services.ts_pipeline_store import (
        bind_stage_job,
        commit_input_revision,
        get_process,
        get_revision_receipt,
    )

    db, pid, request, state = revision_fixture(tmp_path)
    job = bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key="ts_opt", attempt=1, job_payload=job_payload())
    with db.connect() as con:
        con.execute('UPDATE compute_jobs SET state=? WHERE id=?', (job_state, job))
        jobs_before = con.execute('SELECT * FROM compute_jobs').fetchall()
    request = request.model_copy(update={"expected_revision": get_process(db, pid)["revision"]})
    before = get_process(db, pid)
    with pytest.raises(ValueError, match="active"):
        commit_input_revision(db, process_id=pid, request=request, record=state, receipt=receipt(request))
    assert get_process(db, pid) == before
    assert get_revision_receipt(db, process_id=pid, request_key=request.request_key) is None
    with db.connect() as con:
        assert con.execute('SELECT * FROM compute_jobs').fetchall() == jobs_before


def test_invalid_evidence_rolls_back_input_and_receipt(tmp_path):
    from cloudra.services.ts_pipeline_store import commit_input_revision, get_process, get_revision_receipt

    db, pid, request, state = revision_fixture(tmp_path)
    before = get_process(db, pid)
    ref = dict(declaration_revision=1, stage_key="ts_opt", attempt=1, job_id=999)
    with pytest.raises(ValueError, match="evidence binding"):
        commit_input_revision(db, process_id=pid, request=request, record=state, receipt=receipt(request, retained=[ref]))
    assert get_process(db, pid) == before
    assert get_revision_receipt(db, process_id=pid, request_key=request.request_key) is None


def test_simultaneous_response_loss_replay_commits_only_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from cloudra.services.ts_pipeline_store import commit_input_revision, get_process

    db, pid, request, state = revision_fixture(tmp_path)

    def accept(_):
        return commit_input_revision(ComputeDB.from_path(db.path), process_id=pid, request=request,
                                     record=state, receipt=receipt(request))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, range(2)))
    assert results[0] == results[1]
    assert get_process(db, pid)["revision"] == 2


def test_revision_without_source_overwrite_does_not_inventory_job_artifacts(tmp_path, monkeypatch):
    from cloudra.services.ts_pipeline_store import commit_input_revision

    db, pid, request, state = revision_fixture(tmp_path)
    job = tmp_path / "other-job.inp"
    job.write_text("unrelated calculation")
    with db.connect() as con:
        con.execute("INSERT INTO compute_jobs(conversation_id,path,state,jobtype) VALUES (?,?,?,?)",
                    ("project", str(job), "done", "orca"))

    def unexpected_inventory(*_):
        pytest.fail("a revision without source writes must not inventory unrelated calculation files")

    monkeypatch.setattr("cloudra.infra.compute_utils.resolve_log_path", unexpected_inventory)
    commit_input_revision(db, process_id=pid, request=request, record=state, receipt=receipt(request))
