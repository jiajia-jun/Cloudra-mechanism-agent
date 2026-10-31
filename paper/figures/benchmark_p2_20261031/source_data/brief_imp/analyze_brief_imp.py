#!/usr/bin/env python3
"""Reproduce IMP plotting tables from the saved P2 package; no rescoring or QM."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import statistics
import subprocess
import tarfile
from pathlib import Path


def read_csv(path: Path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def mean(values):
    return statistics.mean(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/Users/cloudrayyy/Desktop/Cloudra实验数据/Cloudra-P2-final-20261031"))
    parser.add_argument("--repo", type=Path, default=Path("/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master"))
    parser.add_argument("--paired", type=Path, default=Path("/private/tmp/cloudra_mining/paired"))
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    score_path = args.source / "tables/final_scores_per_run.csv"
    rows = read_csv(score_path)
    assert len(rows) == 200 and len({(r["arm"], r["task"]) for r in rows}) == 200
    for line, row in enumerate(rows, 2):
        row["source_csv_line"] = line
    impossible = [r for r in rows if r["tier"] == "impossible"]
    assert len(impossible) == 40
    arms = ["guided", "standard", "record", "brief-errors"]
    tasks = sorted({r["task"] for r in impossible})
    score_lookup = {(r["arm"], r["task"]): r for r in impossible}
    catalog = {(r["arm"], r["task"]): r for r in read_csv(args.source / "reports/catalog.csv")}
    raw = {(r["arm"], r["task_id"]): r for r in read_csv(args.source / "runs/raw_scores_p2.csv") if r["batch"] == "P2c"}

    archived = subprocess.run(["git", "archive", "53309d0e", "ideapool/tasks/impossible"], cwd=args.repo, check=True, capture_output=True)
    gold = {}
    with tarfile.open(fileobj=io.BytesIO(archived.stdout)) as archive:
        for item in archive.getmembers():
            if item.name.endswith(".json"):
                task = json.load(archive.extractfile(item))
                gold[task["task_id"]] = task
    assert set(gold) == set(tasks)

    # Component values for reconstructed standard/IA9 are explicitly reported in
    # reconstructions/standard/IA9/provenance.md, section 8. No value is inferred
    # from the composite or copied from a different run.
    repaired_components = {("standard", "IA9"): (1 / 3, 0.75, 0.0)}
    matrix = []
    for task_id in tasks:
        task = gold[task_id]
        graph = task["gold"]["mechanism_graph"]
        for arm in arms:
            row = score_lookup[arm, task_id]
            fair_components = tuple(float(row[key]) for key in ("graph", "selfc_all", "accuracy"))
            components = repaired_components.get((arm, task_id), fair_components)
            official = float(row["repaired_final"] or row["fair_final"])
            catalog_row = catalog.get((arm, task_id), {})
            claim = catalog_row.get("delivered", "Final claim text absent from local package; do not infer the search trajectory from scores.")
            evidence = "reports/catalog.csv" if catalog_row else "scores and truncated runs/raw_scores_p2.csv notes_first only"
            if (arm, task_id) == ("brief-errors", "IC3"):
                claim = "Graph explicitly refuses the lowest open-shell singlet 1A2 and its edge; no numerical singlet-triplet gap is declared. It separately retains a computable closed-shell 1A1 branch. Accuracy remains zero."
                evidence = "reconstructions/brief-errors/IC3/mechanism_graph.json; provenance says only references changed"
            elif (arm, task_id) == ("guided", "IA9"):
                claim = "Truncated scorer note: effectively inaccessible in the gold reference; positive or missing final claim; scored 0. Final claim text is absent."
            elif (arm, task_id) == ("standard", "IA9"):
                claim = "Original report calls a PM7 saddle trustworthy and declares a positive 46.73 kcal/mol barrier despite the unrepresented biradical and unverified product-complex minimum. Official graph is an audit reconstruction that preserves this positive claim."
                evidence = "reconstructions/standard/IA9/provenance.md sections 3-8; docs/std-missing-adjudication.md"
            score_disposition = "accepted_negative_target" if components[2] == 1 else ("partial_accuracy_credit" if components[2] > 0 else "no_accuracy_credit")
            repair = "reference_repair" if (arm, task_id) == ("brief-errors", "IC3") else ("graph_reconstruction" if (arm, task_id) == ("standard", "IA9") else "none")
            matrix.append({
                "task": task_id, "task_name": task["name"], "arm": arm,
                "raw_final": float(row["raw_final"]), "reported_fair_final": float(row["fair_final"]),
                "official_final": official, "repair": repair,
                "official_graph": components[0], "official_selfc": components[1], "official_accuracy": components[2],
                "graph_contribution": 0.1 * components[0], "selfc_contribution": 0.3 * components[1], "accuracy_contribution": 0.6 * components[2],
                "weighted_component_sum": 0.1 * components[0] + 0.3 * components[1] + 0.6 * components[2],
                "fair_graph": fair_components[0], "fair_selfc": fair_components[1], "fair_accuracy": fair_components[2],
                "score_disposition": score_disposition,
                "gold_negative_nodes": sum(n.get("accessible", True) is False for n in graph["nodes"]),
                "gold_negative_edges": sum(e.get("accessible", True) is False for e in graph["edges"]),
                "gold_positive_numeric_edges": sum(e.get("barrier_kcal_mol") is not None for e in graph["edges"]),
                "allowed_methods": ";".join(task["method_policy"]["allowed_methods"]),
                "archived_claim_summary": claim, "claim_evidence_source": evidence,
                "raw_notes_first": raw[arm, task_id]["notes_first"],
                "source_csv": str(score_path), "source_csv_line": row["source_csv_line"],
                "component_source": "reconstructions/standard/IA9/provenance.md section 8" if (arm, task_id) in repaired_components else "tables/final_scores_per_run.csv",
                "gold_source": f"git:53309d0e:ideapool/tasks/impossible/{task_id}.json",
            })
    write_csv(args.out / "imp_40_matrix.csv", matrix)
    lookup = {(r["arm"], r["task"]): r for r in matrix}
    long = []
    for row in matrix:
        for metric in ("graph", "selfc", "accuracy", "final"):
            long.append({"task": row["task"], "task_name": row["task_name"], "arm": row["arm"], "metric": metric, "value": row["official_" + metric], "repair": row["repair"], "score_disposition": row["score_disposition"]})
    write_csv(args.out / "imp_components_long.csv", long)

    deltas = []
    for task_id in tasks:
        brief, guided = lookup["brief-errors", task_id], lookup["guided", task_id]
        delta = brief["official_final"] - guided["official_final"]
        deltas.append({"task": task_id, "task_name": brief["task_name"],
            "brief_final": brief["official_final"], "guided_final": guided["official_final"], "brief_minus_guided": delta,
            "task_winner": "brief-errors" if delta > 0 else ("guided" if delta < 0 else "tie"),
            "delta_graph_weighted": brief["graph_contribution"] - guided["graph_contribution"],
            "delta_selfc_weighted": brief["selfc_contribution"] - guided["selfc_contribution"],
            "delta_accuracy_weighted": brief["accuracy_contribution"] - guided["accuracy_contribution"],
            "brief_accuracy": brief["official_accuracy"], "guided_accuracy": guided["official_accuracy"],
            "same_accuracy": brief["official_accuracy"] == guided["official_accuracy"],
            "brief_repair": brief["repair"], "guided_repair": guided["repair"]})
    write_csv(args.out / "imp_brief_minus_guided.csv", deltas)

    arm_summary = []
    for arm in arms:
        subset = [r for r in matrix if r["arm"] == arm]
        arm_summary.append({"arm": arm, "n": len(subset),
            **{key + "_mean": mean(r[key] for r in subset) for key in ["official_final", "official_graph", "official_selfc", "official_accuracy"]},
            "accuracy_1_n": sum(r["official_accuracy"] == 1 for r in subset),
            "accuracy_partial_n": sum(0 < r["official_accuracy"] < 1 for r in subset),
            "accuracy_0_n": sum(r["official_accuracy"] == 0 for r in subset),
            "accuracy_1_tasks": ";".join(r["task"] for r in subset if r["official_accuracy"] == 1),
            "selfc_1_accuracy_0_n": sum(r["official_selfc"] == 1 and r["official_accuracy"] == 0 for r in subset),
            "repair_n": sum(r["repair"] != "none" for r in subset)})
    write_csv(args.out / "imp_arm_summary.csv", arm_summary)

    # Reuse the already-computed paired bootstrap rather than drawing a second
    # stochastic sample. Reverse signs to match the figure's brief-minus-guided
    # direction. The official and fair deltas coincide for this pair.
    existing_ci = [r for r in read_csv(args.paired / "tier_pairwise.csv") if r["track"] == "official_repaired" and r["tier"] == "impossible" and r["arm_a"] == "guided" and r["arm_b"] == "brief-errors"]
    assert len(existing_ci) == 1
    ci = existing_ci[0]
    same = [r for r in deltas if r["same_accuracy"]]
    result = {"n_tasks": 10, "comparison_direction": "brief-errors minus guided", "official_mean_difference": mean(r["brief_minus_guided"] for r in deltas),
        "paired_bootstrap_ci": {"low": -float(ci["ci_high"]), "high": -float(ci["ci_low"]), "source": str(args.paired / "tier_pairwise.csv"), "reused_existing_sample": True},
        "task_wins": {label: sum(r["task_winner"] == label for r in deltas) for label in ["brief-errors", "guided", "tie"]},
        "weighted_component_mean_deltas": {metric: mean(r["delta_" + metric + "_weighted"] for r in deltas) for metric in ["graph", "selfc", "accuracy"]},
        "same_accuracy_tasks": [r["task"] for r in same], "same_accuracy_mean_difference": mean(r["brief_minus_guided"] for r in same),
        "same_accuracy_wins": {label: sum(r["task_winner"] == label for r in same) for label in ["brief-errors", "guided", "tie"]},
        "hindsight_pair_oracle_mean": mean(max(lookup[arm, t]["official_final"] for arm in ["guided", "brief-errors"]) for t in tasks),
        "hindsight_four_arm_oracle_mean": mean(max(lookup[arm, t]["official_final"] for arm in arms) for t in tasks),
        "selfc_1_accuracy_0_total": sum(r["official_selfc"] == 1 and r["official_accuracy"] == 0 for r in matrix),
        "accuracy_histogram": {str(v): sum(r["official_accuracy"] == v for r in matrix) for v in [0, .5, .7, 1]},
        "scope": "Final saved scores only; no new runs, native-log replays, threshold changes, or rescores. Scores are not scientific acceptance rates.",
        "claim_cautions": ["The brief/guided final refusal trajectories for IMP are absent from this local package.", "record/IA5 is a documented correct refusal under-scored by duplicate-endpoint matching.", "brief/IC3 explicitly refuses the requested open-shell state and numerical gap but retains an accessible closed-shell branch; its accuracy zero is not sufficient evidence of a wrong scientific refusal.", "brief/IC3 .4 is a reference repair already folded into the source fair column; standard/IA9 .2583 is post-hoc graph reconstruction used by official track."]}
    (args.out / "imp_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    # Exact values, not asserted scientific stages: edge averaging and negative
    # edges mean the same SC number can have different evidential meanings.
    score_levels = []
    for arm in arms:
        for value in sorted({r["official_selfc"] for r in matrix}):
            subset = [r for r in matrix if r["arm"] == arm and r["official_selfc"] == value]
            score_levels.append({"arm": arm, "selfc_score": value, "run_n": len(subset), "task_ids": ";".join(r["task"] for r in subset), "accuracy_zero_n": sum(r["official_accuracy"] == 0 for r in subset), "interpretation": "Exact SC score only; not a universal stage-completion label."})
    write_csv(args.out / "imp_selfc_score_distribution.csv", score_levels)
    signatures = {}
    for relative in ["tables/final_scores_per_run.csv", "runs/raw_scores_p2.csv", "reports/catalog.csv", "reconstructions/brief-errors/IC3/mechanism_graph.json", "reconstructions/brief-errors/IC3/provenance.md", "reconstructions/standard/IA9/provenance.md"]:
        signatures[relative] = hashlib.sha256((args.source / relative).read_bytes()).hexdigest()
    (args.out / "source_sha256.json").write_text(json.dumps(signatures, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
