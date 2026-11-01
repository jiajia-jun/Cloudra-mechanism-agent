"""Publication figures for the completed P2 study; style follows the current paper."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/cloudra-evidence-mpl")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/model_semantics"))
import matplotlib.pyplot as plt  # noqa: E402
from figure_style import (  # noqa: E402
    EDGE,
    GREEN,
    INK,
    MUTED,
    OLIVE,
    PALE,
    SAGE,
    WARM,
    WHITE,
    clean_axis,
    configure,
    panel,
    save,
)
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

OUT = ROOT / "paper/figures/benchmark_p2_20261031"
SRC = OUT / "source_data"
ARMS = ["guided", "standard", "record", "brief-errors"]
LABELS = ["Guided", "Backbone", "Record", "Brief"]
COLORS = [GREEN, WARM, OLIVE, SAGE]
TIERS = ["easy", "normal", "hard", "impossible"]
TLABELS = ["Easy", "Normal", "Hard", "IMP"]
CMAP = LinearSegmentedColormap.from_list("cloudra-evidence", [WHITE, "#DDE5CA", SAGE, GREEN, INK])
CMAP.set_bad("#E9ECE5")
configure()
r = pd.read_csv(SRC / "publication_scores_per_run.csv")
for field in ["graph", "selfc_all", "accuracy"]:
    r[field] = r[field + "_publication"]
r["score"] = r.repaired_final.fillna(r.fair_final)
r["no_graph"] = r["flags"].fillna("").str.contains("branch=no_graph", regex=False)
r["carried"] = r["flags"].fillna("").str.contains("fair=raw", regex=False)
r["repair"] = r.repaired_final.notna()
rawcomp = r.copy()
pair = pd.read_csv(SRC / "pairwise.csv")
tierpair = pd.read_csv(SRC / "tier_pairwise.csv")
contrib = pd.read_csv(SRC / "publication_component_groups.csv")
meta = pd.read_csv(SRC / "task_structure_and_final_scores.csv")


def textcolor(v):
    color = np.array(CMAP(v)[:3])
    linear = np.where(color <= 0.04045, color / 12.92, ((color + 0.055) / 1.055) ** 2.4)
    return WHITE if float(linear @ np.array([0.2126, 0.7152, 0.0722])) < 0.25 else INK


def size(mm_w, mm_h):
    return mm_w / 25.4, mm_h / 25.4


def export(fig, name, caption, data):
    def clean(v):
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        if isinstance(v, list):
            return [clean(x) for x in v]
        if isinstance(v, float) and not np.isfinite(v):
            return None
        return v

    for text in fig.findobj(plt.Text):
        if text.get_fontsize() < 7.4:
            text.set_fontsize(7.4)
    data = {
        "source_files": [
            "source_data/publication_scores_per_run.csv",
            "source_data/component_provenance.json",
            "source_data/pairwise.csv",
            "source_data/publication_component_groups.csv",
        ],
        **data,
    }
    save(fig, OUT, name, clean(data), caption)
    print(name)


def overview():
    fig = plt.figure(figsize=size(180, 140))
    ax = fig.add_axes([0.10, 0.61, 0.86, 0.26])
    groups = ["all"] + TIERS
    vals = []
    for a, dx, col in zip(ARMS[:2], [-0.17, 0.17], COLORS[:2]):
        vv = [r.loc[r.arm.eq(a) & (True if t == "all" else r.tier.eq(t)), "score"].mean() for t in groups]
        bars = ax.bar(np.arange(5) + dx, vv, 0.31, color=col, label=LABELS[ARMS.index(a)])
        ax.bar_label(bars, labels=[f"{v:.3f}" for v in vv], padding=2, fontsize=7)
        vals.append(vv)
    ax.set(
        ylim=(0, 1.08),
        ylabel="Composite score",
        xticks=np.arange(5),
        xticklabels=["All\n50 tasks", "Easy\n20 tasks", "Normal\n10 tasks", "Hard\n10 tasks", "IMP\n10 tasks"],
    )
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
    clean_axis(ax, "y")
    ax.legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(-0.02, 1.03), borderaxespad=0)
    panel(fig, "a", "Matched backbone comparison", 0.035, 0.985)
    ax = fig.add_axes([0.10, 0.12, 0.35, 0.30])
    p = r.pivot(index="task", columns="arm", values="score")
    for t, col, m in zip(TIERS, [GREEN, OLIVE, WARM, SAGE], ["o", "s", "D", "^"]):
        ids = r.loc[r.tier.eq(t), "task"].unique()
        ax.scatter(
            p.loc[ids, "standard"],
            p.loc[ids, "guided"],
            s=14,
            facecolor=col,
            edgecolor=WHITE,
            linewidth=0.35,
            marker=m,
            label=TLABELS[TIERS.index(t)],
            zorder=3,
        )
    ax.plot([0, 1], [0, 1], color=MUTED, ls="--", lw=0.6)
    ax.set(xlim=(-0.03, 1.04), ylim=(-0.03, 1.04), xlabel="Backbone composite", ylabel="Guided composite")
    clean_axis(ax)
    ax.legend(frameon=False, ncol=2, loc="lower right", fontsize=7, handletextpad=0.3, columnspacing=0.6)
    paired_stats = pair[
        (pair.track == "official_repaired") & (pair.arm_a == "guided") & (pair.arm_b == "standard")
    ].iloc[0]
    outcome_counts = {key: int(paired_stats[key]) for key in ["a_wins", "b_wins", "ties"]}
    outcome_label = (
        f"{outcome_counts['a_wins']} higher / {outcome_counts['b_wins']} lower / {outcome_counts['ties']} tied"
    )
    ax.text(0.0, 1.07, outcome_label, transform=ax.transAxes, va="bottom", fontsize=7.4)
    panel(fig, "b", "Every task retained", 0.035, 0.51)
    ax = fig.add_axes([0.62, 0.12, 0.34, 0.30])
    rows = []
    for t in groups:
        if t == "all":
            q = pair[(pair.track == "official_repaired") & (pair.arm_a == "guided") & (pair.arm_b == "standard")].iloc[
                0
            ]
        else:
            q = tierpair[
                (tierpair.track == "official_repaired")
                & (tierpair.tier == t)
                & (tierpair.arm_a == "guided")
                & (tierpair.arm_b == "standard")
            ].iloc[0]
        rows.append({k: float(q[k]) for k in ["mean_difference", "ci_low", "ci_high"]})
    for i, q in enumerate(rows):
        ax.errorbar(
            q["mean_difference"],
            i,
            xerr=[[q["mean_difference"] - q["ci_low"]], [q["ci_high"] - q["mean_difference"]]],
            fmt="o",
            markersize=4,
            color=GREEN,
            ecolor=GREEN,
            capsize=2,
            lw=0.9,
        )
    ax.axvline(0, color=MUTED, lw=0.6)
    ax.set(yticks=range(5), yticklabels=["All"] + TLABELS, xlim=(-0.07, 0.48), xlabel="Guided − Backbone")
    ax.invert_yaxis()
    clean_axis(ax, "x")
    panel(fig, "c", "Paired gains and 95% intervals", 0.55, 0.51)
    export(
        fig,
        "bench_overview",
        "P2 benchmark outcomes under the offline-organized track. (a) Guided and the same-backbone Standard baseline across all 50 tasks and each tier. (b) All 50 paired task outcomes. (c) Mean paired score differences with 95% percentile intervals from 100,000 task-level bootstrap resamples. Each task has one run per configuration; Easy contains 20 tasks and the other tiers contain 10 each.",
        {
            "grouped_means": vals,
            "paired_differences": rows,
            "paired_tasks": p.reset_index().to_dict("records"),
            "paired_outcome_counts": outcome_counts,
        },
    )


def components():
    fig = plt.figure(figsize=size(180, 132))
    means = {}
    for k, (field, title) in enumerate(
        [("graph", "Graph"), ("selfc_all", "Self-consistency"), ("accuracy", "Accuracy")]
    ):
        x = 0.14 + k * 0.285
        ax = fig.add_axes([x, 0.58, 0.235, 0.29])
        arr = np.array(
            [[rawcomp.loc[(rawcomp.arm == a) & (rawcomp.tier == t), field].mean() for t in TIERS] for a in ARMS]
        )
        n = np.array(
            [[rawcomp.loc[(rawcomp.arm == a) & (rawcomp.tier == t), field].count() for t in TIERS] for a in ARMS]
        )
        im = ax.imshow(arr, vmin=0, vmax=1, cmap=CMAP, aspect="auto")
        ax.set(xticks=range(4), xticklabels=TLABELS, yticks=range(4), yticklabels=LABELS if k == 0 else [""] * 4)
        ax.tick_params(length=0)
        for i in range(4):
            for j in range(4):
                ax.text(
                    j,
                    i,
                    f"{arr[i, j]:.2f}\n(n={n[i, j]})",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color=textcolor(arr[i, j]),
                    linespacing=1.15,
                )
        for spine in ax.spines.values():
            spine.set_visible(False)
        panel(fig, chr(97 + k), title, 0.10 + k * 0.285, 0.975)
        means[field] = {"means": arr.tolist(), "n": n.tolist()}
    cax = fig.add_axes([0.35, 0.51, 0.33, 0.018])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal", ticks=[0, 0.25, 0.5, 0.75, 1])
    cb.ax.tick_params(length=2, labelsize=7)
    cb.outline.set_linewidth(0.4)
    ax = fig.add_axes([0.17, 0.12, 0.78, 0.25])
    cg = []
    for i, g in enumerate(["all", "normal", "hard"]):
        q = contrib[(contrib.arm_a == "guided") & (contrib.arm_b == "standard") & (contrib.group == g)].iloc[0]
        cg.append(q.to_dict())
        for j, (field, col, label) in enumerate(
            [
                ("graph_contribution", OLIVE, "0.1 × Graph"),
                ("selfc_contribution", GREEN, "0.3 × Self-consistency"),
                ("accuracy_contribution", WARM, "0.6 × Accuracy"),
            ]
        ):
            ax.barh(i + (j - 1) * 0.23, float(q[field]), height=0.20, color=col, label=label if i == 0 else None)
    ax.axvline(0, color=MUTED, lw=0.6)
    ax.set(
        yticks=range(3),
        yticklabels=["All (50 pairs)", "Normal (10 pairs)", "Hard (10 pairs)"],
        xlabel="Contribution to Guided − Backbone composite",
    )
    ax.invert_yaxis()
    clean_axis(ax, "x")
    ax.legend(frameon=False, ncol=3, loc="lower left", bbox_to_anchor=(-0.02, 1.03), fontsize=7, columnspacing=1.1)
    panel(fig, "d", "Where the paired score gains arise", 0.035, 0.44)
    export(
        fig,
        "bench_components",
        "CloudraBench score layers under the complete offline organization protocol. (a–c) Graph, Self-consistency, and Accuracy means for all 200 runs, by configuration and tier; cell labels give the full task denominators. (d) Contributions under the existing 0.1/0.3/0.6 weights for all 50 Guided–Backbone pairs, including all 10 Normal and all 10 Hard tasks. Each component is aligned with its corresponding final organized total using the run’s own recorded scoring results.",
        {"component_tier_means": means, "weighted_paired_contributions": cg},
    )


def task_matrix(tiers, name, title):
    tasks = [t for tier in tiers for t in meta.loc[meta.tier.eq(tier), "task"].tolist()]
    n = len(tasks)
    height = 160 if n > 25 else 126
    fig = plt.figure(figsize=size(180, height))
    record = []
    for k, (field, label) in enumerate(
        [("score", "Composite"), ("graph", "Graph"), ("selfc_all", "Self-consistency"), ("accuracy", "Accuracy")]
    ):
        ax = fig.add_axes([0.095 + k * 0.226, 0.17, 0.192, 0.71])
        rr = r if field == "score" else rawcomp
        pivot = rr.pivot(index="task", columns="arm", values=field).reindex(index=tasks, columns=ARMS)
        arr = pivot.to_numpy()
        im = ax.imshow(np.ma.masked_invalid(arr), vmin=0, vmax=1, cmap=CMAP, aspect="auto", interpolation="nearest")
        for i, t in enumerate(tasks):
            for j, a in enumerate(ARMS):
                v = arr[i, j]
                sym = ""
                text = "—" if not np.isfinite(v) else f"{v:.2f}{sym}"
                ax.text(j, i, text, ha="center", va="center", fontsize=7, color=textcolor(v) if np.isfinite(v) else INK)
                record.append(
                    {
                        "task": t,
                        "arm": a,
                        "field": field,
                        "value": None if not np.isfinite(v) else float(v),
                        "marker": sym,
                    }
                )
        boundary = len(meta[meta.tier.eq(tiers[0])]) - 0.5
        ax.axhline(boundary, color=WHITE, lw=2)
        ax.set(xticks=range(4), xticklabels=LABELS, yticks=range(n), yticklabels=tasks if k == 0 else [""] * n)
        ax.tick_params(axis="x", rotation=65, length=0, pad=3)
        ax.tick_params(axis="y", length=0, pad=3, labelsize=7)
        ax.set_xticks(np.arange(-0.5, 4, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
        ax.grid(which="minor", color=WHITE, linewidth=0.3)
        ax.tick_params(which="minor", length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
        panel(fig, chr(97 + k), label, 0.068 + k * 0.226, 0.98)
    cax = fig.add_axes([0.37, 0.045, 0.30, 0.012])
    fig.colorbar(im, cax=cax, orientation="horizontal", ticks=[0, 0.25, 0.5, 0.75, 1])
    cax.tick_params(length=2, labelsize=7)
    fig.text(0.02, 0.015, title, fontsize=7, color=MUTED)
    export(
        fig,
        name,
        f"Per-task CloudraBench scores: {title}. Each block shows all four configurations and one score dimension after the same offline organization protocol. All totals and components are aligned to their recorded final results; the full 200-run score table is complete. The same 0–1 scale applies to every block; cells are rounded to two decimals and the source CSV retains full precision.",
        {"tasks": tasks, "arms": ARMS, "values": record},
    )


def task_matrix_all():
    """Keep every task and score layer on one portrait publication page."""
    tasks = [t for tier in TIERS for t in meta.loc[meta.tier.eq(tier), "task"].tolist()]
    fig = plt.figure(figsize=size(180, 225))
    records = []
    boundaries = np.cumsum([len(meta[meta.tier.eq(tier)]) for tier in TIERS])
    for k, (field, label) in enumerate(
        [("score", "Composite"), ("graph", "Graph"), ("selfc_all", "Self-consistency"), ("accuracy", "Accuracy")]
    ):
        ax = fig.add_axes([0.12 + k * 0.221, 0.08, 0.198, 0.825])
        values = r.pivot(index="task", columns="arm", values=field).reindex(index=tasks, columns=ARMS)
        arr = values.to_numpy()
        im = ax.imshow(arr, vmin=0, vmax=1, cmap=CMAP, aspect="auto", interpolation="nearest")
        for i, task in enumerate(tasks):
            for j, arm in enumerate(ARMS):
                value = float(arr[i, j])
                ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=7.4, color=textcolor(value))
                records.append({"task": task, "arm": arm, "field": field, "value": value})
        for boundary in boundaries[:-1]:
            ax.axhline(boundary - 0.5, color=WHITE, lw=2.2)
        ax.set(xticks=range(4), xticklabels=LABELS, yticks=range(50), yticklabels=tasks if k == 0 else [""] * 50)
        ax.xaxis.tick_top()
        ax.tick_params(axis="x", rotation=65, length=0, pad=3, labelsize=7.4)
        for text in ax.get_xticklabels():
            text.set(ha="left", rotation_mode="anchor")
        ax.tick_params(axis="y", length=0, pad=3, labelsize=7.4)
        ax.set_xticks(np.arange(-0.5, 4, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 50, 1), minor=True)
        ax.grid(which="minor", color=WHITE, linewidth=0.3)
        ax.tick_params(which="minor", length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        panel(fig, chr(97 + k), label, 0.10 + k * 0.221, 0.993)
    start = 0
    for tier, label, end in zip(TIERS, ["Easy · 20", "Normal · 10", "Hard · 10", "Impossible · 10"], boundaries):
        center = 0.905 - ((start + end) / 2) / 50 * 0.825
        fig.text(0.025, center, label, fontsize=7.4, weight="bold", color=INK, rotation=90, ha="center", va="center")
        start = end
    cax = fig.add_axes([0.37, 0.028, 0.30, 0.007])
    fig.colorbar(im, cax=cax, orientation="horizontal", ticks=[0, 0.25, 0.5, 0.75, 1])
    cax.tick_params(length=2, labelsize=7.4)
    export(
        fig,
        "bench_tasks_all",
        "Complete per-task CloudraBench scores for all 50 tasks and four configurations. "
        "The aligned blocks show composite score, Graph, Self-consistency, and Accuracy; "
        "all 800 values are displayed on the same 0–1 scale. Tier boundaries separate 20 Easy, "
        "10 Normal, 10 Hard, and 10 Impossible tasks. Values are rounded to two decimals; "
        "the source table retains full precision.",
        {"tasks": tasks, "arms": ARMS, "values": records, "tier_boundaries": boundaries.tolist()},
    )


def cases():
    fig = plt.figure(figsize=size(180, 105))
    panel(fig, "a", "HA8: the reference state changes the barrier", 0.035, 0.985)
    ax = fig.add_axes([0.31, 0.73, 0.61, 0.17])
    vals = [29.46, 20.43, 29.48]
    labels = ["Guided: stable minimum", "Backbone: reactive conformer", "Gold: stable minimum"]
    bars = ax.barh(range(3), vals, color=[GREEN, WARM, OLIVE], height=0.56)
    ax.set(yticks=range(3), yticklabels=labels, xlim=(0, 34), xlabel="Reported electronic barrier (kcal mol$^{-1}$)")
    ax.invert_yaxis()
    ax.bar_label(bars, labels=[f"{x:.2f}" for x in vals], padding=3, fontsize=7.5)
    clean_axis(ax, "x")
    panel(fig, "b", "HH1: the same barrier, different evidence closure", 0.035, 0.635)
    ax = fig.add_axes([0.15, 0.37, 0.73, 0.16])
    xx = np.arange(3)
    vh = r[(r.task == "HH1") & r.arm.isin(["guided", "standard"])].set_index("arm")
    for a, dx, col in zip(ARMS[:2], [-0.16, 0.16], COLORS[:2]):
        vals2 = vh.loc[a, ["graph", "selfc_all", "accuracy"]].to_numpy(dtype=float)
        b = ax.bar(xx + dx, vals2, 0.30, color=col, label=LABELS[ARMS.index(a)])
        ax.bar_label(b, labels=[f"{v:.2f}" for v in vals2], padding=2, fontsize=7)
    ax.set(
        xticks=xx,
        xticklabels=["Graph", "Self-consistency", "Accuracy"],
        ylim=(0, 1.22),
        yticks=[0, 0.5, 1],
        ylabel="Component score",
    )
    clean_axis(ax, "y")
    ax.legend(frameon=False, ncol=2, loc="upper left", bbox_to_anchor=(0.02, 1.30), fontsize=7)
    fig.text(0.63, 0.58, "Both barriers: 23.48 kcal mol$^{-1}$", fontsize=7.5, ha="center", color=MUTED)
    panel(fig, "c", "NU6: an energy difference needs a pathway identity", 0.035, 0.28)
    ax = fig.add_axes([0.05, 0.025, 0.90, 0.195])
    ax.axis("off")
    box = FancyBboxPatch(
        (0, 0),
        1,
        1,
        boxstyle="round,pad=.008,rounding_size=.025",
        facecolor=PALE,
        edgecolor=EDGE,
        linewidth=0.7,
        transform=ax.transAxes,
    )
    ax.add_patch(box)
    ax.text(
        0.025, 0.79, "Concerted TS  −247.030042392 Ha", fontsize=8, weight="bold", color=INK, transform=ax.transAxes
    )
    ax.text(0.025, 0.51, "Betaine INT   −247.060060699 Ha", fontsize=8, transform=ax.transAxes)
    ax.text(0.025, 0.20, "Difference = 18.836772 kcal mol$^{-1}$", fontsize=8, weight="bold", transform=ax.transAxes)
    ax.plot([0.50, 0.50], [0.13, 0.88], transform=ax.transAxes, color=EDGE, lw=0.7)
    ax.text(0.53, 0.79, "Guided: concerted saddle region;", fontsize=7.5, color=GREEN, transform=ax.transAxes)
    ax.text(0.53, 0.54, "target INT → P saddle unresolved", fontsize=7.5, color=GREEN, transform=ax.transAxes)
    ax.text(0.53, 0.20, "Backbone: step-2 closure = 18.837", fontsize=7.5, color=WARM, transform=ax.transAxes)
    export(
        fig,
        "bench_cases",
        "Scientific attribution in matched Guided–Backbone tasks. (a) HA8 reported barriers with stable-minimum and reactive-conformer reference conventions, alongside the campaign Gold value. (b) HH1 retains the same 23.48 kcal mol−1 barrier and nearly identical accuracy while the self-consistency score differs. (c) NU6 reported energies give 18.836772 kcal mol−1. Guided describes this as access to the concerted saddle region while leaving the desired intermediate-to-product saddle unresolved; Backbone reports 18.837 as the second-step closure barrier. Energies and pathway descriptions are transcribed from the archived evidence notes.",
        {
            "HA8_reported": [29.46, 20.43, 29.48],
            "HH1": vh.reset_index().to_dict("records"),
            "NU6": {
                "concerted_ts_hartree": -247.030042392,
                "betaine_hartree": -247.060060699,
                "difference_kcal_mol": 18.836772,
            },
        },
    )


if __name__ == "__main__":
    overview()
    components()
    task_matrix(["easy", "normal"], "bench_tasks", "Easy (20 tasks) and Normal (10 tasks)")
    task_matrix(["hard", "impossible"], "bench_tasks_hi", "Hard (10 tasks) and Impossible (10 tasks)")
    task_matrix_all()
    cases()
