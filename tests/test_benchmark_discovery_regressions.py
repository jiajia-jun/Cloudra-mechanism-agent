"""Native scorer recovery must retain ownership and real Opt/Freq lineage."""
import json
from pathlib import Path

import pytest

from cloudra.benchmark.evidence_search import SandboxEvidence, discover_edge_proof
from cloudra.benchmark.integrity import NodeBinding, scan_evidence_files
from cloudra.benchmark.schema import GoldMechanismGraph
from cloudra.benchmark.selfconsistency import audit_self_consistency
from tests.test_irc_endpoint_optimization import check_bundle, write_lineage_bundle


def _graph(paths):
    return GoldMechanismGraph.model_validate({
        'nodes': [
            {'id': 'R', 'role': 'reactant', 'smiles': [paths['reactant_smiles']]},
            {'id': 'P', 'role': 'product', 'smiles': [paths['product_smiles']]},
            {'id': 'TS', 'role': 'transition_state', 'smiles': [],
             'properties': {'energy_hartree': -92.0}},
        ],
        'edges': [{'id': 'E', 'from': 'R', 'to': 'P', 'via': 'TS'}],
    })


def _discover(root, paths):
    graph = _graph(paths)
    return discover_edge_proof(SandboxEvidence(root), graph, graph.edges[0])


@pytest.mark.parametrize('extension', ['.out', '.log', '.OUT'])
def test_discovery_recovers_separate_native_opt_and_freq(tmp_path, extension, rdkit_chemistry):
    paths = write_lineage_bundle(tmp_path)
    for key, path in list(paths.items()):
        if isinstance(path, Path):
            replacement = path.with_suffix(extension)
            path.rename(replacement)
            paths[key] = replacement
    assert check_bundle(paths)[0]

    result = _discover(tmp_path, paths)

    assert result.passed, result.notes
    assert result.score == 1.0
    assert {str(paths[key]) for key in ('reactant_opt', 'reactant_freq', 'product_opt', 'product_freq')} <= set(result.evidence)


@pytest.mark.parametrize('fault', ['missing_freq', 'wrong_opt_start', 'failed_ts', 'wrong_species'])
def test_discovery_does_not_recover_incomplete_native_proof(tmp_path, fault, rdkit_chemistry):
    paths = write_lineage_bundle(tmp_path)
    if fault == 'missing_freq':
        paths['reactant_freq'].unlink()
    elif fault == 'wrong_opt_start':
        path = paths['reactant_opt']
        path.write_text(path.read_text().replace('-1.25000000', '-1.65000000', 1))
    elif fault == 'failed_ts':
        path = paths['ts']
        path.write_text(path.read_text().replace('****ORCA TERMINATED NORMALLY****', 'ORCA finished by error termination'))
    else:
        paths['reactant_smiles'] = 'N#N'

    result = _discover(tmp_path, paths)

    assert not result.passed
    assert result.score < 1.0
    if fault == 'failed_ts':
        assert result.score == 0.0


@pytest.mark.parametrize('bound', [False, True])
@pytest.mark.parametrize('escape', ['logs', 'sidecar', 'native_name'])
def test_scoring_cannot_borrow_another_tasks_native_proof(tmp_path, escape, bound, rdkit_chemistry):
    root, foreign = tmp_path / 'current-task', tmp_path / 'other-task'
    paths = write_lineage_bundle(root)
    foreign.mkdir()
    # Native verifier intentionally permits arbitrary file locations; the scorer
    # must apply its stricter task sandbox boundary at both entry points.
    if escape == 'logs':
        for key in ('ts', 'irc', 'reactant_opt', 'product_opt'):
            path = paths[key]
            external = foreign / path.name
            path.rename(external)
            path.symlink_to(external)
    else:
        for path in root.glob('irc_IRC_*.xyz'):
            external = foreign / path.name
            path.rename(external)
            if escape == 'sidecar':
                path.symlink_to(external)
        if escape == 'native_name':
            irc = paths['irc']
            irc.write_text(irc.read_text().replace('* O   R   C   A *',
                '* O   R   C   A *\nNAME = ' + str(foreign / 'irc.inp'), 1))
    if escape != 'logs':
        assert check_bundle(paths)[0]
    graph = _graph(paths)
    bindings = [NodeBinding(node_id=node, bound_files=[paths[key].name], matched=True, quality=1.0)
                for node, key in [('R', 'reactant_freq'), ('P', 'product_freq')]]
    if bound:
        bindings.append(NodeBinding(node_id='TS', bound_files=[paths['ts'].name], matched=True, quality=1.0))

    report = audit_self_consistency(graph, bindings, scan_evidence_files(root), root)

    assert not report.passed
    assert not next(check.covered for check in report.checks if check.element_id == 'E')
    assert not _discover(root, paths).passed


