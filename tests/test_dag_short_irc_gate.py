"""Native IRC proof gates complete claims without forbidding honest partial delivery."""

import asyncio
import json

import pytest

from cloudra.dag.controller import DagController
from cloudra.dag.engine import DagEngine
from cloudra.dag.models import (
    AddEdge,
    AddNode,
    ClaimSpec,
    ElementaryStepEdge,
    GraphActor,
    MechanismDraft,
    MutationBatch,
    OccurrenceNode,
    StageState,
    UpdateEdge,
)
from cloudra.dag.review_requests import ReviewDecision
from cloudra.persistence.database import ConversationDB
from cloudra.tools.core.qm_log_facts import read_qm_log
from tests.test_irc_endpoint_optimization import write_lineage_bundle


async def _native_controller(tmp_path, *, version=1, broken=None, mode='dag_record'):
    paths = write_lineage_bundle(tmp_path)
    if broken == 'wrong_ts':
        paths['irc'].write_text(paths['irc'].read_text().replace('0.50000000', '0.70000000'))
    elif broken == 'bad_log':
        paths['irc'].write_text('This is not a native IRC log.\n')
    db = await asyncio.to_thread(lambda: ConversationDB('irc-gate', data_dir=tmp_path / 'data').init())
    controller = DagController(db, 's1', mode, conversation_id='irc-gate', working_directory=tmp_path)
    await controller.initialize()
    refs = {}
    for name in ('ts', 'reactant_opt', 'reactant_freq', 'product_opt', 'product_freq', 'irc'):
        facts = await asyncio.to_thread(read_qm_log, paths[name])
        arguments = {} if broken == 'no_log' and name == 'irc' else {'log_path': str(paths[name])}
        delta = await controller.on_tool_finished(name, 'log_parser', arguments, {
            'is_success': True, 'normal_termination': facts.normal_termination,
            'opt_converged': facts.opt_converged, 'frequencies_cm': facts.frequencies_cm,
            'imaginary_frequencies': [f for f in facts.frequencies_cm or [] if f < 0],
        })
        refs[name] = delta.evidence_ref
    if broken == 'missing_file':
        paths['irc'].unlink()
    operations = [
        AddNode(op='add_node', graph='delivery', node=OccurrenceNode(
            node_id='r', label='R', role='reactant', smiles=paths['reactant_smiles'],
            refs=[] if broken == 'missing_opt' else [refs['reactant_opt']],
            stages=[StageState(kind='geometry')])),
        AddNode(op='add_node', graph='delivery', node=OccurrenceNode(
            node_id='p', label='P', role='product',
            smiles='N#N' if broken == 'wrong_species' else paths['product_smiles'],
            refs=[] if broken == 'missing_product_opt' else [refs['product_opt']],
            stages=[StageState(kind='geometry')])),
        AddEdge(op='add_edge', graph='delivery', edge=ElementaryStepEdge(
            edge_id='step1', source_node_id='r', target_node_id='p',
            stages=[StageState(kind=kind) for kind in ('ts_opt', 'frequency', 'short_irc')])),
    ]
    seeded = await asyncio.to_thread(lambda: DagEngine(controller.store).apply_batch(MutationBatch(
        session_id='s1', actor=GraphActor.AGENT, actor_id='a-0',
        base_revisions=controller.store.load_bundle().revisions,
        rationale='Declare a native short IRC proof', operations=operations)))
    assert seeded.accepted, seeded
    if version == 2:
        await asyncio.to_thread(controller.store.save_draft, MechanismDraft(
            operations=[operations[0]], rationale='Accepted v2 evidence contract', state='accepted',
            contract_version=2, claim_spec=ClaimSpec(kind='mechanism', scope={'targets': ['step1']},
                required_checks={'stationary_point', 'curvature'})), actor_id='a-0')
    for target, stage, name in [('r', 'geometry', 'reactant_freq'), ('p', 'geometry', 'product_freq'),
                                ('step1', 'ts_opt', 'ts'), ('step1', 'frequency', 'ts')]:
        bound = await controller.apply_stage_bind(element_id=target, stage_kind=stage, ref=refs[name],
            verdict='agree', tool_succeeded=True)
        assert bound.accepted, bound
    return controller, refs


