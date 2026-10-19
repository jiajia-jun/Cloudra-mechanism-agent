"""DAG and Benchmark retain native endpoint Opt/Freq evidence for IRC proof."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.benchmark.integrity import EvidenceFile, NodeBinding
from cloudra.benchmark.schema import GoldMechanismGraph
from cloudra.benchmark.selfconsistency import audit_self_consistency
from cloudra.dag.evidence_ingest import snapshot_evidence_file
from cloudra.dag.file_science import file_scientific_checks
from cloudra.dag.models import ElementaryStepEdge, GraphData, GraphRef, OccurrenceNode


def _bundle(tmp_path):
    from tests.test_irc_endpoint_optimization import write_lineage_bundle

    return write_lineage_bundle(tmp_path)


@pytest.mark.parametrize('missing_optimization', [False, True])
def test_benchmark_uses_endpoint_optimization_instead_of_interval_gate(tmp_path, missing_optimization, rdkit_chemistry):
    bundle = _bundle(tmp_path)
    if missing_optimization:
        Path(bundle['reactant_opt']).unlink()
    graph = GoldMechanismGraph.model_validate({'nodes': [
        {'id': 'R', 'role': 'reactant', 'smiles': [bundle['reactant_smiles']]},
        {'id': 'P', 'role': 'product', 'smiles': [bundle['product_smiles']]},
        {'id': 'TS', 'role': 'transition_state', 'smiles': []},
    ], 'edges': [{'id': 'E', 'from': 'R', 'to': 'P', 'via': 'TS'}]})
    bindings = [NodeBinding(node_id=node_id, bound_files=[Path(bundle[key]).name], matched=True, quality=1.)
        for node_id, key in [('R', 'reactant_freq'), ('P', 'product_freq'), ('TS', 'ts')]]
    files = [EvidenceFile(path=str(path.relative_to(tmp_path)), kind='orca', size=path.stat().st_size)
        for key, raw in bundle.items() if key not in {'reactant_smiles', 'product_smiles'}
        for path in [Path(raw)] if path.is_file() and path.suffix == '.out']

    report = audit_self_consistency(graph, bindings, files, tmp_path)

    edge = next(check for check in report.checks if check.element_id == 'E')
    assert edge.covered is (not missing_optimization), edge.notes
    assert report.passed is (not missing_optimization), report.notes
    if not missing_optimization:
        assert {'reactant_opt.out', 'product_opt.out'} <= set(edge.evidence_used)
        assert any('[warning]' in note.lower() for note in edge.notes)


@pytest.mark.parametrize('explicit_minimum', [False, True])
@pytest.mark.parametrize('missing_optimization', [False, True])
def test_dag_keeps_opt_and_freq_when_minimum_logs_are_separate(
    tmp_path, explicit_minimum, missing_optimization, rdkit_chemistry,
):
    bundle = _bundle(tmp_path)
    payloads, refs = {}, {}
    for key in ('irc', 'ts', 'reactant_opt', 'reactant_freq', 'product_opt', 'product_freq'):
        if missing_optimization and key == 'reactant_opt':
            continue
        snapshot = snapshot_evidence_file(bundle[key], tmp_path)
        payloads[key] = snapshot.model_dump(mode='json')
        refs[key] = GraphRef(ref_type='file', ref_id=key, content_hash='sha256:' + snapshot.sha256)
    graph = GraphData(graph_id='delivery', graph_kind='delivery', revision=0,
        nodes=[OccurrenceNode(node_id='R', smiles=bundle['reactant_smiles'],
                   refs=[refs[key] for key in ('reactant_opt', 'reactant_freq') if key in refs]),
               OccurrenceNode(node_id='P', smiles=bundle['product_smiles'],
                   refs=[refs['product_opt'], refs['product_freq']])],
        edges=[ElementaryStepEdge(edge_id='E', source_node_id='R', target_node_id='P',
                   refs=[refs['ts'], refs['irc'], *([refs['reactant_freq'], refs['product_freq']] if explicit_minimum else [])])])
    endpoint_refs = ({'endpoint_b': refs['reactant_freq'].model_dump(mode='json'),
                      'endpoint_a': refs['product_freq'].model_dump(mode='json')}
                     if explicit_minimum else None)
    store = SimpleNamespace(resolve_evidence=lambda ref: payloads[ref.ref_id])

    checks = file_scientific_checks(store, graph, 'E', workspace_root=tmp_path,
        endpoint_refs=endpoint_refs)

    assert checks['short_irc']['status'] == ('incomplete' if missing_optimization else 'passed'), checks
    if not missing_optimization:
        assert '[warning]' in checks['short_irc']['detail'].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize('missing_optimization', [False, True])
async def test_direct_gaussian_dag_submission_needs_native_endpoint_optimization(
    tmp_path, monkeypatch, missing_optimization, rdkit_chemistry,
):
    """A captured Gaussian IRC needs no sidecar or pipeline atom-binding ledger.

    Endpoint Opt/Freq logs are synthetic parser fixtures, not calculated results.
    Frequency-verified minima alone cannot establish the actual IRC connection.
    """
    from cloudra.base.session_class import Session
    from cloudra.dag.store import DagStore
    from cloudra.infra.config import get_config
    from cloudra.persistence.database import ConversationDB
    from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanism
    from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
    from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
    from tests.dag_identity import call_dag_tool, make_coordinator
    from tests.test_gaussian_irc_evidence import _bundle as gaussian_bundle

    monkeypatch.setattr(get_config(), 'data_dir', tmp_path / 'runtime')
    monkeypatch.setenv('CLOUDRA_DB_SYNC_ON_LOOP', 'raise')

    def prepare_native_files():
        bundle = gaussian_bundle(tmp_path)
        if missing_optimization:
            bundle['reactant_opt'].unlink()
        original_bytes = {path: path.read_bytes() for path in bundle.values() if path.is_file()}
        return bundle, original_bytes

    bundle, original_bytes = await asyncio.to_thread(prepare_native_files)
    manifest = tmp_path / 'irc_endpoints.json'
    assert not await asyncio.to_thread(manifest.exists)
    project_id = 'direct-gaussian-dag'
    agent = make_coordinator(project_id, workspace_dir=str(tmp_path))
    session = Session(id='s1', path=str(tmp_path / 'session.json'))
    proposal = await call_dag_tool(DagProposeMechanism, agent, session,
        rationale='Test native Gaussian IRC endpoint evidence without a TS pipeline',
        species=[{'name': 'R', 'smiles': 'C#N'}, {'name': 'P', 'smiles': '[C-]#[NH+]'}],
        steps=[{'name': 'step1', 'from': 'R', 'to': 'P'}])
    assert proposal.is_success, proposal
    for name, prefix in [('R', 'reactant'), ('P', 'product')]:
        missing = missing_optimization and prefix == 'reactant'
        submitted = await call_dag_tool(DagSubmitSpeciesEvidence, agent, session,
            species_name=name,
            opt_file=str(bundle[prefix + ('_freq' if missing else '_opt')]),
            freq_file=None if missing else str(bundle[prefix + '_freq']))
        assert submitted.is_success, submitted
        assert submitted.result['scientific_checks']['geometry']['status'] == 'passed', submitted

    submitted = await call_dag_tool(DagSubmitStepEvidence, agent, session,
        step_name='step1', ts_file=str(bundle['ts']), irc_file=str(bundle['irc']),
        source_minimum_file=str(bundle['reactant_freq']),
        target_minimum_file=str(bundle['product_freq']))

    assert submitted.is_success, submitted
    checks = submitted.result['scientific_checks']
    assert checks['frequency']['status'] == 'passed', checks
    assert checks['ts_opt']['status'] == 'incomplete', checks  # The TS fixture is Freq-only.
    assert checks['short_irc']['status'] == ('incomplete' if missing_optimization else 'passed'), checks
    if missing_optimization:
        assert checks['short_irc']['next_action']
        assert 'supply a normally converged Opt log' in checks['short_irc']['detail']

    def persisted_evidence():
        store = DagStore(ConversationDB(project_id))
        request = store.get_review_request(submitted.result['review_id'])
        payloads = [store.resolve_evidence(ref) for ref in request.supporting_refs]
        irc = next(payload for payload in payloads if payload.get('original_path') == str(bundle['irc']))
        return request, irc

    request, irc = await asyncio.to_thread(persisted_evidence)
    assert request.proposal['scientific_checks'] == checks
    assert 'atom_binding' not in irc['metadata']
    assert await asyncio.to_thread(Path(irc['snapshot_path']).read_bytes) == original_bytes[bundle['irc']]
    assert not await asyncio.to_thread(manifest.exists)
    assert await asyncio.to_thread(
        lambda: {path: path.read_bytes() for path in original_bytes}
    ) == original_bytes
