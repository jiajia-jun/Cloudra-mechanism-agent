# gold_compute — 工作进度（Coordinator）

## 用户指令（2026-09-13）
- 下一步：为 benchmark 补齐 gold 参考答案。
- **填充方式：文献调研**（不跑计算）。
- **以 JSON 题（ideapool/tasks/**/*.json）为准**；计划类文档（paper/reference_*.md、旧 README）基本过时。
- 计划与用户说法不一致处，由 Coordinator 改计划。

## 权威产物
- bench 题：`ideapool/tasks/{easy,normal,hard,impossible}/*.json`
- 生成器仍以题源 md 为输入；`tests/test_benchmark.py -k regenerate_identically` 当前**通过**。
  → 填值时同时改题源 md 单元格并重跑生成器，保持 JSON==generator（守卫绿）。
- 生成器：`cloudra/benchmark/gen_{easy,normal,hard}_tasks.py`；能垒解析 `gen_easy_tasks._parse_barrier`。

## 口径
- barrier_reference = central_complex（默认）；非该口径须在 md 括号注明并登记
  `_BARRIER_FRAME_UNVERIFIED`（easy 在 gen_easy_tasks.py，normal 在 gen_normal_tasks.py）。
- barrier_type ∈ Ea/ΔE‡/ΔH‡/ΔG‡，源未注明则 None。
- verification ∈ verified/partial/unverified/已核实存在→verified。

## 缺口清单（JSON 实测）
- normal 缺 barrier（9）：NA2 NA5 NI1 NO3 NR1 NU3 NU5 NU6 NY3
- hard 缺 barrier（2）：HD2 HL1（registry anchor 现为 None，需改 "barrier"）
- hard selectivity（ΔΔ 已有值，7）：HA1 HA6 HE2 HE3 HF1 HG2 HI1 —— 绝对能垒**不在本轮范围**
- easy 待核（10）：C3 D1 D3 D4 F1 G2 G3 M1 M16 M8

## 已派发文献调研（researcher a-3，异步 swarm）
- Swarm A（缺锚点 11 题）group_id = `grp_7d0b3c75236f4aadae3e8e260d4abd1f`，max_concurrency=4
- Swarm B（easy 复核 10 题）group_id = `grp_64873805d57f4a5294d96359f1a4c1f9`，max_concurrency=4
- 每题要求：barrier_kcal_mol / type / frame / DOI / verification / method / justification / proposed_md_cell。

## 下一步
1. 收齐 21 份文献结论（agent_hub 通知 / get_subagent_report(group_id)）。
2. 汇总 → 编辑 `ideapool/reaction_candidates/{normal,hard,easy}.md` 能垒单元格。
3. HD2/HL1：改 `hard_registry/de.py`、`jl.py` 的 anchor None→"barrier"。
4. 重跑生成器 → 断言 regenerate_identically + 相关 benchmark 测试通过。
5. 交付总结（哪些题填了值、哪些仍缺测）。


## 修正（2026-09-13，用户指正）
- **以 JSON 题为准**：`ideapool/tasks/**/*.json` 是权威题面与 gold 机理图；md 池文档的「gold 机理概要」散文列已过时。
- 确认 NA2 确实在 JSON 中（`ideapool/tasks/normal/NA2.json`，丙酮自缩合 aldol → mesityl oxide），
  但其 gold 机理已**重构为 5 个基元步**（E1 烯醇盐生成 / E2 C–C 加成 / E3 烷氧负离子再质子化 / E4 E1cb 去质子 / E5 E1cb 消除），
  md 散文写的 3 步为过时描述。
