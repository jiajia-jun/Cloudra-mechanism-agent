"""Evidence pairing keeps the Agent workspace through binding and review."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cloudra.base.session_class import Session
from cloudra.dag.controller import DagController
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    AddEdge,
    AddNode,
    ElementaryStepEdge,
    GraphActor,
    MutationBatch,
    OccurrenceNode,
    StageState,
)
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Chemtool.log_parser import LogParser
from cloudra.tools.Plantool.dag_tools.dag_bind_evidence import DagBindEvidence
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step
from tests.dag_identity import call_dag_tool, make_coordinator


def _seed_logs_and_step(workspace: Path, conversation_id: str) -> DagStore:
    workspace.mkdir(exist_ok=True)
    log = (
        '* O   R   C   A *\n'
        'THE OPTIMIZATION HAS CONVERGED\n'
        'FINAL SINGLE POINT ENERGY -100.0\n'
        'CARTESIAN COORDINATES (ANGSTROEM)\n'
        '-----------------------------\n'
        'C 0 0 0\nN 0 0 2\nH 0 0 1\n\n'
        'VIBRATIONAL FREQUENCIES\n'
        '0: -300.0 cm**-1\n1: 200.0 cm**-1\n'
        'ORCA TERMINATED NORMALLY\n'
    )
    (workspace / 'opt.out').write_text(log, encoding='utf-8')
    (workspace / 'freq.out').write_text(log.replace('-100.0', '-100.1'), encoding='utf-8')
    store = DagStore(ConversationDB(conversation_id).init())
    store.ensure_bundle('seed')
    seeded = DagEngine(store).apply_batch(MutationBatch(
        session_id='seed', actor=GraphActor.AGENT, actor_id='a-0',
        base_revisions=store.load_bundle().revisions,
        rationale='declare separate optimization and frequency evidence',
        operations=[
            AddNode(op='add_node', graph='delivery', node=OccurrenceNode(
                node_id='r', label='R', role='reactant')),
            AddNode(op='add_node', graph='delivery', node=OccurrenceNode(
                node_id='p', label='P', role='product')),
            AddEdge(op='add_edge', graph='delivery', edge=ElementaryStepEdge(
                edge_id='step1', source_node_id='r', target_node_id='p',
                stages=[StageState(kind='ts_opt'), StageState(kind='frequency')],
            )),
        ],
    ))
    assert seeded.accepted
    return store


@pytest.mark.asyncio
@pytest.mark.parametrize('batch', [False, True])
async def test_record_frequency_binding_reads_agent_workspace(tmp_path, monkeypatch, batch):
    """Real tools pair native logs in the sandbox while process cwd is elsewhere."""
    workspace = tmp_path / 'sandbox'
    source_dir = tmp_path / 'source'
    source_dir.mkdir()
    monkeypatch.chdir(source_dir)
    store = await asyncio.to_thread(_seed_logs_and_step, workspace, 'record-evidence-workspace')
    agent = make_coordinator(
        'record-evidence-workspace', orchestration_mode='dag_record', workspace_dir=str(workspace),
    )
    session = Session('s1', str(tmp_path / 'session.json'))
    controller = DagController(
        store.db, session.id, 'dag_record', working_directory=workspace,
    )
    attachments = []
    for kind, name in [('ts_opt', 'opt'), ('frequency', 'freq')]:
        parsed = await call_dag_tool(
            LogParser, agent, session, log_path=f'{name}.out',
            properties=['convergence', 'frequencies'],
        )
        assert parsed.is_success
        assert parsed.normal_termination is True
        assert parsed.opt_converged is True
        assert parsed.imaginary_frequencies == [-300.0]
        await controller.on_tool_finished(
            name, 'log_parser', {'log_path': f'{name}.out'}, parsed.model_dump(mode='json'),
        )
        attachments.append({'tool_call_id': name, 'bind_target': 'step1', 'stage_kind': kind})
    if batch:
        result = await call_dag_tool(DagBindEvidence, agent, session, attachments=attachments)
    else:
        for item in attachments:
            result = await call_dag_tool(DagBindEvidence, agent, session, attachments=[item])
            assert result.is_success, result.error
    assert result.is_success, result.error
    graph = await asyncio.to_thread(store.load_snapshot)
    assert [(stage.kind.value, stage.status.value) for stage in graph.delivery.edges[0].stages] == [
        ('ts_opt', 'supported'), ('frequency', 'supported'),
    ]


@pytest.mark.asyncio
async def test_guided_log_pair_survives_supervisor_review_in_other_cwd(tmp_path, monkeypatch):
    """Levers: workspace bridge, real parser, explicit submission and Supervisor verdict."""
    bind_ready, review_ready, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    bind_args = {'attachments': []}
    reviews = [{}, {}]
    provider = ScriptedProvider(by_role={
        'coordinator': [
            Step(tools=[('log_parser', {'log_path': 'opt.out', 'properties': ['convergence', 'frequencies']})]),
            Step(tools=[('log_parser', {'log_path': 'freq.out', 'properties': ['convergence', 'frequencies']})]),
            Step(wait_for=bind_ready, tools=[('dag_bind_evidence', bind_args)]),
            Step(wait_for=finish, stop=True),
        ],
        'supervisor': [
            Step(wait_for=review_ready, tools=[('dag_review_call', reviews[0])]),
            Step(tools=[('dag_review_call', reviews[1])]),
            Step(wait_for=finish, stop=True),
        ],
    })
    workspace, source_dir = tmp_path / 'sandbox', tmp_path / 'source'
    source_dir.mkdir()
    monkeypatch.chdir(source_dir)
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=workspace, provider=provider)
    try:
        store = await asyncio.to_thread(_seed_logs_and_step, workspace, harness.project.id)
        from cloudra.runtime_v2.schemas import Command

        updated = await harness.bus.execute(Command(
            type='role.update', target={'role_id': 'supervisor'},
            payload={'default_settings': {
                'orchestration_mode': 'dag_guided', 'invocation_protocol': 'traditional',
            }},
        ))
        assert updated.accepted
        agent = await harness.spawn('coordinator', protocol='traditional', orchestration_mode='dag_guided')
        await harness.wait_for(
            lambda: len([row for row in harness.tool_events(agent)
                         if row['tool_name'] == 'log_parser' and row['status'] == 'completed']) == 2,
            'both relative native logs parsed',
        )
        parsers = [row for row in harness.tool_events(agent) if row['tool_name'] == 'log_parser']
        assert all(row['started'] and not row['blocked'] and row['is_success'] for row in parsers)
        for row, kind in zip(parsers, ('ts_opt', 'frequency')):
            bind_args['attachments'].append({
                'tool_call_id': row['tool_call_id'], 'bind_target': 'step1', 'stage_kind': kind,
                'claim': f'the selected native log supports {kind}',
            })
        bind_ready.set()
        await harness.wait_for(
            lambda: any(row['tool_name'] == 'dag_bind_evidence' and row['status'] == 'completed'
                        for row in harness.tool_events(agent)),
            'explicit evidence submission',
        )
        submitted = next(row for row in harness.tool_events(agent) if row['tool_name'] == 'dag_bind_evidence')
        assert submitted['is_success'], submitted
        inbox = await asyncio.to_thread(store.list_call_reviews, 'pending', source='explicit')
        for args, kind in zip(reviews, ('ts_opt', 'frequency')):
            pending = next(item for item in inbox if item.suggested_stage == kind)
            args.update(review_id=pending.review_id, target_id='step1', stage_kind=kind, verdict='agree')
        review_ready.set()
        await harness.wait_for(
            lambda: len([row for supervisor in harness.core.agents.values()
                         if supervisor.role_id == 'supervisor'
                         for row in harness.tool_events(supervisor)
                         if row['tool_name'] == 'dag_review_call' and row['status'] == 'completed']) == 2,
            'both Supervisor stage verdicts',
        )
        reviewed = [row for supervisor in harness.core.agents.values()
                    if supervisor.role_id == 'supervisor'
                    for row in harness.tool_events(supervisor) if row['tool_name'] == 'dag_review_call']
        assert all(row['started'] and not row['blocked'] and row['is_success'] for row in reviewed), [row['result_data'] for row in reviewed]
        assert all(row['result_data']['accepted'] and row['result_data']['result']['stage_changed']
                   for row in reviewed), reviewed
        graph = await asyncio.to_thread(store.load_snapshot)
        assert [(stage.kind.value, stage.status.value) for stage in graph.delivery.edges[0].stages] == [
            ('ts_opt', 'supported'), ('frequency', 'supported'),
        ]
    finally:
        await harness.aclose()
        bind_ready.set()
        review_ready.set()
        finish.set()
