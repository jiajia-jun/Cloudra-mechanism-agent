# gold 计算战役 — Coordinator 进度台账

更新：2026-09-18（Context 压缩后重建）

## 口径（黄金标准）
- 方法 B3LYP-D3(BJ)/def2-SVP（ORCA 6.1.1 `! B3LYP D3BJ def2-SVP def2/J RIJCOSX`），nproc=1（Mac 上 MPI Hessian SEGFAULT）。
- ΔE‡ = E(TS) − E(该步起点极小值)，纯电子能，无 ZPE/热校正，逐边相对自身起点。
- 溶剂按题面 conditions（具名溶剂→CPCM；gas phase→气相）。
- 验收：两端极小值 opt+freq 0 虚频；TS 恰 1 虚频（只数 ORCA **final** VIBRATIONAL 块）；IRC 连通性用「IRC 自身最外侧帧独立 opt 到极小值再与声明端点同源比对」证明，**不为是否收敛而加长 IRC**。
- 资源：新 ORCA 作业总量 4–8 GB（默认 nproc=1 → memory_mb=4000，较小体系可用）；不再改节点注册/并发（用户要求本机算）。
- fail-loud，但 gold 阶段「尽可能不要 null」：每条边至少给 定值 / constrained_scan_upper_bound / 0(barrierless)；仅在穷尽路线后仍无证据才 null+原因。

## 已完成任务（computed/<TASK>.json）
| 题 | 边值 (kcal/mol) | 状态 |
|---|---|---|
| F1 | E1 39.4 (TS −879.9) | verified（ts_log 已修正为 calc-410 freq 作业） |
| HA1 | E1 33.04 / EM1 38.76 | verified（成对 TS，ΔΔ 5.72 方向同 gold） |
| NU6 | E1 2.66 / E2 15.72 | verified（CPCM(DCM)） |
| NU3 | E1 1.70 | partial（到声明的氧膦杂环丁烷无独立关环 TS） |
| NY3 | E2 12.5 / E3 0.0 | verified（CPCM(water)） |
| NU5 | E1 11.9(上界,unresolved)/E2 8.20/E3 0.0/E4 31.7 | E1 弱、E4 中等；E2/E3 验证通过 |
| HA6 | E1 31.24 / EM1 42.31（ΔΔ 11.06） | verified；证伪 gold 记的 2.0，与文献 11.3 一致 |
| HL1 | e1 0(无垒)/e2 23.13(真TS −304.17)/e3 7.5(上界)/e5 18.1(上界)；e4 subsumed | **已按真实 PES 重写机理图，无 null 边**（节点=5 个真极小值） |
| NA5 | E1 51.47/E2 39.83/E3 52.78/E4 4.60/E5 3.87（全 constrained_scan_upper_bound, unresolved） | **已完成**：5 条边全部有值、无 null、无文献回填；均未定位到一阶鞍点（E4 有内顶点 3.00Å=+4.6） |
| HG2 | E1(syn/boat) 29.67 / EM1(anti/chair) 26.39（ΔΔ 3.28） | **已定案**：文献裁决计算正确、gold 配对反置（chair→anti 为优势）；DOI 已写入 |

## 进行中
- 无（本轮纠错收口：HL1 重写、NA5 最小化 null、HG2 文献定案 均完成）。

## 待用户裁决 / 下一步
- gold 回填（改源→重跑 gen_easy/normal/hard→tests/test_benchmark.py 绿）：batch-2 值已变（NU5/HA6/HL1/NA5/HG2，含机理纠正与选择性 ΔΔ），是否现在执行。
- 继续批一剩余（easy/normal 约 20 题）与批二剩余题（HE2/HE3/HF1/HI1/HD2/HH1 等）。
- HL1 e3/e5、NA5 全边均为约束扫描上界而非真鞍点（松散多分子体系难定位）；如需真鞍点需额外机时。

## 待办
- 收 NA5 追加结果 → 复核（final 块虚频数、扫描证据）；HL1/HG2 已完成。
- HL1 e3/e5 目前为约束扫描上界（非严格鞍点）；e3 C–O 顶点未 bracket 到 1.60 以下——若用户要求真鞍点需补机时。
- 校核全部产物后回填 gold（改源→重跑 gen_easy/normal/hard→tests/test_benchmark.py 绿）+ 刷新 review 树。
- 继续批一剩余题（easy/normal 约 20 题）与批二剩余题。
- 已提 issue：#37（多片段含 sp2 立体 SMILES 崩共享 builder，已修）、#39（ts_prepare guess 阶段硬阻塞无 fallback）。
