"""Column-sized vector figures; expanded matrices are split without shrinking type."""

import json
import math
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "figures" / "agent_landscape_expanded_20261026"
ROWS = json.loads((HERE / "systems.json").read_text())
COUNTS = json.loads((HERE / "counts.json").read_text())
GROUPS = ["extended_materials_surfaces", "finite_molecules_complexes", "soft_biomolecular", "cross_domain"]
COLORS = dict(zip(GROUPS, ["#658568", "#587C92", "#BD9950", "#7A858A"]))
INK = "#263238"
TASKS = "TEOFRD"
LABELS = {
    "en": {"groups": ["Materials / surfaces", "Molecules / complexes", "Soft matter /\nbiomolecules", "Multiple target\nclasses"], "group_titles": ["Materials / surfaces", "Molecules / complexes", "Soft matter / biomolecules", "Multiple target classes"], "number": "Number of systems", "system": "System", "positive": "Filled: positive evidence; blank: unencoded.", "task_names": ["Structure / editing", "Static energy / properties", "Geometry optimization", "Vibrations / thermo.", "Explicit paths / TS", "Dynamics"], "work": "Cloudra · this work (outside sample)", "position": "Geometry perception + operators\nEvidence DAG · molecular mechanism exploration", "sample": "Structured sample; counts are not field prevalence."},
    "zh": {"groups": ["材料 / 表面", "有限分子 / 配合物", "软物质 / 生物分子", "跨类展示"], "group_titles": ["材料 / 表面", "有限分子 / 配合物", "软物质 / 生物分子", "跨类展示"], "number": "系统数量", "system": "系统", "positive": "实心：正面证据；空白：未编码。", "task_names": ["结构构建 / 编辑", "静态能量 / 性质", "几何优化", "振动 / 频率热化学", "显式路径 / 过渡态", "分子 / 量子动力学"], "work": "Cloudra · 本工作（不计入样本）", "position": "几何感知 + 几何算子\n证据 DAG · 分子反应机理探索", "sample": "结构化文献样本，不代表全领域比例。"},
}
SHORT = {"multireference_qc_agent": "Multireference QC", "evolving_ts_workflows": "Evolving TS workflows", "mdagent_biomolecular_2026": "MDAgent (bio, 2026)", "dynamate_biomolecular": "DynaMate (protein–ligand)", "matagent_lv": "MatAgent (Lv et al.)", "ursa_lammps": "URSA LAMMPS agent"}
MANIFEST = []


def style(language):
    family = "DejaVu Sans"
    if language == "zh":
        path = Path("/Library/Fonts/Arial Unicode.ttf")
        if not path.exists():
            path = Path("/System/Library/Fonts/Supplemental/Songti.ttc")
        font_manager.fontManager.addfont(path)
        family = font_manager.FontProperties(fname=path).get_name()
    return {"font.family": family, "font.size": 7.8, "text.color": INK, "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none", "axes.unicode_minus": False}


def canvas(height):
    fig = plt.figure(figsize=(86 / 25.4, height / 25.4), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, 86), ylim=(height, 0))
    ax.axis("off")
    return fig, ax


def save(fig, stem, language, height):
    OUT.mkdir(exist_ok=True, parents=True)
    for ext in ("svg", "pdf", "png"):
        fig.savefig(OUT / f"{stem}_{language}.{ext}", dpi=400, facecolor="white")
    plt.close(fig)
    MANIFEST.append({"stem": stem, "language": language, "width_mm": 86, "height_mm": height, "minimum_font_pt": 7.5})


def axis(ax, start, width, y, upper, language):
    ax.plot([start, start + width], [y, y], color="#AAB5B3", lw=.6)
    step = 5 if upper <= 30 else 10
    for value in range(0, upper + 1, step):
        x = start + width * value / upper
        ax.plot([x, x], [y, y + .8], color="#AAB5B3", lw=.6)
        ax.text(x, y + 3.2, str(value), ha="center", va="center", fontsize=7.5)
    ax.text(start + width / 2, y + 7.3, LABELS[language]["number"], ha="center", va="center", fontsize=7.5)


