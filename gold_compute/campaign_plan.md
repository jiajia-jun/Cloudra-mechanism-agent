# gold 能垒全量自算战役计划

> 状态：**计划稿（待用户确认后执行）**
> 决策依据（用户）：文献锚点审计发现三类系统性失配（参考系 / 能量类型 / 方法级别），
> 不再逐条修补文献值，**全部按任务自身口径重算**。
> 本文取代 `compute_campaign.md` 的「文献优先，缺口用计算补」策略（该文保留为历史记录）。

## 1. 为什么要重算（审计结论）

`gold` 边的 `barrier_kcal_mol` 目前全部是文献转录值，与任务强制口径不一致的三类：

| 失配类型 | 代表 | 说明 |
|---|---|---|
| 参考系不同 | **E1 / C3** | 任务是「相对该步起点极小值（双分子步＝反应物络合物）」，锚点是「相对分离反应物渐近线」；E1 的离子-偶极阱深约 18 kcal，按协议算出的值与 gold 差一个阱深 |
| 模型化学不同 | **NI1 / NR1 / HL1 / HD2** | 锚点来自 G2(MP2,SVP)＋双水辅助、H₃O⁺(H₂O)ₙ 微溶剂化簇、微溶剂化 Ea；任务强制气相/隐式溶剂 B3LYP/def2-SVP，原则上够不到 |
| 能量类型不同 | normal 6 条带值边、HH1、P2/P3/L1/L2/X1/M1/M8 | 锚点是溶液 ΔG‡ / 气相 ΔH‡ / Ea / 实验区间值，任务评的是电子能 ΔE‡ |

另有：锚点取自底物类似物（NU3/NA2/NA5）、方法未确认或回忆值（NQ1）、题源 md 与 registry 已脱节（NO3/NU5）。

## 2. 范围（实测）

| 档 | 题 | gold 边 | 本战役重算边 |
|---|---|---|---|
| easy | 20 | 20 | 20（F1 现为 null，一并补） |
| normal | 10 | 32 | 32（19 null + 13 待替换） |
| hard | 10 | 23 | 23（含 7 道选择性题的成对 TS，ΔΔ 以计算裁决） |
| impossible | 20 | 15 | 0（I 题不评数值；S 题锚点为实验性质值，另案） |

**合计 75 条边。**

## 3. 统一口径（黄金标准）

- 方法：**B3LYP-D3(BJ)/def2-SVP**（ORCA 写作 `! B3LYP D3BJ def2-SVP def2/J RIJCOSX`；
  用户口径：本基准的 B3LYP 一律带 D3(BJ) 色散），与 `method_policy.allowed_methods`
  的 `b3lyp/def2svp` 条目对应；能量取 ORCA 最终单点电子能。
  任务 query 的方法条款已同步渲染为 "B3LYP-D3(BJ)/def2-SVP"（`query_builder.py`），
  并重跑四个生成器——agent 侧据此写输入，避免"裸 B3LYP vs 带色散 gold"的口径错位。
- 能垒：**ΔE‡（电子能差，无 ZPE/热校正），相对该步自身起点极小值**（任务 query 明文口径）。
- 溶剂：逐题按 query 显式要求（气相题气相；要求隐式溶剂者用 CPCM + 对应溶剂名），在 campaign 配置里**逐题钉死**，不猜；15 题的 conditions 文本提及溶剂/液相，需逐条确认。
- 每条边必须齐备：起点/终点极小值（freq 无虚频）、TS 日志（**恰 1 个虚频**）、IRC 双侧、`irc_path.assign_irc_endpoints` 区间证明通过。
- 近无能垒质子转移步（计划内已知：NR1_E1/E3、HL1_E1/E4、NY3_E3、NU5_E1、NO3_E1/E4）：约束扫描确认无垒 → 记 ≈0 并附扫描证据；**不虚构活化能**。
- **fail-loud**：不收敛 / 多于 1 个虚频 / IRC 不通 / SCF 失败 → 该边 `barrier_kcal_mol=null` + 失败原因入库，绝不用文献值或猜测填充。

