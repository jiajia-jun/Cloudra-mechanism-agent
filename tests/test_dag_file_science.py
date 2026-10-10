"""File review acceptance cannot replace scientific evidence or prevent repair."""
import asyncio

import pytest

from cloudra.dag.controller import DagController
from cloudra.tools.Plantool.dag_tools.dag_review_step import DagReviewStep
from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
from tests.dag_identity import call_dag_tool, make_supervisor
from tests.test_dag_async_evidence_review import FIXTURES_DIR, _coordinator, _seed_review_graph


@pytest.mark.asyncio
async def test_accepted_irc_file_leaves_explicit_scientific_gap(tmp_path):
    session, db, store = _seed_review_graph(tmp_path, 'file-irc-missing-proof')
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, MutationBatch, UpdateEdge
    mutation = DagEngine(store).apply_batch(MutationBatch(session_id='s1', actor=GraphActor.HARNESS,
        actor_id='test', base_revisions=store.load_bundle().revisions, rationale='require IRC',
        operations=[UpdateEdge(op='update_edge', graph='delivery', edge_id='step1',
            changes={'stages': [{'kind': 'ts_opt'}, {'kind': 'frequency'}, {'kind': 'short_irc'}]})]))
    assert mutation.accepted
    out = await call_dag_tool(DagSubmitStepEvidence, _coordinator(db.conversation_id), session,
        step_name='step1', ts_file=str(FIXTURES_DIR/'xtb/ts_hess_xtb.out'),
        irc_file=str(FIXTURES_DIR/'gaussian/hcn_ts_irc_g16.log'))
    assert out.is_success  # Incomplete evidence can still be reviewed and repaired.
    checks = out.result['scientific_checks']
    assert checks['short_irc']['status'] != 'passed'
    assert checks['short_irc']['next_action']
    request = store.get_review_request(out.result['review_id'])
    assert request.proposal['scientific_checks'] == checks
    reviewed = await call_dag_tool(DagReviewStep,
        make_supervisor(db.conversation_id, workspace_dir=str(tmp_path)), session,
        step_name='step1', verdict='supported', rationale='accept the mechanism hypothesis')
    assert reviewed.is_success
    decision = store.get_review_decision_for_request(out.result['review_id'])
    assert decision.next_action
    controller = DagController(db, 's1', 'dag_guided', conversation_id=db.conversation_id)
    report = await asyncio.to_thread(controller.delivery_report)
    assert not report.complete
    assert any(g.code == 'scientific_check_incomplete' and 'short_irc' in g.detail for g in report.unresolved)
    assert await controller.check_substantive_gate('submit_compute_job', {}) is None


def test_orca_irc_snapshot_preserves_bound_endpoint_files(tmp_path, monkeypatch):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.tools.core import orca_frames
    log = tmp_path/'irc.out'
    log.write_text('ORCA TERMINATED NORMALLY\n')
    endpoints = {}
    for direction, suffix in [('forward','F'),('backward','B')]:
        path = tmp_path/f'irc_IRC_{suffix}_trj.xyz'
        path.write_text('2\nendpoint\nH 0 0 0\nH 0 0 .74\n')
        endpoints[direction] = {'geometry_ref': str(path)}
    monkeypatch.setattr('cloudra.dag.evidence_ingest._extract_qm_log', lambda _: (True,'orca',None,None,None,None))
    monkeypatch.setattr(orca_frames, 'extract_irc', lambda _: {})
    monkeypatch.setattr(orca_frames, 'extract_irc_endpoints', lambda _: endpoints)
    snap = snapshot_evidence_file(log, tmp_path)
    from pathlib import Path
    for endpoint in endpoints.values():
        original = Path(endpoint['geometry_ref'])
        archived = Path(snap.snapshot_path).parent/original.name
        assert archived.is_file() and archived.read_bytes() == original.read_bytes()
    old_snapshot = snap.snapshot_path
    Path(endpoints['forward']['geometry_ref']).write_text('2\nchanged endpoint\nH 0 0 0\nH 0 0 .8\n')
    assert snapshot_evidence_file(log, tmp_path).snapshot_path != old_snapshot


