"""Build editable bilingual journal-style Word methods chapters.

Run with the Codex bundled Python runtime, for example::

    PYTHONPATH=/private/tmp/cloudra-mathdeps \
      /Users/cloudrayyy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
      paper/word/build_methods_docx.py

Dependencies: bundled python-docx and lxml, plus latex2mathml 3.81.1 made
available through PYTHONPATH (or --math-dependencies). Native OMML conversion
uses the user's installed Microsoft Word MathML stylesheet at
``/Applications/Microsoft Word.app/Contents/Resources/mathml2omml.xsl``;
the proprietary stylesheet is read in place and is not copied into the repo.
Only layout markup is changed: aligned formulas become native OMML equation
arrays with row breaks suitable for an 84.6 mm journal column. Equations remain
editable and are numbered (2.1) through (2.15); no equation images or tables.

Render with the documents skill's render_docx.py using the same bundled Python
and its bundled LibreOffice, with
FONTCONFIG_FILE=/private/tmp/cloudra-fontconfig/fonts.conf. Rendered previews
and QA PDFs belong in a temporary directory, not in the delivery folder.
"""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/Cloudra_论文当前稿/01_正文"
WORD_MATH_XSL = Path("/Applications/Microsoft Word.app/Contents/Resources/mathml2omml.xsl")
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
COLUMN_MM = 84.6


def fonts(style, size: float, *, bold: bool = False, east_asia: str = "Songti SC"):
    """Match the existing introduction typography without executing its builder."""
    style.font.name = "Times New Roman"
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor(0, 0, 0)
    rpr = style.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    for key, value in (("ascii", "Times New Roman"), ("hAnsi", "Times New Roman"),
                       ("eastAsia", east_asia)):
        rf.set(qn("w:" + key), value)
    for key in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme"):
        rf.attrib.pop(qn("w:" + key), None)


class MathConverter:
    def __init__(self, dependencies: Path, stylesheet: Path):
        if str(dependencies) not in sys.path:
            sys.path.insert(0, str(dependencies))
        from latex2mathml.converter import convert
        self.convert = convert
        self.transform = etree.XSLT(etree.parse(str(stylesheet)))

    def omml(self, latex: str, *, display: bool = False, size: float = 10):
        mathml = self.convert(latex, display="block" if display else "inline")
        tree = etree.fromstring(mathml.encode("utf-8"))
        for token in tree.iter("{http://www.w3.org/1998/Math/MathML}mo"):
            if token.text in {"sin", "cos", "max", "min", "det", "diag"}:
                token.set("mathvariant", "normal")
            if token.text == "⋀":
                # Word accepts the general n-ary operator, while LO's OMML
                # importer only implements a subset of n-ary characters.
                # An indexed upright glyph is the same editable conjunction.
                token.tag = "{http://www.w3.org/1998/Math/MathML}mi"
                token.set("mathvariant", "normal")
        result = self.transform(tree)
        root = deepcopy(result.getroot())
        if root.tag != qn("m:oMath"):
            candidates = root.findall(f".//{{{MATH_NS}}}oMath")
            if len(candidates) != 1:
                raise ValueError(f"Math conversion did not produce a single equation: {latex}")
            root = deepcopy(candidates[0])
        # Every native math run uses a mathematical font. Body text retains TNR.
        for run in root.iter(f"{{{MATH_NS}}}r"):
            rpr = run.find(f"{{{WORD_NS}}}rPr")
            if rpr is None:
                rpr = OxmlElement("w:rPr")
                run.insert(0, rpr)
            rf = OxmlElement("w:rFonts")
            for key in ("ascii", "hAnsi", "cs"):
                rf.set(qn("w:" + key), "Cambria Math")
            rpr.append(rf)
            sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), str(round(size * 2)))
            rpr.append(sz)
            color = OxmlElement("w:color")
            color.set(qn("w:val"), "000000")
            rpr.append(color)
        return root


