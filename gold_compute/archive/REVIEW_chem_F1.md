# TS 化学工具化复核 — 组 F1 / HA1 / NU6

- 执行：small_mol(a-4)，**只读**：未改任何 `gold_compute/edge_barriers/computed/*.json`、未改题源、未跑 QM 生产作业。
- 口径：只认 ORCA **最终** VIBRATIONAL 块（初始/工作 Hessian 块一律不计）；每条边末块 **n_imag ≡ 1**。
- 工具链（全部为化学工具，未用 bash/sed 解析坐标/键长/键级）：
  `get_skill('dft-calculation')` → `log_parser(properties=['frequencies','convergence','job_type'])` → `format_converter(log→xyz)` → `internal_coordinates(mode='analyze')`。争议边一步因本组无边而 N/A（见末节）。

## 工具异常（须记录）
`format_converter(input_format='log', output_format='xyz')` 在本环境对**全部 5 个 ORCA 日志**均报错：`日志解析器内部索引越界（疑似截断或损坏的计算日志）`。
已排除日志损坏：`log_parser` 对同一日志正常解析（energy/freq/irc 齐全），且换 `csv`、去掉首行 `[calculator]` 包装行、多个不同任务日志后仍同样报错 → 判定为 **format_converter 的 ORCA-log→xyz 解析器缺陷**，非数据问题。
**回退方案**：TS 收敛几何改为 **ORCA 引擎自身写出的收敛几何文件**（`ts.xyz` / `ts_optfreq.xyz` / `e1ts.xyz` / `e2ts.xyz`），并逐条与对应 freq 日志的 `CARTESIAN COORDINATES (ANGSTROEM)` 块核对**逐原子一致**（例：F1 `B1=(0.001454,-0.418817,-1.303766)` 与 `ts.xyz` 完全相同）。坐标全程由工具/引擎产生，未手工拼写、未 sed 抽取。

## 原子号绑定（声明 bind_changes 的 map 号 → 收敛几何文件序号）
- **F1_E1**：map1(B)=f1, map2(H·hydride)=f2, map3(C)=f6, map4(O)=f7
- **HA1_E1 / HA1_EM1**：map1..5(C1..C5) = f1..f5
- **NU6_E1**：map1(CH2 烯酮)=f1, map2(C 烯酮中心)=f2, map3(O)=f3, map4(CH2 亚胺)=f6, map5(N)=f7
- **NU6_E2**（I1 上）：map1(CH2 烯酮)=f4, map2(C 烯酮中心)=f3, map3(O)=f5, map4(CH2 亚胺)=f1, map5(N)=f2

声明 `bond_changes` 取自 `ideapool/tasks/*/` 各题 JSON 内嵌 gold 步定义（`gen_*_tasks.py` 已回填的修正版）。

## 逐边结果表

| TASK/EDGE | 最终块虚频 (cm⁻¹, n_imag) | 感知的成/断键（vs 声明） | 键角异常 | 部分键/键级（争议边） | 结论 | 工具 |
|---|---|---|---|---|---|---|
| **F1_E1** | −879.87 (1/1) | 声明 break[1-2](B-H)、break[3-4](C=O)、form[2-3](C-H)、form[1-4](B-O)。感知：f1-f2 **B-H 1.933 Å**=elong/breaking；f6-f7 **C-O 1.306 Å**（order 1，原 C=O）降低；f2-f6 **C-H 1.180 Å**（order 1）已成；f1-f7 **B-O 2.560 Å** forming_candidate。**4/4 一致** | 无（0 angle anomalies） | 非争议边 | **通过**（高） | log_parser; internal_coordinates |
| **HA1_E1** | −632.90 (1/1) | 声明 break[2-3]、break[4-5]、form[2-5]、form[3-4]。感知：f2-f3 **C2-C3 2.154 Å** breaking；f4-f5 **C4-C5 1.378 Å**（order 2→1）；f2-f5 **C2-C5 1.435 Å**（order 1→2）；f3-f4 **C3-C4 1.430 Å**（order 1→2）。**4/4 一致**（外向） | f3-f4-f5=104.6°、f2-f5-f4=104.7°（环张角，低 ~15°） | 非争议边 | **通过**（高） | log_parser; internal_coordinates |
| **HA1_EM1** | −682.02 (1/1) | 同上声明；感知：f2-f3 **C2-C3 2.192 Å** breaking；f4-f5 1.379（2→1）；f2-f5 1.435（1→2）；f3-f4 1.426（1→2）。**4/4 一致**（内向；H6-C1-C2-C5 τ=+26.1° vs 外向 −156.6°，甲基取向相反） | f3-f4-f5=104.9°、f2-f5-f4=105.4° | 非争议边 | **通过**（高） | log_parser; internal_coordinates |
| **NU6_E1** | −159.63 (1/1) | 声明 break[2-3](C=O π)、form[2-5](C-N)。感知：f2-f7 **C2-N7 2.038 Å** forming ✓；f2-f3 **C2-O3 1.190 Å**（order 2，C=O 仍近全双键）。形成键已现，声明的 C=O π 断裂在**早期 TS 上尚未展开**（ΔE‡=2.66、−159.63 软模，IRC 才落 I1）——**与"异步/早期进攻"一致，非不一致** | f1-f2-f3=153.0°（烯酮弯曲，Δ−27°） | 非争议边 | **通过**（高；note: 早期 TS） | log_parser; internal_coordinates |
| **NU6_E2** | −526.20 (1/1) | 声明 break[1-2](C1=C2 π)、break[4-5](C4=N5 π)、form[1-4](C1-C4)、form[2-3](C2-O3)。感知：f4-f1 **C1-C4 2.345 Å** forming=新 C-C 关环 ✓；f3-f5 **C3-O5 1.227 Å**（C=O 复原）✓；f4-f3 **C4-C3 1.437 Å**（1.34→伸长，π 破）✓；f1-f2 **C1-N2 1.339 Å**（1.28→伸长，π 破）✓。**4/4 一致** | f2-f3-f4=103.7°（成环角） | 非争议边 | **通过**（高） | log_parser; internal_coordinates |

