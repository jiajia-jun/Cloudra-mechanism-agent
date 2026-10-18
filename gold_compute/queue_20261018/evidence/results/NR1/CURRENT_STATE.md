# NR1 · 甲酰胺气相热脱水

## 题面要素（以 `ideapool/tasks/normal/NR1.json` 为准）

- 反应：NH2CHO → HCN + H2O
- 规模：6 原子 / 3 重原子，气相，净电荷 0，单重态
- 方法：B3LYP-D3(BJ)/def2-SVP，Gaussian 16（本机）
- 待建路线（假设起点，须自算验证）：Formamide → INT-1a → INT-1b → INT-1c → HCN + H2O
- TS 需求：tsH-1,3 / tsR-1a1b / tsR-1b1c / INT-1c-tsH2O（其中两段是构象转换）
- 文献来源（只作背景，数值不得直接回填）：Nguyen et al., JPCA 2011, 115, 841–851；SI 有 3 个中间体全正频 + 4 个一虚频 TS

## 验收口径（项目既定，D1 三环）

每条可交付的边必须同时具备：
1. **(a) 方向**：同程序 TS 恰 1 虚频，虚频模在声明 watch pair 上的净位移与 `bond_changes` 同向；反向即 pseudo-saddle，永不回填。
2. **(b) 成分**：三种归一化份额（反应中心 / 全重原子 / 最大单原子）如实记录，不设阈值。
3. **(c) 交付**：同程序同方法 TS 减**本步自身起点**极小值（纯电子能），两端均 `Opt+Freq` 0 虚频且身份核验通过。

附加：短 IRC 双向方向区间（不要求跑满）；构象边可有空 `bond_changes`，不得捏造成断键。

## 当前状态

- [x] 反应物/中间体/产物结构与频率：R(1121)、INT-1a(1123)、INT-1b(1124)、INT-1c(1125)、第4构象(1126)、HCN(1127)、H2O(1128)、HCN···H2O(1213)，全部 0 虚频
- [x] 各 TS 一虚频 + 方向判据：tsH-1,3 = ts_0032（-1897.6514，verified）、tsR-1a1b = ts_0033（-991.8673，verified）、tsR-1b1c = ts_0034（-508.3050，verified）、**INT-1c-tsH2O = ts_0042（-1923.6069，工作流 verdict=candidate_only，原因仅 IRC 区间证明，见下）**；旧 ts_0035 已废止（三次都滑到 O–H 转子鞍点）
- [x] 两端身份 + 0 虚频：三条已验证边的两端均 Opt+Freq 0 虚频（job 1210/1214、1215/1216；1196/1198、1200/1202；1187/1190、1192/1194）
- [x] mechanism_graph.json：已写（4 条边，e1 46.32 / e2 22.80 / e3 7.25 / **e4 68.85**（稳定中间体分母 INT-1a；64.93 作 barrier_conformer_specific 保留） kcal/mol；每条边新增 barrier_denominator 字段（物种+job+E+理由）；两条构象边 bond_changes 空；e4 带完整 provenance：TS job 1296 freq.log sha `a5e4129e…` L419/L614、ts_opt 1295 L4366、IRC 1297 sha `7faf6018…`、端点 declaration_0004 四份日志 sha+L 行号）
- [x] REPORT.txt：已写（80 行，sha256 `6ddaa7eafb27ad81402861750898a2cdf405497db90953f6ef676e8087d1defd`；§二 TS4 段已改为「已定位」，§四 十次失败尝试保留为排查记录并标注「已被 ts_0042 取代」）
- [x] **四条边 4/4 完成**。e4 = INT-1c-tsH2O 已定位：run ts_0042，TS E = **−169.641371451 Ha**（job 1295 refine.log L4366）、恰 1 虚频 **−1923.6069 cm⁻¹**（job 1296 freq.log L614）、四列投影 O3–H4 +0.9036 / N1–H4 −0.8482 / C2–O3 −0.1206 / N1–H6 −0.0174、**ΔE‡ = +68.85 kcal/mol**（08:40 按「稳定中间体」口径改为分母 INT-1a job 1196 = −169.751090026；相对 INT-1c 的 64.93 保留为构象特定值，两者差 3.92 kcal/mol）；反向 +49.81；端点（declaration_0004）reactant −169.744844755（0 虚频，与 INT1c 差 6e−8 Ha，RMSD<1e−4 Å，dih 0.00°/180.00°）、product −169.720742511（0 虚频，与 job 1213 差 2.5e−8 Ha，P−INT1c = +15.12 kcal/mol）
- [ ] e4 唯一未闭合项：**工作流 verdict = candidate_only**，仅因“IRC 区间证明”——产物臂 10 步只到 C2–O3 1.82 Å、产物极小在 4.21 Å，外侧帧与产物极小距离矩阵 RMSD 1.68 Å 超门槛。连接性本身已被两臂单调下降 + 两端 0 虚频 + 能量与两个独立驻点一致到 1e−7 Ha 证明。加长 IRC（MaxPoints=100,StepSize=20，declaration_0005 job 1308）**无效**：route 是 `irc=calcfc`，Gaussian 用默认 10 点，逐帧能量与 0002 逐位相同。需平台侧把 MaxPoints/StepSize 写进 route 才能闭此环。证据链见 REPORT.txt §二 TS4 与 §五、E4_GRID.md「E4-IRC 逐帧」与「最终 TS 与端点」两节。

（本文件由主协调维护，每轮更新。详细数值进 `REPORT.txt`，裁决进 `gold_fill_20261018/DECISION_LOG.md`。）
