#!/usr/bin/env python3
"""Generate SELECTION.md (screening sheet with verbatim abstracts + curated
recommendation scores) from the four tier metadata.json files.

Abstracts/titles/candidates are taken verbatim from metadata.json (no hand
transcription); scores are curated by the coordinator agent in REC below.
"""
import datetime
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
TIER_ORDER = ["easy", "normal", "hard", "impossible"]
TIER_TITLE = {
    "easy": "EASY 梯队 —— 单步基元反应（重原子 ≤7，xTB 全流程可算；目标 30 题）",
    "normal": "NORMAL 梯队 —— 多步机理 / 竞争路径（中等分子；目标 30 题）",
    "hard": "HARD 梯队 —— 立体化学 / 微观几何感知（目标 20 题）",
    "impossible": "IMPOSSIBLE 梯队 —— 多参考态 / 开壳层（考察合理拒答；目标 20 题）",
}
OA_LABEL = {
    "oa": "OA", "gold_oa": "Gold OA", "green_oa": "Green OA",
    "hybrid_oa": "Hybrid OA", "bronze_oa": "Bronze OA", "closed": "付费墙",
}
WEIGHTS = (0.30, 0.25, 0.30, 0.15)  # fit, data, value, access

# id -> (fit, data, value, access, reason)   各分项 0-10
REC = {
    # ---------------- EASY ----------------
    "easy-01": (10, 10, 10, 9,
        "全梯队最高优先：11 个周环反应实验活化焓已标准化到 ΔH‡0K，题目—真值链最完整，可直接出 5–8 道 Easy 题。"),
    "easy-02": (10, 10, 9, 6,
        "BHPERI 26 能垒的 Wn-F12 真值比 Guner 2003 更新更准；虽付费墙，数值可通过本地 GMTKN55 子集交叉获取。"),
    "easy-03": (10, 10, 8, 6,
        "28 个 CCSDT(Q)/CBS 能垒且刻意限定 4–7 个非氢原子过渡态，与 Easy 定义逐字吻合，适合作高精度参考值层。"),
    "easy-04": (8, 8, 6, 5,
        "方法学论文，数据集可反查但反应条目零散；仅作参考能垒补充源。"),
    "easy-05": (10, 9, 9, 9,
        "SN2/E2 竞争教科书级体系，全势能面公开且有 PDF；卤素+乙基卤素系列可直接出题。"),
    "easy-06": (9, 9, 8, 9,
        "5000+ 自动化 [3+2] 剖面数据库（Sci Data），小型原型子集即取即用，还可与本项目自动剖面流程对标。"),
    "easy-07": (10, 8, 8, 9,
        "最小体系 F−+CH3Cl 仅 3 重原子，金色 OA 数据完整；与 easy-05 组成甲基取代/离去基效应梯度。"),
    "easy-08": (8, 7, 7, 9,
        "小环二酮 keto-enol 含水催化通道，机理略超'单步'定义但仍属 Easy；互变异构类补充。"),
    "easy-09": (9, 10, 8, 6,
        "NHTBH38/04 是原子转移/SN2 类经典真值库；付费墙但全部数值收录于 GMTKN55（本地已有）。"),
    "easy-10": (7, 8, 5, 5,
        "大型泛函评测元基准，自身不提供新反应体系；仅在需要更多参考点时反查。"),
    "easy-11": (7, 6, 7, 7,
        "autodE 工具论文——与基准 Agent 的自动剖面流程直接同构，方法学对照价值大于选题价值。"),
    "easy-12": (9, 10, 8, 9,
        "GMTKN55 一站式汇总 BHPERI/BH76/RC21 等子集真值，本地已有 PDF；作为 Easy 梯队总真值库保留。"),
    # ---------------- NORMAL ----------------
    "normal-01": (8, 8, 9, 5,
        "MBH 三步机理+两类质子转移通道竞争，假设淘汰型考题的经典素材；体系中等偏大但 DFT 可算。"),
    "normal-02": (8, 8, 9, 5,
        "Wittig 机理剖析权威文献，加成/氧磷杂环丁烷/环消除三段式结构清晰，适合多步路径排序题。"),
    "normal-03": (8, 7, 8, 5,
        "与 normal-02 配套的'[2+2] 还是两阶段一步'争议点，单独成题价值稍低，建议合并使用。"),
    "normal-04": (8, 8, 9, 5,
        "离子 vs 自由基通道定量能垒对比（18.7 vs 27.6 kcal/mol），标准假设淘汰题模板。"),
    "normal-05": (7, 7, 8, 5,
        "结论依赖 CASSCF，单参考流程可能无法复现判据——更适合挪入 Impossible 作方法依赖性讨论，故降为备选。"),
    "normal-06": (9, 9, 8, 9,
        "同一反应对两条通道（极性 DA vs 极性 ene）完整能量剖面，OA 有 PDF，竞争路径题的标准配置。"),
    "normal-07": (8, 8, 8, 9,
        "三种 Lewis 酸引起机理切换（两阶段一步 vs 分步），催化剂调制变量设计良好，OA。"),
    "normal-08": (9, 8, 9, 9,
        "已发表机理被推翻+显式排除 DA 通道，假设淘汰素材最丰富的一篇；中等尺寸呋喃-硝基烯烃体系对 xTB/DFT 流水线友好，OA。"),
    "normal-09": (7, 7, 7, 8,
        "动力学模拟视角考察同步性；静态基准只取其能垒数据，动态结论本项目暂不考核。"),
    "normal-10": (6, 6, 7, 8,
        "自由基离子开壳层体系，常规闭壳层流水线处理困难，边界属性强于 Normal 梯队定位。"),
    "normal-11": (8, 7, 7, 8,
        "氮杂双烯体 HDA 的 peri/区域/立体三重选择性竞争，arXiv 版可得，异原子体系扩展的好素材。"),
    "normal-12": (7, 7, 8, 9,
        "自动反应网络探索的对照组文献，HCHO+NH3 网络小而全，可作'网络级'扩展题型试点。"),
    # ---------------- HARD ----------------
    "hard-01": (9, 9, 10, 5,
        "endo 规则的现代活化应变解释，几何感知考题的核心锚点文献。"),
    "hard-02": (9, 8, 9, 5,
        "与 hard-01 构成正反方辩论（次级轨道相互作用是否必要），配对出题价值高。"),
    "hard-03": (9, 8, 8, 5,
        "小张力双烯亲合物导致 endo/exo 偏好翻转（1.8–2.8 kcal/mol），量化翻转幅度适合写进评分细则。"),
    "hard-04": (10, 9, 10, 9,
        "教科书规则失效的反例集（反常 exo 选择性），阴性对照考题最佳来源，且有 PDF。"),
    "hard-05": (4, 8, 7, 9,
        "腔量子电动力学控制选择性——概念震撼但 QED-CC 无法在本项目流程复现，仅作概念拓展阅读。"),
    "hard-06": (7, 8, 8, 6,
        "氢键供体催化使 DA 反转为 exo 选择性；催化剂底物复合物偏大且出版社 PDF 被 403 拦截。"),
    "hard-07": (9, 8, 8, 8,
        "溶剂介电+Lewis 酸结合切换 endo/exo 并变分步机理，金色 OA，小杂芳体系可算性好。"),
    "hard-08": (10, 8, 9, 9,
        "3-取代环丁烯顺旋开环内外选择性的最小体系，有 PDF，torquoselectivity 类题首选。"),
    "hard-09": (9, 9, 8, 5,
        "取代基系列（含 3-boryl 内旋特例）QTAIM/IQA 定量能垒表；付费墙但表格数值是现成评分基准。"),
    "hard-10": (10, 9, 8, 5,
        "Houk 内旋 torquoselectivity 奠基作，取代基逐一能垒表可直接转成系列考题。"),
    "hard-11": (8, 8, 7, 9,
        "N-N 阻转异构体消旋化能垒，实验+计算互证协议完整，轴手性分支代表作，有 PDF。"),
    "hard-12": (6, 8, 8, 5,
        "CPA 对映选择性起源经典，但催化剂空腔体系重原子数 >50，计算成本超出常规预算。"),
    "hard-13": (6, 7, 7, 6,
        "同为 CPA 大体系且 PDF 被 403 拦截；除非手性催化分支扩容再考虑。"),
    "hard-14": (7, 8, 8, 5,
        "CBS 硼烷还原 Re/Si 面竞争，六元船式 TS 几何感知典型；工作量中等。"),
    "hard-15": (10, 8, 8, 9,
        "硝酮 [3+2] 的 endo/exo 定量能垒+ELF/BET 分析；小分子硝酮+顺丁烯二酸二甲酯体系完全在算力舒适区，有 PDF，把 Hard 梯队从 DA 扩展到偶极环加成。"),
    "hard-16": (8, 8, 8, 6,
        "Ireland-Claisen 船式/椅式 TS 竞争决定非对映选择性；PMC 有全文（此前自动下载失败，可手动补）。"),
    # ---------------- IMPOSSIBLE ----------------
    "impossible-01": (10, 10, 10, 9,
        "多参考态识别的金标准体系：D4h 方形过渡构型基态双组态简并，CCSDTQ 级真值齐备，拒答判定题首选。"),
    "impossible-02": (10, 10, 9, 9,
        "沿自动异构化坐标给出单/三线态双势能面，与 impossible-01 配对构成完整考题组。"),
    "impossible-03": (10, 10, 10, 9,
        "连 DMRG(24,25) 与 CAS(2,2)-MkCCSDT 都难以正确描述的单线态扭转面——检验 Agent 方法边界意识的极端案例。"),
    "impossible-04": (9, 10, 9, 9,
        "13 个强双自由基单三态能隙+基于自旋污染选参考的判据，一次入库一整族考题。"),
    "impossible-05": (9, 10, 8, 9,
        "约 13000 条 MRCI 卡宾自旋能隙数据库；自旋态指认错误即机理判断错误的典型案例库。"),
    "impossible-06": (8, 9, 8, 9,
        "有用的边界反例：DFT/CCSD(T) 尚可而 MP2 失效，训练 Agent 区分弱关联失效与多参考失效。"),
    "impossible-07": (9, 8, 9, 9,
        "π 键扭转双自由基的原型考题（90° 扭转处单参考完全失效），还展示 CASSCF 自身的陷阱，深化'多参考方法也有坑'的认知。"),
    "impossible-08": (9, 8, 9, 5,
        "双自由基oid Cope 重排的 CASSCF/CASPT2 vs B3LYP 对照标杆；付费墙但结论被综述广泛引用。"),
    "impossible-09": (9, 10, 8, 5,
        "一篇同时给 5 个经典多参考体系的 CCSDT 级单三态能隙，性价比极高的真值库。"),
    "impossible-10": (6, 7, 8, 5,
        "单参考诊断方法学论文（T1/D1/D2/S-diagnostic），作为'何时应怀疑单参考结果'的判据引用而非选题来源。"),
    "impossible-11": (6, 8, 7, 9,
        "LiF 解离避免交叉等强关联案例，方法学色彩浓于反应体系色彩。"),
    "impossible-12": (5, 7, 7, 9,
        "CASPT2 权威综述章节，作方法学锚点文档保留，不用于直接出题。"),
}


