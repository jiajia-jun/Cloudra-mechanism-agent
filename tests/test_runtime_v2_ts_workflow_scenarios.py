"""The real agent/tool pipeline keeps a declared scan inside its TS process."""
import pytest

from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step


@pytest.mark.asyncio
async def test_agent_scan_workflow_advances_without_resume_or_duplicate_submission(tmp_path, monkeypatch):
    pytest.importorskip('rdkit')

    import cloudra.tools.core.ts_process as process

    submissions = _script_compute(monkeypatch)
    declaration = {
        'reactant_smiles':'O', 'product_smiles':'O', 'engine':'orca', 'method':'b3lyp/def2svp',
        'atom_map':[0,1,2], 'reaction_center':[[0,1]],
        'scan':{'method':'b3lyp/def2svp', 'scans':[{'atoms':[0,1],'scan_end':2.,'scan_steps':5}]},
    }
    provider = _RecordingProvider(tmp_path, [
        Step(tools=[('ts_prepare',{'declaration':declaration})]),
        Step(text='Waiting for refinement', stop=True),
    ])
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        calls = harness.tool_events(agent)
        assert all(row['is_success'] for row in calls), harness.describe(agent)
        assert [row['tool_name'] for row in calls] == ['ts_prepare']
        assert [row['purpose'] for row in submissions] == ['scan', 'ts_opt']
        record = process.load_record(str(tmp_path), 'ts_0001')
        assert record.path_kind == 'scan'
        assert record.intervention_count == 0
        assert record.waiting_for == 'job:2'
        assert record.declaration.scan.scans[0].atoms == [0,1]
        assert record.current_ts_guess_path.endswith('scan_peak.xyz')
    finally:
        await harness.aclose()


class _RecordingProvider(ScriptedProvider):
    """Observe persisted process state between real agent tool calls."""

    def __init__(self, workspace, steps, *, complete_scans=True):
        super().__init__(by_role={'small_mol': steps})
        self.workspace = workspace
        self.records = []
        self.complete_scans = complete_scans

    async def complete(self, *args, **kwargs):
        import asyncio

        from cloudra.tools.core.ts_process import load_record

        def snapshot():
            if (self.workspace / 'ts/ts_0001/process.json').exists():
                return load_record(str(self.workspace), 'ts_0001')
            return None
        record = await asyncio.to_thread(snapshot)
        if record is not None:
            self.records.append(record)
            if (self.complete_scans and record.scan_step is not None
                    and record.waiting_for == f'job:{record.scan_step.job_id}'):
                await asyncio.to_thread(_complete_scan, record.scan_step.job_id)
        return await super().complete(*args, **kwargs)


