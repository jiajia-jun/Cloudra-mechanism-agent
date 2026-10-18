# gold 计算战役 · 总看板（四道替换题）

> 同步master：2026-10-18；来源gold-finish-artifacts/f24f9d3d。状态见[REFERENCE_STATUS.md](REFERENCE_STATUS.md)。
> 裁决台账：`gold_fill_20261018/DECISION_LOG.md`

## 交付状态

| 题 | 反应 | 报告值覆盖 | 各边 |
|---|---|---|---|
| **NR1** | 甲酰胺气相热脱水 NH2CHO → HCN + H2O | **4/4** | e1=46.32, e2=22.8, e3=7.25, e4=64.93 |
| **NY3** | 异氰酸单水中性水解 HNCO+H2O → NH3+CO2 | **3/3** | e1=36.79, e2=11.06, e3=43.13 |
| **HI1** | threo/erythro 胺氧化物 Cope 消除 | **2/3** | HI1_e1_erythro_syn=16.62, HI1_e2_threo_syn=15.85, HI1_e3_erythro_regio=null |
| **HL1** | HCNO + 降冰片烯两面 [3+2] 环加成 | **2/2** | e_exo=11.89, e_endo=6.95 |

## 说明

「已填能垒」= `mechanism_graph.json` 里 `barrier_kcal_mol` 非 null 的边数。
**本表只反映文档里写了什么，不判断这些数值是否合格**——合格性由各题 REPORT 的证据链与项目判据决定。
四题已有11条非空报告值；HI1区域异构边仍null。缺可信参考项按最新用户要求标为本轮缺测，不再列待算；报告数值和正式Gold入库分开记录。

## 原机交付时的作业快照（不是当前实时状态）

- #1292 4c `refine.gjf`
- #1328 4c `reactant_opt.gjf`
- #1329 4c `reactant_opt.gjf`

算力 **12/32**
