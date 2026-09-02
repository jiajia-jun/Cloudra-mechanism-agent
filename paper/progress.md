# progress.md — novelty 叙事打磨 + benchmark 构建叙事 + 架构图清理（2026-09-02）

## ⭐ 竞品实时核查（2026-09 更新）
**结论：Cloudra 的竞品已出现且集中为 2025–2026 的表面催化/计算工作流类 agent；核心差异化（均相小分子机理）仍未被占据。**

**已确认在线并已入 bib（7 篇，均 2025-2026）：**
- **TSAgent**（2026-05-13）— 明确为**异相催化**：OC20NEB 异相催化基准 100 例、83% 精度、NH3 解离 BEP 标度。
- **Aitomia** — 已从 preprint 落地为 **J. Chem. Theory Comput. 2026**（DOI 10.1021/acs.jctc.6c00591），多 agent 计算工作流。
- **ChemGraph** — 落地为 **Communications Chemistry 2026-01-08**（DOI 10.1038/s42004-025-01776-9），multi-agent 计算化学工作流。
- CatDT（异相网络数字孪生）、AdsMind（吸附构型搜索）、El Agente、ARplorer（LLM 反应路径探索）。

**⚠️ 关键新发现（必须回填论文）：**
> **arXiv:2608.18508**（2026-08-19）「Science Done on a Machine by a Machine: AI Agents in Computational Chemistry」——截至 2026-08-08 已收录**近 50 个**计算化学 agentic 系统（2024 约 6、2025 约 12 → 2026 约 50）。这证明：(a) 该赛道已爆发，竞争激烈；(b) 该文指出"专门 agent 可能被通用 agent 取代""多数系统仅有开发者自行采用"——这是 Cloudra 必须正面回应的**价值主张挑战**（为何专用 agent + 证据门控仍有必要）。

**差异化未变：** 所有已确认竞品要么异相催化（TSAgent/CatDT/AdsMind），要么通用计算工作流（Aitomia/ChemGraph），**无一**做均相小分子有机机理 + 立体化学感知 + 证据门控 deliverable-DAG + GraphRAG 的自主阐明。均相机理 niche 仍空缺——但需把"无人做过"说法收紧为"目前无公开系统占据该 niche"，避免被"已被 50 家覆盖"的审稿人质疑。

## 本轮（用户反馈后）完成
- **架构图重画**（`paper/main.tex` §2 figure* `fig:architecture`）：由原"放射状 6-agent + 3 条 16.4cm 宽横条"的拥挤布局，改为**自上而下的四段式**：
  1. Peer Collective 容器（6 个 agent 等环 + AgentHub 椭圆中心，标"equal peers, no commander"）；
  2. Governance & Knowledge 带（GraphRAG | Delivery DAG Evidence Engine | Supervisor 三框并排，箭头指向中间 DAG）；
  3. Event-Sourced Runtime v2 横条；
  4. Execution Plane 横条。
  收紧 node text、加带宽/内边距至不重叠、`\small` 统一字号。用户反馈"感觉很堵"已解决。
- **benchmark 构建叙事**：在 `main.tex` §3.2 末尾（tier 列表后、§3.3 前）新增 6 个 `\paragraph`：
  候选池（easy/normal/hard/impossible.md 为唯一事实源）→ 确定性生成器（gen_*_tasks + regenerate-identically 守卫）→ 原子映射 & bond_change 推导（多步档由 registry 相邻步映射 SMILES 差分推导、非手填；fail-loud 校验）→ gold 机理图（节点/边/TS/accessible=false）→ gold 参考计算（`reference_computation` + `selectivity` ΔΔG‡，诚实 `verified/partial/unverified` + `computed_by_us`）→ method whitelist（MACE-OMol25/xTB，fail-closed）+ 四层评分（integrity/self-consistency/GED/accuracy，composite=(0.5·graph+0.2·self-consistency+0.3·accuracy)×binding_quality）。
