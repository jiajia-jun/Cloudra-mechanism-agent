"""Independent-review regressions at the TS scientific and retry boundaries."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.test_ts_stage_inputs import record_fixture

pytestmark = pytest.mark.usefixtures('ts_producer_authority')


@pytest.mark.parametrize('field', ['orca_blocks'])
def test_irc_hessian_requires_complete_scientific_settings(tmp_path, field):
    from cloudra.tools.core.ts_inputs import TsCalculation
    from cloudra.tools.core.ts_process import TsJobStep, _write_irc_input
    record = record_fixture(tmp_path)
    old = TsCalculation(engine='orca', method='HF/STO-3G', keywords='', **{field: '%cpcm epsilon 20 end'})
    new = old.model_copy(update={field: '%cpcm epsilon 80 end'})
    record.input.verification.frequency = old
    record.input.verification.irc = new
    freq = tmp_path/'frequency.inp'
    freq.write_text('! Freq HF STO-3G')
    freq.with_suffix('.hess').write_text('$hessian')
    (tmp_path/'optimized.xyz').write_text('2\nTS\nH 0 0 0\nH 0 0 .74\n')
    record.job_steps = [TsJobStep(purpose='frequency',job_id=1,state='done',input_path=str(freq),actual_calculation=old)]
    folder=tmp_path/'irc'
    folder.mkdir()
    error,path = _write_irc_input(record,str(folder))
    assert not error
    assert 'InitHess calc_numfreq' in Path(path).read_text()
    assert 'InitHess read' not in Path(path).read_text()


def test_mol_cannot_mask_dissociated_xyz_before_conformer_optimization(tmp_path, monkeypatch):
    from rdkit import Chem

    from cloudra.tools.core.ts_inputs import FileConformer, TsCalculation
    from cloudra.tools.core.ts_process import _build
    from tests.test_ts_input_evidence import concrete
    record=record_fixture(tmp_path)
    record.input.reaction.reactant_smiles=record.input.reaction.product_smiles='O'
    record.input.conformers.guidance.ring_order=[]
    graph=tmp_path/'water.mol'
    graph.write_text(concrete('O'))
    xyz=tmp_path/'water.xyz'
    xyz.write_text('3\ndissociated\nO 0 0 0\nH 30 0 0\nH 0 30 0\n')
    record.input.conformers.reactant=FileConformer(kind='file',xyz_path=str(xyz),mol_path=str(graph),optimization=TsCalculation(engine='xtb',method='GFN2-xTB',keywords=''))
    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step',lambda *_:pytest.fail('Invalid actual geometry cannot spend compute'))
    _build(record)
    assert record.blocked.failure_class=='input_identity_unconfirmed'
    assert record.job_steps==[]
    assert Chem.MolFromMolFile(str(graph)) is not None


@pytest.mark.parametrize('key', [None, '', '   '])
def test_prepare_requires_nonblank_stable_request_key(tmp_path, key):
    from cloudra.tools.Chemtool.ts_search_process import TsPrepare_input_schema
    from cloudra.tools.core.ts_process import TsStartRequest
    record=record_fixture(tmp_path)
    payload={'input':record.input}
    if key is not None:
        payload['request_key']=key
    with pytest.raises(ValidationError):
        TsPrepare_input_schema(**payload)
    with pytest.raises(ValidationError):
        TsStartRequest(**payload,workspace_dir=str(tmp_path))


@pytest.mark.parametrize('engine', ['orca','gaussian'])
def test_scan_preserves_declared_native_scientific_settings(tmp_path, monkeypatch, engine):
    from cloudra.tools.core.calculation_intent import compare_calculation_input
    from cloudra.tools.core.ts_inputs import ScanGuess
    from cloudra.tools.core.ts_process import _guess_scan
    xyz=tmp_path/'seed.xyz'
    xyz.write_text('2\nseed\nH 0 0 0\nH 0 0 .74\n')
    record=record_fixture(tmp_path)
    calculation={'engine':engine,'method':'HF/STO-3G','keywords':'',
                 'orca_blocks':'%cpcm epsilon 20 end' if engine=='orca' else None,
                 'end_setting':'' if engine=='orca' else 'C 0\nSTO-3G\n****'}
    record.input.guess=ScanGuess(kind='scan',calculation=calculation,scans=[{'atoms':[0,1],'scan_end':1.5,'scan_steps':3}])
    monkeypatch.setattr('cloudra.tools.core.ts_process._read_built_xyz',lambda *_:(['H','H'],[[0,0,0],[0,0,.74]],str(xyz),''))
    captured=[]
    def submit(state,purpose,path,program):
        captured.append(Path(path).read_text())
        return '',42
    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step',submit)
    _guess_scan(record)
    assert captured and record.waiting_for=='job:42'
    assert calculation['end_setting'] in captured[0]
    if engine=='orca':
        assert calculation['orca_blocks'] in captured[0]
        assert not compare_calculation_input(captured[0],record.input.guess.calculation.model_dump(),charge=0,multiplicity=1)


def recovery_fixture(tmp_path, purpose='frequency', failure='wrong_mode'):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.tools.core.ts_inputs import TsCalculation, TsResumeRequest
    from cloudra.tools.core.ts_process import TsJobStep, _record_candidate_failure
    db=ComputeDB(data_dir=tmp_path/'ledger').init()
    record=record_fixture(tmp_path)
    old=tmp_path/'failed.inp'
    old.write_text('! Freq HF STO-3G\n* xyz 0 1\nH 0 0 0\nH 0 0 .74\n*\n')
    job=insert_compute_job(db,conversation_id='project',session_id='owner',path=str(old),state='done',jobtype='orca',node_id='fixture')
    step=TsJobStep(purpose=purpose,job_id=job,state='done',input_path=str(old),actual_calculation=TsCalculation(engine='orca',method='HF/STO-3G',keywords=''))
    record.job_steps=[step]
    _record_candidate_failure(record,failure,step,str(old.with_suffix('.out')))
    record.input.verification.frequency=step.actual_calculation
    def request(changes,refs):
        return TsResumeRequest(reason='bound repair',request_key='repair',expected_revision=0,changes=changes,recovery={'failed_attempt':record.failed_attempt['attempt_id'],'evidence_refs':[str(p) for p in refs]})
    return db,record,old,request


@pytest.mark.parametrize('log_text', ['', 'ORCA TERMINATED NORMALLY\nVIBRATIONAL FREQUENCIES\n0: 100.0 cm**-1\n'])
def test_same_bytes_done_job_cannot_clear_wrong_mode(tmp_path, log_text):
    from cloudra.infra.compute_utils import resolve_log_path
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.tools.core.ts_revision import validate_recovery
    db,record,old,request=recovery_fixture(tmp_path)
    repaired=tmp_path/'repaired.inp'
    repaired.write_bytes(old.read_bytes())
    job=insert_compute_job(db,conversation_id='project',session_id='owner',path=str(repaired),state='done',jobtype='orca',node_id='fixture')
    log=Path(resolve_log_path(str(repaired),job_type='orca',task_id=job))
    log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text(log_text)
    with use_pipeline_database(db),pytest.raises(ValueError,match='recovery evidence'):
        validate_recovery(record,request({},[log]))


@pytest.mark.parametrize('route', ['provided','xtb_path'])
def test_failed_scan_can_change_route_with_bound_new_route_artifacts(tmp_path,route):
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.tools.core.ts_process import TsBlocked
    from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
    db,record,old,request=recovery_fixture(tmp_path,purpose='scan',failure='scan_no_candidate')
    record.scan_step=record.job_steps.pop()
    record.stage='guess'
    record.blocked=TsBlocked(stage='guess',failure_class='scan_no_candidate',message='No internal peak')
    seed=tmp_path/'seed.xyz'
    seed.write_text('3\nwater\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n')
    record.input.reaction.reactant_smiles=record.input.reaction.product_smiles='O'
    record.current_seed_xyz_path=record.product_seed_xyz_path=str(seed)
    record.input.reaction.atom_map=[0,1,2]
    old.with_suffix('.out').write_text('bound old attempt evidence')
    change={'kind':'provided','xyz_path':str(seed),'evidence_refs':[str(old.with_suffix('.out'))]} if route=='provided' else {'kind':'xtb_path','method':'GFN2-xTB'}
    req=request({'guess':change},[old.with_suffix('.out'),seed])
    before=record.model_dump()
    files=set(tmp_path.rglob('*'))
    with use_pipeline_database(db):
        receipt=plan_input_revision(record,req)
        assert record.model_dump()==before
        assert set(tmp_path.rglob('*'))==files
        revised=revise_record(record,req,receipt)
    assert revised.run_id==record.run_id and revised.scan_step is None
    assert revised.input.guess.kind==route
    assert revised.attempt_history[-1].failed_attempt['failure_class']=='scan_no_candidate'


def test_catalog_source_binds_stable_atom_table_before_assemble(tmp_path):
    import json

    from cloudra.persistence.database import ComputeDB
    from cloudra.services.conformer_store import list_candidates
    from cloudra.tools.core.conformer_catalog import Qualification
    from cloudra.tools.core.ts_candidate_pipeline import use_catalog_source
    from cloudra.tools.core.ts_inputs import CatalogConformer
    from cloudra.tools.core.ts_process import _assemble
    from tests.test_ts_selected_optimizer import catalog_seed
    source,_=catalog_seed(tmp_path,Qualification(status='qualified'))
    db=ComputeDB()
    selected=list_candidates(db,'cat',project_id='project',owner_id='owner')[0]
    record=record_fixture(tmp_path)
    record.input.conformers.guidance.ring_order=[]
    record.input.reaction.reaction_center=[(0,1)]
    use_catalog_source(record,CatalogConformer(**source),'reactant')
    _assemble(record)
    assert record.blocked is None
    table=json.loads(Path(record.current_reactant_prepared_path).read_text())
    assert [a['stable_atom_id'] for a in table['atom_identities']]==selected.atom_ids
    assert [a['symbol'] for a in table['atom_identities']]==selected.symbols
    assert table['candidate_id']==selected.candidate_id


def test_missing_atom_map_prompt_uses_the_grouped_structure_numbering(tmp_path):
    from cloudra.tools.core.ts_process import _map
    record=record_fixture(tmp_path)
    record.input.reaction.atom_map=[]
    _map(record)
    assert '1-based' in record.blocked.message
    assert 'ORCA 0-based' not in record.blocked.message


@pytest.mark.parametrize('engine', ['orca', 'gaussian'])
def test_repaired_frequency_requires_valid_result_and_uses_original_input_engine(tmp_path, monkeypatch, engine):
    from cloudra.infra.compute_utils import resolve_log_path
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.tools.core.ts_revision import validate_recovery
    db,record,old,request=recovery_fixture(tmp_path)
    repaired=tmp_path/('repaired.inp' if engine=='orca' else 'repaired.gjf')
    repaired.write_bytes(old.read_bytes()) if engine=='orca' else repaired.write_text('#p HF/STO-3G Freq\n\nrepair\n\n0 1\nH 0 0 0\nH 0 0 .74\n\n')
    job=insert_compute_job(db,conversation_id='project',session_id='owner',path=str(repaired),state='done',jobtype=engine,node_id='fixture')
    log=Path(resolve_log_path(str(repaired),job_type=engine,task_id=job))
    log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text('ORCA TERMINATED NORMALLY' if engine=='orca' else 'Normal termination of Gaussian 16')
    monkeypatch.setattr('cloudra.dag.evidence_ingest._extract_qm_log',lambda *_:(True,engine,[-300.,100.],[-300.],None,None))
    req=request({'verification':{'frequency':{'engine':engine,'method':'HF/STO-3G','keywords':''}}},[log])
    with use_pipeline_database(db):
        validate_recovery(record,req)


def test_route_change_rejects_unrelated_failure_provenance(tmp_path):
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.tools.core.ts_revision import validate_recovery
    db,record,old,request=recovery_fixture(tmp_path,purpose='scan',failure='scan_no_candidate')
    record.scan_step=record.job_steps.pop()
    seed=tmp_path/'candidate.xyz'
    seed.write_text('2\ncandidate\nH 0 0 0\nH 0 0 .74\n')
    unrelated=tmp_path/'unrelated.txt'
    unrelated.write_text('claim of repair')
    req=request({'guess':{'kind':'provided','xyz_path':str(seed),'evidence_refs':[str(unrelated)]}},[seed,unrelated])
    with use_pipeline_database(db),pytest.raises(ValueError,match='recovery evidence'):
        validate_recovery(record,req)
