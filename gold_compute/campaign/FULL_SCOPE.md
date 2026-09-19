# gold 能垒全量自算 —— 范围与口径（对齐用）

更新：2026-09-17 · Coordinator

## 0. 一句话
把 benchmark 里 **easy/normal/hard 全部 50 题**、**gold 机理图的每一条基元步（TS）与每一个物种极小值（起始复合物/中间体/产物）**，用**同一套方法口径**自算一遍，取代现有文献锚点，使每题 gold 带一套自洽的逐边参考能垒。

## 1. 方法口径（黄金标准，全部统一）
- 级别：**B3LYP-D3(BJ)/def2-SVP**（ORCA 6.1.1，route 例：`! B3LYP D3BJ def2-SVP def2/J RIJCOSX`）；**一律带 D3(BJ) 色散**。
- 能垒：**ΔE‡ = E(TS) − E(该步自身起点的极小值)**，**纯电子能**（无 ZPE/热校正），逐边各自相对其起点（双分子步的起点=反应物复合物）。
- 溶剂：按题面 conditions 原样读——具名溶剂→CPCM(该溶剂)；未具名相/溶剂→气相；酸催化以 [OH3+] 写入 SMILES。
- 资源：OptTS/Freq/IRC **nproc=1**（本机 MPI 析 Hessian SEGFAULT）；作业内存 **4–8 GB 总量**。
- 验收：起点/终点极小值 opt+freq **0 虚频**；TS opt+freq **恰 1 虚频**（只认最终 VIBRATIONAL 块）；**IRC 双向**（ts_guess verify, engine='orca'）；**fail-loud**——不收敛/多虚频/IRC 不通 → 该边 barrier=null + 写明原因，绝不填文献值或猜测。
- 近无能垒的质子转移/消除步（如 NY3_E3、NU5_E1、HL1_E1/E4、NO3_E1/E4、NR1_E1/E3）：约束扫描确认无内顶点 → 记 **≈0（附扫描证据）**，不虚构。

## 2. 范围与规模
| 档 | 题数 | gold 边数 | 说明 |
|---|---|---|---|
| easy | 20 | 20 | 各 1 条单步边 |
| normal | 10 | 33 | 多步机理（2–5 步/题） |
| hard | 10 | 23 | 含 7 道选择性题（成对 TS，ΔΔ 以计算裁决） |
| **合计** | **50** | **76** | **全量重算** |
| impossible | 20 | — | 不评数值，**不在范围** |

## 3. 进度
| 状态 | 题 | 边数 |
|---|---|---|
| ✅ 已完成（批次一） | F1、NU6、NY3、NU3、HA1 | 11 |
| 🔄 进行中（批次二，全机理） | HA6、HL1、NU5、NA5、HG2 | 18 |
| ⏳ 待算 | 其余 40 题 | 47 |

现有 gold 里 54 条边带文献值（口径/参考系/能量类型与本战役不一致）→ 将被自算值取代；22 条边原本为空缺。

## 4. 待算清单（batch3 起，按原子数/难度分批）
- normal（9 题 / 20 边）：NA2(5) · NA5* · NI1(2) · NO3(4) · NQ1(2) · NR1(3) · NU3* · NU5* · NU6* · NY3*（带*为已算/在算）
  → 实际待算：NA2、NI1、NO3、NQ1、NR1（16 边）
- hard（9 题 / 18 边）：HD2(1) · HE2(2) · HE3(2) · HF1(2) · HH1(1) · HI1(4)（+ HA1/HA6/HG2/HL1 已算/在算）
  → 实际待算：HD2、HE2、HE3、HF1、HH1、HI1（12 边）
- easy（19 题 / 19 边）：C1 C3 D1 D3 D4 E1 G2 G3 L1 L2 M1 M14 M15 M16 M3 M8 P2 P3 X1（F1 已算）

## 5. 交付物
1. `gold_compute/edge_barriers/computed/<TASK>.json`：逐边值 + type/frame/method/溶剂/证据路径/validation；
2. 回填 gold 边（**经生成器重跑，禁手改 JSON**）→ `uv run pytest -q tests/test_benchmark.py` 守卫绿；
3. 原始 ORCA 日志：`gold_compute/campaign/runs/<TASK>/<EDGE>/`；逐批 `summary_batchN.md`（值 + 与旧文献值差异 + 失败边清单）。

## 6. 待你/师兄拍板的 1 点
- "全部算完"是否**包含 easy 档 20 题**（各 1 条边、现有文献值）？本文按"全部=50 题"列入；若只算 normal/hard，则 easy 19 题可移出范围。
