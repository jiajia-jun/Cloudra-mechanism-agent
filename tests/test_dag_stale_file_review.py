"""Removed delivery targets leave readable history without hanging Supervisor reads."""

from __future__ import annotations

import asyncio
import shutil

import pytest

from cloudra.dag.engine import DagEngine
from cloudra.dag.evidence_ingest import snapshot_evidence_file
from cloudra.dag.file_science import file_scientific_checks
from cloudra.dag.models import (
    AddEdge,
    AddNode,
    ElementaryStepEdge,
    GraphActor,
    MutationBatch,
    OccurrenceNode,
    RemoveEdge,
    RemoveNode,
)
from cloudra.dag.review_requests import ReviewDecision, ReviewRequest
from cloudra.dag.store import InvalidGraphReference
from cloudra.dag.supervisor_tools import SupervisorToolExecutor
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, supervisor_stale_file_review_steps
from tests.dag_identity import make_supervisor
from tests.test_dag_async_evidence_review import FIXTURES_DIR, _seed_review_graph


def _stale_review(tmp_path, project, kind='step'):
    session, db, store = _seed_review_graph(tmp_path, project)
    native = tmp_path / 'minimum.out'
    shutil.copyfile(FIXTURES_DIR/'gaussian/water_opt_freq_g16.out', native)
    snapshot = snapshot_evidence_file(native, tmp_path, db.conversation_id)
    ref = store.register_evidence(session.id, native.name, snapshot.model_dump(mode='json'), source_type='file')
    target_id = 'step1' if kind == 'step' else 'r'
    request = ReviewRequest(kind='evidence', requester='coordinator', target_ids=[target_id],
        question='Does the original calculation support this target?', supporting_refs=[ref],
        proposal={'element_type': kind, 'original_file': str(native)}, basis_fingerprint='pending')
    basis = store.review_basis(request)
    request_id = store.enqueue_review(request.model_copy(update={'basis_fingerprint': basis}))
    decision = ReviewDecision(request_id=request_id, basis_fingerprint=basis, verdict='needs_evidence',
        reason='The original submission needs direction evidence.', next_action='Inspect the original endpoints.', evidence_refs=[ref])
    assert store.resolve_review(decision, expected_basis=basis)['accepted']
    operations = [RemoveEdge(op='remove_edge', graph='delivery', edge_id='step1')]
    if kind == 'species':
        operations += [RemoveNode(op='remove_node', graph='delivery', node_id='r'),
            AddNode(op='add_node', graph='delivery', node=OccurrenceNode(node_id='replacement', label='R', role='reactant'))]
    else:
        operations += [AddEdge(op='add_edge', graph='delivery', edge=ElementaryStepEdge(
            edge_id='replacement', name='step1', source_node_id='r', target_node_id='p'))]
    removed = DagEngine(store).apply_batch(MutationBatch(session_id=session.id, actor=GraphActor.HARNESS,
        actor_id='test-harness', base_revisions=store.load_bundle().revisions,
        rationale='Replace the original target after new evidence.', operations=operations))
    assert removed.accepted
    return session, db, store, request_id, target_id


@pytest.mark.asyncio
async def test_removed_target_exception_returns_through_to_thread(tmp_path):
    _, _, store, _, target_id = await asyncio.to_thread(_stale_review, tmp_path, 'stale-file-thread')
    graph = (await asyncio.to_thread(store.load_snapshot)).delivery
    with pytest.raises(InvalidGraphReference):
        await asyncio.wait_for(asyncio.to_thread(file_scientific_checks, store, graph, target_id), timeout=2)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['species', 'step'])
async def test_supervisor_reads_removed_target_history_without_credit_or_retargeting(tmp_path, kind):
    session, db, store, review_id, target_id = await asyncio.to_thread(_stale_review, tmp_path, f'stale-file-{kind}', kind)
    before = await asyncio.to_thread(store.load_snapshot)
    request = await asyncio.to_thread(store.get_review_request, review_id)
    decision = await asyncio.to_thread(store.get_review_decision_for_request, review_id)
    executor = SupervisorToolExecutor(project_id=db.conversation_id, workspace_root=str(tmp_path))
    executor.bind_run(agent=make_supervisor(db.conversation_id, workspace_dir=str(tmp_path)), session=session)
    result = await asyncio.wait_for(executor.execute('dag_view_evidence', {'review_id': review_id}), timeout=2)
    assert result['is_success'], result
    history = result['result']
    assert history['target_ids'] == [target_id]
    assert history['question'] == request.question
    assert history['proposal'] == request.proposal
    assert history['supporting_refs'] == [ref.model_dump(mode='json') for ref in request.supporting_refs]
    assert history['decision'] == decision.model_dump(mode='json')
    assert history['message']
    assert 'scientific_checks' not in history
    attempted = await executor.execute('dag_review_evidence', {
        'request_id': review_id, 'verdict': 'accept', 'reason': 'The historical record was read.'})
    assert not attempted['is_success']
    assert await asyncio.to_thread(store.load_snapshot) == before
    assert await asyncio.to_thread(store.get_review_request, review_id) == request
    assert await asyncio.to_thread(store.get_review_decision_for_request, review_id) == decision
    # Viewing history must not make it a current review or satisfy replacement stages.
    assert await asyncio.to_thread(store.list_review_requests, state='queued') == []
    graph = (await asyncio.to_thread(store.load_snapshot)).delivery
    assert all(stage.ref is None for element in [*graph.nodes, *graph.edges] for stage in element.stages)


@pytest.mark.asyncio
async def test_supervisor_stale_file_read_finishes_and_reaches_the_next_model_turn(tmp_path):
    """Levers: actual Supervisor adapter, offloaded file query, tool completion and next-turn context."""
    provider = ScriptedProvider()
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        _, _, store, review_id, target_id = await asyncio.to_thread(_stale_review, tmp_path, harness.project.id)
        provider.script('supervisor', *supervisor_stale_file_review_steps(review_id))
        agent = await harness.spawn('supervisor', protocol='traditional', orchestration_mode='dag_guided')
        await harness.wait_terminal(agent)
        reads = [row for row in harness.tool_events(agent) if row['tool_name'] == 'dag_view_evidence']
        assert len(reads) == 1 and reads[0]['status'] == 'completed', harness.describe(agent)
        assert reads[0]['is_success'], reads
        history = reads[0]['result_data']['result']
        assert history['target_ids'] == [target_id] and history['review_id'] == review_id
        assert 'scientific_checks' not in history
        assert provider.call_count('supervisor') == 2
        assert any(message.get('role') == 'tool' and review_id in str(message.get('content', ''))
            for role, messages in provider.calls[1:] if role == 'supervisor' for message in messages)
        assert await asyncio.to_thread(store.list_review_requests, state='queued') == []
    finally:
        await harness.aclose()
