from __future__ import annotations

import copy
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont


OLD_TITLE = "基于智能代理的轴手性体系过渡态自动化搜索与催化模型研究"
NEW_TITLE = "基于化学智能体的轴手性反应过渡态自动搜索与机理解析研究"
NEW_EN_TITLE = "Chemical-Agent-Based Automated Transition-State Search and Mechanistic Elucidation for Axially Chiral Reactions"


def font(size: int, bold: bool = False):
    paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ]
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size, index=1 if bold and "PingFang" in path else 0)
    return ImageFont.load_default()


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
    run.font.name = "Arial"
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "PingFang SC")
    if bold is not None:
        run.bold = bold


def set_cell_text(cell, text: str) -> None:
    replace_paragraph(cell.paragraphs[0], text)
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


def add_picture_after(paragraph, path: Path, width: float, caption: str):
    p = insert_paragraph_after(paragraph)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(width))
    cap = insert_paragraph_after(p, caption)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in cap.runs:
        run.font.size = Pt(9)
    return cap


def replace_picture(paragraph, path: Path, width: float) -> None:
    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(path), width=Inches(width))


def draw_centered(draw, box, text, fnt, fill="#17202A", spacing=8):
    x1, y1, x2, y2 = box
    lines = text.split("\n")
    heights = [draw.textbbox((0, 0), line, font=fnt)[3] for line in lines]
    total = sum(heights) + spacing * (len(lines) - 1)
    y = (y1 + y2 - total) / 2
    for line, h in zip(lines, heights):
        draw.text(((x1 + x2) / 2, y), line, font=fnt, fill=fill, anchor="ma")
        y += h + spacing


def arrow(draw, x1, y1, x2, y2, color="#2878B5", width=10):
    draw.line((x1, y1, x2, y2), fill=color, width=width)
    draw.polygon([(x2, y2), (x2 - 28, y2 - 18), (x2 - 28, y2 + 18)], fill=color)


