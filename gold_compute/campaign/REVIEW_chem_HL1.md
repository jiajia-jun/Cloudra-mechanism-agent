# REVIEW_chem_HL1 — 化学工具化复核（只读，未跑 QM 生产作业）

**复核范围**：任务 **HL1, NA5**（本组第一个任务 = HL1，故文件名为 REVIEW_chem_HL1.md）。
只读复核：未修改任何 `gold_compute/edge_barriers/computed/*.json` 或题源，未提交任何 QM 计算作业。
所有化学量（虚频、几何、成/断键、键级）均经化学工具获得，未用 bash/sed 切割坐标或键长。

**工具链**：`log_parser` → `format_converter` →（回退）ORCA 引擎自写的最终几何 sidecar `.xyz` → `internal_coordinates` → `electronic_analysis`（PySCF B3LYP/def2-SVP, DF/RI）。

**重要流程偏差（据实记录）**：任务书首选 `format_converter(input_format='log', output_format='xyz')` 从 freq 日志导出"最后一个收敛帧"，但该工具对本文全部 8 个 ORCA 日志均失败（`日志解析器内部索引越界`，与 `log_parser` 的 `cclib could not parse ... no SCF blocks` 一致，疑为 RIJCOSX/CPCM 日志解析不兼容）。
**回退方案**：改用 ORCA 该作业自身写出的最终坐标文件 `<job>.xyz`（引擎产物，非手工拼坐标）。已逐一核验 sidecar 头部能量与该 job 的 `state_<id>.json` 能量**逐位一致**（例：HL1_E2 `-364.045333943017`、NA5_E2 `-440.571648790635`），并用日志内 `INPUT FILE = ...inp` 确认 sidecar 与 freq 作业同名匹配：
- calc-531→ts_e1；calc-528→ts_e2；calc-529→ts_e5；calc-645→ts_e3_seed3
- NA5 calc-653→E2_optTS3；calc-636→E3_optTS4；calc-646→E4_optTS3；calc-579→E5_optTS

---

## 结论（逐边表格）

原子编号：**HL1** 的文件序与 JSON note 的编号一致；**NA5** 的文件序与 `mechanism_graph.bond_changes` 的声明编号**不一致**（见下注），故 NA5 各边标注"声明原子号未绑定"。

