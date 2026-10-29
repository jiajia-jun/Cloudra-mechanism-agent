"""Show native E1 coordinates, target angles, and measured action transitions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from scripts.model_semantics.figure_style import (
    EDGE,
    GREEN,
    GRID,
    INK,
    LIME,
    MUTED,
    OLIVE,
    WHITE,
    clean_axis,
    configure,
    panel,
    plt,
    save,
)

# isort: split
# The shared style sets the writable Matplotlib cache before its first import.
from matplotlib.patches import Circle


def xyz_points(text: str) -> np.ndarray:
    lines = text.splitlines()
    return np.array([[float(v) for v in line.split()[1:4]] for line in lines[2:2 + int(lines[0])]])


def newman(ax, points: np.ndarray, camera: tuple, label: str, rotation: int,
           target_angle: float) -> list[dict]:
    """Use native projected directions, normalized for a Newman drawing."""
    u, v = camera
    ax.set(xlim=(-1.7, 1.7), ylim=(-1.65, 1.5), aspect="equal")
    ax.set_axis_off()
    ax.add_patch(Circle((0, 0), .28, edgecolor=OLIVE, facecolor=WHITE, lw=1.1, zorder=3))
    labels = {3: "Cl4", 4: "H5", 5: "H6", 6: "H7", 7: "H8", 8: "H9"}
    result = []
    for atom in (3, 7, 8, 4, 5, 6):
        front = atom in (4, 5, 6)
        vec = points[atom] - points[1 if front else 2]
        xy = np.array([vec @ u, vec @ v])
        xy = xy / np.linalg.norm(xy)
        start = xy * (0 if front else .28)
        end = xy * 1.04
        selected = atom in (3, 6)
        color = GREEN if selected else EDGE if atom in (5, 7, 8) else MUTED
        ax.plot([start[0], end[0]], [start[1], end[1]], color=color,
                lw=1.8 if selected else .85, zorder=4 if front else 2)
        if atom == 6:
            ax.scatter(*end, s=165, color=LIME, edgecolor="none", zorder=5)
        ax.text(*(xy * 1.32), labels[atom], ha="center", va="center",
                fontsize=8, weight="bold" if selected else "normal", color=INK if selected else color)
        result.append({"atom_1based": atom + 1, "side": "front" if front else "back",
                       "normalized_projection": xy.tolist()})
    ax.scatter(0, 0, s=16, color=INK, zorder=6)
    ax.text(0, 1.57, f"Candidate {label}  ({rotation:+d}°)", ha="center", weight="bold", fontsize=8)
    ax.text(0, -1.62, f"H7 target angle: {abs(target_angle):.1f}°", ha="center", fontsize=8,
            weight="bold", color=GREEN)
    return result


def build(source: Path, transition_source: Path, output: Path) -> None:
    raw = source.read_bytes()
    case = json.loads(raw)
    follow = json.loads(transition_source.read_text())
    geo = case["geometric_recalculation"]
    configure()
    fig = plt.figure(figsize=(7.0, 5.55))
    panel(fig, "a", "Atom-specific geometry operation", .035, .97)
    fig.text(.035, .902, "E1 · H7–C2–C3–Cl4 → 180° · view down C2 → C3", fontsize=7.5)
    input_points = xyz_points(case["source_structure"]["xyz_text"])
    axis = input_points[2] - input_points[1]
    axis /= np.linalg.norm(axis)
    toward_h7 = input_points[6] - input_points[1]
    u = toward_h7 - axis * (toward_h7 @ axis)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    # Put H7 at 12 o'clock in both drawings; front and back share one camera.
    camera = (-v, u)
    projections, angle_rows = {}, []
    for name, x, rotation in (("A", .055, 120), ("B", .385, -120)):
        c = geo["candidates"][name]
        text = case["source_events"][c["source_result_event"]]["data"]["result"]["data"]["xyz_text"]
        ax = fig.add_axes((x, .555, .285, .29))
        projections[name] = newman(ax, xyz_points(text), camera, name, rotation,
                                   c["measurements"]["H7-C2-C3-Cl4"]["signed_degrees"])
        for atom in ("H5", "H7"):
            m = c["measurements"][f"{atom}-C2-C3-Cl4"]
            angle_rows.append({"candidate": name, "atom": atom, **m,
                               "source_result_event": c["source_result_event"],
                               "xyz_sha256": c["xyz_sha256"]})
    fig.text(.71, .798, "Operation sequence", fontsize=8, weight="bold")
    for y, heading, detail in [
        (.746, "1  Specify", "H7 is the transferring H"),
        (.677, "2  Rotate", "C3 side: +120° / −120°"),
        (.608, "3  Measure", "Evaluate H7 in both candidates"),
        (.539, "4  Continue", "Next guess: candidate B")]:
        fig.text(.71, y, heading, weight="bold", fontsize=7.5)
        fig.text(.71, y - .025, detail, fontsize=6.9, color=MUTED)
    panel(fig, "b", "Target-angle residual", .035, .415)
    panel(fig, "c", "Next action", .525, .415)
    ax = fig.add_axes((.12, .15, .34, .21))
    for r in angle_rows:
        y = 1 if r["candidate"] == "A" else 0
        offset = .115 if r["atom"] == "H5" else -.115
        x = r["circular_distance_to_180_degrees"]
        ax.plot([0, x], [y + offset, y + offset], color=GRID, lw=.6)
        ax.scatter(x, y + offset, s=32, marker="o" if r["atom"] == "H7" else "s",
                   facecolor=GREEN if r["atom"] == "H7" else WHITE,
                   edgecolor=INK if r["atom"] == "H7" else MUTED, lw=.8, zorder=3)
        ax.annotate(f"{x:.1f}°", (x, y + offset), xytext=(5, -7 if r["atom"] == "H7" else 7),
                    textcoords="offset points", fontsize=7, color=GREEN if r["atom"] == "H7" else MUTED)
    ax.set(xlim=(-3, 180), ylim=(-.48, 1.48), yticks=[1, 0], yticklabels=["A", "B"],
           xticks=[0, 60, 120, 180])
    ax.set_xlabel("Circular residual to 180° (degrees)", fontsize=7, labelpad=5)
    clean_axis(ax, "x")
    fig.text(.12, .062, "○ H7 specified target    □ H5 comparator", fontsize=7, color=MUTED)
    # The three lines retain the three cyclic arrangements of action choices.
    act = fig.add_axes((.55, .15, .4, .2))
    act.set_axis_off()
    act.set(xlim=(0, 1), ylim=(-.6, 3))
    act.text(.19, 2.8, "H5 only", ha="center", weight="bold", fontsize=7.5)
    act.text(.78, 2.8, "+ H7", ha="center", weight="bold", fontsize=7.5)
    for i, r in enumerate(follow["operation_transitions"]["next_action"]):
        y = 2 - i
        act.text(.19, y, "Request H7", ha="center", va="center", color=OLIVE, fontsize=7.5)
        act.annotate("", xy=(.59, y), xytext=(.39, y),
                     arrowprops={"arrowstyle": "->", "color": EDGE, "lw": .8})
        act.text(.78, y, "Select B", ha="center", va="center", color=GREEN, weight="bold", fontsize=7.5)
        act.text(.01, y, str(r["option_rotation"] + 1), ha="right", va="center", color=MUTED, fontsize=7)
    data = {
        "source": str(source), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_case_id": case["id"], "angle_rows": angle_rows,
        "newman_projection": projections, "camera_basis": [a.tolist() for a in camera],
        "drawing": "Native XYZ directions projected normal to C2→C3; bond lengths normalized for a Newman diagram",
        "native_followup": case["native_followup"],
        "transition_source": str(transition_source),
        "transitions": follow["operation_transitions"],
        "population": "One archived DeepSeek E1 operation chain; separate local Qwen follow-up: 10 inputs, five pairs",
    }
    caption = (
        "Target-aligned geometry feedback. (a) Candidate coordinates from one archived guided/r2 E1 "
        "operation are projected down C2→C3 using a shared camera; substituent directions are retained "
        "and bond lengths normalized for a Newman diagram. The intended transferring atom is H7. "
        "Rotating the C3 side by +120° (A) or −120° (B) gives H7–C2–C3–Cl4 absolute angles of "
        "59.4° and 179.4°, respectively. The next recorded ts_resume request uses guess_B.xyz. "
        "(b) Circular angular residuals to the already specified 180° goal distinguish the H7 "
        "target from the H5 comparator. (c) Three local Qwen3.8:27b option rotations request H7 "
        "measurements when only H5 is given, then choose candidate B when H7 is supplied. "
        "Two additional counterbalanced sufficiency pairs, included in the accompanying data, "
        "likewise change from insufficient to sufficient information. The archived operation and "
        "the ten local diagnostic inputs are separate evidence sources.\n\n"
        "目标一致的几何反馈。原始候选坐标沿C2→C3投影，强调真正参与研究目标的H7。"
        "候选B的目标角为179.4°，历史后续操作也实际选用了B。局部成对诊断中，只提供H5比较量时三次均要求补测H7；"
        "提供目标量后三次均选择B。系统应把研究意图、原子身份、测量量与下一步操作保持关联。"
    )
    save(fig, output, "intent_alignment", data, caption)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path("output/cloudra_model_study_20261028")
    parser.add_argument("--source", type=Path, default=root / "operation_feedback_case.json")
    parser.add_argument("--transitions", type=Path, default=root / "history_operation_analysis.json")
    parser.add_argument("--output", type=Path, default=Path("paper/figures/model_semantics_20261028/evidence_panels"))
    args = parser.parse_args()
    build(args.source, args.transitions, args.output)


if __name__ == "__main__":
    main()
