# Cloudra 论文文献空缺分析（Literature Gap Analysis）

> 目的：识别当前论文（`paper/main.tex` + `paper/sections/*`）在文献覆盖上的空缺，作为下一步文献补充/深读的执行清单。
> 分析基准：`paper/references.bib`（当前 18 条引用）与 `chemistry_ai_agents_literature_report.md`（2026-02 调研报告，19 篇核心候选）。

---

## 一、当前引用总览（references.bib，18 条）

| 类别 | 条目 | 条数 |
|------|------|------|
| 早期通用化学 agent（综述/引言对照） | boiko2023autonomous, bran2024chemcrow, swanson2025virtuallab | 3 |
| 计算/TS 机理 agent（引言直接对标） | zou2025elagente, chemgraph2026, arplorer2025, aitomia2026, tsagent2026, catdt2026, adsmind2026 | 7 |
| 自主科研/批评评测 | coscientist2026, yik2024chatgpt, canai2026 | 3 |
| 方法学基础（机理工作流） | fukui1981irc, smidstrup2014idpp, grimme2019crest, grimme2012goodvibes | 4 |
| 未在正文中出现的残留 | song2025chemagents（正文引用于 5.4/引言） | 1 |

**关键判断**：论文的 TS/机理 agent 对标是近年（2025–2026）的"表面催化 / 计算工作流"类系统（TSAgent、CatDT、AdsMind、El Agente、ChemGraph、ARplorer、Aitomia）。这构成了 Cloudra 的核心差异化叙事（均相小分子 vs 表面催化）。

---

## 二、文献空缺 — 调研报告已收录但论文未引用（首要补齐项）

调研报告 `chemistry_ai_agents_literature_report.md` 收录了 19 篇，其中以下 12 篇**没有**进入 `references.bib`，属于"已经调研、尚未落到论文引用"的直接空缺：

| 空缺文献 | 对 Cloudra 论文的具体价值 | 建议落点 |
|----------|--------------------------|----------|
| **ChemAgent**（Tang et al., ICLR 2025, arXiv:2501.06590）— 动态记忆库/三种记忆 | Cloudra GraphRAG（§2.5）正是"自更新记忆/经验库"的化学同构；这是综述里"记忆机制最值钱"的那篇，支撑 Cloudra 记忆设计的**差异化对照**。报告称其提升最高 46%。 | §2.5（GraphRAG）、§4.1(Stage-2 消融讨论) |
| **ChemToolAgent**（Yu et al., NAACL 2025, arXiv:2411.07228）— **负结果**：工具增强不总优于裸 LLM | 与 Cloudra"工具必须带证据校验才有增益"的论点直接对话；避免审稿人抓"工具增强必然有效"的漏洞。 | §2（coord_guard/确定性门控论述） |
| **ChemBench**（Mirza et al., Nat. Chem. 2025）— 7200 问答评测 | 给"LLM 化学能力天花板"叙事提供实证；支撑"当前 agent 能力仍有限、需要纵深验证"的动机。 | §1（引言）、§6（结论） |
| **MaCBench**（Alampara et al., Nat. Comput. Sci. 2025）— 多模态 VLLM 局限 | 与 §5.2"结构化电子感知 vs 纯多模态视觉"直接对立/对照——Cloudra 主张结构化感知优于看图，引用这篇支撑视觉路径的局限。 | §5.2（Discussion） |
| **Aviary**（Narayanan et al., ICLR 2025, arXiv:2412.21154）— LDP/POMDP 在线 RL | Cloudra 是"prompt 工程 agent"；Aviary 代表"可训练 agent"方向，是 §5.4"未来方向"里训练范式的对照点。 | §5.4（Limitations/Future） |
| **MolAct**（Yang et al., arXiv:2512.20135）— agentic RL 分子编辑 | 同上，可训练 agent 方向的另一实证；与 Cloudra"确定性证据驱动编排"形成对照。 | §5.4 |
| **SciAgent**（Ma et al., EMNLP 2024）— 工具增强科学推理训练 | 工具使用能力的训练范式，可补充 §5.4 训练方向。 | §5.4 |
| **k-agents**（Cao et al., Patterns 2025）— 量子计算实验自动化 | 广义"计算 agent"对照，完善引言"计算 agent 版图"。 | §1、§5.4 |
| **AtomAgents**（Ghafarollahi & Buehler, PNAS 2025）— 材料/合金多 agent | 材料侧 agent 版图补充（Cloudra 专注分子侧，作为对比视野）。 | §1 |
| **Virtual Lab**（已在 bib） | — | 已覆盖 |
| **DrugAgent / DrugPilot / MolAgent / Biomni / SciAgents** | 药物/材料/文献推理支线，与 Cloudra 机理主题较远 | 可选（维 C，不建议强行塞入） |

**优先级建议**：上面最值得补的是 **ChemAgent**（记忆对照）、**ChemToolAgent**（负结果对冲）、**ChemBench + MaCBench**（评测天花板 + 多模态局限对照）。其余按篇幅斟酌。

---

## 三、文献空缺 — 领域内"机理/TS agent"深挖（报告未覆盖，需补检索）

论文对标的核心叙事是"均相有机机理 agent 这块无人做过"。要坐实这个 claim，需要把**机理/TS agent 领域最邻近的工作**补全到参考文献，目前 `references.bib` 只引了 TSAgent/CatDT/AdsMind/El Agente/ChemGraph/ARplorer/Aitomia 这 7 篇。以下邻近工作**可能未真实核实收录**，需 researcher 逐篇检索核实：

