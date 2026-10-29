"""Build the unified bilingual Word manuscript, including the Results chapter.

Combines the Introduction, System Design and Methods, and Results and Discussion,
including nine figures, fifteen display equations and consolidated references.
The verified Results chapter is inserted by the shared integration script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/Cloudra_论文当前稿/01_正文"
WORD_MATH_XSL = Path("/Applications/Microsoft Word.app/Contents/Resources/mathml2omml.xsl")
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
COLUMN_MM = 84.6

# Import existing helpers
sys.path.insert(0, str(ROOT / "paper/word"))
import build_introduction_docx as intro_builder  # noqa: E402
import build_methods_docx as methods_builder  # noqa: E402

CONSOLIDATED_REFERENCES = {
    "en": [
        "Zou, Y., et al. El Agente: An autonomous agent for quantum chemistry. Matter 2025, 8, 102263. https://doi.org/10.1016/j.matt.2025.102263",
        "Hu, J., et al. Aitomia: An Agentic Framework for AI-Driven Atomistic and Quantum Chemical Simulations. Journal of Chemical Theory and Computation 2026, 22, 6557–6571. https://doi.org/10.1021/acs.jctc.6c00591",
        "Pérez-Sánchez, J. B., et al. El Agente Quntur: A research collaborator agent for quantum chemistry. Chem 2026, 103259. https://doi.org/10.1016/j.chempr.2026.103259",
        "Choi, C., et al. El Agente Estructural: An Artificially Intelligent Molecular Editor. 2026. https://arxiv.org/abs/2602.04849",
        "Li, D., et al. Autonomous Chemical Mechanistic Discovery through Agentic Reasoning and Validation. 2026. https://arxiv.org/abs/2609.11147",
        "Bai, J., et al. El Agente Gráfico: A Semantic Execution Runtime for Scientific Agents. arXiv:2602.17902v2, 2026. https://arxiv.org/abs/2602.17902v2",
        "Kabsch, W. A discussion of the solution for the best rotation to relate two sets of vectors. Acta Crystallographica Section A 1978, 34, 827–828. https://doi.org/10.1107/S0567739478001680",
        "Smidstrup, S.; Pedersen, A.; Stokbro, K.; Jónsson, H. Improved initial guess for minimum energy path calculations. The Journal of Chemical Physics 2014, 140, 214106. https://doi.org/10.1063/1.4878664",
        "Fukui, K. Formulation of the reaction coordinate. The Journal of Physical Chemistry 1970, 74, 4161–4163. https://doi.org/10.1021/j100717a029",
        "Maeda, S.; Harabuchi, Y.; Ono, Y.; Taketsugu, T.; Morokuma, K. Intrinsic reaction coordinate: Calculation, bifurcation, and automated search. International Journal of Quantum Chemistry 2015, 115, 258–269. https://doi.org/10.1002/qua.24757",
        "FACCTs. ORCA 6.1 Manual: Vibrational frequencies and Intrinsic reaction coordinate. https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/frequencies.html",
        "Riniker, S.; Landrum, G. A. Better Informed Distance Geometry: Using What We Know To Improve Conformation Generation. Journal of Chemical Information and Modeling 2015, 55, 2562–2574. https://doi.org/10.1021/acs.jcim.5b00654",
        "RDKit. Getting Started in Python: Conformer Generation and Maximum Common Substructure. https://www.rdkit.org/docs/GettingStartedInPython.html",
        "Cloudra source code. Revision 70daa5a. https://github.com/yyywaa/Cloudra-mechanism-agent/tree/70daa5a",
    ],
    "zh": [
        "Zou, Y., et al. El Agente: An autonomous agent for quantum chemistry. Matter 2025, 8, 102263. https://doi.org/10.1016/j.matt.2025.102263",
        "Hu, J., et al. Aitomia: An Agentic Framework for AI-Driven Atomistic and Quantum Chemical Simulations. Journal of Chemical Theory and Computation 2026, 22, 6557–6571. https://doi.org/10.1021/acs.jctc.6c00591",
        "Pérez-Sánchez, J. B., et al. El Agente Quntur: A research collaborator agent for quantum chemistry. Chem 2026, 103259. https://doi.org/10.1016/j.chempr.2026.103259",
        "Choi, C., et al. El Agente Estructural: An Artificially Intelligent Molecular Editor. 2026. https://arxiv.org/abs/2602.04849",
        "Li, D., et al. Autonomous Chemical Mechanistic Discovery through Agentic Reasoning and Validation. 2026. https://arxiv.org/abs/2609.11147",
        "Bai, J., et al. El Agente Gráfico: A Semantic Execution Runtime for Scientific Agents. arXiv:2602.17902v2, 2026. https://arxiv.org/abs/2602.17902v2",
        "Kabsch, W. A discussion of the solution for the best rotation to relate two sets of vectors. Acta Crystallographica Section A 1978, 34, 827–828. https://doi.org/10.1107/S0567739478001680",
        "Smidstrup, S.; Pedersen, A.; Stokbro, K.; Jónsson, H. Improved initial guess for minimum energy path calculations. The Journal of Chemical Physics 2014, 140, 214106. https://doi.org/10.1063/1.4878664",
        "Fukui, K. Formulation of the reaction coordinate. The Journal of Physical Chemistry 1970, 74, 4161–4163. https://doi.org/10.1021/j100717a029",
        "Maeda, S.; Harabuchi, Y.; Ono, Y.; Taketsugu, T.; Morokuma, K. Intrinsic reaction coordinate: Calculation, bifurcation, and automated search. International Journal of Quantum Chemistry 2015, 115, 258–269. https://doi.org/10.1002/qua.24757",
        "FACCTs. ORCA 6.1 Manual: Vibrational frequencies and Intrinsic reaction coordinate. https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/frequencies.html",
        "Riniker, S.; Landrum, G. A. Better Informed Distance Geometry: Using What We Know To Improve Conformation Generation. Journal of Chemical Information and Modeling 2015, 55, 2562–2574. https://doi.org/10.1021/acs.jcim.5b00654",
        "RDKit. Getting Started in Python: Conformer Generation and Maximum Common Substructure. https://www.rdkit.org/docs/GettingStartedInPython.html",
        "Cloudra 源代码仓库. 提交版本 70daa5a. https://github.com/yyywaa/Cloudra-mechanism-agent/tree/70daa5a",
    ],
}


def add_architecture_figure(doc, language: str):
    png_path = ROOT / "docs/assets/figure1_architecture_prototype.png"
    svg_path = ROOT / "docs/assets/figure1_architecture_prototype.svg"
    picture = doc.add_paragraph()
    picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture.paragraph_format.first_line_indent = Mm(0)
    picture.paragraph_format.space_before = Pt(6)
    picture.paragraph_format.space_after = Pt(3)
    picture.paragraph_format.line_spacing = 1.0
    picture.paragraph_format.keep_with_next = True

    run_pic = picture.add_run().add_picture(str(png_path), width=Mm(COLUMN_MM))
    if svg_path.exists():
        partname = PackURI("/word/media/figure_architecture.svg")
        part = Part(partname, "image/svg+xml", svg_path.read_bytes(), doc.part.package)
        rid = doc.part.relate_to(part, RT.IMAGE)
        blip = run_pic._inline.xpath(".//a:blip")[0]
        extensions = OxmlElement("a:extLst")
        extension = OxmlElement("a:ext")
        extension.set("uri", "{96DAC541-7B7A-43D3-8B79-37D633B846F1}")
        svg = etree.Element(f"{{{SVG_NS}}}svgBlip", nsmap={"asvg": SVG_NS})
        svg.set(qn("r:embed"), rid)
        extension.append(svg)
        extensions.append(extension)
        blip.append(extensions)

    caption = doc.add_paragraph(style="Caption")
    caption.add_run("Figure 4: " if language == "en" else "图 4: ").bold = True
    caption_text = (
        "Cloudra multi-agent system architecture: coupling mechanistic hypothesis generation (Coordinator), "
        "deterministic geometric manipulation (Operators), asynchronous computational execution (ComputeDB), "
        "and physical evidence validation gates."
        if language == "en"
        else "Cloudra 多智能体系统架构：机理假设推演（协调智能体）、确定性空间几何算子、"
        "异步计算调度账本（ComputeDB）以及物理证据校验门禁的协同闭环。"
    )
    caption.add_run(caption_text)


def create_combined_manuscript(language: str, converter: methods_builder.MathConverter):
    doc = Document()
    methods_builder.configure_document(doc)

    # Configure styles
    intro_builder.fonts(doc.styles["Caption"], 8.5, bold=False, east_asia="Songti SC")
    caption_fmt = doc.styles["Caption"].paragraph_format
    caption_fmt.first_line_indent = Mm(0)
    caption_fmt.line_spacing = Pt(10.5)
    caption_fmt.space_before = Pt(0)
    caption_fmt.space_after = Pt(7)
    caption_fmt.keep_together = True

    # Title & Subtitle
    title_text = (
        "Cloudra: Geometric Reasoning and Scientific Evidence in Autonomous Mechanism Exploration"
        if language == "en"
        else "Cloudra：自主机理探索中的几何推理与科学证据"
    )
    title_p = doc.add_paragraph(title_text, style="Title")
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_before = Pt(10)
    title_p.paragraph_format.space_after = Pt(10)
    title_p.paragraph_format.first_line_indent = Mm(0)

    subtitle_p = doc.add_paragraph(
        "Working Draft (Introduction & Methods) — 28 October 2026"
        if language == "en"
        else "工作审阅稿（引言与系统方法）— 2026年10月28日"
    )
    subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_p.paragraph_format.first_line_indent = Mm(0)
    subtitle_p.paragraph_format.space_after = Pt(12)
    for run in subtitle_p.runs:
        run.font.size = Pt(10)

    # ---------------- PART 1: INTRODUCTION ----------------
    intro_source = ROOT / "paper/sections" / ("01_introduction.md" if language == "en" else "01_introduction_zh.md")
    blocks = intro_source.read_text(encoding="utf-8").strip().split("\n\n")

    materials_marker = "<!-- figure:molecular-tasks-1 -->"
    if materials_marker in blocks:
        blocks.remove(materials_marker)
        blocks.insert(blocks.index("<!-- figure:molecular-tasks-2 -->"), materials_marker)

    first = True
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
            intro_builder.figure(doc, label, language)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if first:
                p.paragraph_format.first_line_indent = Mm(0)
                p.paragraph_format.keep_together = True
            intro_builder.add_text(p, block)
            first = False

    # ---------------- PART 2: METHODS ----------------
    methods_source = (
        ROOT
        / "paper/sections"
        / ("02_architecture_and_methods.md" if language == "en" else "02_architecture_and_methods_zh.md")
    )
    equation_count = 0
    first_methods = True
    arch_figure_added = False

    for kind, value in methods_builder.blocks(methods_source.read_text(encoding="utf-8")):
        if kind.startswith("heading"):
            if value in ("参考文献", "References"):
                continue  # Handled at the end
            if kind == "heading2":
                title_clean = value.replace("2. ", "2 ", 1)
                doc.add_paragraph(title_clean, style="Heading 1")
            elif kind == "heading4":
                doc.add_paragraph(value, style="Heading 2")
            else:
                doc.add_paragraph(value, style="Heading 2" if kind == "heading4" else "Heading 1")
            first_methods = True
        elif kind == "equation":
            equation_count += 1
            methods_builder.add_equation(doc, value, equation_count, converter)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if first_methods:
                p.paragraph_format.first_line_indent = Mm(0)
            methods_builder.add_inline(p, value, converter)
            first_methods = False

            # Embed Architecture figure right after the overview paragraph in 2.1
            if not arch_figure_added and (
                "Cloudra 将反应物结构" in value or "Cloudra takes reactant identities" in value
            ):
                add_architecture_figure(doc, language)
                arch_figure_added = True

    # ---------------- CONSOLIDATED REFERENCES ----------------
    doc.add_paragraph("References" if language == "en" else "参考文献", style="Heading 1")
    for n, text in enumerate(CONSOLIDATED_REFERENCES[language], 1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Mm(3.5)
        p.paragraph_format.first_line_indent = Mm(-3.5)
        p.paragraph_format.line_spacing = Pt(10.5)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(f"[{n}] {text}")
        run.font.size = Pt(8.5)

    if language == "zh":
        doc.add_section(WD_SECTION_START.CONTINUOUS)

    doc.core_properties.title = title_text
    doc.core_properties.author = "Cloudra Team"
    doc.core_properties.subject = "Cloudra Complete Manuscript: Introduction and Methods"
    doc.core_properties.language = "zh-CN" if language == "zh" else "en-US"

    dest = OUTPUT / f"Cloudra_Manuscript_{language.upper()}.docx"
    doc.save(dest)
    sys.path.insert(0, str(ROOT))
    from scripts.model_semantics.integrate_manuscript import integrate

    integrate(language)
    print(f"Successfully created: {dest}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("zh", "en", "both"), default="both")
    parser.add_argument("--math-dependencies", type=Path, default=Path("/private/tmp/cloudra-mathdeps"))
    parser.add_argument("--math-stylesheet", type=Path, default=WORD_MATH_XSL)
    args = parser.parse_args()

    converter = methods_builder.MathConverter(args.math_dependencies, args.math_stylesheet)
    for lang in ("zh", "en") if args.language == "both" else (args.language,):
        create_combined_manuscript(lang, converter)


if __name__ == "__main__":
    main()
