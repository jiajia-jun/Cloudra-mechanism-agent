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
    change = request(record, {'ts_optimization': {'replace': {'engine': 'orca', 'method': 'b97-3c', 'basis_set': '', 'keywords': ''}}})
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
    change = request(record, {'verification': {'reactant_endpoint': {'optimization': {'replace': {'engine': 'orca', 'method': 'b97-3c', 'basis_set': '', 'keywords': ''}}}}})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    assert [s.job_id for s in revised.job_steps] == [1, 2, 3, 6, 7]
    assert revised.stage == 'refine'
    assert [ref.stage_key for ref in receipt.invalidated] == ['reactant_opt', 'reactant_frequency']


def test_failed_scan_point_count_change_preserves_failure_history(tmp_path):
    from cloudra.tools.core.ts_process import TsBlocked, TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    record = record_fixture(tmp_path, stage='guess', blocked=TsBlocked(stage='guess', failure_class='scan_job_failed', message='native failure'))
    record.scan_step = TsJobStep(purpose='scan', job_id=7, state='failed')
    guess = record.input.guess.model_dump(mode='json')
    guess['scans'][0]['scan_steps'] = 8
    change = request(record, {'guess': guess})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    assert revised.input.guess.scans[0].scan_steps == 8
    assert revised.stage == 'guess' and revised.scan_step is None
    assert revised.attempt_history[-1].blocked == record.blocked
    assert revised.attempt_history[-1].job_steps[0].job_id == 7
    assert record.blocked.failure_class == 'scan_job_failed'
    assert record.attempt_history == []
    assert record.scan_step.state == 'failed'


