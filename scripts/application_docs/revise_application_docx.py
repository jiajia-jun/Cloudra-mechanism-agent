from __future__ import annotations

import copy
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from PIL import Image, ImageDraw, ImageFont

OLD_TITLE = "基于智能代理的轴手性体系过渡态自动化搜索与催化模型研究"
NEW_TITLE = "基于化学智能体的轴手性反应过渡态自动搜索与机理解析研究"
NEW_EN_TITLE = (
    "Chemical-Agent-Based Automated Transition-State Search and Mechanistic "
    "Elucidation for Axially Chiral Reactions"
)


def iter_paragraphs(document: Document):
    yield from document.paragraphs
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs


def replace_paragraph(paragraph, text: str, *, bold: bool | None = None) -> None:
    rpr = None
    if paragraph.runs and paragraph.runs[0]._r.rPr is not None:
        rpr = copy.deepcopy(paragraph.runs[0]._r.rPr)
        for tag in ("w:highlight", "w:color"):
            for node in rpr.findall(qn(tag)):
                rpr.remove(node)
    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)
    run = paragraph.add_run(text)
    if rpr is not None:
        run._r.insert(0, rpr)
    if bold is not None:
        run.bold = bold
    return None


def set_cell_text(cell, text: str) -> None:
    paragraph = cell.paragraphs[0]
    replace_paragraph(paragraph, text)
    for extra in list(cell.paragraphs[1:]):
        cell._tc.remove(extra._p)


def insert_paragraph_after(paragraph, text: str = ""):
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    new_para = paragraph._parent.add_paragraph()
    new_para._p.getparent().remove(new_para._p)
    new_p.addnext(new_para._p)
    new_para._p.getparent().remove(new_p)
    replace_paragraph(new_para, text)
    return new_para