def make_runtime_figure(path: Path) -> None:
    w, h = 2400, 1180
    im = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(im)
    d.text((w // 2, 55), "Cloudra：重新划分智能与自动化的边界", font=font(60, True), fill="#102A43", anchor="ma")
    layers = [
        (145, 245, 2255, 440, "科学决策层  智能体议会", "提出竞争机理假设｜选择探索方向｜诊断异常｜处理证据冲突｜决定继续或停止", "#E8F1FB", "#2878B5"),
        (145, 490, 2255, 710, "化学工具与确定性自动化层", "反应映射｜过渡态初猜与校验｜过渡态优化及路径验证｜构象与电子结构工具｜日志解析", "#EAF6F2", "#259B79"),
        (145, 760, 2255, 965, "事件驱动运行环境与计算资源层", "长任务调度｜高性能计算集群与本地资源适配｜失败恢复｜事件唤醒｜上下文连续性｜权限与安全门禁", "#FFF3DF", "#E69528"),
    ]
    for x1,y1,x2,y2,title,body,fill,edge in layers:
        d.rounded_rectangle((x1,y1,x2,y2), radius=28, fill=fill, outline=edge, width=5)
        d.text((x1+45,y1+38),title,font=font(43,True),fill=edge)
        d.text((x1+45,y1+112),body,font=font(31),fill="#263746")
    d.rounded_rectangle((760, 1010, 1640, 1130), radius=22, fill="#F3E9FF", outline="#7653A6", width=4)
    draw_centered(d,(760,1010,1640,1130),"交付证据图：让结论可审计、可证伪",font(35,True),"#573A7C")
    d.text((70, 350), "需要智能", font=font(34,True), fill="#2878B5", anchor="mm")
    d.text((70, 605), "外包机械工作", font=font(30,True), fill="#259B79", anchor="mm")
    d.text((70, 860), "托管长周期计算", font=font(30,True), fill="#E69528", anchor="mm")
    im.save(path, dpi=(220,220))


def make_toolchain_figure(path: Path) -> None:
    w, h = 2400, 940
    im=Image.new("RGB",(w,h),"white"); d=ImageDraw.Draw(im)
    d.text((w//2,48),"从反应定义到可核验机理的化学工具链",font=font(58,True),fill="#102A43",anchor="ma")
    items=[
        ("反应映射","原子对应与反应中心\n成键/断键及竞争通道"),
        ("初猜与校验","路径插值与初猜生成\n几何校验、参考构型比较"),
        ("路径验证","过渡态优化 → 单虚频\n双向反应路径 → 端点确认"),
        ("化学分析工具","构象、轨道、电荷、键级\n日志与轨迹结构化解析"),
        ("交付证据图","物种与路径绑定证据\n能垒、性质与缺口审计"),
    ]
    x0,y0,bw,bh,gap=70,205,390,430,70
    for i,(head,body) in enumerate(items):
        x=x0+i*(bw+gap); fill="#EAF2F8" if i<3 else ("#EAF6F2" if i==3 else "#F3E9FF")
        edge="#2878B5" if i<3 else ("#259B79" if i==3 else "#7653A6")
        d.rounded_rectangle((x,y0,x+bw,y0+bh),radius=25,fill=fill,outline=edge,width=5)
        d.text((x+bw/2,y0+72),head,font=font(39,True),fill=edge,anchor="ma")
        draw_centered(d,(x+28,y0+135,x+bw-28,y0+365),body,font(29),"#263746",12)
        if i<len(items)-1: arrow(d,x+bw+10,y0+bh/2,x+bw+gap-10,y0+bh/2)
    d.rounded_rectangle((420,715,1980,860),radius=24,fill="#FFF3DF",outline="#E69528",width=4)
    draw_centered(d,(420,715,1980,860),"智能体只在假设选择、异常诊断、证据冲突和方法边界处介入",font(34,True),"#9A5A12")
    im.save(path,dpi=(220,220))


def make_benchmark_figure(path: Path) -> None:
    w,h=2400,950
    im=Image.new("RGB",(w,h),"white"); d=ImageDraw.Draw(im)
    d.text((w//2,52),"形式化评测：不仅看答案，还审计科学过程",font=font(58,True),fill="#102A43",anchor="ma")
    cols=[
        ("交付诚信","计算材料是否真实存在\n声明与日志是否一致"),
        ("路径自洽","过渡态、频率、双向反应路径与端点\n是否形成闭合证据链"),
        ("结果准确","机理图覆盖、能垒误差\n性质与选择性判断"),
        ("效率稳健","计算成本、异常恢复\n长任务连续性"),
        ("科学拒答","面对科学不可行任务时\n能否有依据地停止"),
    ]
    x0,y0,bw,bh,gap=70,205,390,380,70
    colors=[("#E8F1FB","#2878B5"),("#EAF6F2","#259B79"),("#F3E9FF","#7653A6"),("#FFF3DF","#E69528"),("#FDECEC","#C64B4B")]
    for i,((head,body),(fill,edge)) in enumerate(zip(cols,colors)):
        x=x0+i*(bw+gap); d.rounded_rectangle((x,y0,x+bw,y0+bh),radius=25,fill=fill,outline=edge,width=5)
        d.text((x+bw/2,y0+65),head,font=font(39,True),fill=edge,anchor="ma")
        draw_centered(d,(x+24,y0+130,x+bw-24,y0+335),body,font(29),"#263746",10)
    d.rounded_rectangle((285,675,2115,855),radius=25,fill="#F5F7FA",outline="#5D6D7E",width=4)
    draw_centered(d,(285,675,2115,855),"消融对照：自由探索 → 记录证据图 → 证据图引导 → 知识增强\n回答每一层机制是否真正提高可靠性与效率",font(34,True),"#263746",16)
    im.save(path,dpi=(220,220))


def make_dogfood_figure(path: Path, report_page3: Path, report_page8: Path) -> None:
    page3=Image.open(report_page3).convert("RGB")
    page8=Image.open(report_page8).convert("RGB")
    # Pair one representative atomistic model with a quantitative result from
    # the same interfacial system; normalize their visual footprint.
    acidic_model=page3.crop((535,835,790,1015))
    binding_plot=page8.crop((120,305,845,720))
    acidic_model=acidic_model.resize((708,500),Image.Resampling.LANCZOS)
    binding_plot=binding_plot.resize((820,470),Image.Resampling.LANCZOS)
    w,h=2400,900; im=Image.new("RGB",(w,h),"white"); d=ImageDraw.Draw(im)
    d.text((w//2,42),"未发表合作研究中的代表性模型与定量结果",font=font(55,True),fill="#102A43",anchor="ma")
    panels=[("A  酸性 Glu⁻ / Li⁺ / Ag + Li 终态模型",acidic_model),("B  Li 吸附能定量比较",binding_plot)]
    for i,(label,panel) in enumerate(panels):
        x=105+i*1165
        d.rounded_rectangle((x,140,x+1025,790),radius=22,fill="#FAFCFE",outline="#B7C9D6",width=4)
        d.text((x+35,170),label,font=font(34,True),fill="#2878B5",anchor="la")
        px=x+(1025-panel.width)//2; py=225+(535-panel.height)//2
        im.paste(panel,(px,py))
    d.text((w//2,850),"结构模型与吸附能相互对应，酸性 Glu 修饰体系表现出更强的 Li 结合",font=font(30,True),fill="#263746",anchor="mm")
    im.save(path,dpi=(220,220))


def crop_cjc(src: Path, out: Path) -> None:
    im=Image.open(src).convert("RGB")
    # LibreOffice exports the EMF on a full portrait canvas. The scientific
    # panel occupies this stable central band; exclude the old checkbox/footer.
    im=im.crop((35, 405, 770, 680))
    im.save(out,dpi=(220,220))


def style_table(table) -> None:
    table.autofit = False
    for r,row in enumerate(table.rows):
        for c,cell in enumerate(row.cells):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcPr=cell._tc.get_or_add_tcPr()
            shd=tcPr.find(qn("w:shd")) or OxmlElement("w:shd")
            shd.set(qn("w:fill"), "DCE6F1" if r==0 else ("F5F7FA" if r%2==0 else "FFFFFF"))
            if shd.getparent() is None: tcPr.append(shd)
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c<2 else WD_ALIGN_PARAGRAPH.LEFT
                for run in p.runs:
                    run.font.size=Pt(8.5); run.font.name="Arial"
                    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "PingFang SC")
                    run.font.color.rgb=RGBColor(0,0,0)
                    if r==0: run.bold=True
            borders=tcPr.find(qn("w:tcBorders")) or OxmlElement("w:tcBorders")
            if borders.getparent() is None: tcPr.append(borders)
            for edge in ("top","left","bottom","right","insideH","insideV"):
                e=borders.find(qn(f"w:{edge}")) or OxmlElement(f"w:{edge}")
                e.set(qn("w:val"),"single"); e.set(qn("w:sz"),"4"); e.set(qn("w:color"),"D9D9D9")
                if e.getparent() is None: borders.append(e)


def insert_comparison_table(document, paragraph):
    data=[
        ["比较维度","El Agente","ARCHE","Cloudra"],
        ["核心定位","通用量子化学任务编排","机理假设—Gaussian计算—反思闭环","复杂均相机理的可验证自主解析"],
        ["智能放置","意图解析、任务分解与工具调用","通用推理模型与Gaussian专家模型协作","智能用于假设、异常与证据冲突；机械工序外包"],
        ["化学工具","常规量子化学工具链","以Gaussian计算为中心的规划与诊断","反应映射、初猜校验、路径验证及结构/电子工具"],
        ["运行环境与资源","工作流执行与常规重试","工具工作流图","事件驱动调度、集群/本地适配、恢复、唤醒与权限门禁"],
        ["科学交付","任务结果与文本报告","案例式机理闭环","计算证据绑定的机理图与阶段门禁"],
        ["系统评测","课业任务和典型案例","案例叙事与专项模型准确率","多维形式化评测、消融与科学不可行任务拒答"],
        ["真实科研接入","代表性演示任务","三类案例验证","直接接入实验室计算任务并用反馈迭代系统"],
    ]
    table=document.add_table(rows=len(data),cols=4)
    for i,row in enumerate(data):
        for j,val in enumerate(row): table.cell(i,j).text=val
    widths=[1.15,1.65,1.85,3.05]
    for row in table.rows:
        for cell,width in zip(row.cells,widths): cell.width=Inches(width)
    style_table(table)
    paragraph._p.addnext(table._tbl)
    cap=insert_paragraph_after(paragraph,"表1. Cloudra与近邻化学智能体的系统设计比较")
    cap._p.addnext(table._tbl)
    cap.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for run in cap.runs: run.font.size=Pt(9)
    return table


def main(src: Path, out: Path, asset_dir: Path, emf_png: Path, report_dir: Path) -> None:
    asset_dir.mkdir(parents=True,exist_ok=True)
    runtime=asset_dir/"runtime_boundary.png"; toolchain=asset_dir/"chemical_toolchain.png"
    benchmark=asset_dir/"formal_benchmark.png"; dogfood=asset_dir/"lab_dogfood.png"; cjc=asset_dir/"cjc_prior_work.png"
    make_runtime_figure(runtime); make_toolchain_figure(toolchain); make_benchmark_figure(benchmark)
    make_dogfood_figure(dogfood,report_dir/"page-03.png",report_dir/"page-08.png"); crop_cjc(emf_png,cjc)

    doc=Document(src)
    # Remove embedded OLE preview objects; they are replaced by stable PNG figures below.
    for p in list(doc.paragraphs):
        if p._p.xpath('.//w:object'):
            p._element.getparent().remove(p._element)
    for p in list(doc.paragraphs):
        if OLD_TITLE in p.text: replace_paragraph(p,p.text.replace(OLD_TITLE,NEW_TITLE))
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    if OLD_TITLE in p.text: replace_paragraph(p,p.text.replace(OLD_TITLE,NEW_TITLE))

    info=doc.tables[3]
    set_cell_text(info.cell(14,2),NEW_EN_TITLE)
    set_cell_text(info.cell(22,1),"（限400字）：\n轴手性反应的选择性形成涉及复杂构象、细微过渡态能差与严格路径验证，是人工智能辅助化学研究的理想压力测试。现有化学智能体已能编排常规量子化学任务，但仍常把模型用于机械操作，在长周期计算、过渡态校验和证据交付中缺乏稳定约束。本项目拟发展Cloudra化学智能体，重新讨论“何时真正需要智能”：将原子映射、反应中心识别、过渡态初猜与校验、计算调度和结果解析交给确定性工具与事件驱动运行环境，使智能体议会聚焦机理假设、异常诊断和证据冲突；以证据图和阶段门禁保证结论可审计；建立覆盖机理图、路径自洽、能垒准确性、计算效率及科学拒答的形式化评测体系。申请人具备轴手性机理与材料界面计算经验，并已推动Cloudra服务真实实验室工作者的计算任务。")
    set_cell_text(info.cell(23,1),"(Limit: 3000 characters):\nAxially chiral reactions provide a demanding test bed for AI for Science because their selectivity depends on conformational complexity, small transition-state energy differences, and rigorous reaction-path validation. Existing chemistry agents can orchestrate routine quantum-chemical jobs, but they often expend model intelligence on mechanical operations and lack robust support for long-running calculations, transition-state verification, and evidence-based delivery. This project will advance Cloudra by asking a fundamental design question: when is intelligence genuinely required? Deterministic tools and an event-driven execution environment will handle atom mapping, reactive-center identification, transition-state preparation and validation, resource scheduling, and result parsing. A peer agent council will focus on mechanistic hypotheses, exception diagnosis, and evidence conflicts. An evidence graph with ordered stage gates will make mechanistic claims auditable, while a formal evaluation framework will assess mechanism coverage, pathway consistency, barrier accuracy, computational efficiency, and justified refusal on scientifically infeasible tasks. The applicant brings prior experience in axial-chirality mechanisms and materials-interface computation and has advanced Cloudra toward computational tasks used by real laboratory researchers.")

    ps=list(doc.paragraphs)
    for p in ps:
        t=p.text.strip()
        if t.startswith("小分子药物的三维空间复杂度"):
            replace_paragraph(p,"小分子药物的三维空间复杂度与理化性质和临床开发成功率密切相关。提高sp3杂化比例、引入稳定手性元素能够拓展传统平面芳香体系之外的化学空间（图1；J. Med. Chem. 2024, 67, 4322）。其中，轴手性不依赖传统手性中心，却能够通过受限旋转形成稳定、信息密集的三维构型，已成为不对称合成和药物分子设计的重要结构来源。")
        elif t.startswith("手性合成方法的发展"):
            replace_paragraph(p,"中心手性、螺旋手性、面手性和轴手性共同构成分子三维性的不同实现方式（图2）。轴手性体系兼具构象柔性与构型稳定性：反应发生前存在大量可互变构象，而选择性往往由若干竞争过渡态之间仅1–3 kcal/mol量级的自由能差决定。研究者不仅需要找到过渡态，还必须证明其具有单一虚频，并通过双向反应路径计算连接正确端点，同时比较构象与非共价相互作用。由此形成“假设多、搜索贵、验证严”的典型AI4S问题。")
        elif t.startswith("然而，非中心手性元素"):
            replace_paragraph(p,"传统研究依赖专家凭经验提出候选构型、逐项准备输入文件、等待计算并人工回收结果。高通量实验和自动化量化工具虽能扩大搜索范围，却不能自动保证机理结论的完整性。真正的瓶颈不是“能否调用一次计算”，而是能否在长周期、异步、多分支的探索中保持科学目标不漂移，并把每个结论绑定到可复查的结构、日志与路径证据。")
        elif t.startswith("近年来，随着人工智能技术"):
            replace_paragraph(p,"近年来，El Agente证明了常规量子化学任务可由智能体自动编排；ARCHE进一步展示了“机理假设—Gaussian计算—结果反思”的闭环。它们构成Cloudra的重要系统与任务近邻。Cloudra的切入点不是堆叠更多角色或让模型接管所有操作，而是重新讨论：究竟在什么时候才真正需要“智能”？本项目将重复、规则明确、可验收的工作外包给确定性工具和运行时，把Agent保留在机理假设、竞争路径取舍、异常诊断、证据冲突与方法边界判断等不可预先枚举的位置（图3）。")
            insert_comparison_table(doc,p)
        elif t.startswith("轴手性体系因其构象灵活"):
            replace_paragraph(p,"Cloudra围绕这一边界形成四层体系：反应映射工具从反应物与产物中提取原子对应、反应中心及成断键关系；过渡态初猜模块结合路径插值、参考构型和几何检查生成并筛选可计算结构；自动处理流程连续完成过渡态优化、频率分析、双向反应路径计算与端点确认；构象、轨道、电荷、键级、日志和轨迹工具则提供结构化化学感知。事件驱动运行环境进一步托管本地与集群资源、长任务唤醒、失败恢复、上下文连续性和权限门禁。智能体议会以对等讨论组织不同专业判断，作为确定性模块之间的“润滑层”；交付证据图则以阶段锁阻止未经验证的自然语言结论。")
        elif t.startswith("申请人前期围绕轴手性化合物"):
            replace_paragraph(p,"申请人已在真实轴手性问题中完成“计算预测—实验事实—机理解释”的前期训练。针对锥形化N–N轴手性体系，通过理论计算比较N–N键旋转与氮中心反转两条构型转化途径：前者能垒为29.8 kcal/mol，后者仅为2.6 kcal/mol；结合实验构型稳定性，确认该类分子的手性来源是受阻N–N键旋转而非稳定氮中心。相关成果以共同第一作者发表于Chinese Journal of Chemistry（2026, 44, 3033；图4）。")
        elif t.startswith("（可写与喻院长合作的项目"):
            replace_paragraph(p,"申请人还参与了喻林萍院长团队聂艳媚老师主持的未发表合作研究，围绕不同酸碱性氨基酸对Ag/Cu集流体和金属锂沉积行为的差异调控，开展表面模型、前线轨道、界面偶极与功函数、Li吸附能、差分电荷密度和Bader电荷等计算，形成可供实验团队讨论的分子层面解释（图5）。该工作与CJC轴手性研究共同表明，申请人能够从实验问题出发组织多层次计算证据，并将电子结构结果转化为可检验的机理认识。")
        elif t.startswith("申请人拟进一步推动研究范式"):
            replace_paragraph(p,"在系统研发方面，申请人已独立完成Cloudra事件驱动内核、计算调度、智能体协作、化学工具与证据图的主体实现。系统具备反应映射、过渡态初猜与校验、过渡态优化及路径验证，以及结构构建、构象采样、电子结构分析和日志解析等能力；计算任务可在本地与集群环境中异步运行，并通过事件唤醒回到科学决策。前期还建立了分难度机理题库和科学不可行任务，并已让真实实验室工作者使用Cloudra辅助日常计算任务，为本项目开展用户场景验证、系统消融与形式化评测奠定基础。")
        elif t.startswith("研究目标："):
            replace_paragraph(p,"研究目标：以Cloudra为核心，建立面向轴手性反应的AI4S计算研究体系：（1）明确智能决策与确定性自动化的边界，使智能体聚焦机理假设和异常判断；（2）完善从反应映射、过渡态初猜与校验到优化和路径验证的完整工具链，实现长周期过渡态搜索的稳定执行；（3）以证据图交付可审计机理，并建立多维形式化评测体系验证各组成机制的有效性；（4）在真实实验室合作中完成“实验问题—自动计算—机理证据—实验反馈”闭环。")
        elif t.startswith("拟解决的关键问题："):
            replace_paragraph(p,"拟解决的关键问题：（1）智能应在何处介入？如何把规则明确的机械操作交给工具和运行环境，同时给予智能体足够灵活的化学操作权限，使其能在未知机理、失败计算与证据冲突处发挥作用？（2）如何可靠获得并验证轴手性反应的竞争过渡态？需要同时解决反应中心识别、初猜质量、构象覆盖、单虚频与双向反应路径连通。（3）如何证明系统真正有效？不能只展示成功案例，而应从交付诚信、路径自洽、结果准确、效率稳健和科学拒答等维度进行可重复评测。")
        elif t.startswith("拟采取的研究思路："):
            replace_paragraph(p,"研究方法：首先建立反应物与产物之间的原子对应，识别反应中心和候选通道；随后生成过渡态初猜，并通过几何合理性、参考结构和反应坐标变化进行校验；再自动推进过渡态优化、单虚频分析、双向反应路径计算和端点优化，异常节点交由智能体议会结合构象与电子结构工具诊断；最终把物种、路径、能量和原始计算材料绑定到交付证据图，只有满足阶段要求的结果才能进入机理结论（图6）。")
            cap=add_picture_after(p,toolchain,7.5,"图6. 从反应映射、过渡态初猜到路径验证的证据交付工具链")
            evalp=insert_paragraph_after(cap,"形式化评测：构建基础、常规、高难和科学不可行四档任务，以交付诚信、机理图覆盖、过渡态及反应路径自洽性、能垒与性质准确性、资源消耗、错误恢复和结构化拒答为指标；设置自由探索、记录证据图、证据图引导和知识增强等消融条件，回答运行环境、证据门禁和领域知识分别贡献了什么（图7）。")
            evalp.paragraph_format.page_break_before = True
            add_picture_after(evalp,benchmark,7.5,"图7. Cloudra形式化评测与消融设计")
        elif t.startswith("预期成果："):
            replace_paragraph(p,"预期成果：形成一套关于“何时需要智能”的化学智能体运行环境；完善反应映射、过渡态初猜与校验、过渡态优化及路径验证等配套化学工具；发布可复现的分级机理评测集和多维评分方法；完成轴手性竞争路径与立体选择性案例，并在真实实验室合作任务中验证其可用性；形成软件著作权、研究论文和可供后续实验迭代的机理计算材料。")
        elif t == "图3. 人工智能/理论计算精准设计":
            replace_paragraph(p,"图3. Cloudra对智能决策与确定性自动化边界的重新划分")
        elif t == "图3. AI预测场景应用":
            replace_paragraph(p,"图4. N–N轴手性来源的计算辨识与已发表前期成果")
        elif t == "图5. 自动筛选应用场景":
            replace_paragraph(p,"图5. 未发表合作研究中的酸性界面模型与Li吸附能定量结果")

    # Replace the original rough AI diagram.
    replace_picture(doc.paragraphs[53],runtime,7.5)
    for p in list(doc.paragraphs):
        if "rId13" in p._p.xpath('.//a:blip/@r:embed'):
            p._element.getparent().remove(p._element)
    # Insert stable replacements for the two former OLE figures before their captions.
    for p in list(doc.paragraphs):
        if p.text.strip().startswith("图4. N–N轴手性"):
            before=insert_paragraph_after(doc.paragraphs[58]) if False else None
            pic=doc.add_paragraph(); pic.alignment=WD_ALIGN_PARAGRAPH.CENTER; pic.add_run().add_picture(str(cjc),width=Inches(7.1))
            p._p.addprevious(pic._p)
        if p.text.strip().startswith("图5. 未发表合作研究"):
            pic=doc.add_paragraph(); pic.alignment=WD_ALIGN_PARAGRAPH.CENTER; pic.add_run().add_picture(str(dogfood),width=Inches(7.3))
            system_p=next(q for q in doc.paragraphs if q.text.strip().startswith("在系统研发方面"))
            # Keep the figure with the unpublished-collaboration paragraph;
            # the Cloudra platform paragraph belongs after the figure.
            system_p._p.addprevious(pic._p)
            system_p._p.addprevious(p._p)

    out.parent.mkdir(parents=True,exist_ok=True)
    doc.save(out)


if __name__=="__main__":
    if len(sys.argv)!=6:
        raise SystemExit("usage: revise_application_ai4s.py SOURCE OUTPUT ASSET_DIR CJC_EMF_PNG REPORT_RENDER_DIR")
    main(*(Path(x) for x in sys.argv[1:]))
