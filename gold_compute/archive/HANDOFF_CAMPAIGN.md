# gold 逐边能垒战役 — 完整交接（campaign handoff）

更新：2026-09-18（Coordinator）。本文件是给接手方/师兄对齐的**自包含交接**。

## 1. 目标与范围
- 目标：为本 benchmark 的 gold 机理**全部自算**能垒——每题把 gold 机理图的**每个物种极小值（起点复合物/中间体/产物）+ 每条基元步的过渡态**用统一口径算出并给值，替代原文献锚点。
- 已完成/在算：batch-1（F1/HA1/NU6/NU3/NY3）+ batch-2（NU5/HA6/HL1/NA5/HG2），共 10 题。
- 未派：NA2/NO3/NR1/NQ1/HE3 及 easy 20 题（用户尚未要求开启）。

## 2. 黄金口径（必须遵守）
- 方法：**B3LYP-D3(BJ)/def2-SVP**，ORCA 6.1.1，route `! B3LYP D3BJ def2-SVP def2/J RIJCOSX`（+ 题面指定隐式溶剂）。
- 能量：**ΔE‡ = E(TS) − E(该步起点极小值)，纯电子能，无 ZPE/热校正**，逐边相对自身起点。
- 溶剂：严格按题面 conditions（具名溶剂→CPCM(该溶剂)；未具名→气相）。
- 本机约束：**nproc=1**（Mac 上 ORCA 并行解析 Hessian 段 SEGFAULT）；新作业 **memory_mb=4000**（总量 4–8GB 口径）。
- **验收**：极小值 opt+freq **0 虚频**；TS **恰 1 虚频**（只认 ORCA **最终** VIBRATIONAL 块）；虚模位移须落在成/断键重原子；IRC（或 IRC 最外侧帧独立 opt）连通两端极小值；鞍点几何不是产物。

### 硬性禁令（用户多次强调）
- **绝不用约束扫描的最大值冒充能垒**。扫描最大值只能当 OptTS 种子/上界。
- **不用文献值回填**（原文献锚点与强制口径不一致，本战役即其替代）。
- 穷尽路线仍无真鞍点的边：记 `no_first_order_saddle_located` + 列出试过的全部路线；只有沿真实反应坐标单调下降/自发完成才记 0（无垒）+证据。
- **机理不对就纠正**：若声明物种在模型 PES 上不是极小值、或声明的步端点不存在，按真实 PES 重定义物种与基元步并记录（这是交付，不是失败）。

## 3. 逐题逐边结果（当前）
> 值单位 kcal/mol；"真TS"= 恰 1 虚频 + 连通；证据=gold_compute/campaign/runs/<TASK>/…

| 题 | 溶剂 | 边 | 值 | 判定 |
|---|---|---|---|---|
| F1 | 气相 | F1_E1 | 39.36 | verified（1 虚频 −879.9；产物=硼烷-甲氧基加合物） |
| HA1 | 气相 | E1/EM1 | 33.04 / 38.76 | verified（成对 TS，ΔΔ=5.72 方向同 gold） |
| NU6 | CPCM(DCM) | E1/E2 | 2.66 / 15.72 | verified（RDS=E2 关环） |
| NU3 | 气相 | E1 / E2a / E2b | 1.70 / 55.81 / 23.76 | verified |
| NY3 | CPCM(water) | E2 / E3 | 12.5 / 0 | verified（E3 无垒） |
| NU5 | CPCM(DCM) | E1 / E2 / E3 / E4 | **0** / 8.20 / 0 / 31.7 | E1=无垒(原 11.9 扫描值作废为局部极小假象)；E2 真TS(严格);E3 无垒;E4 端点证连通 |
| HA6 | 气相 | E1 / EM1 | 31.24 / 42.31 | verified（ΔΔ=11.06 有利外向；**证伪 gold 记的 2.0，与文献 11.3 一致**） |
| HL1 | 气相 | e1 / e2 / e3 / e5 | **0** / 23.13 / **unresolved** / **unresolved** | e2 真 TS(−304.17，N–O 断+anti-1,2-乙基迁移)；e3/e5 未定位到一阶鞍点(需≥3 耦合坐标，无扫描充数) |
| NA5 | CPCM(water) | E1 / E2 / E3 / E4 / E5 | null / 13.94 / **69.94** / 3.37 / null | E3=真鞍点(烯醇化,−2140.76,双向 IRC 连通)但属"无碱 1,3-H 迁移"模型、值偏高已 flag；E2=真鞍点(−283.64,H3O+→O4 质子转移)但连通性部分；E4=真鞍点(−363.63,C1–C10 成键)但 IRC 两端都回 I3→非生产性;E1/E5 未定位 |
| HG2 | 气相 | E1 / EM1 | 29.67 / 26.39 | verified（chair→anti、boat→syn；**gold 的 chair→syn 配对反置**，文献裁决后按计算纠正） |

