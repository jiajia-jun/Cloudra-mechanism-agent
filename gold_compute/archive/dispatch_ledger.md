# gold_compute 计算战役 — 派发台账（Coordinator）

更新时间：2026-09-14

## 用户指令
- 从 gold_compute 计划中领**原子数较小**的题去真实计算，补齐缺口边。
- 一个任务一个 small_mol；务必处理好条件（溶剂）与方法（色散校正 D3(BJ)）。

## 统一口径（黄金标准）
- 方法：B3LYP-D3(BJ)/def2-SVP（ORCA '! B3LYP D3BJ def2-SVP def2/J RIJCOSX'）。
- 能垒：ΔE‡ = E(TS) − E(该步起点极小值)，纯电子能，无 ZPE/热校正；逐边各自相对其起点。
- 溶剂：按题面 conditions 原样（具名溶剂→CPCM；gas phase→气相）。
- 验收：端点 opt+freq 0 虚频；TS 恰 1 虚频；IRC 双向落回两端极小值；fail-loud。
- 产物：gold_compute/campaign/runs/<TASK>/<EDGE>/ 日志 + gold_compute/edge_barriers/computed/<TASK>.json。

## 本批派发（swarm group_id = grp_dcc229bb4140439b9d1d21e6d1949aa8，agent a-4，max_concurrency=3）
| 题 | tier | 缺口边 | 体系 | 电荷 | 溶剂 | 状态 |
|---|---|---|---|---|---|---|
| F1 | easy | F1_E1 | BH4- + HCHO -> CH3O- + BH3 | -1 | 气相 | running |
| NU6 | normal | NU6_E1, NU6_E2 | 烯酮 + 甲亚胺 -> β-内酰胺 | 0 | CPCM(DCM) | running |
| NY3 | normal | NY3_E2, NY3_E3 | 甲酸甲酯 + OH- | -1 | CPCM(water) | running |
| NU3 | normal | NU3_E1 | Wittig 叶立德 + HCHO | 0 | 气相 | running |
| HA1 | hard | HA1_E1, HA1_EM1 | 3-甲基环丁烯开环（成对 TS） | 0 | 气相 | running |

共 9 条缺口边。

## 待办
- 收 5 份 small_mol 结果（AgentHub 通知）。
- 汇总 → 回填 gold 边（经生成器重跑，禁止手改 JSON）→ tests/test_benchmark.py 守卫绿。
- 若验证通过，再领下一批（NU5 / HA6 / HL1 ...）。

## 回填路径（已探明，供收值后合并）
gold 边的 barrier 来源（禁止手改 JSON；改这些源再重跑生成器）：
- F1 (easy): `ideapool/reaction_candidates/easy.md` 的 F1 行能垒单元格 → `gen_easy_tasks.py`（`_parse_barrier`）
- NU3 (U3): `cloudra/benchmark/normal_registry/ru.py` → TASKS["U3"]["steps"][0] 加 `"barrier"`（可选 `"weight"`）
- NU6 (U6): `cloudra/benchmark/normal_registry/ru.py` → TASKS["U6"]["steps"][0] 与 [1]
- NY3 (Y3): `cloudra/benchmark/normal_registry/yo.py` → TASKS["Y3"]["steps"][1] 与 [2]
- NU5 (U5): `cloudra/benchmark/normal_registry/ru.py` → TASKS["U5"]["steps"][0]
- HA1: `cloudra/benchmark/hard_registry/ab.py`
收值后：编辑上述源 → 重跑 gen_easy/normal/hard_tasks → `uv run pytest -q tests/test_benchmark.py` 守卫绿。
（registry 现有写法：step dict 里 `"barrier": <float>, "weight": 0.5|1.0`；weight 越小=越难算准。）

