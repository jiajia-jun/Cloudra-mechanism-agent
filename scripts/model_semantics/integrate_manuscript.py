"""Insert the verified Results chapter into the existing bilingual manuscript."""

from __future__ import annotations

import argparse
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from shutil import copy2

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/Cloudra_论文当前稿/01_正文"


def installed_fonts(doc) -> None:
    """Use standard publication fonts: Times New Roman / Songti SC for text, Cambria Math for math."""
    replacements = {
        "ＭＳ 明朝": "Songti SC",
        "MS Mincho": "Songti SC", "ＭＳ ゴシック": "Heiti SC",
        "MS Gothic": "Heiti SC", "Courier": "Courier New",
        "Cambria": "Times New Roman", "Calibri": "Times New Roman",
    }
    for part in doc.part.package.parts:
        if not str(part.partname).endswith(".xml"):
            continue
        root = part._element if hasattr(part, "_element") else etree.fromstring(part.blob)
        for element in root.iter():
            for key, value in list(element.attrib.items()):
                if value in replacements:
                    element.set(key, replacements[value])
        if str(part.partname).endswith("/fontTable.xml"):
            seen = set()
            for font in list(root):
                name = font.get(qn("w:name"))
                if name in seen:
                    root.remove(font)
                seen.add(name)
        if not hasattr(part, "_element"):
            part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    # Ensure all math runs retain Cambria Math font
    for fonts in doc.element.xpath(".//m:r/w:rPr/w:rFonts"):
        for attribute in list(fonts.attrib):
            if attribute.endswith("Theme"):
                del fonts.attrib[attribute]
        for name in ("ascii", "hAnsi", "cs"):
            fonts.set(qn(f"w:{name}"), "Cambria Math")
        if qn("w:eastAsia") in fonts.attrib:
            del fonts.attrib[qn("w:eastAsia")]


def journal_columns(doc) -> None:
    """Keep prose in two columns and span only wide figures."""
    for paragraph in list(doc.paragraphs):
        if paragraph._p.xpath("./w:pPr/w:sectPr"):
            paragraph._p.getparent().remove(paragraph._p)
    settings = doc.element.body.sectPr
    settings.find(qn("w:cols")).set(qn("w:num"), "2")
    doc.sections[-1].start_type = WD_SECTION_START.CONTINUOUS

    def boundary(anchor, columns: int, after: bool = False) -> None:
        paragraph = OxmlElement("w:p")
        properties = OxmlElement("w:pPr")
        section = deepcopy(settings)
        section.find(qn("w:cols")).set(qn("w:num"), str(columns))
        properties.append(section)
        paragraph.append(properties)
        if after:
            anchor.addnext(paragraph)
        else:
            anchor.addprevious(paragraph)

    svg = (ROOT / "docs/assets/figure1_architecture_prototype.svg").read_bytes()
    for shape in doc.inline_shapes:
        architecture = False
        for blip in shape._inline.iter("{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip"):
            part = doc.part.related_parts[blip.get(qn("r:embed"))]
            if str(part.partname).endswith("/figure_architecture.svg"):
                part._blob = svg
                architecture = True
        if architecture:
            height = round(shape.height * Mm(170) / shape.width)
            shape.width, shape.height = Mm(170), height
    paragraphs = list(doc.paragraphs)
    first_heading = next(p for p in paragraphs if p.style.name == "Heading 1")
    boundary(first_heading._p, 1)
    for i, paragraph in enumerate(paragraphs):
        drawings = paragraph._p.xpath(".//wp:extent")
        if drawings and any(int(p.get("cx")) >= Mm(150) for p in drawings):
            caption = paragraphs[i + 1]
            boundary(paragraph._p, 2)
            boundary(caption._p, 1, after=True)


def global_methods_citations(text: str) -> str:
    """Map the methods' seven local references into the shared bibliography."""
    result, position = [], 0
    while position < len(text):
        start = text.find("[", position)
        end = text.find("]", start + 1) if start >= 0 else -1
        if start < 0 or end < 0:
            result.append(text[position:])
            break
        result.append(text[position:start])
        numbers = text[start + 1:end].split(",")
        if all(n.strip() in {str(i) for i in range(1, 8)} for n in numbers):
            result.append("[" + ",".join(str(int(n.strip()) + 6) for n in numbers) + "]")
        else:
            result.append(text[start:end + 1])
        position = end + 1
    return "".join(result)


