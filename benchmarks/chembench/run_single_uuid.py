from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["CLOUDRA_YOLO_MODE"] = "true"

from benchmarks.chembench.runner import ChemBenchRunner, RunnerConfig
from benchmarks.chembench.utils import get_field
from chembench.task import TaskRegistry

DATA_DIR = PROJECT_ROOT / "benchmarks" / "data" / "chembench-repo" / "data"
TARGET_UUID = "208c7b0d-db9f-b499-8fa3-47f41845fb10"


def find_question(benchmark, uuid: str):
    for tq in benchmark.topics.values():
        for task in tq.tasks:
            if get_field(task, "uuid", None) == uuid:
                return task
    return None


async def main():
    benchmark = TaskRegistry.from_directory(str(DATA_DIR))
    question = find_question(benchmark, TARGET_UUID)
    if question is None:
        print(f"未找到 uuid={TARGET_UUID} 的题目", file=sys.stderr)
        sys.exit(1)

    config = RunnerConfig(
        timeout_per_question=300.0,
        concurrency=1,
        verbose=True,
        run_id="single_dft_verify",
    )
    runner = ChemBenchRunner(config)
    runner.setup()

    result = await runner._run_question(0, 1, question)
    print("\n--- 单题结果 ---")
    print(f"uuid: {result.uuid}")
    print(f"answer: {result.extracted_answer!r}")
    print(f"all_correct: {result.metrics.get('all_correct')}")
    print(f"timed_out: {result.timed_out}")
    print(f"elapsed_seconds: {result.elapsed_seconds}")


if __name__ == "__main__":
    asyncio.run(main())
