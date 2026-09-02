# 参考答案计算任务单 — 计算者 P1（工作分 ~421）

> 依据：`paper/reference_calc_plan.md`（能垒标定分工），任务定义见 `ideapool/tasks/<tier>/<task_id>.json`。
> **统一口径**：全档以 **MACE-OMol25** 为唯一物理计算金标准（单引擎，2026-08-25 决策）；参考值=我们自算标定，
> **不把文献二手数字当 ground truth**。`xTB` 仅作快速构象/结构预筛与 TS 猜测辅助，**不计入参考能垒**。
> 参考能垒参考系统一 `central_complex`（TS 相对反应物/离子-偶极络合物）；能垒类型按题目实际定义（ΔE‡ 缺省，其余按字段）。

---

## 0. 开工前提（必须先确认，否则计算无法进行）

本机沙箱**未安装** MACE-OMol25 / Gaussian 计算栈（无 `g16` 二进制、无 `g16-mlips` 插件、无 `mace` python 包、无 `xtb` 二进制）。
- 计算者必须在**装有 MACE-OMol25 + Gaussian (g16) + g16-mlips** 的机器上执行。
- 权重文件（OMol25, Levine 2025）已在仓库：`ideapool/mlp_benchmark/models/md_omol25/2025_levine_omol25/2025_levine_omol25.md`。
- MACE 经 Gaussian `external="mace"`（g16-mlips 插件）驱动，见 `cloudra/skills/dft-calculation/references/mlip-gaussian-external.md`。

---

## 1. 单步计算协议（每题、每条边都要走完）

对 **每条 elementary step**（即每个 TS）执行：

1. **构象/结构预筛**（conformer_search，rdkit 或 xtb backend）：对反应物络合物（central_complex 基准）找预组织反应构象，必要时用 `distance_filters` 框住键形成/断裂原子间距；产物/中间体同理。
2. **TS 猜测**（ts_guess）：优先 `interpolate`（reactant↔product xyz），若歧义则 `scan_prepare`+`scan_parse` 扫一个坐标找最高点作为 TS guess。
3. **TS 优化 + 频率**（qm_input_writer 生成 Gaussian 输入，submit_compute_job `job_type="gaussian"`）：
   - `method="external"`, `basis_set=""`, `extra_keywords='external="mace"'`, `charge`/`multiplicity` 从 JSON 引用**必须设对**。
   - task_type：`[{"opt":"ts,noeigen,calcfc"},{"freq":None}]`。（MLIP PES 振荡不收敛时退 `nomicro`，见 skill）。
   - **验收**：log_parser 读频率，`n_imag==1`（排除 <100 cm^-1 的伪低频）→ 一阶鞍点。
4. **双向 IRC**（ts_guess `verify` 或两次 IRC 作业）：确认 TS 正确地连接 **reactant⟷product / intermediate** 两端。**仅"找到鞍点"不算完成**，必须 IRC 连通性通过。
5. **提取能垒**（log_parser / thermo_analysis）：ΔE‡ = E(TS) − E(central_complex)。需要 ΔG‡ 时叠加 RRHO 热校正。每条边记录；多步网络记 **RDS** 作为 `barrier_kcal_mol`。

---

## 2. 回填格式（每题最后写回 `ideapool/tasks/<tier>/<task_id>.json` 的 `gold`）

```jsonc
"reference_computation": {
  "level_of_theory": "MACE-OMol25",
  "barrier_kcal_mol": <float>,               // RDS / 唯一 TS 能垒，ΔΔ 不放进这里
  "barrier_type": "ΔE‡",                     // 按实际：Ea/ΔH‡/ΔE‡/ΔG‡；源数据未注明则保持 null
  "barrier_reference": "central_complex",
  "verification": "computed_by_us",
  "reference_doi": "<原值保留,作交叉核对,不作 ground truth>",
  "computed_by_us": true
}
```

- **hard 侧额外**：`gold.selectivity` 需计算**主 + 副两条通道 TS**，并回填
  ```jsonc
  "selectivity": {
    "spread_kcal_mol": <副TS能垒 − 主TS能垒, 同一反应物络合物基准>,
    "spread_type": "ΔE‡" / "ΔG‡",
    "minor_channel": "<原字符串保留>",
    "verification": "computed_by_us",
    "computed_by_us": true
  }
  ```
  绝不要把 ΔΔ 塞进 `barrier_kcal_mol`。
- 多步网络：**建议逐边记录**能垒（便于 graph/self-consistency 层校验）。

---

## 3. P1 分配题单（task_id 列表，能垒标定）

> 工作分模型：`题分 = Σ(TS数 × 体系重原子数)`，family 为不可分单元。P1 总计 ~421。

### normal（13 题，最重）
| family | task_id | TS 数 | 备注 |
|:--|:--|:--|:--|
| A | NA1, NA2, NA4, NA5, NA7 | 3+5+5+5+3 | NA1=试点题，最重族 |
| U | NU1, NU5, NU6, NU7 | 3+4+2+1 | |
| X | NX1, NX2, NX3, NX4 | 1+1+1+1 | |

