"""Real native IRC proof, rather than trajectory length or a stop label, gates delivery."""

import asyncio

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
            refs=[refs['product_opt']], stages=[StageState(kind='geometry')])),
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


@pytest.mark.parametrize('mode', ['dag_record', 'dag_guided'])
@pytest.mark.parametrize('disposition', ['complete', 'partial'])
@pytest.mark.asyncio
async def test_stop_label_cannot_bypass_required_irc(tmp_path, rdkit_chemistry, mode, disposition):
    controller, _refs = await _native_controller(tmp_path, mode=mode)

    gate = await controller.audit_stop(disposition)

    assert gate.action == 'continue_work'
    assert gate.basis is None
    assert not gate.report.complete
    assert any(gap.code == 'short_irc_check_failed' for gap in gate.report.unresolved)


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

    assert gate.action == 'continue_work'
    assert not gate.report.complete
    assert any(gap.code == 'short_irc_check_failed' for gap in gate.report.unresolved)
    assert controller._pending_stop is None


@pytest.mark.parametrize('disposition', ['complete', 'partial'])
@pytest.mark.asyncio
async def test_supported_irc_is_rechecked_when_native_log_disappears(tmp_path, rdkit_chemistry, disposition):
    controller, refs = await _native_controller(tmp_path)
    assert (await _bind_irc(controller, refs, batch=False))['accepted']
    (tmp_path / 'irc.out').unlink()

    gate = await controller.audit_stop(disposition)

    assert gate.action == 'continue_work'
    assert not gate.report.complete
    assert any(gap.code == 'short_irc_check_failed' for gap in gate.report.unresolved)


@pytest.mark.asyncio
@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('disposition', ['complete', 'partial'])
@pytest.mark.parametrize('change', ['deleted', 'corrupted', 'unchanged'])
async def test_commit_rechecks_native_irc_after_successful_audit(
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

    if change == 'unchanged':
        await controller.commit_stop()
    else:
        with pytest.raises(RuntimeError, match='Required IRC direction proof changed after audit'):
            await controller.commit_stop()

    def recorded():
        with controller.db.connect() as con:
            return con.execute('SELECT disposition FROM dag_delivery_dispositions').fetchall()

    assert await asyncio.to_thread(recorded) == ([(disposition,)] if change == 'unchanged' else [])


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