async def _bind_irc(controller, refs, *, batch, broken=None):
    name = 'reactant_freq' if broken == 'non_irc' else 'irc'
    if batch:
        return await controller.bind_stage_attachments([
            {'tool_call_id': name, 'bind_target': 'step1', 'stage_kind': 'short_irc'}])
    result = await controller.apply_stage_bind(element_id='step1', stage_kind='short_irc', ref=refs[name],
        verdict='agree', tool_succeeded=True)
    return result.model_dump()


def _recorded_dispositions(controller):
    with controller.db.connect() as con:
        return con.execute('SELECT disposition FROM dag_delivery_dispositions').fetchall()


@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('batch', [False, True])
@pytest.mark.parametrize('broken', ['no_log', 'missing_file', 'bad_log', 'non_irc',
                                   'wrong_ts', 'wrong_species', 'missing_opt'])
@pytest.mark.asyncio
async def test_invalid_native_chain_cannot_support_short_irc(tmp_path, rdkit_chemistry, version, batch, broken):
    controller, refs = await _native_controller(tmp_path, version=version, broken=broken)

    result = await _bind_irc(controller, refs, batch=batch, broken=broken)

    assert not result['accepted'], result
    assert result['rejection_code'] == 'short_irc_check_failed'
    edge = (await asyncio.to_thread(controller.store.load_snapshot)).delivery.edges[0]
    assert edge.stages[-1].status.value == 'pending'
    assert not (await asyncio.to_thread(controller.delivery_report)).complete
    assert (await controller.audit_stop('complete')).action == 'continue_work'


@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('batch', [False, True])
@pytest.mark.asyncio
async def test_valid_short_unconverged_irc_still_completes(tmp_path, rdkit_chemistry, version, batch):
    controller, refs = await _native_controller(tmp_path, version=version)

    result = await _bind_irc(controller, refs, batch=batch)

    assert result['accepted'], result
    edge = (await asyncio.to_thread(controller.store.load_snapshot)).delivery.edges[0]
    assert edge.stages[-1].status.value == 'supported'
    assert '[warning]' in edge.stages[-1].reason  # Non-monotone intervals remain advisory.
    assert (await asyncio.to_thread(controller.delivery_report)).complete
    gate = await controller.audit_stop('complete')
    assert gate.action == 'allow_final'
    assert gate.basis == 'dag_verified'


