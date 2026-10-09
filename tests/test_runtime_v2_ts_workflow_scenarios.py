"""Zero-key Agent scenarios exercise the real grouped TS tool/driver boundary."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.schemas import MethodPolicy
from cloudra.services.ts_pipeline_context import use_runtime_authority
from tests.agent_scenarios import TS_SCENARIOS, ScenarioHarness, ScriptedProvider, Step, d1_component_order_files


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
@pytest.mark.usefixtures('rdkit_chemistry')
async def test_ts_conformer_source_revision_same_run(tmp_path, monkeypatch):
    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.core.ts_process import load_record

    assert 'ts_conformer_source_revision_same_run' in TS_SCENARIOS
    service = tmp_path / 'service'
    service.mkdir()
    monkeypatch.chdir(service)
    payload = water_input(tmp_path)
    payload['conformers']['reactant']['xyz_path'] = 'missing.xyz'
    payload['conformers']['product']['xyz_path'] = 'water.xyz'

    def complete(provider):
        record = load_record(str(tmp_path), 'ts_0001')
        provider.records.append(record)
        if len(provider.records) == 1:
            provider._scripts['small_mol'][0].tools = [('ts_resume', {
                'run_id': record.run_id, 'expected_revision': record.revision,
                'reason': 'Supply the available endpoint source',
                'changes': {'conformers': {'reactant': {'kind': 'file', 'xyz_path': 'water.xyz'}}},
            })]

    provider = StateProvider(tmp_path, [Step(tools=[('ts_prepare', {'input': payload})]),
                                      Step(), Step(stop=True)], complete)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    provider.harness = harness
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(e['tool_name'], e['is_success']) for e in harness.tool_events(agent)] == [
            ('ts_prepare', True), ('ts_resume', True),
        ], harness.describe(agent)
        first, revised = provider.records[0], provider.records[-1]
        assert first.blocked.issues[0]['path'] == str(tmp_path / 'missing.xyz')
        assert revised.run_id == first.run_id and revised.declaration_revision == 2
        assert revised.blocked.failure_class == 'atom_map_missing'
        assert revised.input.reaction.atom_map == [] and revised.input.guess is None
        assert revised.attempt_history[0].input.reaction.atom_map == [0, 1, 2]
        with ComputeDB().connect() as con:
            assert con.execute('SELECT COUNT(*) FROM ts_pipeline_processes').fetchone()[0] == 1
            assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 0
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_ts_same_structure_source_keeps_declarations(tmp_path, monkeypatch):
    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.core.ts_process import load_record

    assert 'ts_same_structure_source_keeps_declarations' in TS_SCENARIOS
    service = tmp_path / 'service'
    service.mkdir()
    monkeypatch.chdir(service)
    payload = water_input(tmp_path)
    payload['conformers']['reactant']['xyz_path'] = 'water.xyz'
    payload['conformers']['product']['xyz_path'] = 'water.xyz'
    payload['guess']['xyz_path'] = 'missing-guess.xyz'
    payload['reaction']['reaction_center'] = [[1, 2]]
    replacement = tmp_path / 'renamed-water.xyz'
    replacement.write_bytes((tmp_path / 'water.xyz').read_bytes())

    def complete(provider):
        record = load_record(str(tmp_path), 'ts_0001')
        provider.records.append(record)
        if len(provider.records) == 1:
            provider._scripts['small_mol'][0].tools = [('ts_resume', {
                'run_id': record.run_id, 'expected_revision': record.revision,
                'reason': 'Use the same structure under its new filename',
                'changes': {'conformers': {'reactant': {
                    'kind': 'file', 'xyz_path': 'renamed-water.xyz',
                }}},
            })]

    provider = StateProvider(tmp_path, [Step(tools=[('ts_prepare', {'input': payload})]),
                                      Step(), Step(stop=True)], complete)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    provider.harness = harness
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(e['tool_name'], e['is_success']) for e in harness.tool_events(agent)] == [
            ('ts_prepare', True), ('ts_resume', True),
        ], harness.describe(agent)
        first, revised = provider.records[0], provider.records[-1]
        assert first.blocked.stage == 'guess'
        assert revised.run_id == first.run_id and revised.declaration_revision == 2
        assert revised.input.reaction.atom_map == first.input.reaction.atom_map == [0, 1, 2]
        assert revised.input.reaction.reaction_center == first.input.reaction.reaction_center
        assert revised.input.guess == first.input.guess
        assert revised.input_binding['binding_status'] == 'complete'
        assert revised.blocked.stage == 'guess'
        with ComputeDB().connect() as con:
            assert con.execute('SELECT COUNT(*) FROM ts_pipeline_processes').fetchone()[0] == 1
            assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 0
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize('explicit_references', [False, True])
async def test_ts_canonical_source_overwrite_matches_agent_numbering(tmp_path, explicit_references):
    from rdkit import Chem

    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_process import load_record

    assert 'ts_canonical_source_overwrite' in TS_SCENARIOS
    payload = water_input(tmp_path)
    payload['guess']['xyz_path'] = 'missing-guess.xyz'
    payload['reaction']['reaction_center'] = [[1, 2]]
    xyz_path = tmp_path / 'water.xyz'
    mol_path = tmp_path / 'water.mol'
    molecule = Chem.AddHs(Chem.MolFromSmiles('O'))
    original_atoms = read_xyz_atoms(str(xyz_path))
    conformer = Chem.Conformer(3)
    for index, (symbol, position) in enumerate(original_atoms):
        assert molecule.GetAtomWithIdx(index).GetSymbol() == symbol
        molecule.GetAtomWithIdx(index).SetAtomMapNum(index + 10)
        conformer.SetAtomPosition(index, position)
    molecule.AddConformer(conformer)
    mol_path.write_text(Chem.MolToMolBlock(molecule))
    for role in ('reactant', 'product'):
        payload['conformers'][role]['mol_path'] = str(mol_path)
    raw_payloads = []
    raw_atoms = []

    def complete(provider):
        record = load_record(str(tmp_path), 'ts_0001')
        provider.records.append(record)
        if len(provider.records) == 1:
            raw = Chem.RenumberAtoms(molecule, [2, 0, 1])
            for index in range(raw.GetNumAtoms()):
                position = raw.GetConformer().GetAtomPosition(index)
                raw.GetConformer().SetAtomPosition(index, (position.x + .1, position.y, position.z))
            xyz_path.write_text(Chem.MolToXYZBlock(raw))
            mol_path.write_text(Chem.MolToMolBlock(raw))
            raw_payloads.append(xyz_path.read_bytes())
            raw_atoms.append(read_xyz_atoms(str(xyz_path)))
            changes = {'reaction': {'atom_map': [1, 2, 3], 'reaction_center': [[2, 3]]}} if explicit_references else {}
            # Both endpoints share the overwritten source, so an explicit raw
            # product->reactant map is identity; both slots and values normalize.
            provider._scripts['small_mol'][0].tools = [('ts_resume', {
                'run_id': record.run_id, 'expected_revision': record.revision,
                'reason': 'Update coordinates and restore the current canonical atom order',
                'changes': changes,
            })]

    provider = StateProvider(tmp_path, [Step(tools=[('ts_prepare', {'input': payload})]),
                                      Step(), Step(tools=[('ts_inspect', {'run_id': 'ts_0001'})]),
                                      Step(stop=True)], complete)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    provider.harness = harness
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(e['tool_name'], e['is_success']) for e in harness.tool_events(agent)] == [
            ('ts_prepare', True), ('ts_resume', True), ('ts_inspect', True),
        ], harness.describe(agent)
        first, current = provider.records[0], provider.records[-1]
        assert current.input.reaction.atom_map == first.input.reaction.atom_map == [0, 1, 2]
        assert current.input.reaction.reaction_center == [(0, 1)]
        assert current.input.guess == first.input.guess
        assert read_xyz_atoms(str(xyz_path)) == [raw_atoms[0][index] for index in [1, 2, 0]]
        assert xyz_path.read_bytes() != raw_payloads[0]
        actual_mol = Chem.MolFromMolFile(str(mol_path), removeHs=False)
        assert [atom.GetSymbol() for atom in actual_mol.GetAtoms()] == ['O', 'H', 'H']
        for role in ('reactant', 'product'):
            assert read_xyz_atoms(current.structures[role]['xyz_path']) == read_xyz_atoms(str(xyz_path))
            assert [row['symbol'] for row in current.structures[role]['atoms']] == ['O', 'H', 'H']
        outputs = [event.data['result']['data'] for event in harness.core.event_log.query_session(agent.id)
                   if event.type == 'tool.result_recorded' and event.data.get('tool_name') in ('ts_resume', 'ts_inspect')]
        assert len(outputs) == 2
        for output in outputs:
            assert output['revision'] == current.revision
            for role in ('reactant', 'product'):
                table = output['structures'][role]
                assert [row['symbol'] for row in table['atoms']] == ['O', 'H', 'H']
                assert [row['number'] for row in table['atoms']] == [1, 2, 3]
                assert table['normalization']['status'] == 'applied'
                assert table['normalization']['paths']['xyz'] == str(xyz_path)
                assert 'raw_source_paths' not in table['normalization']
        with ComputeDB().connect() as con:
            assert con.execute('SELECT COUNT(*) FROM ts_pipeline_processes').fetchone()[0] == 1
            assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 0
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
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
    provider=StateProvider(tmp_path,[Step(tools=[('ts_prepare',{'input':payload})]),Step(stop=True)],complete)
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
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_ts_failed_scan_repair_same_run(tmp_path,monkeypatch):
    import hashlib

    from cloudra.tools.core.ts_inputs import ScanRepairReceipt

    assert TS_SCENARIOS[1]=='ts_failed_scan_repair_same_run'
    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.core import ts_process as process
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal
    submissions=_script_compute(monkeypatch,first_scan='missing_log')
    payload=water_input(tmp_path,scan=True)
    def complete(provider):
        record=process.load_record(str(tmp_path),'ts_0001')
        if record.scan_step and record.waiting_for==f'job:{record.scan_step.job_id}':
            with ComputeDB().connect() as con:
                state = 'failed' if record.declaration_revision == 1 else 'done'
                con.execute("UPDATE compute_jobs SET state=? WHERE id=?",(state,record.scan_step.job_id))
            record=process.TsProcessRecord.model_validate(handle_process_job_terminal(ComputeDB(),record.scan_step.job_id)['record'])
        provider.records.append(record)
        if record.failed_attempt and record.declaration_revision==1:
            failed = record.scan_step
            attempt_id = f'{failed.source_input_revision}:scan:{failed.job_id}'
            input_hash = hashlib.sha256(Path(failed.input_path).read_bytes()).hexdigest()
            repair = tmp_path / 'scan-repair-receipt.json'
            repair.write_text(ScanRepairReceipt(
                failed_attempt_id=attempt_id, failure_input_sha256=input_hash,
                repair='Fixture execution environment repaired after the first scan failed to produce output',
            ).model_dump_json())
            provider._scripts['small_mol'][0].tools=[('ts_resume',{
                'run_id':record.run_id,
                'reason':'Retry the failed scan with an independently bound environment repair receipt',
                'expected_revision':record.revision,
                'scan_recovery': {
                    'failed_attempt_id': attempt_id,
                    'failure_input_sha256': input_hash,
                    'failure_log_sha256': None,
                    'evidence_refs': [{'path': str(repair),
                                       'sha256': hashlib.sha256(repair.read_bytes()).hexdigest()}],
                },
            })]
    provider=StateProvider(tmp_path,[Step(tools=[('ts_prepare',{'input':payload})]),Step(),Step(stop=True)],complete)
    harness=await ScenarioHarness.start(tmp_path,workspace_dir=tmp_path,provider=provider)
    provider.harness=harness
    harness.project.settings.method_policy=MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent=await harness.spawn('small_mol',protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(e['tool_name'],e['is_success']) for e in harness.tool_events(agent)]==[('ts_prepare',True),('ts_resume',True)],harness.describe(agent)
        current=provider.records[-1]
        assert current.run_id=='ts_0001' and current.intervention_count==1
        assert current.attempt_history[-1].failed_attempt['failure_class']=='unclassified_failure'
        assert current.attempt_history[-1].blocked.failure_class == 'scan_job_failed'
        recovery = current.attempt_history[-1].recovery_evidence
        assert recovery['failed_attempt']['attempt_id'] == f'1:scan:{submissions[0]["id"]}'
        assert recovery['input_diff'] == []
        assert recovery['evidence_refs'][0]['kind'] == 'repair_receipt'
        assert recovery['scientific_recovery_verified'] is False
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
    provider=ScriptedProvider(by_role={'small_mol':[Step(tools=[('ts_prepare',{'input':inputs})]),Step(stop=True)],
        'explorer':[Step(tools=[('ts_inspect',{'run_id':'ts_0001'})]),Step(tools=[('ts_prepare',{'input':inputs})]),Step(stop=True)]})
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


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_ts_resume_scan_without_freeze(tmp_path, monkeypatch):
    """A real Agent dispatch can replace an absent guess and queue the scan on the same run."""
    assert 'ts_resume_scan_without_freeze' in TS_SCENARIOS
    from cloudra.tools.core import ts_process as process

    submissions = _script_compute(monkeypatch)
    payload = water_input(tmp_path, scan=True)
    scan = payload.pop('guess')
    scan.pop('freeze')

    def complete(provider):
        record = process.load_record(str(tmp_path), 'ts_0001')
        provider.records.append(record)
        if record.input.guess is None:
            provider._scripts['small_mol'][0].tools = [('ts_resume', {
                'run_id': record.run_id, 'reason': 'provide explicit scan declaration',
                'expected_revision': record.revision,
                'changes': {'guess': scan},
            })]

    provider = StateProvider(tmp_path, [
        Step(tools=[('ts_prepare', {'input': payload})]),
        Step(), Step(stop=True),
    ], complete)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    provider.harness = harness
    harness.project.settings.method_policy = MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(e['tool_name'], e['is_success']) for e in harness.tool_events(agent)] == [
            ('ts_prepare', True), ('ts_resume', True),
        ], harness.describe(agent)
        record = provider.records[-1]
        assert record.run_id == 'ts_0001' and record.intervention_count == 1
        assert record.input.guess.freeze == []
        assert len(submissions) == 1 and submissions[0]['purpose'] == 'scan'
        assert record.waiting_for == f"job:{submissions[0]['id']}"
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures('rdkit_chemistry')
async def test_ts_d1_atom_binding_native_scan_recovery(tmp_path, monkeypatch):
    """A scripted Agent reads the true 16-atom table and repairs both bindings without probing numbers."""
    assert 'ts_d1_atom_binding_native_scan_recovery' in TS_SCENARIOS
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core.ts_process import load_record
    from tests.ts_fixtures import calculation_input

    xyz, graph = d1_component_order_files(tmp_path)
    base = calculation_input(reactant_smiles='C=CC=C.C=C', product_smiles='C=CC=C.C=C',
                             method='HF/STO-3G').model_dump(mode='json')
    base['reaction']['atom_map'] = []
    base['conformers'] = {'reactant': {'kind':'file','xyz_path':str(xyz),'mol_path':str(graph)},
                          'product': {'kind':'file','xyz_path':str(xyz),'mol_path':str(graph)}}
    base['guess'] = {'kind':'scan','calculation':{'engine':'xtb','method':'GFN2-xTB'},
                     'scans':[{'atoms':[4,11],'scan_start':7.,'scan_end':4.,'scan_steps':3}],
                     'force_constant':.5}
    # This two-component fixture must declare the same pair used by its scan.
    base['reaction']['reaction_center'] = [[4,11]]
    invalid = {**base, 'guess': {key:value for key,value in base['guess'].items() if key != 'force_constant'}}
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
                        lambda **_: AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))

    def repair(provider):
        if provider.call_count('small_mol') != 3:
            return
        record = load_record(str(tmp_path), 'ts_0001')
        assert record.blocked.failure_class == 'atom_map_missing'
        assert [row['symbol'] for row in record.structures['reactant']['atoms'][4:6]] == ['H','H']
        assert [record.structures['reactant']['atoms'][i-1]['symbol'] for i in (1,2,3,4,11,12)] == ['C']*6
        changes = {'reaction':{'atom_map':list(range(1,17))},'conformers':{}}
        for role in ('reactant','product'):
            changes['conformers'][role] = {'kind':'file','xyz_path':str(xyz),'mol_path':str(graph),
                'heavy_atom_binding':{'structure_digest':record.structures[role]['structure_digest'],
                                      'indices':[1,2,3,4,11,12]}}
        provider._scripts['small_mol'][0].tools = [('ts_resume', {
            'run_id':record.run_id,'expected_revision':record.revision,
            'reason':'Bind both concrete endpoint atom orders and the complete all-atom map',
            'changes':changes})]

    provider = StateProvider(tmp_path, [Step(tools=[('ts_prepare', {'input':invalid})]),
        Step(tools=[('ts_prepare', {'input':base})]),
        Step(tools=[('ts_inspect', {'run_id':'ts_0001'})]), Step(), Step(stop=True)], repair)
    harness = await ScenarioHarness.start(tmp_path,workspace_dir=tmp_path,provider=provider)
    provider.harness = harness
    try:
        agent = await harness.spawn('small_mol',protocol='traditional')
        await harness.wait_terminal(agent)
        calls = harness.tool_events(agent)
        assert [(item['tool_name'],item['is_success']) for item in calls] == [
            ('ts_prepare',False),('ts_prepare',True),('ts_inspect',True),('ts_resume',True)], harness.describe(agent)
        record = await asyncio.to_thread(load_record,str(tmp_path),'ts_0001')
        assert record.input_binding['binding_status'] == 'complete', record.input_binding
        assert record.blocked is None, record.blocked
        assert record.waiting_for and record.scan_step and record.scan_step.purpose == 'scan'
        with ComputeDB().connect() as con:
            jobs = con.execute('SELECT jobtype FROM compute_jobs').fetchall()
        assert [row[0] for row in jobs] == ['chem_task']
    finally:
        await harness.aclose()