## 4. 已独立复核（Coordinator 亲验）
- 8 条已交付真 TS 的 ORCA 日志，用 log_parser 只读**最终** VIBRATIONAL 块：HA6_E1(−520.96)/HA6_EM1(−631.01)/HL1_e2(−304.17)/NU5_E2(−351.30)/NU5_E4(−153.44)/NA5_E3(−2140.76)/HG2_E1(−355.71)/HG2_EM1(−402.62) —— **全部恰 1 虚频 + opt 收敛 + 正常终止**。

## 5. 已知问题 / 缺口
- **HL1**：e3(水加成 I2→I4)、e5(I4→P 互变) 未定位到一阶鞍点（I2 里两水 O···O=4.29 Å，需≥3 耦合坐标）。e2 的 IRC 连通性仅部分成立（后向端未回 I1）。
- **NA5（已定稿）**：E3=69.94 verified；E2=13.94 ts_located（连通性部分）；E4=3.37 ts_located（非生产性，连通未证）；E1/E5 null。E3 的模型不匹配（应碱催化）已 flag。
- **HG2**：gold 的 chair/boat ↔ syn/anti 配对反置，已按文献（Vittorelli/Schmid 1968/1975；Ireland 规则；Khaledy-Houk 2003；Gül-Houk 2010）纠正。
- 部分 JSON 存在字段重复/未同步（HL1 的 corrected_mechanism_graph 与顶层 edges 两套；NA5 已修；HG2_EM1 ts_log 跨目录）。

## 6. 工程坑（复用须知）
- `ts_prepare` 持久进程在 **guess 阶段** 常硬阻塞（xTB MTD 不闭合/artifact 不全），无自动 fallback（issue #39）→ 转人工路线。
- ORCA `%geom Scan` 松弛扫描在本机**崩溃**（SHARK/PROPERTIES 错，与 nproc 无关）→ 用 `%geom Constraints` 逐点约束优化。
- ORCA `%geom Constraints` 原子索引是 **0-based**（坐标块 1-based）。
- 松散多分子/离子-偶极体系的 1 虚频鞍点可能是**旁观软模**（虚模几乎全在单氢上）→ 必须核虚模位移落在反应重原子。
- 可用的 TS 种子法（有效）：先用手动几何操作/约束把关键坐标（成键键长、进攻角、**转移质子的桥位**）摆到鞍点附近，再放**无约束 OptTS（带初始 Hessian）**。NA5 的 E3/E4 即此法成功。

## 7. 回填流程（改源→重跑生成器→守卫绿；禁手改 JSON）
1. 改题源：`ideapool/reaction_candidates/{easy,normal,hard}.md`（easy 的 F1）、`cloudra/benchmark/normal_registry/{ru,yo,...}.py`、`cloudra/benchmark/hard_registry/{ab,...}.py`——把对应 step 的 barrier 写入。
2. 重跑生成器：`gen_easy_tasks` / `gen_normal_tasks` / `gen_hard_tasks`。
3. 守卫：`uv run pytest -q tests/test_benchmark.py` 必须绿。
4. 刷新审核树 `gold_compute/review/`（a-8 已建：INDEX.md + 每题 README + hardlink 证据）。

## 8. 产物与证据路径
- 逐题边界值：`gold_compute/edge_barriers/computed/<TASK>.json`（含每边 value/type/validation/ts_log/irc_log/routes_tried + 物种极小值 + mechanism_graph）。
- 证据日志：`gold_compute/campaign/runs/<TASK>/…/.cloudra/calc-*.out.log`。
- 审核树：`gold_compute/review/`（INDEX.md + 每题 README）。
- 进度台账：`gold_compute/campaign/progress.md`；计划：`campaign_plan.md`、`batch2_selection.md`、`BATCH2_FINAL.md`。

## 9. 回填状态（2026-09-18 完成）
- **逐边能垒已回填到题源**（easy.md / normal_registry / hard_registry 的 step barrier），重跑 gen_easy/normal/hard_tasks，`uv run pytest tests/test_benchmark.py -q` = **136 passed**（impossible 22 passed）。未手改生成的 JSON。
- **HG2 选择性配对已纠正**：gold 现为 chair→anti favored/major(26.39)、boat→syn minor(29.67)、spread 3.28；生成器加向后兼容可选键（其余 9 个 hard 题逐字节不变）。hard.md G2 散文同步。
- HL1 anchor（hard.md）39.9→23.13（生成器强制 = 该题逐边最大；文献值括注保留）。
- 交接记录：[`HANDOFF_backfill.md`](HANDOFF_backfill.md)、[`HANDOFF_hg2_pairing.md`](HANDOFF_hg2_pairing.md)（本归档目录）。

## 10. 待办
- 若需，刷新审核树 `gold_compute/review/`（其内容基于更新前的 JSON）。
- 下一批（NA2/NO3/NR1/NQ1/HE3 及 easy 20）待用户开启。
- 用户确认是否开启下一批（NA2/NO3/NR1/NQ1/HE3）与 easy 20 题。
- 回填 gold + 刷新审核树（待用户拍板）。
