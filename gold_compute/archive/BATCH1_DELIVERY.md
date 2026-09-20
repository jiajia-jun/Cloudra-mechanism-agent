# gold_compute 批次一交付文档（BATCH1_DELIVERY）

> 面向项目成员的中文交付说明。本文所有数字均取自下列来源文件，可逐条回溯：
> - 派发台账：`gold_compute/campaign/dispatch_ledger.md`
> - 逐边计算结果：`gold_compute/edge_barriers/computed/{F1,NU3,NU6,NY3,HA1}.json`
> - 回填后的题库 gold：`ideapool/tasks/easy/F1.json`、`ideapool/tasks/normal/{NU3,NU6,NY3}.json`、`ideapool/tasks/hard/HA1.json`
> - 环境诊断报告：`gold_compute/campaign/_orca_env_probe/REPORT_orca_crash_diagnosis.md`
>
> 交付日期：2026-09-16。文中凡来源未给出的字段，一律写「见台账」，不作推测。

---

## 1. 概述

- **覆盖范围**：批次一（swarm `group_id = grp_dcc229bb4140439b9d1d21e6d1949aa8`）覆盖 **5 题 / 8 条缺口边**——F1（easy）、NU3 / NU6 / NY3（normal）、HA1（hard）。其中 NU3 在计算后由 2 步 gold 更正为 3 步（见 §3a），故计算覆盖 8 条缺口边；回填后这 5 题的 gold 合计 11 条边（含原有文献值边 NY3_E1 = 15.5，非本批计算）。
- **统一方法**：**B3LYP-D3(BJ)/def2-SVP**，引擎 **ORCA 6.1.1**（ORCA 路线 `! B3LYP D3BJ def2-SVP def2/J RIJCOSX`）。方法口径由题库 `method_policy.allowed_methods`（`xtb` / `b3lyp/def2svp`）限定。
- **能量口径**：**ΔE‡ = 纯电子能**（无 ZPE、无热校正），**逐边相对该步自身起点极小值**（双分子步的起点为反应物复合物 RC，单分子步的起点为该步反应物极小值）。
- **溶剂**：按题面 `conditions` 原样——具名溶剂走 **CPCM**，`gas phase` 走气相。
- **验收口径**：端点 opt+freq 0 虚频；TS 恰 1 虚频；IRC 双向落回两端极小值；fail-loud。
- **gold 回填**：改题源 md / registry 源后再重跑生成器，**禁止手改 JSON**（见 §6）。台账「批次一交付完成」一节记录回填后 `tests/test_benchmark.py` **136 passed**、ruff 干净。

---

## 2. 逐边结果表

数值取自 `gold_compute/edge_barriers/computed/*.json`；TS 虚频列除 HA1 外均取自同批 computed JSON。证据 log 为绝对路径，根目录 `gold_compute/campaign/runs/`。

| 题 | 边 | 值 (kcal/mol) | 溶剂 | 验证状态 | TS 虚频 (cm⁻¹) | 证据 log（TS / IRC） |
|---|---|---|---|---|---|---|
| F1 | F1_E1 | 39.36 | 气相 | verified | −879.87 | TS `…/F1/F1_E1/16/ts06/calc-408.out.log`；IRC `…/F1/F1_E1/16/ts06/calc-411.out.log` |
| NU3 | NU3_E1 | 1.70 | 气相 | verified | −279.0 | TS `…/NU3/NU3_E1/1/calc-382.out.log`；IRC `…/NU3/NU3_E1/1/calc-387.out.log` |
| NU3 | NU3_E2a | 55.81 | 气相 | verified | −1021.6 | TS `…/NU3/NU3_E1/1/calc-418.out.log`；IRC `…/NU3/NU3_E1/1/calc-422.out.log` |
| NU3 | NU3_E2b | 23.76 | 气相 | verified | −624.8 | TS `…/NU3/NU3_E1/1/calc-424.out.log`；IRC `…/NU3/NU3_E1/1/calc-425.out.log` |
| NU6 | NU6_E1 | 2.66 | CPCM(DCM) | verified | −159.63 | TS `…/NU6/E1_ts/2/.cloudra/calc-355.out.log`；IRC `…/NU6/E1_ts/2/.cloudra/calc-366.out.log` |
| NU6 | NU6_E2 | 15.72 | CPCM(DCM) | verified | −526.2 | TS `…/NU6/E2_ts/2/.cloudra/calc-367.out.log`；IRC `…/NU6/E2_ts/2/.cloudra/calc-383.out.log` |
| NY3 | NY3_E2 | 12.5 | CPCM(water) | verified | −159.06 | TS `…/NY3/E2/1/.cloudra/calc-365.out.log`；IRC `…/NY3/E2/1/.cloudra/calc-384.out.log` |
| NY3 | NY3_E3 | 0.0 | CPCM(water) | verified | 无 TS（0 虚频，无垒） | 约束扫描 `…/NY3/E3/1/.cloudra/calc-351.out.log` |
| HA1 | HA1_E1 | 33.04 | 气相 | verified | −632.90 | TS `…/HA1/HA1_E1/1/.cloudra/calc-350.out.log`；IRC `…/HA1/HA1_E1/1/.cloudra/calc-363.out.log` |
| HA1 | HA1_EM1 | 38.76 | 气相 | verified | −682.02 | TS `…/HA1/HA1_EM1/1/.cloudra/calc-353.out.log`；IRC `…/HA1/HA1_EM1/1/.cloudra/calc-364.out.log` |

