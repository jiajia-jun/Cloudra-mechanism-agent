#!/usr/bin/env python3
"""Publication figure for the final P2 impossible-tier comparison."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "model_semantics"))
import figure_style as style  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, to_rgb  # noqa: E402
from matplotlib.ticker import MaxNLocator, StrMethodFormatter  # noqa: E402

ARMS = ("guided", "standard", "record", "brief-errors")
LABELS = {"guided": "Guided", "standard": "Backbone", "record": "Record", "brief-errors": "Brief"}
COLORS = {"guided": style.GREEN, "standard": style.WARM, "record": style.OLIVE, "brief-errors": style.SAGE}
TASKS = ("IA1", "IA5", "IA7", "IA9", "IB9", "IC3", "ID2", "IE2", "IF3", "IG8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def luminance(color) -> float:
    rgb = to_rgb(color)
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def cell_text_color(color) -> str:
    value = luminance(color)
    white = 1.05 / (value + 0.05)
    ink = (value + 0.05) / (luminance(style.INK) + 0.05)
    return style.WHITE if white > ink else style.INK


def short(value: float) -> str:
    return str(int(value)) if value in (0, 1) else f"{value:.2f}"


def heatmap(fig, rect, metric, lookup, cmap):
    ax = fig.add_axes(rect)
    values = np.array([[float(lookup[arm, task][metric]) for arm in ARMS] for task in TASKS])
    ax.imshow(values, vmin=0, vmax=1, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(ARMS)), [LABELS[arm] for arm in ARMS])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(TASKS)), TASKS)
    ax.tick_params(axis="both", length=0, pad=4, labelsize=7.4)
    for tick, arm in zip(ax.get_xticklabels(), ARMS, strict=True):
        tick.set_color(COLORS[arm])
        tick.set_fontweight("bold")
    ax.set_xticks(np.arange(-0.5, len(ARMS), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(TASKS), 1), minor=True)
    ax.grid(which="minor", color=style.WHITE, linewidth=1)
    ax.tick_params(which="minor", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for row in range(len(TASKS)):
        for column in range(len(ARMS)):
            value = values[row, column]
            ax.text(
                column,
                row,
                short(value),
                ha="center",
                va="center",
                color=cell_text_color(cmap(value)),
                fontsize=7.5,
            )
    return ax


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "paper/figures/benchmark_p2_20261031/source_data")
    parser.add_argument("--output", type=Path, default=ROOT / "paper/figures/benchmark_p2_20261031")
    args = parser.parse_args()
    publication_scores = read_csv(args.source_dir / "publication_scores_per_run.csv")
    assert len(publication_scores) == 200
    matrix = [row for row in publication_scores if row["tier"] == "impossible"]
    assert len(matrix) == 40
    lookup = {(row["arm"], row["task"]): row for row in matrix}
    assert set(lookup) == {(arm, task) for arm in ARMS for task in TASKS}
    deltas = []
    for task in TASKS:
        brief, guided = lookup["brief-errors", task], lookup["guided", task]
        difference = float(brief["score"]) - float(guided["score"])
        deltas.append(
            {
                "task": task,
                "brief_final": float(brief["score"]),
                "guided_final": float(guided["score"]),
                "brief_minus_guided": difference,
                "task_winner": "brief-errors" if difference > 0 else "guided" if difference < 0 else "tie",
                **{
                    "delta_" + metric + "_weighted": weight * (float(brief[field]) - float(guided[field]))
                    for metric, field, weight in [
                        ("graph", "graph_publication", 0.1),
                        ("selfc", "selfc_all_publication", 0.3),
                        ("accuracy", "accuracy_publication", 0.6),
                    ]
                },
            }
        )
    comparisons = [
        row
        for row in read_csv(args.source_dir / "tier_pairwise.csv")
        if row["track"] == "official_repaired"
        and row["tier"] == "impossible"
        and row["arm_a"] == "guided"
        and row["arm_b"] == "brief-errors"
    ]
    assert len(comparisons) == 1
    paired = comparisons[0]
    summary = {
        "official_mean_difference": mean(row["brief_minus_guided"] for row in deltas),
        "task_wins": {
            arm: sum(row["task_winner"] == arm for row in deltas) for arm in ["brief-errors", "guided", "tie"]
        },
        "weighted_component_mean_deltas": {
            metric: mean(row["delta_" + metric + "_weighted"] for row in deltas)
            for metric in ["graph", "selfc", "accuracy"]
        },
        "paired_bootstrap_ci": {"low": -float(paired["ci_high"]), "high": -float(paired["ci_low"])},
    }
    assert abs(summary["official_mean_difference"] + float(paired["mean_difference"])) < 1e-10
    delta_lookup = {row["task"]: row for row in deltas}
    mean_lookup = {arm: mean(float(lookup[arm, task]["score"]) for task in TASKS) for arm in ARMS}
    means = [{"arm": arm, "n": len(TASKS), "composite_mean": mean_lookup[arm]} for arm in ARMS]
    style.configure()
    plt.rcParams.update({"xtick.labelsize": 7.4, "ytick.labelsize": 7.4})
    fig = plt.figure(figsize=(180 / 25.4, 120 / 25.4))
    cmap = LinearSegmentedColormap.from_list("cloudra_evidence", [style.PALE, "#C9D8BB", style.GREEN])

    lefts = (0.076, 0.394, 0.712)
    for letter, title, metric, left in zip(
        ("a", "b", "c"),
        ("Composite score", "Self-consistency", "Accuracy"),
        ("score", "selfc_all_publication", "accuracy_publication"),
        lefts,
        strict=True,
    ):
        style.panel(fig, letter, title, left - 0.035, 118 / 120)
        heatmap(fig, [left, 66 / 120, 0.264, 42 / 120], metric, lookup, cmap)

    # The same complete offline organization track supplies totals and components.
    mean_ax = fig.add_axes([lefts[0], 59.5 / 120, 0.264, 3.8 / 120])
    mean_ax.set_xlim(-0.5, 3.5)
    mean_ax.set_ylim(0, 1)
    mean_ax.axis("off")
    mean_ax.text(-0.8, 0.5, "Mean", ha="right", va="center", fontsize=7.4)
    for index, arm in enumerate(ARMS):
        mean_ax.text(
            index,
            0.5,
            f"{mean_lookup[arm]:.3f}",
            ha="center",
            va="center",
            fontsize=7.5,
            color=COLORS[arm],
            weight="bold",
        )

    # One common numerical key keeps the three heatmaps comparable.
    color_ax = fig.add_axes([0.586, 60 / 120, 0.273, 1.6 / 120])
    color_ax.imshow(np.linspace(0, 1, 200)[None, :], vmin=0, vmax=1, cmap=cmap, aspect="auto", extent=(0, 1, 0, 1))
    color_ax.set_yticks([])
    color_ax.set_xticks((0, 0.5, 1), ("0", "0.5", "1"))
    color_ax.tick_params(axis="x", length=2, pad=2, labelsize=7.4)
    for spine in color_ax.spines.values():
        spine.set_visible(False)

    style.panel(fig, "d", "Brief − Guided, by task", 0.041, 51.5 / 120)
    delta_ax = fig.add_axes([0.096, 12 / 120, 0.402, 29.5 / 120])
    values = np.array([float(delta_lookup[task]["brief_minus_guided"]) for task in TASKS])
    bar_colors = [COLORS["brief-errors"] if value > 0 else COLORS["guided"] for value in values]
    delta_ax.barh(np.arange(10), values, height=0.66, color=bar_colors, linewidth=0)
    delta_ax.scatter(
        np.zeros(sum(values == 0)), np.flatnonzero(values == 0), s=8, marker="o", color=style.MUTED, zorder=3
    )
    delta_ax.axvline(0, color=style.INK, linewidth=0.65)
    delta_ax.set_yticks(range(10), TASKS)
    delta_ax.invert_yaxis()
    delta_ax.set_xlim(-0.86, 1.04)
    delta_ax.set_xticks((-0.6, 0, 0.6), ("−0.6", "0", "+0.6"))
    delta_ax.set_xlabel("Composite score difference", fontsize=7.5, labelpad=3)
    style.clean_axis(delta_ax, grid="x")
    delta_ax.spines["left"].set_visible(False)
    delta_ax.tick_params(axis="y", length=0)
    for index, value in enumerate(values):
        positive = value >= 0
        inside = value < -0.5
        delta_ax.text(
            value + (0.025 if positive or inside else -0.025),
            index,
            "0" if value == 0 else f"{value:+.3f}".replace("-", "−"),
            ha="left" if positive or inside else "right",
            va="center",
            fontsize=7.4,
            color=style.WHITE if inside else style.INK,
            weight="bold" if TASKS[index] in ("IA1", "IA9", "IG8") else "normal",
        )
    wins = summary["task_wins"]
    fig.text(
        0.102,
        44.5 / 120,
        f"Brief higher: {wins['brief-errors']}     Guided higher: {wins['guided']}     Tied: {wins['tie']}",
        fontsize=7.4,
    )

    style.panel(fig, "e", "Mean score contributions", 0.562, 51.5 / 120)
    contribution_ax = fig.add_axes([0.626, 12 / 120, 0.335, 29.5 / 120])
    weighted = summary["weighted_component_mean_deltas"]
    contributions = [weighted["graph"], weighted["selfc"], weighted["accuracy"], summary["official_mean_difference"]]
    contribution_ax.bar(
        range(4),
        contributions,
        width=0.64,
        color=[style.WARM, style.WARM, COLORS["brief-errors"], COLORS["guided"]],
        linewidth=0,
    )
    contribution_ax.axhline(0, color=style.INK, linewidth=0.65)
    contribution_ax.set_xticks(range(4), ("Graph\n× 0.1", "SC\n× 0.3", "Accuracy\n× 0.6", "Total"))
    contribution_ax.set_ylim(min(-0.04, min(contributions) * 2.2), max(0.081, max(contributions) * 1.35))
    contribution_ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    contribution_ax.yaxis.set_major_formatter(StrMethodFormatter("{x:+.2f}"))
    contribution_ax.set_ylabel("Mean score difference", fontsize=7.5, labelpad=3)
    style.clean_axis(contribution_ax, grid="y")
    for index, value in enumerate(contributions):
        positive = value >= 0
        contribution_ax.text(
            index,
            value + (0.0035 if positive else -0.0025),
            f"{value:+.5f}".replace("-", "−"),
            ha="center",
            va="bottom" if positive else "top",
            fontsize=7.4,
            weight="bold" if index in (2, 3) else "normal",
        )
    fig.text(0.628, 44.5 / 120, "Brief − Guided; 10 paired tasks", fontsize=7.4)

    # Figure-border check is numerical and complements the rendered image QA.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bounds = fig.bbox
    for text in fig.findobj(match=plt.Text):
        if text.get_visible() and text.get_text():
            assert text.get_fontsize() >= 7.4, text.get_text()
            box = text.get_window_extent(renderer)
            if box.width > 0 and box.height > 0:
                assert box.x0 >= bounds.x0 - 1 and box.y0 >= bounds.y0 - 1, text.get_text()
                assert box.x1 <= bounds.x1 + 1 and box.y1 <= bounds.y1 + 1, text.get_text()

    data = {
        "source_data_dir": str(args.source_dir),
        "figure_mm": [180, 120],
        "arms": list(ARMS),
        "labels": LABELS,
        "colors": COLORS,
        "tasks": list(TASKS),
        "score_source": str(args.source_dir / "publication_scores_per_run.csv"),
        "score_track": "Common complete offline organization and scoring track for totals and components.",
        "heatmap_metrics": ["score", "selfc_all_publication", "accuracy_publication"],
        "heatmap_range": [0, 1],
        "minimum_font_pt": 7.4,
        "offline_organization_sources": [
            {
                "arm": "brief-errors",
                "task": "IC3",
                "source": "Evidence references organized from existing records; scientific claims unchanged.",
            },
            {
                "arm": "standard",
                "task": "IA9",
                "source": "Graph organized from the run's preserved artifacts; graph=1/3, SC=0.75, accuracy=0, score=0.2583, as documented in provenance.md.",
            },
        ],
        "matrix": matrix,
        "task_deltas": deltas,
        "arm_means": means,
        "summary": summary,
        "component_rounding_note": (
            f"Mean component contributions sum to {sum(contributions[:3]):+.7f}; "
            f"saved composite delta is {contributions[3]:+.7f} because final scores are rounded."
        ),
        "interpretation": "Composite, self-consistency, and accuracy scores for the offline-organized runs in the publication CSV.",
    }
    interval = summary["paired_bootstrap_ci"]
    caption = (
        "Impossible-tier outcomes after offline organization and scoring. "
        "(a–c) Composite score, self-consistency (SC), and accuracy for ten tasks and four arms, "
        "using the same complete scoring track and a shared 0–1 color scale. Backbone denotes "
        "the standard arm using the same backbone model. "
        f"Brief averages {mean_lookup['brief-errors']:.3f} and Guided {mean_lookup['guided']:.3f}. "
        f"(d) Guided scores higher on {wins['guided']} tasks, Brief on {wins['brief-errors']}, "
        f"and {wins['tie']} tie. "
        f"(e) The {summary['official_mean_difference']:+.5f} mean difference comprises "
        f"accuracy {weighted['accuracy']:+.5f}, Graph {weighted['graph']:+.5f}, "
        f"and SC {weighted['selfc']:+.5f} after weighting; the small sum discrepancy reflects "
        "saved-score rounding. The paired task-bootstrap 95% interval is "
        f"{interval['low']:+.3f} to {interval['high']:+.3f}."
    )
    style.save(fig, args.output, "bench_imp", data, caption)
    print(args.output / "bench_imp.png")


if __name__ == "__main__":
    main()
