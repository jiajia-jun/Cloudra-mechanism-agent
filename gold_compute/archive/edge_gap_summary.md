# 逐边能垒缺口汇总（2026-09-13 收尾）

来源：逐边文献 swarm（group grp_fb61a32a712f4ed3a0d3ecaf2ccf5d9b，19 项，全部终端）
落盘：gold_compute/edge_barriers/*.json（19 文件）
口径：方案 B —— 文献优先，缺口用计算补（gold 值取 b3lyp/def2svp）
范围：normal 10 题 + hard 9 题（选择性族）+ easy F1

## 统计
- 逐边总数：55
- 已有文献值：26
- 缺值：29

## 已有文献值（26 条）
| edge | 值 | frame | 来源/核实 |
|---|---|---|---|
| NA2_E2 | 5 | 类似物(Li 烯醇盐) | Pratt 2005, partial |
| NA5_E4 | 8.9 | central_complex | Petrović 2018, partial(类似底物) |
| NI1_E1 | 3.5 | central_complex | Hall & Smith 1998, partial |
| NI1_E2 | 26.7 | central_complex | Hall & Smith 1998, partial |
| NO3_E2 | 14.3 | own-min | Mora-Diez 2009 OBC, verified |
| NO3_E3 | 11.4 | protonated Criegee | Mora-Diez 2009 OBC, verified |
| NQ1_E1 | 30.0 | central_complex | Eur.JOC 2012 (benchmark anchor), unverified |
| NR1_E2 | 26.2 | central_complex | Yamabe 2007 JCC, partial |
| NU3_E2 | 19.1 | central_complex | Bofill 2024 CEJ, partial(Me3P 类似物) |
| NY3_E1 | 15.5 | central_complex | Pliego & Riveros 2002, verified |
| NU5_E2 | 19.9 | separated reactants(DCM) | Ferdeghini 2025 JOC, verified(类似物) |
| NU5_E3 | 16.6 | separated reactants(DCM) | Ferdeghini 2025 JOC, verified |
| NU5_E4 | 13.8 | central_complex | Santos 2026 ACS Omega, verified |
| NU6_E2 | 9.2 | solution DCM rel zwitterion | Komjáti 2018, verified(类似物) |
| HE2_E1 | 16.1 | central_complex | Neufeldt 2014 JOC (SI), verified |
| HE2_EM1 | 17.3 | central_complex | Neufeldt 2014 JOC (SI), verified |
| HF1_E1 | 9.2 | separated reactants | Koskowich 2008 JOC, partial(类似物) |
| HF1_EM1 | 10.9 | separated reactants | Koskowich 2008 JOC, partial |
| HI1_E1 | 19.2 | own-min | Yu/Blyth/Coote 2022, verified(类似底物) |
| HI1_E2 | 9.1 | enamine-aldehyde complex | Yu/Blyth/Coote 2022, verified |
| HI1_E3 | 16.9 | C-C adduct-water | Yu/Blyth/Coote 2022, verified |
| HI1_EM1 | 11.5 | enamine-aldehyde complex | Yu/Blyth/Coote 2022, estimated |
| HL1_E2 | 39.9 | central_complex | Yamabe 2005 JOC (SI), verified |
| HL1_E3 | 18.0 | central_complex | Ronchin 2008, verified(类似物) |
| HL1_E5 | 30.5 | gas phase | Kerkeni & Simmie 2023, verified(类似物) |
| F1_E1 | 30.4 | separated reactants | Eisenstein/Schlegel/Kayser 1982 JOC, verified(full text) |

## 缺值（29 条）→ 计算补
**normal 族**
- NA2: E1(烯醇盐生成) E3(再质子化) E4(E1cb 去质子) E5(E1cb 消除)  —— 注：E2 亦仅类似物，建议整题自算
- NA5: E1(羟胺生成) E2(亚胺生成) E3(烯醇化) E5(去质子)
- NO3: E1(羰基质子化) E4(去质子)
- NQ1: E2(酮-烯醇/再芳构化)
- NR1: E1(质子化) E3(去质子)
- NU3: E1([2+2] 加成→氧化膦)
- NY3: E2(甲氧基消除) E3(质子转移)
- NU5: E1(质子转移)
- NU6: E1(亚胺 N 进攻→两性离子)
**hard 族（选择性）**
- HA1: E1 / EM1（3-甲基环丁烯扭转选择性，无绝对值）
- HA6: E1 / EM1（3,4-二甲基环丁烯；gold ΔΔ=2.0 与文献 11.3 冲突）
- HL1: E1 / E4（质子转移）
- HG2: E1 / EM1（Claisen chair/boat，无绝对值）
- HE3: E1 / EM1（CBS 还原，无绝对值）
- （HA1 文件内存在一条空 edge 条目，计算前修正）

## 冲突/待复核
- HA6：gold selectivity.spread = 2.0 kcal/mol（未核实）vs 同底物文献 11.3 kcal/mol（Morales-Bayuelo 2013）→ 需计算裁决。
- 多条 normal/hard 值来自类似底物，逐边表已标 note。

## 计算战役建议
1. 每个缺值题 = 一个体系，用 b3lyp/def2svp 做 opt+freq，TS/扫描定位每步鞍点，得到逐边 ΔE‡；
2. 质子转移步（NR1_E1/E3、HL1_E1/E4、NY3_E3、NU5_E1、NO3_E1/E4）：预期近无能垒，用约束扫描确认无障碍并通过 → 记 ≈0（并注明）；
3. 选择性题（HA1/HA6/HG2/HE3）按定性方案：只裁决优势通道，绝对值同时给出。
