"""Create editable bilingual Word versions of the current introduction."""

import ast
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/Cloudra_论文当前稿/01_正文"
SVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
tree = ast.parse((ROOT / "paper/latex/build_introduction_sources.py").read_text())
CAPTIONS = next(
    ast.literal_eval(node.value)
    for node in tree.body
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CAPTIONS" for t in node.targets)
)
FIGURE_FILES = next(
    ast.literal_eval(node.value)
    for node in tree.body
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FIGURE_FILES" for t in node.targets)
)
FIGURES = {label: (n, path) for n, (label, path) in enumerate(FIGURE_FILES.items(), 1)}
REFERENCES = [
    "Zou, Y., et al. El Agente: An autonomous agent for quantum chemistry. Matter 2025, 8, 102263. https://doi.org/10.1016/j.matt.2025.102263",
    "Hu, J., et al. Aitomia: An Agentic Framework for AI-Driven Atomistic and Quantum Chemical Simulations. Journal of Chemical Theory and Computation 2026, 22, 6557–6571. https://doi.org/10.1021/acs.jctc.6c00591",
    "Pérez-Sánchez, J. B., et al. El Agente Quntur: A research collaborator agent for quantum chemistry. Chem 2026, 103259. https://doi.org/10.1016/j.chempr.2026.103259",
    "Choi, C., et al. El Agente Estructural: An Artificially Intelligent Molecular Editor. 2026. https://arxiv.org/abs/2602.04849",
    "Li, D., et al. Autonomous Chemical Mechanistic Discovery through Agentic Reasoning and Validation. 2026. https://arxiv.org/abs/2609.11147",
    "Bai, J., et al. El Agente Gráfico: A Semantic Execution Runtime for Scientific Agents. arXiv:2602.17902v2, 2026. https://arxiv.org/abs/2602.17902v2",
]


def fonts(style, size, *, bold=False, east_asia="Songti SC"):
    style.font.name = "Times New Roman"
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor(0, 0, 0)
    rpr = style.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    for key, value in (("ascii", "Times New Roman"), ("hAnsi", "Times New Roman"), ("eastAsia", east_asia)):
        rf.set(qn("w:" + key), value)
    for key in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme"):
        rf.attrib.pop(qn("w:" + key), None)


def field(paragraph, instruction, cached):
    element = OxmlElement("w:fldSimple")
    element.set(qn("w:instr"), instruction)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = str(cached)
    run.append(text)
    element.append(run)
    paragraph._p.append(element)


def bookmark(paragraph, name, number, content=None):
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(number))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(number))
    paragraph._p.append(start)
    if content:
        content()
    paragraph._p.append(end)


def add_text(paragraph, text):
    text = text.replace("Figures 2 and 3", "Figures [[FIG:2]] and [[FIG:3]]")
    for n in (1, 2, 3):
        text = text.replace(f"Figure {n}", f"Figure [[FIG:{n}]]").replace(f"图{n}", f"图[[FIG:{n}]]")
    position = 0
    buffer = []

    def flush():
        if buffer:
            paragraph.add_run("".join(buffer))
            buffer.clear()

    while position < len(text):
        if text.startswith("[[FIG:", position):
            end = text.index("]]", position)
            number = text[position + 6 : end]
            flush()
            field(paragraph, f" REF fig{number} \\h ", number)
            position = end + 2
            continue
        if text[position] == "[":
            end = text.find("]", position)
            numbers = text[position + 1 : end].split(",") if end >= 0 else []
            if numbers and all(n.strip() in {str(i) for i in range(1, len(REFERENCES) + 1)} for n in numbers):
                flush()
                run = paragraph.add_run(",".join(n.strip() for n in numbers))
                run.font.superscript = True
                position = end + 1
                continue
        buffer.append(text[position])
        position += 1
    flush()


def add_svg_picture(document, paragraph, filename, language):
    base = ROOT / "paper/figures" / f"{filename}_{language}"
    picture = paragraph.add_run().add_picture(str(base.with_suffix(".png")), width=Mm(84.6))
    partname = PackURI(f"/word/media/{base.name}.svg")
    part = Part(partname, "image/svg+xml", base.with_suffix(".svg").read_bytes(), document.part.package)
    rid = document.part.relate_to(part, RT.IMAGE)
    blip = picture._inline.xpath(".//a:blip")[0]
    extensions = OxmlElement("a:extLst")
    extension = OxmlElement("a:ext")
    extension.set("uri", "{96DAC541-7B7A-43D3-8B79-37D633B846F1}")
    svg = etree.Element(f"{{{SVG_NS}}}svgBlip", nsmap={"asvg": SVG_NS})
    svg.set(qn("r:embed"), rid)
    extension.append(svg)
    extensions.append(extension)
    blip.append(extensions)
    picture._inline.docPr.set(
        "descr", f"Figure {FIGURES[next(k for k, v in FIGURES.items() if v[1] == filename)][0]} - literature survey"
    )


