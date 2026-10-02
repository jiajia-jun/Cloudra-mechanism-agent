from pathlib import Path

import pytest

from cloudra.tools.core.ts_inputs import TsInputChanges, TsResumeRequest
from tests.test_ts_stage_inputs import record_fixture


def request(record, changes, **overrides):
    data = dict(changes=TsInputChanges.model_validate(changes), reason='revise explicitly declared input',
                request_key='revision-1', expected_revision=record.revision)
    data.update(overrides)
    return TsResumeRequest(**data)


@pytest.mark.parametrize('outcome', ['verified', 'candidate_only', 'search_failed', 'invalid_input'])
def test_same_run_can_change_guess_and_formal_method_after_attempt_ends(tmp_path, outcome):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record = record_fixture(tmp_path, terminal=outcome, stage='verdict')
    change = request(record, {'ts_optimization': {'engine': 'orca', 'method': 'b97-3c', 'keywords': ''}})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    assert revised.run_id == record.run_id
    assert revised.terminal is None
    assert revised.declaration_revision == 2
    assert revised.stage == 'submit'
    assert revised.attempt_history[0].terminal == outcome
    assert record.terminal == outcome


def test_endpoint_revision_retains_independent_completed_branch(tmp_path):
    from cloudra.tools.core.ts_process import TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record = record_fixture(tmp_path, terminal='verified', stage='verdict')
    purposes = ['ts_opt', 'frequency', 'irc', 'reactant_opt', 'reactant_frequency', 'product_opt', 'product_frequency']
    record.job_steps = [TsJobStep(purpose=p, job_id=i + 1, state='done') for i, p in enumerate(purposes)]
    change = request(record, {'verification': {'reactant_endpoint': {'optimization': {'engine': 'orca', 'method': 'b97-3c', 'keywords': ''}}}})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    assert [s.job_id for s in revised.job_steps] == [1, 2, 3, 6, 7]
    assert revised.stage == 'refine'
    assert [ref.stage_key for ref in receipt.invalidated] == ['reactant_opt', 'reactant_frequency']


def test_failed_scan_point_count_only_does_not_requeue(tmp_path):
    from cloudra.tools.core.ts_process import TsBlocked, TsJobStep
    from cloudra.tools.core.ts_revision import validate_recovery

    record = record_fixture(tmp_path, stage='guess', blocked=TsBlocked(stage='guess', failure_class='scan_job_failed', message='First point optimization / SHARK temporary file failed', needs=['guess']))
    path = tmp_path / 'scan.inp'
    path.write_text('accepted scan input')
    record.scan_step = TsJobStep(purpose='scan', job_id=7, state='failed', input_path=str(path))
    guess = record.input.guess.model_dump(mode='json')
    guess['scans'][0]['scan_steps'] = 8
    change = request(record, {'guess': guess})
    before = record.model_dump()
    with pytest.raises(ValueError, match='recovery evidence'):
        validate_recovery(record, change)
    assert record.model_dump() == before


def test_active_job_and_empty_resume_are_rejected_without_side_effects(tmp_path):
    from cloudra.tools.core.ts_process import TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision

    record = record_fixture(tmp_path)
    with pytest.raises(ValueError, match='ts_inspect'):
        plan_input_revision(record, request(record, {}))
    record.job_steps = [TsJobStep(purpose='ts_opt', job_id=1, state='ready')]
    with pytest.raises(ValueError, match='active'):
        plan_input_revision(record, request(record, {'reaction': {'charge': 1}}))
    assert record.job_steps[0].state == 'ready'


def test_unbound_recovery_artifact_cannot_authorize_retry(tmp_path):
    from cloudra.tools.core.ts_process import TsBlocked, TsJobStep
    from cloudra.tools.core.ts_revision import validate_recovery

    record = record_fixture(tmp_path, stage='guess', blocked=TsBlocked(stage='guess', failure_class='scan_job_failed', message='native failure'))
    record.scan_step = TsJobStep(purpose='scan', job_id=7, state='failed')
    evidence = tmp_path / 'claim.txt'
    evidence.write_text('environment repaired')
    change = request(record, {}, recovery={'failed_attempt': '1:scan:7', 'evidence_refs': [str(evidence)]})
    with pytest.raises(ValueError, match='authoritative'):
        validate_recovery(record, change)


def test_optional_null_changes_do_not_reinterpret_internal_atom_numbers(tmp_path):
    from cloudra.tools.core.ts_inputs import normalize_ts_input_atoms
    record = record_fixture(tmp_path)
    patch = normalize_ts_input_atoms(TsInputChanges.model_validate({'ts_optimization': None}), atom_tables={})
    assert patch.model_dump(exclude_unset=True) == {'ts_optimization': None}
    assert Path(record.run_dir) == tmp_path


