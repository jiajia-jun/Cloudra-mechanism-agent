"""Re-score organized deliveries already stored in a P2 or P1b archive.

Calls ``BenchmarkRunner.score_sandbox`` on retained sandboxes. Does not run
agents or quantum chemistry, and does not modify the archive. A file under
``reconstructions/<arm>/<task>/`` replaces the native delivery only when the
score table's ``repair_source`` names that reconstructed graph, or when the
sandbox has no ``mechanism_graph.json``. A completed delivery is kept when a
reconstruction is only a fallback; guided/HI1 is that case. The P1b offline
package still supplies the one reconstructed Standard HA1/r2 graph.
Workstation-absolute evidence paths are rewritten only when that exact file
is already inside the retained sandbox.

``--apply-target-overlay`` copies the five published 2 November Accuracy
values and composites from the correction CSV. It does not calculate new
scores. Graph and self-consistency stay whatever this checkout's scorer
returned; the untouched scorer values are kept beside the copied cells.

Example:
    python -m cloudra.benchmark.rescore_archive \\
        --p2-root /path/to/Cloudra-P2-final-20261031 \\
        --output /path/to/p2-rescore \\
        --apply-target-overlay
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from cloudra.benchmark.runner import W_ACCURACY, W_GRAPH, W_SELFCONSISTENCY, BenchmarkRunner
from cloudra.benchmark.schema import TaskSpec
from cloudra.runtime_v2.schemas import OrchestrationMode

REPO = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = REPO / "ideapool" / "tasks"
DEFAULT_OVERLAY = (
    REPO
    / "paper/overleaf/Cloudra_SI/companion_data/revision_20261102"
    / "target_matching/target_matching_accuracy_corrections.csv"
)
DEFAULT_P1B_OFFLINE = REPO / "docs/benchmarks/p1b_offline_20261025"
P2_DIRNAME = "Cloudra-P2-final-20261031"
ROUNDS = {"r1", "r2", "r3"}
ARM_MODE = {
    "guided": OrchestrationMode.DAG_GUIDED,
    "record": OrchestrationMode.DAG_RECORD,
    "standard": OrchestrationMode.STANDARD,
    # reproduce_f4.py records brief-errors on the guided orchestration mode.
    "brief-errors": OrchestrationMode.DAG_GUIDED,
}
P1B_RECONSTRUCTED = "human_reconstructed_from_own_run"
P1B_NATIVE = "original_graph"
COLUMNS = [
    "archive",
    "campaign",
    "arm",
    "round",
    "task",
    "tier",
    "sandbox",
    "score_input",
    "scored_sandbox",
    "graph_source",
    "reconstruction",
    "paths_relativized",
    "graph_sha256",
    "graph_score",
    "selfconsistency_score",
    "selfconsistency_passed",
    "accuracy_score",
    "final_score",
    "scorer_accuracy",
    "scorer_final",
    "target_overlay",
    "undelivered",
    "error",
]


@dataclass(frozen=True)
class OnlySelector:
    arm: str
    round: str
    task: str


@dataclass
class Job:
    archive: str
    campaign: str
    arm: str
    round: str
    task: str
    tier: str
    sandbox: Path
    sandbox_display: str
    organized: Path | None
    graph_source: str
    task_spec: TaskSpec


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def require_columns(path: Path, fieldnames: list[str], required: set[str]) -> None:
    missing = required - set(fieldnames)
    if missing:
        raise ValueError(f"{path} is missing columns {sorted(missing)}")


def parse_only(raw: str) -> list[OnlySelector]:
    selectors = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        parts = token.split("/")
        if len(parts) == 1:
            selectors.append(OnlySelector("", "", parts[0]))
        elif len(parts) == 2:
            selectors.append(OnlySelector(parts[0], "", parts[1]))
        elif len(parts) == 3:
            selectors.append(OnlySelector(parts[0], parts[1], parts[2]))
        else:
            raise ValueError(
                f"--only selector {token!r} must be TASK, ARM/TASK, or ARM/ROUND/TASK"
            )
    return selectors


def matches_only(selectors: list[OnlySelector], arm: str, round_: str, task: str) -> bool:
    if not selectors:
        return True
    return any(
        (not item.arm or item.arm == arm)
        and (not item.round or item.round == round_)
        and item.task == task
        for item in selectors
    )


def round_from_path(path: Path) -> str:
    found = [part for part in path.parts if part in ROUNDS]
    if len(found) != 1:
        raise ValueError(f"sandbox path must contain one of {sorted(ROUNDS)}: {path}")
    return found[0]


def resolve_p2_root(path: Path) -> Path:
    path = path.expanduser().resolve()
    if _is_p2_root(path):
        return path
    nested = path / P2_DIRNAME
    if _is_p2_root(nested):
        return nested
    raise ValueError(
        f"{path} is not an extracted P2 FULL archive; expected campaign_data/ "
        f"and tables/final_scores_per_run.csv, or a parent of {P2_DIRNAME}/"
    )


def _is_p2_root(path: Path) -> bool:
    return (path / "campaign_data").is_dir() and (
        path / "tables" / "final_scores_per_run.csv"
    ).is_file()


def p2_sandbox(archive: Path, campaign: str, sandbox_field: str) -> Path:
    parts = Path(sandbox_field).parts
    if campaign not in parts:
        raise ValueError(f"sandbox path {sandbox_field} does not contain campaign {campaign}")
    suffix = Path(*parts[parts.index(campaign) + 1 :])
    if suffix == Path():
        raise ValueError(f"sandbox path {sandbox_field} has no path inside {campaign}")
    candidate = archive / "campaign_data" / campaign / suffix
    if not candidate.is_dir():
        raise ValueError(f"retained sandbox is not in the archive: {candidate}")
    return candidate


def p1b_sandbox(root: Path, sandbox_field: str) -> Path:
    raw = Path(sandbox_field)
    options = [root / raw]
    if len(raw.parts) > 1:
        options.append(root / Path(*raw.parts[1:]))
    options.append(root.parent / raw)
    seen: set[Path] = set()
    for candidate in options:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.is_dir():
            return candidate
    raise ValueError(f"P1b sandbox is not under {root}: {sandbox_field}")


def repair_source_names_reconstruction(repair_source: str, arm: str, task: str) -> bool:
    """True when the score table points at this run's reconstructed graph.

    The archive records that path as ``repair_source``. guided/HI1's completed
    delivery has an empty ``repair_source``; its ``reconstructions/`` file is
    the fallback INDEX.md says must not replace the run's own graph.
    """
    text = repair_source.strip()
    if not text:
        return False
    parts = Path(text).parts
    if len(parts) < 3 or parts[-1] != "mechanism_graph.json":
        return False
    return parts[-2] == task and parts[-3] == arm


def organized_p2_graph(
    archive: Path,
    arm: str,
    task: str,
    sandbox: Path,
    repair_source: str,
) -> Path | None:
    """Choose the organized graph, or None to score the native delivery.

    ``repair_source`` authorizes a reconstruction to replace a graph that is
    already in the sandbox (the brief-errors/IC3 reference repair and the
    seven standard missing-graph repairs). A reconstruction file on its own
    does not. When the sandbox has no mechanism graph, the reconstruction is
    still the only delivery and is used.
    """
    reconstruction = archive / "reconstructions" / arm / task / "mechanism_graph.json"
    native = sandbox / "mechanism_graph.json"
    if repair_source_names_reconstruction(repair_source, arm, task):
        if not reconstruction.is_file():
            raise ValueError(
                f"{arm}/{task} repair_source names a reconstructed graph, "
                f"but {reconstruction} is missing"
            )
        return reconstruction
    if native.is_file():
        return None
    if reconstruction.is_file():
        return reconstruction
    return None


def relativize_evidence_path(raw: str, sandbox: Path) -> str:
    """Map a workstation-absolute evidence path onto this sandbox.

    A suffix is accepted only when that file already exists under the sandbox.
    Anything else is left unchanged so a missing log is not invented.
    """
    path = Path(raw)
    if not path.is_absolute():
        return raw
    parts = path.parts
    for index in range(1, len(parts)):
        suffix = Path(*parts[index:])
        if (sandbox / suffix).is_file():
            return suffix.as_posix()
    return raw


def relativize_graph(node: object, sandbox: Path) -> tuple[object, int]:
    count = 0

    def walk(value: object) -> object:
        nonlocal count
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str):
            relative = relativize_evidence_path(value, sandbox)
            if relative != value:
                count += 1
            return relative
        return value

    return walk(node), count


def _link_or_copy(src, dst) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def stage_sandbox(sandbox: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(sandbox, dest, copy_function=_link_or_copy, symlinks=False)


def replace_graph(dest: Path, text: str) -> None:
    """Write a new graph file. Unlink first so a hardlink cannot touch the archive."""
    target = dest / "mechanism_graph.json"
    if target.exists() or target.is_symlink():
        target.unlink()
    target.write_text(text, encoding="utf-8")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scoring_directory(
    sandbox: Path,
    staged: Path,
    organized: Path | None,
) -> tuple[Path, int, str]:
    """Return the directory, relativized-path count, and graph sha256 to score.

    The archive sandbox is scored in place when its graph can be used as stored.
    A staged hardlink tree is used only to hold an organized graph or a
    path-rewritten copy. ``mechanism_graph.json`` in that tree is replaced
    after unlinking, so the archive inode is not rewritten.
    """
    native = sandbox / "mechanism_graph.json"
    if organized is not None:
        payload = json.loads(organized.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"organized graph is not a JSON object: {organized}")
        rewritten, count = relativize_graph(payload, sandbox)
        stage_sandbox(sandbox, staged)
        text = (
            organized.read_text(encoding="utf-8")
            if count == 0
            else json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n"
        )
        replace_graph(staged, text)
        return staged, count, file_sha256(staged / "mechanism_graph.json")
    if not native.is_file():
        return sandbox, 0, ""
    try:
        payload = json.loads(native.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return sandbox, 0, file_sha256(native)
    if not isinstance(payload, dict):
        return sandbox, 0, file_sha256(native)
    rewritten, count = relativize_graph(payload, sandbox)
    if count == 0:
        return sandbox, 0, file_sha256(native)
    stage_sandbox(sandbox, staged)
    replace_graph(staged, json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n")
    return staged, count, file_sha256(staged / "mechanism_graph.json")


def task_path(tasks_root: Path, tier: str, task_id: str) -> Path:
    if tier:
        path = tasks_root / tier / f"{task_id}.json"
        if not path.is_file():
            raise ValueError(f"task definition not found: {path}")
        return path
    matches = sorted(p for p in tasks_root.glob(f"*/{task_id}.json") if p.is_file())
    if len(matches) != 1:
        raise ValueError(f"expected one task definition for {task_id}, found {len(matches)}")
    return matches[0]


def load_task(tasks_root: Path, tier: str, task_id: str, arm: str) -> tuple[str, TaskSpec]:
    path = task_path(tasks_root, tier, task_id)
    task = TaskSpec.model_validate_json(path.read_text(encoding="utf-8"))
    if task.task_id != task_id:
        raise ValueError(f"{path} declares task_id {task.task_id}, expected {task_id}")
    mode = ARM_MODE.get(arm)
    if mode is None:
        raise ValueError(f"unknown arm {arm!r}")
    task = task.model_copy(
        update={"prompt": task.prompt.model_copy(update={"orchestration_mode": mode})}
    )
    return path.parent.name, task


def relative_to(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def assert_output_outside(output: Path, roots: list[Path]) -> None:
    output = output.resolve()
    for root in roots:
        root = root.resolve()
        if output == root or root in output.parents:
            raise ValueError(f"choose an output directory outside the preserved archive: {root}")


def load_overlay(path: Path) -> dict[tuple[str, str], tuple[float, float]]:
    fieldnames, rows = read_csv_rows(path)
    require_columns(path, fieldnames, {"arm", "task", "accuracy", "score"})
    if not rows:
        raise ValueError(f"{path} has no correction rows")
    overlay: dict[tuple[str, str], tuple[float, float]] = {}
    for row in rows:
        key = (row["arm"], row["task"])
        if key in overlay:
            raise ValueError(f"duplicate target-overlay row {key[0]}/{key[1]}")
        overlay[key] = (float(row["accuracy"]), float(row["score"]))
    return overlay


def p2_jobs(archive: Path, tasks_root: Path, selectors: list[OnlySelector]) -> list[Job]:
    table = archive / "tables" / "final_scores_per_run.csv"
    fieldnames, rows = read_csv_rows(table)
    require_columns(table, fieldnames, {"campaign", "arm", "task", "tier", "sandbox"})
    if not rows:
        raise ValueError(f"{table} has no retained runs")
    jobs: list[Job] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        arm, task = row["arm"], row["task"]
        key = (arm, task)
        if key in seen:
            raise ValueError(f"duplicate retained P2 run {arm}/{task}")
        seen.add(key)
        sandbox = p2_sandbox(archive, row["campaign"], row["sandbox"])
        round_ = round_from_path(sandbox)
        if not matches_only(selectors, arm, round_, task):
            continue
        tier, spec = load_task(tasks_root, row["tier"], task, arm)
        organized = organized_p2_graph(
            archive, arm, task, sandbox, row.get("repair_source", "")
        )
        jobs.append(
            Job(
                archive="p2",
                campaign=row["campaign"],
                arm=arm,
                round=round_,
                task=task,
                tier=tier,
                sandbox=sandbox,
                sandbox_display=relative_to(sandbox, archive),
                organized=organized,
                graph_source=""
                if organized is None
                else relative_to(organized, archive),
                task_spec=spec,
            )
        )
    return jobs


def p1b_jobs(
    root: Path,
    offline: Path,
    tasks_root: Path,
    selectors: list[OnlySelector],
) -> list[Job]:
    table = offline / "standard_results.csv"
    graph = offline / "ha1_r2_graph.json"
    fieldnames, rows = read_csv_rows(table)
    require_columns(
        table,
        fieldnames,
        {"arm", "round", "task_id", "sandbox", "offline_reconstruction"},
    )
    if not rows:
        raise ValueError(f"{table} has no retained runs")
    if not graph.is_file():
        raise ValueError(f"P1b reconstructed graph is missing: {graph}")
    jobs: list[Job] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        arm, round_, task = row["arm"], row["round"], row["task_id"]
        key = (arm, round_, task)
        if key in seen:
            raise ValueError(f"duplicate retained P1b run {arm}/{round_}/{task}")
        seen.add(key)
        if round_ not in ROUNDS:
            raise ValueError(f"P1b round must be one of {sorted(ROUNDS)}: {round_}")
        flag = row["offline_reconstruction"]
        if flag == P1B_RECONSTRUCTED:
            if task != "HA1" or round_ != "r2":
                raise ValueError(
                    "the P1b offline package only publishes a reconstructed graph for standard/r2/HA1"
                )
            organized: Path | None = graph
            graph_source = "ha1_r2_graph.json"
        elif flag == P1B_NATIVE:
            organized = None
            graph_source = ""
        else:
            raise ValueError(f"unknown P1b offline_reconstruction value {flag!r}")
        sandbox = p1b_sandbox(root, row["sandbox"])
        if round_from_path(sandbox) != round_:
            raise ValueError(f"P1b sandbox round does not match {round_}: {sandbox}")
        if not matches_only(selectors, arm, round_, task):
            continue
        tier, spec = load_task(tasks_root, "", task, arm)
        jobs.append(
            Job(
                archive="p1b",
                campaign="cloudra-p1b-20261024",
                arm=arm,
                round=round_,
                task=task,
                tier=tier,
                sandbox=sandbox,
                sandbox_display=relative_to(sandbox, root),
                organized=organized,
                graph_source=graph_source,
                task_spec=spec,
            )
        )
    return jobs


def _blank_row(job: Job) -> dict[str, object]:
    return {
        "archive": job.archive,
        "campaign": job.campaign,
        "arm": job.arm,
        "round": job.round,
        "task": job.task,
        "tier": job.tier,
        "sandbox": job.sandbox_display,
        "score_input": "",
        "scored_sandbox": "",
        "graph_source": job.graph_source,
        "reconstruction": job.organized is not None,
        "paths_relativized": 0,
        "graph_sha256": "",
        "graph_score": None,
        "selfconsistency_score": None,
        "selfconsistency_passed": None,
        "accuracy_score": None,
        "final_score": None,
        "scorer_accuracy": None,
        "scorer_final": None,
        "target_overlay": "",
        "undelivered": None,
        "error": "",
    }


def score_job(
    job: Job,
    runner: BenchmarkRunner,
    output: Path,
    overlay: dict[tuple[str, str], tuple[float, float]] | None,
) -> dict[str, object]:
    row = _blank_row(job)
    staged = output / "staged" / job.archive / job.campaign / job.arm / job.round / job.task
    try:
        scored, count, digest = scoring_directory(job.sandbox, staged, job.organized)
        row["paths_relativized"] = count
        row["graph_sha256"] = digest
        if scored == job.sandbox:
            row["score_input"] = "archive"
            row["scored_sandbox"] = job.sandbox_display
        else:
            row["score_input"] = "staged"
            row["scored_sandbox"] = relative_to(scored, output)
        result = runner.score_sandbox(job.task_spec, scored)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row
    row["graph_score"] = result.graph_score
    row["selfconsistency_score"] = result.selfconsistency_score
    row["selfconsistency_passed"] = result.selfconsistency_passed
    row["scorer_accuracy"] = result.accuracy_score
    row["scorer_final"] = result.final_score
    row["accuracy_score"] = result.accuracy_score
    row["final_score"] = result.final_score
    row["undelivered"] = result.undelivered
    if overlay is None:
        row["target_overlay"] = ""
    elif job.archive == "p2" and (job.arm, job.task) in overlay:
        accuracy, composite = overlay[(job.arm, job.task)]
        row["accuracy_score"] = accuracy
        row["final_score"] = composite
        row["target_overlay"] = "applied"
    else:
        row["target_overlay"] = "not_listed"
    return row


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".16g")
    return str(value)


def write_table(output: Path, payload: dict[str, object], rows: list[dict[str, object]]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "rescored_runs.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _cell(row[key]) for key in COLUMNS})
    (output / "rescored_runs.json").write_text(
        json.dumps({**payload, "rows": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--p2-root", type=Path, help="extracted P2 FULL archive, or its parent directory")
    parser.add_argument("--p1b-root", type=Path, help="extracted P1b campaign directory that contains standard/r*/sandboxes")
    parser.add_argument(
        "--p1b-offline",
        type=Path,
        help="P1b offline package with standard_results.csv and ha1_r2_graph.json "
        "(default: the copy in docs/benchmarks/p1b_offline_20261025 when --p1b-root is set)",
    )
    parser.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS, help="task JSON root (default: ideapool/tasks)")
    parser.add_argument("--output", type=Path, required=True, help="directory outside the archive for the score table")
    parser.add_argument(
        "--only",
        default="",
        help="comma-separated TASK, ARM/TASK, or ARM/ROUND/TASK selectors",
    )
    parser.add_argument(
        "--apply-target-overlay",
        action="store_true",
        help="copy the five published 2 November Accuracy values and composites; "
        "does not compute new scores",
    )
    parser.add_argument(
        "--target-overlay",
        type=Path,
        help="correction CSV used by --apply-target-overlay "
        "(default: revision_20261102/target_matching/target_matching_accuracy_corrections.csv). "
        "Passing this path also turns the overlay on.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.p2_root is None and args.p1b_root is None:
        print("pass --p2-root, --p1b-root, or both", file=sys.stderr)
        return 2
    try:
        selectors = parse_only(args.only)
        p2_root = resolve_p2_root(args.p2_root) if args.p2_root is not None else None
        p1b_root = args.p1b_root.expanduser().resolve() if args.p1b_root is not None else None
        if p1b_root is not None and not p1b_root.is_dir():
            raise ValueError(f"P1b campaign directory does not exist: {p1b_root}")
        offline = None
        if p1b_root is not None:
            offline = (args.p1b_offline or DEFAULT_P1B_OFFLINE).expanduser().resolve()
            if not offline.is_dir():
                raise ValueError(f"P1b offline package does not exist: {offline}")
        elif args.p1b_offline is not None:
            raise ValueError("--p1b-offline requires --p1b-root; the offline package has the graph, not the sandboxes")
        tasks_root = args.tasks_root.expanduser().resolve()
        if not tasks_root.is_dir():
            raise ValueError(f"task directory does not exist: {tasks_root}")
        output = args.output.expanduser().resolve()
        roots = [root for root in (p2_root, p1b_root, offline) if root is not None]
        assert_output_outside(output, roots)
        overlay_path = None
        overlay = None
        if args.apply_target_overlay or args.target_overlay is not None:
            overlay_path = (args.target_overlay or DEFAULT_OVERLAY).expanduser().resolve()
            if not overlay_path.is_file():
                raise ValueError(f"target overlay CSV not found: {overlay_path}")
            overlay = load_overlay(overlay_path)
        jobs: list[Job] = []
        if p2_root is not None:
            jobs.extend(p2_jobs(p2_root, tasks_root, selectors))
        if p1b_root is not None and offline is not None:
            jobs.extend(p1b_jobs(p1b_root, offline, tasks_root, selectors))
        if not jobs:
            raise ValueError("no retained runs matched")
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    output.mkdir(parents=True, exist_ok=True)
    runner = BenchmarkRunner(output / "scorer_runtime")
    rows = [score_job(job, runner, output, overlay) for job in jobs]
    payload = {
        "tool": "cloudra.benchmark.rescore_archive",
        "agents_rerun": False,
        "quantum_chemistry_rerun": False,
        "weights": {"graph": W_GRAPH, "self_consistency": W_SELFCONSISTENCY, "accuracy": W_ACCURACY},
        "p2_root": None if p2_root is None else str(p2_root),
        "p1b_root": None if p1b_root is None else str(p1b_root),
        "p1b_offline": None if offline is None else str(offline),
        "tasks_root": str(tasks_root),
        "target_overlay": None if overlay_path is None else str(overlay_path),
        "target_overlay_scope": (
            "Copies published Accuracy and composite for listed P2 rows. "
            "Graph and self-consistency remain the scorer output. "
            "scorer_accuracy and scorer_final keep the untouched values."
            if overlay is not None
            else "Not applied. accuracy_score and final_score are this checkout's score_sandbox output."
        ),
        "note": (
            "Re-scores archived organized deliveries. Does not rerun agents or quantum chemistry. "
            "The SI companion replots figures and tables from CSV and is a separate path."
        ),
    }
    write_table(output, payload, rows)
    failures = 0
    for row in rows:
        if row["error"]:
            failures += 1
            print(
                f"{row['archive']} {row['arm']}/{row['round']} {row['task']}: ERROR {row['error']}",
                flush=True,
            )
            continue
        print(
            f"{row['archive']} {row['arm']}/{row['round']} {row['task']}: "
            f"final={row['final_score']} graph={row['graph_score']} "
            f"selfconsistency={row['selfconsistency_score']} accuracy={row['accuracy_score']} "
            f"reconstruction={str(row['reconstruction']).lower()}",
            flush=True,
        )
    print(f"wrote {output / 'rescored_runs.csv'} ({len(rows)} rows, {failures} errors)", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