def esc(s):
    return str(s).replace("|", "\\|")


def clean(s):
    return " ".join(str(s).split())


def load(tier):
    return json.loads((BASE / tier / "metadata.json").read_text(encoding="utf-8"))


def overall(eid):
    fit, dat, val, acc, _ = REC[eid]
    return round(fit * WEIGHTS[0] + dat * WEIGHTS[1] + val * WEIGHTS[2] + acc * WEIGHTS[3], 1)


def badge(sc):
    if sc >= 8.5:
        return "必选"
    if sc >= 7.5:
        return "推荐"
    return "备选"


def acquire_line(e):
    st = OA_LABEL.get(e.get("oa_status"), e.get("oa_status", "?"))
    if e.get("pdf_file"):
        return "✅ 已下载 PDF `" + e["pdf_file"] + "`（" + st + "）"
    if e.get("already_held"):
        return "✅ 本地已有：`" + str(e["already_held"]) + "`（未重复下载）"
    return "❌ 未下载（" + st + "，仅元数据+摘要）"


def main():
    missing = []
    tiers = {}
    for t in TIER_ORDER:
        entries = load(t)
        tiers[t] = entries
        for e in entries:
            if e["id"] not in REC:
                missing.append(e["id"])
    extra = [k for k in REC if k not in {e["id"] for es in tiers.values() for e in es}]
    if missing or extra:
        raise SystemExit("REC/metadata mismatch: missing=" + str(missing) + " extra=" + str(extra))

    L = []
    today = datetime.date.today().isoformat()
    A = L.append

    tot = sum(len(v) for v in tiers.values())
    tot_pdf = sum(1 for v in tiers.values() for e in v if e.get("pdf_file"))
    tot_cand = sum(len(e.get("candidate_reactions", [])) for v in tiers.values() for e in v)

    A("# 四级测试集候选文献筛选清单（含摘要与推荐系数）")
    A("")
    A("> 生成日期：" + today + "｜数据来源：`ideapool/benchmark_literature/{easy,normal,hard,impossible}/metadata.json` 共 "
      + str(tot) + " 篇自动汇编，**摘要为原文未删节**。配套背景见 [INDEX.md](INDEX.md)。")
    A("> 用途：人工筛选正式进入四级测试集（Easy 30 / Normal 30 / Hard 20 / Impossible 20）的文献与反应体系；筛选结果反馈编号即可。")
    A("")
    A("## 数据完备度")
    A("")
    A("| 梯队 | 文献数 | PDF 在手 | 仅元数据 | 候选反应标注 | 目标题量 |")
    A("|---|---|---|---|---|---|")
    for t in TIER_ORDER:
        es = tiers[t]
        npdf = sum(1 for e in es if e.get("pdf_file"))
        ncand = sum(len(e.get("candidate_reactions", [])) for e in es)
        goal = {"easy": 30, "normal": 30, "hard": 20, "impossible": 20}[t]
        A("| " + t + " | " + str(len(es)) + " | " + str(npdf) + " | " + str(len(es) - npdf)
          + " | " + str(ncand) + " | " + str(goal) + " |")
    A("| **合计** | **" + str(tot) + "** | **" + str(tot_pdf) + "** | **" + str(tot - tot_pdf)
      + "** | **" + str(tot_cand) + "** | 100 |")
    A("")
    A("## 推荐系数说明")
    A("")
    A("综合分 = 体系适配×0.30 + 参考数据×0.25 + 测试价值×0.30 + 可获取性×0.15（各分项 0–10）：")
    A("- **体系适配**：是否符合该梯队难度定义与本项目算力（xTB→DFT 流水线、重原子规模）")
    A("- **参考数据**：是否提供可用于评分的真值（实验/高精度能垒、完整能量剖面、选择性数据）")
    A("- **测试价值**：对结构感知、机理发现、假设淘汰、合理拒答四大能力的区分度")
    A("- **可获取性**：OA 状态、PDF 是否在手、数据可否经其他途径交叉验证")
    A("")
    A("档位：**≥8.5 必选**（强烈建议纳入）｜**7.5–8.4 推荐**｜**<7.5 备选**。")

    # ---- overview ----
    A("")
    A("---")
    A("## 总览（各梯队按综合分降序）")
    for t in TIER_ORDER:
        es = sorted(tiers[t], key=lambda e: overall(e["id"]), reverse=True)
        npdf = sum(1 for e in es if e.get("pdf_file"))
        ncand = sum(len(e.get("candidate_reactions", [])) for e in es)
        A("")
        A("### " + TIER_TITLE[t])
        A("")
        A("(" + str(len(es)) + " 篇｜PDF 在手 " + str(npdf) + "｜候选反应标注 " + str(ncand) + " 条)")
        A("")
        A("| 综合分 | 档位 | ID | 年份 | 文献（短题名） | PDF |")
        A("|---|---|---|---|---|---|")
        for e in es:
            sc = overall(e["id"])
            short = esc(clean(e["title"]))
            if len(short) > 60:
                short = short[:60] + "…"
            pdftxt = "✅" if e.get("pdf_file") else ("📚" if e.get("already_held") else "—")
            A("| " + str(sc) + " | " + badge(sc) + " | " + e["id"] + " | " + str(e["year"])
              + " | " + short + " | " + pdftxt + " |")
    A("")
    A("> ✅ = 已下载 PDF；📚 = 本地另有存档；— = 付费墙仅元数据。")

    # ---- details ----
    A("")
    A("---")
    for t in TIER_ORDER:
        A("")
        A("# " + TIER_TITLE[t])
        es = sorted(tiers[t], key=lambda e: overall(e["id"]), reverse=True)
        for e in es:
            sc = overall(e["id"])
            fit, dat, val, acc, reason = REC[e["id"]]
            authors = e.get("authors", [])
            ashown = "、".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
            A("")
            A("### " + e["id"] + "｜综合 " + str(sc) + "【" + badge(sc) + "】｜" + str(e["year"]))
            A("")
            A("**" + clean(e.get("title") or "（无题名）") + "**")
            A("")
            A("- 作者：" + esc(ashown) + "（共 " + str(len(authors)) + " 人）")
            A("- 出处：" + esc(clean(e.get("venue") or "")))
            doi = e.get("doi") or ""
            if doi:
                A("- DOI：[" + doi + "](https://doi.org/" + doi + ")")
            else:
                A("- DOI：—")
            A("- 获取：" + acquire_line(e))
            A("- 分项：体系适配 " + str(fit) + "｜参考数据 " + str(dat) + "｜测试价值 " + str(val)
              + "｜可获取 " + str(acc))
            A("")
            A("**摘要**：" + clean(e.get("abstract") or ""))
            cands = e.get("candidate_reactions", [])
            A("")
            A("**候选反应（" + str(len(cands)) + "）**：")
            for c in cands:
                A("- " + clean(c))
            A("")
            A("**推荐理由**：" + reason)
            A("")
            A("`筛选标记`：☐ 入选　☐ 待定　☐ 排除")

    # ---- footer ----
    A("")
    A("---")
    A("## 筛选建议")
    A("")
    A("- **Easy**：必选 8 篇（easy-01/02/03/05/06/07/09/12）已足以覆盖 30 题，easy-08 视互变异构类需求增补。")
    A("- **Normal**：必选 2 篇打底（normal-06/08），从推荐档（01/02/04/07/11/12）按机理类型均衡挑 5–6 篇；normal-05 建议改投 Impossible 作方法依赖性案例。")
    A("- **Hard**：必选 4 篇（hard-01/04/08/15）覆盖 endo/exo、torquoselectivity、偶极环加成三大主题，推荐档按轴手性/不对称催化需求补 3–4 篇。")
    A("- **Impossible**：必选 6 篇（imp-01/02/03/04/05/07）即够 20 题；impossible-06 作为'边界反例'强烈建议保留。")
    A("- 每篇可出 1–3 题，注意跨文献的重复体系（如 BHPERI 同时见于 easy-01/02/12，环丁二烯同时见于 imp-01/02/09）。")
    A("")
    A("> 筛选完成后请回复入选编号清单（如 `easy-01, easy-05, normal-06, …`），将据此生成正式反应清单与自动化评测脚本。")

    out = BASE / "SELECTION.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("written:", out, out.stat().st_size, "bytes")
    for t in TIER_ORDER:
        es = tiers[t]
        b = {"必选": 0, "推荐": 0, "备选": 0}
        for e in es:
            b[badge(overall(e["id"]))] += 1
        print(t, "entries=", len(es),
              "must=", b["必选"], "rec=", b["推荐"], "alt=", b["备选"],
              "pdf=", sum(1 for e in es if e.get("pdf_file")))


if __name__ == "__main__":
    main()
