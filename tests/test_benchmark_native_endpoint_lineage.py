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


def _restore_hb10_dag(case, sandbox, data_dir):
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    record = case['dag_snapshot']
    content = (FIXTURES / record['archive']).read_bytes()
    assert _sha256(content) == record['sha256']
    captured = json.loads(content)
    db = ConversationDB('historical-hb10', data_dir=data_dir).init()
    with db.connect() as connection:
        for table, rows in captured['tables'].items():
            for row in rows:
                columns = ', '.join(row)
                placeholders = ', '.join('?' for _ in row)
                connection.execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})',
                                   tuple(row.values()))

    def localize(value):
        if isinstance(value, str) and value.startswith(case['source_workspace'] + '/'):
            return str(sandbox / value[len(case['source_workspace']) + 1:])
        if isinstance(value, dict):
            return {key: localize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [localize(item) for item in value]
        return value

    class HistoricalStore(DagStore):
        def resolve_evidence(self, ref):
            # Translate locations only when reading; captured rows/hashes stay exact.
            return localize(super().resolve_evidence(ref))

    return HistoricalStore(db)


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


@pytest.mark.parametrize(('task_id', 'expected_edges'), [
    ('L1', {'Ring_opening_conrotatory', 'Butadiene_torsional_relaxation',
            'Butadiene_reverse_torsion'}),
    ('M17', {'e1'}),
    ('M3', {'e1'}),
])
def test_actual_automatic_delivery_scores_gold_without_rebuilding_metadata(tmp_path, task_id, expected_edges):
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
    expected = automatic['formal_gold_result'] if task_id == 'M3' else case['original_result']
    assert result.accuracy_score == pytest.approx(expected['accuracy_score'])
    assert result.final_score == 1.0
    assert {check.element_id for check in science.checks if check.kind == 'edge' and check.covered} == expected_edges
    assert science.passed, science.notes
    if task_id == 'M3':
        graph = json.loads((sandbox / 'mechanism_graph.json').read_bytes())
        assert all(node['smiles'] == ['N'] for node in graph['nodes'])
        inversion = next(check for check in science.checks if check.kind == 'edge' and check.element_id == 'e1')
        assert any(note.startswith('[advisory] No atom-pair distance change') for note in inversion.notes)
        assert any('both actual IRC outer frames were independently optimized' in note for note in inversion.notes)
    for relative, content in originals.items():
        assert (sandbox / relative).read_bytes() == content
    _assert_native_bytes(sandbox, case)


def test_hb10_original_delivery_keeps_partial_score_without_endpoint_export(tmp_path):
    sandbox = tmp_path / 'actual-hb10-delivery'
    task, case = _restore_case('HB10', sandbox)

    result, science = _score_with_science(task, sandbox, tmp_path / 'score')

    expected = case['formal_gold_result']
    assert result.graph_score == pytest.approx(expected['graph_score'])
    assert result.selfconsistency_passed is False
    assert result.accuracy_score == pytest.approx(expected['accuracy_score'])
    assert result.final_score == pytest.approx(expected['final_score'])
    edges = {check.element_id: check for check in science.checks if check.kind == 'edge'}
    assert edges['exo_DA'].covered
    assert not edges['endo_DA'].covered
    assert any('native starting geometry matches neither actual IRC outer frame' in note
               and 'calc-39.out.log' in note for note in edges['endo_DA'].notes)
    assert not (sandbox / '.cloudra/mechanism_evidence.json').exists()
    _assert_original_bytes(sandbox, case)


def test_hb10_real_step_reviews_pass_science_but_keep_extra_thermo_contract(tmp_path):
    from cloudra.dag.controller import DagController
    from cloudra.dag.engine import DagEngine
    from cloudra.dag.file_science import file_scientific_checks

    sandbox = tmp_path / 'actual-hb10-dag'
    task, case = _restore_case('HB10', sandbox)
    store = _restore_hb10_dag(case, sandbox, tmp_path / 'data')
    graph = store.load_snapshot().delivery

    for request_id in case['accepted_step_reviews'].values():
        request = store.get_review_request(request_id)
        decision = store.get_review_decision_for_request(request_id)
        assert decision.verdict == 'accept'
        checks = file_scientific_checks(store, graph, request.target_ids[0],
            workspace_root=sandbox, evidence_refs=request.supporting_refs,
            irc_files=request.proposal.get('irc_files'),
            endpoint_refs=request.proposal.get('endpoint_refs'))
        assert {stage: check['status'] for stage, check in checks.items()} == {
            'ts_opt': 'passed', 'frequency': 'passed', 'short_irc': 'passed'}
    assert 'without ZPE or thermal corrections' in task.prompt.query
    assert store.load_coverage_contract().require_thermochemistry
    assert all('thermochemistry' not in {stage.kind.value for stage in edge.stages}
               for edge in graph.edges)
    controller = DagController(store.db, 'historical-hb10', 'dag_guided',
                               working_directory=sandbox)
    controller.store = store
    controller.engine = DagEngine(store)

    report = controller.delivery_report()

    assert not report.complete
    assert {(gap.code, gap.target_id) for gap in report.unresolved} == {
        ('missing_thermochemistry', 'step_8700874a'),
        ('missing_thermochemistry', 'step_1f59336c')}
    assert len(report.unresolved) == 2
    assert not report.inconclusive
    assert not (sandbox / '.cloudra/mechanism_evidence.json').exists()
    _assert_original_bytes(sandbox, case)
