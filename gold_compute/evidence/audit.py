"""Check retained bytes and recompute indexed barriers; never run QM jobs."""

from __future__ import annotations

import hashlib
import json
import sys
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))


def echoed_orca_input(text: str) -> str | None:
    """Recover only numbered lines inside the native INPUT FILE block."""
    active = False
    lines = []
    for line in text.splitlines():
        if not active:
            active = line.strip() == "INPUT FILE"
            continue
        if "****END OF INPUT****" in line:
            return "\n".join(lines).rstrip() + "\n" if lines else None
        stripped = line.lstrip()
        if stripped.startswith("|"):
            number, separator, content = stripped[1:].partition(">")
            if separator and number.strip().isdigit():
                lines.append(content[1:] if content.startswith(" ") else content)
    return None


def main() -> int:
    from cloudra.benchmark.barrier_evidence import (
        _engine_energy_kcal,
        _imaginary_frequency_count,
    )
    from cloudra.benchmark.runner import load_tasks

    manifest = json.loads((ROOT / "MANIFEST.json").read_text())
    errors = []
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        if not path.is_file():
            errors.append(f"MISSING {entry['path']}")
            continue
        blob = path.read_bytes()
        if len(blob) != entry["bytes"] or hashlib.sha256(blob).hexdigest() != entry["sha256"]:
            errors.append(f"CHANGED {entry['path']}")
        if entry["role"] == "recovered_native_input":
            echoed = echoed_orca_input((ROOT / entry["derived_from"]).read_text(errors="replace"))
            if echoed is None or echoed.encode() != blob:
                errors.append(f"INPUT ECHO MISMATCH {entry['path']}")
    tasks = {
        task.task_id: task
        for tier in ("easy", "normal", "hard", "impossible")
        for task in load_tasks(REPO / "ideapool" / "tasks" / tier)
    }
    if set(tasks) != {task["task_id"] for task in manifest["tasks"]}:
        errors.append("FORMAL TASK CATALOG MISMATCH")

    @cache
    def energy(path: str):
        value, reason = _engine_energy_kcal(ROOT, path)
        if value is None:
            raise ValueError(reason)
        return value

    @cache
    def imaginary(path: str):
        return _imaginary_frequency_count(ROOT, path)

    recomputed = 0
    unavailable = []
    for step in manifest["steps"]:
        task_id, edge_id = step["task_id"], step["edge_id"]
        edge = next(edge for edge in tasks[task_id].gold.mechanism_graph.edges if edge.id == edge_id)
        reference = edge.barrier_kcal_mol
        if reference != step["barrier_kcal_mol"]:
            errors.append(f"STALE REFERENCE {task_id}/{edge_id}")
        if not step.get("ts_log") or not step.get("reference_log"):
            unavailable.append(f"{task_id}/{edge_id}: missing original TS/reference log")
            continue
        try:
            actual = energy(step["ts_log"]) - energy(step["reference_log"])
            digits = max(2, len(str(reference).partition(".")[2]))
            if round(actual, digits) != reference:
                errors.append(f"BARRIER MISMATCH {task_id}/{edge_id}: {actual:.8f} vs {reference}")
            ts_imag = imaginary(step["ts_log"])
            ref_imag = imaginary(step["reference_log"])
            expected_ref = step.get("expected_reference_imaginary_count", 0)
            if ts_imag != 1 or ref_imag != expected_ref:
                errors.append(f"FREQUENCY MISMATCH {task_id}/{edge_id}: TS={ts_imag}, reference={ref_imag}")
            print(f"{task_id}/{edge_id}: {actual:.8f} kcal/mol; Gold={reference}; "
                  f"imaginary modes TS/reference={ts_imag}/{ref_imag}")
            recomputed += 1
        except (OSError, ValueError) as exc:
            errors.append(f"UNREADABLE {task_id}/{edge_id}: {exc}")
    print(f"Integrity: {len(manifest['files'])} retained files; "
          f"catalog: {len(tasks)} tasks; recomputed: {recomputed} reference barriers.")
    for item in unavailable:
        print(f"KNOWN GAP: {item}")
    print("Integrity and arithmetic checks do not establish complete IRC/scientific acceptance; see README.")
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