def integrate(language: str, destination: Path | None = None) -> Path:
    destination = destination or (OUTPUT / f"Cloudra_Manuscript_{language.upper()}.docx")
    chapter = Document(OUTPUT / f"Cloudra_Results_and_Discussion_{language.upper()}.docx")
    source_template = OUTPUT / f"Cloudra_Manuscript_{language.upper()}.docx"
    doc = Document(source_template)
    backup = OUTPUT.parent / "archive/20261029_before_chapter3" / destination.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists() and destination.exists():
        copy2(destination, backup)
    paragraphs = list(doc.paragraphs)
    reference_index = next(i for i, p in enumerate(paragraphs)
                           if p.text in {"References", "参考文献"})
    references = [deepcopy(p._p) for p in paragraphs[reference_index + 1:]
                  if any(p.text.startswith(f"[{n}] ") for n in range(1, 15))]
    if len(references) != 14:
        raise ValueError("Expected fourteen existing manuscript references")
    for p in paragraphs[:reference_index]:
        if p.text.startswith(("Working Draft", "工作审阅稿")):
            p.text = ("Working Draft — 29 October 2026" if language == "en"
                      else "工作审阅稿 — 2026年10月29日")
    # Remove the old bibliography as one range.
    body = doc.element.body
    first_removed = paragraphs[reference_index]._p
    for element in list(body)[list(body).index(first_removed):]:
        if element.tag != qn("w:sectPr"):
            body.remove(element)
    heading = doc.styles["Heading 3"]
    heading.base_style = doc.styles["Heading 2"]
    properties = heading.element.get_or_add_rPr()
    existing_fonts = properties.find(qn("w:rFonts"))
    if existing_fonts is not None:
        properties.remove(existing_fonts)
    properties.insert(0, deepcopy(doc.styles["Heading 2"].element.rPr.rFonts))
    heading.font.size, heading.font.bold = Pt(10), True
    heading.font.color.rgb = RGBColor(0, 0, 0)
    next_id = max((int(n.get("id")) for n in doc.element.xpath(".//wp:docPr")), default=0) + 1
    new_references = []
    in_references = False
    for paragraph in chapter.paragraphs:
        if paragraph.text in {"本节参考文献", "References for this section"}:
            in_references = True
            continue
        element = deepcopy(paragraph._p)
        if in_references:
            new_references.append(element)
            continue
        for blip in element.xpath(".//a:blip"):
            old_id = blip.get(qn("r:embed"))
            blob = chapter.part.related_parts[old_id].blob
            relationship, _ = doc.part.get_or_add_image(BytesIO(blob))
            blip.set(qn("r:embed"), relationship)
        for properties in element.xpath(".//wp:docPr"):
            properties.set("id", str(next_id))
            next_id += 1
        body.insert_element_before(element, "w:sectPr")
        if paragraph.text.startswith("3 "):
            doc.paragraphs[-1].style = doc.styles["Heading 1"]
        elif paragraph.text.startswith("3."):
            number = paragraph.text.split(" ", 1)[0]
            level = min(number.count(".") + 1, 3)
            doc.paragraphs[-1].style = doc.styles[f"Heading {level}"]
    if len(new_references) != 4:
        raise ValueError("Expected four chapter references")
    doc.add_paragraph("References" if language == "en" else "参考文献", style="Heading 1")
    for element in references + new_references:
        body.insert_element_before(element, "w:sectPr")
    bibliography = False
    for paragraph in doc.paragraphs:
        if paragraph.text in {"References", "参考文献"}:
            bibliography = True
        elif bibliography:
            paragraph.paragraph_format.keep_together = True
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
            for run in paragraph.runs:
                run.font.size = Pt(8)
    journal_columns(doc)
    installed_fonts(doc)

    # Update Figure 1 (targets) image blobs
    png_path_1 = ROOT / f"paper/figures/agent_landscape_acid_20261027/targets_{language}.png"
    svg_path_1 = ROOT / f"paper/figures/agent_landscape_acid_20261027/targets_{language}.svg"
    if png_path_1.exists() and svg_path_1.exists():
        png_data_1 = png_path_1.read_bytes()
        svg_data_1 = svg_path_1.read_bytes()
        for rel_id, part in doc.part.related_parts.items():
            if "image1.png" in str(part.partname):
                part._blob = png_data_1
            elif f"targets_{language}.svg" in str(part.partname):
                part._blob = svg_data_1

    # Update Figure 3 (matrix_finite_molecules_complexes_02) with Cloudra row
    png_path_3 = ROOT / f"paper/figures/agent_landscape_acid_20261027/matrix_finite_molecules_complexes_02_{language}.png"
    svg_path_3 = ROOT / f"paper/figures/agent_landscape_acid_20261027/matrix_finite_molecules_complexes_02_{language}.svg"
    if png_path_3.exists() and svg_path_3.exists():
        png_data_3 = png_path_3.read_bytes()
        svg_data_3 = svg_path_3.read_bytes()
        for rel_id, part in doc.part.related_parts.items():
            if "image3.png" in str(part.partname):
                part._blob = png_data_3
            elif f"matrix_finite_molecules_complexes_02_{language}.svg" in str(part.partname):
                part._blob = svg_data_3

    # Adjust inline shape heights for updated aspect ratios
    from PIL import Image
    for shape in doc.inline_shapes:
        for blip in shape._inline.xpath(".//a:blip"):
            rel_id = blip.get(qn("r:embed"))
            part = doc.part.related_parts.get(rel_id)
            if part:
                if "image1.png" in str(part.partname) and png_path_1.exists():
                    im = Image.open(png_path_1)
                    shape.height = round(shape.width * im.size[1] / im.size[0])
                elif "image3.png" in str(part.partname) and png_path_3.exists():
                    im = Image.open(png_path_3)
                    shape.height = round(shape.width * im.size[1] / im.size[0])

    doc.core_properties.subject = "Cloudra Manuscript: Introduction, Methods, Results and Discussion"
    doc.save(destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("zh", "en", "both"), default="both")
    args = parser.parse_args()
    for language in (("zh", "en") if args.language == "both" else (args.language,)):
        print(integrate(language))


if __name__ == "__main__":
    main()
