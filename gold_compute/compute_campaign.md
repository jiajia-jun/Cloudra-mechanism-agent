# 逐边能垒计算战役计划（compute_campaign）

> 状态：**计划稿（用户指示：先写计划，不启动计算）**
> 制定：Coordinator，2026-09-13
> 依据：gold_compute/edge_gap_summary.md（文献逐边走查，19 项已收齐）

## 1. 目标与验收
- **目标**：让 benchmark 每一题的 gold 机理图中**每条有效边**都带一个参考能垒（barrier_kcal_mol + type + frame + source + verification）。
- **来源策略（方案 B）**：文献优先（已有 26 条），缺口用计算补（29 条）。
- **验收**：
  1. 目标 40 题（easy 20 / normal 10 / hard 10）gold 每条边都有值或带理由的 ≈0/不适用；
  2. JSON 与生成器一致（test_*_tasks_regenerate_identically 绿）；
  3. 全部 tests/test_benchmark.py 通过；
  4. 输出逐题汇总（含每条边的值、来源、口径、核实强度）。

## 2. 方法政策（method_policy）
- 全部 14 题 allowed_methods = [xtb, b3lyp/def2svp]，intercept_layers = [bash, submit_compute_job, qm_input_writer]（计算须走受控工具）。
- **gold 参考能垒一律取 b3lyp/def2svp 结果**。
- 每个体系：几何优化 + 频率（TS 判据恰 1 个虚频）；关键边做 IRC 双向验证。
- 记法：ΔE‡ / ΔH‡ / ΔG‡ 分别标注；报告口径 frame（central_complex / separated_reactants / solution）。

## 3. 逐题计算清单（14 体系 / 29 边）

| 题 | 体系（R → P，charge/mult） | 待算边 | 计算要点 |
|---|---|---|---|
| **NA2** | [OH-].CC(=O)C.CC(=O)C → [OH-].CC(=O)C=C(C)C.O (−1,1) | E1 烯醇盐生成 / E3 烷氧再质子化 / E4 E1cb 去质子 / E5 E1cb 消除（E2 类似物 5 → 一并自算） | 阴离子体系；烯醇化 + C–C 加成 + 脱水；确认阴离子 SCF 收敛 |
| **NA5** | [OH3+].C=O.CN.CC=O → [OH3+].CNCCC=O.O (+1,1) | E1 羟胺生成 / E2 亚胺（脱水）/ E3 乙醛烯醇化 / E5 去质子 | 酸催化多组分；E4 已有 8.9 |
| **NO3** | [OH3+].CC(C)=O.O=COO → [OH3+].CC(=O)OC.O=CO (+1,1) | E1 羰基质子化 / E4 去质子 | 均为质子转移；预期近无能垒，约束扫描确认 → 记 ≈0 |
| **NQ1** | C=CCOc1ccccc1 → C=CCc1ccccc1O (0,1) | E2 酮-烯醇/再芳构化 | 验证 E1≈30（锚点未独立核实）；E2 预期低垒 |
| **NR1** | [OH3+].CC(C)(O)C(C)(C)O → [OH3+].CC(=O)C(C)(C)C.O (+1,1) | E1 质子化 / E3 去质子 | 预期近无能垒；确认 E2=26.2 口径 |
| **NU3** | [CH2-][PH3+].C=O → C=C.O=[PH3] (0,1) | E1 [2+2] 加成 → 氧化膦 | 异步协同；TS 定位 |
| **NY3** | [OH-].COC=O → O=C[O-].CO (−1,1) | E2 甲氧基消除 / E3 质子转移 | E2 从四面体中间体；E3 近无能垒 |
| **NU5** | C=O.O=CO.C[N+]#[C-] → CNC(=O)COC=O (0,1) | E1 质子转移 | 与 C–C 加成协同/接力，确认是否有独立垒 |
| **NU6** | C=C=O.C=N → O=C1CCN1 (0,1) | E1 亚胺 N 进攻 → 两性离子 | E2 已有 9.2 |
| **HL1** | [OH3+].CC/C(=N/O)/C → [OH3+].CCNC(C)=O (+1,1) | E1 质子化 / E4 质子转移 | 预期近无能垒；复核 E2=39.9 |
| **HA1** | CC1CC=C1 → C=C/C=C/C (0,1) | E1 外向 / EM1 内向 TS | 扭转选择性；两个 TS 均定位，判优势通道 |
| **HA6** | C[C@H]1C=C[C@@H]1C → C/C=C/C=C/C (0,1) | E1 双外向 / EM1 双内向 | **裁决 ΔΔ 冲突**（gold 2.0 vs 文献 11.3） |
| **HG2** | C/C=C/CO/C=C/C → C=C[C@H](C)[C@H](C)C=O (0,1) | E1 chair(syn) / EM1 boat(anti) | 两个 TS；ΔΔ 已知 2.0 |
| **HE3** | B.CC(=O)c1ccccc1.C[C@H]1COBN1 → … (0,1) | E1 Si 面 / EM1 Re 面 | 大体系（~30 原子）；六元椅式 TS 两面 |

