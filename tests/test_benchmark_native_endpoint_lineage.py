"""Historical real ORCA replays; no new QM calculation or mocked science."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from cloudra.benchmark.delivery_evidence import write_step_endpoint_evidence
from cloudra.benchmark.integrity import audit_integrity
from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import TaskSpec
from cloudra.benchmark.selfconsistency import audit_self_consistency

FIXTURES = Path(__file__).parent / 'fixtures/native_endpoint_lineage_20261020'
MANIFEST = json.loads((FIXTURES / 'manifest.json').read_text())
pytest.importorskip('rdkit')


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _native_bytes(record):
    archive = (FIXTURES / record['archive']).read_bytes()
    assert _sha256(archive) == record['gzip_sha256']
    content = gzip.decompress(archive)
    assert len(content) == record['uncompressed_bytes']
    assert _sha256(content) == record['sha256']
    return content


def _restore_case(task_id, sandbox):
    case = MANIFEST['cases'][task_id]
    sandbox.mkdir()
    for record in case['files']:
        destination = sandbox / record['sandbox_path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_native_bytes(record))
    graph = (FIXTURES / case['graph']['archive']).read_bytes()
    assert _sha256(graph) == case['graph']['sha256']
    (sandbox / 'mechanism_graph.json').write_bytes(graph)
    task = (FIXTURES / case['task']['archive']).read_bytes()
    assert _sha256(task) == case['task']['sha256']
    return TaskSpec.model_validate_json(task), case


def _assert_original_bytes(sandbox, case):
    assert _sha256((sandbox / 'mechanism_graph.json').read_bytes()) == case['graph']['sha256']
    _assert_native_bytes(sandbox, case)


def _assert_native_bytes(sandbox, case):
    for record in case['files']:
        assert _sha256((sandbox / record['sandbox_path']).read_bytes()) == record['sha256']


def _score_with_science(task, sandbox, score_directory):
    runner = BenchmarkRunner(score_directory)
    result = runner.score_sandbox(task, sandbox)
    cfg = runner._ged_config_for(task)
    integrity = audit_integrity(sandbox, task.rubric.integrity, cfg)
    science = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings,
        integrity.evidence_files, sandbox, task.rubric.self_consistency,
        charge=task.system.charge, integrity_rubric=task.rubric.integrity, ged_config=cfg)
    return result, science


@pytest.mark.parametrize('task_id', ['L1', 'M17'])
def test_original_native_delivery_rejects_its_actual_wrong_endpoint_selection(tmp_path, task_id):
    sandbox = tmp_path / 'historical-delivery'
    task, case = _restore_case(task_id, sandbox)

    result = BenchmarkRunner(tmp_path / 'score').score_sandbox(task, sandbox)

    assert result.selfconsistency_passed is False
    assert result.graph_score == pytest.approx(2 / 3)
    assert result.accuracy_score == pytest.approx(case['original_result']['accuracy_score'])
    assert result.final_score == pytest.approx(0.6667)
    assert any('native starting geometry matches neither actual IRC outer frame' in note
               for note in result.notes)
    _assert_original_bytes(sandbox, case)


@pytest.mark.parametrize('task_id', ['L1', 'M17'])
def test_native_step_endpoint_index_preserves_each_historical_chain(tmp_path, task_id):
    sandbox = tmp_path / 'historical-reconstruction'
    task, case = _restore_case(task_id, sandbox)
    original_task = task.model_dump(mode='json')
    write_step_endpoint_evidence(sandbox, case['graph']['sha256'], case['step_endpoint_evidence'])

    result, science = _score_with_science(task, sandbox, tmp_path / 'score')

    expected_edges = {'Ring_opening_conrotatory', 'Butadiene_torsional_relaxation',
                      'Butadiene_reverse_torsion'} if task_id == 'L1' else {'e1'}
    assert {check.element_id for check in science.checks if check.kind == 'edge' and check.covered} == expected_edges
    assert science.passed, science.notes
    assert result.selfconsistency_passed, result.notes
    assert result.graph_score == 1.0
    assert result.accuracy_score == pytest.approx(case['original_result']['accuracy_score'])
    assert result.final_score == 1.0
    assert task.model_dump(mode='json') == original_task
    _assert_original_bytes(sandbox, case)


@pytest.mark.parametrize('task_id', ['L1', 'M17'])
def test_actual_automatic_delivery_scores_gold_without_rebuilding_metadata(tmp_path, task_id):
    sandbox = tmp_path / 'actual-automatic-delivery'
    task, case = _restore_case(task_id, sandbox)
    automatic = case['automatic_delivery']
    originals = {}
    for label, relative in [('graph', 'mechanism_graph.json'),
                            ('step_endpoint_evidence', '.cloudra/mechanism_evidence.json')]:
        record = automatic[label]
        content = (FIXTURES / record['archive']).read_bytes()
        assert _sha256(content) == record['sha256']
        destination = sandbox / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        originals[relative] = content
    # These are the actual automatic sidecar's snapshot paths. Restore the
    # exact archived native bytes, reusing the existing gzip by SHA256.
    for alias in automatic['native_file_aliases']:
        record = next(row for row in case['files'] if row['archive'] == alias['archive'])
        content = _native_bytes(record)
        assert _sha256(content) == alias['sha256']
        destination = sandbox / alias['sandbox_path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        originals[alias['sandbox_path']] = content

    result, science = _score_with_science(task, sandbox, tmp_path / 'score')

    assert result.graph_score == 1.0
    assert result.selfconsistency_passed, result.notes
    assert result.accuracy_score == pytest.approx(case['original_result']['accuracy_score'])
    assert result.final_score == 1.0
    expected_edges = {'Ring_opening_conrotatory', 'Butadiene_torsional_relaxation',
                      'Butadiene_reverse_torsion'} if task_id == 'L1' else {'e1'}
    assert {check.element_id for check in science.checks if check.kind == 'edge' and check.covered} == expected_edges
    assert science.passed, science.notes
    for relative, content in originals.items():
        assert (sandbox / relative).read_bytes() == content
    _assert_native_bytes(sandbox, case)
