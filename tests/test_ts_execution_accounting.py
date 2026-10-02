import json

import pytest

from cloudra.persistence.database import ComputeDB


def test_ts_current_record_has_no_time_estimate_contract(tmp_path):
    from cloudra.tools.core.ts_process import TsProcessRecord
    from tests.test_ts_stage_inputs import record_fixture
    record=record_fixture(tmp_path)
    assert 'compute_estimates' not in record.model_dump()
    assert 'exploration_budget' not in record.model_dump()
    with pytest.raises(ValueError):
        TsProcessRecord.model_validate(dict(record.model_dump(),compute_estimates={'scan':2}))


def test_ts_subjobs_admit_without_time_estimates_and_action_cap_remains(tmp_path, monkeypatch):
    from cloudra.runtime.chem_task import ChemTask
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.exploration_budget_store import ExplorationBudget, budget_usage, configure_budget
    from cloudra.services.ts_pipeline_store import create_process
    from cloudra.tools.core.ts_inputs import TsCalculation, TsExecutionLimits, XtbPathGuess
    from cloudra.tools.core.ts_process import _submit_step
    from tests.test_ts_pipeline_store import payload
    from tests.test_ts_stage_inputs import record_fixture
    record=record_fixture(tmp_path)
    record.input.execution.limits=TsExecutionLimits(source='explicit_user',max_compute_actions=2)
    record.input.conformers.reactant.optimization=TsCalculation(engine='xtb',method='GFN2-xTB',keywords='')
    record.input.guess=XtbPathGuess(kind='xtb_path',method='GFN2-xTB')
    db=ComputeDB().init()
    record.pipeline_id=create_process(db,request_key='accounting',payload=payload(workspace_dir=str(tmp_path),input=record.input.model_dump()))['process_id']
    configure_budget(db,process_id=record.pipeline_id,project_id='project',owner_id='owner',budget=ExplorationBudget(source='explicit_user',max_compute_actions=2))
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    for i, kind in enumerate(('xtb_hessian','xtb_gradient','xtb_gradient')):
        path=tmp_path/f'point-{i}.json'
        path.write_text(ChemTask(task=kind,reactant_xyz='1\nseed\nH 0 0 0\n',cpus=record.compute_cpus).model_dump_json())
        error,job=_submit_step(record,'candidate_evaluation',str(path),'chem_task',stage_key=f'point:{i}',action_kind='frequency' if i==0 else 'gradient')
        assert (not error and job>0) if i<2 else ('budget exhausted' in error and job==-1)
    assert budget_usage(db,record.pipeline_id).compute_actions==2
    assert budget_usage(db,record.pipeline_id).unknown_cpu_actions==2


def test_actual_usage_is_recorded_and_unknown_is_not_zero(tmp_path):
    from cloudra.tools.core.ts_state_view import build_process_view
    from tests.test_ts_stage_inputs import record_fixture
    jobs=[dict(job_id=1,state='done',start_timestamp=100,end_timestamp=190,req_cpus=4,req_memory_mb=1024),dict(job_id=2,state='ready',req_cpus=4)]
    view=build_process_view(record_fixture(tmp_path).model_dump(),jobs,can_write=False)
    assert view.usage['jobs'][0]['runtime_seconds']==90
    assert view.usage['jobs'][0]['allocated_cpu_hours']==0.1
    assert view.usage['jobs'][0]['measured_cpu_hours'] is None
    assert view.usage['jobs'][1]['allocated_cpu_hours'] is None


def test_reconcile_isolates_old_record_and_keeps_active_job_alive(tmp_path, monkeypatch):
    from cloudra.infra.flocks import locked
    from cloudra.services.ts_pipeline_store import create_process, get_process
    from cloudra.tools.core.ts_pipeline_driver import reconcile_processes
    from tests.test_ts_pipeline_driver import waiting_process
    from tests.test_ts_pipeline_store import payload
    db,new_id,job=waiting_process(tmp_path)
    old=create_process(db,request_key='old',payload=payload(workspace_dir=str(tmp_path)))['process_id']
    data=dict(get_process(db,new_id)['record'],format_version=2,pipeline_id=old,run_id='old')
    with db.connect() as con:
        con.execute("UPDATE ts_pipeline_processes SET record=?,status='waiting' WHERE process_id=?",(json.dumps(data),old))
    with locked(str(tmp_path/'qm.lock')):
        results=reconcile_processes(db,'project')
    assert {r['status'] for r in results}=={'isolated','waiting'}
    with db.connect() as con:
        assert con.execute('SELECT state FROM compute_jobs WHERE id=?',(job,)).fetchone()[0]=='ready'
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]==1
    assert get_process(db,old)['record']==data


pytestmark=pytest.mark.usefixtures('ts_producer_authority')