@pytest.mark.asyncio
async def test_file_review_id_exposes_science_and_repair_in_view(tmp_path):
    from cloudra.tools.Plantool.dag_tools.dag_view_evidence import DagViewEvidence
    session, db, _ = _seed_review_graph(tmp_path, 'file-review-visible')
    submitted = await call_dag_tool(DagSubmitStepEvidence, _coordinator(db.conversation_id), session,
        step_name='step1', ts_file=str(FIXTURES_DIR/'xtb/ts_hess_xtb.out'))
    viewed = await call_dag_tool(DagViewEvidence,
        make_supervisor(db.conversation_id, workspace_dir=str(tmp_path)), session,
        review_id=submitted.result['review_id'])
    assert viewed.is_success
    assert viewed.result['scientific_checks']['short_irc']['status'] == 'incomplete'
    assert viewed.result['scientific_checks']['short_irc']['next_action']


def test_archived_irc_never_reads_later_original_endpoint(tmp_path):
    from pathlib import Path

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.tools.core import orca_frames
    log = tmp_path/'calc.out'
    log.write_text(f'NAME = {tmp_path}/job.inp\n' + (FIXTURES_DIR/'orca/hcn_irc_orca60.out').read_text())
    for suffix in ['F','B']:
        (tmp_path/f'job_IRC_{suffix}_trj.xyz').write_text('2\narchived endpoint\nH 0 0 0\nH 0 0 .74\n')
    snap = snapshot_evidence_file(log, tmp_path)
    (tmp_path/'job_IRC_F.xyz').write_text('2\nunbound later endpoint\nH 0 0 0\nH 0 0 5\n')
    endpoints = orca_frames.extract_irc_endpoints(snap.snapshot_path)
    assert Path(endpoints['forward']['geometry_ref']).parent == Path(snap.snapshot_path).parent
    assert endpoints['forward']['geometry_ref'].endswith('_trj.xyz')
    Path(endpoints['forward']['geometry_ref']).unlink()
    with pytest.raises(ValueError, match='hash mismatch'):
        orca_frames.extract_irc_endpoints(snap.snapshot_path)


def test_separate_directional_logs_share_geometric_proof(monkeypatch):
    from cloudra.tools.core import irc_evidence
    from cloudra.tools.core.gaussian_frames import FrameRecord
    symbols = ['C', 'N', 'H']
    def geometry(z):
        return symbols, [[0.,0.,0.],[0.,0.,2.],[0.,0.,z]]
    monkeypatch.setattr(irc_evidence.qm_engine, 'detect_qm_engine', lambda _: 'gaussian')
    def frames(path):
        z = .7 if path == 'forward' else 1.3
        return [FrameRecord(frame=1, reaction_coordinate=1.,
            xyz=f'3\npartial endpoint\nC 0 0 0\nN 0 0 2\nH 0 0 {z}\n')]
    monkeypatch.setattr(irc_evidence, 'irc_frames_for', frames)
    monkeypatch.setattr(irc_evidence, 'probe_log', lambda path, **_: {
        'ts': (1, geometry(1.)), 'source': (0, geometry(.1)), 'target': (0, geometry(1.9))}[path])
    passed, _ = irc_evidence.verify_short_irc_pair('forward','reverse',['ts'],['target'],['source'])
    assert passed
    monkeypatch.setattr(irc_evidence, 'irc_frames_for', lambda _: [])
    assert not irc_evidence.verify_short_irc_pair('forward','reverse',['ts'],['target'],['source'])[0]


