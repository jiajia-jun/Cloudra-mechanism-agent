"""Agent-created TS runs recover completed dependencies without another tool call."""
import asyncio
from pathlib import Path

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from cloudra.runtime_v2.schemas import MethodPolicy
from cloudra.services.compute_store import mark_notified
from cloudra.services.ts_pipeline_store import get_process
from cloudra.tools.core.ts_process import load_record
from tests.agent_scenarios import TS_SCENARIOS, ScenarioHarness, ScriptedProvider, Step
from tests.test_runtime_v2_ts_workflow_scenarios import _script_compute, water_input


@pytest.mark.asyncio
@pytest.mark.usefixtures('rdkit_chemistry')
async def test_ts_acknowledged_completion_recovers_without_resume(tmp_path, monkeypatch):
    assert 'ts_acknowledged_completion_recovers_without_resume' in TS_SCENARIOS
    submissions = _script_compute(monkeypatch)
    payload = water_input(tmp_path)

    def frequency_writer(_record, directory):
        path = Path(directory) / 'frequency.inp'
        geometry = (tmp_path / 'water.xyz').read_text()
        path.write_text('! HF STO-3G Freq\n* xyz 0 1\n' + '\n'.join(geometry.splitlines()[2:]) + '\n*\n')
        (Path(directory) / 'optimized.xyz').write_text(geometry)
        return '', str(path)

    monkeypatch.setattr('cloudra.tools.core.ts_process._write_frequency_input', frequency_writer)
    provider = ScriptedProvider(by_role={'small_mol': [
        Step(tools=[('ts_prepare', {'input': payload})]), Step(stop=True),
    ]})
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    harness.project.settings.method_policy = MethodPolicy(allowed_methods=['hf/sto3g'])
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        await harness.wait_terminal(agent)
        assert [(event['tool_name'], event['is_success']) for event in harness.tool_events(agent)] == [
            ('ts_prepare', True),
        ], harness.describe(agent)
        first = await asyncio.to_thread(load_record, str(tmp_path), 'ts_0001')
        assert [step['purpose'] for step in submissions] == ['ts_opt']
        job_id = first.job_steps[0].job_id

        def completed_dependency():
            db = ComputeDB()
            with db.connect() as con:
                con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job_id,))
            mark_notified(db, job_id)
            return get_process(db, first.pipeline_id)

        before = await asyncio.to_thread(completed_dependency)
        assert before['record']['waiting_for'] == f'job:{job_id}'
        calls_before = provider.call_count()
        messages_before = harness.messages(agent)
        runs_before = harness.run_rows(agent)

        # 模拟通知服务恢复：它必须从已有运行引用定位这条管线，无需 Agent 再调用 resume。
        broker = ComputeNotifyBroker(harness.core)
        await broker._poll_all()
        await broker._poll_all()
        current = await asyncio.to_thread(get_process, ComputeDB(), first.pipeline_id)

        assert [step['purpose'] for step in submissions] == ['ts_opt', 'frequency']
        assert current['record']['job_steps'][0]['job_id'] == job_id
        assert current['record']['waiting_for'] == f'job:{submissions[1]["id"]}'
        assert current['declaration_revision'] == before['declaration_revision'] == 1
        assert current['record']['intervention_count'] == before['record']['intervention_count'] == 0
        assert harness.tool_events(agent)[0]['tool_name'] == 'ts_prepare'
        assert len(harness.tool_events(agent)) == 1
        assert harness.messages(agent) == messages_before
        assert harness.run_rows(agent) == runs_before
        assert provider.call_count() == calls_before
    finally:
        await harness.aclose()