## 4. 关键设计：从 atom-mapped 反应物生成全通路连通性

50 道题（easy/normal/hard 全部）的 query 都带 **Atom-mapped reactant SMILES**，且 `bond_changes` 用同一套 map 号——这是本战役的地基，避免一切 2D↔3D 原子对应问题：

1. 从 query 的映射 SMILES 构建起点分子（保留显式 H 与 map 号 → RDKit atom idx 一一对应）；
2. 沿 gold 通路**逐边累积施加 `bond_changes`**（break 删键、form 加键/提键级）→ 得到每个物种节点在同一原子序号下的连通性；
   - 顺带校验 gold 图内部自洽：break 的键必须存在、form 不产生超价（不满足即 fail-loud 报题源 bug）；
3. 每个节点：按编辑后的连通性 RDKit 嵌入初始坐标 → **xtb(gfn2) 优化**（按题电荷/多重度/溶剂）→ 极小值几何与能量；
4. TS 初猜：同序号端点 → **IDPP 插值**取能量/几何峰值帧（`ts_guess` 纯函数），质子转移/消除步辅以**约束扫描**（`ts_guess` scan 路径）；
5. TS 精修：ORCA `! OptTS Freq` (CalcFC 起步)；
6. IRC 双侧 → 端点续优化 → 区间证明；
7. 出值：`E(TS) − E(该步起点极小值)`，Hartree × 627.5095。

**已知题源 bug（执行前先修）**：`E1` 的 gold 产物节点 `C=C.F.[Cl-]` 化学上应为 HF（`C=C.F[H].[Cl-]` 或等价），现写法是 F 自由基；query 文本同错。同类问题在执行中逐题检查并列出清单，交回题库维护。

## 5. 实施

### 5.1 代码（新建 `gold_compute/campaign/`）

| 文件 | 职责 |
|---|---|
| `model.py` | `EdgeJob` 数据类：task/edge/节点映射 SMILES/电荷/多重度/溶剂/`bond_changes` |
| `config.py` | 逐题运行配置（方法行、溶剂、特殊处理与已知无垒步清单） |
| `build.py` | 映射 SMILES → 连通性累积编辑 → 嵌入 → xtb 优化（端点极小值） |
| `pipeline.py` | 单边流水线（guessing → OptTS → IRC → 验证 → 出值），**断点续跑**（`state.json` + flock） |
| `runner.py` | CLI：`--task/--edge`、`--batch 1|2`、`--stage {min,guess,optts,irc,validate,value}`、`--workers N` |
| `summary.py` | 汇总 `summary.md`：逐边值/方法/溶剂/frame/验证状态/与旧文献值差异 |

- 复用而非新写：`ts_guess` 的插值/扫描纯函数、`orca_frames`/`gaussian_frames` 解析、`irc_path` 区间证明、`run_dirs` 的目录与进程组管理。
- 运行目录 `gold_compute/campaign/runs/<TASK>/<EDGE>/<n>/`，日志命名沿用 `calc-<id>.out.log` 以复用解析器。
- 并发：18 核机器，ORCA 每作业 4-6 核，默认 **2 作业并行**（可配），不与日常任务抢满。

### 5.2 分两批执行（用户口径）

**批一 — easy + normal（52 边）**

| 阶段 | 内容 | 目的 |
|---|---|---|
| 批一·Wave 0 | E1（阴离子 E2，参考系差最狠）、NI1_E2（案例题）、L1（周环）、HA1（选择性成对 TS，借 hard 题验成对链路） | 全链路跑通 + 验收口径 |
| 批一·Wave 1 | easy 20 边 | 单步、体系小，产量最高 |
| 批一·Wave 2 | normal 32 边 | 多步 + 离子体系（NA2/NY3 −1；NA5/NO3/NR1/HL1 +1） |