路径前缀 `…/` = `/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/gold_compute/campaign/runs/`（完整绝对路径见对应 computed JSON 的 `ts_log` / `irc_log` 字段）。

**读表说明（均可回溯）**

- **值 vs gold 回填**：F1 计算值 39.36，题库 `F1.json` 与台账回填表记 39.4（四舍五入）；NU3/NU6/NY3/HA1 计算值与题库 gold 逐条一致（1.7 / 55.81 / 23.76；2.66 / 15.72；12.5 / 0.0；33.04 / 38.76）。
- **边名映射**：computed `NU3.json` 用 `NU3_E1 / NU3_E2a / NU3_E2b`，题库 `NU3.json` 回填后用 `NU3_E1 / NU3_E2 / NU3_E3`——旧的单一 `NU3_E2` 被拆为 `E2a`（adduct→oxaphosphetane）+`E2b`（oxaphosphetane→products）。三边在题库中 `weight` 均为 **1.0**。
- **HA1 虚频来源**：`computed/HA1.json` 只记 `n_imag = 1`，未记具体的虚频波数；上表 HA1 的 −632.90 / −682.02 取自台账「HA1 — 已完成」一节（`TS -632.90 cm-1` / `TS -682.02 cm-1`）。其余各边虚频取自 computed JSON。
- **NU3 的 IRC caveat**：三条 NU3 边各**有一个方向撞 `%irc MaxIter=30` 被截断**，并非双向完全收敛（`NU3.json` 的 `irc_convergence_note` 明确不表述「双向收敛」）。E1 截断侧（adduct 侧）外侧帧独立优化后落到 adduct min（低 3.17 kcal）；E2a 截断侧（adduct 侧）外侧帧比 adduct min 高 2.76 kcal；E2b 截断侧（products 侧）外侧帧为 C2H4…H3P=O 接触对，比分离产物低 3.57 kcal。strict 复核 **PASS**（strict 明文允许部分 IRC）。
- **NY3_E3** 为无垒步（约束扫描 O3–H5 0.98→2.10 Å 单调下降、无内顶点；无约束优化自发质子转移），故按 **0.0** 记账、无 TS 虚频。
- **RDS**：NU6 两式中 NU6_E2（15.72）为决速步；NU3 以 NU3_E2a（55.81）为最高垒。

---

## 3. 两处 gold 机理更正

### 3a. NU3——原 2 步 gold 不成立，更正为 3 步

**原判**：gold 原为 2 步——旧 NU3_E1（RC→氧磷杂环丁烷）与旧 NU3_E2（氧磷杂环丁烷→产物）。计算发现旧 NU3_E2 并**非基元步**，且在本题模型 PES 上「RC↔氧磷杂环丁烷」无独立关环鞍点（定向搜索收敛回同一 C–C 偶联鞍点），故原 2 步机理不成立。

**更正后（3 步，全部自算，无文献替代）**：

| 步 | 边 | 反应 | ΔE‡ (kcal/mol) |
|---|---|---|---|
| 1 | NU3_E1 | RC → 加成物 I1（H2P–CH2–CH2–OH） | 1.70 |
| 2 | NU3_E2a | 加成物 I1 → 氧磷杂环丁烷 I2（C1C[PH3]O1） | 55.81 |
| 3 | NU3_E2b | 氧磷杂环丁烷 I2 → 产物（C2H4 + H3P=O） | 23.76 |

**能量梯（相对 RC，kcal/mol）**：RC 0 → 加成物 −59.45 → 氧磷杂环丁烷 −27.95 → 产物 −32.21
（对应极小值电子能 Ha：RC −496.541090；adduct −496.635831；oxaphosphetane −496.585627；products −496.592417 = −78.477468 + −418.114949）。