@pytest.mark.asyncio
async def test_scientific_repair_still_requires_new_supervisor_acceptance(tmp_path, monkeypatch):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, MutationBatch, UpdateEdge
    from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
    session, db, store = _seed_review_graph(tmp_path, 'science-repair-and-review')
    DagEngine(store).apply_batch(MutationBatch(session_id='s1', actor=GraphActor.HARNESS,
        actor_id='test', base_revisions=store.load_bundle().revisions, rationale='require IRC',
        operations=[UpdateEdge(op='update_edge', graph='delivery', edge_id='step1',
            changes={'stages': [{'kind':'ts_opt'}, {'kind':'frequency'}, {'kind':'short_irc'}]})]))
    agent = _coordinator(db.conversation_id)
    for species in ['R','P']:
        out = await call_dag_tool(DagSubmitSpeciesEvidence, agent, session, species_name=species,
            opt_file=str(FIXTURES_DIR/'gaussian/water_opt_freq_g16.out'))
        assert out.is_success
    state = {'passed': False}
    monkeypatch.setattr('cloudra.dag.file_science.verify_short_irc_direction',
        lambda *_: (state['passed'], ['test direction gap'] if not state['passed'] else []))
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    controller = DagController(db,'s1','dag_guided',conversation_id=db.conversation_id)
    async def submit():
        return await call_dag_tool(DagSubmitStepEvidence, agent, session, step_name='step1',
            ts_file=str(FIXTURES_DIR/'benchmark_synthetic/ts_freq.out'),
            irc_file=str(FIXTURES_DIR/'gaussian/hcn_ts_irc_g16.log'))
    first = await submit()
    assert first.result['scientific_checks']['short_irc']['status'] == 'incomplete'
    await call_dag_tool(DagReviewStep, supervisor, session, step_name='step1',
        verdict='supported', rationale='accept hypothesis; more IRC evidence remains')
    assert not (await asyncio.to_thread(controller.delivery_report)).complete
    state['passed'] = True
    repaired = await submit()
    assert repaired.result['scientific_checks']['short_irc']['status'] == 'passed'
    report = await asyncio.to_thread(controller.delivery_report)
    assert not report.complete
    await call_dag_tool(DagReviewStep, supervisor, session, step_name='step1',
        verdict='supported', rationale='accept repaired evidence')
    report = await asyncio.to_thread(controller.delivery_report)
    assert not any(g.target_id == 'step1' for g in report.unresolved)



def test_mixed_file_and_parser_stage_material_is_usable(tmp_path):
    from cloudra.dag.file_science import file_scientific_checks
    from cloudra.dag.models import GraphRef, StageState
    from tests.test_dag_async_evidence_review import _seed_review_graph
    _, _, store = _seed_review_graph(tmp_path, 'mixed-evidence-science')
    ref = store.register_evidence('s1', 'log_parser',
        {'arguments': {'log_path': str(FIXTURES_DIR/'xtb/ts_hess_xtb.out')}})
    edge = store.load_snapshot().delivery.edges[0]
    edge = edge.model_copy(update={'stages': [StageState(kind='frequency', status='supported', ref=GraphRef.model_validate(ref.model_dump()))]})
    graph = store.load_snapshot().delivery.model_copy(update={'edges': [edge]})
    assert file_scientific_checks(store, graph, 'step1')['frequency']['status'] == 'passed'


