from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

PATH = Path("/Users/cloudrayyy/Desktop/申报书_附件4_杨程驿_AI4S融合润色版.docx")


def copy_paragraph_format(source, target) -> None:
    target.style = source.style
    source_ppr = source._p.pPr
    target_ppr = target._p.get_or_add_pPr()
    for child in list(target_ppr):
        target_ppr.remove(child)
    if source_ppr is not None:
        for child in source_ppr:
            target_ppr.append(deepcopy(child))


def normalize_run(run) -> None:
    run.font.name = "Arial"
    run.font.size = Pt(12)
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn("w:ascii"), "Arial")
    fonts.set(qn("w:hAnsi"), "Arial")
    fonts.set(qn("w:eastAsia"), "宋体")


def normalize_caption_run(run) -> None:
    run.font.name = "Arial"
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn("w:ascii"), "Arial")
    fonts.set(qn("w:hAnsi"), "Arial")
    fonts.set(qn("w:eastAsia"), "宋体")
    rpr = run._element.get_or_add_rPr()
    for tag in ("w:sz", "w:szCs"):
        child = rpr.find(qn(tag))
        if child is not None:
            rpr.remove(child)


def main() -> None:
    doc = Document(PATH)
    source = next(p for p in doc.paragraphs if p.text.startswith("轴手性体系因其构象灵活"))
    prefixes = (
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
    matched = []
    for paragraph in doc.paragraphs:
        if paragraph.text.lstrip().startswith(prefixes):
            copy_paragraph_format(source, paragraph)
            for run in paragraph.runs:
                normalize_run(run)
            matched.append(paragraph.text[:24])

    if len(matched) != len(prefixes):
        raise RuntimeError(f"expected {len(prefixes)} AI4S body paragraphs, found {len(matched)}: {matched}")

    caption_source = next(p for p in doc.paragraphs if p.text.startswith("图1."))
    caption_prefixes = (
        "表1. Cloudra与近邻化学智能体",
        "图4. 未发表合作研究中的酸性界面模型",
        "图6. 从反应映射、过渡态初猜到路径验证",
        "图7. Cloudra形式化评测与消融设计",
    )
    captions = []
    for paragraph in doc.paragraphs:
        if paragraph.text.startswith(caption_prefixes):
            copy_paragraph_format(caption_source, paragraph)
            for run in paragraph.runs:
                normalize_caption_run(run)
            captions.append(paragraph.text[:24])
    if len(captions) != len(caption_prefixes):
        raise RuntimeError(f"expected {len(caption_prefixes)} captions, found {len(captions)}: {captions}")

    comparison = next(table for table in doc.tables if table.cell(0, 0).text.strip() == "比较维度")
    for row in comparison.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.name = "Arial"
                    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
                    fonts.set(qn("w:ascii"), "Arial")
                    fonts.set(qn("w:hAnsi"), "Arial")
                    fonts.set(qn("w:eastAsia"), "宋体")
    doc.save(PATH)


if __name__ == "__main__":
    main()