- **参考答案逐条计算**：明确写出"当前全部 gold 能垒为 literature-anchored、`computed_by_us=false`，正在 run reference-answer campaign 逐条 first-principles 重算并替换"，避免把未核验文献数当 ground truth。这正是用户在文档里强调的基准构建逻辑。
- **同步 working markdown**：`paper/sections/03_benchmarks_and_results.md` §3.2 追加相同构建叙事（markdown 版）。
- **编译验证**：`tectonic main.tex` EXIT=0（仅原有 Underfull hbox 排版警告，无错误）。`main.pdf` 约 166–171 KiB 已更新。main.tex 现约 378 行，sha256 `87c67e39...`——注意：随后又做了一次图微调（band2 三框并排不重叠），最终 sha256 为 `6f8c840d...`（见 git/文件时间戳）。

## 实码核实依据（benchmark 构建叙事）
- `cloudra/benchmark/schema.py`：`TaskSpec`/`GoldSpec`/`ReferenceComputation`（barrier_type Ea/ΔH‡/ΔE‡/ΔG‡、barrier_reference central_complex/reactants、verification verified/partial/unverified/computed_by_us、computed_by_us flag）、`SelectivityReference`（spread_kcal_mol ΔΔG‡）、`MethodPolicy`（allowed_methods + intercept_layers bash/submit_compute_job/qm_input_writer）、`RubricSpec` 四层。
- 生成器：`gen_easy_tasks.py`（`_MAPPED_REACTANTS`/`_BOND_CHANGES` 手填表）、`gen_normal_tasks.py`/`gen_hard_tasks.py`/`gen_impossible_tasks.py`（bond_changes 由 `normal_registry/`/`hard_registry/`/`impossible_registry/` 相邻步映射 SMILES 差分推导，fail-loud 校验）；守卫测试 `tests/test_benchmark.py::test_*_tasks_regenerate_identically`。
- 任务 JSON 事实（`ideapool/tasks/`）：easy 30 / normal 30 / hard 20 / impossible 40（20 题 × I/S 兄弟对照）。各档 gold `computed_by_us` 全部 false；easy `barrier_reference` 28×central_complex；hard 有 11 个 `selectivity` 锚点。

## 叙事定位（用户洞察，上轮已落地）
- 工具从"guard/防火墙"升格为"instrument/科学仪器"（进攻性工程贡献）。
- GraphRAG 从"troubleshooting 加速器"升格为"结构化科学记忆/知识表示"。
- 最终五支柱：任务域 / 证据工程（DAG，最 fancy）/ 工具套件 / GraphRAG / 架构。

## 统领命题（rev. 2026-09-03，已落盘 novelty_statement.md §0.5）
- 冷评审否定原"成本感知/性价比优化"营销式 novelty → 重构为**统领命题：把"结论正确"与"模型聪明"解耦，实现模型无关性**。
- 五支柱 = 实现模型无关性的五个机制，而非并列卖点；成本优势只是架构原则的可测推论/自然结果，非 headline。
- 竞品"通用 agent 取代一切"论断全部建立在**前沿/最贵模型**前提上（ChemCrow=GPT-4、ChemAgents=GPT-4o、Virtual Lab=GPT-4、k-agents=GPT-4o、ChemReasoner=GPT-4o/4o-mini）。

## ⚠️ 用户决定：ablation 暂缓（2026-09-03）
> **"我们组做不起复杂模型的消融，留在 novelty 里等审稿人问了再说吧。"**
- **端到端成本-质量曲线（≥2 模型档 × 各任务域对照）不在本文跑**——现阶段做不起复杂模型消融。
- 处理：作为**可测试论点**留在 novelty（陈述架构原则 + 竞品模型文献佐证），**不下"便宜/性价比领先"未量化结论**；等审稿人质询时再补（届时给出平滑衰减 vs 断崖坍塌）。
- 已在 `novelty_statement.md` §0.5 + §3 写入该边界，避免 overclaim。

## 下一步候选（待用户选择）
- 是否把 tools-as-instruments 提法补进架构图注或 §2.5，使图与五支柱完全对齐。
- 文献空缺：`paper/literature_gap_analysis.md` 仍开放多参考/diradical TS 深检索、SciBench 类评测对照、LLM homogeneous TS search 深检索（用户上轮优先级=novelty，文献列为次优先级）。

## 关键路径
- 论文：`paper/main.tex`（约 378 行）+ `paper/main.pdf`
- 叙事文件：`paper/novelty_statement.md`
- 文献空缺：`paper/literature_gap_analysis.md`