@pytest.mark.parametrize("optimization_marker,want", [
    ("", "incomplete"),
    ("The optimization did not converge", "failed"),
    ("THE OPTIMIZATION HAS CONVERGED", "passed"),
])
def test_frequency_count_does_not_substitute_for_optimization_convergence(tmp_path, optimization_marker, want):
    from types import SimpleNamespace

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.file_science import file_scientific_checks
    from cloudra.dag.models import ElementaryStepEdge, GraphData, GraphRef, SpeciesNode

    log = tmp_path / "ts.out"
    text = (FIXTURES_DIR / 'benchmark_synthetic/ts_freq.out').read_text().replace('THE OPTIMIZATION HAS CONVERGED', '')
    log.write_text(text + '\n' + optimization_marker + '\n')
    snap = snapshot_evidence_file(log, tmp_path)
    ref = GraphRef(ref_type='file', ref_id='ts')
    store = SimpleNamespace(resolve_evidence=lambda _ref: snap.model_dump(mode='json'))
    graph = GraphData(graph_id='delivery', graph_kind='delivery', revision=0,
        nodes=[SpeciesNode(node_id='r', smiles='O'), SpeciesNode(node_id='p', smiles='O')],
        edges=[ElementaryStepEdge(edge_id='e', source_node_id='r', target_node_id='p', refs=[ref])])

    checks = file_scientific_checks(store, graph, 'e')

    assert checks['frequency']['status'] == 'passed'
    assert checks['ts_opt']['status'] == want


@pytest.mark.asyncio
async def test_step_submission_binds_separate_optimization_and_frequency_logs(tmp_path):
    session, db, store = await asyncio.to_thread(_seed_review_graph, tmp_path, 'separate-ts-opt-freq')
    opt = tmp_path / 'optimization.out'
    freq = tmp_path / 'frequency.out'
    text = await asyncio.to_thread((FIXTURES_DIR / 'benchmark_synthetic/ts_freq.out').read_text)
    await asyncio.to_thread(opt.write_text, text)
    await asyncio.to_thread(freq.write_text, text.replace('THE OPTIMIZATION HAS CONVERGED', ''))

    from tests.dag_identity import make_coordinator
    submitted = await call_dag_tool(DagSubmitStepEvidence, make_coordinator(db.conversation_id, workspace_dir=str(tmp_path)), session,
        step_name='step1', ts_file=str(freq), opt_file=str(opt))

    assert submitted.is_success, submitted
    assert submitted.result['scientific_checks']['ts_opt']['status'] == 'passed'
    request = await asyncio.to_thread(store.get_review_request, submitted.result['review_id'])
    assert len(request.supporting_refs) == 2


def test_snapshot_checks_reject_modified_direction_manifest(tmp_path):
    from pathlib import Path
    from types import SimpleNamespace

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.file_science import _logs
    log = tmp_path/'irc.out'
    log.write_text((FIXTURES_DIR/'orca/hcn_irc_orca60.out').read_text())
    for suffix in ('F', 'B'):
        (tmp_path / f'irc_IRC_{suffix}.xyz').write_text('2\nendpoint\nH 0 0 0\nH 0 0 .74\n')
    snap = snapshot_evidence_file(log, tmp_path)
    payload = snap.model_dump(mode='json')
    store = SimpleNamespace(resolve_evidence=lambda _: payload)
    element = SimpleNamespace(refs=['ref'], stages=[])
    assert _logs(store, element)[0]
    manifest = Path(snap.metadata['irc_manifest']['snapshot_path'])
    manifest.write_text('{}')
    logs, problems = _logs(store, element)
    assert not logs and any('Immutable IRC' in problem for problem in problems)


def test_detached_irc_log_fails_with_original_log_repair_before_snapshot(tmp_path):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    log = tmp_path / "copied.out"
    log.write_text((FIXTURES_DIR / "orca/hcn_irc_orca60.out").read_text())
    with pytest.raises(ValueError, match="original IRC log"):
        snapshot_evidence_file(log, tmp_path)
    assert not list((tmp_path / ".cloudra/evidence").rglob("irc_endpoints.json"))


