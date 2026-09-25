# Easy 存量题自算参考值回填·第二批（2026-09-25）

本次依用户要求回填剩余八道已有 Easy 题（第一批十题见
`easy_backfill_2026-09-23.md`）。数值均为气相 ORCA 5.0.2
B3LYP-D3(BJ)/def2-SVP（def2/J、RIJCOSX；TS 作业 +TightSCF、
`%geom Calc_Hess true`）的**电子能垒**：
`(E_TS - E_RC) × 627.5095 kcal mol⁻¹ Eh⁻¹`，无 ZPE、热修正或溶剂修正。
题源 `ideapool/reaction_candidates/easy.md` 是生成器输入；生成的
`ideapool/tasks/easy/*.json` 承载评分用 `barrier_kcal_mol`。这组回填是
`gold_compute/README.md` 所允许的存量题择机回填，不属于新策展题目队列。

原始计算在 gold 节点 `/public/home/yyywaa/cloudra_workspace/`（调度台账
`EASY_GOLD_LEDGER.md`，八题全部经 coordinator 用 log_parser 复核）；
对应文件已备份在本机 `gold_compute/remote_backups/2026-09-25/`
（`.gbw` 波函数文件除外）。以下证据路径相对该备份目录。回填前本批
能量已逐项由原始 ORCA 日志最后一条 `FINAL SINGLE POINT ENERGY` 重读，
虚频数以日志**最终**频率块为准（OptTS 日志含初始 Hessian 与最终频率
两块，只取后者）。

| 题 | RC / Eh | TS / Eh | ΔE‡ / kcal/mol | RC 日志 | TS 日志 | 证据状态 |
|---|---:|---:|---:|---|---|---|
| D3 | −387.700696311672 | −387.677344932963 | 14.65 | `D3/.cloudra/calc-256.out.log` | `D3/.cloudra/calc-239.out.log` | 双端极小值（0 虚频）、TS 恰 1 虚频 −441.23 cm⁻¹（成键 C2–C13）、IRC（calc-248）双向收敛、端点重优化（calc-255/256）零虚频；分离反应物口径 10.06（单体 calc-261） |
| D4 | −385.523510860311 | −385.505500929178（endo）/ −385.505419728964（exo） | 11.30（endo）/ 11.35（exo） | `D4/.cloudra/calc-242.out.log` | `D4/.cloudra/calc-241.out.log`（endo，−448.44 cm⁻¹）、`D4/.cloudra/calc-233.out.log`（exo，−430.72 cm⁻¹） | RC/双 P（calc-173/174）零虚频；两 TS 各恰 1 虚频；IRC（calc-236/246）双向、端点重优化（calc-251/252/257/258）零虚频；预反应络合物结合 6.18，分离反应物口径 endo 5.12 / exo 5.17 |
| X1 | −266.824327146258 | −266.759151754684 | 40.90 | `X1/.cloudra/calc-141.out.log` | `X1/.cloudra/calc-212.out.log` | 双端极小值、TS 恰 1 虚频 −894.65 cm⁻¹（C2–C5/O3–C4）、IRC（calc-214）双向、端点重优化（calc-223/224）零虚频 |
| E1 | −638.838696599589 | −638.837300580032 | 0.88 | `E1/.cloudra/calc-222.out.log` | `E1/.cloudra/calc-213.out.log` | RC/P（calc-220）零虚频、TS 恰 1 虚频 −289.71 cm⁻¹（F1···H5 成 / C2–H5 断）、IRC（calc-225）双向收敛、端点重优化零虚频；**近淹没浅垒**：络合物结合 43.8、TS 低于分离反应物 42.9，文献锚点 ~6.9 未复现（真实结果，非强制吻合） |
| F1 | −141.578432490126 | −141.515621903215 | 39.41 | `F1/.cloudra/calc-228.out.log` | `F1/.cloudra/calc-235.out.log` | RC/P（calc-148）零虚频、TS 恰 1 虚频 −875.35 cm⁻¹（B5–H6 氢负转移）、IRC（calc-238）双向、端点重优化（calc-244/250）零虚频；重现先前自算值 39.36（差 0.05）；RC 结合 11.8，分离反应物口径 30.4 |
| G3 | −196.225462661978 | −196.177412040927 | 30.15 | `G3/.cloudra/calc-178.out.log` | `G3/.cloudra/calc-293.out.log` | RC/P（calc-158）零虚频、TS 恰 1 虚频 −1157.39 cm⁻¹（烯丙基 H 迁移，calc-294 独立重现同一鞍点）；IRC（calc-295）双向 40/40 点但达迭代上限，连通性由端点重优化（calc-298/299）零虚频确认；**TS 非协同**（H 先迁移，TS 处 C3–C10 3.14 Å）且具一定双自由基特征；分离反应物口径 27.57 |
| M1 | −541.249196155247 | −541.225141274564 | 15.10 | `M1/.cloudra/calc-167.out.log` | `M1/.cloudra/calc-274.out.log` | RC 零虚频（τ≈−90.4°）；交付 TS 为 τ=180° 约束弛豫后的单一软虚频（−33.15 cm⁻¹，甲基耦合）驻点——无约束 OptTS 会滑向甲基旋转赝鞍点（已判弃）；IRC（calc-275）双向收敛，端点重优化（calc-280/281）落在两个对映极小值（τ≈∓90°，互差 ~1e-6 Eh） |
| M16 | −189.533051541670 | −189.419946296876 | 70.97 | `M16/.cloudra/calc-144.out.log` | `M16/.cloudra/calc-218.out.log` | RC（syn-HCOOH）与产物（CO₂ calc-145、H₂ calc-146）零虚频、TS 恰 1 虚频 −2212.24 cm⁻¹（H 迁移坐标）、IRC 双向、端点重优化零虚频；**TS 为 anti 构象**，相对 anti 反应物口径 66.15；文献锚点 ~71 含 ZPE，与本纯电子能值不同基准 |

## 解释边界

- 上表八个**数值**都由各自 RC/TS 原始电子能算得；它们与原来的实验
  ΔG‡、ΔH‡、Ea 或别的方法/基准态的文献数值不可直接当成同一种量比较
  （M16 的文献锚点含 ZPE，是最明显的一例；E1 的浅垒是络合物强结合
  43.8 kcal/mol 下的真实结果，不是缺陷）。
- D4 为双通道题：题图单边现取 endo 值 11.30（与题源文献锚点 endo 在前
  的写法一致），exo 11.35 并列记录；两鞍点近简并（差 0.05）。
- G3、M1 的 TS 搜索走了手工链（xtb/CREST 在该节点不可用），TS 资格由
  最终频率块恰 1 虚频 + IRC 端点闭合保证，与第一批同口径。
- C1/C3（CH₃Cl 气相 SN2）按用户决定跳过（淹没能垒不可算），不在本批。
- M8 的补充分段 IRC（Slurm cloudra-137）按用户指示留在远端继续跑、
  未触碰；M8 已回填值 12.00 不变。
- 远端调度台账 `EASY_GOLD_LEDGER.md` 记录了逐题 verify 细节与中间
  状态；本文件是回填的权威汇总。
