# gold 计算战役 · 总看板（四道替换题）

> 刷新：2026-10-18 07:41:41
> 裁决台账：`gold_fill_20261018/DECISION_LOG.md`

## 交付状态

| 题 | 反应 | REPORT.txt | mechanism_graph.json | 已填能垒 | 各边 |
|---|---|---|---|---|---|
| **NR1** | 甲酰胺气相热脱水 NH2CHO → HCN + H2O | 16890 B | 6163 B | **4/4** | e1=46.32, e2=22.8, e3=7.25, e4=64.93 |
| **NY3** | 异氰酸单水中性水解 HNCO+H2O → NH3+CO2 | 27060 B | 14059 B | **3/3** | e1=36.79, e2=11.06, e3=43.13 |
| **HI1** | threo/erythro 胺氧化物 Cope 消除 | 15306 B | 5830 B | **2/3** | HI1_e1_erythro_syn=12.82, HI1_e2_threo_syn=14.74, HI1_e3_erythro_regio=null |
| **HL1** | HCNO + 降冰片烯两面 [3+2] 环加成 | 23989 B | 14705 B | **2/2** | e_exo=11.89, e_endo=6.95 |

## 说明

「已填能垒」= `mechanism_graph.json` 里 `barrier_kcal_mol` 非 null 的边数。
**本表只反映文档里写了什么，不判断这些数值是否合格**——合格性由各题 REPORT 的证据链与项目判据决定。
HI1 / HL1 的边已建好但 `barrier=None`，表示尚未写入能垒（不是「算不出来」的结论）。

## 在跑

- #1292 4c `refine.gjf`
- #1328 4c `reactant_opt.gjf`
- #1329 4c `reactant_opt.gjf`

算力 **12/32**
