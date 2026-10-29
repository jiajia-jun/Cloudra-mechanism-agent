"""Publication styling shared by the Cloudra model-study evidence figures."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/cloudra-evidence-mpl")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

INK = "#173B2A"
GREEN = "#3D6947"
OLIVE = "#667C45"
SAGE = "#94A15B"
LIME = "#D7E955"
MUTED = "#68785F"
GRID = "#DFE5D4"
EDGE = "#B8C4AA"
PALE = "#F7F9EF"
WARM = "#A56A42"
WHITE = "#FFFFFF"


def configure() -> None:
    plt.rcParams.update({
        "font.family": "Arial", "font.size": 7.5,
        "text.color": INK, "axes.labelcolor": INK,
        "axes.edgecolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.linewidth": 0.6, "axes.titlesize": 9,
        "axes.titleweight": "bold", "xtick.labelsize": 7,
        "ytick.labelsize": 7, "legend.fontsize": 7,
        "svg.fonttype": "none", "pdf.fonttype": 42,
        "savefig.facecolor": WHITE, "figure.facecolor": WHITE,
        "lines.linewidth": 1, "hatch.linewidth": 0.5,
    })


def panel(fig, letter: str, title: str, x: float, y: float) -> None:
    """Place the manuscript's 3.5-mm lime panel tag at figure coordinates."""
    w, h = fig.get_size_inches()
    bw, bh = 3.5 / 25.4 / w, 3.5 / 25.4 / h
    fig.add_artist(Rectangle((x, y - bh), bw, bh, transform=fig.transFigure,
                             facecolor=LIME, edgecolor="none", zorder=10))
    fig.text(x + bw / 2, y - bh / 2, letter, ha="center", va="center",
             fontsize=8, weight="bold", zorder=11)
    fig.text(x + bw + 0.013, y - bh / 2, title, fontsize=9,
             weight="bold", va="center")


def clean_axis(ax, grid: str | None = None) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(length=2.5, width=0.6)
    if grid:
        ax.set_axisbelow(True)
        ax.grid(axis=grid, color=GRID, linewidth=0.45)


def save(fig, output: Path, name: str, data: dict, caption: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "svg", "pdf"):
        options = {"dpi": 320} if suffix == "png" else {}
        if suffix == "svg":
            options["metadata"] = {"Date": None}
        fig.savefig(output / f"{name}.{suffix}", **options)
    (output / f"{name}.data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / f"{name}.caption.txt").write_text(caption.strip() + "\n", encoding="utf-8")
    plt.close(fig)