def test_source_revision_clears_old_geometry_and_numeric_checkpoints(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    record = record_fixture(tmp_path, stage='map', current_seed_xyz_path='old.xyz',
        current_seed_mol_path='old.mol', product_seed_xyz_path='old-product.xyz',
        active_attempt_dir='old-attempt', current_ts_guess_path='old-ts.xyz', job_id=3,
        job_input_path='old-ts.inp')
    change = request(record, {'conformers': {'reactant': {'kind': 'generate', 'generation': 'ETKDGv3', 'seed': 123}}})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.stage == 'build'
    assert revised.current_seed_xyz_path == revised.current_seed_mol_path == ''
    assert revised.product_seed_xyz_path == revised.active_attempt_dir == ''
    assert revised.job_id is None and revised.job_input_path == ''
    assert record.current_seed_xyz_path == 'old.xyz'


def test_guess_revision_cannot_skip_an_unfinished_mapping_dependency(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    record = record_fixture(tmp_path, stage='map')
    change = request(record, {'guess': {'kind': 'xtb_path', 'method': 'GFN2-xTB'}})
    assert revise_record(record, change, plan_input_revision(record, change)).stage == 'map'


def test_custom_derivative_binding_is_preserved_in_revision_receipt(tmp_path):
    from cloudra.tools.core.ts_process import TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision
    record = record_fixture(tmp_path)
    record.job_steps = [TsJobStep(purpose='candidate_evaluation', stage_key='candidate_constraints:point',
        job_id=3, state='done')]
    receipt = plan_input_revision(record, request(record, {'conformers': {'guidance': {'ring_order': []}}}))
    assert receipt.invalidated[0].stage_key == 'candidate_constraints:point'


def test_environment_repair_evidence_allows_same_input_new_attempt(tmp_path):
    from cloudra.infra.compute_utils import resolve_log_path
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.tools.core.ts_process import TsBlocked, TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    db = ComputeDB(data_dir=tmp_path / 'ledger').init()
    old = tmp_path / 'failed.inp'
    old.write_text('accepted native input')
    failed = insert_compute_job(db, conversation_id='project', session_id='owner', path=str(old), state='failed', jobtype='orca', node_id='fixture')
    repaired = tmp_path / 'repaired.inp'
    repaired.write_bytes(old.read_bytes())
    success = insert_compute_job(db, conversation_id='project', session_id='owner', path=str(repaired), state='done', jobtype='orca', node_id='fixture')
    log = Path(resolve_log_path(str(repaired),job_type='orca',task_id=success))
    log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text('ORCA TERMINATED NORMALLY')
    record = record_fixture(tmp_path, stage='guess', blocked=TsBlocked(stage='guess', failure_class='scan_job_failed', message='SHARK temporary directory failure'),
        scan_step=TsJobStep(purpose='scan', job_id=failed, input_path=str(old),state='failed'))
    change = request(record, {}, recovery={'failed_attempt':f'1:scan:{failed}', 'evidence_refs':[str(log)]})
    with use_pipeline_database(db):
        revised = revise_record(record,change,plan_input_revision(record,change))
    assert revised.scan_step is None and revised.blocked is None
    assert revised.run_id == record.run_id
    assert revised.attempt_history[-1].blocked.failure_class == 'scan_job_failed'
    with db.connect() as con:
        assert con.execute('SELECT state FROM compute_jobs WHERE id=?',(failed,)).fetchone()[0] == 'failed'
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 2


def test_nonempty_unchanged_revision_preserves_outcome_and_usage(tmp_path, monkeypatch):
    from cloudra.services.ts_pipeline_store import get_process, save_process_record
    from cloudra.tools.core.ts_process import TsProcessRecord, resume
    from tests.test_ts_pipeline_driver import waiting_process
    db, pid, job = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)['record'])
    record.waiting_for = ''
    record.terminal, record.stage = 'verified', 'verdict'
    record.job_steps[0].state = 'done'
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
    save_process_record(db, process_id=pid, record=record.model_dump(mode='json'))
    version = get_process(db, pid)['revision']
    before = get_process(db, pid)
    monkeypatch.setattr('cloudra.tools.core.ts_pipeline_driver.advance_process',lambda *_: (_ for _ in ()).throw(AssertionError('No-op must not advance')))
    result = resume(record, request(record, {'execution':{'cpus':record.compute_cpus}}, expected_revision=version))
    assert result.terminal == 'verified'
    assert get_process(db,pid) == before


pytestmark = pytest.mark.usefixtures("ts_producer_authority")


def test_scientific_failure_requires_bound_recovery_even_when_job_done(tmp_path):
    import pytest

    from cloudra.tools.core.ts_inputs import TsResumeRequest
    from cloudra.tools.core.ts_process import TsJobStep, _record_candidate_failure
    from cloudra.tools.core.ts_revision import plan_input_revision
    from tests.test_ts_stage_inputs import record_fixture
    record = record_fixture(tmp_path)
    step = TsJobStep(purpose='frequency', job_id=7, input_path=str(tmp_path/'freq.inp'), state='done')
    record.job_steps = [step]
    _record_candidate_failure(record, 'wrong_mode', step, str(tmp_path/'freq.out'))
    assert record.failed_attempt['failure_class'] == 'wrong_mode'
    request = TsResumeRequest(expected_revision=0, request_key='retry', reason='change frequency', changes={'verification':{'frequency':{'engine':'orca','method':'HF/STO-3G','keywords':''}}})
    with pytest.raises(ValueError, match='recovery evidence'):
        plan_input_revision(record, request)


def test_intervention_limit_blocks_changes_without_erasing_history(tmp_path):
    from cloudra.tools.core.ts_inputs import TsExecutionLimits
    from cloudra.tools.core.ts_revision import plan_input_revision
    record = record_fixture(tmp_path, intervention_count=1)
    record.input.execution.limits=TsExecutionLimits(source='explicit_user',max_interventions=1)
    with pytest.raises(ValueError,match='intervention'):
        plan_input_revision(record,request(record,{'ts_optimization':None}))
    assert record.intervention_count==1