@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('batch', [False, True])
@pytest.mark.parametrize('side,stage_kind', [('reactant', 'endpoint_b'), ('product', 'endpoint_a')])
@pytest.mark.parametrize('endpoint_proof', ['valid', 'wrong_start', 'missing'])
@pytest.mark.asyncio
async def test_bound_endpoint_stage_proof_survives_complete_audit(
        tmp_path, rdkit_chemistry, version, batch, side, stage_kind, endpoint_proof):
    # A missing selected stage must not silently fall back to an older valid node proof.
    missing_optimization = 'missing_opt' if side == 'reactant' else 'missing_product_opt'
    controller, refs = await _native_controller(tmp_path, version=version,
        broken=None if endpoint_proof == 'missing' else missing_optimization)

    def write_endpoint():
        frequency = (tmp_path / f'{side}_freq.out').read_text()
        section = frequency[frequency.index('VIBRATIONAL FREQUENCIES'):
                            frequency.index('****ORCA TERMINATED NORMALLY****')]
        optimization = (tmp_path / f'{side}_opt.out').read_text()
        if endpoint_proof == 'wrong_start':
            optimization = optimization.replace('-1.25000000' if side == 'reactant' else '2.35000000',
                                                '-1.65000000' if side == 'reactant' else '2.75000000', 1)
        path = tmp_path / f'{side}_endpoint.out'
        path.write_text(optimization.replace('****ORCA TERMINATED NORMALLY****',
            section + '****ORCA TERMINATED NORMALLY****'))
        return path, read_qm_log(path)

    path, facts = await asyncio.to_thread(write_endpoint)
    delta = await controller.on_tool_finished(side + '_endpoint', 'log_parser',
        {'log_path': str(path)}, {'is_success': True,
            'normal_termination': facts.normal_termination, 'opt_converged': facts.opt_converged,
            'frequencies_cm': facts.frequencies_cm, 'imaginary_frequencies': []})
    snapshot = await asyncio.to_thread(controller.store.load_snapshot)
    edge = snapshot.delivery.edges[0]
    # Version 1 binds in declared order; both versions use the same endpoint material.
    stages = [*edge.stages[:-1], StageState(kind=stage_kind), edge.stages[-1]]
    mutation = await asyncio.to_thread(controller.engine.apply_batch, MutationBatch(
        session_id='s1', actor=GraphActor.HARNESS, actor_id='endpoint-proof',
        base_revisions=snapshot.bundle.revisions, rationale='Bind endpoint optimization to its step stage',
        operations=[UpdateEdge(op='update_edge', graph='delivery', edge_id='step1',
            changes={'stages': [stage.model_dump(mode='json') for stage in stages]})]))
    assert mutation.accepted, mutation
    bound = await controller.apply_stage_bind(element_id='step1', stage_kind=stage_kind,
        ref=delta.evidence_ref, verdict='agree', tool_succeeded=True)
    assert bound.accepted, bound
    if endpoint_proof == 'missing':
        await asyncio.to_thread(path.unlink)

    irc = await _bind_irc(controller, refs, batch=batch)
    if endpoint_proof != 'valid':
        assert not irc['accepted'], irc
        assert irc['rejection_code'] == 'short_irc_check_failed'
        assert (await controller.audit_stop('complete')).action == 'continue_work'
        return

    assert irc['accepted'], irc
    assert (await asyncio.to_thread(controller.delivery_report)).complete
    gate = await controller.audit_stop('complete')
    assert gate.action == 'allow_final', gate
    assert gate.basis == 'dag_verified'
    # Commit must recheck the exact bound stage dependency, not only node files.
    await asyncio.to_thread(path.unlink)
    with pytest.raises(RuntimeError, match='Required IRC direction proof changed after audit'):
        await controller.commit_stop()
    assert await asyncio.to_thread(_recorded_dispositions, controller) == []


@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('mode', ['dag_record', 'dag_guided'])
@pytest.mark.parametrize('disposition', ['complete', 'partial'])
@pytest.mark.asyncio
async def test_missing_irc_keeps_complete_and_partial_distinct(
        tmp_path, rdkit_chemistry, version, mode, disposition):
    controller, _refs = await _native_controller(tmp_path, version=version, mode=mode)
    original_report = await asyncio.to_thread(controller.delivery_report)

    gate = await controller.audit_stop(disposition)

    assert not gate.report.complete
    assert await asyncio.to_thread(_recorded_dispositions, controller) == []
    if disposition == 'complete':
        assert gate.action == 'continue_work'
        assert gate.basis is None
        assert any(gap.code == 'short_irc_check_failed' for gap in gate.report.unresolved)
        assert controller._pending_stop is None
        return

    assert gate.report == original_report
    assert any(gap.code == 'missing_stage_evidence' and 'short_irc' in gap.detail
               for gap in gate.report.unresolved)
    if mode == 'dag_guided':
        assert gate.action == 'wait_review'
        assert gate.basis is None
        assert controller._pending_stop is None
        await controller.commit_stop()
        assert await asyncio.to_thread(_recorded_dispositions, controller) == []
        request = await asyncio.to_thread(controller.store.get_review_request, gate.request_id)
        assert request.kind == 'exit'
        assert request.proposal['disposition'] == 'partial'
        assert request.proposal['remaining_gaps'] == [
            gap.model_dump(mode='json') for gap in [*gate.report.unresolved, *gate.report.inconclusive]]
        decision = ReviewDecision(request_id=request.request_id,
            basis_fingerprint=request.basis_fingerprint, verdict='accept',
            reason='Accept the partial result with the IRC evidence gap explicitly retained.')
        assert (await asyncio.to_thread(controller.store.resolve_review, decision,
            expected_basis=request.basis_fingerprint))['accepted']
        approved = await controller.audit_stop('partial')
        assert approved.action == 'allow_final'
        assert approved.basis == 'supervisor_approved'
        assert approved.request_id == gate.request_id
        assert approved.report == original_report
    else:
        assert gate.action == 'allow_final'
        assert gate.basis == 'partial_recorded'

    await controller.commit_stop()
    assert await asyncio.to_thread(_recorded_dispositions, controller) == [('partial',)]
    assert not (await asyncio.to_thread(controller.delivery_report)).complete