def split_top_level(text: str, delimiter: str) -> list[str]:
    """Split layout tokens outside brace groups, retaining nested math intact."""
    result, start, depth, pos = [], 0, 0, 0
    while pos < len(text):
        if depth == 0 and text.startswith(delimiter, pos):
            result.append(text[start:pos])
            pos += len(delimiter)
            start = pos
            continue
        if text[pos] == "\\" and pos + 1 < len(text) and text[pos + 1] in "{}":
            pos += 2
            continue
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced braces in formula")
        pos += 1
    if depth:
        raise ValueError("Unbalanced braces in formula")
    result.append(text[start:])
    return result


def equation_lines(latex: str, number: int) -> list[str]:
    latex = latex.strip()
    for environment in ("aligned", "aligned*", "split"):
        begin, end = f"\\begin{{{environment}}}", f"\\end{{{environment}}}"
        if latex.startswith(begin) and latex.endswith(end):
            latex = latex[len(begin):-len(end)].strip()
            break
    lines = [part.replace("&", "").strip() for part in split_top_level(latex, "\\\\")]
    # These are typesetting breaks, not changes to formula content.
    if number == 1:
        pieces = split_top_level(lines[0], "+4\\Delta_H")
        if len(pieces) == 2:
            lines = [pieces[0].strip(), "+4\\Delta_H" + pieces[1].strip()]
    elif number == 2:
        pieces = split_top_level(lines[0], ",\\qquad\\mathbf{R}=")
        if len(pieces) == 2:
            lines = [pieces[0].strip() + ",", "\\mathbf{R}=" + pieces[1].strip()]
    elif number == 3:
        lines = [piece.strip() for line in lines for piece in split_top_level(line, "\\qquad")]
    elif number == 4:
        lines = [piece.strip() for line in lines for piece in split_top_level(line, "\\qquad")]
    elif number == 5:
        pieces = split_top_level(lines[0], ",\\quad y_s=")
        if len(pieces) == 2:
            lines = [pieces[0].strip() + ",", "y_s=" + pieces[1].strip()]
    elif number == 6:
        pieces = split_top_level(lines[0], "\\{0")
        if len(pieces) == 2:
            lines = [pieces[0].strip(), "\\{0" + pieces[1].strip()]
    elif number == 7:
        pieces = split_top_level(lines[0], ",\\quad\\mathbf{P}^{\\mathsf{T}}\\mathbf{R}=")
        if len(pieces) == 2:
            lines = [pieces[0].strip() + ",", "\\mathbf{P}^{\\mathsf{T}}\\mathbf{R}=" + pieces[1].strip()]
    elif number == 8:
        pieces = split_top_level(lines[0], ",\\qquad V_k=")
        if len(pieces) == 2:
            lines = [pieces[0].strip() + ",", "V_k=" + pieces[1].strip()]
    elif number == 9:
        pieces = split_top_level(lines[0], "\\wedge \\mathbf{1}[\\nexists")
        if len(pieces) == 2:
            lines = [pieces[0].strip(), "\\wedge \\mathbf{1}[\\nexists" + pieces[1].strip()]
    elif number == 10:
        pieces = split_top_level(lines[0], ",\\qquad\\mathbf{H}_{\\mathrm{mw}}")
        if len(pieces) == 2:
            lines = [pieces[0].strip() + ",", "\\mathbf{H}_{\\mathrm{mw}}" + pieces[1].strip()]
    elif number == 12:
        pieces = split_top_level(lines[0], ",\\qquad")
        if len(pieces) == 2:
            lines = [pieces[0].strip() + ",", pieces[1].strip()]
    elif number == 15:
        lines = [piece.strip() for line in lines for piece in split_top_level(line, "\\qquad")]
    return [" ".join(line.split()) for line in lines if line.strip()]


def add_inline(paragraph, text: str, converter: MathConverter):
    """Preserve source prose and insert each inline expression as native math."""
    pos = 0
    while pos < len(text):
        start = text.find("$", pos)
        if start < 0:
            paragraph.add_run(text[pos:])
            return
        paragraph.add_run(text[pos:start])
        end = text.find("$", start + 1)
        if end < 0:
            raise ValueError(f"Unclosed inline formula: {text[start:]}")
        paragraph._p.append(converter.omml(text[start + 1:end]))
        pos = end + 1


