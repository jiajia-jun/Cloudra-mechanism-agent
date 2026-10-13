"""Final-file claims must match the authoritative DAG and approval version."""
import asyncio
import json

import pytest

from cloudra.dag.controller import DagController
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import AddEdge, AddNode, ElementaryStepEdge, GraphActor, MutationBatch, SpeciesNode
from cloudra.dag.review_requests import ReviewDecision
from cloudra.persistence.database import ConversationDB


async def controller(tmp_path):
    db = await asyncio.to_thread(lambda: ConversationDB('artifact-test', data_dir=tmp_path / 'runtime').init())
    c = DagController(db, 's1', 'dag_guided', working_directory=tmp_path)
    await c.initialize()
    revisions = await asyncio.to_thread(c.store.load_bundle)
    mutation = MutationBatch(session_id='s1', actor=GraphActor.HARNESS, actor_id='harness',
        base_revisions=revisions.revisions, rationale='declare the actual delivery', operations=[
            AddNode(op='add_node', graph='delivery', node=SpeciesNode(node_id='r', name='R', smiles='O')),
            AddNode(op='add_node', graph='delivery', node=SpeciesNode(node_id='p', name='P', smiles='O')),
            AddEdge(op='add_edge', graph='delivery', edge=ElementaryStepEdge(edge_id='e', name='step', source_node_id='r', target_node_id='p')),
        ])
    assert (await asyncio.to_thread(DagEngine(c.store).apply_batch, mutation)).accepted
    return c


def graph():
    return {'nodes': [{'id': 'R', 'role': 'reactant', 'smiles': ['O']},
                      {'id': 'P', 'role': 'product', 'smiles': ['O']},
                      {'id': 'TS', 'role': 'transition_state', 'smiles': []}],
            'edges': [{'id': 'step', 'from': 'R', 'to': 'P', 'via': 'TS'}]}


async def approve(c, request_id):
    request = await asyncio.to_thread(c.store.get_review_request, request_id)
    decision = ReviewDecision(request_id=request_id, basis_fingerprint=request.basis_fingerprint,
        verdict='accept', reason='allow an explicitly unverified partial')
    assert (await asyncio.to_thread(c.store.resolve_review, decision, expected_basis=request.basis_fingerprint))['accepted']
    return (await asyncio.to_thread(c.store.get_review_decision_for_request, request_id)).decision_id


@pytest.mark.asyncio
async def test_editing_final_file_invalidates_its_exit_approval(tmp_path):
    c = await controller(tmp_path)
    path = tmp_path / 'mechanism_graph.json'
    document = graph()
    await asyncio.to_thread(path.write_text, json.dumps(document))
    first = await c.audit_stop('partial')
    assert first.action == 'wait_review'
    await approve(c, first.request_id)
    unchanged = await c.audit_stop('partial')
    assert unchanged.action == 'allow_final', unchanged
    document['nodes'][0]['label'] = 'changed delivery statement'
    await asyncio.to_thread(path.write_text, json.dumps(document))

    changed = await c.audit_stop('partial')

    assert changed.action == 'wait_review'
    assert changed.request_id != first.request_id


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['wrong_species', 'foreign_edge', 'unsupported_barrier', 'unsupported_ts_log'])
async def test_invalid_file_claims_cannot_be_approved_as_partial(tmp_path, fault):
    c = await controller(tmp_path)
    document = graph()
    if fault == 'wrong_species':
        document['nodes'][0]['smiles'] = ['C']
    elif fault == 'foreign_edge':
        document['edges'][0]['from'], document['edges'][0]['to'] = 'P', 'R'
    elif fault == 'unsupported_barrier':
        document['edges'][0]['barrier_kcal_mol'] = 1.09
    else:
        document['nodes'][2]['properties'] = {'energy_hartree': -1.0, 'evidence_log': 'unbound.out'}
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))

    result = await c.audit_stop('partial')

    assert result.action == 'continue_work'
    assert not await asyncio.to_thread(c.store.list_review_requests, 'queued')