## 结果（滚动更新）
### HA1 — ✅ 已完成并独立验证（2026-09-14）
方法 B3LYP-D3(BJ)/def2-SVP 气相，ΔE‡ 电子能，相对 3-甲基环丁烯极小值 E=-195.027189720741 Ha(0虚频)：
- HA1_E1 外向→(E)-戊二烯 = **33.04** kcal/mol（TS -632.90 cm-1，IRC 双向收敛，端点 0 虚频）
- HA1_EM1 内向→(Z)-戊二烯 = **38.76** kcal/mol（TS -682.02 cm-1，IRC 双向收敛，端点 0 虚频）
- |ΔΔE‡| = 5.72（方向同 gold；gold 未核实值 2.0，选择性不评数值，仅记录）
产物 gold_compute/edge_barriers/computed/HA1.json（validation=verified）。
验证：log_parser 复核两 TS 均 opt+freq 收敛、final freq 块恰 1 虚频；raw grep 计数>1 是初始 Hessian 块所致。

### 环境坑（重要）
- ORCA 解析 Hessian 模块 orca_scfresp_mpi 在 MPI 下 SEGFAULT（本机 Mac）→ OptTS/Freq/IRC 一律 nproc=1。

### NU6 — ✅ 已完成并独立验证
B3LYP-D3(BJ)/def2-SVP CPCM(DCM)，ΔE‡ 纯电子能：
- NU6_E1 亚胺 N 进攻烯酮中心 C = **2.66** kcal/mol（frame=RC 复合物 -246.9285768 Ha，bound 4.12；TS -159.63 cm-1，IRC 双向→RC/I1）
- NU6_E2 conrotatory 4π 关环 = **15.72** kcal/mol（frame=I1 -246.9300050；TS -526.20 cm-1，IRC 双向→I1/P）→ RDS
验证：log_parser 两 TS opt+freq 收敛、final 块恰 1 虚频；ΔE 复算一致。caveat：RC 有 -24 cm-1 弱复合物软模（记录在案，对 ΔE‡ 影响<0.1）。

### NU3 — ⚠️ partial（值可用，但有科学 caveat）
B3LYP-D3(BJ)/def2-SVP 气相，ΔE‡ 纯电子能，frame=RC 最低 PH3 转子构象(-496.541090 Ha)：
- NU3_E1 [2+2]/C–C 偶联 = **1.70** kcal/mol（TS -279.0 cm-1，IRC 双向收敛）
- caveat：IRC 正向端点是 P–H→O 质子转移加合物(H2P-CH2-CH2-OH, -496.630774)，**不是**声明的氧膦杂环丁烷 I1(-496.585627, 自身的 0 虚频极小值，但不在该 IRC 路径上)；定向搜索 RC↔I1 的 P–O 关环 TS 未找到(收敛回同一 C–C 鞍点)。
- 结论：该模型 PES 上 C–C 偶联垒≈1.7，但到声明的 I1 无独立关环 TS；NU3_E1 记 partial（值=1.70，note 已写明）。
产物 gold_compute/edge_barriers/computed/NU3.json。

### NY3 — ✅ 已完成并独立验证
B3LYP-D3(BJ)/def2-SVP CPCM(water)，ΔE‡ 纯电子能：
- NY3_E2 甲氧基消除 = **12.5** kcal/mol（frame=INT1 -304.61642648，TS -159.06 cm-1 恰1虚频，IRC 双向→INT1/甲酸+甲氧负；吸热 8.8）
- NY3_E3 分子间质子转移 = **0.0** kcal/mol（无垒：约束扫描 O3-H5 0.98→2.10 单调下降无内顶点 + 无约束优化自发质子转移成甲酸根+甲醇）
验证：log_parser TS opt+freq 收敛、final 块恰1虚频；ΔE 复算一致。
产物 gold_compute/edge_barriers/computed/NY3.json。
坑：ORCA %irc 块不接受 Calc_Hess（用 %irc MaxIter N end）。

