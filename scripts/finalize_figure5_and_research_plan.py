from copy import deepcopy
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches


DOCX = Path("/Users/cloudrayyy/Desktop/申报书_附件4_杨程驿_AI4S融合润色版.docx")
FIGURE = Path("/tmp/cloudra-application-review.ip4vOO/figure5_screening_loop.png")

RESEARCH_PLAN = (
    "拟采取的研究思路：本项目以轴手性反应为验证场景，围绕“机理假设提出—候选路径生成—"
    "过渡态搜索与路径核验—机理图交付—实验反馈”展开。首先由反应映射和结构工具提取反应中心与"
    "构象约束，形成可计算的候选路径；随后依托事件驱动运行环境自动推进本地或集群计算，并在异常"
    "诊断、路径取舍和证据冲突等关键节点引入智能体议会；最终以可追溯的计算材料和阶段门禁形成机理"
    "结论。项目将结合轴手性与阻转异构代表体系，对比El Agente等近邻体系，并通过分级任务、消融"
    "实验和科学不可行任务检验方法的准确性、稳定性与合理拒答能力。"
)


def font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size, index=1 if bold else 0)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded(draw, box, fill, outline):
    draw.rounded_rectangle(box, radius=24, fill=fill, outline=outline, width=4)


def make_figure() -> None:
    w, h = 2200, 1050
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.text((w // 2, 70), "从预测到验证的轴手性反应筛选闭环", font=font(54, True), fill="#17324D", anchor="ma")
    boxes = [
        (140, 255, 700, 695, "AI预测", "机理先验与过渡态特征\n小数据模型给出候选体系", "#EAF2FA", "#2F7DB8"),
        (820, 255, 1380, 695, "Cloudra自动筛选", "候选排序与自动计算\n路径核验与证据门禁", "#EAF7F2", "#239A76"),
        (1500, 255, 2060, 695, "实验验证", "关键底物与选择性测定\n实验结果反馈下一轮筛选", "#FFF3E2", "#DC8A1A"),
    ]
    for x1, y1, x2, y2, title, body, fill, color in boxes:
        rounded(d, (x1, y1, x2, y2), fill, color)
        d.text(((x1 + x2) // 2, y1 + 95), title, font=font(40, True), fill=color, anchor="mm")
        d.multiline_text(((x1 + x2) // 2, y1 + 265), body, font=font(28), fill="#263746", anchor="mm", align="center", spacing=18)
    for x in (730, 1410):
        d.line((x, 475, x + 60, 475), fill="#55758F", width=12)
        d.polygon([(x + 60, 475), (x + 34, 452), (x + 34, 498)], fill="#55758F")
    d.arc((420, 650, 1780, 1000), start=5, end=175, fill="#7A55A3", width=8)
    d.polygon([(430, 825), (465, 805), (460, 845)], fill="#7A55A3")
    d.text((1100, 920), "实验反馈持续更新候选空间、机理假设与筛选策略", font=font(28), fill="#6A468F", anchor="mm")
    im.save(FIGURE, dpi=(220, 220))


def copy_ppr(source, target) -> None:
    current = target._p.pPr
    if current is not None:
        target._p.remove(current)
    if source._p.pPr is not None:
        target._p.insert(0, deepcopy(source._p.pPr))


def set_rpr(run, source_rpr, remove_highlight=False) -> None:
    current = run._r.rPr
    if current is not None:
        run._r.remove(current)
    rpr = deepcopy(source_rpr)
    if remove_highlight:
        highlight = rpr.find(qn("w:highlight"))
        if highlight is not None:
            rpr.remove(highlight)
    run._r.insert(0, rpr)


def main() -> None:
    make_figure()
    doc = Document(DOCX)
    auto = next(p for p in doc.paragraphs if p.text.startswith("申请人拟进一步推动研究范式"))
    caption4 = next(p for p in doc.paragraphs if p.text.startswith("图4. 未发表合作研究"))
    caption4_index = next(i for i, p in enumerate(doc.paragraphs) if p.text.startswith("图4. 未发表合作研究"))
    picture4 = doc.paragraphs[caption4_index - 1]

    # Keep the unpublished-study paragraph, result panel, and Figure 4 caption together.
    caption4._p.addnext(auto._p)

    picture5 = doc.add_paragraph()
    copy_ppr(picture4, picture5)
    picture5.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture5.add_run().add_picture(str(FIGURE), width=Inches(7.25))

    caption5 = doc.add_paragraph()
    copy_ppr(caption4, caption5)
    caption5.alignment = caption4.alignment
    source_runs = [r for r in caption4.runs if r.text]
    r1 = caption5.add_run("图5. ")
    set_rpr(r1, source_runs[0]._r.rPr)
    r2 = caption5.add_run("“AI预测—自动筛选—实验验证”的闭环研究模式")
    set_rpr(r2, source_runs[-1]._r.rPr)

    auto._p.addnext(picture5._p)
    picture5._p.addnext(caption5._p)

    plan = next(p for p in doc.paragraphs if p.text.startswith("拟采取的研究思路："))
    source_rpr = plan.runs[0]._r.rPr
    for run in list(plan.runs):
        plan._p.remove(run._r)
    run = plan.add_run(RESEARCH_PLAN)
    set_rpr(run, source_rpr, remove_highlight=True)

    doc.save(DOCX)


if __name__ == "__main__":
    main()
