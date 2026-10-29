#!/usr/bin/env python3
"""Plot saved identity choices by pair, representation, and option order."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from analyze_identity_binding import normalize
from figure_style import (
    EDGE,
    GREEN,
    GRID,
    INK,
    LIME,
    MUTED,
    PALE,
    WARM,
    WHITE,
    clean_axis,
    configure,
    panel,
    plt,
    save,
)
from matplotlib.patches import Rectangle
from rdkit import Chem
from rdkit.Chem import rdDepictor, rdMolDescriptors

ROOT = Path(__file__).resolve().parents[2]
NAME = "chemical_identity_stability"
CONDITIONS = (
    ("literal", "forward"), ("literal", "swapped"),
    ("equivalent_rewrite", "forward"), ("equivalent_rewrite", "swapped"),
)
GROUPS = (
    ("same_identity", "Same identity", list(range(1, 9))),
    ("same_formula_connectivity", "Same formula · changed connectivity", [10, 11, 13, 14, 15]),
    ("same_formula_connectivity_and_charge_relocation", "Connectivity + charge relocation", [9]),
    ("specified_double_bond_stereochemistry", "Specified alkene stereochemistry", [12]),
    ("protonation_and_formal_charge", "Protonation + formal charge", [16]),
)
ROW_LABELS = {
    1: "E1 · reactants", 2: "E1 · products", 3: "NB1 · reactant",
    4: "NB1 · products", 5: "HA1 · cyclic reactant", 6: "HA1 · E declaration",
    7: "HA1 · Z declaration", 8: "IA1 · reactant", 9: "E1 · reactants / products",
    10: "NB1 · reactant / products", 11: "HA1 · cyclic / acyclic",
    12: "HA1 · E / Z", 13: "NB1 · connectivity control",
    14: "HA1 · connectivity control", 15: "IA1 · ring / chain",
    16: "NB1 · protonation control",
}


def file_source(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def smiles_pair(probe: dict) -> list[str]:
    lines = probe["prompt"].splitlines()
    return [next(line.removeprefix(prefix) for line in lines if line.startswith(prefix))
            for prefix in ("SMILES 1: ", "SMILES 2: ")]


def load(study: Path) -> tuple[list[dict], dict, dict]:
    folder = study / "pilot_identity_binding"
    probe_path = folder / "frozen_probes.jsonl"
    result_path = folder / "results.json"
    provenance_path = study / "chemical_identity_controls" / "chemical_identity_provenance.json"
    probes = [json.loads(line) for line in probe_path.read_text().splitlines()]
    result_by_id = {row["id"]: row for row in json.loads(result_path.read_text())}
    provenance = json.loads(provenance_path.read_text())
    rows = []
    for probe in probes:
        if probe["mainline"].startswith("chemical_identity/"):
            row = normalize(probe, result_by_id[probe["id"]])
            row["display_smiles"] = smiles_pair(probe)
            rows.append(row)
    if len(rows) != 64 or len({row["base_case_id"] for row in rows}) != 16:
        raise ValueError("The figure requires the complete saved 16-pair × 4-condition set")
    pair_by_id = {row["base_case_id"]: row for row in provenance["pairs"]}
    for row in rows:
        if row["prediction"] not in ("A", "B"):
            raise ValueError(f"Saved choice is not A/B: {row['id']}")
    sources = {
        "frozen_probes": file_source(probe_path), "results": file_source(result_path),
        "pair_provenance": file_source(provenance_path),
        "deployment": file_source(folder / "deployment.json"),
        "script": file_source(Path(__file__)),
    }
    return rows, pair_by_id, sources


def symbol(ax, x: float, y: float, prediction: str, correct: bool, size: float = 70) -> None:
    ax.scatter([x], [y], s=size, marker="o" if correct else "D",
               color=GREEN if correct else WARM, edgecolors=WHITE, linewidths=0.5, zorder=3)
    ax.text(x, y, prediction, color=WHITE, ha="center", va="center",
            fontsize=7.5, weight="bold", zorder=4)


def molecule(ax, smiles: str, color: str) -> dict:
    """Use RDKit 2D coordinates and vector bonds for the all-carbon inset."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("Cannot parse selected saved structure")
    rdDepictor.Compute2DCoords(mol)
    positions = np.asarray(mol.GetConformer().GetPositions())[:, :2]
    for bond in mol.GetBonds():
        start, end = positions[[bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()]]
        direction = end - start
        normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
        ax.plot(*np.asarray([start, end]).T, color=color, linewidth=1.25)
        if bond.GetBondTypeAsDouble() == 2:
            center = positions.mean(axis=0)
            midpoint = (start + end) / 2
            if np.dot(normal, center - midpoint) < 0:
                normal *= -1
            inner_start = start + direction * 0.17 + normal * 0.14
            inner_end = end - direction * 0.17 + normal * 0.14
            ax.plot(*np.asarray([inner_start, inner_end]).T, color=color, linewidth=1.1)
    ax.set_aspect("equal")
    ax.margins(0.2)
    ax.axis("off")
    return {"smiles": smiles, "canonical_smiles": Chem.MolToSmiles(mol),
            "formula": rdMolDescriptors.CalcMolFormula(mol),
            "drawing": "RDKit Compute2DCoords; vector bond drawing; implicit carbon/hydrogen"}