def test_empty_resume_without_failed_attempt_is_rejected(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision

    record = record_fixture(tmp_path)
    with pytest.raises(ValueError, match='ts_inspect'):
        plan_input_revision(record, request(record, {}))


@pytest.mark.parametrize('waiting_for', ['', 'job:1'])
def test_queued_job_allows_input_revision_with_or_without_waiting_marker(tmp_path, waiting_for):
    from cloudra.tools.core.ts_process import TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record = record_fixture(tmp_path, stage='refine', waiting_for=waiting_for)
    record.job_steps = [TsJobStep(purpose='ts_opt', job_id=1, state='ready')]
    before = record.model_dump(mode='json')
    change = request(record, {'ts_optimization': {'keywords': 'D3BJ TightSCF'}})

    planned = plan_input_revision(record, change)
    revised = revise_record(record, change, planned)

    assert [ref.job_id for ref in planned.invalidated] == [1]
    assert revised.declaration_revision == 2
    assert revised.input.ts_optimization.keywords == 'D3BJ TightSCF'
    assert revised.job_steps == []
    assert revised.waiting_for == ''
    assert record.model_dump(mode='json') == before


@pytest.mark.parametrize('job_state', ['running', 'cancel_requested'])
def test_started_job_still_rejects_input_revision_without_side_effects(tmp_path, job_state):
    from cloudra.tools.core.ts_process import TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision

    record = record_fixture(tmp_path, stage='refine', waiting_for='job:1')
    record.job_steps = [TsJobStep(purpose='ts_opt', job_id=1, state=job_state)]
    before = record.model_dump(mode='json')
    with pytest.raises(ValueError, match='active'):
        plan_input_revision(record, request(record, {'ts_optimization': {'keywords': 'D3BJ TightSCF'}}))
    assert record.model_dump(mode='json') == before




def test_optional_null_changes_do_not_reinterpret_internal_atom_numbers(tmp_path):
    from cloudra.tools.core.ts_inputs import normalize_ts_input_atoms
    record = record_fixture(tmp_path)
    patch = normalize_ts_input_atoms(TsInputChanges.model_validate({'ts_optimization': None}), atom_tables={})
    assert patch.model_dump(exclude_unset=True) == {'ts_optimization': None}
    assert Path(record.run_dir) == tmp_path


@pytest.mark.usefixtures("rdkit_chemistry")
def test_source_revision_clears_replaced_molecule_and_numeric_checkpoints(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    from tests.test_ts_revision_identity import molecular_fixture
    record, _ = molecular_fixture(tmp_path)
    record.active_attempt_dir, record.job_id, record.job_input_path = 'old-attempt', 3, 'old-ts.inp'
    change = request(record, {'conformers': {'reactant': {'kind': 'generate', 'generation': 'ETKDGv3', 'seed': 123}}})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.stage == 'build'
    assert revised.structures.reactant is None
    assert revised.structures.candidate is None
    assert revised.structures.product_to_reactant is None
    assert revised.active_attempt_dir == ''
    assert revised.job_id is None and revised.job_input_path == ''
    assert revised.input.conformers.guidance.ring_order == []
    assert revised.input.guess is None
    assert record.structures.reactant is not None


@pytest.mark.usefixtures("rdkit_chemistry")
def test_mutable_external_file_changes_require_explicit_source_patch(tmp_path):
    from cloudra.tools.core.molecule import serialize_molecule
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    from tests.test_ts_revision_identity import molecular_fixture, write_source
    record, mol = molecular_fixture(tmp_path, labels=False)
    original = serialize_molecule(record.structures.reactant)
    mol.GetConformer().SetAtomPosition(1, (2., 1., 0.))
    source = write_source(tmp_path, 'reactant', mol)
    change = request(record, {'ts_optimization': {'keywords': 'TightSCF'}})
    untouched = revise_record(record, change, plan_input_revision(record, change))
    assert serialize_molecule(untouched.structures.reactant) == original
    assert untouched.structures.product_to_reactant == (0, 1, 2)
    change = request(record, {'conformers': {'reactant': {'xyz_path': source['xyz_path']}}})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.stage == 'build'
    assert revised.structures.product_to_reactant is None
    assert revised.input.reaction.reaction_center == []
    assert revised.input.guess is None
    assert serialize_molecule(revised.attempt_history[-1].structures.reactant) == original


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize('relative_source', [False, True])
def test_repeated_method_revisions_retain_imported_source_binding(tmp_path, monkeypatch, relative_source):
    from cloudra.tools.core.molecule import serialize_molecule
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    from tests.test_ts_revision_identity import molecular_fixture
    record, _ = molecular_fixture(tmp_path)
    source = Path(record.input.conformers.reactant.xyz_path)
    cwd = tmp_path / 'service'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    if relative_source:
        record.input.conformers.reactant.xyz_path = 'reactant.xyz'
    original = serialize_molecule(record.structures.reactant)
    original_input = record.input.model_copy(deep=True)
    for method, basis in (('b97-3c', ''), ('b3lyp', 'def2svp')):
        change = request(record, {'ts_optimization': {'replace': {
            'engine': 'orca', 'method': method, 'basis_set': basis}}})
        receipt = plan_input_revision(record, change)
        record = revise_record(record, change, receipt)
        assert record.stage == 'submit'
        assert record.structures.product_to_reactant == (0, 1, 2)
        assert record.input.guess == original_input.guess
        assert serialize_molecule(record.structures.reactant) == original
    source.unlink()
    change = request(record, {'ts_optimization': {'keywords': 'TightSCF'}})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert serialize_molecule(revised.structures.reactant) == original


@pytest.mark.usefixtures("rdkit_chemistry")
def test_missing_external_source_can_be_explicitly_supplied_at_same_path(tmp_path):
    from cloudra.tools.core.ts_inputs import FileConformer
    from cloudra.tools.core.ts_process import TsBlocked
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    source = tmp_path / 'delayed.xyz'
    record = record_fixture(tmp_path, stage='build', blocked=TsBlocked(
        stage='build', failure_class='conformer_source_invalid', message='missing source',
        issues=[{'code': 'source_missing', 'role': 'reactant', 'field': 'conformers.reactant.xyz_path',
                 'path': str(source)}]))
    record.input.conformers.reactant = FileConformer(kind='file', xyz_path=str(source))
    source.write_text('2\nsupplied\nH 0 0 0\nH 0 0 .74\n')
    change = request(record, {'conformers': {'reactant': {'xyz_path': str(source)}}})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.stage == 'build'
    assert revised.structures.reactant is not None
    assert revised.structures.product_to_reactant is None
    assert revised.input.guess is None


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


def test_failed_scan_same_input_retry_keeps_native_input_job_and_history(tmp_path):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.tools.core.ts_process import TsBlocked, TsJobStep
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    db = ComputeDB(data_dir=tmp_path / 'ledger').init()
    old = tmp_path / 'failed.inp'
    old.write_text('accepted native input')
    failed = insert_compute_job(db, conversation_id='project', session_id='owner', path=str(old), state='failed', jobtype='orca', node_id='fixture')
    record = record_fixture(tmp_path, stage='guess', blocked=TsBlocked(stage='guess', failure_class='scan_job_failed', message='SHARK temporary directory failure'),
        scan_step=TsJobStep(purpose='scan', job_id=failed, input_path=str(old),state='failed'))
    change = request(record, {})
    with use_pipeline_database(db):
        revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.stage == 'guess' and revised.scan_step is None
    assert revised.attempt_history[-1].job_steps[0].job_id == failed
    assert revised.attempt_history[-1].blocked == record.blocked
    assert revised.terminal is None
    assert old.read_text() == 'accepted native input'
    assert record.scan_step.job_id == failed
    assert record.blocked.failure_class == 'scan_job_failed'
    assert record.attempt_history == []
    with db.connect() as con:
        assert con.execute('SELECT state FROM compute_jobs WHERE id=?',(failed,)).fetchone()[0] == 'failed'
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 1


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


def test_failed_scientific_check_can_retry_without_claiming_verification(tmp_path):
    from cloudra.tools.core.ts_process import TsJobStep, _record_candidate_failure
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    record = record_fixture(tmp_path, stage='refine')
    record.job_steps = [TsJobStep(purpose='frequency', job_id=7, state='done')]
    _record_candidate_failure(record, 'wrong_mode', record.job_steps[0], str(tmp_path/'freq.out'))
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    assert [ref.job_id for ref in receipt.invalidated] == [7]
    assert revised.job_steps == [] and revised.terminal is None
    assert revised.stage == 'refine'
    assert revised.failed_attempt is None
    assert revised.attempt_history[-1].failed_attempt['failure_class'] == 'wrong_mode'
    assert record.failed_attempt['failure_class'] == 'wrong_mode'


def test_repeated_input_repairs_preserve_history_without_an_intervention_cap(tmp_path):
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record

    record = record_fixture(tmp_path, intervention_count=2)
    for keywords in ('TightSCF', 'D3BJ TightSCF', 'D3BJ'):
        change = request(record, {'ts_optimization': {'keywords': keywords}})
        record = revise_record(record, change, plan_input_revision(record, change))
    assert record.intervention_count == 5
    assert len(record.attempt_history) == 3
    assert record.declaration_revision == 4
    assert record.terminal is None


@pytest.mark.parametrize('purpose,stage,restart', [('ts_opt','refine','submit'), ('frequency','verdict','refine')])
def test_same_input_retry_restarts_at_failed_job_producer(tmp_path, purpose, stage, restart):
    from cloudra.tools.core.ts_process import TsJobStep, _record_candidate_failure
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    record = record_fixture(tmp_path, stage=stage, terminal='candidate_only' if stage == 'verdict' else None)
    step = TsJobStep(purpose=purpose, job_id=7, state='failed')
    if purpose == 'scan':
        record.scan_step = step
    else:
        record.job_steps = [step]
    _record_candidate_failure(record, 'nonconvergence', step, str(tmp_path/'failed.out'))
    change = request(record, {})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.stage == restart
    assert revised.attempt_history[-1].job_steps[-1].job_id == 7
    assert revised.terminal is None
