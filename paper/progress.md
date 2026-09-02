# progress.md — novelty 叙事打磨 + benchmark 构建叙事 + 架构图清理（2026-09-02）

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

## 下一步候选（待用户选择）
- 是否把 tools-as-instruments 提法补进架构图注或 §2.5，使图与五支柱完全对齐。
- 文献空缺：`paper/literature_gap_analysis.md` 仍开放多参考/diradical TS 深检索、SciBench 类评测对照、LLM homogeneous TS search 深检索（用户上轮优先级=novelty，文献列为次优先级）。

## 关键路径
- 论文：`paper/main.tex`（约 378 行）+ `paper/main.pdf`
- 叙事文件：`paper/novelty_statement.md`
- 文献空缺：`paper/literature_gap_analysis.md`