def build(study: Path, output: Path) -> None:
    rows, pair_by_id, sources = load(study)
    lookup = {(row["base_case_id"], row["representation"], row["order"]): row for row in rows}
    configure()
    fig = plt.figure(figsize=(180 / 25.4, 143 / 25.4))
    panel(fig, "a", "Chemical identity across notation and option order", 0.025, 0.975)
    panel(fig, "b", "Same formula, different identity", 0.667, 0.975)

    ax = fig.add_axes((0.025, 0.11, 0.615, 0.79))
    ax.set(xlim=(0, 110), ylim=(123, 0))
    clean_axis(ax)
    ax.axis("off")
    xs = (61, 74, 91, 104)
    ax.text(0, 0.7, "Pair / task system", va="top", color=MUTED)
    ax.text(67.5, 0, "Source strings", ha="center", va="top", weight="bold")
    ax.text(97.5, 0, "Equivalent rewrite", ha="center", va="top", weight="bold")
    for x, (_, order) in zip(xs, CONDITIONS, strict=True):
        ax.text(x, 5, "Fwd" if order == "forward" else "Swap", ha="center", va="top", color=MUTED)
    ax.plot((0, 110), (10, 10), color=INK, linewidth=0.65)
    current = 13.0
    row_positions = {}
    for change_type, group_label, pair_numbers in GROUPS:
        ax.text(0, current, group_label, fontsize=7.5, weight="bold", va="center")
        current += 4.1
        start_y = current - 1.95
        if change_type == "same_identity":
            ax.add_patch(Rectangle((54, start_y), 26, len(pair_numbers) * 4.2,
                                   facecolor=PALE, edgecolor=EDGE, linewidth=0.5, zorder=0))
        for number in pair_numbers:
            base_id = f"chemical_identity_{number:02d}"
            row_positions[base_id] = current
            highlight = number == 14
            if highlight:
                ax.add_patch(Rectangle((0, current - 1.9), 110, 3.8,
                                       facecolor=PALE, edgecolor="none", zorder=0))
                ax.add_patch(Rectangle((0, current - 1.9), 1.0, 3.8,
                                       facecolor=LIME, edgecolor="none", zorder=1))
            ax.text(1.7 if highlight else 0, current, f"{number:02d}  {ROW_LABELS[number]}",
                    va="center", color=INK)
            for x, (representation, order) in zip(xs, CONDITIONS, strict=True):
                row = lookup[(base_id, representation, order)]
                if row["change_type"] != change_type:
                    raise ValueError("The displayed stratum disagrees with the saved pair")
                symbol(ax, x, current, row["prediction"], row["correct"])
            current += 4.2
        current += 3.4
        ax.plot((0, 110), (current - 2.2, current - 2.2), color=GRID, linewidth=0.45)

    bx = fig.add_axes((0.667, 0.12, 0.308, 0.79))
    bx.set(xlim=(0, 1), ylim=(0, 1))
    clean_axis(bx)
    bx.axis("off")
    bx.text(0.5, 0.975, "Pair 14 · HA1 reactant", ha="center", va="top", weight="bold")
    left_smiles, right_smiles = lookup[("chemical_identity_14", "literal", "forward")]["display_smiles"]
    left_ax = fig.add_axes((0.721, 0.715, 0.20, 0.15))
    right_ax = fig.add_axes((0.721, 0.445, 0.20, 0.15))
    left_mol = molecule(left_ax, left_smiles, GREEN)
    right_mol = molecule(right_ax, right_smiles, INK)
    bx.text(0.5, 0.73, left_smiles, ha="center", fontsize=7.5)
    bx.text(0.5, 0.685, r"C$_5$H$_8$", ha="center")
    bx.text(0.5, 0.62, "Connectivity control", ha="center", weight="bold")
    bx.text(0.5, 0.38, right_smiles, ha="center", fontsize=7.5)
    bx.text(0.5, 0.335, r"C$_5$H$_8$", ha="center")
    bx.plot((0, 1), (0.275, 0.275), color=GRID, linewidth=0.6)
    bx.text(0, 0.225, "Option order", color=MUTED)
    bx.text(0.58, 0.225, "A", color=MUTED, ha="center")
    bx.text(0.9, 0.225, "B", color=MUTED, ha="center")
    bx.text(0, 0.165, "Forward")
    bx.text(0.58, 0.165, "Same", ha="center")
    bx.text(0.9, 0.165, "Different", ha="center")
    bx.text(0, 0.105, "Swapped")
    bx.text(0.58, 0.105, "Different", ha="center")
    bx.text(0.9, 0.105, "Same", ha="center")

    legend = fig.add_axes((0.025, 0.018, 0.95, 0.073))
    legend.set(xlim=(0, 1), ylim=(0, 1))
    legend.axis("off")
    symbol(legend, 0.009, 0.5, "A", True, size=55)
    legend.text(0.027, 0.5, "Correct identity", va="center")
    symbol(legend, 0.232, 0.5, "A", False, size=55)
    legend.text(0.252, 0.5, "Wrong identity", va="center")
    legend.add_patch(Rectangle((0.47, 0.365), 0.014, 0.27, facecolor=PALE,
                               edgecolor=EDGE, linewidth=0.5))
    legend.text(0.495, 0.5, "Identical strings",
                va="center", color=MUTED)

    data = {
        "figure": NAME, "dimensions_mm": [180, 143], "sources": sources,
        "model": json.loads((study / "pilot_identity_binding" / "deployment.json").read_text()),
        "unit": "16 identity pairs derived from four task systems; four paired conditions per pair",
        "conditions": [{"representation": r, "option_order": o} for r, o in CONDITIONS],
        "option_meanings": {"forward": {"A": "same_identity", "B": "different_identity"},
                            "swapped": {"A": "different_identity", "B": "same_identity"}},
        "encoding": {"correct": {"shape": "circle", "color": GREEN},
                     "wrong": {"shape": "diamond", "color": WARM},
                     "cell_text": "actual saved A/B response",
                     "pale_region": "same-identity source-string pairs are identical-string baselines"},
        "display_order": [f"chemical_identity_{n:02d}" for _, _, ns in GROUPS for n in ns],
        "pair_provenance": [pair_by_id[f"chemical_identity_{n:02d}"] for _, _, ns in GROUPS for n in ns],
        "records": rows,
        "selected_pair": {"base_case_id": "chemical_identity_14", "structures": [left_mol, right_mol],
                          "origin": "formal HA1 reactant paired with a documented synthetic connectivity control",
                          "observation": "The saved response is A in all four conditions; semantic correctness changes with option order"},
        "design_connection": "Persistent chemical identity and atom references connect model intent to the intended structure; atom mapping itself is not tested here",
    }
    caption = """Chemical identity judgments across notation and option order. (a) The 64 saved local Qwen responses comprise 16 identity pairs from four task systems, grouped by change type. Columns cross source or equivalently rewritten second SMILES with forward or swapped option meanings. Letters show the recorded responses; green circles indicate correct identities and brown diamonds incorrect ones. The shaded source-string cells for pairs 01–08 contain identical strings. (b) Pair 14 comprises the HA1 reactant and its documented synthetic connectivity control, both C5H8. Structures use saved SMILES and RDKit 2D coordinates. The table gives the A/B meanings under each option order.

化学身份判断在记法与选项顺序变化下的稳定性。（a）64条本机Qwen响应来自四个任务体系中的16个身份对，按变化类型分组。四列组合第二个SMILES的原字符串或等价改写，以及正向或交换选项。字母为保存的响应；绿色圆形表示正确，棕色菱形表示错误。01–08对原字符串条件的浅色单元格使用相同字符串。（b）第14对为HA1反应物及已记录的连接方式构造对照，分子式均为C5H8。结构按保存的SMILES和RDKit二维坐标绘制；小表列出各选项顺序下A/B的含义。
"""
    save(fig, output, NAME, data, caption)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, default=ROOT / "output" / "cloudra_model_study_20261028")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "paper" / "figures" / "model_semantics_20261028" / "evidence_panels")
    args = parser.parse_args()
    build(args.study.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