| TASK/EDGE | 最终块虚频 | 感知的成/断键（与声明是否一致） | 键角异常 | 部分键/键级(争议边) | 结论 | 工具 |
|---|---|---|---|---|---|---|
| HL1_E1 | 1 imag，**-1791.63** | N4–H18 伸长 1.191 Å（**断/迁移**）；H12→O16 形成 1.499 Å。几何=**O→N 质子转移**鞍点，**非**声明的 H3O+→oxime-O | O5–N4–H18 52.1°(Δ-67.9°)；C3–N4–H18 150.8°(Δ+30.8°) | —（非争议边） | **通过（读数与记录一致）**：确为收敛一阶鞍点(1 imag)，几何证实其不是声明的 E1 步——与 JSON note 完全吻合 | log_parser, internal_coordinates |
| HL1_E2 | 1 imag，**-304.17** | 断 **C2–C3** 1.786 Å(elongated)；N5–O6 已断(~4 Å, 分属不同片)；成 **C3–N5** 1.191 Å(compressed)；成 C2–N5 2.073 Å | C4–C3–N5 153.7°；C2–C3–N5 85.8°；C3–C2–H11 90.8° | **BO: C2–C3 0.519（部分键,断）**；**C3–N5 2.260（成,近三键）**；**C2–N5 0.336（incipient）** | **通过**：几何=Na—O 断裂+anti-1,2-乙基迁移的 Beckmann 鞍点，与声明步一致；无软模/产物型迹象；闭壳单重态 | +electronic_analysis |
| HL1_E5 | 1 imag，**-653.06** | **无重原子反应键**；仅 O6(羰基O)…H3O+(O16) 的 H···O 1.746/1.784 Å H 键 | 无(Δ>12° 无) | BO: N3–C4 1.401、C4–O6 1.609（**酰胺**）；N3–H15 0.919 → **几何=酰胺产物+H3O+** | **存疑/不通过**：-653 为孤立质子软模，几何是产物侧，**非 I4→P 互变异构 TS**（与 JSON 降级一致） | +electronic_analysis |
| HL1_E3m | 1 imag，**-63.55** | **无 C–O 成键**（C8···O4 未成键）；仅 O1–H5 1.858 Å 水 H 键 | 无 | BO: **C8–N9 1.150, 2.542（nitrilium 完好）**；无部分键 | **存疑/不通过**：软旁观(水)模，几何=nitrilium+2H2O，非声明的 C–O 加成 | +electronic_analysis |
| NA5_E2 | 1 imag，**-283.64** | **H2 飞行中**：O1–H2 1.218 Å（O1=水合氢 O）↔ H2–O8 1.201 Å（O8=氨基甲醇 O）。质子转移鞍点。声明原子号未绑定 | 无 | **BO: O1–H2 0.502 / H2–O8 0.520（对称部分键，质子飞行）** | **通过（几何一致）**：确为氨基甲醇-O 质子化子步的质子转移鞍点；IRC 连通性仅部分建立（JSON 已记） | +electronic_analysis |
| NA5_E3 | 1 imag，**-2140.76** | **成 O12–H14** 1.315 Å / **断 C10–H14** 1.501 Å；C10–C11 1.402 Å、C11–O12 1.297 Å（烯醇化骨架）。声明原子号未绑定 | C11–O12–H14 76.8°(Δ-32.7°) | **BO: C10–H14 0.421 / O12–H14 0.476（H 在 C 与 O 之间）**；C10–C11 1.349、C11–O12 1.429（部分双键） | **通过**：几何=α-C–H→O 的 1,3-H 迁移（烯醇化）鞍点，与声明一致；-2140 刚性模符合直接 H 转移 | +electronic_analysis |
| NA5_E4 | 1 imag，**-363.63** | **成 C1–C10** 1.963 Å（iminium C ↔ 烯醇 C）。声明原子号未绑定 | H4–C1–C10 91.4°(Δ-18.1°)；C1–N2–C3 122.1°(Δ+12.6°) | **BO: C1–C10 0.581（incipient,成）**；同时 C1–N2 1.356、C10–C11 1.370、C11–O12 1.451（均部分键→两片均畸变） | **存疑**：确有真实 C–C 部分键，但两端 IRC 均落回 I3 → 是 approach/preorganisation 鞍点，**productive I3→I4 未证实**（与 JSON 一致） | +electronic_analysis |
| NA5_E5 | 1 imag，**-56.48** | O6–H16 1.501 Å、O17–H22 1.422 Å（质子接力）；**无重原子部分键** | 无 | 无重原子部分键 → **软质子模** | **存疑/不通过**：软质子旁观模，非 productive I4→P 鞍点（与 JSON 一致） | +electronic_analysis |

**注（NA5 原子号未绑定）**：NA5 的 `mechanism_graph.bond_changes` 声明编号与几何文件序不一致。例如 E2 note 写 "O4–H2=1.201, C3–O4=1.53"，而几何文件序中该 O 为 **O8**、该 C 为 **C7**（`internal_coordinates` 报告 dihedrals `C5–N6–C7–O8` 佐证）。故 NA5 各边我按"元素/邻接+报告距离"定性对照声明步的化学，**声明原子号未绑定**；HL1 各边原子号可直接对应。

**范围注**：任务清单中的争议边 **NU3_E2a 不属于本组（HL1, NA5）**，未复核（属 NU3 组，见 REVIEW_modes_NU3.md）。

---

## 逐边要点（置信度）

