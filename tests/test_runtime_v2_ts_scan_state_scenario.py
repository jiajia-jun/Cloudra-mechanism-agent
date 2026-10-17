"""Agent scan revisions retain run science/resources through the shared renderer."""
import asyncio
from pathlib import Path

import pytest

from cloudra.runtime_v2.schemas import MethodPolicy
from tests.agent_scenarios import TS_SCENARIOS, ScenarioHarness, Step
from tests.test_runtime_v2_ts_workflow_scenarios import StateProvider, _script_compute, water_input


@pytest.mark.asyncio
@pytest.mark.usefixtures('rdkit_chemistry')
async def test_ts_run_scan_revision_inherits_shared_input_settings(tmp_path, monkeypatch):
    """Real Agent tools revise a queued scan without another electronic/resource declaration."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter
    from cloudra.tools.core.ts_process import load_record

    assert 'ts_run_scan_revision_inherits_shared_input_settings' in TS_SCENARIOS
    submissions = _script_compute(monkeypatch)
    payload = water_input(tmp_path, scan=True)
    payload['reaction']['electronic_character'] = 'closed_shell'
    payload['execution'].update(cpus=8, memory_mb=8192)
    payload['guess']['calculation']['engine'] = 'gaussian'
    payload['guess']['scans'] = [{'atoms': [1, 2], 'scan_end': 2., 'scan_steps': 3}]
    revision = {
        'run_id': 'ts_0001', 'mode': 'scan_prepare',
        'scans': [{'atoms': [1, 2], 'scan_end': 2.4, 'scan_steps': 3}],
    }
    render_calls = []
    real_render = QmInputWriter.render_input

    def render(request, molecule):
        native = real_render(request, molecule)
        render_calls.append((request.model_copy(deep=True), native))
        return native

    monkeypatch.setattr(QmInputWriter, 'render_input', staticmethod(render))

    def checkpoint(provider):
        provider.records.append(load_record(str(tmp_path), 'ts_0001'))

    provider = StateProvider(tmp_path, [
        Step(tools=[('ts_prepare', {'input': payload})]),
        Step(tools=[('ts_guess', revision)]), Step(stop=True),
    ], checkpoint)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    provider.harness = harness
    harness.project.settings.method_policy = MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(event['tool_name'], event['is_success']) for event in harness.tool_events(agent)] == [
            ('ts_prepare', True), ('ts_guess', True),
        ], harness.describe(agent)
        assert [event.data['arguments_summary'] for event in harness.events(agent)
                if event.type == 'tool.requested' and event.data.get('tool_name') == 'ts_guess'] == [revision]
        first, revised = provider.records[0], provider.records[-1]
        assert first.run_id == revised.run_id == 'ts_0001'
        assert first.pipeline_id == revised.pipeline_id
        assert (first.declaration_revision, revised.declaration_revision) == (1, 2)
        assert revised.attempt_history[-1].input == first.input
        assert first.input.guess.scans[0].scan_end == 2.
        assert revised.input.guess.scans[0].scan_end == 2.4
        for record in (first, revised):
            assert (record.input.reaction.charge, record.input.reaction.multiplicity,
                    record.input.reaction.electronic_character) == (0, 1, 'closed_shell')
            assert (record.compute_cpus, record.compute_memory_mb) == (8, 8192)
            assert record.input.guess.scans[0].atoms == [0, 1]
            assert record.input.guess.calculation.engine == 'gaussian'
            assert (record.input.guess.calculation.method,
                    record.input.guess.calculation.basis_set) == ('HF', 'STO-3G')
            assert record.blocked is None and record.terminal is None

        assert [submission['purpose'] for submission in submissions] == ['scan', 'scan']
        old, current = submissions
        assert old['id'] != current['id'] and old['path'] != current['path']
        assert revised.waiting_for == f"job:{current['id']}"
        assert revised.scan_step.job_id == current['id']
        assert Path(old['path']).read_text() == old['input']
        assert len(render_calls) == 2
        checkpoints = []
        for (request, native), submission in zip(render_calls, submissions, strict=True):
            assert request.output_path == submission['path']
            assert native == submission['input']
            assert (request.charge, request.multiplicity, request.electronic_character) == (0, 1, 'closed_shell')
            assert (request.nproc, request.mem) == (8, '8192MB')
            assert '%nproc=8\n' in native and '%mem=8192MB\n' in native
            chk = Path(submission['path']).resolve().with_suffix('.chk')
            assert f'%chk={chk}\n' in native
            checkpoints.append(chk)
            lines = native.splitlines()
            atoms = [row.split() for row in lines[lines.index('0 1') + 1:][:3]]
            assert [row[0] for row in atoms] == ['O', 'H', 'H']
            assert [[float(value) for value in row[1:]] for row in atoms] == [
                [0., 0., 0.], [.96, 0., 0.], [-.24, .93, 0.],
            ]
            assert '\n\nB 1 2 S 3 ' in native
        assert checkpoints[0] != checkpoints[1]

        def ledger():
            with ComputeDB().connect() as connection:
                return connection.execute(
                    'SELECT id,state,req_cpus,req_memory_mb,jobtype FROM compute_jobs ORDER BY id',
                ).fetchall()

        assert await asyncio.to_thread(ledger) == [
            (old['id'], 'cancelled', 8, 8192, 'gaussian'),
            (current['id'], 'ready', 8, 8192, 'gaussian'),
        ]
    finally:
        await harness.aclose()
