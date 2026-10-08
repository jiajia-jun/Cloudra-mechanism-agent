"""Explicit catalog seeds use only their declared optimizer; never auto-select."""
import json
from pathlib import Path

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.tools.core import ts_process

pytestmark = pytest.mark.usefixtures('ts_producer_authority')


def catalog_seed(tmp_path, qualification=None):
    from cloudra.services.conformer_store import put_candidate, put_region_snapshot
    from cloudra.tools.core.conformer_catalog import CandidateRecord
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates
    xyz = tmp_path/'water.xyz'
    xyz.write_text('3\nWater\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n')
    candidate = CandidateRecord(catalog_id='cat',project_id='project',owner_id='owner',species_key='water',
        atom_ids=['O1','H1','H2'],fragment_ids=['f','f','f'],symbols=['O','H','H'],
        positions=[[0,0,0],[0.96,0,0],[-0.24,0.93,0]],geometry_ref=str(xyz),generator='fixture',seed=42, **({'qualification':qualification} if qualification else {}))
    db=ComputeDB().init()
    put_candidate(db,candidate)
    snapshot=partition_candidates([candidate],RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance',stable_atom_ids=['O1','H1'])]))
    put_region_snapshot(db,snapshot,project_id='project',owner_id='owner')
    return dict(kind='catalog',catalog_id='cat',partition_revision=snapshot.revision,candidate_id=candidate.candidate_id), xyz


@pytest.mark.usefixtures("rdkit_chemistry")
def test_catalog_prepare_requires_explicit_member_optimizer_and_deduplicates(tmp_path,monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core.ts_inputs import CatalogConformer, FileConformer
    from tests.ts_fixtures import calculation_input
    source, xyz=catalog_seed(tmp_path)
    inputs=calculation_input(reactant_smiles='O',product_smiles='O',method='b3lyp/def2svp',atom_map=[0,1,2])
    inputs.conformers.reactant=CatalogConformer(**source)
    inputs.conformers.product=FileConformer(kind='file',xyz_path=str(xyz))
    first=ts_process.start(ts_process.TsStartRequest(input=inputs,workspace_dir=str(tmp_path),owner_conversation_id='project',owner_session_id='owner',request_key='unqualified'))
    assert first.blocked.needs==['conformers.reactant.optimization']
    with ComputeDB().connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]==0
    inputs.conformers.reactant=CatalogConformer(**source,optimization={'engine':'xtb','method':'GFN2-xTB','keywords':''})
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    request=ts_process.TsStartRequest(input=inputs,workspace_dir=str(tmp_path),owner_conversation_id='project',owner_session_id='owner',request_key='explicit-selected')
    first,second=ts_process.start(request),ts_process.start(request)
    assert first.waiting_for==second.waiting_for and first.waiting_for
    assert first.selected_candidate_id==source['candidate_id']
    with ComputeDB().connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]==1


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize("engine,suffix", [("gaussian", ".gjf"), ("orca", ".inp")])
def test_native_selected_seed_writes_and_submits_declared_input_once(tmp_path, monkeypatch, engine, suffix):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core.calculation_intent import inspect_input
    from cloudra.tools.core.ts_inputs import CatalogConformer, FileConformer
    from tests.ts_fixtures import calculation_input

    source, xyz = catalog_seed(tmp_path)
    inputs = calculation_input(reactant_smiles='O', product_smiles='O', method='b3lyp/def2svp', atom_map=[0, 1, 2])
    inputs.conformers.reactant = CatalogConformer(**source, optimization={
        'engine': engine, 'method': 'b3lyp/def2svp', 'keywords': '',
    })
    inputs.conformers.product = FileConformer(kind='file', xyz_path=str(xyz))
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
                        lambda **_: AdmissionOutcome(ok=True, node_id='fixture', scheduler='local'))
    request = ts_process.TsStartRequest(input=inputs, workspace_dir=str(tmp_path),
        owner_conversation_id='project', owner_session_id='owner', request_key='native-selected')
    first, second = ts_process.start(request), ts_process.start(request)
    assert first.waiting_for == second.waiting_for and first.waiting_for
    step = first.job_steps[-1]
    assert step.purpose == 'candidate_opt'
    assert Path(step.input_path).suffix == suffix
    assert inspect_input(Path(step.input_path).read_text(), engine=engine).tasks == {'minimum_opt'}
    with ComputeDB().connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 1


@pytest.mark.usefixtures("rdkit_chemistry")
def test_completed_explicit_seed_opt_advances_other_seed_once(tmp_path,monkeypatch):
    from cloudra.runtime.chem_task import ChemTask, result_path
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core.conformer_catalog import content_digest
    from cloudra.tools.core.ts_inputs import CatalogConformer, FileConformer
    from cloudra.tools.core.ts_pipeline_driver import advance_process
    from tests.ts_fixtures import calculation_input
    source, xyz=catalog_seed(tmp_path)
    calculation={'engine':'xtb','method':'GFN2-xTB','keywords':''}
    inputs=calculation_input(reactant_smiles='O',product_smiles='O',method='b3lyp/def2svp',atom_map=[0,1,2])
    inputs.conformers.reactant=CatalogConformer(**source,optimization=calculation)
    inputs.conformers.product=FileConformer(kind='file',xyz_path=str(xyz),optimization=calculation)
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    record=ts_process.start(ts_process.TsStartRequest(request_key='fixture-prepare', input=inputs,workspace_dir=str(tmp_path),owner_conversation_id='project',owner_session_id='owner'))
    step=record.job_steps[-1]
    task=ChemTask.model_validate_json(Path(step.input_path).read_text())
    Path(result_path(step.input_path)).write_text(json.dumps(dict(manifest_digest=content_digest(task.model_dump()),process_exit_code=0,
        result=dict(returncode=0, normal_termination=True,optimization_converged=True,optimized_xyz=str(xyz)))))
    with ComputeDB().connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?",(step.job_id,))
    first=advance_process(ComputeDB(),record.pipeline_id)
    second=advance_process(ComputeDB(),record.pipeline_id)
    assert first['record']['blocked'] is None
    assert first['record']['job_steps'][-1]['purpose']=='product_seed_opt'
    assert second['record']['waiting_for']==first['record']['waiting_for']
    with ComputeDB().connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0]==2
