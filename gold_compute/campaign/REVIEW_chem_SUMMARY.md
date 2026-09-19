# TS 化学工具化复核 — 汇总（4 组）

更新：2026-09-19（Coordinator 汇总）。审稿人均为独立新会话 small_mol(a-4)，只读；**未改任何 computed/*.json 或题源，未跑 QM 生产作业**。

## 方法（工具化，非文本切割）
get_skill(dft-calculation) → log_parser(frequencies/convergence/job_type，只认**最终** VIBRATIONAL 块) → format_converter(log→xyz) → internal_coordinates(mode='analyze', 声明的成/断键 watch_pairs) → 争议边 electronic_analysis(PySCF B3LYP/def2-SVP，Mayer 键级/自旋)。

## 结果：23 条有 TS 日志的边
| 组 | 边数 | 通过 | 备注 |
|---|---|---|---|
| F1/HA1/NU6 | 5 | 5 | F1 异步氢负迁移+部分 B–O；HA1 真 torquoselectivity 对；NU6 早期 TS/4π 关环 |
| NU3/NY3/NU5 | 6 | 6 | NU3_E2a 经键级确认是真 O→P-H/P-O 局域鞍点（非纯质子/非旁观） |
| HA6/HG2 | 4 | 4 | 4π 顺旋开环、[3,3] 协同；闭壳 <S²>=0 |
| HL1/NA5 | 8 | 6+2 存疑 | 见下 |

**逐条（最终块虚频 | 判定）**
- 全部 23 条：final 块**恰 1 虚频**，opt_converged、normal_termination；虚频值与 computed/*.json 逐一吻合。
- **HL1_E2**（−304.17）通过：C2–C3 断(BO 0.519)/C3–N5 成(BO 2.260)/C2–N5 incipient(0.336) = 真 Beckmann 鞍点（含 ~9% 旁观水，次要）。
- **HL1_E1**（−1791.63）几何确为 O→N 质子转移（非声明步）；**HL1_E5**（−653.06，酰胺+H₃O⁺）与 **HL1_E3m**（−63.55，nitrilium+2H₂O）经键级确认无重原子反应键 → 支持 JSON 的 null/降级。
- **NA5_E2**（−283.64）通过：H2 飞行于 O1(1.218)–O8(1.201) 之间，BO 0.502/0.520 对称部分键 = 氨基甲醇-O 质子化子步鞍点。
- **NA5_E3**（−2140.76）通过：成 O12–H14(1.315)/断 C10–H14(1.501)，且 C10–C11 BO 1.349、C11–O12 BO 1.429 → **是真烯醇化 1,3-H 迁移鞍点（伴显著重原子键级变化）**，69.94 kcal 高垒与刚性模自洽（此前"纯质子模"疑虑解除；但模型为无碱 1,3-H 迁移，仍偏高）。
- **NA5_E4**（−363.63）**存疑**：C1–C10 incipient BO 0.581（真部分键）但两片畸变、IRC 两端均回 I3 → approach/preorganisation 鞍点，**productive I3→I4 未证**；保留 JSON 的 unverified。
- **NA5_E5**（−56.48）**存疑/不通过**：软质子模、无重原子反应坐标 → 非 productive。

## 结论
化学工具化复核**全部支持**先前结论：有值真鞍点的成/断键与声明步一致；无"旁观软模被当有值 TS 售出"。新增量化证据澄清了 3 个争议点：**NA3_E2a 真鞍点**、**NA5_E3 真烯醇化鞍点（伴重原子键级变化）**、**NA5_E4 仅 approach 鞍点**。

## 需记录的两个问题
1. **工具 bug**：format_converter(input_format='log', output_format='xyz') 对 **全部 ORCA 日志**（含普通 Opt+Freq）报"内部索引越界"（4 组一致复现，log_parser 同日志正常）。回退方案：用 ORCA 引擎自写的最终几何 sidecar .xyz（已验能量逐位一致、由日志 INPUT FILE 同名绑定）。→ **建议提 issue**。
2. **NA5 原子号未绑定**：NA5 几何文件的原子序与 mechanism_graph.bond_changes 的声明编号不一致（如 E2 的氨基甲醇 O 声明 O4、文件序 O8）→ NA5 各边按元素/邻接定性对照（HL1 可对应）。复核结论不受影响，但 gold 的 bond_changes 原子号与几何来源需对齐。

## 报告位置
gold_compute/campaign/REVIEW_chem_{F1,NU3,HA6,HL1}.md
