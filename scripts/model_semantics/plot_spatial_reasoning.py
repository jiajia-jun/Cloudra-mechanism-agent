"""Plot paired native geometry decisions and their generated-token counts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median

from scripts.model_semantics.figure_style import (
    EDGE,
    GREEN,
    GRID,
    INK,
    MUTED,
    OLIVE,
    WARM,
    WHITE,
    clean_axis,
    configure,
    panel,
    plt,
    save,
)


def build(source: Path, output: Path) -> None:
    raw = source.read_bytes()
    study = json.loads(raw)
    configure()
    sources = sorted(study["by_source"], key=lambda d: d["base_case_id"])
    conditions = [(False, "original_xyz"), (False, "tool_distances"),
                  (True, "original_xyz"), (True, "tool_distances")]
    rows, token_pairs = [], []
    fig = plt.figure(figsize=(7.0, 3.9))
    panel(fig, "a", "Geometry decisions under option reversal", 0.035, 0.96)
    panel(fig, "b", "Numerical reasoning work", 0.68, 0.96)
    ax = fig.add_axes((0.14, 0.22, 0.48, 0.51))
    ax.set(xlim=(-0.48, 3.48), ylim=(-0.75, 3.6))
    ax.set_axis_off()
    for col, (thinking, condition) in enumerate(conditions):
        ax.text(col, 4.02, "XYZ" if condition == "original_xyz" else "Measured\ndistances",
                ha="center", va="center", fontsize=7.5)
        ax.text(col - 0.15, 3.58, "F", ha="center", color=MUTED, fontsize=6.5)
        ax.text(col + 0.15, 3.58, "R", ha="center", color=MUTED, fontsize=6.5)
    ax.text(0.5, 4.73, "Direct response", ha="center", weight="bold", fontsize=7.5)
    ax.text(2.5, 4.73, "Reasoning enabled", ha="center", weight="bold", fontsize=7.5)
    ax.plot([-0.4, 1.4], [4.38, 4.38], color=GRID, lw=0.6, clip_on=False)
    ax.plot([1.6, 3.4], [4.38, 4.38], color=GRID, lw=0.6, clip_on=False)
    ax.plot([1.5, 1.5], [-0.6, 4.15], color=GRID, lw=0.6, clip_on=False)
    for i, item in enumerate(sources):
        y = 3 - i
        ax.text(-0.65, y, f"G{i + 1}", ha="right", va="center", weight="bold")
        ax.axhline(y, color=GRID, lw=0.45, zorder=0)
        for col, (thinking, condition) in enumerate(conditions):
            pair = next(p for p in item["pairs"]
                        if p["thinking"] == thinking and p["condition"] == condition)
            for order, dx in (("forward", -0.15), ("swapped", 0.15)):
                r = next(r for r in pair["records"] if r["option_order"] == order)
                x = col + dx
                if r["budget_truncated"]:
                    ax.scatter(x, y, marker="^", s=155, facecolor=WHITE,
                               edgecolor=WARM, lw=0.9, zorder=2)
                    ax.text(x, y - 0.025, "!", ha="center", va="center", color=WARM, fontsize=7)
                else:
                    ax.scatter(x, y, marker="o" if r["correct"] else "D", s=126,
                               facecolor=GREEN if r["correct"] else WHITE,
                               edgecolor=INK if r["correct"] else WARM, lw=0.75, zorder=2)
                    ax.text(x, y, r["prediction"], ha="center", va="center", fontsize=7,
                            color=WHITE if r["correct"] else WARM, weight="bold")
                rows.append({"structure": f"G{i + 1}", **r,
                             "source_xyz_sha256": item["source_xyz_sha256"]})
        for order in ("forward", "swapped"):
            rr = [next(r for r in p["records"] if r["option_order"] == order)
                  for p in item["pairs"] if p["thinking"]]
            xyz = next(r for r in rr if r["condition"] == "original_xyz")
            measured = next(r for r in rr if r["condition"] == "tool_distances")
            token_pairs.append({"structure": f"G{i + 1}", "order": order,
                                "xyz_tokens": xyz["eval_count"],
                                "distance_tokens": measured["eval_count"],
                                "xyz_budget_truncated": xyz["budget_truncated"],
                                "xyz_id": xyz["id"], "distance_id": measured["id"]})
    totals = []
    for col, key in enumerate(conditions):
        recs = [r for r in rows if (r["thinking"], r["condition"]) == key]
        summary = f"{sum(r['correct'] for r in recs)}/8"
        if any(r["budget_truncated"] for r in recs):
            summary += " + 1 limit"
        ax.text(col, -0.65, summary, ha="center", va="center", fontsize=7.2, weight="bold")
        totals.append({"thinking": key[0], "condition": key[1],
                       "correct": sum(r["correct"] for r in recs), "n": len(recs),
                       "budget_truncated": sum(r["budget_truncated"] for r in recs)})
    # Each line preserves one structure and option order across the two inputs.
    bt = fig.add_axes((0.75, 0.22, 0.21, 0.51))
    for r in token_pairs:
        ys = [r["xyz_tokens"], r["distance_tokens"]]
        bt.plot([0, 1], ys, color=EDGE, lw=0.75, zorder=1)
        bt.scatter(0, ys[0], s=25, marker="^" if r["xyz_budget_truncated"] else "o",
                   facecolor=WHITE if r["xyz_budget_truncated"] else OLIVE,
                   edgecolor=WARM if r["xyz_budget_truncated"] else INK, lw=0.7, zorder=3)
        bt.scatter(1, ys[1], s=19, color=GREEN, marker="s", edgecolor=INK, lw=0.5, zorder=3)
    bt.set(xlim=(-0.28, 1.48), ylim=(0, 1120), xticks=[0, 1],
           xticklabels=["XYZ", "Measured\ndistances"], yticks=[0, 256, 512, 768, 1024])
    bt.set_ylabel("Generated tokens", labelpad=4)
    bt.axhline(1024, color=WARM, lw=0.6, ls=(0, (3, 3)))
    bt.text(0.98, 1058, "Output limit", color=WARM, fontsize=6.8, ha="right")
    mt = [median([r[k] for r in token_pairs]) for k in ("xyz_tokens", "distance_tokens")]
    fig.text(.75, .83, "Reasoning enabled · 8 pairs", color=MUTED, fontsize=7)
    fig.text(.75, .785, f"Median: {mt[0]:.0f} → {mt[1]:.0f} tokens", fontsize=7.5, weight="bold")
    clean_axis(bt)
    # Compact outcome legend also explains what is written inside each cell.
    legend = fig.add_axes((0.14, 0.055, 0.81, 0.06))
    legend.set_axis_off()
    for x, marker, fill, edge, text in [
        (0, "o", GREEN, INK, "Correct"), (.2, "D", WHITE, WARM, "Wrong"),
        (.4, "^", WHITE, WARM, "Budget limit")]:
        legend.scatter(x, .5, s=35, marker=marker, facecolor=fill, edgecolor=edge, lw=.7)
        legend.text(x+.025, .5, text, va="center", fontsize=7)
    legend.text(.65, .5, "F / R: original / reversed options", va="center", fontsize=7, color=MUTED)
    legend.set(xlim=(-.025, 1.03), ylim=(0, 1))
    data = {"source": str(source), "source_sha256": hashlib.sha256(raw).hexdigest(),
            "model": study["model"], "rows": rows, "totals": totals,
            "token_pairs": token_pairs, "median_tokens": {"xyz": mt[0], "distances": mt[1]},
            "population": "4 NB1 geometries, 2 option orders, 2 representations, 2 thinking settings",
            "token_measure": "Native generated-token count, including thinking when enabled",
            "distance_condition": "Externally computed numerical distances, not formatting alone"}
    caption = (
        "Spatial decisions and numerical reasoning work. (a) Four archived NB1 geometries are shown "
        "under direct response and reasoning-enabled native chat, using either Cartesian coordinates "
        "or tool-computed distances. Each pair retains the actual answer letters under original (F) "
        "and reversed (R) option order. Filled circles are correct, open diamonds are wrong, and the "
        "triangle is the one response reaching the 1,024-token budget without a final choice. "
        "The direct XYZ condition answers A throughout; measured distances retain the same correct "
        "semantic answer under option reversal. (b) Each connector follows one of the eight "
        "geometry/order combinations with reasoning enabled. Median generated-token counts are "
        f"{mt[0]:.1f} for XYZ and {mt[1]:.0f} for distances. All 32 inputs use local Qwen3.8:27b; "
        "four source geometries are reused across conditions.\n\n"
        "空间判断与数值推理负担。每一对圆点保留选项交换前后的实际回答。直接读取XYZ时始终回答A；"
        "工具测量距离后，两种选项顺序均正确。开启思考后，连接线显示同一输入从坐标推算到直接利用测量值所需的生成token。"
        "这将工具的作用落到明确分工：程序计算几何关系，模型据此作出化学决策。"
    )
    save(fig, output, "spatial_reasoning", data, caption)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("output/cloudra_model_study_20261028/native_chat_analysis.json"))
    parser.add_argument("--output", type=Path, default=Path("paper/figures/model_semantics_20261028/evidence_panels"))
    args = parser.parse_args()
    build(args.source, args.output)


if __name__ == "__main__":
    main()