**批间闸门（批一结束、批二开始前必须完成）**：
1. 批一 52 条边的产物 JSON 齐全（含失败边的 null + 原因）；
2. 回填 registry/题源 md → 重跑 `gen_easy_tasks`/`gen_normal_tasks` → `pytest tests/test_benchmark.py` 生成器守卫绿；
3. 用批一的新锚点复评历史批次（runs 表已有的 easy/normal 记录），出 accuracy 前后对照，确认新锚点在实际交付上可判分；
4. 输出批一 `summary.md` 与题库 bug 清单。

**批二 — hard（23 边）**

| 阶段 | 内容 | 目的 |
|---|---|---|
| 批二·Wave 3a | 逐边评分题 HD2 / HH1 / HL1（含 hard 的两条严重失配） | 先把真正进 accuracy 的边算出来 |
| 批二·Wave 3b | 选择性题成对 TS：HA1 / HA6 / HE2 / HE3 / HF1 / HG2 / HI1（ΔΔ 以计算裁决，HA6 的 2.0 vs 11.3 冲突一并结案） | 定性评分 + 完整能垒数据 |
| 批二·Wave 3c | HE3（~30 原子）单独安排，可跨批次尾 | 大体系机时 |

批二同样以「回填 → 重跑 `gen_hard_tasks` → 守卫绿」收尾。

### 5.3 验收闸门（每批共同适用）

1. 逐边：freq 恰 1 虚频 + IRC 区间证明 + 两端极小值无虚频；
2. 交叉校验：仅在口径一致（同 frame、同类型、同底物）时与文献值做 ±3 kcal 合理性对照，不一致只报差异、不自动改值；
3. 回填：`edge_barriers/computed/<TASK>.json` → registry/题源 md → 重跑 `gen_*_tasks.py` → `uv run pytest -q tests/test_benchmark.py`（`test_*_tasks_regenerate_identically` 必须绿）。

### 5.4 预算与风险

- 单边 5-10 个 ORCA 作业（端点 opt+freq ×2、TS 尝试 1-3、TS freq、IRC 1-2）；17 原子体系单作业约 20-60 min。**批一 52 边 ≈ 350-550 作业**（2-3 并行约 2-4 天）；**批二 23 边 ≈ 150-250 作业**（含 HE3 大体系，约 1-2 天）。
- 风险：阴阳离子 SCF 收敛（NA2/NY3/NA5/NO3/NR1/HL1）、大体系成本（HE3）、TS 初猜失败（有界重试后落 null）。
- 全部产物 append-only：失败的尝试同样保留（与 benchmark 沙箱纪律一致），便于复盘。

## 6. 交付物（分批各一套）

1. `gold_compute/edge_barriers/computed/<TASK>.json`（逐边：值/type/frame/method/溶剂/证据路径/验证状态）；
2. `gold_compute/campaign/summary_batch{1,2}.md`（汇总 + 与旧锚点差异对照表 + 失败边清单）；
3. 题源 md 与 registry 回填、任务 JSON 重生成、生成器守卫绿（分批各做一次）；
4. 题库 bug 清单（如 E1 产物 SMILES）。

## 7. 待确认

1. 分批口径是否照本文 §5.2（批一 easy+normal 52 边 → 批间闸门 → 批二 hard 23 边）执行？
2. 溶剂题（15 题）的隐式溶剂模型与溶剂名是否按 query 文本逐题钉死（推荐）？
3. HE3（~30 原子）是否接受其单边可能数小时的机时，或先跳过、后续单独安排？
4. **D3(BJ) 是否要硬性拦截**：`method_policy` 的白名单是方法族粒度（`b3lyp` + `def2svp`），
   裸 `! B3LYP def2-SVP`（无 D3BJ）目前仍能通过拦截——query 已写明 D3(BJ)，但
   agent 若漏写色散，其能量与 gold 会差几 kcal。是否要在拦截层 fail-closed
   （请求 b3lyp 家族时缺 `d3bj` 关键字即拒），需用户拍板。
