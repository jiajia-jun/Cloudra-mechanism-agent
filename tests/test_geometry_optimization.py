import json
from pathlib import Path

import numpy as np
import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.runtime.chem_task import ChemTask, result_path
from cloudra.services.compute_admission import AdmissionOutcome
from cloudra.services.ts_pipeline_store import create_process
from cloudra.tools.core.conformer_catalog import content_digest
from cloudra.tools.core.constrained_optimization import OptimizationRequest
from cloudra.tools.core.ts_inputs import TsInput
from cloudra.tools.core.ts_process import TsProcessRecord


def setup_record(tmp_path, monkeypatch, budget=None):
    from cloudra.services.exploration_budget_store import configure_budget
    db = ComputeDB().init()
    from tests.test_ts_inputs import input_payload
    value = input_payload()
    value['reaction'].update(reactant_smiles='[H][H]', product_smiles='[H][H]', charge=0, atom_map=[0, 1])
    value['conformers']['reactant']['optimization'] = dict(engine='xtb', method='GFN2-xTB', keywords='')
    if budget:
        value['execution']['limits'] = dict(source=budget.source,max_compute_actions=budget.max_compute_actions,max_model_calls=budget.max_model_calls)
    inputs = TsInput.model_validate(value)
    payload = dict(project_id='project', owner_id='owner', workspace_dir=str(tmp_path), input=inputs.model_dump(mode='json'))
    pid = create_process(db, request_key='constrained', payload=payload)['process_id']
    record = TsProcessRecord(run_id='constrained', run_dir=str(tmp_path/'ts'), workspace_dir=str(tmp_path),
        owner_conversation_id='project', owner_session_id='owner', pipeline_id=pid, input=inputs)
    Path(record.run_dir).mkdir()
    if budget:
        configure_budget(db, process_id=pid, project_id='project', owner_id='owner', budget=budget)
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job', lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    request = OptimizationRequest(symbols=['H','H'], positions=[[0.,0.,0.],[1.5,0.,0.]], frozen_atoms=[0],
        distance_constraints=[dict(atoms=[0,1],min_ang=1.,max_ang=2.)])
    return db, record, request


def finish(db, step, *, failed=False):
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    task=ChemTask.model_validate_json(Path(step.input_path).read_text())
    xyz=Path(step.input_path).parent/'fixture.xyz'
    xyz.write_text(task.reactant_xyz)
    points=[p for _,p in read_xyz_atoms(str(xyz))]
    p=np.asarray(points)
    target=np.array([[0.,0.,0.],[1.2,0.,0.]])
    result=dict(returncode=1 if failed else 0,normal_termination=not failed,evaluation_valid=not failed,
        input_hash=content_digest(points),method_fingerprint='GFN2-xTB',symbols=['H','H'],
        positions=points,energy_hartree=float(np.sum((p-target)**2)/2),log_file=str(xyz))
    if task.task=='xtb_hessian':
        result['hessian_hartree_per_angstrom2']=np.eye(6).tolist()
    else:
        result['gradient_hartree_per_angstrom']=(p-target).tolist()
    Path(result_path(step.input_path)).write_text(json.dumps(dict(manifest_digest=content_digest(task.model_dump()),process_exit_code=result['returncode'],result=result)))
    with db.connect() as con:
        con.execute('UPDATE compute_jobs SET state=? WHERE id=?',('failed' if failed else 'done',step.job_id))


def test_durable_constrained_queue_resumes_and_charges_each_point_once(tmp_path, monkeypatch):
    from cloudra.services.exploration_budget_store import ExplorationBudget, budget_usage
    from cloudra.tools.core.geometry_optimization import advance_optimization
    db,record,request=setup_record(tmp_path,monkeypatch,ExplorationBudget(source='explicit_user',max_compute_actions=20))
    result=None
    for _ in range(30):
        result=advance_optimization(record,'selected',request)
        if result is not None:
            break
        first=record.job_steps[-1]
        record=TsProcessRecord.model_validate_json(record.model_dump_json())
        assert advance_optimization(record,'selected',request) is None
        assert record.job_steps[-1].job_id==first.job_id
        finish(db,first)
    assert result and result['optimization_converged']
    assert result['positions'][1][0]==pytest.approx(1.2,abs=.001)
    assert result['positions'][0]==[0.,0.,0.]
    with db.connect() as con:
        count=con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]
    assert count==len(result['job_ids'])==budget_usage(db,record.pipeline_id).compute_actions
    assert count>=3
    assert advance_optimization(record,'selected',request)==result