## 题面修正（用户指令 B，仅硼那题）
用户确认：只改 F1（BH4- + HCHO）的产物物种——产物 B 应与 O 成键（硼烷-甲氧基配位加合物）。
改动（改源+重跑生成器，未手改 JSON）：
- cloudra/benchmark/gen_easy_tasks.py：_NAME_EN[F1] -> '...-> borane-methoxide adduct [CH3OBH3]-'；_STEP_TYPE_EN[F1] 增补 B-O 配位成键；_BOND_CHANGES[F1] -> break [[1,2],[3,4]] / form [[2,3],[1,4]]（新增 B1-O4 成键）。
- ideapool/reaction_candidates/easy.md F1 行：SMILES 单元格改为 [BH4-].C=O>>CO[BH3-]，反应列/机理列同步。
- 已重跑 gen_easy_tasks -> ideapool/tasks/easy/F1.json（products=['CO[BH3-]']，gold F1_P=['CO[BH3-]']）。
- 验证：RDKit 校验 CO[BH3-] 与 [BH4-].C=O 原子/电荷配平（CH6BO-, -1）；tests/test_benchmark.py 全绿；ruff 干净。
- 备注：E1 产物 F（应为 HF）同类化学错误已指出，但用户本轮只要求改硼题，故未动。

## 题面脱敏（用户指令：全库去第1类硬泄漏，尺度 a）
改了 name 源（生成器/registry 的 name_en），未手改 JSON；重跑 gen_easy/normal/hard；tests exit=0；ruff 干净。
硬泄漏去除清单（旧 -> 新）：
- NY3: Ester saponification (BAC2): ... -> Ester saponification: ...
- NU3: ...-> ethylene + H3P=O (via oxaphosphetane) -> 去掉 (via oxaphosphetane)
- NQ1: ...(via ortho-cyclohexadienone) -> 去掉
- L1: conrotatory ring opening -> ring opening ; L2: disrotatory ring closure -> ring closure
- HA1/HA6: ...conrotatory...torquoselectivity -> ...ring opening: determine the stereochemical outcome
- C3: retention-pathway mechanism (vs backside SN2) -> F- + CH3Cl: determine the stereochemical course (retention vs inversion)
- D3: (endo, self DA) -> (self Diels-Alder); D4: DA (heteroatom dienophile) -> Diels-Alder
- E1: E2 elimination -> elimination
- P2: [1,5]-H shift -> degenerate H shift; P3: Claisen ([3,3]) -> Claisen
- X1: (decarboxylative extrusion) 去掉; G2: (double H transfer) 去掉; M1: atropisomer rotation -> aryl-aryl rotation
- HD2: SN2 epoxide opening -> epoxide opening; HE2: axial vs equatorial attack on a conformationally locked ketone -> determine the stereochemical outcome
- HE3: enantioface selection -> addition; HF1/HG2/HI1: diastereoselectivity/enantioselectivity/preferred TS geometry -> stereochemical outcome
- HH1: 1,1'-binaphthyl atropisomerization (thermal racemization) -> 1,1'-binaphthyl thermal racemization
保留（按尺度 a）：通用反应名（Diels-Alder/Claisen/Wittig/Staudinger/Passerini/Mannich/Baeyer-Villiger/pinacol/Beckmann/aldol/ene…）、D1 的 (parent DA)、HL1 的 'which group migrates'（即为题面问题）、NU6 的 'Staudinger beta-lactam synthesis'。
遗留：easy.md/normal.md/hard.md 的文档性题名列未同步（不参与生成/题面，仅文档）。

