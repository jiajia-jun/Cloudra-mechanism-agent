"""Reproducible 86-mm literature figures in a restrained forest/citrus palette.

Counts use systems.json directly.
Run with --data-dir pointing to another curated snapshot to preview that data.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, Rectangle
from matplotlib.textpath import TextPath

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "figures" / "agent_landscape_acid_20261027"
WIDTH = 86.0
TASKS = "TEOFRD"
GROUPS = (
    "extended_materials_surfaces",
    "finite_molecules_complexes",
    "soft_biomolecular",
    "cross_domain",
)

# One chromatic family; citrus is an accent, not a third data dimension.
INK = "#173B2A"
GREEN = "#3D6947"
OLIVE = "#667C45"
CITRUS = "#D7E955"
MUTED = "#68785F"
GUIDE = "#DFE5D4"
OPEN = "#B8C4AA"
GROUP_COLORS = dict(zip(GROUPS, (GREEN, OLIVE, "#94A15B", CITRUS)))

LABELS = {
    "en": {
        "target_title": "Chemical AI agent systems",
        "task_title": "Tasks of chemical AI agents",
        "groups": (
            "Materials / surfaces",
            "Molecules / complexes",
            "Soft matter /\nbiomolecules",
            "Multiple target classes",
        ),
        "group_titles": (
            "Materials / surfaces",
            "Molecules / complexes",
            "Soft matter / biomolecules",
            "Multiple target classes",
        ),
        "task_names": (
            "Structure / editing",
            "Static energy / properties",
            "Geometry optimization",
            "Vibrations / thermo.",
            "Explicit paths / TS",
            "Dynamics",
        ),
        "count": "Number of chemical\nAI agent systems",
        "system": "AI agent system",
        "filled": "Demonstrated",
        "open": "Unencoded",
    },
    "zh": {
        "target_title": "化学 AI Agent 系统",
        "task_title": "化学 AI Agent 的计算任务",
        "groups": ("材料 / 表面", "有限分子 / 配合物", "软物质 / 生物分子", "跨类展示"),
        "group_titles": ("材料 / 表面", "有限分子 / 配合物", "软物质 / 生物分子", "跨类展示"),
        "task_names": (
            "结构构建 / 编辑",
            "静态能量 / 性质",
            "几何优化",
            "振动 / 频率热化学",
            "显式路径 / 过渡态",
            "分子 / 量子动力学",
        ),
        "count": "化学 AI Agent 系统数量",
        "system": "化学 AI Agent 系统",
        "filled": "已展示",
        "open": "未编码",
    },
}

# Short display labels retain distinctive system identities; full names and IDs
# remain in systems.json and each exported matrix's manifest entry.
SHORT = {
    "buehler_molecular_dft_multiagent": "Buehler molecular DFT",
    "chemagents_azobenzene": "ChemAgents (azobenzene)",
    "openclaw_compchem_skills": "OpenClaw comp. chemistry",
    "multireference_qc_agent": "Multireference QC agent",
    "mdagent_biomolecular_2026": "MDAgent (bio, 2026)",
}


def style(language: str) -> dict:
    """Use actual local font files so SVG text and embedded PDF agree."""
    path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    if language == "zh":
        path = Path("/Library/Fonts/Arial Unicode.ttf")
    if path.exists():
        font_manager.fontManager.addfont(path)
        family = font_manager.FontProperties(fname=path).get_name()
    else:
        family = "DejaVu Sans"
    return {
        "font.family": family,
        "font.size": 7.5,
        "text.color": INK,
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "savefig.facecolor": "white",
    }


def canvas(height: float, width: float = WIDTH):
    fig = plt.figure(figsize=(width / 25.4, height / 25.4), facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, width), ylim=(height, 0))
    ax.axis("off")
    return fig, ax


def text(ax, x, y, value, size=7.5, **kwargs):
    return ax.text(x, y, value, fontsize=size, va="center", **kwargs)


def heading(ax, index, title, sample_n, page=None):
    # A compact citrus panel index is the only non-data ornament.
    ax.add_patch(Rectangle((3, 3.1), 3.5, 3.5, fc=CITRUS, ec="none"))
    text(ax, 4.75, 4.9, chr(96 + index), size=8, ha="center", weight="bold")
    text(ax, 9, 4.9, title, size=9, weight="bold")
    scope = f"n = {sample_n}"
    if page:
        scope += f" · {page}"
    text(ax, 83, 4.9, scope, ha="right", color=MUTED)


def number_axis(ax, x0, x1, y, upper, label):
    ax.plot((x0, x1), (y, y), lw=0.6, color=MUTED)
    step = 5 if upper <= 30 else 10
    for value in range(0, upper + 1, step):
        x = x0 + (x1 - x0) * value / upper
        ax.plot((x, x), (y, y + 0.9), lw=0.6, color=MUTED)
        text(ax, x, y + 3.4, str(value), ha="center", color=MUTED)
    text(ax, (x0 + x1) / 2, y + 7.5, label, ha="center", color=MUTED, linespacing=1.1)


def dot_counts(ax, labels, values, colors, first_y, step_y):
    x0, x1 = 43.5, 77.5
    upper = max(10, math.ceil((max(values) + 1) / 10) * 10)
    for i, (label, value, color) in enumerate(zip(labels, values, colors)):
        y = first_y + step_y * i
        text(ax, 3, y, label, linespacing=1.15)
        ax.plot((x0, x1), (y, y), lw=0.45, color=GUIDE, zorder=1)
        ax.plot((x0, x0), (y - 0.65, y + 0.65), lw=0.55, color=OPEN)
        x = x0 + (x1 - x0) * value / upper
        ax.add_patch(Circle((x, y), 1.25, fc=color, ec=INK, lw=0.65, zorder=3))
        text(ax, x + 2.1, y, str(value), size=8.5, weight="bold", zorder=4)
    return x0, x1, upper


def export(fig, out, stem, language, height, manifest, **metadata):
    """Preserve the exact physical size rather than expanding a tight bbox."""
    for ext in ("svg", "pdf", "png"):
        fig.savefig(out / f"{stem}_{language}.{ext}", dpi=400)
    plt.close(fig)
    manifest.append({
        "stem": stem,
        "language": language,
        "width_mm": WIDTH,
        "height_mm": round(height, 2),
        "minimum_font_pt": 7.5,
        **metadata,
    })


def targets(rows, language, out, manifest):
    words = LABELS[language]
    values = Counter(row["physical_target"] for row in rows)
    height = 60
    fig, ax = canvas(height)
    heading(ax, 1, words["target_title"], len(rows))
    x0, x1, upper = dot_counts(
        ax, words["groups"], [values[g] for g in GROUPS],
        [GROUP_COLORS[g] for g in GROUPS], 14, 9,
    )
    number_axis(ax, x0, x1, 48, upper, words["count"])
    export(fig, out, "targets", language, height, manifest,
           sample_n=len(rows), counts={g: values[g] for g in GROUPS})


def tasks(rows, language, out, manifest):
    words = LABELS[language]
    values = Counter(task for row in rows for task in row["demonstrated_tasks"])
    height = 78
    fig, ax = canvas(height)
    heading(ax, 2, words["task_title"], len(rows))
    x0, x1, upper = dot_counts(
        ax, words["task_names"], [values[t] for t in TASKS],
        [GREEN] * len(TASKS), 14, 9,
    )
    for i, task in enumerate(TASKS):
        # Small task codes link the count figure to the matrix columns.
        text(ax, 39.4, 14 + i * 9, task, color=OLIVE, ha="center", weight="bold")
    number_axis(ax, x0, x1, 66, upper, words["count"])
    export(fig, out, "tasks", language, height, manifest,
           sample_n=len(rows), counts={t: values[t] for t in TASKS})


def wrap_label(value, width_mm=35.5):
    """Wrap at measured font width, keeping the print font at 7.5 points."""
    font = font_manager.FontProperties(family=plt.rcParams["font.family"], size=7.5)
    lines = []
    current = ""
    for word in value.split():
        candidate = f"{current} {word}".strip()
        width = TextPath((0, 0), candidate, prop=font).get_extents().width * 25.4 / 72
        if current and width > width_mm:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def matrix_pages(records):
    sized = []
    for record in records:
        label = wrap_label(SHORT.get(record["id"], record["name"]))
        row_height = max(5.2, (label.count("\n") + 1) * 3.0 + 1.8)
        sized.append((record, label, row_height))
    # Keep chronological pages at a readable height without shrinking labels.
    pages, page, used = [], [], 0.0
    for item in sized:
        if page and (used + item[2] > 76 or len(page) >= 14):
            pages.append(page)
            page, used = [], 0.0
        page.append(item)
        used += item[2]
    if page:
        pages.append(page)
    return pages


def matrix_legend(ax, y, words, color):
    ax.add_patch(Circle((4.1, y), 0.9, fc=color, ec=INK, lw=0.55))
    text(ax, 6.6, y, words["filled"], color=MUTED)
    ax.add_patch(Circle((39.5, y), 0.9, fc="white", ec=OPEN, lw=0.55))
    text(ax, 42, y, words["open"], color=MUTED)


def matrices(rows, language, out, manifest):
    words = LABELS[language]
    xs = (48.5, 55.2, 61.9, 68.6, 75.3, 82.0)
    for gi, group in enumerate(GROUPS):
        records = [row for row in rows if row["physical_target"] == group]
        if not records:
            continue
        pages = matrix_pages(records)
        for pi, chunk in enumerate(pages, 1):
            is_cloudra_page = (group == "finite_molecules_complexes" and pi == len(pages))
            cloudra_extra = 6.2 if is_cloudra_page else 0.0
            rows_bottom = 16 + sum(item[2] for item in chunk) + cloudra_extra
            height = rows_bottom + 9
            fig, ax = canvas(height)
            page = f"{pi}/{len(pages)}" if len(pages) > 1 else None
            heading(ax, gi + 3, words["group_titles"][gi], len(records), page)
            text(ax, 8, 12, words["system"], color=MUTED)
            for x, task in zip(xs, TASKS):
                text(ax, x, 12, task, ha="center", weight="bold")
            ax.plot((3, 83), (15.3, 15.3), lw=0.7, color=INK)
            y = 16.0
            offset = sum(len(page) for page in pages[:pi - 1])
            for ri, (record, label, row_height) in enumerate(chunk, offset + 1):
                cy = y + row_height / 2
                text(ax, 3, cy, f"{ri:02d}", color=OLIVE)
                text(ax, 8, cy, label, linespacing=1.12)
                for x, task in zip(xs, TASKS):
                    present = task in record["demonstrated_tasks"]
                    ax.add_patch(Circle(
                        (x, cy), 0.97 if present else 0.78,
                        fc=GROUP_COLORS[group] if present else "white",
                        ec=INK if present else OPEN, lw=0.55 if present else 0.4,
                    ))
                y += row_height
                ax.plot((8, 83), (y, y), lw=0.3, color=GUIDE, zorder=0)

            if is_cloudra_page:
                ax.plot((3, 83), (y + 0.6, y + 0.6), lw=0.6, color=INK)
                ax.add_patch(Rectangle((3, y + 1.0), 80, 5.0, fc="#F3F6ED", ec="none", zorder=0))
                cy_c = y + 3.5
                ax.add_patch(Rectangle((3, cy_c - 1.0), 2.0, 2.0, fc=CITRUS, ec=OLIVE, lw=0.4))
                name = "Cloudra（本工作）" if language == "zh" else "Cloudra (this work)"
                text(ax, 8, cy_c, name, weight="bold", color=INK, size=7.8)
                for x, task in zip(xs, TASKS):
                    present = task in "TEOFR"
                    ax.add_patch(Circle(
                        (x, cy_c), 0.97 if present else 0.78,
                        fc=GROUP_COLORS[group] if present else "white",
                        ec=INK if present else OPEN, lw=0.55 if present else 0.4,
                    ))
                ax.plot((3, 83), (y + 6.0, y + 6.0), lw=0.4, color=GUIDE, zorder=0)

            matrix_legend(ax, rows_bottom + 4.7, words, GROUP_COLORS[group])
            export(
                fig, out, f"matrix_{group}_{pi:02d}", language, height, manifest,
                sample_n=len(rows), group_n=len(records),
                record_ids=[record["id"] for record, _, _ in chunk],
                record_names=[record["name"] for record, _, _ in chunk],
                positive_tasks={record["id"]: record["demonstrated_tasks"] for record, _, _ in chunk},
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=HERE)
    args = parser.parse_args()
    rows = json.loads((args.data_dir / "systems.json").read_text())
    rows = [row for row in rows if row.get("include_main", True)]
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for language in ("en", "zh"):
        with plt.rc_context(style(language)):
            targets(rows, language, OUT, manifest)
            tasks(rows, language, OUT, manifest)
            matrices(rows, language, OUT, manifest)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Exported {len(manifest)} figures for {len(rows)} systems to {OUT}")


if __name__ == "__main__":
    main()
