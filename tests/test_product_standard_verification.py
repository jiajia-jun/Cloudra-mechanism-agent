"""Ordinary standard-mode projects retain scientific TS verification capabilities."""

from pathlib import Path

import pytest

pytest.importorskip('rdkit')

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command, OrchestrationMode
from cloudra.runtime_v2.tool_catalog import guest_tool_names, wire_tool_schemas
from tests.test_ts_guess import (
    _HCN_XYZ,
    _HNC_XYZ,
    _TS_FREQ_WITH_GEOMETRY,
    IRC_LOG,
    _endpoint_optimization_logs,
)


@pytest.mark.asyncio
@pytest.mark.parametrize('strict,evidence,status', [
    (False, 'complete', 'candidate'),
    (True, 'complete', 'pass'),
    (True, 'missing', 'inconclusive'),
    (True, 'wrong_identity', 'fail'),
])
async def test_product_standard_runs_real_ts_verification(tmp_path, strict, evidence, status):
    """Mode must not disable verification or bypass its frequency/IRC evidence checks."""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type='project.create', payload={
        'name': 'Ordinary chemistry project', 'workspace_dir': str(tmp_path),
        'settings': {'orchestration_mode': 'standard'},
    }))
    project = next(iter(core.projects.values()))
    spawned = await bus.execute(Command(type='agent.spawn', target={'project_id': project.id},
        payload={'role_id': 'coordinator', 'settings': {'invocation_protocol': 'traditional'}}))
    agent = spawned.data
    assert agent.settings.orchestration_mode is OrchestrationMode.STANDARD
    assert project.settings.benchmark_task_id is None
    assert 'ts_guess' in guest_tool_names(['ts_guess'], orchestration_mode=agent.settings.orchestration_mode,
                                        role_id=agent.role_id)
    assert 'ts_guess' in {schema['function']['name'] for schema in wire_tool_schemas(agent, ['ts_guess'])}

    freq_log = tmp_path / 'ts_freq.log'
    freq_log.write_text(_TS_FREQ_WITH_GEOMETRY)
    arguments = dict(mode='verify', strict=strict, freq_log=freq_log.name, irc_log=str(IRC_LOG),
        reactant_text=_HCN_XYZ, product_text=_HNC_XYZ, watch_pairs=[[1, 3], [2, 3]],
        output_dir='verified')
    if strict and evidence != 'missing':
        logs = _endpoint_optimization_logs(tmp_path,
            product_xyz=_HCN_XYZ if evidence == 'wrong_identity' else _HNC_XYZ)
        arguments.update(reactant_logs=logs['reactant'], product_logs=logs['product'])

    result = await LegacyToolExecutor(core).execute(agent,
        ToolCall(id='verify', name='ts_guess', arguments=arguments))
    assert result.is_success, result.summary
    assert result.data['verification_status'] == status, result.data['checks']
    assert result.data['n_imag'] == 1
    assert result.data['imag_freqs'] == [pytest.approx(-915.34, abs=0.01)]
    assert result.data['checks']
    for field in ('irc_end_a_path', 'irc_end_b_path'):
        assert Path(result.data[field]).is_file()