### hard（13 题，立体化学主力）
| family | task_id | TS 数 | 选择性 |
|:--|:--|:--|:--|
| E | HE1, HE2, HE3 | 2+2+2 | 有 |
| I | HI1, HI4 | 4+2 | 有 |
| G | HG1, HG2 | 2+2 | 有 |
| J | HJ1, HJ2, HJ4 | 1+2+1 | 无 |
| H | HH1 | 1 | 无 |
| B | HB7 | 2 | 无 |
| K | HK1 | 2 | 无 |

### easy（17 题）
| family | task_id |
|:--|:--|
| M | M1, M10, M12, M14, M15, M16, M3, M6, M8 |
| L | L1, L2 |
| C | C1, C2, C3 |
| T | T1, T3 |
| X | X1 |

（M 族含 1 个大体系 M1，需留意构象与计算成本。）

---

## 4. impossible I/S「确不可算」验证（P1 主责，P0 交叉复核）

> 本档 40 题**不走能垒计算**（拒答验证档）。参考答案本质 = **确认 I 题确不可算 + S 兄弟题可达对照**。
> 每对共享同一反应；I 题用 `accessible=False` 标记不可信路径（`expected_outcome=correct_refusal`），
> S 题是单参考可达对照（`expected_outcome=mechanism_found`）。判据来自 `rubric.impossible_case`
> （`evidence_strength` ironclad/gray_zone，`wrongly_solve_penalty` high/medium/low）。

### 4.1 每对 I/S 的执行步骤

对每个 **I 题（accessible=False）** 标的不可信物种/TS，执行：

1. **S 兄弟题对照验证（可达性证明）**：用 MACE-OMol25 跑 **S 题**（同一族、单参考可算）的 TS 搜索 + 频率 + 双向 IRC，
   确认**能正常走通**（n_imag==1 + IRC 前后连通）。这证明"题目本身不难、该族用 MACE 可算"——**这是拒答信号成立的对照前提**。
2. **I 题不可算性诊断**：对 I 题标注 `accessible=False` 的节点/TS，做**电子结构诊断**，坐实单参考方法失效：
   - 用 `electronic_analysis`（open-shell/多参考代理：<S^2>、Mulliken 自旋布居、IBO Lewis 图）检查**强静态关联/近简并双自由基特征**；
   - 尝试单参考 TS 优化：若 MACE-OMol25 在该区输出**错误态序、虚假对称破缺、n_imag≠1、或能垒偏差数十 kcal/mol**、
     或 SCF/优化不收敛——即坐实"单参考不可信"。
   - 引用 `impossible.md` 中该题的诊断证据（T1/D1/%TAE/C0²/y0 标注）作为佐证引文。
3. **判拒答**：若 I 题路径的确在 MACE-OMol25/单参考下不可信，则记录：
   - 该 I 题应**正确拒答**（`expected_outcome=correct_refusal`）；
   - 给出所需的高等级方法（CASSCF/CASPT2/MRCI）；
   - 回填 `impossible_case` 的 `evidence_strength`（ironclad 题有文献多参考背书；gray_zone 题需连同证据强度说明）。
   - 若发现某题其实单参考可算（accessible=False 判定过强），**标记回退**并说明理由——不要为了凑拒答而强行判不可算。

### 4.2 P1 负责的 impossible I/S 对（10 对）

| I 题 | S 兄弟（对照） | 关键不可信节点 |
|:--|:--|:--|
| IA11 | SA11 | R、TS |
| IA7 | SA7 | TS、P |
| IA8 | SA8 | R、TS |
| IE2 | SE2 | —(单节点/电子态) |
| IG7 | SG7 | —(单节点) |
| IH8 | SH8 | —(单节点) |
| II2 | SI2 | —(单节点) |
| II8 | SI8 | —(单节点) |
| IJ6 | SJ6 | —(单节点) |
| IJ7 | SJ7 | —(单节点) |

> 另 10 对（IA1/IA5/IA9/IB5/IC3/ID2/IF3/IG6/IG8/IH7 + S 兄弟）由 P0 承担（见任务单 P0 §5）。
> 跨档校准：impossible 档主指标是**跨档拒答 precision/recall**（不是单档拒答率）——本题拒答 × 兄弟题作答的合取才是信号。P1 复核 P0 的 barrier 口径，P0 复核 P1 的 S 可达性。

---

## 5. 执行顺序（P1）

1. **试点**：先跑 **NA1**（normal A 最重族），跑通「TS 搜索 → n_imag==1 → 双向 IRC → 提取能垒 → 回填 JSON」全流程，产出 1 个 `computed_by_us=True` 样例。
2. normal A→U→X；hard E→I→G→J→H→B→K；easy M→L→C→T→X。
3. 再做 impossible I/S 确不可算验证（第 4 节）。
4. 每完成一个 family，把进度与数值记到本文件下方或 `paper/reference_answer_progress.md`。
