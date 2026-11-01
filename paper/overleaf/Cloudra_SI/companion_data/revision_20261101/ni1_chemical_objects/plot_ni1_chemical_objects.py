"""Render the archived NI1 structures and electronic-energy diagram.

Coordinates are parsed from existing Gaussian results, never embedded or optimized.
Run with --output-dir DIR to write the PDF and PNG to a manuscript figure folder.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle
from rdkit import Chem
from rdkit.Chem import rdDetermineBonds

ROOT = Path(__file__).resolve().parent
BLUE = "#275E86"
ORANGE = "#B45E29"
INK = "#22262C"
GRAY = "#69717B"
ATOM = {"C": "#59616B", "N": "#356CC1", "O": "#CA4547", "H": "#F2F3F5"}
RADIUS = {"C": 0.118, "N": 0.126, "O": 0.126, "H": 0.075}
COV = {"C": 0.76, "N": 0.71, "O": 0.66, "H": 0.31}


def read_xyz(path):
    lines = path.read_text().splitlines()
    rows = [line.split() for line in lines[2:] if line.strip()]
    return [row[0] for row in rows], np.array([[float(v) for v in row[1:4]] for row in rows])


def projection(coords, elements):
    """Select an orthographic view with separated atom projections; preserve geometry."""
    xyz = coords - coords.mean(axis=0)
    _, _, axes = np.linalg.svd(xyz, full_matrices=False)
    if np.linalg.det(axes) < 0:
        axes[-1] *= -1
    xyz = xyz @ axes.T
    best = None
    for tilt in [-0.65, -0.35, 0.0, 0.35, 0.65]:
        for spin in np.linspace(0, 2 * np.pi, 24, endpoint=False):
            a = np.array([[np.cos(spin), -np.sin(spin), 0], [np.sin(spin), np.cos(spin), 0], [0, 0, 1]])
            b = np.array([[1, 0, 0], [0, np.cos(tilt), -np.sin(tilt)], [0, np.sin(tilt), np.cos(tilt)]])
            view = xyz @ a.T @ b.T
            score = 0.0
            for i in range(len(view)):
                for j in range(i):
                    d = np.linalg.norm(view[i, :2] - view[j, :2])
                    w = 0.6 if "H" in (elements[i], elements[j]) else 1.0
                    score += w / max(d, 0.04) ** 3
            score += 0.3 * np.ptp(view[:, 1]) / max(np.ptp(view[:, 0]), 0.1)
            if best is None or score < best[0]:
                best = score, view
    view = best[1]
    if view[np.argmax(np.linalg.norm(view[:, :2], axis=1)), 0] < 0:
        view[:, :2] *= -1
    return view


def bonds(path, elements, coords, transition):
    if not transition:
        mol = Chem.MolFromXYZBlock(path.read_text())
        rdDetermineBonds.DetermineBonds(mol, charge=0)
        return [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(b.GetBondTypeAsDouble())) for b in mol.GetBonds()]
    pairs = []
    for i in range(len(elements)):
        for j in range(i):
            if np.linalg.norm(coords[i] - coords[j]) < 1.23 * (COV[elements[i]] + COV[elements[j]]):
                pairs.append((j, i, 1))
    return pairs


def molecule(ax, row, transition=False):
    path = ROOT / row["geometry_file"]
    elements, coords = read_xyz(path)
    view = projection(coords, elements)
    # These indices refer to the archived XYZ atom order, not the benchmark map.
    changing = {"TS1": {(0, 5), (5, 9), (1, 9)}, "TS2": {(2, 3), (1, 7), (3, 7)}}.get(row["id"], set())
    linework = bonds(path, elements, coords, transition)
    present = {(min(i, j), max(i, j)) for i, j, _ in linework}
    linework += [(i, j, 1) for i, j in changing if (i, j) not in present]
    for i, j, order in sorted(linework, key=lambda x: np.mean(view[[x[0], x[1]], 2])):
        p, q = view[i, :2], view[j, :2]
        partial = (min(i, j), max(i, j)) in changing
        if order == 2 and not partial:
            v = q - p
            shift = np.array([-v[1], v[0]]) / np.linalg.norm(v) * 0.043
            for s in [-1, 1]:
                ax.plot([p[0] + s * shift[0], q[0] + s * shift[0]], [p[1] + s * shift[1], q[1] + s * shift[1]], color="#535C66", lw=1.6, zorder=2)
        else:
            ax.plot([p[0], q[0]], [p[1], q[1]], color=ORANGE if partial else "#6B737D", lw=1.45, ls=(0, (2.1, 1.6)) if partial else "solid", zorder=2)
    for i in np.argsort(view[:, 2]):
        e = elements[i]
        ax.add_patch(Circle(view[i, :2], RADIUS[e], facecolor=ATOM[e], edgecolor="#414A54", lw=0.45, zorder=3))
    center = (view[:, :2].max(0) + view[:, :2].min(0)) / 2
    span = max(np.ptp(view[:, 0]), np.ptp(view[:, 1])) + 0.65
    ax.set_xlim(center[0] - span / 2, center[0] + span / 2)
    ax.set_ylim(center[1] - span / 2, center[1] + span / 2)
    ax.set_aspect("equal")
    ax.axis("off")


def render(output_dir):
    rows = list(csv.DictReader((ROOT / "energies.csv").open()))
    data = {r["id"]: r for r in rows}
    provenance = json.loads((ROOT / "provenance.json").read_text())
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.4, "pdf.fonttype": 42, "ps.fonttype": 42, "axes.linewidth": 0.7, "mathtext.fontset": "dejavusans"})
    fig = plt.figure(figsize=(7.25, 5.45), facecolor="white")
    fig.text(0.035, 0.965, "a", fontsize=11, weight="bold", va="top")
    fig.text(0.075, 0.965, "Calculated molecular objects", fontsize=10.2, weight="bold", va="top", color=INK)
    cols = [0.035, 0.195, 0.355, 0.515, 0.675, 0.835]
    selected = ["RC1", "TS1", "INT1_lowest", "INT1_IRC2", "TS2", "P1_lowest"]
    titles = ["RC", "TS1", "I", "I′", "TS2", "P"]
    names = ["reactant complex", "addition saddle", "lowest conformer", "e2 endpoint conformer", "dehydration saddle", "imine + water"]
    for left, key, title, name in zip(cols, selected, titles, names):
        ax = fig.add_axes([left, 0.657, 0.135, 0.235])
        molecule(ax, data[key], title.startswith("TS"))
        fig.text(left + 0.0675, 0.912, title, fontsize=9.5, ha="center", weight="bold", color=INK)
        fig.text(left + 0.0675, 0.64, name, fontsize=7.2, ha="center", color=GRAY)
    fig.text(cols[1] + 0.0675, 0.614, r"1 imag.: −1481.1 cm$^{-1}$", fontsize=7.2, ha="center", color=BLUE)
    fig.text(cols[4] + 0.0675, 0.614, r"1 imag.: −1796.8 cm$^{-1}$", fontsize=7.2, ha="center", color=ORANGE)
    fig.text(0.5, 0.585, "I and I′ are conformers of the same carbinolamine object.", fontsize=8, ha="center", color=GRAY)
    for i, (element, label) in enumerate([("C", "C"), ("H", "H"), ("N", "N"), ("O", "O")]):
        x = 0.768 + i * 0.047
        fig.add_artist(Circle((x, 0.966), 0.004, transform=fig.transFigure, facecolor=ATOM[element], edgecolor="#414A54", lw=0.4))
        fig.text(x + 0.008, 0.966, label, fontsize=7.2, va="center", color=GRAY)
    fig.text(0.035, 0.555, "b", fontsize=11, weight="bold", va="top")
    fig.text(0.075, 0.555, "Electronic energies and verified step connections", fontsize=10.2, weight="bold", va="top", color=INK)
    ax = fig.add_axes([0.10, 0.18, 0.86, 0.34])
    xs = np.array([0.0, 1.0, 2.05, 2.85, 3.9, 4.95])
    ys = np.array([float(data[key]["relative_energy_kcal_mol"]) for key in selected])
    width = 0.33
    # Connections display only the two computed elementary-step chains.
    for ii, color in [([0, 1, 2], BLUE), ([3, 4, 5], ORANGE)]:
        for i, j in zip(ii[:-1], ii[1:]):
            ax.plot([xs[i] + width / 2, xs[j] - width / 2], [ys[i], ys[j]], color=color, lw=1.35, zorder=2)
        for i in ii:
            ax.plot([xs[i] - width / 2, xs[i] + width / 2], [ys[i], ys[i]], color=color, lw=2.2, zorder=3)
    for i, (x, y, label) in enumerate(zip(xs, ys, titles)):
        value = f"{y:+.2f}" if y else "0.00"
        above = i in [1, 4]
        ax.text(x, y + (3.0 if above else -3.5), f"{label}  {value}", ha="center", va="bottom" if above else "top", weight="bold", fontsize=8.1, color=INK)
    ax.text(0.39, 9.0, "e1", fontsize=8.7, weight="bold", color=BLUE)
    ax.text(3.28, 18, "e2", fontsize=8.7, weight="bold", color=ORANGE)
    ax.annotate("ΔE(I′ − I) = 0.71", xy=(2.45, -11.9), xytext=(2.45, 2.5), ha="center", fontsize=8.0, color=GRAY, arrowprops={"arrowstyle": "-", "color": "#9298A0", "lw": 0.6})
    ax.text(2.45, 26.0, "Conformer interconversion\ncalculation pending", ha="center", va="center", fontsize=7.7, color=GRAY)
    ax.text(0.03, 0.96, r"ΔE‡(e1) = 28.12", transform=ax.transAxes, fontsize=8.0, color=BLUE, va="top")
    ax.text(0.56, 0.96, r"ΔE‡(e2) = 57.92 vs I; 57.21 vs I′", transform=ax.transAxes, fontsize=8.0, color=ORANGE, va="top")
    ax.set_xlim(-0.45, 5.3)
    ax.set_ylim(-28, 78)
    ax.set_yticks([-20, 0, 20, 40, 60])
    ax.set_ylabel(r"ΔE relative to RC (kcal mol$^{-1}$)", fontsize=8.3)
    ax.set_xticks([])
    ax.tick_params(axis="y", labelsize=7.8, width=0.6, length=3)
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.axhline(0, color="#C5C9CE", lw=0.6, ls=(0, (2, 3)), zorder=0)
    fig.text(0.10, 0.125, "e1 and e2: same-TS short IRC (24 + 24 points) → endpoint Opt/Freq; both minima have 0 imaginary frequencies.", fontsize=7.7, color=INK)
    fig.text(0.10, 0.083, r"B3LYP-D3(BJ)/def2-SVP · gas phase · charge 0, singlet · electronic energies", fontsize=7.5, color=GRAY)
    fig.text(0.10, 0.043, "Reaction progress is schematic; dashed molecular contacts mark the TS reaction center.", fontsize=7.3, color=GRAY)
    output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["pdf", "png"]:
        fig.savefig(output_dir / f"fig_ni1_chemical_objects.{ext}", dpi=360, facecolor="white", metadata={"Creator": "Cloudra NI1 archived-data figure"} if ext == "pdf" else None)
    plt.close(fig)
    return provenance


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    render(args.output_dir)