@pytest.mark.parametrize('status', ['supported', 'skipped', 'not_applicable'])
@pytest.mark.parametrize('disposition', ['complete', 'partial'])
@pytest.mark.asyncio
async def test_stage_label_cannot_replace_native_irc_proof(tmp_path, rdkit_chemistry, status, disposition):
    controller, refs = await _native_controller(tmp_path)
    edge = (await asyncio.to_thread(controller.store.load_snapshot)).delivery.edges[0]
    stages = [*edge.stages[:-1], StageState(kind='short_irc', status=status,
        ref=refs['reactant_freq'] if status == 'supported' else None,
        reason='A saved label is not native direction evidence.')]
    # Simulate persisted pre-fix state, including #237's false SUPPORTED label.
    result = await asyncio.to_thread(lambda: controller.engine.apply_batch(MutationBatch(
        session_id='s1', actor=GraphActor.HARNESS, actor_id='saved-state',
        base_revisions=controller.store.load_bundle().revisions,
        rationale='Replay a previously saved stage label', operations=[UpdateEdge(
            op='update_edge', graph='delivery', edge_id='step1',
            changes={'stages': [stage.model_dump(mode='json') for stage in stages]})])))
    assert result.accepted

    gate = await controller.audit_stop(disposition)

    if disposition == 'complete':
        assert gate.action == 'continue_work'
        assert not gate.report.complete
        assert any(gap.code == 'short_irc_check_failed' for gap in gate.report.unresolved)
        assert controller._pending_stop is None
    else:
        assert gate.action == 'allow_final'
        assert gate.basis == 'partial_recorded'
        assert gate.report == await asyncio.to_thread(controller.delivery_report)
        await controller.commit_stop()
        assert await asyncio.to_thread(_recorded_dispositions, controller) == [('partial',)]


@pytest.mark.parametrize('disposition', ['complete', 'partial'])
@pytest.mark.asyncio
async def test_only_complete_requires_native_log_to_remain_available(tmp_path, rdkit_chemistry, disposition):
    controller, refs = await _native_controller(tmp_path)
    assert (await _bind_irc(controller, refs, batch=False))['accepted']
    await asyncio.to_thread((tmp_path / 'irc.out').unlink)

    gate = await controller.audit_stop(disposition)

    if disposition == 'complete':
        assert gate.action == 'continue_work'
        assert not gate.report.complete
        assert any(gap.code == 'short_irc_check_failed' for gap in gate.report.unresolved)
    else:
        assert gate.action == 'allow_final'
        assert gate.basis == 'partial_recorded'
        assert gate.report == await asyncio.to_thread(controller.delivery_report)
        await controller.commit_stop()
        assert await asyncio.to_thread(_recorded_dispositions, controller) == [('partial',)]


@pytest.mark.asyncio
@pytest.mark.parametrize('unsupported_barrier', [False, True])
async def test_partial_with_missing_native_log_still_enforces_artifact_consistency(
        tmp_path, rdkit_chemistry, unsupported_barrier):
    controller, refs = await _native_controller(tmp_path)
    assert (await _bind_irc(controller, refs, batch=False))['accepted']
    await asyncio.to_thread((tmp_path / 'irc.out').unlink)
    document = {
        'nodes': [
            {'id': 'r', 'role': 'reactant', 'smiles': ['C#N']},
            {'id': 'p', 'role': 'product', 'smiles': ['[C-]#[NH+]']},
            {'id': 'ts', 'role': 'transition_state', 'smiles': []},
        ],
        'edges': [{'id': 'step1', 'from': 'r', 'to': 'p', 'via': 'ts'}],
    }
    if unsupported_barrier:
        document['edges'][0]['barrier_kcal_mol'] = 1.0
    await asyncio.to_thread((tmp_path / 'mechanism_graph.json').write_text, json.dumps(document))

    gate = await controller.audit_stop('partial')

    if unsupported_barrier:
        assert gate.action == 'continue_work'
        assert 'Delivery artifact is inconsistent with the DAG' in gate.reason
        assert 'cannot declare a barrier' in gate.reason
        assert controller._pending_stop is None
        assert await asyncio.to_thread(_recorded_dispositions, controller) == []
    else:
        assert gate.action == 'allow_final'
        assert gate.basis == 'partial_recorded'
        artifact = controller._delivery_artifact
        assert artifact is not None
        assert artifact.scientific_checks['step1']['short_irc']['status'] != 'passed'
        await controller.commit_stop()
        assert await asyncio.to_thread(_recorded_dispositions, controller) == [('partial',)]


