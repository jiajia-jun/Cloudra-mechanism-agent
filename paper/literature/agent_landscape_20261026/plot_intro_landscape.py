"""Compact, editable EN/ZH introduction figures from the reviewed source records."""

import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "figures"
ROWS = json.loads((HERE / "systems.json").read_text())
GROUPS = [
    "extended_materials_surfaces",
    "finite_molecules_complexes",
    "soft_biomolecular",
]
COLORS = dict(zip(GROUPS, ["#658568", "#587C92", "#BD9950"]))
TASKS = ["T", "E", "O", "F", "R", "D"]
COUNTS = Counter(r["physical_target"] for r in ROWS)
TASK_COUNTS = Counter(t for r in ROWS for t in r["demonstrated_tasks"])
ORDERED = sorted(
    ROWS,
    key=lambda r: (
        GROUPS.index(r["physical_target"]),
        r["first_public_date"],
        r["name"],
    ),
)

TEXT = {
    "en": {
        "a": "a  Demonstrated physical targets",
        "groups": [
            "Extended materials / surfaces",
            "Finite molecules / complexes",
            "Soft matter / biomolecular systems",
        ],
        "number": "Number of systems",
        "b": "b  Demonstrated tasks across the 26 reported systems",
        "tasks": [
            "Build / edit\nstructures",
            "Energy /\nproperties",
            "Geometry\nrelaxation",
            "Frequencies /\nthermochem.",
            "Transition\npaths / TS",
            "MD / quantum\ndynamics",
        ],
        "work": "Cloudra · this work",
        "position": (
            "Cheminformatics perception + geometry operators for geometric reasoning\n"
            "Evidence DAG for scientific validation · organic molecular mechanisms"
        ),
    },
    "zh": {
        "a": "a  已展示的物理研究对象",
        "groups": ["扩展材料 / 表面", "有限分子 / 配合物", "软物质 / 生物分子体系"],
        "number": "系统数量",
        "b": "b  26 个已报道系统中展示的计算任务",
        "tasks": [
            "结构\n构建 / 编辑",
            "能量 /\n性质",
            "几何\n优化",
            "频率 /\n热化学",
            "反应路径 /\n过渡态",
            "分子 / 量子\n动力学",
        ],
        "work": "Cloudra · 本工作",
        "position": (
            "化学信息学感知 + 几何算子，支持几何推理\n"
            "证据 DAG 承载科学验证 · 有机分子反应机理探索"
        ),
    },
}


def draw(language: str) -> None:
    """Export at final double-column width; all text is at least 7.2 pt."""
    labels = TEXT[language]
    family = "DejaVu Sans"
    if language == "zh":
        path = Path("/Library/Fonts/Arial Unicode.ttf")
        if not path.exists():
            path = Path("/System/Library/Fonts/Supplemental/Songti.ttc")
        font_manager.fontManager.addfont(path)
        family = font_manager.FontProperties(fname=path).get_name()

    with plt.rc_context(
        {
            "font.family": family,
            "font.size": 7.4,
            "text.color": "#263238",
            "axes.labelcolor": "#263238",
            "xtick.color": "#59666A",
            "ytick.color": "#263238",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "axes.linewidth": 0.6,
        }
    ):
        fig = plt.figure(figsize=(180 / 25.4, 190 / 25.4), facecolor="white")
        fig.text(.035, .970, labels["a"], fontsize=8.2, weight="bold", va="top")

        bars = fig.add_axes([.425, .820, .490, .112])
        for i, (group, label) in enumerate(zip(GROUPS, labels["groups"])):
            bars.barh(i, COUNTS[group], height=.49, color=COLORS[group])
            bars.text(
                COUNTS[group] + .30,
                i,
                f"{COUNTS[group]}",
                fontsize=7.8,
                weight="bold",
                va="center",
            )
        bars.set_yticks(range(3), labels["groups"], fontsize=7.4)
        bars.set_ylim(2.55, -.55)
        bars.set_xlim(0, 16)
        bars.set_xticks([0, 5, 10, 15])
        bars.tick_params(axis="y", length=0, pad=7)
        bars.tick_params(axis="x", length=2.5, labelsize=7.2, pad=2)
        bars.set_xlabel(labels["number"], fontsize=7.2, labelpad=3)
        bars.spines[["top", "right", "left"]].set_visible(False)
        bars.spines["bottom"].set_color("#B4BDBD")
        bars.xaxis.grid(True, color="#E6EAE8", linewidth=.5)
        bars.set_axisbelow(True)

        fig.text(.035, .748, labels["b"], fontsize=8.2, weight="bold", va="top")
        matrix = fig.add_axes([.365, .122, .605, .598])
        n = len(ORDERED)
        matrix.set_xlim(-.5, 5.5)
        matrix.set_ylim(n - .5, -3.1)
        for i, row in enumerate(ORDERED):
            color = COLORS[row["physical_target"]]
            matrix.add_patch(
                Rectangle(
                    (-.5, i - .5),
                    6,
                    1,
                    facecolor="#F2F5F3" if i % 2 == 0 else "white",
                    edgecolor="none",
                )
            )
            for j, task in enumerate(TASKS):
                if task in row["demonstrated_tasks"]:
                    matrix.scatter(
                        j, i, s=22, marker="s", color=color,
                        edgecolors="white", linewidths=.35,
                    )
            matrix.text(-.77, i, row["name"], ha="right", va="center", fontsize=7.4)
            matrix.add_patch(
                Rectangle(
                    (-.66, i - .29), .045, .58,
                    facecolor=color, edgecolor="none", clip_on=False,
                )
            )
        for j, (task, label) in enumerate(zip(TASKS, labels["tasks"])):
            matrix.text(j, -2.14, label, ha="center", va="center", fontsize=7.2, linespacing=1.15)
            matrix.text(j, -1.03, f"n = {TASK_COUNTS[task]}", ha="center", va="center", fontsize=7.2, color="#59666A")
        for group in GROUPS[1:]:
            k = next(i for i, row in enumerate(ORDERED) if row["physical_target"] == group)
            matrix.axhline(k - .5, color="#AEBDB4", linewidth=.7)
        matrix.axis("off")

        fig.add_artist(plt.Line2D([.035, .97], [.100, .100], transform=fig.transFigure, color="#B7C5BB", linewidth=.7))
        fig.text(.035, .085, labels["work"], fontsize=8.2, weight="bold", color="#3D6250", va="top")
        fig.text(.035, .062, labels["position"], fontsize=7.4, linespacing=1.4, va="top")

        OUT.mkdir(exist_ok=True)
        for extension in ("svg", "pdf", "png"):
            fig.savefig(OUT / f"agent_landscape_intro_{language}.{extension}", dpi=350, facecolor="white")
        plt.close(fig)


if __name__ == "__main__":
    for language in ("en", "zh"):
        draw(language)
    print(f"Exported EN/ZH at 180 × 190 mm to {OUT}")
