"""Redraw three evidence diagrams as editable vectors at manuscript size."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

HERE = Path(__file__).resolve().parent
INK = "#173E2E"
SAGE = "#F3F6ED"
LINE = "#98AB80"
ACID = "#D6E655"
WARM = "#A36B47"
PALE_WARM = "#FAF5EF"
BACK = "#E8EEDC"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 7.5,
    "text.color": INK, "pdf.fonttype": 42, "svg.fonttype": "none",
    "savefig.facecolor": "white", "axes.unicode_minus": True,
})


def canvas(width, height):
    fig = plt.figure(figsize=(width / 25.4, height / 25.4), dpi=180)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, width), ylim=(0, height))
    ax.axis("off")
    return fig, ax, []


def rounded(ax, box, fill=SAGE, edge=LINE, radius=1.1, width=.65, zorder=2):
    x, y, w, h = box
    patch = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
                          linewidth=width, edgecolor=edge, facecolor=fill, zorder=zorder)
    ax.add_patch(patch)
    return patch


def stack(ax, box):
    x, y, w, h = box
    rounded(ax, (x + 1, y - .8, w, h), "white", "#D5DEC7", .65, .45, 0)
    rounded(ax, (x + .5, y - .4, w, h), BACK, "#B8C7A4", .65, .5, 1)
    rounded(ax, box, "white", LINE, .65)


def cut_card(ax, box, fill=PALE_WARM, edge=WARM, cut=2.3):
    x, y, w, h = box
    points = [(x, y), (x + w, y), (x + w, y + h - cut),
              (x + w - cut, y + h), (x, y + h)]
    ax.add_patch(Polygon(points, closed=True, edgecolor=edge, facecolor=fill,
                         linewidth=.75, zorder=2))
    ax.plot((x + w - cut, x + w - cut, x + w),
            (y + h, y + h - cut, y + h - cut), color=edge, linewidth=.55, zorder=3)


def text(ax, checks, x, y, value, size=7.5, weight="normal", color=INK,
         ha="left", box=None, name="", va="top", **kwargs):
    artist = ax.text(x, y, value, fontsize=size, weight=weight, color=color,
                     ha=ha, va=va, linespacing=1.2, zorder=5, **kwargs)
    if box is not None:
        checks.append((name or value, artist, box))
    return artist


def arrow(ax, start, end, color=INK, scale=5.7):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=scale,
                                 color=color, linewidth=.65, shrinkA=0, shrinkB=0,
                                 zorder=3))


def content_box(box, pad=1.6):
    x, y, w, h = box
    return (x + pad, y + pad, w - 2 * pad, h - 2 * pad)


def finish(fig, ax, checks, name, width, height):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    minimum_margin = float("inf")
    failures = []
    for label, artist, box in checks:
        x, y, w, h = box
        lower = ax.transData.transform((x, y))
        upper = ax.transData.transform((x + w, y + h))
        bounds = artist.get_window_extent(renderer)
        margins = [bounds.x0 - lower[0], upper[0] - bounds.x1,
                   bounds.y0 - lower[1], upper[1] - bounds.y1]
        minimum_margin = min(minimum_margin, *margins)
        if min(margins) < -.2:
            failures.append((label, [round(v, 2) for v in margins]))
    if failures:
        raise ValueError(f"{name}: text outside padded card regions: {failures}")
    for suffix in ("svg", "pdf", "png"):
        fig.savefig(HERE / f"{name}.{suffix}", dpi=600)
    plt.close(fig)
    return {"name": name, "width_mm": width, "height_mm": height,
            "min_font_pt": 7.5, "checked_text_blocks": len(checks),
            "minimum_card_padding_mm": 1.6 if name == "fact_intervention" else 1.4,
            "minimum_extra_clearance_mm": round(float(minimum_margin) / fig.dpi * 25.4, 3)}


def fact_intervention():
    width, height = 155, 28
    fig, ax, checks = canvas(width, height)
    text(ax, checks, 2, 26.6, "A one-digit edit at the same input position", 10.1, "bold")
    ledger = (2, 2.1, 79, 18.5)
    stack(ax, ledger)
    inner = content_box(ledger, 1.6)
    text(ax, checks, 4.3, 18.5, "Reported distances (Å)", 7.7, "bold", box=inner)
    text(ax, checks, 49.3, 18.5, "Original", 7.7, "bold", ha="center", box=inner)
    text(ax, checks, 69.3, 18.5, "Changed", 7.7, "bold", WARM, "center", inner)
    ax.plot((4.3, 78.8), (15.3, 15.3), linewidth=.45, color=LINE, zorder=4)
    for y, label, original, changed in ((13.3, "r(C2–C4)", "2.029", "1.029"),
                                         (7.6, "r(O3–H8)", "1.248", "1.248")):
        text(ax, checks, 4.3, y, label, 8.1, box=inner)
        text(ax, checks, 49.3, y, original, 8.5, "bold", ha="center", box=inner)
        text(ax, checks, 69.3, y, changed, 8.5, "bold" if changed == "1.029" else "normal",
             WARM if changed == "1.029" else INK, "center", inner)
    arrow(ax, (56.2, 11.6), (62.8, 11.6), WARM)
    original = (87.8, 3.7, 25.6, 14.6)
    changed = (125.2, 3.7, 27.6, 14.6)
    stack(ax, original)
    rounded(ax, changed, PALE_WARM, WARM, 1.8, .8)
    ax.add_patch(Rectangle((125.2, 7.0), .75, 8.0, color=WARM, linewidth=0, zorder=3))
    for box, title, color in ((original, "Original", INK), (changed, "Changed", WARM)):
        x, y, w, h = box
        inner = content_box(box, 1.7)
        text(ax, checks, x + w / 2, y + h - 2.2, title, 8.3, "bold", color,
             "center", inner)
        text(ax, checks, x + w / 2, y + 6.2, r"$h_\ell(p53)$", 9.0,
             ha="center", box=inner, va="center")
    text(ax, checks, 119.2, 22.0, "state patch", 8.3, "bold", ha="center")
    arrow(ax, (115.0, 11.0), (123.5, 11.0))
    return finish(fig, ax, checks, "fact_intervention", width, height)


def evidence_links():
    width, height = 85, 67
    fig, ax, checks = canvas(width, height)
    text(ax, checks, 1.5, 65.4, "Evidence–geometry association", 9.3, "bold")
    optimization = (1.5, 40.5, 35.8, 18)
    frequency = (47.7, 40.5, 35.8, 18)
    irc = (16.8, 20.6, 51.4, 14.4)
    source = (1.5, 1.5, 36.4, 14)
    target = (47.1, 1.5, 36.4, 14)
    stack(ax, optimization)
    cut_card(ax, frequency, PALE_WARM, WARM, 1.9)
    rounded(ax, irc, SAGE, LINE, 1.5)
    ax.add_patch(Rectangle((16.8, 23.1), .85, 9.4, color=ACID, linewidth=0, zorder=3))
    stack(ax, source)
    stack(ax, target)

    for box, heading, lines, accent in (
        (optimization, "TS optimization", ["final geometry: g_63", "converged: true"], INK),
        (frequency, "TS frequency", ["geometry: g_63 → g_42", "1 imaginary:", "−299.6562 cm⁻¹"], WARM),
    ):
        x, y, w, h = box
        inner = content_box(box, 1.5)
        text(ax, checks, x + 2, y + h - 2.2, heading, 8.5, "bold", accent, box=inner)
        for index, line in enumerate(lines):
            text(ax, checks, x + 2, 52.3 - index * 3.4, line, 7.5,
                 color=accent if index == 0 and box == frequency else INK, box=inner)
    inner = content_box(irc, 1.5)
    text(ax, checks, 19.2, 32.7, "Bidirectional IRC", 8.5, "bold", box=inner)
    text(ax, checks, 19.2, 28.9, "start: g_63", 7.5, box=inner)
    text(ax, checks, 19.2, 25.5, "outer frames: g_29 / g_17", 7.5, box=inner)
    for box, heading, ids in ((source, "Source Opt/Freq", "g_29 → g_42"),
                              (target, "Target Opt/Freq", "g_17 → g_08")):
        x, y, w, h = box
        inner = content_box(box, 1.4)
        text(ax, checks, x + 2, 13.3, heading, 8.3, "bold", box=inner)
        text(ax, checks, x + 2, 9.6, ids, 7.5, box=inner)
        text(ax, checks, x + 2, 6.2, "0 imaginary frequencies", 7.5, box=inner)
    arrow(ax, (38.5, 47.4), (46.5, 47.4))
    text(ax, checks, 42.5, 54.5, "same\nTS", 7.5, ha="center",
         box=(37.8, 47.8, 9.4, 7.0))
    arrow(ax, (20.2, 39.2), (28.5, 35.9))
    arrow(ax, (30.8, 19.5), (20.2, 16.5))
    arrow(ax, (54.2, 19.5), (65.6, 16.5))
    return finish(fig, ax, checks, "evidence_links", width, height)


def completion_sequence():
    width, height = 170, 43
    fig, ax, checks = canvas(width, height)
    text(ax, checks, 1.5, 41.2, "Completion request and DAG response", 10.1, "bold")
    boxes = [(1.5 + i * 33.9, 5.0, 31.0, 28.5) for i in range(5)]
    stack(ax, boxes[0])
    rounded(ax, boxes[1], "white", WARM, 1.7, .8)
    x, y, w, h = boxes[1]
    ax.plot((x + 2, x + w - 2), (y + h - .8, y + h - .8), color=WARM, linewidth=1.2, zorder=4)
    cut_card(ax, boxes[2], PALE_WARM, WARM, 2.4)
    rounded(ax, boxes[3], SAGE, LINE, 2.0)
    x, y, w, h = boxes[3]
    ax.add_patch(Rectangle((x, y + 3), .85, h - 6, color=LINE, linewidth=0, zorder=3))
    rounded(ax, boxes[4], "white", INK, 2.2, .85)
    x, y, w, h = boxes[4]
    ax.add_patch(Rectangle((x + 1.7, y + h - 1.2), 8.0, .9, color=ACID, linewidth=0, zorder=3))
    headings = ["Structured\nreport", "Completion\nrequest", "DAG response", "Model receives\ngap", "Revised\nrequest"]
    lines = [
        ["complete: false", "unresolved", "evidence", "waived: []"],
        ["stop", "disposition:", '"complete"'],
        ["action:", '"continue_work"', "IRC proof still", "missing"],
        ["missing short_irc", "bind supporting", "evidence", "or declare partial"],
        ["stop", "disposition:", '"partial"'],
    ]
    for index, (box, heading, body) in enumerate(zip(boxes, headings, lines, strict=True)):
        x, y, w, h = box
        inner = content_box(box, 1.4)
        accent = WARM if index in (1, 2) else INK
        text(ax, checks, x + 2, 30.5, heading, 8.2, "bold", accent, box=inner)
        for row, value in enumerate(body):
            position = 22.0 - row * 3.7
            text(ax, checks, x + 2, position, value, 7.5,
                 "bold" if index == 4 and value == '"partial"' else "normal",
                 WARM if index == 3 and row == 0 else INK, box=inner)
    for left, right in zip(boxes[:-1], boxes[1:], strict=True):
        arrow(ax, (left[0] + left[2] + .35, 17.5), (right[0] - .35, 17.5), scale=5.3)
    return finish(fig, ax, checks, "completion_sequence", width, height)


def main():
    summaries = [fact_intervention(), evidence_links(), completion_sequence()]
    (HERE / "box_diagrams_manifest.json").write_text(json.dumps(summaries, indent=2) + "\n")
    for summary in summaries:
        print(summary)


if __name__ == "__main__":
    main()