@pytest.mark.asyncio
async def test_changed_review_state_blocks_deferred_commit_without_graph_revision(tmp_path):
    from cloudra.dag.review_requests import ReviewRequest
    c = await controller(tmp_path)
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(graph()))
    first = await c.audit_stop('partial')
    await approve(c, first.request_id)
    assert (await c.audit_stop('partial')).action == 'allow_final'
    await asyncio.to_thread(c.store.enqueue_review, ReviewRequest(kind='evidence', requester='s1',
        target_ids=['r'], question='New evidence requires review', basis_fingerprint='sha256:new'))
    with pytest.raises(RuntimeError, match='changed|re-audit'):
        await c.commit_stop()


def bind_water(c, tmp_path):
    from pathlib import Path

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.models import AttachRef
    log = tmp_path / 'water.out'
    log.write_bytes((Path(__file__).parent / 'fixtures/gaussian/water_opt_freq_g16.out').read_bytes())
    snap = snapshot_evidence_file(log, tmp_path)
    ref = c.store.register_evidence('s1', 'water', snap.model_dump(mode='json'), source_type='file')
    assert DagEngine(c.store).apply_batch(MutationBatch(session_id='s1', actor=GraphActor.HARNESS,
        actor_id='harness', base_revisions=c.store.load_bundle().revisions, rationale='bind real water',
        operations=[AttachRef(op='attach_ref', graph='delivery', target_type='node', target_id='r', ref=ref)])).accepted
    return log, snap


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['false_energy', 'changed_log'])
async def test_declared_energy_and_log_must_match_the_bound_immutable_file(tmp_path, fault):
    c = await controller(tmp_path)
    log, snap = await asyncio.to_thread(bind_water, c, tmp_path)
    document = graph()
    document['nodes'][0]['properties'] = {'energy_hartree': snap.final_energy_hartree,
        'evidence_log': str(log)}
    if fault == 'false_energy':
        document['nodes'][0]['properties']['energy_hartree'] = -999.0
    else:
        await asyncio.to_thread(log.write_text, 'Replaced original log')
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))
    result = await c.audit_stop('partial')
    assert result.action == 'continue_work', result


@pytest.mark.asyncio
async def test_audit_rejects_report_graph_race(tmp_path, monkeypatch):
    from cloudra.dag.models import DeliveryReport
    c = await controller(tmp_path)
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(graph()))
    def raced_report():
        result = DeliveryReport(complete=True)
        c.store.register_evidence('s1', 'late evidence', {'new': True})
        return result
    monkeypatch.setattr(c, 'delivery_report', raced_report)
    assert (await c.audit_stop('complete')).action == 'continue_work'


@pytest.mark.asyncio
async def test_deferred_commit_keeps_immutable_artifact_receipt(tmp_path):
    c = await controller(tmp_path)
    path = tmp_path / 'mechanism_graph.json'
    await asyncio.to_thread(path.write_text, json.dumps(graph()))
    request = await c.audit_stop('partial')
    await approve(c, request.request_id)
    assert (await c.audit_stop('partial')).action == 'allow_final'
    await c.commit_stop()
    def receipt():
        with c.store.db.connect() as con:
            return json.loads(con.execute('SELECT report FROM dag_delivery_dispositions').fetchone()[0])
    saved = await asyncio.to_thread(receipt)
    from pathlib import Path
    snapshot = Path(saved['output_artifact']['snapshot_path'])
    before = await asyncio.to_thread(snapshot.read_bytes)
    await asyncio.to_thread(path.write_text, '{}')
    assert await asyncio.to_thread(snapshot.read_bytes) == before