def _species_checks(tmp_path, smiles, filenames):
    from types import SimpleNamespace

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.file_science import file_scientific_checks
    from cloudra.dag.models import GraphData, GraphRef, SpeciesNode
    payloads = {}
    refs = []
    for i, filename in enumerate(filenames):
        source = FIXTURES_DIR / filename
        copied = tmp_path / source.name
        copied.write_bytes(source.read_bytes())
        ref = GraphRef(ref_type='file', ref_id=str(i))
        refs.append(ref)
        payloads[str(i)] = snapshot_evidence_file(copied, tmp_path).model_dump(mode='json')
    store = SimpleNamespace(resolve_evidence=lambda ref: payloads[ref.ref_id])
    graph = GraphData(graph_id='delivery', graph_kind='delivery', revision=0, nodes=[SpeciesNode(node_id='rc', smiles=smiles, refs=refs)])
    return file_scientific_checks(store, graph, 'rc')


@pytest.mark.usefixtures("rdkit_chemistry")
def test_fragment_minimum_cannot_certify_whole_species(tmp_path):
    checks = _species_checks(tmp_path, 'O.O=C=O', ['gaussian/water_opt_freq_g16.out'])
    assert checks['geometry']['status'] != 'passed'
    assert checks['geometry']['next_action']


@pytest.mark.usefixtures("rdkit_chemistry")
def test_same_atom_count_wrong_species_cannot_certify_minimum(tmp_path):
    checks = _species_checks(tmp_path, 'C#N', ['gaussian/water_opt_freq_g16.out'])
    assert checks['geometry']['status'] != 'passed'


@pytest.mark.usefixtures("rdkit_chemistry")
def test_all_component_minima_explicitly_report_component_coverage(tmp_path):
    checks = _species_checks(tmp_path, 'O.O=C=O',
        ['gaussian/water_opt_freq_g16.out', 'orca/co2_freq_orca42.out'])
    assert checks['geometry']['status'] == 'passed'
    assert 'component' in checks['geometry']['detail'].lower()
    assert 'complex minimum' in checks['geometry']['detail'].lower()


@pytest.mark.asyncio
async def test_partial_stage_credit_reports_only_remaining_stages(tmp_path):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, MutationBatch, UpdateEdge
    session, db, store = _seed_review_graph(tmp_path, 'partial-stage-credits')
    result = DagEngine(store).apply_batch(MutationBatch(session_id='s1', actor=GraphActor.HARNESS,
        actor_id='test', base_revisions=store.load_bundle().revisions, rationale='IRC required',
        operations=[UpdateEdge(op='update_edge',graph='delivery',edge_id='step1',changes={
            'stages':[{'kind':'ts_opt'},{'kind':'frequency'},{'kind':'short_irc'}]})]))
    assert result.accepted
    await call_dag_tool(DagSubmitStepEvidence, _coordinator(db.conversation_id), session,
        step_name='step1', ts_file=str(FIXTURES_DIR/'xtb/ts_hess_xtb.out'))
    await call_dag_tool(DagReviewStep, make_supervisor(db.conversation_id,workspace_dir=str(tmp_path)),
        session, step_name='step1',verdict='supported',rationale='accept available TS evidence')
    controller = DagController(db,'s1','dag_guided',conversation_id=db.conversation_id)
    report = await asyncio.to_thread(controller.delivery_report)
    gap = next(g for g in report.unresolved if g.code=='missing_stage_evidence' and g.target_id=='step1')
    assert 'short_irc' in gap.detail
    assert 'ts_opt' in gap.detail  # A Hessian-only log cannot prove optimization.
    assert 'frequency' not in gap.detail


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_component_files_submit_as_one_review_without_borrowing_history(tmp_path):
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, MutationBatch, UpdateNode
    from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
    session, db, store = _seed_review_graph(tmp_path, 'component-set-review')
    assert DagEngine(store).apply_batch(MutationBatch(session_id='s1',actor=GraphActor.HARNESS,
        actor_id='test',base_revisions=store.load_bundle().revisions,rationale='declare complex',
        operations=[UpdateNode(op='update_node',graph='delivery',node_id='r',changes={'smiles':'O.O=C=O'})])).accepted
    agent = _coordinator(db.conversation_id)
    water = str(FIXTURES_DIR/'gaussian/water_opt_freq_g16.out')
    co2 = str(FIXTURES_DIR/'orca/co2_freq_orca42.out')
    whole = await call_dag_tool(DagSubmitSpeciesEvidence,agent,session,species_name='R',opt_file=[water,co2])
    assert whole.is_success
    assert whole.result['scientific_checks']['geometry']['status']=='passed'
    request = store.get_review_request(whole.result['review_id'])
    assert len(request.supporting_refs)==2
    # A later incomplete submission must not borrow the old CO2 evidence.
    later = await call_dag_tool(DagSubmitSpeciesEvidence,agent,session,species_name='R',opt_file=water)
    assert later.result['scientific_checks']['geometry']['status']!='passed'


