"""Render the checked 50-task design and its saved source-name PCA; no model calls."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pypdfium2 as pdfium
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / "paper/figures/benchmark_semantic_space_20261028"
W, H = 180 / 25.4 * 72, 115 / 25.4 * 72
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
FONT_FILES = {
    "Arial": "/System/Library/Fonts/Supplemental/Arial.ttf",
    "ArialBold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "Heiti": "/System/Library/Fonts/STHeiti Light.ttc",
    "HeitiBold": "/System/Library/Fonts/STHeiti Medium.ttc",
}
for font_name, font_file in FONT_FILES.items():
    pdfmetrics.registerFont(TTFont(font_name, font_file, subfontIndex=0))

TIERS = ["easy", "normal", "hard", "impossible"]
COLORS = {"easy": "#3D6947", "normal": "#87935D", "hard": "#B58C32", "impossible": "#A56A42"}
SHAPES = {"easy": "circle", "normal": "square", "hard": "diamond", "impossible": "triangle"}
INK, MUTED, GRID = "#173B2A", "#65745F", "#E1E6D9"
LABELS = {
    "en": {
        "a": "Task tiers and evaluation focus",
        "b": "Topic space of source task names",
        "total": "50 source tasks",
        "xlabel": "PC1 (11.0%)",
        "ylabel": "PC2 (7.2%)",
        "note_a": "Tiers are predefined evaluation categories.",
        "note_b": "Topic proximity does not imply equal difficulty.",
        "focus": [
            "Elementary steps and conformational change",
            "Multi-step networks and evidence continuity",
            "Competing stereochemical pathways",
            "Method and electronic-state boundaries",
        ],
    },
    "zh": {
        "a": "任务分层与评估重点",
        "b": "原始任务名称的主题空间",
        "total": "50 道原始任务",
        "xlabel": "PC1（11.0%）",
        "ylabel": "PC2（7.2%）",
        "note_a": "分层为题库预先规定的评估类别。",
        "note_b": "主题接近不代表难度相同。",
        "focus": ["基元反应与构象变化", "多步网络与证据连续性", "竞争立体化学路径", "规定方法与电子态的适用边界"],
    },
}


def color(value):
    return tuple(int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))


class Figure:
    """One point-based drawing specification for portable SVG, vector PDF and PNG."""

    def __init__(self, stem, language):
        self.stem, self.language = stem, language
        self.svg = ET.Element(f"{{{NS}}}svg", {"width": "180mm", "height": "115mm", "viewBox": f"0 0 {W} {H}"})
        ET.SubElement(self.svg, f"{{{NS}}}title").text = LABELS[language]["a"] + "; " + LABELS[language]["b"]
        self.pdf = Canvas(str(OUT / f"{stem}.pdf"), pagesize=(W, H))
        self.pdf.setTitle("CloudraBench task design")
        self.rect(0, 0, W, H, "#FFFFFF")
        self.point_ids = []

    def line(self, x1, y1, x2, y2, stroke=GRID, width=0.5):
        ET.SubElement(
            self.svg,
            f"{{{NS}}}line",
            {"x1": str(x1), "y1": str(y1), "x2": str(x2), "y2": str(y2), "stroke": stroke, "stroke-width": str(width)},
        )
        self.pdf.setStrokeColorRGB(*color(stroke))
        self.pdf.setLineWidth(width)
        self.pdf.line(x1, H - y1, x2, H - y2)

    def rect(self, x, y, w, h, fill, stroke=None, width=0.6):
        attrs = {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "fill": fill}
        if stroke:
            attrs.update(stroke=stroke, **{"stroke-width": str(width)})
        ET.SubElement(self.svg, f"{{{NS}}}rect", attrs)
        self.pdf.setFillColorRGB(*color(fill))
        self.pdf.setLineWidth(width)
        if stroke:
            self.pdf.setStrokeColorRGB(*color(stroke))
        self.pdf.rect(x, H - y - h, w, h, stroke=bool(stroke), fill=1)

    def text(self, x, y, text, size=8, bold=False, anchor="start", rotate=False, fill=INK):
        assert size >= 7.5
        cjk = self.language == "zh" and any(ord(c) > 127 for c in text)
        font = ("HeitiBold" if bold else "Heiti") if cjk else ("ArialBold" if bold else "Arial")
        attrs = {
            "x": str(x),
            "y": str(y),
            "font-family": "Heiti SC, Arial" if cjk else "Arial",
            "font-size": str(size),
            "font-weight": "bold" if bold else "normal",
            "fill": fill,
            "text-anchor": anchor,
        }
        if rotate:
            attrs["transform"] = f"rotate(-90 {x} {y})"
        ET.SubElement(self.svg, f"{{{NS}}}text", attrs).text = text
        self.pdf.saveState()
        self.pdf.setFillColorRGB(*color(fill))
        self.pdf.setFont(font, size)
        if rotate:
            self.pdf.translate(x, H - y)
            self.pdf.rotate(90)
            x, y = 0, H
        if anchor == "middle":
            self.pdf.drawCentredString(x, H - y, text)
        elif anchor == "end":
            self.pdf.drawRightString(x, H - y, text)
        else:
            self.pdf.drawString(x, H - y, text)
        self.pdf.restoreState()

    def mark(self, x, y, tier, radius=3.2, highlighted=False, task_id=None):
        fill = COLORS[tier]
        edge = INK if highlighted else "#FFFFFF"
        width = 1 if highlighted else 0.65
        shape = SHAPES[tier]
        attrs = {"fill": fill, "stroke": edge, "stroke-width": str(width)}
        if task_id:
            attrs.update({"data-task-id": task_id, "data-tier": tier})
            self.point_ids.append(task_id)
        self.pdf.setFillColorRGB(*color(fill))
        self.pdf.setStrokeColorRGB(*color(edge))
        self.pdf.setLineWidth(width)
        if shape == "circle":
            ET.SubElement(self.svg, f"{{{NS}}}circle", {**attrs, "cx": str(x), "cy": str(y), "r": str(radius)})
            self.pdf.circle(x, H - y, radius, stroke=1, fill=1)
            return
        if shape == "square":
            points = [
                (x - radius, y - radius),
                (x + radius, y - radius),
                (x + radius, y + radius),
                (x - radius, y + radius),
            ]
        elif shape == "diamond":
            points = [(x, y - radius * 1.35), (x + radius * 1.1, y), (x, y + radius * 1.35), (x - radius * 1.1, y)]
        else:
            points = [(x, y - radius * 1.3), (x + radius * 1.2, y + radius), (x - radius * 1.2, y + radius)]
        ET.SubElement(self.svg, f"{{{NS}}}polygon", {**attrs, "points": " ".join(f"{a},{b}" for a, b in points)})
        p = self.pdf.beginPath()
        p.moveTo(points[0][0], H - points[0][1])
        for a, b in points[1:]:
            p.lineTo(a, H - b)
        p.close()
        self.pdf.drawPath(p, stroke=1, fill=1)

    def save(self):
        assert len(self.point_ids) == len(set(self.point_ids)) == 50
        self.pdf.save()
        ET.ElementTree(self.svg).write(OUT / f"{self.stem}.svg", encoding="utf-8", xml_declaration=True)
        doc = pdfium.PdfDocument(str(OUT / f"{self.stem}.pdf"))
        image = doc[0].render(scale=600 / 72).to_pil().convert("RGB")
        image.save(OUT / f"{self.stem}.png", dpi=(600, 600))
        dimensions = list(image.size)
        doc.close()
        return dimensions


def main():
    tasks = []
    for tier in TIERS:
        for path in sorted((ROOT / "ideapool/tasks" / tier).glob("*.json")):
            row = json.loads(path.read_text())
            assert row["task_id"] == path.stem and row["tier"] == tier
            tasks.append(
                {
                    "task_id": row["task_id"],
                    "tier": tier,
                    "name": row["name"],
                    "source": str(path.relative_to(ROOT)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    counts = Counter(t["tier"] for t in tasks)
    assert dict(counts) == {"easy": 20, "normal": 10, "hard": 10, "impossible": 10}
    corpus = json.loads((SOURCE / "corpus.json").read_text())
    arrays = np.load(SOURCE / "embeddings_and_projections.npz")
    ids, coordinates = arrays["task_ids"].tolist(), arrays["source_pca"]
    assert len(ids) == len(set(ids)) == 50 and set(ids) == {t["task_id"] for t in tasks}
    assert np.isfinite(coordinates).all() and coordinates.shape == (50, 2)
    by_id = {t["task_id"]: t for t in tasks}
    for c in corpus:
        assert c["raw_text"] == by_id[c["task_id"]]["name"].split(": determine ", 1)[0]
        assert c["tier"] == by_id[c["task_id"]]["tier"]
    for task in tasks:
        task["pca"] = coordinates[ids.index(task["task_id"])].astype(float).tolist()
    highlighted = {"E1", "NB1", "HA1", "IA1"}
    records = []
    for lang in ["en", "zh"]:
        text = LABELS[lang]
        fig = Figure(f"task_distribution_{lang}", lang)
        fig.rect(9, 10, 11, 11, "#D7E955")
        fig.text(14.5, 18.5, "a", 8, True, "middle")
        fig.text(25, 19, text["a"], 9.5, True)
        fig.rect(256, 10, 11, 11, "#D7E955")
        fig.text(261.5, 18.5, "b", 8, True, "middle")
        fig.text(272, 19, text["b"], 9.5, True)
        fig.text(12, 42, text["total"], 9, True)
        for i, tier in enumerate(TIERS):
            y = 64 + i * 49
            fig.text(12, y + 8, tier.capitalize(), 8.5, True)
            fig.rect(82, y, 112 * counts[tier] / 20, 11, COLORS[tier])
            fig.text(200, y + 8.5, f"{counts[tier]} ({counts[tier] * 2}%)", 7.5)
            fig.text(12, y + 31, text["focus"][i], 7.5, fill=MUTED)
        fig.text(12, 285, text["note_a"], 7.5, fill=MUTED)
        # The same unmodified PCA coordinates are used in both languages.
        px, py, pw, ph = 289, 47, 210, 193
        xlim, ylim = (-0.51, 0.59), (-0.63, 0.40)

        def xy(v):
            return px + (v[0] - xlim[0]) / (xlim[1] - xlim[0]) * pw, py + ph - (v[1] - ylim[0]) / (
                ylim[1] - ylim[0]
            ) * ph

        for value in [-0.4, 0, 0.4]:
            x, _ = xy((value, 0))
            fig.line(x, py, x, py + ph)
            fig.text(x, py + ph + 12, f"{value:.1f}", 7.5, anchor="middle", fill=MUTED)
        for value in [-0.5, 0, 0.3]:
            _, y = xy((0, value))
            fig.line(px, y, px + pw, y)
            fig.text(px - 7, y + 2.5, f"{value:.1f}", 7.5, anchor="end", fill=MUTED)
        fig.line(px, py + ph, px + pw, py + ph, MUTED, 0.65)
        fig.line(px, py, px, py + ph, MUTED, 0.65)
        fig.text(px + pw / 2, 267, text["xlabel"], 8, anchor="middle")
        fig.text(262, py + ph / 2, text["ylabel"], 8, anchor="middle", rotate=True)
        fig.text(px, 38, "50 / 50", 7.5, fill=MUTED)
        for task in sorted(tasks, key=lambda t: t["task_id"] in highlighted):
            x, y = xy(task["pca"])
            fig.mark(
                x,
                y,
                task["tier"],
                3.4 if task["task_id"] in highlighted else 3.0,
                task["task_id"] in highlighted,
                task["task_id"],
            )
        offsets = {"E1": (-11, 28), "NB1": (-48, -10), "HA1": (-27, -14), "IA1": (9, 21)}
        for task_id, (dx, dy) in offsets.items():
            x, y = xy(by_id[task_id]["pca"])
            fig.line(x + dx * 0.2, y + dy * 0.2, x + dx, y + dy - 3, MUTED, 0.55)
            fig.text(x + dx, y + dy, task_id, 8, True)
        for tier, x, y in [("easy", 293, 285), ("normal", 383, 285), ("hard", 293, 301), ("impossible", 383, 301)]:
            fig.mark(x, y - 2.5, tier, 2.7)
            fig.text(x + 8, y, tier.capitalize(), 7.5)
        fig.text(256, 320, text["note_b"], 7.5, fill=MUTED)
        dimensions = fig.save()
        records.append(
            {
                "language": lang,
                "svg": str(OUT / f"task_distribution_{lang}.svg"),
                "pdf": str(OUT / f"task_distribution_{lang}.pdf"),
                "png": str(OUT / f"task_distribution_{lang}.png"),
                "width_mm": 180,
                "height_mm": 115,
                "png_dpi": 600,
                "png_size_px": dimensions,
            }
        )
    en = "Figure 5. CloudraBench task-bank design. (a) The 50 source tasks are assigned to Easy (20), Normal (10), Hard (10), and Impossible (10). The annotations summarize the intended evaluation focus: elementary transformations and conformational changes, multi-step evidence continuity, competing stereochemical pathways, and the boundaries of prescribed methods and electronic-state treatments. These are predefined task-bank categories, not categories derived from the projection. (b) PCA of saved BAAI/bge-m3 embeddings of the original task names (PC1, 11.0%; PC2, 7.2% of variance). All 50 tasks are plotted; E1, NB1, HA1, and IA1 are labeled as the four tasks used for repeated evaluation. Color and marker shape encode the existing tier labels. This two-dimensional semantic projection illustrates topic coverage within this task bank; it neither establishes numerical difficulty nor measures chemical-space coverage. No Qwen-rewritten task descriptions are used."
    zh = "图 5. CloudraBench 题库设计。a，50 道原始任务按预先规定的类别分为 Easy（20 道）、Normal（10 道）、Hard（10 道）和 Impossible（10 道）。图内说明概括相应评估重点：基元反应与构象变化、多步过程的证据连续性、竞争立体化学路径，以及规定方法和电子态处理的适用边界。类别由题库预先规定，并非由投影结果推导。b，已保存的原始任务名称 BAAI/bge-m3 嵌入的主成分投影（PC1、PC2 分别解释 11.0% 和 7.2% 的方差）。图中保留全部 50 道任务，并标注用于重复评估的 E1、NB1、HA1 和 IA1。颜色和点形对应原有类别。该二维语义投影用于说明本题库内部的主题覆盖，不用于确定数值难度，也不代表化学空间覆盖率；未使用 Qwen 改写的任务描述。"
    provenance = {
        "task_count": 50,
        "tier_counts": dict(counts),
        "source_tasks": tasks,
        "coordinate_key": "source_pca",
        "coordinate_file": str((SOURCE / "embeddings_and_projections.npz").relative_to(ROOT)),
        "coordinate_file_sha256": hashlib.sha256((SOURCE / "embeddings_and_projections.npz").read_bytes()).hexdigest(),
        "corpus_file_sha256": hashlib.sha256((SOURCE / "corpus.json").read_bytes()).hexdigest(),
        "embedding_model": "BAAI/bge-m3",
        "embedding_revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "pca_explained_variance_ratio": [0.11001647263765335, 0.07213253527879715],
        "unused_arrays": ["rewritten_embeddings", "rewritten_pca"],
        "model_calls": 0,
        "new_experiments": 0,
        "minimum_figure_font_pt": 7.5,
        "fonts": FONT_FILES,
        "highlighted_task_ids": sorted(highlighted),
        "tier_focus_examples": {
            "easy": ["E1", "M3", "M8"],
            "normal": ["NB1", "NI1", "NQ5", "NU5"],
            "hard": ["HA1", "HB1", "HB10", "HL1"],
            "impossible": ["IA1", "IC3", "IE2", "IF3", "IG8"],
        },
        "limitations": [
            "Predefined tiers are not inferred from PCA.",
            "The two displayed PCs retain 18.2% of source-name embedding variance.",
            "All positions are preserved without jitter; nearby marks may overlap.",
            "Topic coverage is internal to the 50 selected task names, not an external chemical-space coverage estimate.",
            "Impossible includes method/electronic-state boundary questions; it is not a blanket assertion of physical inaccessibility.",
        ],
    }
    manifest = {
        "figure_number": 5,
        "caption_en": en,
        "caption_zh": zh,
        "assets": records,
        "provenance": "provenance.json",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (OUT / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    (OUT / "captions.txt").write_text(en + "\n\n" + zh + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
