from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


PATH = Path("/Users/cloudrayyy/Desktop/申报书_附件4_杨程驿_AI4S融合润色版.docx")


BODY_PREFIXES = (
    "在El Agente与ARCHE等近邻工作",
    "围绕这一原则，Cloudra形成",
    "申请人前期围绕轴手性化合物",
    "申请人还参与了喻林萍院长团队",
    "申请人拟进一步推动研究范式",
    "研究方法：",
    "技术路线：",
    "形式化评测：",
    "真实场景验证：",
    "（2）在罗维纬副教授、喻林萍院长",
)

CAPTION_PREFIXES = (
    "表1. Cloudra与近邻化学智能体",
    "图4. 未发表合作研究中的酸性界面模型",
    "图6. 从反应映射、过渡态初猜到路径验证",
    "图7. Cloudra形式化评测与消融设计",
)


def replace_run_properties(run, source_rpr) -> None:
    current = run._r.rPr
    if current is not None:
        run._r.remove(current)
    run._r.insert(0, deepcopy(source_rpr))


def copy_font_metadata(run, source_rpr) -> None:
    target = run._element.get_or_add_rPr()
    for tag in ("w:rFonts", "w:lang"):
        old = target.find(qn(tag))
        if old is not None:
            target.remove(old)
        source = source_rpr.find(qn(tag))
        if source is not None:
            target.insert(0, deepcopy(source))


def main() -> None:
    doc = Document(PATH)
    body_source = next(p for p in doc.paragraphs if p.text.startswith("轴手性体系因其构象灵活"))
    caption_source = next(p for p in doc.paragraphs if p.text.startswith("图1."))
    body_rpr = body_source.runs[0]._r.rPr
    caption_rpr = caption_source.runs[0]._r.rPr

    body_count = caption_count = 0
    for paragraph in doc.paragraphs:
        text = paragraph.text.lstrip()
        if text.startswith(BODY_PREFIXES):
            for run in paragraph.runs:
                replace_run_properties(run, body_rpr)
            body_count += 1
        elif paragraph.text.startswith(CAPTION_PREFIXES):
            for run in paragraph.runs:
                replace_run_properties(run, caption_rpr)
            caption_count += 1

    comparison = next(table for table in doc.tables if table.cell(0, 0).text.strip() == "比较维度")
    table_runs = 0
    for row in comparison.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    copy_font_metadata(run, body_rpr)
                    table_runs += 1

    if body_count != len(BODY_PREFIXES) or caption_count != len(CAPTION_PREFIXES) or table_runs < 32:
        raise RuntimeError(
            f"unexpected coverage: body={body_count}, captions={caption_count}, table_runs={table_runs}"
        )
    doc.save(PATH)


if __name__ == "__main__":
    main()
