"""Replay retained native-energy observations and target matching; no new jobs.

Run from the recorded Cloudra checkout. Default: replay the stored native-log
extractions. --native-root additionally extracts barriers from the original
sandbox logs under the unpacked FULL archive directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPANION = ROOT.parents[1]
REPO = next(parent for parent in ROOT.parents if (parent / 'cloudra/benchmark').is_dir())
sys.path.insert(0, str(REPO))
from cloudra.benchmark.accuracy import score_accuracy  # noqa: E402
from cloudra.benchmark.barrier_evidence import BarrierEvidence, StepBarrier, collect_barrier_evidence  # noqa: E402
from cloudra.benchmark.graph_similarity import GedConfig  # noqa: E402
from cloudra.benchmark.integrity import parse_delivered_graph  # noqa: E402
from cloudra.benchmark.runner import _apply_declared_barriers, derived_barrier_graph  # noqa: E402
from cloudra.benchmark.schema import TaskSpec  # noqa: E402


def old_scorer():
    spec = importlib.util.spec_from_file_location('target_matching_previous_accuracy', ROOT / 'scorer_before/accuracy.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.score_accuracy


def evidence_from_record(record):
    return BarrierEvidence(
        steps=[StepBarrier(**step) for step in record['steps']],
        notes=record['notes'], graph_found=record['graph_found'],
        alternatives={key: [StepBarrier(**step) for step in values]
                      for key, values in record['alternatives'].items()},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', type=Path)
    args = parser.parse_args()
    records = json.loads((ROOT / 'accuracy_replay.json').read_text())['runs']
    inputs = {(r['arm'], r['task']): r for r in json.loads((ROOT / 'scoring_inputs_200.json').read_text())['rows']}
    previous = old_scorer()
    results = []
    for record in records:
        arm, task_id = record['arm'], record['task']
        source = inputs[arm, task_id]
        graph_path = ROOT / 'organized_graphs' / arm / (task_id + '.json')
        assert hashlib.sha256(graph_path.read_bytes()).hexdigest() == record['graph_sha256']
        graph = derived_barrier_graph(parse_delivered_graph(json.loads(graph_path.read_text())))
        tier = source['tier']
        task = TaskSpec.model_validate_json((COMPANION / 'task_definitions' / tier / (task_id + '.json')).read_text())
        before = TaskSpec.model_validate_json((ROOT / 'original_task_definitions' / tier / (task_id + '.json')).read_text())
        evidence = evidence_from_record(record['barrier_evidence'])
        if args.native_root is not None and task_id == 'L2':
            sandbox = source['sandbox'].split('Cloudra-P2-final-20261031/', 1)[1]
            evidence = _apply_declared_barriers(collect_barrier_evidence(args.native_root / sandbox), graph)
        cfg = GedConfig(stereo_free=task.rubric.graph_similarity.stereo_tier_rule == 'easy_normal_stereo_free')
        options = dict(evidence=evidence, rubric=task.rubric.accuracy, delivered_graph=graph,
                       cfg=cfg, match_threshold=task.rubric.integrity.match_threshold)
        old = previous(gold=before.gold, **options)
        new = score_accuracy(gold=task.gold, **options)
        assert abs(old.final_score - record['old_accuracy']) < 1e-9
        assert abs(new.final_score - record['new_accuracy']) < 1e-9
        assert not new.fail_loud
        results.append({'arm': arm, 'task': task_id, 'old_accuracy': old.final_score,
                        'accuracy': new.final_score, 'changed': abs(new.final_score-old.final_score) > 1e-10})
    assert len(results) == 12 and sum(row['changed'] for row in results) == 5
    print(json.dumps({'runs_replayed': len(results), 'accuracy_changes': 5,
                      'new_qm_or_llm_runs': 0, 'records': results}, indent=2))


if __name__ == '__main__':
    main()