@pytest.mark.parametrize('failure',['cap','engine'])
def test_constrained_queue_blocks_without_cancel_or_false_convergence(tmp_path,monkeypatch,failure):
    from cloudra.services.exploration_budget_store import ExplorationBudget
    from cloudra.tools.core.geometry_optimization import advance_optimization
    db,record,request=setup_record(tmp_path,monkeypatch,ExplorationBudget(source='explicit_user',max_compute_actions=1))
    assert advance_optimization(record,'selected',request) is None
    step=record.job_steps[-1]
    finish(db,step,failed=failure=='engine')
    assert advance_optimization(record,'selected',request) is None
    assert record.blocked
    assert not record.waiting_for
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]==1
        assert con.execute('SELECT state FROM compute_jobs').fetchone()[0]==('failed' if failure=='engine' else 'done')


@pytest.mark.parametrize('boundary',['ready','completed','next_point'])
def test_constrained_crash_recovery_preserves_one_job_per_point(tmp_path,monkeypatch,boundary):
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.geometry_optimization import advance_optimization
    db,record,request=setup_record(tmp_path,monkeypatch)
    original_submit=ts_process._submit_step
    original_save=ts_process.save_record
    if boundary=='ready':
        def submit(*args,**kwargs):
            original_submit(*args,**kwargs)
            raise RuntimeError('crash after READY')
        monkeypatch.setattr(ts_process,'_submit_step',submit)
    else:
        advance_optimization(record,'selected',request)
        finish(db,record.job_steps[-1])
        if boundary=='next_point':
            advance_optimization(record,'selected',request)
            finish(db,record.job_steps[-1])
        def save(current):
            states=[c.state for c in current.optimization_checkpoints.values()]
            if not current.waiting_for and any(s.status=='need_gradient' for s in states):
                if boundary=='next_point':
                    original_save(current)
                raise RuntimeError('crash consuming completed derivative')
            return original_save(current)
        monkeypatch.setattr(ts_process,'save_record',save)
    with pytest.raises(RuntimeError,match='crash'):
        advance_optimization(record,'selected',request)
    recovered=TsProcessRecord.model_validate(get_process(db,record.pipeline_id)['record'])
    monkeypatch.setattr(ts_process,'save_record',original_save)
    monkeypatch.setattr(ts_process,'_submit_step',original_submit)
    advance_optimization(recovered,'selected',request)
    advance_optimization(recovered,'selected',request)
    with db.connect() as con:
        rows=con.execute('SELECT path FROM compute_jobs').fetchall()
    assert len(rows)==len(set(p for p, in rows))
    assert len(rows)=={'ready':1,'completed':2,'next_point':3}[boundary]


def test_budget_revision_reuses_existing_derivative_and_numeric_state(tmp_path,monkeypatch):
    from cloudra.tools.core.geometry_optimization import advance_optimization
    db,record,request=setup_record(tmp_path,monkeypatch)
    assert advance_optimization(record,'selected',request) is None
    job=record.job_steps[-1].job_id
    # Declaration bookkeeping can change for a budget-only revision; chemistry
    # and this accepted job do not change. No compute job may be cancelled.
    record.declaration_revision+=1
    with db.connect() as con:
        con.execute('UPDATE ts_pipeline_processes SET declaration_revision=? WHERE process_id=?',(record.declaration_revision,record.pipeline_id))
    assert advance_optimization(record,'selected',request) is None
    assert record.job_steps[-1].job_id==job
    assert len(record.optimization_checkpoints)==1
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]==1