@pytest.mark.parametrize('metadata', [{}, [], {'input_file': 'irc.inp', 'files': [None]}])
def test_bad_native_metadata_isolated_from_independent_valid_proof(tmp_path, metadata, rdkit_chemistry):
    broken = write_lineage_bundle(tmp_path / 'results')
    (tmp_path / 'path-map.json').write_text(json.dumps(metadata))
    good = write_lineage_bundle(tmp_path / 'good')

    index = SandboxEvidence(tmp_path)
    irc_paths = {fact.path for fact, _start, _ends in index.irc_logs()}
    assert broken['irc'] not in irc_paths
    assert good['irc'] in irc_paths
    result = _discover(tmp_path, good)
    assert result.passed, result.notes
    assert str(good['irc']) in result.evidence
    assert str(broken['irc']) not in result.evidence


def test_native_chain_identity_ignores_snapshot_names_but_preserves_direction(tmp_path):
    from cloudra.benchmark.evidence_search import claim_native_chain

    ts, irc = tmp_path / 'ts.log', tmp_path / 'irc.log'
    ts.write_text('the same native saddle calculation')
    irc.write_text('the same native bidirectional IRC calculation')
    ts_copy, irc_copy = tmp_path / 'snapshot-ts.log', tmp_path / 'snapshot-irc.log'
    ts_copy.write_bytes(ts.read_bytes())
    irc_copy.write_bytes(irc.read_bytes())
    source = (['H', 'H'], [[0., 0., 0.], [0., 0., 0.7]])
    target = (['H', 'H'], [[0., 0., 0.], [0., 0., 1.7]])
    forward = dict(source_endpoint=source, target_endpoint=target)
    reverse = dict(source_endpoint=target, target_endpoint=source)
    ledger = {}
    assert claim_native_chain(ts, [irc], forward, ledger)
    assert not claim_native_chain(ts_copy, [irc_copy], forward, ledger)
    assert not claim_native_chain(ts_copy, [irc, irc_copy], forward, ledger)
    separate = tmp_path / 'separate_direction.log'
    separate.write_text('a separate one-directional IRC')
    assert not claim_native_chain(ts_copy, [irc_copy, separate], forward, ledger)
    changed = (['H', 'H'], [[0., 0., 0.], [0., 0., 2.7]])
    assert not claim_native_chain(ts_copy, [irc_copy, separate],
        dict(source_endpoint=source, target_endpoint=changed), ledger)
    assert not claim_native_chain(ts_copy, [irc_copy, separate],
        dict(source_endpoint=changed, target_endpoint=target), ledger)
    assert claim_native_chain(ts_copy, [irc_copy], reverse, ledger)
    assert not claim_native_chain(ts, [separate], {}, ledger)


def test_unselected_parent_metadata_cannot_veto_owned_archived_chain(tmp_path, rdkit_chemistry):
    from cloudra.benchmark.evidence_search import irc_evidence_within_sandbox
    from cloudra.tools.core.orca_frames import snapshot_irc_endpoints

    root = tmp_path / 'task'
    paths = write_lineage_bundle(root)
    snapshot_irc_endpoints(str(paths['irc']), root)
    (tmp_path / 'evidence.json').write_text('{}')
    assert check_bundle(paths)[0]

    assert irc_evidence_within_sandbox(paths['irc'], root)
    assert _discover(root, paths).passed