def figure(document, label, language):
    number, filename = FIGURES[label]
    picture = document.add_paragraph()
    picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture.paragraph_format.first_line_indent = Mm(0)
    picture.paragraph_format.space_before = Pt(6)
    picture.paragraph_format.space_after = Pt(3)
    picture.paragraph_format.line_spacing = 1.0
    picture.paragraph_format.keep_with_next = True
    add_svg_picture(document, picture, filename, language)
    caption = document.add_paragraph(style="Caption")
    caption.add_run("Figure " if language == "en" else "图 ").bold = True
    bookmark(caption, f"fig{number}", 100 + number, lambda: field(caption, " SEQ Figure \\* ARABIC ", number))
    caption.add_run(": ").bold = True
    add_text(caption, CAPTIONS[language][label])


def create(language):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Inches(8.5)
    sec.page_height = Inches(11)
    sec.top_margin = Mm(12.7)
    sec.bottom_margin = Mm(16.8)
    sec.left_margin = Mm(19.3)
    sec.right_margin = Mm(19.3)
    sec.header_distance = Mm(5)
    sec.footer_distance = Mm(7)
    for name, size, bold in (
        ("Normal", 10, False),
        ("Title", 18, True),
        ("Heading 1", 11, True),
        ("Heading 2", 10, True),
        ("Caption", 8.5, False),
    ):
        fonts(
            doc.styles[name],
            size,
            bold=bold,
            east_asia="Heiti SC" if name in {"Title", "Heading 1", "Heading 2"} else "Songti SC",
        )
    normal = doc.styles["Normal"].paragraph_format
    normal.space_before = Pt(0)
    normal.space_after = Pt(0)
    normal.line_spacing = Pt(12)
    normal.first_line_indent = Mm(3.3)
    normal.widow_control = True
    doc.styles["Title"].paragraph_format.line_spacing = Pt(21)
    for border in doc.styles["Title"].element.xpath(".//w:pBdr"):
        border.getparent().remove(border)
    for name in ("Heading 1", "Heading 2"):
        p = doc.styles[name].paragraph_format
        p.space_before = Pt(7)
        p.space_after = Pt(4)
        p.keep_with_next = True
        p.first_line_indent = Mm(0)
    caption = doc.styles["Caption"].paragraph_format
    caption.first_line_indent = Mm(0)
    caption.line_spacing = Pt(10.5)
    caption.space_before = Pt(0)
    caption.space_after = Pt(7)
    caption.keep_together = True

    title = (
        "Cloudra: Geometric Reasoning and Scientific Evidence in Autonomous Mechanism Exploration"
        if language == "en"
        else "Cloudra：自主机理探索中的几何推理与科学证据"
    )
    p = doc.add_paragraph(title, style="Title")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(10)
    p.paragraph_format.first_line_indent = Mm(0)
    for text in (
        ("Introduction draft", "English version - 27 October 2026")
        if language == "en"
        else ("引言审阅稿", "中文版 - 2026年10月27日")
    ):
        p = doc.add_paragraph(text)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Mm(0)
        p.paragraph_format.space_after = Pt(5)
        for run in p.runs:
            run.font.size = Pt(10)
    body = doc.add_section(WD_SECTION_START.CONTINUOUS)
    cols = body._sectPr.find(qn("w:cols"))
    cols.set(qn("w:num"), "2")
    cols.set(qn("w:space"), "459")
    footer = body.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.first_line_indent = Mm(0)
    field(footer, " PAGE ", "1")

    source = ROOT / "paper/sections" / ("01_introduction.md" if language == "en" else "01_introduction_zh.md")
    first = True
    blocks = source.read_text().strip().split("\n\n")
    # Keep the explanatory paragraphs together; Word has no LaTeX-style float queue.
    materials_marker = "<!-- figure:molecular-tasks-1 -->"
    blocks.remove(materials_marker)
    blocks.insert(blocks.index("<!-- figure:molecular-tasks-2 -->"), materials_marker)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            doc.add_paragraph(block[3:], style="Heading 1")
            first = True
        elif block.startswith("### "):
            doc.add_paragraph(block[4:], style="Heading 2")
            first = True
        elif block.startswith("<!-- figure:"):
            label = block[12:-4].strip()
            figure(doc, label, language)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if first:
                p.paragraph_format.first_line_indent = Mm(0)
                p.paragraph_format.keep_together = True
            add_text(p, block)
            first = False
    doc.add_paragraph("References" if language == "en" else "参考文献", style="Heading 1")
    for n, text in enumerate(REFERENCES, 1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Mm(3.5)
        p.paragraph_format.first_line_indent = Mm(-3.5)
        p.paragraph_format.line_spacing = Pt(10.5)
        p.paragraph_format.space_after = Pt(5)
        bookmark(p, f"ref{n}", 1000 + n)
        run = p.add_run(f"({n}) {text}")
        run.font.size = Pt(8.5)
    doc.add_section(WD_SECTION_START.CONTINUOUS)
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    doc.settings.element.append(update)
    doc.core_properties.title = title
    doc.core_properties.author = ""
    doc.core_properties.subject = "Bilingual introduction with three single-column literature figures"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dest = OUTPUT / f"Cloudra_Introduction_{language.upper()}.docx"
    doc.save(dest)
    print(dest)


if __name__ == "__main__":
    for language in ("en", "zh"):
        create(language)
