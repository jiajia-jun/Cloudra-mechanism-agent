#!/usr/bin/env python3
"""Plot archived benchmark timing, computation and delivery observations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.model_semantics.figure_style import (  # noqa: E402
    EDGE,
    GREEN,
    INK,
    OLIVE,
    SAGE,
    WARM,
    WHITE,
    clean_axis,
    configure,
    panel,
    save,
)

# isort: split
# The shared style selects the export backend before pyplot is imported.
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ARMS = ("guided", "standard", "record", "brief-errors")
LABELS = {"guided": "Guided", "standard": "Backbone", "record": "Record", "brief-errors": "Brief"}
COLORS = {"guided": GREEN, "standard": WARM, "record": OLIVE, "brief-errors": SAGE}
MM = 1 / 25.4


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def source_record(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def numeric(row: dict, *fields: str) -> dict:
    return {**row, **{key: float(row[key]) for key in fields}}


def arm_ticks(ax) -> None:
    ax.set_xticks(range(4), [LABELS[a] for a in ARMS])
    ax.set_xlim(-0.55, 3.55)


def mean_line(ax, x: float, value: float, color: str) -> None:
    ax.plot([x - 0.25, x + 0.25], [value, value], color=WHITE, linewidth=3.4, zorder=2)
    ax.plot([x - 0.25, x + 0.25], [value, value], color=color, linewidth=1.7, zorder=3)


def build_speed(source: Path, output: Path) -> None:
    pilot_path = source / "p1b_batch_elapsed.csv"
    effort_path = source / "p2_effort_common15.csv"
    pilot = [numeric(r, "elapsed_hours", "elapsed_seconds") for r in read_csv(pilot_path)]
    effort = [
        numeric(r, "job_hours", "official_final", "qm_done", "qm_failed", "qm_cancelled") for r in read_csv(effort_path)
    ]
    assert len(pilot) == 12 and len(effort) == 60
    assert all(sum(r["arm"] == a for r in pilot) == 3 for a in ARMS)
    assert all(sum(r["arm"] == a for r in effort) == 15 for a in ARMS)
    assert all(int(r["concurrency"]) == 2 and int(r["n_tasks"]) == 4 for r in pilot)
    index = {(r["arm"], r["task"]): r for r in effort}
    tasks = sorted({r["task"] for r in effort})
    assert len(tasks) == 15 and len(index) == 60

    fig = plt.figure(figsize=(180 * MM, 144 * MM))
    axes = {
        "a": fig.add_axes([14 / 180, 86 / 144, 48 / 180, 37 / 144]),
        "b": fig.add_axes([70 / 180, 86 / 144, 48 / 180, 37 / 144]),
        "c": fig.add_axes([126 / 180, 86 / 144, 48 / 180, 37 / 144]),
        "d": fig.add_axes([14 / 180, 14 / 144, 160 / 180, 49 / 144]),
    }
    panel(fig, "a", "Pilot batch elapsed time", 3 / 180, 141 / 144)
    panel(fig, "b", "P2 computation per run", 59 / 180, 141 / 144)
    panel(fig, "c", "P2 terminal job states", 115 / 180, 141 / 144)
    panel(fig, "d", "P2 paired investment (n=15)", 3 / 180, 77 / 144)
    fig.text(14 / 180, 134 / 144, "3 batches/arm · 4 tasks/batch\nConcurrency 2", fontsize=7.4, va="top")
    fig.text(70 / 180, 134 / 144, "15 matched tasks/arm\nPoints: runs; line: mean", fontsize=7.4, va="top")
    fig.text(126 / 180, 134 / 144, "15 matched tasks/arm", fontsize=7.4, va="top")

    ax = axes["a"]
    for x, arm in enumerate(ARMS):
        rows = sorted((r for r in pilot if r["arm"] == arm), key=lambda r: r["round"])
        for offset, marker, row in zip((-0.20, -0.05, 0.10), ("o", "s", "^"), rows, strict=True):
            ax.scatter(
                x + offset,
                row["elapsed_hours"],
                s=19,
                marker=marker,
                facecolor=COLORS[arm],
                edgecolor=WHITE,
                linewidth=0.4,
                zorder=4,
            )
        average = mean(r["elapsed_hours"] for r in rows)
        ax.plot([x + 0.22, x + 0.43], [average, average], color=COLORS[arm], linewidth=1.7, zorder=3)
    ax.set_ylim(0, 8.0)
    ax.set_yticks([0, 2, 4, 6, 8])
    ax.set_ylabel("Batch elapsed time (h)", labelpad=4)
    arm_ticks(ax)
    clean_axis(ax, "y")
    ax.legend(
        handles=[Line2D([], [], color=INK, linewidth=1.7, label="Mean")],
        loc="upper left",
        frameon=False,
        handlelength=1.3,
        borderpad=0,
    )

    ax = axes["b"]
    for x, arm in enumerate(ARMS):
        rows = sorted((r for r in effort if r["arm"] == arm), key=lambda r: r["task"])
        offsets = np.array([((i * 7) % 15 - 7) / 37 for i in range(15)])
        ax.scatter(
            x + offsets,
            [r["job_hours"] for r in rows],
            s=12,
            facecolor=COLORS[arm],
            edgecolor=WHITE,
            linewidth=0.3,
            alpha=0.78,
            zorder=4,
        )
        mean_line(ax, x, mean(r["job_hours"] for r in rows), COLORS[arm])
    ax.set_ylim(0, 56)
    ax.set_yticks([0, 10, 20, 30, 40, 50])
    ax.set_ylabel("Cumulative QM job-hours", labelpad=1)
    arm_ticks(ax)
    clean_axis(ax, "y")

    job_states = (("qm_done", "Done", GREEN), ("qm_failed", "Failed", WARM), ("qm_cancelled", "Cancelled", SAGE))
    job_means = []
    ax = axes["c"]
    for x, arm in enumerate(ARMS):
        rows = [r for r in effort if r["arm"] == arm]
        bottom = 0.0
        values = {field: mean(r[field] for r in rows) for field, _, _ in job_states}
        for field, _, color in job_states:
            value = values[field]
            ax.bar(x, value, width=0.61, bottom=bottom, color=color, edgecolor=WHITE, linewidth=0.5)
            if value >= 5:
                ax.text(
                    x,
                    bottom + value / 2,
                    f"{value:.1f}",
                    ha="center",
                    va="center",
                    fontsize=7.4,
                    color=WHITE if field != "qm_cancelled" else INK,
                )
            bottom += value
        ax.text(x, bottom + 1.6, f"{bottom:.1f}", ha="center", va="bottom", fontsize=7.4)
        job_means.append({"arm": arm, "n_runs": 15, **values})
    ax.set_ylim(0, 68)
    ax.set_yticks([0, 20, 40, 60])
    ax.set_ylabel("Mean QM jobs per run", labelpad=1)
    arm_ticks(ax)
    clean_axis(ax, "y")
    ax.legend(
        handles=[Patch(facecolor=color, label=label) for _, label, color in job_states],
        loc="lower left",
        bbox_to_anchor=(126 / 180, 126.5 / 144),
        bbox_transform=fig.transFigure,
        ncol=3,
        frameon=False,
        handlelength=0.9,
        columnspacing=0.75,
        handletextpad=0.35,
        borderpad=0,
    )

    ax = axes["d"]
    pairs = []
    for task in tasks:
        backbone, guided = index["standard", task], index["guided", task]
        ax.annotate(
            "",
            xy=(guided["job_hours"], guided["official_final"]),
            xytext=(backbone["job_hours"], backbone["official_final"]),
            arrowprops={
                "arrowstyle": "-|>",
                "color": EDGE,
                "linewidth": 0.65,
                "mutation_scale": 5,
                "shrinkA": 2,
                "shrinkB": 2,
            },
            zorder=2,
        )
        for arm, row in (("standard", backbone), ("guided", guided)):
            marker = "D" if int(row["manual_graph_repair"]) else "o"
            ax.scatter(
                row["job_hours"],
                row["official_final"],
                s=19,
                marker=marker,
                facecolor=COLORS[arm] if arm == "guided" else WHITE,
                edgecolor=COLORS[arm],
                linewidth=0.85,
                zorder=4,
            )
        pairs.append({"task": task, "backbone": backbone, "guided": guided})
    for task, position in (("HF1", (39.1, 0.87)), ("NU5", (28.0, 0.24)), ("NR1", (9.4, 0.50))):
        row = index["guided", task]
        ax.annotate(
            task,
            (row["job_hours"], row["official_final"]),
            xytext=position,
            ha="left",
            va="center",
            fontsize=7.4,
            color=GREEN,
            arrowprops={"arrowstyle": "-", "color": GREEN, "linewidth": 0.5, "shrinkA": 2, "shrinkB": 4},
        )
    ax.set_xlim(-1.4, 42)
    ax.set_ylim(-0.04, 1.08)
    ax.set_xticks([0, 10, 20, 30, 40])
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1], ["0", "0.25", "0.50", "0.75", "1.00"])
    ax.set_xlabel("Cumulative QM job-hours", labelpad=4)
    ax.set_ylabel("Final total score", labelpad=4)
    clean_axis(ax, "y")
    ax.legend(
        handles=[
            Line2D(
                [],
                [],
                marker="o",
                markersize=3.5,
                linestyle="none",
                markerfacecolor=WHITE,
                markeredgecolor=WARM,
                label="Backbone",
            ),
            Line2D([], [], marker="o", markersize=3.5, linestyle="none", color=GREEN, label="Guided"),
            Line2D(
                [],
                [],
                marker="D",
                markersize=3.5,
                linestyle="none",
                markerfacecolor=WHITE,
                markeredgecolor=WARM,
                label="Offline organized",
            ),
        ],
        loc="center right",
        bbox_to_anchor=(174 / 180, 69 / 144),
        bbox_transform=fig.transFigure,
        ncol=3,
        frameon=False,
        handlelength=0.7,
        columnspacing=0.8,
        handletextpad=0.35,
        borderpad=0,
    )

    data = {
        "figure": "bench_speed",
        "size_mm": [180, 144],
        "arm_order": list(ARMS),
        "arm_labels": LABELS,
        "arm_colors": COLORS,
        "sources": [source_record(pilot_path), source_record(effort_path)],
        "pilot_batch_elapsed": pilot,
        "p2_effort_common15": effort,
        "p2_mean_job_states": job_means,
        "p2_backbone_guided_pairs": pairs,
        "grains": {
            "a": "P1b four-task batch; concurrency 2; n=3 batches per arm",
            "b": "P2 selected common 15-task cohort; n=15 runs per arm",
            "c": "Mean terminal QM jobs per run in the same 15-task cohort",
            "d": "Task-paired standard to guided; 15 matched task pairs",
        },
        "job_hours_definition": "Sum of QM process end-start; standard/M1 is reconstructed from native Job CPU time / 4",
        "total_score_definition": "Official totals after offline graph organization; no new scoring",
        "uncertainty": "Raw observations and arithmetic means; no confidence intervals estimated",
    }
    caption = (
        "Elapsed time, computation and outcomes across the pilot and expanded benchmark. "
        "(a) P1b elapsed time for three four-task batches per arm at concurrency two; symbols show the "
        "three batches and horizontal lines their means. Mean batch times were 4.451 h (Guided), "
        "3.958 h (Backbone), 3.894 h (Record) and 4.827 h (Brief). "
        "(b) Cumulative QM job-hours for the 15 P2 tasks available in all four effort snapshots "
        "(15 runs per arm); each point is a task-run and each line is the arm mean. "
        "Job-hours sum individual QM process durations; the Backbone M1 value was reconstructed "
        "from native CPU time divided by four. "
        "(c) Mean completed, failed and cancelled QM jobs per run for the same cohort. "
        "(d) Task-paired arrows from Backbone (open circles) to Guided (filled circles) connect "
        "recorded computation to final total scores. Open diamonds identify three Backbone graphs "
        "organized offline from their existing research artifacts under the benchmark method. "
        "Panels b–d describe computational investment, while panel a measures batch elapsed time."
    )
    save(fig, output, "bench_speed", data, caption)


def build_delivery(source: Path, output: Path) -> None:
    path = source.parent / "publication_scores_per_run.csv"
    rows = read_csv(path)
    assert len(rows) == len({(r["arm"], r["task"]) for r in rows}) == 200
    graph_counts = []
    sc_counts = []
    repairs = []
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        assert len(arm_rows) == 50
        graph_counts.append(
            {
                "arm": arm,
                "n": 50,
                "original_root_graph": sum(r["neg_class"] != "missing_graph" for r in arm_rows),
                "offline_graph_organization": sum(r["neg_class"] == "missing_graph" for r in arm_rows),
            }
        )
        mechanistic = [r for r in arm_rows if r["tier"] != "impossible"]
        assert len(mechanistic) == 40
        counts = Counter()
        for row in mechanistic:
            sc = float(row["selfc_all_publication"])
            if sc == 1:
                counts["full_score"] += 1
            elif sc == 0:
                counts["zero_score"] += 1
            else:
                assert 0 < sc < 1
                counts["partial_score"] += 1
        sc_counts.append(
            {
                "arm": arm,
                "n": 40,
                **{key: counts[key] for key in ("full_score", "partial_score", "zero_score")},
            }
        )
    assert [r["original_root_graph"] for r in graph_counts] == [50, 43, 50, 50]
    assert [r["full_score"] for r in sc_counts] == [24, 7, 16, 20]
    assert sc_counts[1] == {
        "arm": "standard",
        "n": 40,
        "full_score": 7,
        "partial_score": 29,
        "zero_score": 4,
    }
    for task in ("F1", "M17", "P3", "NR1", "HA1", "HF1", "IA9"):
        row = next(r for r in rows if (r["arm"], r["task"]) == ("standard", task))
        assert row["neg_class"] == "missing_graph" and float(row["score"]) > 0
        repairs.append(
            {
                "task": task,
                "tier": row["tier"],
                "score": float(row["score"]),
                "source_csv_row": rows.index(row) + 2,
                "component_source": row["component_source"],
            }
        )

    fig = plt.figure(figsize=(180 * MM, 105 * MM))
    ax_a = fig.add_axes([0.10, 0.60, 0.355, 0.27])
    ax_b = fig.add_axes([0.60, 0.60, 0.355, 0.27])
    ax_c = fig.add_axes([0.10, 0.105, 0.855, 0.245])
    panel(fig, "a", "Root graph delivery", 0.035, 0.965)
    panel(fig, "b", "SC scores on mechanistic tasks", 0.535, 0.965)
    panel(fig, "c", "Offline-organized Backbone results", 0.035, 0.445)
    fig.text(0.10, 0.915, "50 tasks per arm", fontsize=7.4)
    fig.text(0.60, 0.915, "40 non-impossible tasks per arm", fontsize=7.4)
    fig.text(0.10, 0.39, "Seven graphs organized offline from their existing research artifacts", fontsize=7.4)

    for x, item in enumerate(graph_counts):
        count, repaired = item["original_root_graph"], item["offline_graph_organization"]
        ax_a.bar(x, count, width=0.61, color=COLORS[item["arm"]], edgecolor=WHITE, linewidth=0.5)
        ax_a.text(x, count / 2, str(count), color=WHITE, ha="center", va="center", fontsize=8)
        if repaired:
            ax_a.bar(x, repaired, width=0.61, bottom=count, color=WHITE, edgecolor=WARM, hatch="////", linewidth=0.7)
            ax_a.text(x, count + repaired / 2, str(repaired), ha="center", va="center", fontsize=7.4)
    ax_a.set_ylim(0, 55)
    ax_a.set_yticks([0, 10, 20, 30, 40, 50])
    ax_a.set_ylabel("Runs", labelpad=4)
    arm_ticks(ax_a)
    clean_axis(ax_a, "y")
    ax_a.legend(
        handles=[Patch(facecolor=WHITE, edgecolor=WARM, hatch="////", label="Offline graph organization")],
        loc="upper left",
        bbox_to_anchor=(0, -0.22),
        frameon=False,
        borderpad=0,
        handlelength=1.2,
        handletextpad=0.5,
    )

    states = (
        ("full_score", "SC = 1", GREEN, ""),
        ("partial_score", "0 < SC < 1", SAGE, ""),
        ("zero_score", "SC = 0", WARM, ""),
    )
    for y, item in enumerate(sc_counts):
        left = 0
        for key, _, color, hatch in states:
            count = item[key]
            if not count:
                continue
            ax_b.barh(y, count, left=left, height=0.6, color=color, edgecolor=EDGE, linewidth=0.55, hatch=hatch)
            if count >= 2:
                ax_b.text(
                    left + count / 2,
                    y,
                    str(count),
                    ha="center",
                    va="center",
                    fontsize=7.4,
                    color=INK if key == "partial_score" else WHITE,
                )
            else:
                ax_b.text(left + count + 0.65, y, str(count), ha="left", va="center", fontsize=7.4)
            left += count
        assert left == 40
    ax_b.set_xlim(0, 42.5)
    ax_b.set_xticks([0, 10, 20, 30, 40])
    ax_b.set_yticks(range(4), [LABELS[a] for a in ARMS])
    ax_b.invert_yaxis()
    ax_b.set_xlabel("Runs", labelpad=4)
    clean_axis(ax_b, "x")
    ax_b.legend(
        handles=[
            Patch(facecolor=color, edgecolor=EDGE, hatch=hatch, label=label) for key, label, color, hatch in states
        ],
        loc="upper left",
        bbox_to_anchor=(0, -0.34),
        ncol=3,
        frameon=False,
        handlelength=0.95,
        columnspacing=0.75,
        handletextpad=0.4,
        borderpad=0,
        labelspacing=0.35,
    )

    for x, item in enumerate(repairs):
        ax_c.bar(x, item["score"], width=0.58, color=WARM, edgecolor=WHITE, linewidth=0.5)
        ax_c.text(x, item["score"] + 0.009, f"{item['score']:.3f}", ha="center", va="bottom", fontsize=7.5)
    ax_c.set_xticks(range(7), [r["task"] for r in repairs])
    ax_c.set_xlim(-0.6, 6.6)
    ax_c.set_ylim(0, 0.4)
    ax_c.set_yticks([0, 0.1, 0.2, 0.3, 0.4], ["0", "0.1", "0.2", "0.3", "0.4"])
    ax_c.set_ylabel("Final total score", labelpad=4)
    clean_axis(ax_c, "y")

    data = {
        "figure": "bench_delivery",
        "size_mm": [180, 105],
        "arm_order": list(ARMS),
        "arm_labels": LABELS,
        "arm_colors": COLORS,
        "sources": [source_record(path)],
        "p2_run_observations": rows,
        "root_graph_counts": graph_counts,
        "non_impossible_sc_counts": sc_counts,
        "standard_offline_organized_scores": repairs,
        "sc_category_rule": [
            "SC component = 1 → full_score",
            "0 < SC component < 1 → partial_score",
            "SC component = 0 → zero_score",
        ],
        "sc_measure": "Complete publication continuous SC components after offline graph organization",
        "offline_organization_measure": "Official total scores for seven graphs organized from existing research artifacts",
        "root_graph_source": "Final package runtime graph records and offline organization provenance",
    }
    caption = (
        "Graph organization and scored evidence in P2. "
        "(a) Root mechanism graphs written during the 50 runs per arm: Guided 50, Backbone 43, "
        "Record 50 and Brief 50. The hatched segment marks seven additional Backbone graphs "
        "organized offline from each run's existing research artifacts under the benchmark method. "
        "(b) Complete continuous self-consistency (SC) components after offline organization for "
        "the 40 non-impossible tasks per arm, separating SC = 1, 0 < SC < 1 and SC = 0. "
        "The full-score counts were 24, 7, 16 and 20; Backbone additionally had 29 intermediate "
        "and four zero scores. "
        "(c) Final totals for the seven offline-organized Backbone results, ranging from "
        "0.0333 to 0.3425 (mean 0.1537). Offline organization uses the calculations, claims and "
        "evidence already retained by each run."
    )
    save(fig, output, "bench_delivery", data, caption)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    output = ROOT / "paper/figures/benchmark_p2_20261031"
    parser.add_argument("--source-dir", type=Path, default=output / "source_data/speed_delivery")
    parser.add_argument("--output-dir", type=Path, default=output)
    args = parser.parse_args()
    configure()
    plt.rcParams.update({"xtick.labelsize": 7.4, "ytick.labelsize": 7.4, "legend.fontsize": 7.4})
    build_speed(args.source_dir, args.output_dir)
    build_delivery(args.source_dir, args.output_dir)
    print(f"Wrote bench_speed and bench_delivery to {args.output_dir}")


if __name__ == "__main__":
    main()