def font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size, index=1 if "PingFang" in path else 0)
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, width: int) -> list[str]:
    lines, current = [], ""
    for ch in text:
        trial = current + ch
        if draw.textbbox((0, 0), trial, font=fnt)[2] <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def make_route_diagram(path: Path) -> None:
    w, h = 2200, 740
    image = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(image)
    title_font = font(54, True)
    box_font = font(37, True)
    body_font = font(29)
    draw.text((w // 2, 50), "Cloudra 技术路线", font=title_font, fill="#111111", anchor="ma")

    boxes = [
        ("任务定义", "输入反应物、产物与候选通道\n明确交付目标和方法约束"),
        ("结构感知", "原子映射与构象采样\n生成可计算的三维结构"),
        ("路径搜索", "自动产生过渡态初猜\n优化、频率与双向 IRC 验证"),
        ("证据交付", "机理图绑定计算证据\n审计物种、路径与能垒"),
        ("应用验证", "轴手性反应竞争通道比较\n结合实验结果迭代评估"),
    ]
    x0, y0, bw, bh, gap = 75, 180, 360, 360, 65
    for i, (heading, body) in enumerate(boxes):
        x = x0 + i * (bw + gap)
        fill = "#EAF2F8" if i % 2 == 0 else "#F2F4F4"
        draw.rounded_rectangle((x, y0, x + bw, y0 + bh), radius=24, fill=fill, outline="#5D6D7E", width=4)
        draw.text((x + bw // 2, y0 + 60), heading, font=box_font, fill="#17202A", anchor="ma")
        lines = []
        for raw in body.split("\n"):
            lines.extend(wrap(draw, raw, body_font, bw - 64))
        line_h = 55
        start = y0 + 142
        for j, line in enumerate(lines):
            draw.text((x + bw // 2, start + j * line_h), line, font=body_font, fill="#283747", anchor="ma")
        if i < len(boxes) - 1:
            ax1, ax2, ay = x + bw + 10, x + bw + gap - 10, y0 + bh // 2
            draw.line((ax1, ay, ax2, ay), fill="#2E86C1", width=10)
            draw.polygon([(ax2, ay), (ax2 - 30, ay - 22), (ax2 - 30, ay + 22)], fill="#2E86C1")
    image.save(path, dpi=(220, 220))


def main(src: Path, out: Path, diagram: Path) -> None:
    doc = Document(src)

    for paragraph in iter_paragraphs(doc):
        if OLD_TITLE in paragraph.text:
            replace_paragraph(paragraph, paragraph.text.replace(OLD_TITLE, NEW_TITLE))

    info = doc.tables[3]
    set_cell_text(info.cell(14, 2), NEW_EN_TITLE)

    chinese_abstract = (
        "（限400字）：\n"
        "“逃离平面化”是改善小分子药物理化性质与成药性的重要策略，轴手性分子的精准构筑为拓展三维化学空间提供了独特路径。然而，传统试错研究效率低、资源消耗大，现有计算化学智能体又多停留于常规任务编排，尚难可靠完成复杂过渡态搜索与全反应路径验证。本项目拟以申请人开发的Cloudra为核心，采用事件驱动与“生成—验证”架构：利用化学感知工具和自动路径算法推进结构准备、过渡态定位、频率分析及双向IRC验证，以证据约束的机理图记录物种转化和计算结果，并通过分级评测与不可行任务检验系统的可靠性。在前期轴手性体系验证基础上，项目将面向轴手性反应构建可复现的自动机理解析流程，比较竞争路径与立体选择性来源，为人工智能辅助复杂有机反应设计提供方法基础。"
    )
    english_abstract = (
        "(Limit: 3000 characters):\n"
        "Increasing molecular three-dimensionality is an important strategy for improving the physicochemical and drug-like properties of small molecules, and the precise construction of axial chirality offers a distinctive route to expanded three-dimensional chemical space. Conventional trial-and-error studies, however, are costly and inefficient, while existing computational-chemistry agents mainly orchestrate routine calculations and remain unreliable for difficult transition-state searches and complete reaction-path validation. This project will advance Cloudra, a chemical research agent developed by the applicant, through an event-driven, generate-and-verify architecture. Chemical perception tools and automated path algorithms will coordinate structure preparation, transition-state localization, frequency analysis, and bidirectional intrinsic reaction coordinate validation. An evidence-constrained mechanism graph will connect species transformations to auditable computational records, and a graded benchmark containing scientifically infeasible tasks will test both performance and justified refusal. Building on preliminary validation in axially chiral systems, the project will establish a reproducible workflow for automated mechanistic elucidation of axially chiral reactions, compare competing pathways, and analyze the origins of stereoselectivity, thereby providing a rigorous methodological basis for AI-assisted design of complex organic reactions."
    )
    set_cell_text(info.cell(22, 1), chinese_abstract)
    set_cell_text(info.cell(23, 1), english_abstract)

    for paragraph in doc.paragraphs:
        if paragraph.text.strip() == "图3. AI预测场景应用":
            replace_paragraph(paragraph, "图4. AI预测场景应用")
        elif paragraph.text.startswith("（可写与喻院长合作的项目"):
            replace_paragraph(
                paragraph,
                "在系统研发方面，申请人已完成Cloudra事件驱动运行内核、计算任务调度、化学感知工具与证据约束机理图的主体实现，并建立覆盖不同难度及科学不可行任务的评测框架。现有原型能够将结构准备、过渡态搜索、频率判定、双向IRC验证与能垒整理串联为可追溯流程，并已在代表性有机反应及轴手性相关算例中完成端到端验证。这些工作为本项目进一步比较轴手性反应竞争通道、分析立体选择性来源提供了软件与方法基础。",
            )
        elif paragraph.text.startswith("申请人拟进一步推动研究范式由“AI预测”向“自动筛选”拓展"):
            replace_paragraph(
                paragraph,
                "申请人拟进一步推动研究范式由“AI预测”向“自动筛选”拓展。在导师指导下，申请人独立负责Cloudra的方法开发、性能评测与应用研究，结合过渡态信息和小数据建模，已初步建立数据驱动与机理约束相结合的N–N键轴手性生成反应筛选思路，并在罗维纬副教授团队开展实验验证，为形成“AI预测—自动筛选—实验验证”的研究闭环奠定基础。与通用量子化学工作流智能体相比，Cloudra聚焦均相有机反应机理解析，强调计算过程自动推进、关键结果确定性核验和全过程材料可复查；其分级评测还专门设置科学不可行任务，用于检验系统能否在方法不适用时给出有依据的停止判断。",
            )
        elif paragraph.text.startswith("轴手性体系因其构象灵活与立体化学敏感性"):
            replace_paragraph(
                paragraph,
                "轴手性体系构象灵活、立体化学敏感，过渡态搜索成本高且依赖初始结构质量；长程多步计算还容易因上下文漂移造成任务失序。针对这些问题，本项目拟从运行框架与化学方法两方面推进：利用专用工具识别反应中心和关键几何特征，通过构象采样与自动路径算法生成过渡态初猜；将过渡态优化、频率分析、双向IRC及端点核验组织为可恢复的计算流程，并由智能体依据结构化结果处理收敛异常；以证据约束的机理图稳定记录物种、基元步骤、能垒与计算材料。在轴手性反应应用中，项目将比较竞争路径及关键非共价相互作用，结合实验事实分析立体选择性来源，为催化体系的机理导向优化提供可复查依据。",
            )
        elif paragraph.text.startswith("拟采取的研究思路："):
            replace_paragraph(
                paragraph,
                "研究方法：（1）化学结构感知与候选路径生成。基于原子映射、构象采样和反应中心识别，生成轴手性反应的候选构型与竞争通道。（2）自动过渡态搜索与路径核验。利用路径插值和逐级量子化学计算获得过渡态初猜，依次完成过渡态优化、单一虚频判定、双向IRC及端点优化；异常结果由智能体依据结构化诊断信息调整计算。（3）证据约束的机理解析。将物种、基元步骤、计算日志和能垒绑定到机理图，以确定性规则核验路径连通性和证据完整性。（4）轴手性反应应用与评测。比较竞争路径的能垒及关键相互作用，结合实验结果分析选择性来源，并以分级任务、消融对照和不可行任务检验系统的准确性、稳健性与停止能力。",
                bold=False,
            )
            tech = insert_paragraph_after(
                paragraph,
                "技术路线：首先输入目标反应、候选产物与计算约束，完成原子映射、三维结构生成和构象筛选；随后针对可能的成键、断键及构象转化建立候选通道，自动推进过渡态初猜、优化、频率与双向IRC计算；经端点结构匹配后，将可靠路径及热力学、动力学数据写入机理图；最后在轴手性反应中比较竞争通道，结合实验结果复核并迭代模型与工具。整体路线形成“任务定义—结构感知—路径搜索—证据交付—应用验证”的闭环（图6）。",
            )
            make_route_diagram(diagram)
            fig = insert_paragraph_after(tech)
            fig.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = fig.add_run()
            run.add_picture(str(diagram), width=Inches(6.25))
            caption = insert_paragraph_after(fig, "图6. Cloudra自动过渡态搜索与机理解析技术路线")
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in caption.runs:
                run.font.size = Pt(9)

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: revise_application_docx.py SOURCE OUTPUT DIAGRAM")
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