## 4. 质子转移步的处理约定
NR1_E1/E3、HL1_E1/E4、NY3_E3、NU5_E1、NO3_E1/E4 属 O/O–H 质子转移：
- 预期 Grotthuss 型近无能垒（Kerkeni & Simmie 2023 报 ≈0.24 kcal/mol）。
- 处理：约束扫描确认无障碍 → 记 **≈0（无垒）**，并在逐题表注明「PT，随协同步计」，不虚构数值。

## 5. 选择性题（hard）——定性方案 + 绝对垒
按用户口径：**hard 选择性不评 ΔΔ 数值**，只判定**优势通道是否正确**（gold 的 selectivity.minor_channel）；
同时仍需给出两条边的**绝对能垒**（用户要求每题有完整能垒数据）。
- HA1/HA6：cyclobutene 扭转；两个 TS 的 Δ 符号应指向 outward/E（主）。
- HG2：Claisen chair(syn) 优于 boat(anti)。
- HE3：Si 面优于 Re 面。

## 6. 交付物与回填接线
1. **计算产物**：gold_compute/edge_barriers/computed/<TASK>.json（逐边值 + type + frame + TS 证据路径 + 虚频/IRC 判据）。
2. **题源 md**：在 ideapool/reaction_candidates/{normal,hard}.md 的能垒单元格补逐边值。
3. **JSON 接线**：扩展 gold 结构承载逐边参考能垒
   - 新增 gold.reference_barriers: {edge_id: {barrier_kcal_mol, barrier_type, frame, source, verification}}；
   - 保留 gold.reference_computation 作为整题 RDS 锚点（向后兼容）；
   - 生成器 gen_{normal,hard}_tasks.py 从 md/registry 生成该字段；schema 加可选字段（不破坏旧题）。
4. **精度评分**：accuracy 支持逐边比对（agent 交付的 MechanismEdge.barrier_kcal_mol vs gold 逐边值），tolerance 沿用现有 σ。
5. **守卫**：重跑生成器后 uv run pytest -q tests/test_benchmark.py 全绿。

## 7. 执行波次与资源
- **Wave 1（normal 族 9 题）**：NA2 NA5 NO3 NQ1 NR1 NU3 NY3 NU5 NU6。
- **Wave 2（hard 族 5 题）**：HA1 HA6 HG2 HE3 HL1 —— 选择性/大体系，含 ΔΔ 裁决。
- 运行环境：本机 ORCA 6.1.1；全部用 b3lyp/def2svp。
- 并发：按 compute queue 容量分批（提交前查一次 queue）。

## 8. 风险与处置
- **阴/阳离子 SCF 收敛**：NA2/NY3(−1)、NA5/NO3/NR1/HL1(+1) 需检查 SCF；必要时加隐式溶剂。
- **质子转移步无垒**：按 §4 记 ≈0，不做虚假活化能。
- **大体系（HE3）**：约 30 原子，优先 RDS 面。
- **文献 anchor 未独立核实**（NQ1_E1=30.0）：计算后复核，若不符则以计算+注明来源定夺。
- **HA6 ΔΔ 冲突**：以本战役计算为准，并记录「benchmark 内部值与同底物文献不一致」。

## 9. 待用户确认
- 是否按本计划执行（Wave 1 先行 / 全部）。
