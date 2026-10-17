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
    inputs=calculation_input(reactant_smiles='O',product_smiles='O',method='HF/STO-3G')
    inputs.conformers.reactant=inputs.conformers.product=FileConformer(kind='file',xyz_path=str(seed))
    inputs.guess=ScanGuess(kind='scan',calculation={'engine':'orca','method':'HF','basis_set':'STO-3G','keywords':''},scans=[{'atoms':[0,1],'scan_start':1.,'scan_end':2.,'scan_steps':3}]) if scan else ProvidedGuess(kind='provided',xyz_path=str(seed),evidence_refs=[str(evidence)])
    data=inputs.model_dump(mode='json')
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
                'run_id': record.run_id,
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
        assert revised.blocked.failure_class == 'missing_input'
        assert revised.structures.product_to_reactant == (0, 1, 2) and revised.input.guess is None
        assert revised.attempt_history[0].structures.product_to_reactant is None
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
                'run_id': record.run_id,
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
        assert revised.structures.product_to_reactant == first.structures.product_to_reactant == (0, 1, 2)
        assert revised.input.reaction.reaction_center == first.input.reaction.reaction_center
        assert revised.input.guess == first.input.guess
        assert revised.structures.product_to_reactant is not None
        assert revised.blocked.stage == 'guess'
        with ComputeDB().connect() as con:
            assert con.execute('SELECT COUNT(*) FROM ts_pipeline_processes').fetchone()[0] == 1
            assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 0
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize('explicit_references', [False, True])
async def test_ts_source_reorder_keeps_imported_state_and_agent_numbering(tmp_path, explicit_references):
    from rdkit import Chem

    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_process import load_record

    assert 'ts_source_reorder_keeps_imported_state' in TS_SCENARIOS
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
            changes = {'reaction': {'reaction_center': [[2, 3]]}} if explicit_references else {}
            changes['conformers'] = {role: {'xyz_path': str(xyz_path)} for role in ('reactant', 'product')}
            # Both endpoints share the overwritten source, so an explicit raw
            # product->reactant map is identity; both slots and values normalize.
            provider._scripts['small_mol'][0].tools = [('ts_resume', {
                'run_id': record.run_id,
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
        assert current.structures.product_to_reactant == first.structures.product_to_reactant == (0, 1, 2)
        assert current.input.reaction.reaction_center == [(0, 1)]
        assert current.input.guess == first.input.guess
        assert read_xyz_atoms(str(xyz_path)) == raw_atoms[0]
        assert xyz_path.read_bytes() == raw_payloads[0]
        actual_mol = Chem.MolFromMolFile(str(mol_path), removeHs=False)
        assert [atom.GetSymbol() for atom in actual_mol.GetAtoms()] == ['H', 'O', 'H']
        for role in ('reactant', 'product'):
            owned = getattr(current.structures, role)
            assert [atom.GetSymbol() for atom in owned.GetAtoms()] == ['O', 'H', 'H']
            assert owned.GetConformer().GetPositions().tolist() == [point for _, point in [raw_atoms[0][index] for index in [1, 2, 0]]]
        outputs = [event.data['result']['data'] for event in harness.core.event_log.query_session(agent.id)
                   if event.type == 'tool.result_recorded' and event.data.get('tool_name') in ('ts_resume', 'ts_inspect')]
        assert len(outputs) == 2
        for output in outputs:
            assert output['revision'] == current.revision
            for role in ('reactant', 'product'):
                table = output['structures'][role]
                assert [row['symbol'] for row in table['atoms']] == ['O', 'H', 'H']
                assert [row['number'] for row in table['atoms']] == [1, 2, 3]
                assert 'normalization' not in table
                assert table['source']['paths']['xyz'] == str(xyz_path)
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
    for role in ('reactant', 'product'):
        payload['verification'][role + '_endpoint']['seed'] = {
            'kind': 'file', 'xyz_path': str(seed), 'evidence_refs': [str(seed)]}
    real_endpoint_writer = process._write_endpoint_input
    def writer(record,directory,role=None,task=None):
        if role is not None:
            result = real_endpoint_writer(record, directory, role, task)
            (Path(directory)/'optimized.xyz').write_text(seed.read_text())
            return result
        purpose='frequency' if role is None else role+'_'+task
        path=Path(directory)/(purpose+'.inp')
        path.write_text('! HF STO-3G '+('Freq' if purpose.endswith('frequency') else 'Opt')+'\n* xyz 0 1\nO 0 0 0\nH 0.96 0 0\nH -0.24 0.93 0\n*\n')
        (Path(directory)/'optimized.xyz').write_text(seed.read_text())
        return '',str(path)
    monkeypatch.setattr(process,'_write_frequency_input',writer)
    monkeypatch.setattr(process,'_write_endpoint_input',writer)
    monkeypatch.setattr(process,'_endpoint_opt_frame',lambda *_: (seed.read_text(), ''))
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
@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('role,purpose', [('reactant', 'candidate_opt'), ('product', 'product_seed_opt')])
async def test_ts_file_seed_preoptimization_can_be_removed_after_failure(tmp_path, monkeypatch, role, purpose):
    """An Agent reuses its file seed after removing a failed optional optimization."""
    import json

    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.core import ts_process as process
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal

    assert 'ts_file_seed_preoptimization_can_be_removed_after_failure' in TS_SCENARIOS
    submissions = _script_compute(monkeypatch)
    payload = water_input(tmp_path)
    payload['conformers'][role]['optimization'] = {
        'engine': 'orca', 'method': 'HF', 'basis_set': 'STO-3G', 'keywords': '',
    }
    source = payload['conformers'][role]
    patch = {'optimization': None}
    native_failure = 'GEOMETRY OPTIMIZATION DID NOT CONVERGE\nORCA finished by error termination\n'

    def reuse_file_seed(provider):
        record = process.load_record(str(tmp_path), 'ts_0001')
        if not provider.records:
            assert record.job_steps[-1].purpose == purpose
            step = record.job_steps[-1]
            assert record.waiting_for == f'job:{step.job_id}'
            Path(process._refinement_log_path(record, step)).write_text(native_failure)
            with ComputeDB().connect() as con:
                con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (step.job_id,))
            record = process.TsProcessRecord.model_validate(
                handle_process_job_terminal(ComputeDB(), step.job_id)['record'])
            provider._scripts['small_mol'][0].tools = [('ts_resume', {
                'run_id': record.run_id,
                'reason': 'Reuse the supplied file geometry without repeating seed optimization',
                'changes': {'conformers': {role: patch}},
            })]
        provider.records.append(record)

    provider = StateProvider(tmp_path, [
        Step(tools=[('ts_prepare', {'input': payload})]), Step(), Step(stop=True),
    ], reuse_file_seed)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    provider.harness = harness
    harness.project.settings.method_policy = MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(event['tool_name'], event['is_success']) for event in harness.tool_events(agent)] == [
            ('ts_prepare', True), ('ts_resume', True),
        ], harness.describe(agent)
        failed, current = provider.records[0], provider.records[-1]
        assert failed.blocked.failure_class == 'conformer_optimization_failed'
        assert failed.failed_attempt['purpose'] == purpose
        assert failed.run_id == current.run_id == 'ts_0001'
        assert failed.pipeline_id == current.pipeline_id
        assert current.declaration_revision == 2 and current.intervention_count == 1
        assert getattr(current.input.conformers, role).optimization is None
        assert getattr(current.input.conformers, role).xyz_path == source['xyz_path']
        assert current.blocked is None and current.terminal is None
        assert [step['purpose'] for step in submissions] == [purpose, 'ts_opt']
        assert [step.purpose for step in current.job_steps] == ['ts_opt']
        assert current.waiting_for == f"job:{submissions[-1]['id']}"
        history = current.attempt_history[-1]
        assert history.input == failed.input
        assert history.failed_attempt == failed.failed_attempt
        assert history.blocked.failure_class == 'conformer_optimization_failed'
        assert history.job_steps[-1].job_id == submissions[0]['id']
        assert history.job_steps[-1].state == 'failed'
        assert history.failed_attempt['evidence_refs'] == [history.failed_attempt['log_path']]
        assert Path(history.failed_attempt['log_path']).read_text() == native_failure
        assert Path(submissions[0]['path']).read_text() == submissions[0]['input']

        def ledger_state():
            with ComputeDB().connect() as con:
                jobs = con.execute('SELECT id,state FROM compute_jobs ORDER BY id').fetchall()
                evidence = con.execute('SELECT evidence FROM ts_pipeline_stages WHERE job_id=?',
                                       (submissions[0]['id'],)).fetchone()[0]
            return jobs, json.loads(evidence)

        jobs, evidence = await asyncio.to_thread(ledger_state)
        assert jobs == [(submissions[0]['id'], 'failed'), (submissions[1]['id'], 'ready')]
        assert evidence['status'] == 'failed'
        assert evidence['artifacts'] == [submissions[0]['path']]
        assert evidence['input_hash']
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures('rdkit_chemistry')
async def test_ts_queued_refinement_revision_same_run(tmp_path, monkeypatch):
    """An Agent replaces its queued refinement without failing the old job or starting QM."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.core.ts_process import load_record

    assert 'ts_queued_refinement_revision_same_run' in TS_SCENARIOS
    submissions = _script_compute(monkeypatch)
    payload = water_input(tmp_path)

    def revise(provider):
        record = load_record(str(tmp_path), 'ts_0001')
        provider.records.append(record)
        if len(provider.records) == 1:
            assert record.job_steps[-1].purpose == 'ts_opt'
            assert record.job_steps[-1].state == 'ready'
            assert record.waiting_for == f'job:{record.job_steps[-1].job_id}'
            provider._scripts['small_mol'][0].tools = [('ts_resume', {
                'run_id': record.run_id,
                'reason': 'Update the queued refinement convergence setting',
                'changes': {'ts_optimization': {'keywords': 'TightSCF'}},
            })]

    provider = StateProvider(tmp_path, [
        Step(tools=[('ts_prepare', {'input': payload})]), Step(), Step(stop=True),
    ], revise)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    provider.harness = harness
    harness.project.settings.method_policy = MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(event['tool_name'], event['is_success']) for event in harness.tool_events(agent)] == [
            ('ts_prepare', True), ('ts_resume', True),
        ], harness.describe(agent)
        first, revised = provider.records[0], provider.records[-1]
        assert first.run_id == revised.run_id == 'ts_0001'
        assert first.declaration_revision == 1 and revised.declaration_revision == 2
        assert revised.input.ts_optimization.keywords == 'TightSCF'
        assert revised.attempt_history[-1].input == first.input
        assert [step['purpose'] for step in submissions] == ['ts_opt', 'ts_opt']
        old, replacement = submissions
        assert old['id'] != replacement['id'] and old['path'] != replacement['path']
        assert revised.waiting_for == f"job:{replacement['id']}"
        assert [step.job_id for step in revised.job_steps] == [replacement['id']]
        assert Path(old['path']).read_text() == old['input']

        def ledger_state():
            with ComputeDB().connect() as con:
                jobs = con.execute('SELECT id,state FROM compute_jobs ORDER BY id').fetchall()
                processes = con.execute('SELECT COUNT(*) FROM ts_pipeline_processes').fetchone()[0]
            return jobs, processes

        jobs, processes = await asyncio.to_thread(ledger_state)
        assert jobs == [(old['id'], 'cancelled'), (replacement['id'], 'ready')]
        assert processes == 1
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('job_state', ['ready', 'running'])
async def test_ts_stop_prevents_automatic_progression(tmp_path, monkeypatch, job_state):
    """The Agent stops a durable TS chain; later job events cannot submit its next stage."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal, reconcile_processes
    from cloudra.tools.core.ts_process import load_record

    assert 'ts_stop_prevents_automatic_progression' in TS_SCENARIOS
    submissions = _script_compute(monkeypatch)
    payload = water_input(tmp_path)
    reason = 'Stop this TS exploration at the current calculation'

    def request_stop(provider):
        record = load_record(str(tmp_path), 'ts_0001')
        provider.records.append(record)
        if len(provider.records) == 1:
            assert record.job_steps[-1].purpose == 'ts_opt'
            assert record.waiting_for == f'job:{record.job_steps[-1].job_id}'
            if job_state == 'running':
                with ComputeDB().connect() as con:
                    con.execute("UPDATE compute_jobs SET state='running' WHERE id=?",
                                (record.job_steps[-1].job_id,))
            provider._scripts['small_mol'][0].tools = [('ts_stop', {
                'run_id': record.run_id, 'reason': reason,
            })]

    provider = StateProvider(tmp_path, [
        Step(tools=[('ts_prepare', {'input': payload})]), Step(), Step(stop=True),
    ], request_stop)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    provider.harness = harness
    harness.project.settings.method_policy = MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(event['tool_name'], event['is_success']) for event in harness.tool_events(agent)] == [
            ('ts_prepare', True), ('ts_stop', True),
        ], harness.describe(agent)
        first, stopped = provider.records[0], provider.records[-1]
        assert first.run_id == stopped.run_id == 'ts_0001'
        assert first.declaration_revision == stopped.declaration_revision == 1
        assert stopped.stop_reason == reason and stopped.terminal is None
        assert stopped.input == first.input
        assert len(submissions) == 1 and submissions[0]['purpose'] == 'ts_opt'
        job = submissions[0]
        assert Path(job['path']).read_text() == job['input']
        stop_output = next(event.data['result']['data']
            for event in harness.core.event_log.query_session(agent.id)
            if event.type == 'tool.result_recorded' and event.data.get('tool_name') == 'ts_stop')
        assert stop_output['status'] == 'stopped' and stop_output['result'] is None

        def late_notifications():
            db = ComputeDB()
            assert get_process(db, stopped.pipeline_id)['status'] == 'stopped'
            with db.connect() as con:
                state = con.execute('SELECT state FROM compute_jobs WHERE id=?', (job['id'],)).fetchone()[0]
                assert state == ('cancel_requested' if job_state == 'running' else 'cancelled')
                if job_state == 'running':
                    con.execute("UPDATE compute_jobs SET state='cancelled' WHERE id=?", (job['id'],))
            for _ in range(2):
                handle_process_job_terminal(db, job['id'])
                reconcile_processes(db, harness.project.id)
            current = get_process(db, stopped.pipeline_id)
            assert current['status'] == 'stopped'
            assert current['record']['stop_reason'] == reason
            assert current['record']['terminal'] is None
            with db.connect() as con:
                assert con.execute('SELECT id,state FROM compute_jobs').fetchall() == [(job['id'], 'cancelled')]

        with use_runtime_authority(harness.core):
            await asyncio.to_thread(late_notifications)
        assert len(submissions) == 1
        assert Path(job['path']).read_text() == job['input']
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures('rdkit_chemistry')
async def test_ts_stopped_attempt_resumes_same_run(tmp_path, monkeypatch):
    """An Agent can explicitly retry a stopped attempt through the real writer and driver."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core.ts_process import load_record

    assert 'ts_stopped_attempt_resumes_same_run' in TS_SCENARIOS
    submissions = _script_compute(monkeypatch)
    payload = water_input(tmp_path)
    stop_reason = 'Stop the queued attempt before retrying'

    def stop_then_resume(provider):
        record = load_record(str(tmp_path), 'ts_0001')
        provider.records.append(record)
        if len(provider.records) == 1:
            provider._scripts['small_mol'][0].tools = [('ts_stop', {
                'run_id': record.run_id, 'reason': stop_reason,
            })]
        elif len(provider.records) == 2:
            assert record.stop_reason == stop_reason
            with ComputeDB().connect() as con:
                assert con.execute('SELECT state FROM compute_jobs WHERE id=?',
                                   (submissions[0]['id'],)).fetchone()[0] == 'cancelled'
            provider._scripts['small_mol'][0].tools = [('ts_resume', {
                'run_id': record.run_id, 'changes': {}, 'reason': 'Retry stopped attempt',
            })]

    provider = StateProvider(tmp_path, [
        Step(tools=[('ts_prepare', {'input': payload})]), Step(), Step(), Step(stop=True),
    ], stop_then_resume)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    provider.harness = harness
    harness.project.settings.method_policy = MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(event['tool_name'], event['is_success']) for event in harness.tool_events(agent)] == [
            ('ts_prepare', True), ('ts_stop', True), ('ts_resume', True),
        ], harness.describe(agent)
        first, stopped, resumed = provider.records[0], provider.records[1], provider.records[-1]
        assert first.run_id == stopped.run_id == resumed.run_id == 'ts_0001'
        assert first.pipeline_id == stopped.pipeline_id == resumed.pipeline_id
        assert first.declaration_revision == stopped.declaration_revision == 1
        assert resumed.declaration_revision == 2 and resumed.stop_reason is None
        assert resumed.terminal is None and resumed.blocked is None
        assert resumed.input == first.input
        assert resumed.attempt_history[-1].stop_reason == stop_reason
        assert resumed.attempt_history[-1].input == first.input
        assert [step['purpose'] for step in submissions] == ['ts_opt', 'ts_opt']
        old, replacement = submissions
        assert old['id'] != replacement['id'] and old['path'] != replacement['path']
        assert resumed.waiting_for == f"job:{replacement['id']}"
        assert [step.job_id for step in resumed.job_steps] == [replacement['id']]
        assert Path(old['path']).read_text() == old['input']

        def ledger_state():
            db = ComputeDB()
            with db.connect() as con:
                jobs = con.execute('SELECT id,state FROM compute_jobs ORDER BY id').fetchall()
            return get_process(db, resumed.pipeline_id)['status'], jobs

        status, jobs = await asyncio.to_thread(ledger_state)
        assert status == 'waiting'
        assert jobs == [(old['id'], 'cancelled'), (replacement['id'], 'ready')]
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_ts_failed_scan_retry_same_run(tmp_path,monkeypatch):

    assert TS_SCENARIOS[1]=='ts_failed_scan_retry_same_run'
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
            provider._scripts['small_mol'][0].tools=[('ts_resume',{
                'run_id':record.run_id,
                'reason':'Retry the native scan after the execution environment was repaired',
                'changes': {},
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
        history = current.attempt_history[-1]
        assert history.failed_attempt['attempt_id'] == f'1:scan:{submissions[0]["id"]}'
        assert history.input == current.input
        assert history.job_steps[-1].job_id != current.scan_step.job_id
        assert Path(submissions[0]['path']).read_text() == submissions[0]['input']
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
    base['conformers'] = {'reactant': {'kind':'file','xyz_path':str(xyz),'mol_path':str(graph)},
                          'product': {'kind':'file','xyz_path':str(xyz),'mol_path':str(graph)}}
    base['guess'] = {'kind':'scan','calculation':{'engine':'xtb','method':'GFN2-xTB','basis_set':''},
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
        assert record.blocked.failure_class == 'input_identity_unconfirmed'
        from cloudra.tools.core.reaction_state import structure_tables
        tables = structure_tables(record)
        assert [row['symbol'] for row in tables['reactant']['atoms'][4:6]] == ['H','H']
        candidates = record.blocked.issues[0]['candidates']
        assert all(len(candidate['atom_map']) == 16 for candidate in candidates)
        selected = next(i for i, candidate in enumerate(candidates) if candidate['atom_map'] == list(range(1,17)))
        changes = {'reaction': {'selected_candidate': selected}}
        provider._scripts['small_mol'][0].tools = [('ts_resume', {
            'run_id':record.run_id,
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
        assert record.structures.product_to_reactant is not None
        assert record.blocked is None, record.blocked
        assert record.waiting_for and record.scan_step and record.scan_step.purpose == 'scan'
        with ComputeDB().connect() as con:
            jobs = con.execute('SELECT jobtype FROM compute_jobs').fetchall()
        assert [row[0] for row in jobs] == ['chem_task']
    finally:
        await harness.aclose()
