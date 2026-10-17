"""Save the authorized follow-up reference and read-only diagnostic scores.

Original task, formal scores and scientist artifacts remain unchanged. This
script never calls a research backend, an API, or a quantum calculation.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from cloudra.benchmark import runner as scorer_module
from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import TaskSpec

ROOT = Path('/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master')
RUN = ROOT / 'research_runs/NU3-open-to-ring-20261015-26734223'
OLD = ROOT / 'benchmark_smoke_data/final-review-normal-NU3-20261015-ea6936f5'
SOURCE = Path('/Users/cloudrayyy/.codex/worktrees/nu3-final-review/Cloudra-mechanism-agent-master')
COMMIT = 'f2769986a5f3c0271015b7a72f238030afc3bf87'
BATCH = 'batch_8758d928b8794e87'
REF = RUN / 'reference'


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def source_manifest() -> dict:
    paths = {OLD / 'task-set/NU3.json', RUN / 'workspace/mechanism_graph.json'}
    paths.update(p for p in OLD.glob('benchmark.db*') if p.is_file())
    for sandbox in [OLD / 'sandboxes/NU3' / BATCH, RUN / 'workspace']:
        paths.update(p for p in sandbox.rglob('*') if p.is_file() and
                     (p.suffix in {'.out', '.log'} or p.name == 'mechanism_graph.json'))
    return {str(p): {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(paths)}


def forbidden_backend(*args, **kwargs):
    raise AssertionError('This comparison must never invoke a research backend')


assert Path.cwd().resolve() == SOURCE.resolve()
assert Path(scorer_module.__file__).resolve() == SOURCE / 'cloudra/benchmark/runner.py'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip() == COMMIT
status = json.loads((RUN / 'latest-status.json').read_text())
assert status['runtime_finished']
assert not status['pending_compute_notifications'] and not status['pending_review_notifications']
assert all(j['state'] in {'done', 'failed', 'cancelled'} and
           not any(j['locks'].values()) for j in status['compute_jobs'])

before = source_manifest()
route = json.loads((REF / 'full-route-evidence.json').read_text())
original_path = OLD / 'task-set/NU3.json'
original = json.loads(original_path.read_text())
revised = json.loads(original_path.read_text())
barriers = {s['gold_edge_id']: s['barrier_kcal_mol'] for s in route['steps']}
assert set(barriers) == {'NU3_E1', 'NU3_E2', 'NU3_E3'}
changes = []
for edge in revised['gold']['mechanism_graph']['edges']:
    old_barrier = edge['barrier_kcal_mol']
    edge['barrier_kcal_mol'] = barriers[edge['id']]
    changes.append({'edge': edge['id'], 'original_barrier_kcal_mol': old_barrier,
                    'revised_barrier_kcal_mol': edge['barrier_kcal_mol']})
unchanged_sections = ['prompt', 'system', 'method_policy', 'rubric']
assert all(original[k] == revised[k] for k in unchanged_sections)
restored = json.loads(json.dumps(revised))
for edge, old_edge in zip(restored['gold']['mechanism_graph']['edges'],
                          original['gold']['mechanism_graph']['edges']):
    edge['barrier_kcal_mol'] = old_edge['barrier_kcal_mol']
assert restored == original, 'Only the three reference barriers may change'
task = TaskSpec.model_validate(revised)
REF.mkdir(exist_ok=True)
shutil.copy2(original_path, REF / 'NU3.original.json')
revised_path = REF / 'NU3.revised.json'
revised_path.write_text(json.dumps(revised, ensure_ascii=False, indent=2) + '\n')

with closing(sqlite3.connect(f'file:{OLD / "benchmark.db"}?mode=ro', uri=True)) as db:
    db.execute('PRAGMA query_only=ON')
    old_row = db.execute('SELECT task_id,graph_score,selfconsistency_passed,accuracy_score,'
                         'final_score,notes FROM runs WHERE batch_id=?', (BATCH,)).fetchall()
    assert len(old_row) == 1
    row = old_row[0]
    formal = dict(task_id=row[0], graph_score=row[1], selfconsistency_passed=bool(row[2]),
                  accuracy_score=row[3], final_score=row[4], notes=json.loads(row[5]))
    assert formal['final_score'] == 0.5777

results = []
with tempfile.TemporaryDirectory(prefix='nu3-revised-reference-readonly-score-') as scratch:
    runner = BenchmarkRunner(Path(scratch), backend=forbidden_backend)
    for label, sandbox in [
        ('old_formal_delivery_under_revised_reference', OLD / 'sandboxes/NU3' / BATCH),
        ('standalone_middle_step_under_full_revised_NU3_reference', RUN / 'workspace'),
    ]:
        scored = asdict(runner.score_sandbox(task, sandbox))
        results.append({'label': label, 'diagnostic_only': True,
                        'formal_benchmark_run': False, 'sandbox': str(sandbox),
                        'score': scored})
        print(json.dumps({'label': label, 'score': scored['final_score'],
                          'diagnostic_only': True}), flush=True)
    with closing(runner.db._connect()) as db:
        assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0

after = source_manifest()
assert before == after, 'An original task, artifact, native log or formal DB changed'
receipt = {
    'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
    'authorization': 'User conditionally authorized a verified complete ring pathway as the subsequent reference; condition satisfied at species/native-evidence level.',
    'reference_status': 'adopted_as_separate_subsequent_reference; this comparison is offline only, never substituted into a completed or live batch',
    'original_task': str(original_path), 'original_task_sha256': digest(original_path),
    'original_reference_copy': str(REF / 'NU3.original.json'),
    'revised_task': str(revised_path), 'revised_task_sha256': digest(revised_path),
    'reference_changes': changes, 'all_other_task_fields_unchanged': True,
    'unchanged_sections': unchanged_sections, 'scorer_commit': COMMIT,
    'scorer_source': scorer_module.__file__, 'cwd': str(Path.cwd()),
    'pythonpath': os.environ.get('PYTHONPATH'),
    'native_full_route_evidence': str(REF / 'full-route-evidence.json'),
    'middle_source_baseline': 'Actual IRC20 B ->21/22 minimum, not the lower given-A25 conformer. Separate given-A25 arithmetic remains in the evidence report.',
    'route_scope': 'Chemical-species-level route; distinct OCCP conformers preserved. Not a proof of exact conformer interconversion, uniqueness or thermal accessibility.',
    'original_formal_score': formal, 'original_batch_id': BATCH,
    'original_formal_score_preserved': True, 'standalone_formal_score': None,
    'readonly_revised_reference_scores': results,
    'standalone_score_scope': 'The ordinary follow-up delivered only the middle leg, not a full NU3 Benchmark answer. This diagnostic also retains missing structured energy/barrier declarations; it is not a new formal score or a replacement for independent science.',
    'original_materials_unchanged': True, 'before': before, 'after': after,
    'research_backend_invoked': False, 'qm_api_or_model_invoked': False,
    'scratch_formal_run_count': 0, 'scratch_removed': True,
    'scientific_rules_methods_rubric_weights_models_changed': False,
}
(RUN / 'score-comparison.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
(REF / 'adoption.json').write_text(json.dumps({k: v for k, v in receipt.items()
                                              if k not in {'before', 'after', 'readonly_revised_reference_scores'}},
                                             ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'saved': str(RUN / 'score-comparison.json'),
                  'revised_reference': str(revised_path),
                  'original_formal_score': formal['final_score'],
                  'unchanged_file_count': len(before)}), flush=True)