def _complete_scan(job_id):
    """Replace an external calculator completion, retaining the real system driver."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal

    db = ComputeDB().init()
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job_id,))
    first = handle_process_job_terminal(db, job_id)
    repeated = handle_process_job_terminal(db, job_id)
    assert first['record'] == repeated['record']


def _scan_declaration():
    return {
        'reactant_smiles': 'O', 'product_smiles': 'O', 'engine': 'orca',
        'method': 'b3lyp/def2svp', 'atom_map': [0, 1, 2],
        'scan': {
            'method': 'b3lyp/def2svp',
            'scans': [{'atoms': [0, 1], 'scan_end': 2., 'scan_steps': 5}],
            'freeze': [{'coord_type': 'bond', 'atoms': [0, 2]}],
        },
    }


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
@pytest.mark.parametrize('failure,failure_class', [
    ('no_peak', 'scan_no_candidate'),
    ('missing_log', 'scan_parse_failed'),
    ('wrong_atoms', 'scan_invalid_geometry'),
])
async def test_agent_repairs_failed_scan_and_resumes_unconstrained_refinement(
    tmp_path, monkeypatch, failure, failure_class,
):
    """Levers: tool dispatch, persisted blocked state, correction budget, scan parsing."""
    pytest.importorskip('rdkit')
    submissions = _script_compute(monkeypatch, failure)
    declaration = _scan_declaration()
    corrected = _scan_declaration()['scan']
    corrected['scans'][0]['scan_end'] = 2.2
    adjustment = {'scan': corrected}
    if failure == 'no_peak':
        # A geometry correction must also invalidate the old scan and rebuild.
        adjustment['distance_filters'] = [{'atoms': [0, 1], 'min_ang': .8, 'max_ang': 1.2}]
    provider = _RecordingProvider(tmp_path, [
        Step(tools=[('ts_prepare', {'declaration': declaration})]),
        Step(tools=[('ts_resume', {'run_id': 'ts_0001'})]),
        Step(tools=[('ts_resume', {'run_id': 'ts_0001', 'adjustment': adjustment})]),
        Step(tools=[('ts_resume', {'run_id': 'ts_0001'})]),
        Step(tools=[('ts_resume', {'run_id': 'ts_0001'})]),
        Step(stop=True),
    ])
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        calls = harness.tool_events(agent)
        assert len(calls) == 5 and all(row['is_success'] for row in calls), harness.describe(agent)
        waiting, blocked, repaired, refining, repeated = provider.records
        assert waiting.waiting_for == 'job:1'
        assert blocked.blocked.failure_class == failure_class
        assert blocked.waiting_for == '' and blocked.job_steps == []
        assert blocked.intervention_count == 0
        assert repaired.waiting_for == 'job:2' and repaired.blocked is None
        assert repaired.intervention_count == 1
        assert [row['purpose'] for row in submissions] == ['scan', 'scan', 'ts_opt']
        assert submissions[0]['path'] != submissions[1]['path']
        assert 'Constraints' in submissions[1]['input']
        assert 'Constraints' not in submissions[2]['input']
        for record in (refining, repeated):
            assert record.waiting_for == 'job:3' and record.blocked is None
            assert record.path_kind == 'scan' and record.terminal is None
            assert record.intervention_count == 1
            assert record.declaration.scan.freeze[0].atoms == [0, 2]
        if failure == 'no_peak':
            assert repaired.guidance_attempt > waiting.guidance_attempt
            assert repaired.guidance_manifest_path
            assert repaired.declaration.distance_filters[0].atoms == [0, 1]
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_agent_adding_scan_cannot_bypass_missing_map(tmp_path, monkeypatch):
    """Levers: partial declarations, actual map gate, prepare/resume dispatch."""
    pytest.importorskip('rdkit')
    submissions = _script_compute(monkeypatch)
    declaration = _scan_declaration()
    scan = declaration.pop('scan')
    declaration['atom_map'] = []
    provider = _RecordingProvider(tmp_path, [
        Step(tools=[('ts_prepare', {'declaration': declaration})]),
        Step(tools=[('ts_resume', {'run_id': 'ts_0001', 'adjustment': {'scan': scan}})]),
        Step(tools=[('ts_resume', {'run_id': 'ts_0001', 'adjustment': {'atom_map': [0, 1, 2]}})]),
        Step(tools=[('ts_resume', {'run_id': 'ts_0001'})]),
        Step(stop=True),
    ])
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert all(row['is_success'] for row in harness.tool_events(agent)), harness.describe(agent)
        missing, still_missing, mapped, refining = provider.records
        for record in (missing, still_missing):
            assert record.blocked.stage == 'map'
            assert record.blocked.needs == ['atom_map']
            assert record.scan_step is None and record.waiting_for == ''
        assert mapped.waiting_for == 'job:1'
        assert refining.waiting_for == 'job:2'
        assert refining.intervention_count == 2
        assert [row['purpose'] for row in submissions] == ['scan', 'ts_opt']
    finally:
        await harness.aclose()


@pytest.mark.asyncio
async def test_agent_cannot_replace_scan_while_job_is_running(tmp_path, monkeypatch):
    """Levers: rejected tool adjustment leaves durable in-flight state intact."""
    pytest.importorskip('rdkit')
    submissions = _script_compute(monkeypatch)
    corrected = _scan_declaration()['scan']
    corrected['scans'][0]['scan_end'] = 2.2
    provider = _RecordingProvider(tmp_path, [
        Step(tools=[('ts_prepare', {'declaration': _scan_declaration()})]),
        Step(tools=[('ts_resume', {'run_id': 'ts_0001', 'adjustment': {'scan': corrected}})]),
        Step(tools=[('ts_resume', {'run_id': 'ts_0001'})]),
        Step(stop=True),
    ], complete_scans=False)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [row['is_success'] for row in harness.tool_events(agent)] == [True, False, True]
        assert [row['purpose'] for row in submissions] == ['scan']
        for record in provider.records:
            assert record.waiting_for == 'job:1'
            assert record.intervention_count == 0
            assert record.declaration.scan.scans[0].scan_end == 2.
            assert record.scan_step.job_id == 1
    finally:
        await harness.aclose()
