#!/usr/bin/env python3
"""Plot four archived E1 geometry residuals without new geometry or QM work."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def build(source: Path, output: Path) -> dict:
    source_bytes = source.read_bytes()
    case = json.loads(source_bytes)
    recalculation = case["geometric_recalculation"]
    target = recalculation["target_degrees"]
    rows = []
    for candidate in ("A", "B"):
        record = recalculation["candidates"][candidate]
        event = case["source_events"][record["source_result_event"]]
        request = case["source_events"][event["data"]["request_event_id"]]
        operations = request["data"]["arguments_summary"]["operations"]
        rotation = next(operation["degrees"] for operation in operations if operation["type"] == "rotate")
        for atom in ("H5", "H7"):
            name = f"{atom}-C2-C3-Cl4"
            measurement = record["measurements"][name]
            difference = abs(measurement["signed_degrees"] - target) % 360
            checked_residual = min(difference, 360 - difference)
            residual = measurement["circular_distance_to_180_degrees"]
            if round(checked_residual, 10) != round(residual, 10):
                raise ValueError("Stored residual does not match the archived signed angle")
            rows.append({
                "candidate": candidate, "rotation_degrees": rotation, "atom": atom,
                "quantity": name, "role": "comparator" if atom == "H5" else "specified_target_measure",
                **measurement, "residual_degrees": residual,
                "source_result_event": record["source_result_event"],
                "source_request_event": event["data"]["request_event_id"],
                "source_event_locator": event["source"], "xyz_field": record["xyz_field"],
                "xyz_sha256": record["xyz_sha256"],
            })
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "axes.linewidth": 0.8,
        "svg.fonttype": "none", "savefig.facecolor": "white",
    })
    fig, ax = plt.subplots(figsize=(7.2, 4.1))
    fig.subplots_adjust(left=0.17, right=0.965, bottom=0.29, top=0.74)
    fig.text(0.17, 0.955, "Alignment with the specified dihedral target", fontsize=13, va="top")
    fig.text(0.17, 0.895, "One archived E1 decision · H7–C2–C3–Cl4 target: 180°", fontsize=9.5, color="#505050", va="top")
    colors = {"H5": "#777777", "H7": "#707A37"}
    markers = {"H5": "s", "H7": "o"}
    y_centers = {"A": 1, "B": 0}
    offsets = {"H5": 0.11, "H7": -0.11}
    for row in rows:
        atom = row["atom"]
        y = y_centers[row["candidate"]] + offsets[atom]
        x = row["residual_degrees"]
        ax.scatter(x, y, s=55, marker=markers[atom], color=colors[atom],
                   linewidths=0.65, edgecolors="white", zorder=3, clip_on=False)
        ax.annotate(f"{x:.1f}°", (x, y), xytext=(6, 8 if atom == "H5" else -13),
                    textcoords="offset points", ha="left", va="center", fontsize=9, color=colors[atom])
    legend = [Line2D([], [], marker=markers[atom], linestyle="none", color=colors[atom],
                     markersize=7, label=label)
              for atom, label in (("H5", "H5 comparator"), ("H7", "H7 specified target measure"))]
    fig.legend(handles=legend, loc="upper left", bbox_to_anchor=(0.158, 0.835), ncol=2,
               frameon=False, fontsize=9, columnspacing=2, handletextpad=0.55)
    ax.set_xlim(0, 180)
    ax.set_ylim(-0.38, 1.38)
    ax.set_xticks(range(0, 181, 30))
    ax.set_yticks([1, 0], ["A  (+120°)", "B  (−120°)"])
    ax.set_xlabel("Circular angular residual to 180° (degrees)", labelpad=11)
    ax.set_ylabel("Candidate", labelpad=15)
    ax.tick_params(axis="both", length=3, color="#505050", labelsize=9.5)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#E5E5E5", linewidth=0.65)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#505050")
    fig.text(0.17, 0.105, "One archived E1 decision; residuals recomputed from recorded candidate coordinates.", fontsize=8.5, color="#505050")
    fig.text(0.17, 0.055, "Reference angle: 180°; requested quantity: H7–C2–C3–Cl4.", fontsize=8.5, color="#505050")
    for suffix in ("svg", "png"):
        kwargs = {"metadata": {"Date": None}} if suffix == "svg" else {"dpi": 300}
        fig.savefig(output / f"operation_goal_alignment.{suffix}", **kwargs)
    plt.close(fig)
    data = {
        "figure": "operation_goal_alignment", "source_case_id": case["id"],
        "source_json": str(source.resolve()), "source_json_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_database": case["source"], "target_degrees": target,
        "target_source": recalculation["target_source"],
        "dihedral_function": recalculation["function"],
        "dihedral_source_file": recalculation["source_file"],
        "dihedral_source_sha256": recalculation["source_file_sha256"],
        "value_source": "geometric_recalculation.candidates.{A,B}.measurements.{H5,H7}-C2-C3-Cl4.circular_distance_to_180_degrees",
        "rows": rows, "display_precision_degrees": 1,
        "scope": "One archived E1 decision; read-only arithmetic on retained native XYZ, not new QM or independent scientific evidence. No TS or scientific-acceptance label or threshold.",
        "uncertainty": "Four deterministic archived geometry measurements; no statistical intervals estimated.",
        "encoding": {"H5": {"marker": "square", "color": colors["H5"]},
                     "H7": {"marker": "circle", "color": colors["H7"]}},
    }
    (output / "figure_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "caption.txt").write_text(
        "Circular angular residuals for two rotation candidates from one archived E1 decision. "
        "Evaluating the requested H7–C2–C3–Cl4 quantity (olive circles) places candidate B (−120° rotation; residual 0.6°) "
        "ahead of A (+120°; 120.6°), linking the candidate ranking to the quantity named by the geometry goal. "
        "Gray squares retain the H5–C2–C3–Cl4 comparator measurements from the same candidates. "
        "Residuals are shortest circular distances to 180°, recomputed from the recorded coordinates and displayed to 0.1°. "
        "Exact values, coordinate hashes and source-event locators are retained in figure_data.json.\n",
        encoding="utf-8",
    )
    return {"output": str(output.resolve()), "rows": len(rows), "source_case": case["id"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("output/cloudra_model_study_20261028/operation_feedback_case.json"))
    parser.add_argument("--output", type=Path, default=Path("paper/figures/model_semantics_20261028"))
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