@pytest.mark.asyncio
@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('disposition', ['complete', 'partial'])
@pytest.mark.parametrize('change', ['deleted', 'corrupted', 'unchanged'])
async def test_commit_rechecks_native_irc_only_for_complete_after_successful_audit(
        tmp_path, rdkit_chemistry, version, disposition, change):
    controller, refs = await _native_controller(tmp_path, version=version)
    assert (await _bind_irc(controller, refs, batch=False))['accepted']
    gate = await controller.audit_stop(disposition)
    assert gate.action == 'allow_final'
    assert controller._delivery_artifact is None
    state = await asyncio.to_thread(controller.store.delivery_state_fingerprint)

    irc = tmp_path / 'irc.out'
    if change == 'deleted':
        await asyncio.to_thread(irc.unlink)
    elif change == 'corrupted':
        await asyncio.to_thread(irc.write_text, 'This is not a native IRC log.\n')
    # The database and stage-based report alone cannot detect native-file loss.
    assert await asyncio.to_thread(controller.store.delivery_state_fingerprint) == state
    assert await asyncio.to_thread(controller.delivery_report) == gate.report

    blocked = disposition == 'complete' and change != 'unchanged'
    if blocked:
        with pytest.raises(RuntimeError, match='Required IRC direction proof changed after audit'):
            await controller.commit_stop()
    else:
        await controller.commit_stop()

    assert await asyncio.to_thread(_recorded_dispositions, controller) == ([] if blocked else [(disposition,)])


@pytest.mark.asyncio
async def test_irc_gate_preserves_confirmed_delivery_scope(tmp_path, rdkit_chemistry):
    controller, refs = await _native_controller(tmp_path, version=2)
    result = await asyncio.to_thread(lambda: controller.engine.apply_batch(MutationBatch(
        session_id='s1', actor=GraphActor.AGENT, actor_id='a-0',
        base_revisions=controller.store.load_bundle().revisions,
        rationale='Retain an exploratory alternative outside accepted delivery scope', operations=[AddEdge(
            op='add_edge', graph='delivery', edge=ElementaryStepEdge(
                edge_id='exploratory', source_node_id='r', target_node_id='p',
                stages=[StageState(kind='short_irc')]))])))
    assert result.accepted
    assert (await _bind_irc(controller, refs, batch=False))['accepted']

    gate = await controller.audit_stop('complete')

    assert gate.action == 'allow_final'
    assert gate.basis == 'dag_verified'


@pytest.mark.asyncio
async def test_stop_gate_does_not_invent_an_irc_contract(tmp_path, rdkit_chemistry):
    controller, _refs = await _native_controller(tmp_path)
    edge = (await asyncio.to_thread(controller.store.load_snapshot)).delivery.edges[0]
    result = await asyncio.to_thread(lambda: controller.engine.apply_batch(MutationBatch(
        session_id='s1', actor=GraphActor.HARNESS, actor_id='existing-contract',
        base_revisions=controller.store.load_bundle().revisions,
        rationale='Model an existing task with no required IRC check', operations=[UpdateEdge(
            op='update_edge', graph='delivery', edge_id='step1', changes={
                'stages': [stage.model_dump(mode='json') for stage in edge.stages[:-1]]})])))
    assert result.accepted

    gate = await controller.audit_stop('partial')

    assert gate.action == 'allow_final'
    assert gate.basis == 'partial_recorded'
