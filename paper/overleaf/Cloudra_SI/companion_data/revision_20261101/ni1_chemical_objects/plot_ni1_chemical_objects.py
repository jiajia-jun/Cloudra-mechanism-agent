"""Render the archived NI1 structures and electronic-energy diagram.

The structures are pre-rendered by render_ni1_pymol.py from archived coordinates;
no embedding or geometry optimization is performed.
Run with --output-dir DIR to write the PDF and PNG to a manuscript figure folder.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "publication_reproduction/scripts/model_semantics"))
from figure_style import GREEN, GRID, INK, MUTED, WARM, configure, panel  # noqa: E402

ATOM = {"C": "#59616B", "N": "#356CC1", "O": "#CA4547", "H": "#F2F3F5"}

def render(output_dir):
    rows = list(csv.DictReader((ROOT / "energies.csv").open()))
    data = {r["id"]: r for r in rows}
    provenance = json.loads((ROOT / "provenance.json").read_text())
    configure()
    plt.rcParams.update({"font.size": 7.8, "mathtext.fontset": "dejavusans"})
    fig = plt.figure(figsize=(180 / 25.4, 110 / 25.4), facecolor="white")
    panel(fig, "a", "Optimized structures", 0.025, 0.97)

    selected = ["RC1", "TS1", "INT1_lowest", "INT1_IRC2", "TS2", "P1_lowest"]
    titles = ["RC", "TS1", "I", "I′", "TS2", "P"]
    names = ["Reactants", "Addition TS", "Lowest conformer", "IRC conformer", "Dehydration TS", "Products"]
    centers = np.linspace(0.105, 0.905, 6)
    for center, key, title, name in zip(centers, selected, titles, names):
        ax = fig.add_axes([center - 0.075, 0.61, 0.15, 0.265])
        ax.imshow(plt.imread(ROOT / "pymol_renders" / f"{key}.png"))
        ax.axis("off")
        fig.text(center, 0.905, title, fontsize=8.7, ha="center", weight="bold", color=INK)
        fig.text(center, 0.587, name, fontsize=7.4, ha="center", color=MUTED)
    for index, key, color in [(1, "TS1", GREEN), (4, "TS2", WARM)]:
        frequency = float(data[key]["imaginary_frequency_cm1"])
        fig.text(centers[index], 0.552, rf"$\nu_{{imag}}$ = {frequency:.1f} cm$^{{-1}}$", fontsize=7.4, ha="center", color=color)
    for i, element in enumerate(["C", "H", "N", "O"]):
        x = 0.790 + i * 0.047
        fig.add_artist(Circle((x, 0.954), 0.0043, transform=fig.transFigure, facecolor=ATOM[element], edgecolor="#414A54", lw=0.35))
        fig.text(x + 0.009, 0.954, element, fontsize=7.4, va="center", color=MUTED)

    panel(fig, "b", "Electronic energy profile", 0.025, 0.505)
    ys = np.array([float(data[key]["relative_energy_kcal_mol"]) for key in selected])
    e1, e2_i, e2_ip = ys[1] - ys[0], ys[4] - ys[2], ys[4] - ys[3]
    headers = [
        rf"e1   $\Delta E^\ddagger$ = {e1:.2f}",
        rf"e2   $\Delta E^\ddagger$ = {e2_i:.2f} (vs I) / {e2_ip:.2f} (vs I′)",
    ]
    # Separate axes show the two computed steps without implying an I-to-I' path.
    # Both axes retain RC as the common zero and exactly the same energy scale.
    for left, indices, color, header in [
        (0.105, [0, 1, 2], GREEN, headers[0]),
        (0.600, [3, 4, 5], WARM, headers[1]),
    ]:
        ax = fig.add_axes([left, 0.125, 0.365, 0.325])
        xs = np.array([0.0, 1.0, 2.0])
        width = 0.34
        for j in range(2):
            ax.plot([xs[j] + width / 2, xs[j + 1] - width / 2],
                    [ys[indices[j]], ys[indices[j + 1]]], color=color, lw=1.0)
        for j, i in enumerate(indices):
            x, y = xs[j], ys[i]
            ax.plot([x - width / 2, x + width / 2], [y, y], color=color,
                    lw=1.7, solid_capstyle="butt")
            peak = j == 1
            value = f"{y:+.2f}" if y else "0.00"
            ax.text(x, y + (3.2 if peak else -3.8), f"{titles[i]}  {value}",
                    ha="center", va="bottom" if peak else "top", fontsize=7.8,
                    weight="bold" if peak else "normal", color=color if peak else INK)
        ax.text(0.01, 0.97, header, transform=ax.transAxes, fontsize=7.6,
                color=color, va="top")
        ax.set_xlim(-0.45, 2.45)
        ax.set_ylim(-29, 75)
        ax.set_yticks([-20, 0, 20, 40, 60])
        ax.set_xticks([])
        ax.tick_params(axis="y", labelsize=7.4, width=0.6, length=2.5)
        ax.spines[["top", "right", "bottom"]].set_visible(False)
        ax.spines["left"].set_linewidth(0.6)
        ax.axhline(0, color=GRID, lw=0.6, ls=(0, (2, 3)), zorder=0)
    fig.text(0.034, 0.2875, r"$\Delta E$ relative to RC / kcal mol$^{-1}$",
             fontsize=7.8, rotation=90, ha="center", va="center", color=INK)
    fig.text(0.535, 0.087, "Reaction progress (schematic)", fontsize=7.4,
             ha="center", color=INK)
    fig.text(0.105, 0.027, "B3LYP-D3(BJ)/def2-SVP · gas phase · neutral singlet · electronic energies", fontsize=7.4, color=MUTED)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["pdf", "png"]:
        fig.savefig(output_dir / f"fig_ni1_chemical_objects.{ext}", dpi=600 if ext == "pdf" else 360, facecolor="white", metadata={"Creator": "Cloudra NI1 archived-data figure"} if ext == "pdf" else None)
    plt.close(fig)
    return provenance

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    render(args.output_dir)