## 批次一交付完成（5 题 / 8 条缺口边，全部回填 gold）
方法统一 B3LYP-D3(BJ)/def2-SVP（ORCA 6.1.1），ΔE‡ 纯电子能，逐边相对该步起点极小值。
| 边 | 值 | 溶剂 | 验证 | 备注 |
|---|---|---|---|---|
| F1_E1 | 39.4 | 气相 | verified | TS 1 虚频 −879.9；IRC 双向；产物=硼烷-甲氧基加合物 |
| NU3_E1 | 1.7 (w=0.5) | 气相 | partial | IRC 陡降产物为 P–H→O 加合物、非声明的氧膦杂环丁烷；无 RC↔I1 关环 TS |
| NU6_E1 | 2.66 | CPCM(DCM) | verified | frame=RC 复合物 |
| NU6_E2 | 15.72 | CPCM(DCM) | verified | RDS |
| NY3_E2 | 12.5 | CPCM(water) | verified | 甲氧基消除 |
| NY3_E3 | 0.0 | CPCM(water) | verified | 无垒 PT（扫描无内顶点+自发质子转移） |
| HA1_E1 | 33.04 | 气相 | verified | 外向，favored |
| HA1_EM1 | 38.76 | 气相 | verified | 内向 |
回填方式：改源（easy.md 的 F1 能垒格；normal_registry/ru.py 的 U3/U6；yo.py 的 Y3；hard_registry/ab.py 的 A1）→ 重跑 gen_easy/normal/hard → tests/test_benchmark.py 136 passed，ruff 干净。
遗留：HA1 的 gold.selectivity.spread 仍写 2.0（文献值，未评分口径），与本次计算差 5.72 不一致——已记录，未改。F1.json 里关于『gold 产物节点为分离 C[O-].B』的 caveat 已因题面修正而失效（现为 CO[BH3-]）。

## ts_guess 复核（工具级 strict，engine='orca'）
更正：ts_guess verify 之前报『Failed to parse vibrational frequencies』是因为漏了 engine 字段（默认 gaussian）；加 engine='orca' 后可用。
逐边工具判定：F1_E1=pass；NU6_E1=pass；NU6_E2=**fail**（IRC 外侧帧未落到 P，rmsd>0.6，已派 NU6 代理按工具 remedy 重优化外侧帧/调大 %irc MaxIter 后复跑）；NY3_E2=pass；HA1_E1=pass；HA1_EM1=pass；NU3_E1=**fail**（喂『声明的 I1』时方向不一致，与 partial 判定一致；只有把 IRC 自己的端点当中间体才 pass=自证循环）；NY3_E3 无 TS，N/A。

## ts_guess strict 复核结果（终版，engine='orca'）
| 边 | verdict |
|---|---|
| F1_E1 | pass |
| NU6_E1 | pass |
| NU6_E2 | pass（先 fail：IRC 外侧帧与 p.xyz 原子序不同导致 rmsd 假超阈；重优化外侧帧(ep_a≡P, ep_b≡I1, 0虚频)后 pass）|
| NY3_E2 | pass |
| HA1_E1 | pass |
| HA1_EM1 | pass |
| NU3_E1 | fail（对声明的 I1 方向不一致；本质问题，维持 partial）|
| NY3_E3 | N/A（无 TS）|
结论：7 条有 TS 的边里 6 条过工具级 strict；仅 NU3_E1 对声明机理不过（其 C–C 偶联鞍点不通向声明的氧膦杂环丁烷）。

## NU3 机理修正（用户指令 b + 去 Wittig）
按用户要求把 NU3 的声明机理改成该模型 PES 上真实发生的路径，并去掉题面里的 'Wittig' 诱导：
- 源改动：normal_registry/ru.py 的 U3（+ 模块 docstring）、gen_normal_tasks.py 的注释。
- 题名/query：'Wittig reaction simplified model: H3P=CH2 ...' → 'H3P=CH2 ylide + formaldehyde -> ethylene + H3P=O'（query 不再出现 Wittig）。
- mapped_reactants 加显式映射氢：`[CH2-:1][PH2+:2][H:5].[CH2:3]=[O:4]`（P–H→O 质子转移可被 bond_changes 记录）。
- 中间体 I1：氧磷杂环丁烷 `C1C[PH3]O1` → 真实加成物 H2P-CH2-CH2-OH（canonical `OCCP`）。
- NU3_E1 bond_changes：break [[2,5],[3,4]] / form [[1,3],[4,5]]；barrier 1.7（保留）。
- NU3_E2：reactant 改为该加成物；旧文献值 19.1（氧磷杂环丁烷环消除）已不适用 → **barrier 设为 null**，已派 NU3 代理按新定义补算。
- 重跑 gen_normal_tasks；tests/test_benchmark.py 136 passed；ruff 干净。
- strict 复核：用新 I1 时 NU3_E1 = pass；但那是拿 IRC 原始帧当端点（自证循环），已要求代理给独立优化的加成物极小值端点后重跑。