@pytest.mark.asyncio
async def test_species_submission_rejects_unrelated_frequency_file(tmp_path):
    from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
    session, db, _ = _seed_review_graph(tmp_path,'unrelated-frequency')
    result = await call_dag_tool(DagSubmitSpeciesEvidence,_coordinator(db.conversation_id),session,
        species_name='R',opt_file=str(FIXTURES_DIR/'gaussian/water_opt_freq_g16.out'),
        freq_file=str(FIXTURES_DIR/'orca/co2_freq_orca42.out'))
    assert not result.is_success


@pytest.mark.asyncio
@pytest.mark.parametrize('missing_module', ['rdkit', 'rdkit.Chem'])
async def test_missing_rdkit_keeps_species_reviewable_but_delivery_incomplete(
    tmp_path, monkeypatch, missing_module,
):
    import builtins

    from cloudra.dag.engine import DagEngine
    from cloudra.dag.models import GraphActor, MutationBatch, UpdateNode
    from cloudra.tools.Plantool.dag_tools.dag_review_species import DagReviewSpecies
    from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
    from tests.test_dag_async_evidence_review import _seed_simple_complete_graph

    original_import = builtins.__import__

    def without_rdkit(name, *args, **kwargs):
        if name == missing_module:
            raise ModuleNotFoundError(f'No module named {name!r}', name=name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', without_rdkit)
    session, db, store = _seed_simple_complete_graph(tmp_path, 'missing-rdkit-review')
    required_geometry = DagEngine(store).apply_batch(MutationBatch(
        session_id='s1', actor=GraphActor.HARNESS, actor_id='test',
        base_revisions=store.load_bundle().revisions, rationale='require species identity evidence',
        operations=[UpdateNode(op='update_node', graph='delivery', node_id='r',
                               changes={'stages': [{'kind': 'geometry'}]})],
    ))
    assert required_geometry.accepted
    submitted = await call_dag_tool(
        DagSubmitSpeciesEvidence, _coordinator(db.conversation_id), session,
        species_name='R', opt_file=str(FIXTURES_DIR / 'gaussian/water_opt_freq_g16.out'),
    )
    assert submitted.is_success
    check = submitted.result['scientific_checks']['geometry']
    assert check['status'] == 'incomplete'
    assert 'RDKit' in check['detail']
    assert 'cloudra[chem]' in check['detail']
    assert check['next_action']
    review = store.get_review_request(submitted.result['review_id'])
    assert review.proposal['scientific_checks']['geometry'] == check
    assert review.supporting_refs

    reviewed = await call_dag_tool(
        DagReviewSpecies, make_supervisor(db.conversation_id, workspace_dir=str(tmp_path)), session,
        species_name='R', verdict='supported', rationale='accept hypothesis; identity evidence is incomplete',
    )
    assert reviewed.is_success
    controller = DagController(db, 's1', 'dag_guided', conversation_id=db.conversation_id)
    report = await asyncio.to_thread(controller.delivery_report)
    assert not report.complete
    assert any(g.target_id == 'r' and g.code == 'scientific_check_incomplete' and 'RDKit' in g.detail
               for g in report.unresolved)
    assert (await controller.audit_stop('complete')).action != 'allow_final'