def add_equation(doc, latex: str, number: int, converter: MathConverter):
    paragraph = doc.add_paragraph(style="Equation")
    fmt = paragraph.paragraph_format
    fmt.tab_stops.add_tab_stop(Mm(COLUMN_MM / 2), WD_TAB_ALIGNMENT.CENTER)
    fmt.tab_stops.add_tab_stop(Mm(COLUMN_MM), WD_TAB_ALIGNMENT.RIGHT)
    paragraph.add_run("\t")
    lines = equation_lines(latex, number)
    math = OxmlElement("m:oMath")
    if len(lines) == 1:
        native = converter.omml(lines[0], display=True, size=9.5)
        for child in native:
            math.append(child)
    else:
        array = OxmlElement("m:eqArr")
        properties = OxmlElement("m:eqArrPr")
        justification = OxmlElement("m:baseJc")
        justification.set(qn("m:val"), "center")
        properties.append(justification)
        array.append(properties)
        for line in lines:
            row = OxmlElement("m:e")
            for child in converter.omml(line, display=True, size=9.5):
                row.append(child)
            array.append(row)
        math.append(array)
    paragraph._p.append(math)
    paragraph.add_run(f"\t(2.{number})")


def field(paragraph, instruction: str, cached: str):
    element = OxmlElement("w:fldSimple")
    element.set(qn("w:instr"), instruction)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = cached
    run.append(text)
    element.append(run)
    paragraph._p.append(element)


def configure_document(doc):
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin, section.bottom_margin = Mm(12.7), Mm(16.8)
    section.left_margin = section.right_margin = Mm(19.3)
    section.header_distance, section.footer_distance = Mm(5), Mm(7)
    columns = section._sectPr.find(qn("w:cols"))
    columns.set(qn("w:num"), "2")
    columns.set(qn("w:space"), "459")
    for name, size, bold in (("Normal", 10, False), ("Title", 12, True),
                             ("Heading 1", 11, True), ("Heading 2", 10, True)):
        fonts(doc.styles[name], size, bold=bold,
              east_asia="Heiti SC" if name != "Normal" else "Songti SC")
    normal = doc.styles["Normal"].paragraph_format
    normal.space_before = normal.space_after = Pt(0)
    normal.line_spacing, normal.line_spacing_rule = Pt(12), WD_LINE_SPACING.AT_LEAST
    normal.first_line_indent = Mm(3.3)
    normal.widow_control = True
    for name in ("Title", "Heading 1", "Heading 2"):
        fmt = doc.styles[name].paragraph_format
        fmt.first_line_indent = Mm(0)
        fmt.space_before, fmt.space_after = Pt(7), Pt(4)
        fmt.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
        fmt.line_spacing = Pt(14 if name == "Title" else 12)
        fmt.keep_with_next, fmt.keep_together = True, True
        for border in doc.styles[name].element.xpath(".//w:pBdr"):
            border.getparent().remove(border)
    equation = doc.styles.add_style("Equation", 1)
    fonts(equation, 10)
    fmt = equation.paragraph_format
    fmt.first_line_indent = Mm(0)
    fmt.line_spacing = 1.0
    fmt.space_before, fmt.space_after = Pt(5), Pt(5)
    fmt.keep_together, fmt.keep_with_next = True, False
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.first_line_indent = Mm(0)
    footer.paragraph_format.line_spacing = Pt(10)
    field(footer, " PAGE ", "1")
    doc.settings.element.append(OxmlElement("w:updateFields"))
    settings = doc.settings.element.find(qn("w:updateFields"))
    settings.set(qn("w:val"), "true")
    math_properties = doc.settings.element.find(qn("m:mathPr"))
    if math_properties is None:
        math_properties = OxmlElement("m:mathPr")
        doc.settings.element.append(math_properties)
    font = OxmlElement("m:mathFont")
    font.set(qn("m:val"), "Cambria Math")
    math_properties.append(font)


