"""A zero-key Agent consumes the mode advisory and leaves the IRC running."""
import asyncio

import pytest

from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from tests.agent_scenarios import TS_SCENARIOS, ScenarioHarness, ScriptedProvider, Step
from tests.test_ts_mode_advisory_notify import irc_checkpoint, waiting_irc


@pytest.mark.asyncio
async def test_ts_mode_advisory_wakes_owner_while_irc_continues(tmp_path):
    """Consume a durable frequency notice through real wake, tools and background wait."""
    assert 'ts_mode_advisory_wakes_owner_while_irc_continues' in TS_SCENARIOS
    release = asyncio.Event()
    provider = ScriptedProvider(default=[Step(wait_for=release, stop=True)])
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        agent = await harness.spawn('small_mol', protocol='traditional')
        db, process_id, jobs = await asyncio.to_thread(
            waiting_irc, tmp_path, harness.project.id, agent.id,
        )
        before = await asyncio.to_thread(irc_checkpoint, db, process_id, jobs)
        release.set()
        await harness.wait_terminal(agent)
        provider.script_default(
            Step(tools=[('ts_inspect', {'run_id': 'mode-advisory'})]), Step(stop=True),
        )

        broker = ComputeNotifyBroker(harness.core)
        await broker._poll_project(harness.project.id)
        await harness.wait_for(lambda: len(harness.run_rows(agent)) == 2, 'mode advisory processing run')

        inspected = [row for row in harness.tool_events(agent) if row['tool_name'] == 'ts_inspect']
        assert len(inspected) == 1 and inspected[0]['is_success'], harness.describe(agent)
        assert inspected[0]['result_data']['frequency_analysis']['mode_alignment']['status'] == 'misaligned'
        events = harness.events(agent)
        notices = [event for event in events if event.type == 'agent.message_injected'
                   and (event.data.get('manifest') or {}).get('kind') == 'compute_completion']
        assert [event.data['manifest']['task_id'] for event in notices] == [jobs['frequency']]
        gates = [event for event in events if event.type == 'agent.completion_gate']
        assert gates[-1].data['action'] == 'wait_background'
        assert await asyncio.to_thread(irc_checkpoint, db, process_id, jobs) == before
        await broker._poll_project(harness.project.id)
        assert len(harness.run_rows(agent)) == 2
    finally:
        release.set()
        await harness.aclose()
