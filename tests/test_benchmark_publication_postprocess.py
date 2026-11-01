import csv
import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("matplotlib")

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "paper/figures/benchmark_p2_20261031/source_data"


def read_csv(path):
    return list(csv.DictReader(path.open()))


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_prepare_retains_native_components_and_reapplies_corrections(tmp_path):
    script = tmp_path / "scripts/benchmark_p2/prepare_publication_data.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(REPO / "scripts/benchmark_p2/prepare_publication_data.py", script)
    source = tmp_path / "paper/figures/benchmark_p2_20261031/source_data"
    source.mkdir(parents=True)
    for name in ["source_final_scores_per_run.csv", "raw_scores_p2.csv"]:
        shutil.copyfile(SRC / name, source / name)
    shutil.copytree(SRC / "reconstructions", source / "reconstructions")
    corrections = [
        {"arm": "record", "task": "IA5", "accuracy": "1", "score": "1", "reason": "target identity correction"}
    ]
    write_csv(source / "target_matching_accuracy_corrections.csv", corrections)
    subprocess.run([sys.executable, str(script)], check=True, capture_output=True, text=True)
    lookup = {(r["arm"], r["task"]): r for r in read_csv(source / "publication_scores_per_run.csv")}
    assert float(lookup["record", "IA5"]["score"]) == 1
    assert float(lookup["record", "IA5"]["accuracy_publication"]) == 1
    assert float(lookup["record", "IA5"]["graph_publication"]) == 1
    assert float(lookup["record", "IA5"]["selfc_all_publication"]) == 1
    assert float(lookup["record", "IA5"]["fair_final"]) == 0.4
    assert len(lookup) == 200
    provenance = json.loads((source / "component_provenance.json").read_text())
    assert provenance["postprocess_overlay"]["applied_rows"][0]["previous_accuracy"] == 0
    assert provenance["postprocess_overlay"]["applied_rows"][0]["reason"] == "target identity correction"
    subprocess.run([sys.executable, str(script)], check=True, capture_output=True, text=True)
    assert (
        float(
            next(
                r
                for r in read_csv(source / "publication_scores_per_run.csv")
                if r["arm"] == "record" and r["task"] == "IA5"
            )["score"]
        )
        == 1
    )


def test_imp_uses_current_scores_instead_of_stale_brief_imp_tables(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    scores = read_csv(SRC / "publication_scores_per_run.csv")
    for row in scores:
        if row["task"] == "IA5" and row["arm"] in {"guided", "record", "brief-errors"}:
            row["score"] = ".3667" if row["arm"] == "brief-errors" else ".4"
            row["accuracy_publication"] = "0"
        if row["arm"] == "brief-errors" and row["task"] == "IC3":
            row["score"] = "1"
            row["accuracy_publication"] = "1"
    write_csv(source / "publication_scores_per_run.csv", scores)
    tier = read_csv(SRC / "tier_pairwise.csv")
    for row in tier:
        if (
            row["track"] == "official_repaired"
            and row["tier"] == "impossible"
            and row["arm_a"] == "guided"
            and row["arm_b"] == "brief-errors"
        ):
            row["mean_difference"] = "-.09788"
            row["ci_low"] = "-.35"
            row["ci_high"] = ".15"
    write_csv(source / "tier_pairwise.csv", tier)
    output = tmp_path / "figures"
    subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/benchmark_p2/plot_imp.py"),
            "--source-dir",
            str(source),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads((output / "bench_imp.data.json").read_text())
    assert data["summary"]["task_wins"] == {"brief-errors": 4, "guided": 5, "tie": 1}
    assert data["summary"]["official_mean_difference"] == pytest.approx(0.09788)
    assert data["summary"]["paired_bootstrap_ci"]["low"] == -0.15
    assert data["summary"]["paired_bootstrap_ci"]["high"] == 0.35
    caption = (output / "bench_imp.caption.txt").read_text()
    assert "0.543" in caption and "0.09788" in caption


def test_overview_reads_corrected_composite_instead_of_historical_fair_score(tmp_path):
    script = tmp_path / "scripts/benchmark_p2/plot_benchmark_results.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(REPO / "scripts/benchmark_p2/plot_benchmark_results.py", script)
    style = tmp_path / "scripts/model_semantics/figure_style.py"
    style.parent.mkdir(parents=True)
    shutil.copyfile(REPO / "scripts/model_semantics/figure_style.py", style)
    source = tmp_path / "paper/figures/benchmark_p2_20261031/source_data"
    source.mkdir(parents=True)
    for name in [
        "pairwise.csv",
        "tier_pairwise.csv",
        "publication_component_groups.csv",
        "task_structure_and_final_scores.csv",
    ]:
        shutil.copyfile(SRC / name, source / name)
    rows = read_csv(SRC / "publication_scores_per_run.csv")
    for row in rows:
        if row["arm"] == "record" and row["task"] == "IA5":
            row["score"] = "1"
            row["fair_final"] = ".4"
    write_csv(source / "publication_scores_per_run.csv", rows)
    loaded = runpy.run_path(str(script))["r"]
    assert loaded.loc[(loaded.arm == "record") & (loaded.task == "IA5"), "score"].item() == 1
