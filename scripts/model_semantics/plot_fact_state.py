#!/usr/bin/env python3
"""Plot the saved single-digit fact-state intervention; no new model execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.model_semantics.figure_style import (
    EDGE,
    GREEN,
    INK,
    MUTED,
    PALE,
    WARM,
    WHITE,
    clean_axis,
    configure,
    panel,
    save,
)

# isort: split
# Shared style sets a writable Matplotlib cache before pyplot is imported.
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle


def build(source: Path, output: Path) -> dict:
    files = {name: source / name for name in ("measurements.json", "controls.json", "manifest.json")}
    measurements, controls, manifest = (json.loads(files[name].read_text()) for name in files)
    layers = manifest["patch_layers_fixed_before_results"]
    position = manifest["fact_token_position"]
    facts = manifest["changed_measurement"]
    plotted = {}
    for order in ("forward", "swapped"):
        expected = controls[order]["clean_expected"]
        field = "all_vocab_probability_" + expected
        plotted[order] = {
            "original_fact_answer_letter": expected,
            "clean": measurements[order]["clean"][field],
            "changed": measurements[order]["corrupt"][field],
            "patch": [measurements[order][f"fact_patch_layer{layer}"][field] for layer in layers],
        }
        assert controls[order]["changed_token_positions"] == [position]
        for control in ("self_patch", "prefix_control"):
            assert controls[order][control]["all_vocab_exactly_equal"] is True
            assert controls[order][control]["max_absolute_logit_difference"] == 0
    configure()
    fig = plt.figure(figsize=(178 / 25.4, 118 / 25.4))
    panel(fig, "a", "A one-digit edit at the same input position", 0.035, 0.965)
    schematic = fig.add_axes([0.055, 0.755, 0.90, 0.15])
    schematic.set(xlim=(0, 1), ylim=(0, 1))
    schematic.axis("off")
    schematic.text(0.005, 0.96, "Reported distances (Å)", color=MUTED, va="center")
    schematic.text(0.30, 0.96, "Original", ha="center", color=GREEN, weight="bold")
    schematic.text(0.50, 0.96, "Changed", ha="center", color=WARM, weight="bold")
    for y, label, original, changed in (
        (0.59, "r(C2–C4)", facts["source"], facts["counterfactual"]),
        (0.22, "r(O3–H8)", facts["unchanged_other"], facts["unchanged_other"]),
    ):
        schematic.text(0.005, y, label, va="center")
        schematic.text(0.30, y, original, ha="center", va="center", color=GREEN)
        schematic.text(0.50, y, changed, ha="center", va="center", color=WARM if y > 0.4 else INK)
    schematic.add_patch(FancyArrowPatch((0.355, 0.59), (0.445, 0.59), arrowstyle="->",
                                        mutation_scale=9, color=MUTED, linewidth=0.8))
    for x, label, color in ((0.65, "Original", GREEN), (0.84, "Changed", WARM)):
        schematic.add_patch(Rectangle((x, 0.27), 0.15, 0.51, facecolor=PALE, edgecolor=color, linewidth=0.75))
        schematic.text(x + 0.075, 0.66, label, ha="center", va="center", fontsize=7)
        schematic.text(x + 0.075, 0.40, f"hℓ(p{position})", ha="center", va="center", fontsize=8)
    schematic.add_patch(FancyArrowPatch((0.803, 0.51), (0.837, 0.51), arrowstyle="->",
                                        mutation_scale=9, color=INK, linewidth=0.9))
    schematic.text(0.82, 0.89, "state patch", ha="center", weight="bold", fontsize=7)

    panel(fig, "b", "P(original-fact answer) after state replacement", 0.035, 0.725)
    handles = [Line2D([], [], color=MUTED, linestyle=(0, (4, 2)), label="Original input"),
               Line2D([], [], color=WARM, linestyle=(0, (1, 2)), label="Changed input"),
               Line2D([], [], color=GREEN, marker="o", markersize=3.5, label="Original-state patch")]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.53, 0.69),
               frameon=False, ncol=3, handlelength=2.1, columnspacing=1.7)
    for order, left in (("forward", 0.10), ("swapped", 0.59)):
        row = plotted[order]
        ax = fig.add_axes([left, 0.30, 0.36, 0.265])
        clean_axis(ax, "y")
        ax.set(xlim=(3, 51), ylim=(0, 1), xticks=layers, yticks=[0, 0.25, 0.5, 0.75, 1])
        ax.set_xlabel("Layer (0-based)", labelpad=4)
        ax.axhline(row["clean"], color=MUTED, linewidth=0.9, linestyle=(0, (4, 2)))
        ax.axhline(row["changed"], color=WARM, linewidth=0.9, linestyle=(0, (1, 2)))
        ax.plot(layers, row["patch"], color=GREEN, marker="o", markersize=3.8,
                markeredgecolor=WHITE, markeredgewidth=0.5, linewidth=1.05, zorder=3)
        for layer, value in zip(layers, row["patch"], strict=True):
            offset = -12 if value > 0.9 else 10
            ax.annotate(f"{value:.3f}", (layer, value), xytext=(0, offset),
                        textcoords="offset points", ha="center", va="center", fontsize=7)
        if order == "forward":
            ax.set_ylabel("P(original-fact answer)", labelpad=5)
        center = left + 0.18
        fig.text(center, 0.613, f"{order.capitalize()} · original answer {row['original_fact_answer_letter']}",
                 ha="center", fontsize=8, weight="bold")
        fig.text(center, 0.591, f"Original {row['clean']:.3f} · changed {row['changed']:.3f}",
                 ha="center", color=MUTED, fontsize=7)
    panel(fig, "c", "Control substitutions", 0.035, 0.205)
    control_ax = fig.add_axes([0.085, 0.045, 0.84, 0.12])
    control_ax.set(xlim=(0, 1), ylim=(0, 1))
    control_ax.axis("off")
    control_ax.text(0.18, 0.91, "Max |Δ logit|", ha="right", va="center", color=MUTED, fontsize=7)
    for x, label in ((0.43, f"Self patch · p{position}"), (0.78, "Unchanged prefix · p0")):
        control_ax.text(x, 0.91, label, ha="center", va="center", fontsize=7.5)
    for order, y in (("forward", 0.54), ("swapped", 0.15)):
        control_ax.text(0.18, y, order.capitalize(), ha="right", va="center", fontsize=7.5)
        for control, x in (("self_patch", 0.43), ("prefix_control", 0.78)):
            control_ax.add_patch(Rectangle((x - 0.14, y - 0.15), 0.28, 0.30,
                                          facecolor=PALE, edgecolor=EDGE, linewidth=0.6))
            value = controls[order][control]["max_absolute_logit_difference"]
            control_ax.text(x, y, f"{value:.0f}", ha="center", va="center", fontsize=7.5)

    data = {"figure": "internal_fact_state", "width_mm": 178, "height_mm": 118,
            "sources": {name: {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                        for name, path in files.items()},
            "position": position, "layers_0_based": layers, "input_edit": facts,
            "probability_definition": "Full-vocabulary-softmax probability mass of the original-fact answer, combining its bare and leading-space token spellings; not A/B renormalization or success rate.",
            "original_fact_answer": "O3-H8 is shorter under the original 2.029Å versus 1.248 Å facts; B forward and A swapped.",
            "plotted": plotted, "controls": controls, "source_manifest": manifest,
            "schematic": "Residual-state replacement at one input token; boxes do not encode measured activation magnitudes."}
    caption = (
        "Single-position reported-fact state intervention. (a) A synthetic one-digit edit changes the reported "
        "C2–C4 distance from 2.029 to 1.029 Å; O3–H8 remains 1.248 Å. Original-input residual state at token position 53 "
        "is inserted into the changed-input run at the indicated layer. (b) Points show full-vocabulary probability "
        "mass for the original-fact answer (B in forward order, A in swapped order), including bare and leading-space "
        "spellings. Horizontal lines are the original and changed "
        "input baselines. Forward substitutions do not reverse the answer preference. Swapped substitutions restore "
        "the original preference at layers 7 and 15, while layers 31 and 47 remain near the changed baseline. Layer and "
        "token indices are 0-based. (c) Same-state self replacement at p53 and replacement of the unchanged prefix "
        "at p0 preserve all vocabulary logits in both option orders."
    )
    save(fig, output, "internal_fact_state", data, caption)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("output/cloudra_model_study_20261028/fact_token_patch_pilot"))
    parser.add_argument("--output", type=Path, default=Path("paper/figures/model_semantics_20261028/evidence_panels"))
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