1. **HL1_E2 — 通过（高）**：虚频 -304.17 被 `log_parser` 从**最终** VIBRATIONAL 块读出（恰 1 个虚频）；几何显示 C2–C3 断裂(BO 0.52)、C3–N5 成键(BO 2.26)、C2–N5 incipient(BO 0.34)——一个真实的 Beckmann（N–O 断裂+乙基迁移）反应坐标鞍点。唯一遗留是 IRC 一端未回到 I1（JSON 已存疑），但**鞍点本身的几何/模与声明步一致**。
2. **HL1_E1 — 通过（记录一致）/几何非声明步**：calc-531 是收敛一阶鞍点（1 imag -1791.63），但其几何为 O→N 质子转移，不是声明的 H3O+→oxime-O 质子化——与 JSON 的"E1=null + 该鞍点为证据"完全吻合。**证实 JSON 的读法（最终块虚频，而非初始 Hessian 的 5 模块）**。
3. **HL1_E5 / HL1_E3m — 确认为非 productive 软模（高）**：两者几何分别是"酰胺+H3O+"与"nitrilium+2H2O"，**无重原子反应键**，虚频模为孤立/旁观质子模。支持 JSON 将其降级为 null。
4. **NA5_E2/E3 — 通过（几何一致，中—高）**：虚频分别为 -283.64（质子转移，O1–H2–O8 对称部分键）与 -2140.76（烯醇化 C10–H14→O12，C=C/C–O 部分双键），均为真实反应坐标型鞍点。E3 的 69.94 kcal 高势垒与刚性 -2140 模自洽。
5. **NA5_E4 — 存疑（中）**：C1–C10 incipient BO 0.581 说明确有 C–C 成键相互作用，但 C1–N2/C10–C11/C11–O12 均部分键（两片畸变），且两端 IRC 回 I3——approach 鞍点而非 productive I3→I4。保留 JSON 的 ts_located+未连通判定。
6. **NA5_E5 — 存疑/不通过（中）**：-56.48 软质子模，无重原子反应坐标，几何为质子接力的松散复合物，非 productive I4→P 鞍点。

**自旋污染**：所有体系 charge=+1、mult=1、闭壳单重态，PySCF RKS SCF 全部收敛，无 <S²> 污染问题。

---

## Reliability Evidence

- **最终 VIBRATIONAL 块虚频数（`log_parser`, properties=['frequencies','convergence','job_type']）**：8 条边全部 **n_imag = 1**，wavenumber 分别为 -1791.63(HL1_E1)、-304.17(HL1_E2)、-653.06(HL1_E5)、-63.55(HL1_E3m)、-283.64(NA5_E2)、-2140.76(NA5_E3)、-363.63(NA5_E4)、-56.48(NA5_E5)——与 `computed/*.json` 声明值**逐个一致**。特别地 HL1_E1 的 `log_parser` 返回 1 个虚频（非初始 Hessian 块的 5 个），证明取的是最终块。
- **收敛性**：所有 ORCA 作业 `normal_termination=True`、`opt_converged=True`；各 PySCF 单点 `SCF converged = True`。
- **几何来源**：ORCA 引擎最终几何 sidecar `.xyz`（能量与 `state_<id>.json` 逐位一致）。
- **感知层**：`internal_coordinates(mode='analyze')` 给出成/断键（elongated/compressed/forming_candidate）与键角异常；`electronic_analysis` 给出 Mayer 键级/部分键/incipient 键/IBO。
- **IRC 连通性**：本次为**只读化学工具复核，未重跑 IRC**；连通性结论沿用 `computed/*.json` 的 IRC 记录（已在表中如实标注）。
- 未发现任何"虚频计数与记录不符"或"几何与声明步严重矛盾却标为通过"的情况；两处 JSON 自标为 null/存疑的鞍点（HL1_E5、HL1_E3m、NA5_E5、NA5_E4）经独立工具复核后**支持其保留在存疑/不通过**。

## Artifact Paths

- 复核用 TS 几何（自 ORCA 引擎 sidecar 复制，只读副本）：
  `gold_compute/campaign/_chem_review/{HL1_E1,HL1_E2,HL1_E5,HL1_E3m,NA5_E2,NA5_E3,NA5_E4,NA5_E5}_ts.xyz`
- 源 freq 日志：见 `gold_compute/edge_barriers/computed/{HL1,NA5}.json` 的 `ts_log` 字段（calc-531/528/529/645；NA5 calc-653/636/646/579）。
- 计算参数：`electronic_analysis` = PySCF RKS/B3LYP(D3 不计于单点)/def2-SVP，DF/RI，charge=+1，spin=1，scf_conv_tol=1e-7；几何来源 ORCA 6.1.1 `! B3LYP D3BJ def2-SVP def2/J RIJCOSX`（NA5 另加 CPCM(water)）。