**热力学闭合校验**：step2 热力学差 (+31.50) + step3 热力学差 (−4.26) = **+27.24** kcal，与 **E(products) − E(adduct) = −32.21 − (−59.45) = +27.24** 精确吻合（`NU3.json` `closure_check`：EXACT）。

**要点与来源改动**：

- 加成物 I1 由「氧磷杂环丁烷」更正为**真实加成物 H2P–CH2–CH2–OH**（canonical SMILES `OCCP`，题库 node `NU3_I1`）；氧磷杂环丁烷成为**另一个独立极小值**（题库 node `NU3_I2`，SMILES `C1C[PH3]O1`），由 step2 的协同「O→P 质子转移 + P–O 关环」步到达（TS P2–O9 = 2.277 Å，恰 1 虚频 −1021.6 cm⁻¹）。
- **原题面里的 Wittig / oxaphosphetane 诱导已删**：题名由 `Wittig reaction simplified model: H3P=CH2 …` 改为 `H3P=CH2 ylide + formaldehyde -> ethylene + H3P=O`；并去掉题名中的 `(via oxaphosphetane)`（query 不再出现 `Wittig`）。`mapped_reactants` 增加显式映射氢 `[CH2-:1][PH2+:2][H:5].[CH2:3]=[O:4]`，使 P–H→O 质子转移可被 `bond_changes` 记录。
- **旧 NU3_E2 的文献值 19.1（氧磷杂环丁烷环消除）已不适用**，改由自算 E2a/E2b 取代（其中 E2b 仍注明与文献 Me3P 类似物 19.1 类比，但值本身为自算）。
- **措辞更正**：台账 2026-09-16 曾误要求把 IRC 补跑到收敛；用户指出 strict 明文「IRC 无需收敛」，已叫停，仅做措辞修正（`NU3.json` 的 `irc_convergence_note` + 逐边 `irc_detail`）。

### 3b. F1——产物节点更正为硼烷-甲氧基配位加合物

- **原判**：gold 机理图的产物节点声明为**分离物种** `C[O-].B`。
- **更正**：产物节点改为**硼烷-甲氧基配位加合物** `CO[BH3-]`（CH3–O–BH3⁻）；`bond_changes` **新增 B–O 成键**——`break [[1,2],[3,4]]` / `form [[2,3],[1,4]]`，其中新增的 `[1,4]` 即 **B1–O4** 成键；步型补为「B–H 断裂 + C–H 生成 与 B–O 配位成键耦合、单步异步 TS」。
- **计算佐证**（`computed/F1.json`）：真实产物极小值为 CH3–O–BH3⁻ 加合物（B–O = 1.49 Å），比 RC **低 30.1 kcal**（反应放热）；此更正**不影响**所报 ΔE‡（其参考基准为 RC）。加合物 SMILES 即 `CO[BH3-]`。
- **连带效应**：题库 `F1.json` 现 `products = ["CO[BH3-]"]`、gold `F1_P` = `CO[BH3-]`；台账记录「F1.json 里关于『gold 产物节点为分离 C[O-].B』的 caveat 已因题面修正而失效」。
- 备注（台账）：E1 产物 F（应为 HF）存在同类化学错误已指出，但按用户指令**本轮只改硼题**，未动。

---

## 4. 题面脱敏（去「泄漏答案型」诱导）

为消除题名对答案的硬泄漏，**全库 23 个题名**去掉了硬泄漏字眼（改动的是生成器/registry 的 `name_en` 源，未手改 JSON；重跑 `gen_{easy,normal,hard}_tasks`，`tests exit=0`，ruff 干净）。台账「硬泄漏去除清单」逐条如下：