def targets(language):
    fig, ax = canvas(66)
    text = LABELS[language]
    ax.text(2, 4, f"n = {len(ROWS)}", va="center")
    start, width = 42, 35
    values = [COUNTS["physical_target_counts"][g] for g in GROUPS]
    upper = math.ceil((max(values) + 1) / 10) * 10
    for i, (group, value) in enumerate(zip(GROUPS, values)):
        y = 14 + 10 * i
        ax.text(2, y, text["groups"][i], va="center", linespacing=1.05)
        ax.add_patch(Rectangle((start, y - 2.1), width * value / upper, 4.2, color=COLORS[group], ec="none"))
        ax.text(start + width * value / upper + 1.2, y, str(value), va="center", weight="bold", fontsize=8)
    axis(ax, start, width, 51, upper, language)
    ax.text(2, 63, text["sample"], va="center", fontsize=7.5)
    save(fig, "targets", language, 66)


def tasks(language):
    fig, ax = canvas(73)
    text = LABELS[language]
    ax.text(2, 4, f"n = {len(ROWS)}", va="center")
    values = [COUNTS["positive_task_counts"][t] for t in TASKS]
    upper = math.ceil((max(values) + 1) / 10) * 10
    for i, (task, value) in enumerate(zip(TASKS, values)):
        y = 12 + 7.5 * i
        ax.text(2, y, text["task_names"][i], va="center")
        ax.add_patch(Rectangle((43, y - 1.9), 34 * value / upper, 3.8, color="#587C92", ec="none"))
        ax.text(43 + 34 * value / upper + 1.2, y, str(value), va="center", weight="bold", fontsize=8)
    axis(ax, 43, 34, 56, upper, language)
    note = "Tasks overlap; coverage is not scientific acceptance." if language == "en" else "任务可重叠；覆盖不等于科学验收。"
    ax.text(2, 69.5, note, va="center", fontsize=7.5)
    save(fig, "tasks", language, 73)


def matrices(language):
    text = LABELS[language]
    xs = [49, 55.7, 62.4, 69.1, 75.8, 82.5]
    for gi, group in enumerate(GROUPS):
        records = [r for r in ROWS if r["physical_target"] == group]
        wrapped = [(r, textwrap.fill(SHORT.get(r["id"], r["name"]), 26, break_long_words=False, break_on_hyphens=False)) for r in records]
        sized = [(r, label, max(5.1, (label.count("\n") + 1) * 3.2 + 1.1)) for r, label in wrapped]
        panel_count = max(1, math.ceil(sum(r[2] for r in sized) / 82))
        per_panel = math.ceil(len(sized) / panel_count)
        pages = [sized[i:i + per_panel] for i in range(0, len(sized), per_panel)]
        for pi, chunk in enumerate(pages, 1):
            callout = group == "finite_molecules_complexes" and pi == len(pages)
            height = 21 + sum(item[2] for item in chunk) + (19 if callout else 0)
            fig, ax = canvas(height)
            title = f"{text['group_titles'][gi]} (n = {len(records)})"
            if len(pages) > 1:
                title += f" · {pi}/{len(pages)}"
            ax.text(2, 4, title, va="center", color=COLORS[group], weight="bold", fontsize=7.5)
            ax.text(2, 10, text["system"], va="center", weight="bold")
            for x, task in zip(xs, TASKS):
                ax.text(x, 10, task, ha="center", va="center", weight="bold")
            ax.plot([1.5, 84.5], [13.2, 13.2], color="#AAB5B3", lw=.6)
            y = 13.5
            for i, (record, label, rh) in enumerate(chunk):
                if i % 2 == 0:
                    ax.add_patch(Rectangle((1.5, y), 83, rh, color="#F1F4F2", ec="none"))
                ax.text(2.8, y + rh / 2, label, va="center", fontsize=7.8, linespacing=1.02)
                for x, task in zip(xs, TASKS):
                    if task in record["demonstrated_tasks"]:
                        ax.add_patch(Rectangle((x - 1.05, y + rh / 2 - 1.05), 2.1, 2.1, color=COLORS[group], ec="none"))
                y += rh
            ax.text(2, y + 4, text["positive"], va="center", fontsize=7.5)
            if callout:
                ax.plot([1.5, 84.5], [y + 8, y + 8], color="#9CAF9F", lw=.7)
                ax.text(2.8, y + 12, text["work"], va="center", weight="bold", fontsize=7.5, color="#3D6250")
                ax.text(2.8, y + 15.2, text["position"], va="top", linespacing=1.12, fontsize=7.5)
            save(fig, f"matrix_{group}_{pi:02d}", language, height)


if __name__ == "__main__":
    for language in ("en", "zh"):
        with plt.rc_context(style(language)):
            targets(language)
            tasks(language)
            matrices(language)
    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=2) + "\n")
    print(f"Exported {len(MANIFEST)} column figures (SVG/PDF/400-dpi PNG) to {OUT}")