### NU3 进展（2026-09-16 晚）
- NU3_E1 升级为 verified：独立优化加成物极小值(job 416, E=-496.635831, 0 虚频)作端点，ts_guess(strict, engine=orca)=pass；1 虚频 -279.0；IRC 双向配对成立；值 1.70 不变（相对 RC-min -496.541090）。独立优化比 IRC 原始帧低 3.2 kcal，印证端点必须独立优化。
- NU3_E2 待定：跑 417(氧磷杂环丁烷->产物 OptTS)、418(加成物->氧磷杂环丁烷 OptTS) 及直接 加成物->产物 插值；落定后决定 registry 步数（可能 2->3 步）。
- 待办：E2 落定后回填 steps 的 barrier；把 steps[0].weight 由 0.5 改 1.0（E1 已 verified）-> 重跑 gen_normal_tasks -> tests/ruff。

## 派发：ORCA 环境修复（env a-8, session as_96c21bcdaa6e4147）
用户指令：NU3 继续算，同时修 ORCA。
要修：(A) 解析 Hessian 的 MPI 路径(orca_scfresp_mpi)多进程 SEGFAULT（间歇/底物相关）；(B) 松弛扫描 SHARK/PROPERTIES 崩溃。
环境：M5 Pro/arm64，ORCA 6.1.1 本机自编译，链 Open MPI 4.1.8 + Apple Accelerate；现设 OMPI_MCA_btl=vader,self。
实验：VECLIB_MAXIMUM_THREADS=1 / OMP_NUM_THREADS=1；OMPI_MCA_btl 变体；nproc=2 vs 4；最小体系复现。
约束：不碰 NU3 作业与 job 416-421；探针跑独立 scratch，单次 nproc<=4、整机 ORCA<=8 核、跑完清进程。
交付：根因判据 + 实验矩阵 + 可用配置(含注入调度作业的方式) + 症状B替代路线 + 批量 nproc/并发建议。

### NU3 机理解剖（2026-09-16 深夜，B3LYP-D3(BJ)/def2-SVP 气相，纯电子能）
极小值(Ha)：RC=-496.541090；adduct I1(H2P-CH2-CH2-OH)=-496.635831(0虚频, job416)；氧磷杂环丁烷=-496.585627(job362)；产物 C2H4+H3P=O=-78.477468+(-418.114949)=-496.592417(jobs419,420)。
热力学(相对 RC, kcal)：RC 0 → adduct -59.5 →(step2 +55.8)→ oxa -27.9 →(step3 -4.26)→ products -32.2。
闭合自检：adduct->oxa(+31.50) + oxa->products(-4.26) = +27.24 = E(products)-E(adduct) 精确吻合。
直接 adduct->products：**无基元鞍点**（IDPP OptTS 收敛到无关鞍点 job421, +81.9, 1虚频 -1651，IRC 实为 H2P-OH<->H3P=O 互变）。
展开路径：step2(adduct->oxa) 鞍点已找到并 IRC 验证：job418 TS=-496.546894, 恰1虚频 -1021.6, 几何 P2-O9=2.277 + H 已回 P（协同 O->P 质子转移+P-O 关环）；IRC job422 两端=adduct(-496.631425)/oxa(-496.584507) => ΔE‡=+55.81。
step3 待定：job417 只找到低于起点的松散假鞍点(-56cm-1)已弃；job424 重试中。若失败则用文献类似物 19.1(Me3P, weight 0.5) 并标注 analogue。
结论：RC->adduct(1.70, verified) -> oxa(55.8, computed) -> products(pending)；adduct 是深阱。
待办：等 step3 定稿 -> 我把 registry U3 扩成 3 步(含 mapped out 链、逐步 barrier/weight) -> 重跑 gen_normal_tasks -> tests/ruff。