- 因此文献调研必须锚定 JSON 的逐步机理；RDS 以 JSON gold 图为准，不引用 md 散文步数。
- JSON gold 逐步机理（目标题，已抽取）：
  - NA2: E1 enolate / E2 C–C addition / E3 reprotonation / E4 E1cb deprotonation / E5 E1cb elimination
  - NA5: E1 carbinolamine / E2 iminium / E3 enolization / E4 **RDS C–C formation (enol→iminium)** / E5 deprotonation
  - NI1: E1 carbinolamine / E2 **direct dehydration (RDS)**
  - NO3: E1 carbonyl protonation / E2 peracid addition→Criegee / E3 **1,2-Me migration + O–O cleavage (RDS)** / E4 deprotonation
  - NR1: E1 OH protonation / E2 **concerted semipinacol 1,2-Me shift (RDS)** / E3 deprotonation
  - NU3: E1 **async [2+2] addition→oxaphosphetane** / E2 cycloreversion
  - NU5: E1 PT / E2 isocyanide α-addition→nitrilium / E3 imidate / E4 **Mumm rearrangement**
  - NU6: E1 N attack→zwitterion / E2 **conrotatory 4π closure**
  - NY3: E1 OH⁻ addition→tetrahedral / E2 MeO⁻ elimination / E3 PT
  - HL1: E1 OH protonation / E2 **concerted Beckmann: N–O cleavage + anti-1,2-ethyl migration (RDS)** / E3–E5
  - HD2: E1 **backside SN2 trans-diaxial opening (single step)**


## 删除过时反应候选文档（2026-09-13，用户选项 A）
已删除 8 个无代码读取引用的历史产物（write-only，生成器输出，删后不影响任何测试/管线）：
- hard_tagging.html, hard_tags.json
- impossible_tagging.html, impossible_tags.json
- normal_tagging.html
- normal_essence_mining.json, normal_essence_mining.md
- normal_research_notes.md
保留（生成器输入源，删除会破坏 gen_*_tasks + regenerate_identically 守卫）：
easy.md / normal.md / hard.md / impossible.md
遗留：scripts/{gen_hard_tagging,gen_impossible_tagging,gen_normal_tagging,normal_essence_mining}.py 仍会把这些文档再生出来（未删，用户只要求删文档）。


## 回填完成（2026-09-13）
- 已编辑题源 md 能垒单元格：easy.md（D1/D3/D4/F1/G2/G3/M1/M8/M16）、normal.md（A5/I1/U3/U5/Y3）、hard.md（D2/L1）。
- 代码改动：gen_normal_tasks._BARRIER_FRAME_UNVERIFIED 增 {U3,U5,Y3}（非 central_complex 口径降 unverified）；
  hard_registry/de.py(D2)、jl.py(L1) anchor None→"barrier"。
- 已重跑 gen_{easy,normal,hard}_tasks；JSON 已更新。
- `uv run pytest -q tests/test_benchmark.py` = 113 passed（含 regenerate_identically 守卫）。
- compileall + ruff 干净。
- 新增/修正 gold：normal A5=8.9, I1=26.7, U3=19.1, U5=12.4, Y3=15.5；hard D2=14.3, L1=39.9；
  easy D4 17→13.6, M1 13→18.1, M8 10→10.3, M16 65→71, D1 去 ±2/补 DOI, D3 Ea→ΔH‡, G2/G3 补真实出处, F1 撤销失实引用（→无值）。
- 仍无可靠数值（barrier=null，诚实缺测）：normal NA2, NO3, NU6；NR1（待最新文献结论）；easy F1。
- 仍未在本轮范围：hard 选择性题（HA1/HA6/HE2/HE3/HF1/HG2/HI1）仅保留 ΔΔ 锚点，绝对能垒未补。

- NR1 结论：NO RELIABLE VALUE（相关一手计算文献闭源、摘要无数值）→ barrier 保持 null。所有 21 份文献调研已收齐。
- 最终覆盖：normal 5/9 有值（NA5,I1,U3,U5,Y3），4/9 诚实缺测（NA2,NO3,NR1,NU6）；hard 2/2 有值（D2,L1）；
  easy 19/20 有值（F1 撤销失实引用后缺测）。守卫与全部 benchmark 测试通过。

