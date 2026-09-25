from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt


def copy_paragraph_format(source, target) -> None:
    target.style = source.style
    target.alignment = source.alignment
    target.paragraph_format._element.get_or_add_pPr()
    source_ppr = source._p.pPr
    target_ppr = target._p.pPr
    for child in list(target_ppr):
        target_ppr.remove(child)
    if source_ppr is not None:
        for child in source_ppr:
            target_ppr.append(deepcopy(child))


def main(path: Path) -> None:
    doc = Document(path)
    chinese = doc.tables[3].cell(22, 1)
    english = doc.tables[3].cell(23, 1)

    # Match the English abstract body to the paragraph immediately above it.
    copy_paragraph_format(chinese.paragraphs[1], english.paragraphs[1])
    for run in english.paragraphs[1].runs:
        run.font.name = "Times New Roman"
        run.font.size = Pt(10.5)
        run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Times New Roman")
        run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Times New Roman")

    doc.save(path)


if __name__ == "__main__":
    main(Path("/Users/cloudrayyy/Desktop/申报书_附件4_杨程驿_AI4S融合润色版.docx"))
