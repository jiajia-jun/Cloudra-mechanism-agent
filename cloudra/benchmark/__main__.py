"""python -m cloudra.benchmark — run the benchmark task bank.

Default is a dry-run (no-op backend: sandboxes stay empty, every task scores
0 through the real scoring pipeline — useful for checking the harness itself).
`--backend runtime_v2` runs each task on the real in-process runtime_v2 kernel
with the method whitelist enforced. Tasks have no overall duration limit.

Example:
    python -m cloudra.benchmark --backend runtime_v2 --data-dir bench_out --only C1,D3
    python -m cloudra.benchmark --tasks-dir ideapool/tasks/easy --tasks-dir ideapool/tasks/impossible
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    from cloudra.benchmark.runner import BenchmarkRunner, load_tasks

    ap = argparse.ArgumentParser(prog="cloudra.benchmark")
    ap.add_argument("--tasks-dir", type=Path, action="append", default=None,
                    help="task JSON dir; repeatable (default: ideapool/tasks/easy)")
    ap.add_argument("--data-dir", type=Path, default=Path("benchmark_data"),
                    help="benchmark data dir (sandboxes + benchmark.db)")
    ap.add_argument("--backend", choices=["none", "runtime_v2"], default="none")
    ap.add_argument("--only", default="", help="comma-separated task ids (default: all)")
    ap.add_argument("--concurrency", type=int, default=1,
                    help="parallel tasks (threads, per-task event loop + sandbox; default 1 = serial)")
    ap.add_argument("--api-pool", type=Path, default=None,
                    help='JSON endpoint pool for anti-429: [{"base_url","api_key","label"}, ...]; '
                         "each LLM call picks a random endpoint, 429 fails over to the next")
    args = ap.parse_args(argv)

    tasks = []
    for d in (args.tasks_dir or [Path("ideapool/tasks/easy")]):
        tasks.extend(load_tasks(d))
    if args.only:
        wanted = {t.strip() for t in args.only.split(",") if t.strip()}
        tasks = [t for t in tasks if t.task_id in wanted]
    if not tasks:
        print("no tasks matched", file=sys.stderr)
        return 2

    stop_event = threading.Event()
    backend = None
    if args.backend == "runtime_v2":
        # 运行时数据隔离必须在首次读取全局配置前完成；config_file 独立于
        # data_dir，LLM 凭据不受影响。YAML 里的 data_dir 键会覆盖环境变量，
        # 所以两处都钉死。
        isolated = (args.data_dir / "runtime").resolve()
        os.environ["CLOUDRA_DATA_DIR"] = str(isolated)
        from cloudra.infra.config import get_config

        get_config().data_dir = isolated
        llm = None
        if args.api_pool is not None:
            from cloudra.benchmark.api_pool import PooledLLMProvider, load_endpoints

            llm = PooledLLMProvider(load_endpoints(args.api_pool))
        from cloudra.benchmark.backend import RuntimeV2Backend

        backend = RuntimeV2Backend(
            llm=llm,
            store_path=args.data_dir / "runtime" / "runtime-v2.db",
            stop_event=stop_event,
        )

    # CLI 每次调用也是一个批次：batches 行 + 溯源快照（模型/模式/插件）+
    # runs 行带 batch_id——CLI 与 Web 结果在同一 schema 下可并排比较。
    from cloudra.benchmark.runner import provenance_config
    from cloudra.runtime_v2.schemas import new_id

    batch_id = new_id("batch")
    runner = BenchmarkRunner(
        args.data_dir, backend=backend, batch_id=batch_id, stop_event=stop_event,
    )
    runner.db.record_batch(batch_id, "running", {
        **provenance_config("cli", tasks),
        "tasks_dirs": [str(d) for d in (args.tasks_dir or [Path("ideapool/tasks/easy")])],
        "task_ids": [t.task_id for t in tasks],
        "concurrency": max(1, args.concurrency),
    })
    received_signal = None

    def request_stop(signum, _frame):
        nonlocal received_signal
        if received_signal is None:
            received_signal = signum
        # Signals run on the main thread. Never enter a worker's event loop or
        # perform persistence here; each worker owns its shutdown sequence.
        stop_event.set()

    previous_handlers = {
        sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    status = "error"
    try:
        results = runner.run_all(tasks, concurrency=max(1, args.concurrency))
        status = "stopped" if stop_event.is_set() else "done"
    finally:
        try:
            runner.db.finish_batch(batch_id, status)
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
    for r in results:
        print(
            f"{r.task_id:>6}  final={r.final_score:.3f}  graph={r.graph_score:.3f} "
            f"selfcons={int(r.selfconsistency_passed)} accuracy={r.accuracy_score:.3f}"
        )
    return 128 + received_signal if received_signal is not None else 0


if __name__ == "__main__":
    sys.exit(main())
