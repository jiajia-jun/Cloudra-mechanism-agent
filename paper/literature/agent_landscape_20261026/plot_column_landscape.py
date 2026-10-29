"""Three journal-column figures from the unchanged reviewed source records."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "figures"
ROWS = [r for r in json.loads((HERE / "systems.json").read_text()) if r["include_main"]]
COUNTS = json.loads((HERE / "counts.json").read_text())
TASKS = ["T", "E", "O", "F", "R", "D"]
GROUPS = ["extended_materials_surfaces", "finite_molecules_complexes", "soft_biomolecular"]
COLORS = dict(zip(GROUPS, ["#658568", "#587C92", "#BD9950"]))
INK = "#263238"
MUTED = "#59666A"
LIGHT = "#F1F4F2"
LABELS = {
    "en": {
        "targets": ["Materials / surfaces", "Molecules / complexes", "Soft matter /\nbiomolecules"],
        "number": "Number of systems",
        "system": "System",
        "molecules": "Molecules / complexes (n = 9)",
        "soft": "Soft matter / biomolecules (n = 3)",
        "work": "Cloudra · this work (outside the sample)",
        "position": "Geometry-aware perception + operators\nEvidence DAG · molecular mechanism exploration",
    },
    "zh": {
        "targets": ["材料 / 表面", "分子 / 配合物", "软物质 / 生物分子"],
        "number": "系统数量",
        "system": "系统",
        "molecules": "分子 / 配合物（n = 9）",
        "soft": "软物质 / 生物分子（n = 3）",
        "work": "Cloudra · 本工作（不计入样本）",
        "position": "几何感知 + 几何算子\n证据 DAG · 分子反应机理探索",
    },
}
SHORT_NAMES = {
    "el_agente_estructural": "El Agente\nEstructural",
    "el_agente_forjador": "El Agente\nForjador",
    "el_agente_quntur": "El Agente Quntur",
    "evolving_ts_workflows": "Evolving TS\nworkflows",
    "multireference_qc_agent": "Multi-reference QC",
}


def style(language):
    family = "DejaVu Sans"
    if language == "zh":
        path = Path("/Library/Fonts/Arial Unicode.ttf")
        if not path.exists():
            path = Path("/System/Library/Fonts/Supplemental/Songti.ttc")
        font_manager.fontManager.addfont(path)
        family = font_manager.FontProperties(fname=path).get_name()
    return {
        "font.family": family,
        "font.size": 7.8,
        "text.color": INK,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "axes.unicode_minus": False,
    }


def canvas(height):
    fig = plt.figure(figsize=(86 / 25.4, height / 25.4), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, 86), ylim=(height, 0))
    ax.axis("off")
    return fig, ax


def save(fig, stem, language):
    OUT.mkdir(exist_ok=True)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT / f"{stem}_{language}.{ext}", dpi=400, facecolor="white")
    plt.close(fig)


def targets(language):
    text = LABELS[language]
    fig, ax = canvas(44)
    ax.text(2, 3, f"n = {COUNTS['sample_n']}", va="center", fontsize=7.8)
    start, scale = 44, 2.35
    for group, label, y in zip(GROUPS, text["targets"], [12, 21, 30]):
        value = COUNTS["physical_target_counts"][group]
        ax.text(2, y, label, va="center", fontsize=7.8, linespacing=1.05)
        ax.add_patch(Rectangle((start, y - 2.25), value * scale, 4.5,
                               facecolor=COLORS[group], edgecolor="none"))
        ax.text(start + value * scale + 1.4, y, str(value), va="center", fontsize=8, weight="bold")
    ax.plot([start, start + 15 * scale], [35, 35], color="#AAB5B3", lw=.6)
    for value in [0, 5, 10, 15]:
        x = start + value * scale
        ax.plot([x, x], [35, 35.8], color="#AAB5B3", lw=.6)
        ax.text(x, 38.2, str(value), ha="center", va="center", fontsize=7.5, color=MUTED)
    ax.text(start + 7.5 * scale, 42, text["number"], ha="center", va="center", fontsize=7.5)
    save(fig, "agent_targets", language)


def header(ax, language, y):
    ax.text(2, y, LABELS[language]["system"], va="center", fontsize=7.8, weight="bold")
    for x, task in zip([47, 53.8, 60.6, 67.4, 74.2, 81], TASKS):
        ax.text(x, y, task, ha="center", va="center", fontsize=8, weight="bold")


def row(ax, record, y, height, number):
    if number % 2 == 0:
        ax.add_patch(Rectangle((1.5, y - height / 2), 83, height,
                               facecolor=LIGHT, edgecolor="none"))
    color = COLORS[record["physical_target"]]
    ax.text(2.8, y, SHORT_NAMES.get(record["id"], record["name"]),
            va="center", fontsize=7.8, linespacing=1.02)
    for x, task in zip([47, 53.8, 60.6, 67.4, 74.2, 81], TASKS):
        if task in record["demonstrated_tasks"]:
            ax.add_patch(Rectangle((x - 1.05, y - 1.05), 2.1, 2.1,
                                   facecolor=color, edgecolor="none"))


def materials(language):
    fig, ax = canvas(78)
    header(ax, language, 4.8)
    ax.plot([1.5, 84.5], [8.2, 8.2], color="#AAB5B3", lw=.6)
    records = [r for r in ROWS if r["physical_target"] == GROUPS[0]]
    records.sort(key=lambda r: (r["first_public_date"], r["name"]))
    for i, record in enumerate(records):
        row(ax, record, 11 + i * 4.7, 4.7, i)
    save(fig, "agent_material_tasks", language)


def molecular(language):
    text = LABELS[language]
    fig, ax = canvas(98)
    header(ax, language, 4.8)
    ax.plot([1.5, 84.5], [8.2, 8.2], color="#AAB5B3", lw=.6)
    ax.text(2.8, 11.1, text["molecules"], va="center", fontsize=7.5,
            color=COLORS[GROUPS[1]], weight="bold")
    records = [r for r in ROWS if r["physical_target"] == GROUPS[1]]
    records.sort(key=lambda r: (r["first_public_date"], r["name"]))
    for i, record in enumerate(records):
        row(ax, record, 16 + i * 5.65, 5.65, i)
    ax.plot([1.5, 84.5], [64.1, 64.1], color="#BFC8C3", lw=.6)
    ax.text(2.8, 67.2, text["soft"], va="center", fontsize=7.5,
            color="#876B32", weight="bold")
    soft = [r for r in ROWS if r["physical_target"] == GROUPS[2]]
    soft.sort(key=lambda r: (r["first_public_date"], r["name"]))
    for i, record in enumerate(soft):
        row(ax, record, 71.7 + i * 4.3, 4.3, i)
    ax.plot([1.5, 84.5], [83.7, 83.7], color="#9CAF9F", lw=.7)
    ax.text(2.8, 87, text["work"], va="center", fontsize=7.8,
            color="#3D6250", weight="bold")
    ax.text(2.8, 90.2, text["position"], va="top", fontsize=7.5, linespacing=1.2)
    save(fig, "agent_molecular_tasks", language)


if __name__ == "__main__":
    for language in ("en", "zh"):
        with plt.rc_context(style(language)):
            targets(language)
            materials(language)
            molecular(language)
    print(f"Exported six figures to {OUT}; 86 mm wide; heights 44/78/98 mm; minimum font 7.5 pt.")
