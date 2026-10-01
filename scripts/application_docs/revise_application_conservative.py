import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches
from revise_application_ai4s import (
    add_picture_after,
    crop_cjc,
    insert_comparison_table,
    insert_paragraph_after,
    make_benchmark_figure,
    make_dogfood_figure,
    make_runtime_figure,
    make_toolchain_figure,
    replace_paragraph,
    replace_picture,
)


def replace_ole_picture(paragraph, image_path: Path, width: float) -> None:
    for obj in list(paragraph._p.xpath(".//w:object")):
        obj.getparent().remove(obj)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(image_path), width=Inches(width))


def main(source: Path, output: Path, asset_dir: Path, cjc_emf_png: Path, report_dir: Path) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    runtime = asset_dir / "runtime_boundary.png"
    toolchain = asset_dir / "chemical_toolchain.png"
    benchmark = asset_dir / "formal_evaluation.png"
    collaboration = asset_dir / "collaboration_models.png"
    cjc = asset_dir / "cjc_prior_work.png"
    make_runtime_figure(runtime)
    make_toolchain_figure(toolchain)
    make_benchmark_figure(benchmark)
    make_dogfood_figure(collaboration, report_dir / "page-03.png", report_dir / "page-08.png")
    crop_cjc(cjc_emf_png, cjc)

    doc = Document(source)

    # Keep the mentor's wording, changing only the requested collaborator attribution.
    for p in doc.paragraphs:
        if "罗维纬副教授展开合作" in p.text:
            replace_paragraph(p, p.text.replace("罗维纬副教授展开合作", "罗维纬副教授、喻林萍院长展开合作"))
        elif "罗维纬副教授团队开展实验验证" in p.text:
            replace_paragraph(p, p.text.replace("罗维纬副教授团队开展实验验证", "罗维纬副教授、喻林萍院长团队开展实验验证"))
        elif "在罗维纬副教授的指导下" in p.text:
            replace_paragraph(p, p.text.replace("在罗维纬副教授的指导下", "在罗维纬副教授、喻林萍院长的指导下"))

    # Improve the rough AI4S illustration without rewriting its surrounding prose.
    replace_picture(doc.paragraphs[53], runtime, 7.5)
    runtime_story = insert_paragraph_after(
        doc.paragraphs[56],
        "在El Agente与ARCHE等近邻工作已证明智能体可以规划并执行量子化学任务的基础上，Cloudra进一步追问：究竟在什么时候才真正需要“智能”？本项目不让大模型逐条接管重复、规则明确且可验收的机械操作，而是把原子对应、输入生成、任务提交、状态轮询、结果解析和阶段检查交给确定性工具与运行环境；把智能判断保留在机理假设、竞争路径取舍、异常诊断、证据冲突和方法边界等难以预先枚举的环节。这样既继承近邻体系“先计算、后核验”和连接真实量子化学程序的优点，也避免把昂贵且不稳定的模型推理消耗在固定流程上。",
    )
    runtime_detail = insert_paragraph_after(
        runtime_story,
        "围绕这一原则，Cloudra形成“科学决策—化学工具—运行环境—证据交付”的分层体系。上层由多个具有不同专业视角的智能体通过议会式讨论提出竞争机理、复核异常并决定继续或停止；中层提供反应映射、过渡态初猜与参考结构校验、过渡态优化、频率与双向反应路径验证，以及构象、轨道、电荷、键级和日志解析等工具；底层针对长周期计算专门适配本地与集群资源调度、容量控制、异步唤醒、失败恢复、上下文连续性和操作权限。智能体在这些确定性模块之间充当“润滑层”，而不是替代每一步程序。最终，物种、反应路径、能量和原始计算材料被绑定为可追溯的交付证据，未经验证的自然语言判断不能直接进入机理结论。",
    )
    insert_comparison_table(doc, runtime_detail)

    # Restore the CJC figure and fill the explicit unpublished-project placeholder.
    ole_paragraphs = [p for p in doc.paragraphs if p._p.xpath(".//w:object")]
    replace_ole_picture(ole_paragraphs[0], cjc, 7.1)
    placeholder = next(p for p in doc.paragraphs if p.text.strip().startswith("（可写与喻院长合作的项目"))
    replace_paragraph(
        placeholder,
        "申请人还参与了喻林萍院长团队聂艳媚老师主持的未发表合作研究，围绕不同酸碱性氨基酸对Ag/Cu集流体和金属锂沉积行为的差异调控，开展表面模型、前线轨道、界面偶极与功函数、Li吸附能、差分电荷密度和Bader电荷等计算，形成可供实验团队讨论的分子层面解释（图4）。该工作表明，申请人能够从实验问题出发组织多层次计算证据，并将电子结构结果转化为可检验的机理认识。",
    )
    replace_ole_picture(ole_paragraphs[1], collaboration, 7.3)
    collaboration_caption = next(p for p in doc.paragraphs if p.text.strip() == "图5. 自动筛选应用场景")
    replace_paragraph(collaboration_caption, "图4. 未发表合作研究中的酸性界面模型与Li吸附能定量结果")

    # Preserve the mentor's research-plan paragraph, then add the requested
    # AI4S method, technical route and formal evaluation immediately after it.
    plan = next(p for p in doc.paragraphs if p.text.strip().startswith("拟采取的研究思路："))
    method = insert_paragraph_after(
        plan,
        "研究方法：首先利用反应映射建立反应物与产物之间的原子对应，识别反应中心、成键与断键关系及可能的竞争通道；随后综合路径插值、已知相似结构和化学几何约束生成过渡态初猜，并通过反应坐标变化、结构合理性及参考构型比较进行校验。通过初步校验的结构进入过渡态优化、单虚频分析、双向反应路径计算和端点优化；如出现虚频方向错误、路径不连通、构象漂移或计算失败，智能体议会调用构象与电子结构分析工具诊断原因，调整假设后重新计算。最终将物种、路径、能量、频率、轨迹和原始日志绑定到交付证据图，只有满足相应阶段要求的结果才能进入机理结论（图6）。",
    )
    cap6 = add_picture_after(method, toolchain, 7.5, "图6. 从反应映射、过渡态初猜到路径验证的证据交付工具链")
    route = insert_paragraph_after(
        cap6,
        "技术路线：事件驱动运行环境统一管理本地工作站与计算集群，在提交任务时显式申请计算资源，根据实时容量安排队列，并在长任务完成、失败或需要人工判断时唤醒相应智能体。对可机械化的步骤采用确定性程序连续推进，对需要化学判断的节点才调用智能体；议会成员可在权限边界内读取结构、调用工具、提交计算和复核证据，使自动化流程在复杂反应研究中既具有足够操作能力，又能保持过程可控和结果可审计。",
    )
    evaluation = insert_paragraph_after(
        route,
        "形式化评测：除展示个别成功案例外，本项目将建立基础、常规、高难和科学不可行四档任务，从交付诚信、机理图覆盖、过渡态与反应路径自洽性、能垒及性质准确性、资源消耗、错误恢复和合理拒答等维度评价体系。进一步设置自由探索、仅记录证据、证据图引导和知识增强等对照条件，通过消融实验分别检验运行环境、化学工具、证据门禁和领域知识的贡献，从而回答体系为何有效、在哪些条件下有效以及何时不应给出结论（图7）。",
    )
    cap7 = add_picture_after(evaluation, benchmark, 7.5, "图7. Cloudra形式化评测与消融设计")
    insert_paragraph_after(
        cap7,
        "真实场景验证：Cloudra的目标不是停留在封闭题库或演示案例中。申请人将持续把系统接入真实实验室工作者的计算任务，让科研人员以自然语言提出结构构建、计算检查和机理分析需求，系统负责组织确定性工具与长周期计算，并返回可复核的结构、日志和证据链。真实使用中出现的失败、追问和人工修正将反向进入工具完善与评测设计，形成“实验问题—自动计算—机理证据—实验反馈”的闭环，以实际科研工作检验系统的可用性与边界。",
    )

    # The original contains two consecutive page breaks near the end; the
    # second one creates a blank page. Remove only that empty break paragraph.
    for p in list(doc.paragraphs):
        if not p.text.strip() and p._p.xpath('.//w:br[@w:type="page"]'):
            p._element.getparent().remove(p._element)

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)


if __name__ == "__main__":
    if len(sys.argv) != 6:
        raise SystemExit("usage: revise_application_conservative.py SOURCE OUTPUT ASSET_DIR CJC_EMF_PNG REPORT_RENDER_DIR")
    main(*(Path(x) for x in sys.argv[1:]))
