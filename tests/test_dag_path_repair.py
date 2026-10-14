"""Truthful partial artifacts and reviewed coverage share one source of truth."""
import asyncio
import json

import pytest

from cloudra.dag.controller import DagController
from cloudra.tools.Plantool.dag_tools.dag_review_step import DagReviewStep
from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
from cloudra.tools.Plantool.dag_tools.dag_view import DagView
from tests.dag_identity import call_dag_tool, make_supervisor
from tests.test_dag_async_evidence_review import FIXTURES_DIR, _coordinator, _seed_review_graph
from tests.test_dag_delivery_artifact import approve, controller, graph


@pytest.mark.asyncio
async def test_partial_unfound_ts_keeps_null_reference_and_scientific_gap(tmp_path):
    c = await controller(tmp_path)
    document = graph()
    document['nodes'].pop()
    document['edges'][0]['via'] = None
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))

    result = await c.audit_stop('partial')

    assert result.action == 'wait_review', result
    assert not result.report.complete
    assert result.report.unresolved
    await approve(c, result.request_id)
    final = await c.audit_stop('partial')
    assert final.action == 'allow_final', final
    assert not final.report.complete
    assert json.loads((tmp_path / 'mechanism_graph.json').read_text()) == document


@pytest.mark.asyncio
@pytest.mark.parametrize('exploratory_first', [False, True])
async def test_partial_preserves_unreviewed_competing_branch_without_dag_credit(tmp_path, exploratory_first):
    c = await controller(tmp_path)
    document = graph()
    document['nodes'].extend([
        {'id': 'explored', 'role': 'intermediate', 'smiles': ['CO']},
        {'id': 'candidate', 'role': 'transition_state', 'smiles': []},
    ])
    if exploratory_first:
        document['nodes'] = document['nodes'][3:] + document['nodes'][:3]
    document['edges'].append({'id': 'competing', 'from': 'R', 'to': 'explored', 'via': 'candidate'})
    path = tmp_path / 'mechanism_graph.json'
    await asyncio.to_thread(path.write_text, json.dumps(document))

    result = await c.audit_stop('partial')

    assert result.action == 'wait_review', result
    artifact = c._delivery_artifact
    assert artifact is not None
    assert 'explored' not in artifact.target_ids
    assert 'competing' not in artifact.target_ids
    assert not result.report.complete
    await approve(c, result.request_id)
    assert (await c.audit_stop('partial')).action == 'allow_final'
    assert json.loads(path.read_text()) == document


@pytest.mark.asyncio
@pytest.mark.parametrize('exploratory_first', [False, True])
async def test_partial_keeps_another_ts_attempt_for_the_same_endpoints(tmp_path, exploratory_first):
    c = await controller(tmp_path)
    document = graph()
    document['nodes'].append({'id': 'candidate-2', 'role': 'transition_state', 'smiles': []})
    document['edges'].append({'id': 'competing', 'from': 'R', 'to': 'P', 'via': 'candidate-2'})
    if exploratory_first:
        document['edges'].reverse()
    path = tmp_path / 'mechanism_graph.json'
    await asyncio.to_thread(path.write_text, json.dumps(document))

    result = await c.audit_stop('partial')

    assert result.action == 'wait_review', result
    artifact = c._delivery_artifact
    assert artifact.target_ids['step'] == 'e'
    assert 'competing' not in artifact.target_ids
    assert artifact.scientific_checks['competing']['connectivity']['status'] == 'unreviewed'
    assert artifact.scientific_checks['candidate-2']['saddle']['status'] == 'unreviewed'
    assert not result.report.complete
    await approve(c, result.request_id)
    assert (await c.audit_stop('partial')).action == 'allow_final'
    assert json.loads(path.read_text()) == document


@pytest.mark.asyncio
async def test_partial_exploration_does_not_replace_a_declared_step(tmp_path):
    c = await controller(tmp_path)
    document = graph()
    document['edges'][0]['id'] = 'unsubmitted-attempt'
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))

    result = await c.audit_stop('partial')

    assert result.action == 'continue_work'
    assert not await asyncio.to_thread(c.store.list_review_requests, 'queued')


@pytest.mark.asyncio
async def test_reviewed_stage_credit_is_shared_by_report_prompt_and_view(tmp_path):
    session, db, store = await asyncio.to_thread(_seed_review_graph, tmp_path, 'reviewed-view')
    agent = _coordinator(db.conversation_id)
    submitted = await call_dag_tool(DagSubmitStepEvidence, agent, session,
        step_name='step1', ts_file=str(FIXTURES_DIR / 'benchmark_synthetic/ts_freq.out'),
        irc_file=str(FIXTURES_DIR / 'gaussian/hcn_ts_irc_g16.log'))
    assert submitted.is_success
    reviewed = await call_dag_tool(DagReviewStep,
        make_supervisor(db.conversation_id, workspace_dir=str(tmp_path)), session,
        step_name='step1', verdict='supported', rationale='Inspect the submitted native files')
    assert reviewed.is_success
    c = DagController(db, session.id, 'dag_guided', conversation_id=db.conversation_id)
    report = await asyncio.to_thread(c.delivery_report)
    assert report.complete
    before = await asyncio.to_thread(store.load_snapshot)

    prompt = await c.prompt_projection()
    view = await call_dag_tool(DagView, agent, session)

    assert view.is_success
    assert view.result['unresolved_gaps'] == []
    assert view.result['steps'][0]['status'] == 'supported'
    assert 'missing_stage_evidence' not in prompt
    assert (await asyncio.to_thread(store.load_snapshot)).delivery == before.delivery