def test_numeric_failure_records_candidate_attempt_before_blocking(tmp_path,monkeypatch):
    from cloudra.tools.core import geometry_optimization, ts_process
    db,record,request=setup_record(tmp_path,monkeypatch)
    calls=[]
    monkeypatch.setattr(ts_process,'_record_candidate_failure',lambda *args:calls.append(args))
    geometry_optimization.advance_optimization(record,'selected',request)
    finish(db,record.job_steps[-1])
    geometry_optimization.advance_optimization(record,'selected',request)
    finish(db,record.job_steps[-1])
    def blocked(state,evaluation):
        result=state.model_dump(mode='json')
        result.update(status='blocked',error='singular active-distance back-transform')
        return result
    monkeypatch.setattr(geometry_optimization,'step_constrained_state',blocked)
    geometry_optimization.advance_optimization(record,'selected',request)
    assert record.blocked and calls
    assert calls[-1][1]=='geometry'
    assert calls[-1][2].job_id==record.job_steps[-1].job_id


pytestmark = pytest.mark.usefixtures("ts_producer_authority")


def test_failed_constrained_attempt_can_retry_without_repair_evidence(tmp_path, monkeypatch):
    from cloudra.tools.core.geometry_optimization import advance_optimization
    from cloudra.tools.core.ts_inputs import TsResumeRequest
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    db, record, calculation = setup_record(tmp_path, monkeypatch)
    record.stage = 'build'
    assert advance_optimization(record, 'selected', calculation) is None
    old_job = record.job_steps[-1].job_id
    finish(db, record.job_steps[-1], failed=True)
    assert advance_optimization(record, 'selected', calculation) is None
    assert record.blocked is not None
    request = TsResumeRequest(reason='retry failed derivative', request_key='retry', expected_revision=record.revision)
    receipt = plan_input_revision(record, request)
    revised = revise_record(record, request, receipt)
    from cloudra.services.ts_pipeline_store import commit_input_revision
    commit_input_revision(db, process_id=record.pipeline_id, request=request,
                          record=revised.model_dump(mode='json'), receipt=receipt)
    assert revised.optimization_checkpoints == {}
    assert revised.terminal is None
    assert advance_optimization(revised, 'selected', calculation) is None
    assert revised.job_steps[-1].job_id != old_job
    with db.connect() as con:
        assert con.execute('SELECT state FROM compute_jobs WHERE id=?', (old_job,)).fetchone()[0] == 'failed'
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 2


@pytest.mark.parametrize('electronic_character,multiplicity', [('closed_shell', 1), ('open_shell', 3)])
def test_constrained_derivative_manifests_retain_declared_electronic_character(
    tmp_path, monkeypatch, electronic_character, multiplicity,
):
    from cloudra.tools.core.geometry_optimization import advance_optimization

    db, record, request = setup_record(tmp_path, monkeypatch)
    record.input.reaction.electronic_character = electronic_character
    record.input.reaction.multiplicity = multiplicity
    assert advance_optimization(record, 'selected', request) is None
    assert record.blocked is None
    hessian = record.job_steps[-1]
    task = ChemTask.model_validate_json(Path(hessian.input_path).read_text())
    assert task.task == 'xtb_hessian'
    assert task.electronic_character == electronic_character
    assert task.multiplicity == multiplicity
    finish(db, hessian)
    assert advance_optimization(record, 'selected', request) is None
    assert record.blocked is None
    gradient = ChemTask.model_validate_json(Path(record.job_steps[-1].input_path).read_text())
    assert gradient.task == 'xtb_gradient'
    assert gradient.electronic_character == electronic_character
    assert gradient.multiplicity == multiplicity


def test_constrained_cache_does_not_reuse_another_electronic_character(tmp_path, monkeypatch):
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.geometry_optimization import advance_optimization

    _, record, request = setup_record(tmp_path, monkeypatch)
    monkeypatch.setattr(ts_process, '_submit_step', lambda *_, **__: ('', 601))
    monkeypatch.setattr(ts_process, '_read_job_state', lambda *_: 'ready')
    assert advance_optimization(record, 'selected', request) is None
    key, checkpoint = next(iter(record.optimization_checkpoints.items()))
    record.optimization_checkpoints[key] = checkpoint.model_copy(update={
        'result': {'source_state': 'unspecified electronic character'}})
    record.input.reaction.electronic_character = 'closed_shell'
    assert advance_optimization(record, 'selected', request) is None
    assert len(record.optimization_checkpoints) == 2