def blocks(source: str):
    """Yield Markdown headings, paragraphs and complete display equations."""
    paragraph, equation, in_equation = [], [], False
    for raw in source.splitlines():
        line = raw.strip()
        if line == "$$":
            if paragraph:
                yield "paragraph", " ".join(paragraph)
                paragraph = []
            if in_equation:
                yield "equation", "\n".join(equation)
                equation = []
            in_equation = not in_equation
        elif in_equation:
            equation.append(raw)
        elif not line:
            if paragraph:
                yield "paragraph", " ".join(paragraph)
                paragraph = []
        elif line.startswith("#"):
            if paragraph:
                yield "paragraph", " ".join(paragraph)
                paragraph = []
            prefix = len(line) - len(line.lstrip("#"))
            yield f"heading{prefix}", line[prefix:].strip()
        else:
            paragraph.append(line)
    if in_equation:
        raise ValueError("Unclosed display equation")
    if paragraph:
        yield "paragraph", " ".join(paragraph)


def create(source: Path, destination: Path, language: str, converter: MathConverter):
    doc = Document()
    configure_document(doc)
    first, references, equation_count = True, False, 0
    title = ""
    for kind, value in blocks(source.read_text(encoding="utf-8")):
        if kind.startswith("heading"):
            references = value in ("参考文献", "References")
            if kind == "heading2":
                title = value.replace("2. ", "2 ", 1)
                paragraph = doc.add_paragraph(title, style="Title")
                paragraph.paragraph_format.space_before = Pt(0)
            else:
                style = "Heading 2" if kind == "heading4" else "Heading 1"
                doc.add_paragraph(value, style=style)
            first = True
        elif kind == "equation":
            equation_count += 1
            add_equation(doc, value, equation_count, converter)
        else:
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if references:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                paragraph.paragraph_format.keep_together = True
                paragraph.paragraph_format.left_indent = Mm(3.5)
                paragraph.paragraph_format.first_line_indent = Mm(-3.5)
                paragraph.paragraph_format.line_spacing = Pt(10.5)
                paragraph.paragraph_format.space_after = Pt(5)
                add_inline(paragraph, value, converter)
                for run in paragraph.runs:
                    run.font.size = Pt(8.5)
            else:
                if first:
                    paragraph.paragraph_format.first_line_indent = Mm(0)
                add_inline(paragraph, value, converter)
            first = False
    if equation_count != 15:
        raise ValueError(f"Expected 15 numbered display formulas, got {equation_count}: {source}")
    # Balance the short Chinese references page. The English chapter fills its
    # final page; an empty closing section there adds a blank page in LO.
    if language == "zh":
        doc.add_section(WD_SECTION_START.CONTINUOUS)
    doc.core_properties.title = title
    doc.core_properties.author = ""
    doc.core_properties.subject = "Cloudra system design and methods"
    doc.core_properties.language = "zh-CN" if language == "zh" else "en-US"
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destination)
    print(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("zh", "en", "both"), default="both")
    parser.add_argument("--chinese-source", type=Path,
                        default=ROOT / "paper/sections/02_architecture_and_methods_zh.md")
    parser.add_argument("--english-source", type=Path,
                        default=ROOT / "paper/sections/02_architecture_and_methods.md")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--math-dependencies", type=Path, default=Path("/private/tmp/cloudra-mathdeps"))
    parser.add_argument("--math-stylesheet", type=Path, default=WORD_MATH_XSL)
    args = parser.parse_args()
    converter = MathConverter(args.math_dependencies, args.math_stylesheet)
    for language, source in (("zh", args.chinese_source), ("en", args.english_source)):
        if args.language in ("both", language):
            create(source, args.output_dir / f"Cloudra_Methods_{language.upper()}.docx", language, converter)


if __name__ == "__main__":
    main()
