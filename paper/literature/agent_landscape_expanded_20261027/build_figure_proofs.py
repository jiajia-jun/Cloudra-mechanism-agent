"""Place the original vector panels on blank A4 pages at native 86-mm width."""

import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation

ROOT = Path(__file__).resolve().parents[3]
FIGURES = ROOT / "paper/figures/agent_landscape_acid_20261027"
OUT = ROOT / "output/Cloudra_论文当前稿/03_图件"
MM = 72 / 25.4
A4 = (210 * MM, 297 * MM)

PAGES = (
    ("targets", "tasks"),
    (
        "matrix_extended_materials_surfaces_01",
        "matrix_extended_materials_surfaces_02",
        "matrix_extended_materials_surfaces_03",
    ),
    ("matrix_finite_molecules_complexes_01", "matrix_finite_molecules_complexes_02"),
    ("matrix_soft_biomolecular_01", "matrix_cross_domain_01"),
)


def build(language, manifest):
    entries = {entry["stem"]: entry for entry in manifest if entry["language"] == language}
    writer = PdfWriter()
    for stems in PAGES:
        page = writer.add_blank_page(width=A4[0], height=A4[1])
        top = 15.0
        for row_start in range(0, len(stems), 2):
            row = stems[row_start:row_start + 2]
            for column, stem in enumerate(row):
                source = PdfReader(FIGURES / f"{stem}_{language}.pdf").pages[0]
                x = (14 + column * 96) * MM
                y = A4[1] - top * MM - float(source.mediabox.height)
                page.merge_transformed_page(source, Transformation().translate(x, y))
            top += max(entries[stem]["height_mm"] for stem in row) + 12
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"Cloudra_Figures_{language.upper()}.pdf"
    with target.open("wb") as stream:
        writer.write(stream)
    print(f"{target}: {len(writer.pages)} A4 pages, {sum(map(len, PAGES))} vector panels")


if __name__ == "__main__":
    data = json.loads((FIGURES / "manifest.json").read_text())
    for language in ("en", "zh"):
        build(language, data)
