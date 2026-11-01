#!/usr/bin/env python3
"""Offline rescore of the P1b sandboxes with the tolerant schema."""
import csv
import glob
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/ly/cloudra-bench-20261019")
from cloudra.benchmark.runner import BenchmarkRunner, load_tasks

BASE = Path("/home/ly/cloudra-p1b-20261024")
OUT = Path("/home/ly/cloudra-p1b-rescore")
OUT.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

tasks = {}
for tier in ("easy", "normal", "hard", "impossible"):
    for t in load_tasks(Path(f"/home/ly/cloudra-bench-20261019/ideapool/tasks/{tier}")):
        tasks[t.task_id] = t

runner = BenchmarkRunner(OUT, batch_id="rescore")
rows = []
t0 = time.time()
for db in sorted(glob.glob(str(BASE / "*" / "r*" / "benchmark.db"))):
    arm = db.split("/")[-3]
    rnd = db.split("/")[-2]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    old = {r[0]: r for r in con.execute(
        "select task_id, final_score, accuracy_score, selfconsistency_passed, undelivered from runs")}
    con.close()
    for task_id, old_final, old_acc, old_selfc, old_undel in old.values():
        task = tasks.get(task_id)
        if task is None:
            print("missing task spec", task_id, flush=True)
            continue
        sandbox = BASE / arm / rnd / "sandboxes" / task_id
        batches = sorted(p for p in sandbox.glob("*") if p.is_dir())
        if not batches:
            print("no sandbox", arm, rnd, task_id, flush=True)
            continue
        sb = batches[-1]
        started = time.time()
        try:
            res = runner.score_sandbox(task, sb)
            new = (res.final_score, res.accuracy_score, res.selfconsistency_passed, res.undelivered)
            note = "; ".join(res.notes)[:300]
        except Exception as exc:
            new = (None, None, None, None)
            note = f"ERROR {type(exc).__name__}: {exc}"[:300]
        rows.append((arm, rnd, task_id, old_final, old_acc, old_selfc, old_undel,
                     new[0], new[1], new[2], new[3], round(time.time() - started, 1), note))
        print(f"{arm}/{rnd} {task_id}: {old_final:+.3f} -> "
              f"{new[0] if new[0] is not None else float('nan'):+.3f} "
              f"({time.time()-started:.1f}s)", flush=True)

with open(OUT / "results.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["arm", "round", "task", "old_final", "old_acc", "old_selfc", "old_undelivered",
                "new_final", "new_acc", "new_selfc", "new_undelivered", "seconds", "note"])
    w.writerows(rows)
print(f"done in {time.time()-t0:.0f}s, rows={len(rows)}", flush=True)