- **NY3**：`Ester saponification (BAC2): …` → `Ester saponification: …`
- **NU3**：`… -> ethylene + H3P=O (via oxaphosphetane)` → 去掉 `(via oxaphosphetane)`
- **NQ1**：去掉 `(via ortho-cyclohexadienone)`
- **L1**：`conrotatory ring opening` → `ring opening`；**L2**：`disrotatory ring closure` → `ring closure`
- **HA1 / HA6**：`…conrotatory…torquoselectivity` → `…ring opening: determine the stereochemical outcome`
- **C3**：`retention-pathway mechanism (vs backside SN2)` → `F- + CH3Cl: determine the stereochemical course (retention vs inversion)`
- **D3**：`(endo, self DA)` → `(self Diels-Alder)`；**D4**：`DA (heteroatom dienophile)` → `Diels-Alder`
- **E1**：`E2 elimination` → `elimination`
- **P2**：`[1,5]-H shift` → `degenerate H shift`；**P3**：`Claisen ([3,3])` → `Claisen`
- **X1**：去掉 `(decarboxylative extrusion)`；**G2**：去掉 `(double H transfer)`；**M1**：`atropisomer rotation` → `aryl-aryl rotation`
- **HD2**：`SN2 epoxide opening` → `epoxide opening`；**HE2**：`axial vs equatorial attack on a conformationally locked ketone` → `determine the stereochemical outcome`
- **HE3**：`enantioface selection` → `addition`；**HF1 / HG2 / HI1**：`diastereoselectivity / enantioselectivity / preferred TS geometry` → `stereochemical outcome`
- **HH1**：`1,1'-binaphthyl atropisomerization (thermal racemization)` → `1,1'-binaphthyl thermal racemization`

**保留（按尺度 a）**：通用反应名——Diels-Alder / Claisen / Wittig / Staudinger / Passerini / Mannich / Baeyer-Villiger / pinacol / Beckmann / aldol / ene 等；以及 D1 的 `(parent DA)`、HL1 的 `which group migrates`（即为题面问题本身）、NU6 的 `Staudinger beta-lactam synthesis`。

**遗留**：`easy.md / normal.md / hard.md` 的**文档性题名列**未同步（该列不参与生成/题面，仅文档）。

> 计数已核对：实际改名 **23** 个题号（easy 11 / normal 3 / hard 9），与上表逐条一致；此前台账标题写的「24」为笔误。

---

## 5. 环境结论摘要

来源：`gold_compute/campaign/_orca_env_probe/REPORT_orca_crash_diagnosis.md`（env 诊断，2026-09-16）。

- **症状 B（松弛扫描 `%geom Scan` 崩溃）= ORCA 自身缺陷，nproc 无关，避开即可。** 根因定位为 ORCA 松弛扫描驱动在**某个扫描点优化撞 MaxIter** 时的内部错误：即使该点已写出 `.NNN.xyz`，仍报 `Failed to read input file (.SHARKINP.tmp)` 并在 `PROPERTIES` 阶段 error termination；探针 10 s 内**确定性复现**，`nproc=4` 与 `nproc=1` 报文链完全一致（纯 `! OPT` 同 MaxIter 只告警、正常结束；扫描点能收敛则正常）。**规避**：不用 `%geom Scan`，改用约束优化 / 双端 NEB-TS / OptTS（F1 即走 OptTS+NEB-TS）。无任何环境变量能修复。
- **症状 A（并行崩溃）= arm64 自装构建错位导致的偶发问题，环境调参不能根治。** 磁盘上有 5 类崩溃签名（含 `orca_scfgrad_mpi`/`orca_util_mpi` 的 PAL_Abort、serial `VIB_PrintSpectra` 的 SIGSEGV、OpenMPI HNP 崩溃），但约 69 次有效探针运行**零复现**；构建时间错位（serial 2025-11-25 / 构建 11-21 vs 全部 `*_mpi` 于 2026-09-02 19:45 重链，晚于 OpenMPI 安装 4 min）被列为**风险因素而非已证因**。`VECLIB`/`btl`/nproc 等调参既不复现也不消除。
- **稳定性策略（现状维持）**：Hessian 类作业（Opt/Freq/OptTS/IRC/NEB）按 **nproc=1** 跑；必要时 `nproc≤4` 仅用于 SP/Opt；并发作业**不可共用 scratch 目录**；可靠性靠 **log 解析 + 重试阶梯**而非退出码（ORCA 子作业 error termination 仍返回 0）。用户决策：**不加 VECLIB/btl、不提并发、不换 build**，现状 `nproc=1` + 槽 2。

---

## 6. 复现与证据

### 6.1 改动过的源文件（改源 → 重跑生成器，禁止手改 JSON）

- `cloudra/benchmark/gen_easy_tasks.py`：F1 的 `_NAME_EN`、`_STEP_TYPE_EN`、`_BOND_CHANGES`（新增 B–O 成键）。
- `ideapool/reaction_candidates/easy.md`：F1 行 SMILES 改为 `[BH4-].C=O>>CO[BH3-]`，反应列/机理列同步。
- `cloudra/benchmark/normal_registry/ru.py`：U3（NU3）改为 3 步并同步模块 docstring；(U6/NU6 的逐步 barrier)。
- `cloudra/benchmark/gen_normal_tasks.py`：U3 相关注释。
- `cloudra/benchmark/normal_registry/yo.py`：Y3（NY3）的 steps[1]/[2] barrier。
- `cloudra/benchmark/hard_registry/ab.py`：A1（HA1）的 barrier。
- 批量改动：为脱敏同步各生成器/registry 的 `name_en`（见 §4）。