## ORCA 修复线：用户指示「别管了」，关闭（2026-09-16）
env 结论（报告存 gold_compute/campaign/_orca_env_probe/REPORT_orca_crash_diagnosis.md）：
- 症状B(松弛扫描崩) = ORCA 自身缺陷：%geom Scan 某点撞 MaxIter 时在 PROPERTIES/SHARKINP 崩，nproc 无关；规避=不用 %geom Scan。
- 症状A(并行崩) = 真实但偶发；构建错位(serial orca 2025-11-25 vs 全部 *_mpi 2026-09-02 19:45，晚于 OpenMPI 安装 4min)+ORCA/OpenMPI 内部故障；env 调参不能证修。崩溃报告含 serial orca 在 VIB_PrintSpectra 的 SIGSEGV → nproc=1 对 Freq 也非 100% 安全。
- 未采纳任何改动：不加 VECLIB/btl，不提并发，不换 build（用户决定）。现状维持 nproc=1 + 槽2。

### NU3 最终（3 步，全部自算；registry 已落库，tests 136 passed）
name_en 已去 Wittig；mapped 链 step1/2/3 = [CH2:1]([PH2:2])[CH2:3][O:4][H:5] / [CH2:1]1[CH2:3][O:4][PH2:2]1([H:5]) / [CH2:1]=[CH2:3].[O:4]=[PH2:2][H:5]。
gold 边：NU3_E1 R->I1(OCCP)=1.70 w1.0；NU3_E2 I1->I2(oxa)=55.81 w1.0；NU3_E3 I2->P=23.76 w1.0。
能量梯(相对 RC)：0 / -59.45 / -27.95 / -32.21；闭合 (+31.50)+(-4.26)=+27.24=E(P)-E(adduct) 精确。
TS 复核（我独立跑 log_parser）：E1 -279.0 / E2 -1021.55 / E3 -624.78 cm-1，各恰 1 虚频，opt+ts 收敛正常终止。
**发现并已要求修正**：三条 IRC 各有**一个方向撞 MaxIter 被截断**（E1/E2 是 forward，E3 是 backward），并非双向完全收敛；strict 允许部分 IRC 故 E1 pass 成立。已派代理:加大 %irc MaxIter 补跑 + 精确改写 note（禁写'双向收敛'）。

### NU3 收口（措辞已修正，2026-09-16）
NU3.json 增 irc_convergence_note + 逐边 irc_detail，精确写明各方向收敛/截断(MaxIter=30)与截断侧外侧帧优化后的落点及能量差；无任何'双向收敛'表述。
E1: BACKWARD(RC侧)收敛；FORWARD(adduct侧)截断(MaxIter=30)，外侧帧 -496.630773 -> 独立优化(416)落到 adduct min -496.635831(低 3.17)；strict=PASS。
E2a: BACKWARD(oxa侧)收敛(-496.584507)；FORWARD(adduct侧)截断(-496.631425，比 adduct min 高 2.76)。
E2b: FORWARD(oxa侧)收敛(-496.583584)；BACKWARD(products侧)截断(-496.598099, C2H4...H3P=O 接触对，比分离产物 -496.592417 低 3.57)。
barrier 不变 1.70/55.81/23.76；补跑 426/427/428 忽略、不入账。registry 已 3 步、tests 136 passed、ruff 干净。
更正记录：我曾误要求把 IRC 补跑到收敛——用户指出 IRC 无需收敛（strict 明文 IRC need not reach a minimum），已叫停并只做措辞修正。