## 逐边能垒补全战役（2026-09-13，用户升级目标）
要求：gold 机理**每条有效边**都要有参考能垒；来源方案 B：**文献优先，缺口用计算补**（gold 值一律 b3lyp/def2svp；本机 ORCA 6.1.1 就绪）。
- 规模：40 题共 75 条 gold 基元边（69 条有键变化）；初始约 27 有值 → 约 48 待补。
- 逐边文献 swarm：group `grp_fb61a32a712f4ed3a0d3ecaf2ccf5d9b`（19 项）；结果落盘 `gold_compute/edge_barriers/<TASK>.json`。
- 已记录（15 文件）：NA2 NA5 NI1 NO3 NQ1 NR1 NU3 HA1 NY3 NU5 NU6 HA6 HE2 HF1 HI1。
- 仍 running：HG2、HL1(redo)、F1、HE3(redo as_fb24ce939335470a)。
- 全局缺口：多数非 RDS 步（PT/脱水/环化）文献无同底物值 → 需计算；hard 选择性题仅 ΔΔ 锚点，绝对值待计算；easy F1 原引用失实 → 待计算。
- 【口径冲突】HA6 selectivity.spread=2.0 vs 同底物文献 11.3 kcal/mol。
- 【定性方案】hard 选择性题不评 ΔΔ 数值，仅判定优势通道（gold.selectivity.minor_channel）。

## 逐边文献调研收尾 + 计算计划（2026-09-13）
- 19 份逐边文献报告全部收齐，落盘 gold_compute/edge_barriers/*.json（19 文件）。
- 汇总：gold_compute/edge_gap_summary.md（55 边：26 有文献值，29 缺值）。
- **计算战役计划已写**：gold_compute/compute_campaign.md（14 体系/29 边，gold 值一律 b3lyp/def2svp）。
- **用户指示：先写计划，不启动计算。** → 等待用户对计划确认后再开跑。
- 修正 HA1.json：把误置于 edges 的 _note 提为 selectivity_note（非坏边）。


## 2026 逐边能垒重构（用户指令）
- 用户决定：废弃整题 reference_computation.barrier 锚点；能垒只在边上；逐边加权平均评分（越难算准的边权重越小）；不再保留 provenance（DOI/level_of_theory/verification/type/frame）。
- 规格：gold_compute/edge_barrier_refactor_spec.md
- 实施：a-8 env session as_15beb475334f4cde（is_wait=false），按规格重构 schema/生成器/registry/accuracy/barrier_evidence/runner/tests 并重跑 60 JSON。
- 待办：重跑后跑 tests/test_benchmark.py + ruff，接入 26 条逐边文献值，补缺口边。


## 收尾完成（env 收尾会话虽报 failed，实际改动一致且已验收）
- md 过时文字已清理（easy/normal/hard.md 中 barrier_reference/verification/unverified/_BARRIER_FRAME_UNVERIFIED/computed_by_us/central_complex 口径声明与"口径核对登记"节已删/改写；stale grep = 0）。
- 权重按"越难算准越小"落地：frame 不匹配/类似物/部分核实边 weight=0.5（easy D1/D3/D4/C3/G2/G3 等）；分布 = {1.0: 62, 0.5: 28}。
- 全部 60 JSON 经生成器重跑；gold 已无 reference_computation；90 条 gold 边中 45 条带参考值。
- 独立验收：tests/test_benchmark.py 120 passed；4 个 regenerate_identically 守卫 passing；ruff 通过。
- 剩余缺口：约45条边无参考值（多步机理非决速步/质子转移/选择性题），关键边 NA2、HA1/HA6/HE3/HG2；待启动计算战役（gold_compute/compute_campaign.md，b3lyp/def2svp）。

## 批次一交付（2026-09-16）
- 批次一（swarm grp_dcc229bb4140439b9d1d21e6d1949aa8）完成 **5 题 / 8 条缺口边**（F1、NU3、NU6、NY3、HA1），统一 B3LYP-D3(BJ)/def2-SVP（ORCA 6.1.1），ΔE‡ 纯电子能、逐边相对该步起点极小值；全部回填 gold（NU3 由 2 步更正为 3 步），tests 136 passed、ruff 干净。
- 两处 gold 机理更正（NU3 3 步：1.70/55.81/23.76；F1 产物改硼烷-甲氧基加合物 CO[BH3-]）、题面脱敏、ORCA 环境结论、复现命令与证据策略均见 **gold_compute/BATCH1_DELIVERY.md**。
- 遗留：HA1 gold.selectivity.spread 仍 2.0（文献值）与计算 5.72 不一致（已记录未改）；原始 ORCA 日志在 gold_compute/campaign/runs/（.gitignore 排除、不入库）。

