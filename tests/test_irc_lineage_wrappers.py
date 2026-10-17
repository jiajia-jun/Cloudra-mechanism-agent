"""DAG and Benchmark retain native endpoint Opt/Freq evidence for IRC proof."""

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
