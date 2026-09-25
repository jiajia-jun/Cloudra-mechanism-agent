from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt


PATH = Path("/Users/cloudrayyy/Desktop/申报书_附件4_杨程驿_AI4S融合润色版.docx")


def set_fonts(run, *, size=None) -> None:
    run.font.name = "Times New Roman"
    if size is not None:
        run.font.size = Pt(size)
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn("w:ascii"), "Times New Roman")
    fonts.set(qn("w:hAnsi"), "Times New Roman")
    fonts.set(qn("w:eastAsia"), "宋体")


def main() -> None:
    doc = Document(PATH)
    start = next(i for i, p in enumerate(doc.paragraphs) if p.text.startswith("一、研究初衷"))
    end = next(i for i, p in enumerate(doc.paragraphs) if p.text.startswith("四、申请人简历"))

    body_count = 0
    caption_count = 0
    for i, paragraph in enumerate(doc.paragraphs):
        text = paragraph.text.strip()
        if not text or not (start < i < end):
            continue
        if text.startswith(("二、前期工作", "三、研究内容")):
            continue
        if text.startswith(("图", "表")):
            for run in paragraph.runs:
                set_fonts(run)
            caption_count += 1
            continue
        for run in paragraph.runs:
            set_fonts(run, size=12)
        body_count += 1

    comparison = next(table for table in doc.tables if table.cell(0, 0).text.strip() == "比较维度")
    table_run_count = 0
    for row in comparison.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    set_fonts(run)
                    table_run_count += 1

    if body_count < 15 or caption_count < 7 or table_run_count < 32:
        raise RuntimeError(
            f"unexpected coverage: body={body_count}, captions={caption_count}, table_runs={table_run_count}"
        )
    doc.save(PATH)


if __name__ == "__main__":
    main()
