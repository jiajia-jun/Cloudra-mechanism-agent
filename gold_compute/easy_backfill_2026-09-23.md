# Easy 存量十题自算参考值回填（2026-09-23）

本次依用户要求回填十道已有 Easy 题。数值均为气相 ORCA 5.0.2
B3LYP-D3(BJ)/def2-SVP（def2/J、RIJCOSX）的**电子能垒**：
`(E_TS - E_RC) × 627.5095 kcal mol⁻¹ Eh⁻¹`，无 ZPE、热修正或溶剂修正。
题源 `ideapool/reaction_candidates/easy.md` 是生成器输入；生成的
`ideapool/tasks/easy/*.json` 承载评分用 `barrier_kcal_mol`。这组回填是
`gold_compute/README.md` 所允许的存量题择机回填，不属于新策展题目队列。

原始计算在 gold 节点 `/public/home/yyywaa/cloudra_workspace/`；对应文件
已备份在本机 `gold_compute/remote_backups/2026-09-23/`。以下证据路径
相对该备份目录。能量逐项由原始 ORCA 日志最后一条
`FINAL SINGLE POINT ENERGY` 重读；绝对 Hartree 值不采用旧 cclib
换算结果。详见备份中的 `ENERGY_AUDIT.md`、`TS_AUDIT.md`。

| 题 | RC / Eh | TS / Eh | ΔE‡ / kcal/mol | RC 日志 | TS 日志 | 证据状态 |
|---|---:|---:|---:|---|---|---|
| M3 | −56.474317748533 | −56.464857671437 | 5.94 | `M3/.cloudra/calc-49.out.log` | `M3/.cloudra/calc-66.out.log` | 双端极小值、TS 与路径复核通过 |
| M14 | −191.669137874792 | −191.654723451876 | 9.05 | `M14/m14-orca-122762307.out` | `M14/.cloudra/calc-39.out.log` | s-trans 起点；IRC 截断，双端重优化为极小值 |
| M15 | −205.454886105073 | −205.431712349738 | 14.54 | `M15/.cloudra/calc-43.out.log` | `M15/.cloudra/calc-58.out.log` | 双端极小值、TS 与路径复核通过 |
| P2 | −193.846685527787 | −193.804373869665 | 26.55 | `P2/.cloudra/calc-46.out.log` | `P2/.cloudra/calc-63.out.log` | IRC 截断，双端重优化为极小值 |
| L1 | −155.763103580296 | −155.707059694970 | 35.17 | `L1/orca-L1-122762304.out` | `L1/.cloudra/calc-41.out.log` | IRC 截断，双端重优化为极小值 |
| M8 | −235.562388077737 | −235.543265117142 | 12.00 | `M8/.cloudra/calc-51.out.log` | `M8/.cloudra/calc-82.out.log` | IRC 双向收敛；B 端 TightOpt+Freq 至 twist-boat 零虚频极小值 |
| D1 | −234.264165493590 | −234.234155223765 | 18.83 | `D1/.cloudra/calc-100.out.log` | `D1/d1-orca-122769869.out` | **路径端点仍部分**：直接 IRC 反应物端优化未收敛；另有独立零虚频络合物 |
| L2 | −233.090090596594 | −233.042649842153 | 29.77 | `L2/.cloudra/calc-90.out.log` | `L2/.cloudra/calc-88.out.log` | all-trans 起点；IRC 端对应 s-cis 反应构象，双端重优化为极小值 |
| G2 | −188.977442257891 | −188.976059167820 | 0.87 | `G2/.cloudra/calc-106.out.log` | `G2/.cloudra/calc-101.out.log` | **产物端仍部分**：vdW 加合物有 −7.6 cm⁻¹ 软虚频；分离 N₂、乙烷各零虚频 |
| P3 | −270.157705733707 | −270.109532752385 | 30.23 | `P3/p3-orca-122721135.out` | `P3/.cloudra/calc-115.out.log` | 题设伸展起点；IRC 连接折叠起点对应 31.59，不能混用 |

## 解释边界

- 上表十个**数值**都由各自 RC/TS 原始电子能算得；它们与原来的实验
  ΔG‡、ΔH‡、Ea 或别的方法/基准态的文献数值不可直接当成同一种量比较。
- D1、G2 保留已算得的电子能差供题库比较，但不得把端点证据写成严格
  Gate 1/2/3 全过。当前 Easy `TaskSpec` 只有数值锚，没有逐边
  verification 字段；这两题的路径限制必须随参考答案一并展示。
- M8 的补证据位于
  `M8/tight_endpoint_20260923/endB_tight.orca.out`、`.hess`、`.xyz`。
  它从原 IRC B 末端坐标启动，零虚频终态与原 twist-boat 结构
  RMSD 0.0033 Å。新端点采用 TightOpt+DefGrid3，不能把原常规优化的
  boat 鞍点说成合格端点。另一路分段 IRC 仍在计算，是额外复核。
- `RESULTS/SUMMARY.md` 是原始报告，含过时的“全过”表述；应以本文件及
  两份审计记录为准。
