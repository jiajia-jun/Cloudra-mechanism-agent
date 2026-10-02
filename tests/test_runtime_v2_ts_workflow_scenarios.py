"""Zero-key Agent scenarios exercise the real grouped TS tool/driver boundary."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.schemas import MethodPolicy
from cloudra.services.ts_pipeline_context import use_runtime_authority
from tests.agent_scenarios import TS_SCENARIOS, ScenarioHarness, ScriptedProvider, Step


def water_input(tmp_path, *, scan=False):
    from cloudra.tools.core.ts_inputs import FileConformer, ProvidedGuess, ScanGuess
    from tests.ts_fixtures import calculation_input
    seed=tmp_path/'water.xyz'
    seed.write_text('3\nWater seed\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n')
    evidence=tmp_path/'candidate.log'
    evidence.write_text('Explicit candidate provenance')
    inputs=calculation_input(reactant_smiles='O',product_smiles='O',method='HF/STO-3G',atom_map=[0,1,2])
    inputs.conformers.reactant=inputs.conformers.product=FileConformer(kind='file',xyz_path=str(seed))
    inputs.guess=ScanGuess(kind='scan',calculation={'engine':'orca','method':'HF/STO-3G','keywords':''},scans=[{'atoms':[0,1],'scan_start':1.,'scan_end':2.,'scan_steps':3}]) if scan else ProvidedGuess(kind='provided',xyz_path=str(seed),evidence_refs=[str(evidence)])
    data=inputs.model_dump(mode='json')
    data['reaction']['atom_map']=[1,2,3]
    return data


class StateProvider(ScriptedProvider):
    def __init__(self, workspace, steps, callback=None):
        super().__init__(by_role={'small_mol':steps})
        self.workspace, self.callback = workspace, callback
        self.harness = None
        self.records=[]

    async def complete(self,*args,**kwargs):
        if self.callback and (self.workspace/'ts/ts_0001/process.json').exists():
            with use_runtime_authority(self.harness.core):
                await asyncio.to_thread(self.callback,self)
        return await super().complete(*args,**kwargs)


@pytest.mark.asyncio
async def test_ts_prepare_once_auto_complete(tmp_path,monkeypatch):
    assert TS_SCENARIOS[0]=='ts_prepare_once_auto_complete'
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core import ts_process as process
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    payload=water_input(tmp_path)
    seed=tmp_path/'water.xyz'
    def writer(record,directory,role=None,task=None):
        purpose='frequency' if role is None else role+'_'+task
        path=Path(directory)/(purpose+'.inp')
        path.write_text('! HF STO-3G '+('Freq' if purpose.endswith('frequency') else 'Opt')+'\n* xyz 0 1\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n*\n')
        (Path(directory)/'optimized.xyz').write_text(seed.read_text())
        return '',str(path)
    monkeypatch.setattr(process,'_write_frequency_input',writer)
    monkeypatch.setattr(process,'_write_endpoint_input',writer)
    monkeypatch.setattr(process,'_validated_endpoint_minimum',lambda *_: ((['O','H','H'],[[0,0,0],[.96,0,0],[-.24,.93,0]]),''))
    monkeypatch.setattr('cloudra.dag.evidence_ingest.snapshot_evidence_file',lambda *_,**__: SimpleNamespace(frequencies=[-100.,200.],imaginary_frequencies=[-100.]))
    def complete(provider):
        record=process.load_record(str(tmp_path),'ts_0001')
        while record.waiting_for:
            job=int(record.waiting_for.partition(':')[2])
            step=next(s for s in record.job_steps if s.job_id==job)
            log=Path(process._refinement_log_path(record,step))
            log.parent.mkdir(parents=True,exist_ok=True)
            log.write_text('ORCA TERMINATED NORMALLY\n')
            with ComputeDB().connect() as con:
                con.execute("UPDATE compute_jobs SET state='done' WHERE id=?",(job,))
            state=handle_process_job_terminal(ComputeDB(),job)
            assert handle_process_job_terminal(ComputeDB(),job)['record']==state['record']
            record=process.TsProcessRecord.model_validate(state['record'])
        provider.records.append(record)
    provider=StateProvider(tmp_path,[Step(tools=[('ts_prepare',{'input':payload,'request_key':'one-path'})]),Step(stop=True)],complete)
    harness=await ScenarioHarness.start(tmp_path,workspace_dir=tmp_path,provider=provider)
    provider.harness=harness
    harness.project.settings.method_policy=MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent=await harness.spawn('small_mol',protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(e['tool_name'],e['is_success']) for e in harness.tool_events(agent)]==[('ts_prepare',True)],harness.describe(agent)
        record=provider.records[-1]
        assert record.terminal=='candidate_only' and record.intervention_count==0
        assert record.run_id=='ts_0001' and len(record.job_steps)==7
    finally:
        await harness.aclose()


def _script_compute(monkeypatch, first_scan='peak'):
    """Fake engine artifacts/admission, retaining job binding, writers, parser and driver."""
    from pathlib import Path

    import cloudra.tools.core.ts_process as process
    from cloudra.services.compute_admission import AdmissionOutcome

    submissions = []
    submit_step = process._submit_step
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job', lambda **_:
                        AdmissionOutcome(ok=True, node_id='fixture', scheduler='local'))

    def submit(record, purpose, input_path, job_type, **kwargs):
        error, job_id = submit_step(record, purpose, input_path, job_type, **kwargs)
        assert error == ''
        submissions.append({'purpose': purpose, 'path': input_path, 'id': job_id,
                            'input': Path(input_path).read_text()})
        if purpose == 'scan':
            outcome = first_scan if len(submissions) == 1 else 'peak'
            if outcome != 'missing_log':
                stem = Path(input_path).with_suffix('')
                energies = [-1., -1.1, -1.2] if outcome == 'no_peak' else [-1., -.9, -1.]
                stem.with_suffix('.relaxscanact.dat').write_text(''.join(
                    f'{distance} {energy}\n' for distance, energy in zip([1., 1.5, 2.], energies)))
                for i, distance in enumerate([1., 1.5, 2.], start=1):
                    geometry = (f'3\nscan\nO 0 0 0\nH {distance} 0 0\nH 0 1 0\n'
                                if outcome != 'wrong_atoms' else f'3\nwrong\nHe 0 0 0\nH {distance} 0 0\nH 0 1 0\n')
                    Path(str(stem) + f'.{i:03d}.xyz').write_text(geometry)
        return '', job_id
    monkeypatch.setattr(process, '_submit_step', submit)
    monkeypatch.setattr(process, '_refinement_log_path', lambda _record, step:
                        str(Path(step.input_path).with_suffix('.out')))
    return submissions


@pytest.mark.asyncio
async def test_ts_failed_scan_repair_same_run(tmp_path,monkeypatch):
    assert TS_SCENARIOS[1]=='ts_failed_scan_repair_same_run'
    from cloudra.infra.compute_utils import resolve_log_path
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.tools.core import ts_process as process
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal
    submissions=_script_compute(monkeypatch,first_scan='missing_log')
    payload=water_input(tmp_path,scan=True)
    def complete(provider):
        record=process.load_record(str(tmp_path),'ts_0001')
        if record.scan_step and record.waiting_for==f'job:{record.scan_step.job_id}':
            with ComputeDB().connect() as con:
                con.execute("UPDATE compute_jobs SET state='done' WHERE id=?",(record.scan_step.job_id,))
            record=process.TsProcessRecord.model_validate(handle_process_job_terminal(ComputeDB(),record.scan_step.job_id)['record'])
        provider.records.append(record)
        if record.failed_attempt and record.declaration_revision==1:
            repair=tmp_path/'repaired.inp'
            repair.write_bytes(Path(record.scan_step.input_path).read_bytes())
            job=insert_compute_job(ComputeDB(),conversation_id=record.owner_conversation_id,session_id=record.owner_session_id,path=str(repair),state='done',jobtype='orca',node_id='fixture')
            log=Path(resolve_log_path(str(repair),job_type='orca',task_id=job))
            log.parent.mkdir(parents=True,exist_ok=True)
            log.write_text('ORCA TERMINATED NORMALLY\n')
            provider._scripts['small_mol'][0].tools=[('ts_resume',{'run_id':record.run_id,'reason':'native same-input execution confirms environment repair','request_key':'repair','expected_revision':record.revision,'recovery':{'failed_attempt':record.failed_attempt['attempt_id'],'evidence_refs':[str(log)]}})]
    provider=StateProvider(tmp_path,[Step(tools=[('ts_prepare',{'input':payload,'request_key':'scan-path'})]),Step(),Step(stop=True)],complete)
    harness=await ScenarioHarness.start(tmp_path,workspace_dir=tmp_path,provider=provider)
    provider.harness=harness
    harness.project.settings.method_policy=MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent=await harness.spawn('small_mol',protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(e['tool_name'],e['is_success']) for e in harness.tool_events(agent)]==[('ts_prepare',True),('ts_resume',True)],harness.describe(agent)
        current=provider.records[-1]
        assert current.run_id=='ts_0001' and current.intervention_count==1
        assert current.attempt_history[-1].failed_attempt['failure_class']=='scan_parse_failed'
        assert [s['purpose'] for s in submissions]==['scan','scan','ts_opt']
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_ts_readonly_inspection(tmp_path):
    assert TS_SCENARIOS[2]=='ts_readonly_inspection'
    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.core.ts_process import load_record
    inputs=water_input(tmp_path)
    inputs['conformers']={}
    provider=ScriptedProvider(by_role={'small_mol':[Step(tools=[('ts_prepare',{'input':inputs,'request_key':'blocked'})]),Step(stop=True)],
        'explorer':[Step(tools=[('ts_inspect',{'run_id':'ts_0001'})]),Step(tools=[('ts_prepare',{'input':inputs,'request_key':'readonly'})]),Step(stop=True)]})
    harness=await ScenarioHarness.start(tmp_path,workspace_dir=tmp_path,provider=provider)
    try:
        owner=await harness.spawn('small_mol',protocol='traditional')
        await harness.wait_terminal(owner)
        before=await asyncio.to_thread(load_record,str(tmp_path),'ts_0001')
        reviewer=await harness.spawn('explorer',protocol='traditional')
        await harness.wait_terminal(reviewer)
        assert [(e['tool_name'],e['is_success']) for e in harness.tool_events(reviewer)]==[('ts_inspect',True),('ts_prepare',False)],harness.describe(reviewer)
        after=await asyncio.to_thread(load_record,str(tmp_path),'ts_0001')
        assert after.model_dump()==before.model_dump()
        def jobs():
            with ComputeDB().connect() as con:
                return con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]
        assert await asyncio.to_thread(jobs)==0
    finally:
        await harness.aclose()
