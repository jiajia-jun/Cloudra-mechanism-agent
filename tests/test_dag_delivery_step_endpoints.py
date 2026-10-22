"""Delivery retains each reviewed step's native endpoint chain outside the DAG DB."""
import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from cloudra.dag.controller import DagController
from cloudra.dag.delivery_artifact import prepare_delivery_artifact
from cloudra.dag.engine import DagEngine
from cloudra.dag.evidence_ingest import snapshot_evidence_file
from cloudra.dag.models import AddEdge, AttachRef, ElementaryStepEdge, GraphActor, MutationBatch, UpdateNode
from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
from tests.dag_identity import call_dag_tool, make_coordinator
from tests.test_dag_async_evidence_review import _seed_review_graph
from tests.test_dag_delivery_artifact import approve
from tests.test_irc_endpoint_optimization import write_lineage_bundle


def _seed_native_chains(tmp_path):
    session, db, store = _seed_review_graph(tmp_path, 'step-endpoint-delivery')
    bundles = [write_lineage_bundle(tmp_path / name) for name in ('first', 'second')]
    # Distinct native geometries of the same endpoint species and their own IRC.
    # All these small logs are synthetic parser contract data, never QM results.
    for path in bundles[1].values():
        if isinstance(path, Path):
            path.write_text('# synthetic second calculation\n' + path.read_text().replace('-1.06000000', '-1.08000000')
                .replace('2.17000000', '2.19000000').replace('-1.25000000', '-1.35000000')
                .replace('2.35000000', '2.45000000'))
    for path in (tmp_path / 'second').glob('*.xyz'):
        path.write_text(path.read_text().replace('-1.250000', '-1.350000')
            .replace('2.350000', '2.450000'))
    operations = [
        UpdateNode(op='update_node', graph='delivery', node_id='r', changes={'smiles': 'C#N'}),
        UpdateNode(op='update_node', graph='delivery', node_id='p', changes={'smiles': '[C-]#[NH+]'}),
        AddEdge(op='add_edge', graph='delivery', edge=ElementaryStepEdge(
            edge_id='step2', name='step2', source_node_id='r', target_node_id='p')),
    ]
    expected = {}
    for index, bundle in enumerate(bundles, 1):
        expected[f'step{index}'] = {}
        for node_id, side, prefix in [('r', 'source', 'reactant'), ('p', 'target', 'product')]:
            expected[f'step{index}'][side] = []
            for kind in ('opt', 'freq'):
                path = bundle[f'{prefix}_{kind}']
                snapshot = snapshot_evidence_file(path, tmp_path)
                ref = store.register_evidence('s1', path.name, snapshot.model_dump(mode='json'), source_type='file')
                operations.append(AttachRef(op='attach_ref', graph='delivery', target_type='node', target_id=node_id, ref=ref))
                expected[f'step{index}'][side].append({'path': str(Path(snapshot.snapshot_path).relative_to(tmp_path)),
                                                     'sha256': snapshot.sha256})
    result = DagEngine(store).apply_batch(MutationBatch(session_id='s1', actor=GraphActor.HARNESS,
        actor_id='test', base_revisions=store.load_bundle().revisions,
        rationale='retain two real native-shaped endpoint chains for the shared species', operations=operations))
    assert result.accepted, result
    return session, db, bundles, expected


async def _delivery(tmp_path):
    session, db, bundles, expected = await asyncio.to_thread(_seed_native_chains, tmp_path)
    agent = make_coordinator(db.conversation_id, orchestration_mode='dag_guided', workspace_dir=str(tmp_path))
    for index, bundle in enumerate(bundles, 1):
        submitted = await call_dag_tool(DagSubmitStepEvidence, agent, session,
            step_name=f'step{index}', ts_file=str(bundle['ts']), irc_file=str(bundle['irc']),
            source_minimum_file=str(bundle['reactant_freq']), target_minimum_file=str(bundle['product_freq']))
        assert submitted.is_success, submitted
        assert submitted.result['scientific_checks']['short_irc']['status'] == 'passed', submitted.result['scientific_checks']['short_irc']
    document = {'nodes': [
        {'id': 'r', 'role': 'reactant', 'smiles': ['C#N']},
        {'id': 'p', 'role': 'product', 'smiles': ['[C-]#[NH+]']},
        {'id': 'TS1', 'role': 'transition_state', 'smiles': []},
        {'id': 'TS2', 'role': 'transition_state', 'smiles': []}],
        'edges': [{'id': f'step{index}', 'from': 'r', 'to': 'p', 'via': f'TS{index}'} for index in (1, 2)]}
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))
    controller = DagController(db, 's1', 'dag_guided', working_directory=tmp_path)
    await controller.initialize()
    return controller, expected


@pytest.mark.asyncio
async def test_prepare_retains_each_steps_reviewed_endpoint_chain_without_publishing(tmp_path, rdkit_chemistry):
    controller, expected = await _delivery(tmp_path)
    snapshot = await asyncio.to_thread(controller.engine.snapshot)
    report = await asyncio.to_thread(controller.delivery_report)
    artifact = await asyncio.to_thread(prepare_delivery_artifact, controller.store,
        snapshot.delivery, report, tmp_path, disposition='partial')

    actual = artifact.step_endpoint_evidence
    for edge_id in ('step1', 'step2'):
        for side in ('source', 'target'):
            assert sorted(actual[edge_id][side], key=lambda row: row['path']) == sorted(expected[edge_id][side], key=lambda row: row['path'])
    from cloudra.persistence.paths import mechanism_evidence_path
    assert not mechanism_evidence_path(tmp_path).exists()


@pytest.mark.asyncio
async def test_only_committed_delivery_publishes_graph_bound_step_evidence(tmp_path, rdkit_chemistry):
    from cloudra.benchmark.delivery_evidence import read_step_endpoint_evidence
    from cloudra.persistence.paths import mechanism_evidence_path

    controller, expected = await _delivery(tmp_path)
    path = mechanism_evidence_path(tmp_path)
    request = await controller.audit_stop('partial')
    assert request.action == 'wait_review'
    assert not path.exists()
    await approve(controller, request.request_id)
    assert (await controller.audit_stop('partial')).action == 'allow_final'
    assert not path.exists()

    await controller.commit_stop()

    digest = hashlib.sha256((tmp_path / 'mechanism_graph.json').read_bytes()).hexdigest()
    # A DB-free consumer sees both independent source/target chains.
    actual = await asyncio.to_thread(read_step_endpoint_evidence, tmp_path, digest)
    for edge_id in ('step1', 'step2'):
        for side in ('source', 'target'):
            assert sorted(actual[edge_id][side]) == sorted(row['path'] for row in expected[edge_id][side])
    before = path.read_bytes()
    graph_path = tmp_path / 'mechanism_graph.json'
    document = json.loads(graph_path.read_text())
    document['nodes'][0]['label'] = 'changed delivery awaiting approval'
    graph_path.write_text(json.dumps(document))
    assert (await controller.audit_stop('partial')).action == 'wait_review'
    assert path.read_bytes() == before
