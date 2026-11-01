"""Evaluate the four preserved F4 deliveries against the final reference task."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import TaskSpec
from cloudra.runtime_v2.schemas import OrchestrationMode

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--campaign-root', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--arm', choices=['guided', 'standard', 'record', 'brief-errors'])
args = parser.parse_args()
source = args.campaign_root.resolve()
output = args.output.resolve()
if output == source or source in output.parents:
    raise ValueError('Choose an output directory outside the preserved campaign.')
companion = Path(__file__).resolve().parents[1]
task_path = companion / 'task_definitions/easy/F4.json'
modes = {
    'guided': OrchestrationMode.DAG_GUIDED,
    'standard': OrchestrationMode.STANDARD,
    'record': OrchestrationMode.DAG_RECORD,
    'brief-errors': OrchestrationMode.DAG_GUIDED,
}
output.mkdir(parents=True, exist_ok=True)
for arm in [args.arm] if args.arm else list(modes):
    candidates = sorted(p for p in (source / arm / 'r1/sandboxes/F4').iterdir() if p.is_dir())
    if len(candidates) != 1:
        raise ValueError(f'Expected one retained F4 sandbox for {arm}; found {len(candidates)}')
    task = TaskSpec.model_validate_json(task_path.read_text())
    task.prompt.orchestration_mode = modes[arm]
    runner = BenchmarkRunner(output / (arm + '_runtime'))
    result = asdict(runner.score_sandbox(task, candidates[0]))
    result['sandbox'] = str(candidates[0].relative_to(source.parent))
    result['reference_task'] = 'task_definitions/easy/F4.json'
    result['scorer_commit'] = '0961d9abc35b22618683b456d6a0b72ac8f003bb'
    (output / (arm + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(arm, result['final_score'], flush=True)