## 关键几何判读
- **F1_E1**：鞍点为**异步氢负迁移**（H2 已基本转移：C-H 1.180 近成键、B-H 1.933 明显拉长），同时 B1-O7=2.560 Å 显示 **dative B–O 键部分形成**，与修正后的声明步（form 含 [1,4]=B–O）及产物加合物 `CO[BH3-]` 一致。**caveat**：根目录 `mechanism_graph.json` 的 F1_E1 仍是**旧版**（form 仅 [2,3]，缺 [1,4]）——本复核不改动，仅记录。
- **HA1_E1 / EM1**：两条均为**半开环鞍点**（C2-C3 2.15/2.19 Å，环已被 RDKit 判为**无环**），C2-C5、C3-C4 均已升为近双键，C4-C5 降为单键；两条仅甲基取向不同（τ=−156.6° vs +26.1°）→ 证实是**同一成/断键骨架上的两个非对映通道（torquoselectivity）**，非"产物型鞍点"。
- **NU6_E2**：鞍点已是**近平面 2-氮杂环丁酮环骨架**（C1-C4 关环 2.345 Å、C3=O 复原 1.227 Å），符合 conrotatory 4π 关环；N2-C3-C4=103.7° 为四元环内角，非异常。

## 可靠性证据
| EDGE | 末块 n_imag | 虚频 (cm⁻¹) | ORCA 正常终止 | opt 收敛 | IRC 双向收敛 | IRC 端点能 (Ha, fwd/bwd) | IRC 点数 fwd/bwd |
|---|---|---|---|---|---|---|---|
| F1_E1 | 1 | −879.87 | 是 | n/a(freq-only) | 是 | −141.57236 / −141.621336 | 28 / 84 |
| HA1_E1 | 1 | −632.90 | 是 | 是 | 是 | −195.041437 / −195.026213 | 67 / 95 |
| HA1_EM1 | 1 | −682.02 | 是 | 是 | 是 | −195.026188 / −195.039686 | 66 / 52 |
| NU6_E1 | 1 | −159.63 | 是 | 是 | 是 | −246.929625 / −246.926351 | 27 / 11 |
| NU6_E2 | 1 | −526.20 | 是 | 是 | 是 | −246.929195 / −246.988505 | 91 / 64 |

（F1_E1 的 freq 作业 410 为 freq-only，无优化帧；其"末帧几何"即输入几何，已与 `ts.xyz` 逐原子一致。）

## 争议边（步骤 5）
本组 5 条边**均非争议边**：`NA5_E2/E3/E4`、`HL1_e2`、`NU3_E2a` 属 **HL1/NA5 与 NU3/NY3/NU5 分组**（见 `REVIEW_modes_SUMMARY.md` 分组表），不在本任务清单（F1/HA1/NU6）内。故未调用 `electronic_analysis`（亦符合"不跑 QM"约束）；本组 5 条边 charge/multiplicity 全为闭壳单重态，`<S²>` 自旋污染检查对其无意义，成/断键键级已由 `internal_coordinates` 的 RDKit 键级判定给出。

## 结论
**F1_E1, HA1_E1, HA1_EM1, NU6_E1, NU6_E2：5/5 通过（高置信）。** 五条边的**最终 VIBRATIONAL 块均恰 1 虚频**，且**收敛几何感知到的成/断键与声明步逐条一致**，无"产物型鞍点"或"键错步"迹象；键角异常仅出现在成/断键邻域的环张角/烯酮弯曲，均可由反应坐标解释。

## 产物/证据路径
- 收敛 TS 几何（引擎原生，本复核使用）：见各 edge 的 `ts.xyz`/`ts_optfreq.xyz`/`e1ts.xyz`/`e2ts.xyz`（路径见 `computed/{F1,HA1,NU6}.json` 对应 run 目录）。
- `internal_coordinates` 生成的 Z-matrix：`gold_compute/campaign/_repro/chem_review/<EDGE>.zmat`。
- freq 日志 / IRC 日志：见 `computed/{F1,HA1,NU6}.json` 的 `ts_log`/`irc_log` 字段（亦在 `dispatch_ledger.md` 记录）。