1. **ground-state reaction path / TS 自动搜索的经典与最新工具**（方法学侧，非 agent）：
   - GRRM / AFIR（人工力诱导反应）— 自动反应路径搜索的代表，Cloudra 的"自动生成竞争机理假设"与 AFIR 有概念呼应。
   - `ase` / `pyro` /`autodE`（对构象—TS 自动化搜索的 Python 工具链，autodE 与 Cloudra 的"自动 TS 组装"直接同源）。
   - `xtb` / CREST 已在 bib（grimme2019crest）。
2. **LLM 做反应路径 / 机理解析的论文**（agent 侧最近邻）：
   - ARplorer（已在 bib）其实是最相近的"LLM 引导反应路径探索"，需确认正文对其进行了充分引用与对比——这是 Cloudra 最直接的 competitor-characterization，应放在引言显眼位置。
   - 检索关键词建议：`LLM reaction path exploration`、`LLM transition state search homogeneous`、`autonomous mechanism elucidation`、`LLM IRC`。
3. **多参考/开壳层与 diradical TS 自动处理**（对应 §5.4 第 1 条未来方向）：
   - 检索 diradical TS 自动多参考进化的工作，支撑"Impossible 档自动多参考升级"的路线。

---

## 四、文献空缺 — 评测 / 批评体系（报告与 bib 均薄弱，需补）

Cloudra 的一个卖点是"100 反应四档 benchmark + 消融"。要支撑 benchmark 设计的合理性，需要引用评测体系类文献：

- **Yik et al. 2024**（yik2024chatgpt）已在 — "ChatGPT 解释有机机理会轻微出错"，这是 Cloudra"completion by assertion"论点的直接实证，保持。
- **canai2026**（"Can AI Conduct Autonomous Research?" 批评评论）已在 — 支撑"三个根本局限"。
- **补：反应/机理解析基准** — 若有更标准的"机理解析能力评测集"，如 `SciBench`（ChemAgent 用了 4 个 chem 数据集）值得补引作为 benchmark 对照；ChemBench 见上。

---

## 五、执行建议（下一步动作）

1. **首要**：把 §二 里 5 篇高优先文献（ChemAgent、ChemToolAgent、ChemBench、MaCBench、Aviary）经 researcher 核实 DOI/arXiv ID 后补进 `references.bib`，并在对应章节（§2.5 GraphRAG、§5.2 感知、§4.1 消融、§5.4 未来）加 1–2 句对照引用。
2. **次要**：补做"机理/TS agent 最近邻"深检索（§三），重点核实 ARplorer 的角色定位，并检索 autodE / AFIR / GRRM 这类自动 TS 与 Cloudra 的概念关联。
3. **可选**：维 C 文献（DrugAgent 等）若压缩篇幅可放弃；注意 DrugAgent 有 arXiv 同名两篇的坑（报告已警示），引用时必须用 ID 区分。
4. 所有新增引用需在 `paper/references.bib` 补全字段（title/author/journal/volume/pages/year/doi），并重跑 LaTeX 让 citation 正确定位。

---

## 六、执行状态（2026-09-02 更新）

**已完成 ✅**（本次执行轮）：
1. **§二 高优先 5 篇已全部核实并入库**：ChemAgent（tang2025chemagent, arXiv:2501.06590, **arXiv only**，非 ICLR）、ChemToolAgent（yu2025chemtoolagent, **NAACL 2025 Findings**）、ChemBench（mirza2025chembench, Nat. Chem. 17:1027–1034, **2788 QA 非 7200**）、MaCBench（alampara2025macbench, Nat. Comput. Sci. 5:952–961）、Aviary（narayanan2025aviary, **ICLR 2025 确认**）。
2. **方法侧补引**：autodE（young2021autode, Angew. Chem. Int. Ed. 60:4266–4274）、AFIR（sameera2016afir, Acc. Chem. Res. 49:763–773 综述——原始 2010 JCTC 页码未复核，暂用综述）。
3. **agent 版图补引**：SciAgent（ma2024sciagent, EMNLP 2024）、k-agents（cao2025agents, Patterns）、AtomAgents（ghafarollahi2024atomatoms, **arXiv only，非 PNAS**）。
4. **ARplorer 已进正文引言**（competitor-characterization 显眼位置）。
5. 正文接线：§1 引言（autodE/AFIR/ARplorer/SciAgent/k-agents/AtomAgents/ChemBench）、§2.4 确定性门控（ChemToolAgent/ChemBench）、§2.5 GraphRAG（ChemAgent 对照）、§5.2 感知（MaCBench）、§5.4 未来（Aviary/MolAct/SciAgent/ChemToolAgent/ChemBench）。
6. **LaTeX 编译验证通过**（tectonic EXIT 0，29 bibitems 全部解析，无 undefined citation）。

**仍开放 ⏳**：
1. §三 深检索——多参考/diradical TS 自动多参考升级路线的文献（支撑 Impossible 档叙事）；GRRM 尚未入库（AFIR 已入）。
2. §四 的 SciBench 类"机理解析能力评测集"对照（可选）。
3. §五-2 建议的 "LLM homogeneous TS search" 深检索未做实（ARplorer 已覆盖 LLM 路径探索主位）。