### 6.2 重跑生成器（命令）

    .venv/bin/python -m cloudra.benchmark.gen_easy_tasks
    .venv/bin/python -m cloudra.benchmark.gen_normal_tasks
    .venv/bin/python -m cloudra.benchmark.gen_hard_tasks

（等价写法：`uv run python -m cloudra.benchmark.gen_easy_tasks` 等。）

（生成器 `--src` / `--out` 默认即 `ideapool/reaction_candidates/*.md` → `ideapool/tasks/*/*.json`；easy 生成器内含 `assert len(tasks) == 20` 计数守卫。台账「重跑 gen_easy/normal/hard_tasks」即指上述三条。）

### 6.3 测试命令与结果

    .venv/bin/python -m pytest tests/test_benchmark.py    # → 136 passed
    .venv/bin/python -m ruff check cloudra               # → 干净

（136 passed 为批次回填后的最终结果；`tests/test_benchmark.py` 含 `regenerate_identically` 守卫，保证「JSON == generator」一致。）

### 6.4 原始证据与入库策略

- **原始 ORCA 日志位于 `gold_compute/campaign/runs/`**，被 `.gitignore` **排除、不入库**（`.gitignore` 第 147–148 行：`# gold_compute 战役运行目录（append-only 本地证据，日志量大不入库）` / `gold_compute/campaign/runs/`）。
- **绝对路径记录在 computed JSON 中**：`gold_compute/edge_barriers/computed/<TASK>.json` 的 `ts_log` / `irc_log` 字段（见 §2 表）。
- 本批汇总产物：`gold_compute/edge_barriers/computed/{F1,NU3,NU6,NY3,HA1}.json` + 回填后的 `ideapool/tasks/**`。

### 6.5 遗留（已记录，未处理）

- HA1 的 `gold.selectivity.spread` 仍为 **2.0**（文献值、未评分口径），与本次计算所得 **|ΔΔE‡| = 5.72**（`computed/HA1.json`）不一致；方向一致（外向/E 优势）。台账已记录，**未改**。

---

## 7. 引用来源自查要点

逐条列出本文件所引数字与其来源文件，便于复核：

1. 8 条缺口边清单、题 tier、方法/溶剂/口径 → 台账「本批派发」表 + 「统一口径」节。
2. 各边 ΔE‡、TS 虚频、IRC 状态、frame 能量（Ha） → `computed/{F1,NU3,NU6,NY3,HA1}.json`（HA1 虚频波数取自台账「HA1」节）。
3. 回填后的 gold 值/weight/边名 → `ideapool/tasks/easy/F1.json`、`ideapool/tasks/normal/{NU3,NU6,NY3}.json`、`ideapool/tasks/hard/HA1.json`。
4. NU3 三步拆分、能量梯（0 / −59.45 / −27.95 / −32.21）、闭合校验（+31.50 −4.26 = +27.24 = E(P)−E(adduct)） → `computed/NU3.json`（`energy_ladder_rel_RC_kcal`、`closure_check`）+ 台账「NU3 机理解剖」「NU3 最终」节。
5. NU3 去 Wittig、`mapped_reactants` 映射氢、I1 由氧磷杂环丁烷改为 `OCCP`、旧值 19.1 失效 → 台账「NU3 机理修正」节 + 题库 `NU3.json`。
6. F1 产物 `C[O-].B` → `CO[BH3-]`、B–O 成键（`form [1,4]`）、B–O=1.49 Å、低于 RC 30.1 kcal → `computed/F1.json` + 台账「题面修正」节 + 题库 `F1.json`。
7. 脱敏清单与保留项 → 台账「题面脱敏」节。
8. ORCA 症状 A/B 结论与稳定性策略 → `_orca_env_probe/REPORT_orca_crash_diagnosis.md` §0/§4/§6/§7 + 台账「ORCA 修复线」节。
9. 重跑命令、测试结果（136 passed）、ruff、日志入库策略 → 台账「批次一交付完成」节 + `.gitignore` 第 147–148 行。
10. HA1 selectivity 遗留（5.72 vs 2.0） → `computed/HA1.json` 的 `selectivity` + 台账「批次一交付完成」遗留条。