@pytest.mark.asyncio
async def test_ts_cannot_borrow_other_logs_saddle_status(tmp_path):
    from pathlib import Path

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.models import AttachRef
    c = await controller(tmp_path)
    water, snap = await asyncio.to_thread(bind_water, c, tmp_path)
    def bind_step_logs():
        refs = []
        for path in (water, tmp_path / 'saddle.out'):
            if path.name == 'saddle.out':
                path.write_bytes((Path(__file__).parent / 'fixtures/benchmark_synthetic/ts_freq.out').read_bytes())
            snapshot = snapshot_evidence_file(path, tmp_path)
            refs.append(c.store.register_evidence('s1', path.name, snapshot.model_dump(mode='json'), source_type='file'))
        assert DagEngine(c.store).apply_batch(MutationBatch(session_id='s1', actor=GraphActor.HARNESS,
            actor_id='harness', base_revisions=c.store.load_bundle().revisions, rationale='attach attempt logs',
            operations=[AttachRef(op='attach_ref', graph='delivery', target_type='edge', target_id='e', ref=r)
                        for r in refs])).accepted
    await asyncio.to_thread(bind_step_logs)
    document = graph()
    document['nodes'][2]['properties'] = {'energy_hartree': snap.final_energy_hartree, 'evidence_log': str(water)}
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))
    result = await c.audit_stop('partial')
    assert result.action == 'continue_work'
    assert 'imaginary-frequency count' in result.reason


@pytest.mark.asyncio
async def test_commit_transaction_checks_state_after_final_validation(tmp_path, monkeypatch):
    c = await controller(tmp_path)
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(graph()))
    request = await c.audit_stop('partial')
    await approve(c, request.request_id)
    assert (await c.audit_stop('partial')).action == 'allow_final'
    actual_record = c.store.record_delivery_disposition
    def raced_record(*args, **kwargs):
        c.store.register_evidence('s1', 'late input', {'new': True})
        return actual_record(*args, **kwargs)
    monkeypatch.setattr(c.store, 'record_delivery_disposition', raced_record)
    with pytest.raises(RuntimeError, match='changed'):
        await c.commit_stop()
    def count():
        with c.store.db.connect() as con:
            return con.execute('SELECT COUNT(*) FROM dag_delivery_dispositions').fetchone()[0]
    assert await asyncio.to_thread(count) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['nonfinite_barrier', 'cross_type_ids', 'missing_ts', 'duplicate_nodes'])
async def test_malformed_artifact_claims_fail_before_review(tmp_path, fault):
    c = await controller(tmp_path)
    document = graph()
    if fault == 'nonfinite_barrier':
        document['edges'][0]['barrier_kcal_mol'] = 'NaN'
    elif fault == 'cross_type_ids':
        document['edges'][0]['id'] = 'R'
    elif fault == 'missing_ts':
        del document['edges'][0]['via']
        document['nodes'].pop()
    else:
        document['nodes'].append(dict(document['nodes'][0]))
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))
    assert (await c.audit_stop('partial')).action == 'continue_work'


@pytest.mark.asyncio
async def test_adding_file_requires_approval_of_that_file(tmp_path):
    c = await controller(tmp_path)
    request = await c.audit_stop('partial')
    await approve(c, request.request_id)
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(graph()))
    result = await c.audit_stop('partial')
    assert result.action == 'wait_review'
    assert result.request_id != request.request_id


def test_changed_source_during_snapshot_cannot_produce_mismatched_receipt(tmp_path, monkeypatch):
    from cloudra.dag import evidence_ingest
    path = tmp_path / 'mechanism_graph.json'
    path.write_text('{}')
    def mutate(source):
        path.write_text('{"changed": true}')
        return False, None, None, None, None, None
    monkeypatch.setattr(evidence_ingest, '_extract_qm_log', mutate)
    with pytest.raises(ValueError, match='changed during snapshot'):
        evidence_ingest.snapshot_evidence_file(path, tmp_path)


@pytest.mark.asyncio
async def test_consistent_real_minimum_energy_can_be_submitted_for_partial_review(tmp_path):
    c = await controller(tmp_path)
    log, snap = await asyncio.to_thread(bind_water, c, tmp_path)
    document = graph()
    document['nodes'][0]['properties'] = {'energy_hartree': round(snap.final_energy_hartree, 6),
        'evidence_log': str(log)}
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))
    result = await c.audit_stop('partial')
    assert result.action == 'wait_review', result


def test_benchmark_requires_file_but_ordinary_project_can_have_no_file(tmp_path):
    from cloudra.dag.delivery_artifact import prepare_delivery_artifact
    assert prepare_delivery_artifact(None, None, None, tmp_path) is None
    with pytest.raises(ValueError, match='requires mechanism_graph.json'):
        prepare_delivery_artifact(None, None, None, tmp_path, required=True)
