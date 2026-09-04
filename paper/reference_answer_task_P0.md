# 参考答案计算任务单 — 计算者 P0（工作分 ~420）

> 依据：`paper/reference_calc_plan.md`（能垒标定分工），任务定义见 `ideapool/tasks/<tier>/<task_id>.json`。
> **统一口径**：全档以 **MACE-OMol25** 为唯一物理计算金标准（2026-08-25 决策）；参考值=我们自算标定，
> **不把文献二手数字当 ground truth**。`xTB` 仅作快速构象/结构预筛与 TS 猜测辅助，**不计入参考能垒**。
> 金标准指**模型**唯一；**驱动层二选一**：本机走 **ORCA `ExtOpt`（`%method ProgExt`→mace）**，
> 装有 g16+g16-mlips 的机器可走 **Gaussian `external="mace"`** —— 两者产出等价（同一 MACE-OMol25），见 §0。
> 参考能垒参考系统一 `central_complex`（TS 相对反应物/离子-偶极络合物）；能垒类型按题目实际定义（ΔE‡ 缺省，其余按字段）。

---

## 0. 开工前提（环境已就绪，先读再算）

**本机计算栈（2026-09-03 复查，H2O Opt/NumFreq 端到端已跑通；同 P1 任务单 §0，详见 `paper/reference_answer_progress.md`「计算栈验证」与 `deploy/mace_omol25_orca_external_setup.md`）：**

| 成分 | 状态 | 配置 |
|:--|:--|:--|
| ORCA 6.1.1 | ✅ | `/Users/cloudrayyy/opt/orca_6_1_1/orca`（openmpi-4.1.8 在 `~/opt/openmpi-4.1.8/bin`） |
| `orca-mlips-mace` 1.2.1 | ✅ | chemai env；PATH 生成 `mace`/`orca-mlips-mace` |
| `mace` python 包 0.3.16 | ✅ | chemai env；`ProgExt` 必须写**完整解释器路径** `/Users/cloudrayyy/miniconda3/envs/chemai/bin/mace`（只写 `mace` 报 File not found） |
| MACE-OMol25 权重 | ✅ | `/Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model`（422 MB） |
| `xtb` | ✅ | chemai env，仅构象/TS 猜测预筛 |
| `ase` 3.29.0 | ✅ | MACE-ASE 直驱为**备选**（RFO 鞍点优化） |
| g16 + g16-mlips | ❌ 缺失 | 本机 **无** g16 → Gaussian `external="mace"` 路线本机不可用 |

- 运行环境变量：`KMP_DUPLICATE_LIB_OK=TRUE`（libomp 冲突）+ PATH 注入 ORCA/openmpi 目录，经 `calculator.sh`
  检测 `ExtOpt/ProgExt` 自动注入（`submit_compute_job job_type="orca"` 路径），交互式探针需自行 export。
- **权重陷阱**：仓库内 `ideapool/mlp_benchmark/models/md_omol25/2025_levine_omol25/2025_levine_omol25.md`
  实为 **arXiv:2505.08762 论文文本，不是模型权重**；真权重见上表。
- 引擎写法与输入模版：`cloudra/skills/dft-calculation/references/mlip-gaussian-external.md`（Gaussian / ORCA 双引擎版）。

---

## 1. 单步计算协议（每题、每条边都要走完）

对 **每条 elementary step**（即每个 TS）执行：

1. **构象/结构预筛**（conformer_search，rdkit 或 xtb backend）：
   - 对反应物络合物（central_complex 基准）找**预组织反应构象**，必要时用 `distance_filters` 框住键形成/断裂原子间距。
   - 产物/中间体同理。
2. **TS 猜测**（ts_guess）：
   - 优先 `interpolate`（reactant↔product xyz），若歧义则 `scan_prepare`+`scan_parse` 扫一个坐标找最高点作为 TS guess。
3. **TS 优化 + 频率**（qm_input_writer 生成 ORCA 输入 `engine="orca"`，submit_compute_job `job_type="orca"`）：
   - `method="ExtOpt"`, `basis_set=""`（→ `! ExtOpt …`），`task_type=[{"opt":"ts"}]`（→ `! OptTS`）；
     `orca_blocks` 携带 `%method` 块（`ProgExt` 完整解释器路径 + `Ext_Params "--model <权重> --device cpu --dtype float64"`，值见 §0）；
     `charge`/`multiplicity` 从 JSON 引用**必须设对**。
   - **频率一律数值**：MACE 无解析 Hessian —— `task_type` 留空、`extra_keywords="NumFreq"`（`! ExtOpt NumFreq`）；
     解析 `Freq` 会请求解析 Hessian 而失败。
   - **验收**：log_parser 读频率，`n_imag==1`（排除 <100 cm^-1 的伪低频）→ 一阶鞍点。
   - Gaussian 环境替代写法：`engine="gaussian"` + `method="external"` + `basis_set=""` +
     `extra_keywords='external="mace"'` + `task_type=[{"opt":"ts,noeigen,calcfc"},{"freq":null}]`（MLIP PES 振荡时退 `nomicro`）。
   - MLIP PES 反复振荡不收敛时**回退标准 DFT 路径**（skill Fallback discipline），不要无限调参。
4. **双向 IRC**（ts_guess `verify` 或两次 IRC 作业）：
   - 确认 TS 正确地连接 **reactant⟷product / intermediate** 两端。**仅"找到鞍点"不算完成**，必须 IRC 连通性通过。
   - **试点必探**：`ExtOpt OptTS` / `ExtOpt` IRC 尚未端到端验证（只验证过 Opt/NumFreq）——NH1 试点先探明；
     不通则改用 **ASE 直驱 MACE**（MACECalculator + RFO 鞍点优化 + 双向 IRC）作为同等级金标准路径。
5. **提取能垒**（log_parser / thermo_analysis）：
   - 电子能垒 ΔE‡ = E(TS) − E(central_complex)。需要 ΔG‡ 时叠加 RRHO 热校正。
   - **每条边记录**；多步网络记 **RDS（最高能垒步）** 作为该题 `barrier_kcal_mol`。

---

## 2. 回填格式（每题最后写回 `ideapool/tasks/<tier>/<task_id>.json` 的 `gold`）

```jsonc
"reference_computation": {
  "level_of_theory": "MACE-OMol25",          // 原为 "literature anchor (see reference_doi)" 或 "" → 改为实际引擎
  "barrier_kcal_mol": <float>,               // RDS / 唯一 TS 能垒（原文献值被替换），ΔΔ 不放进这里
  "barrier_type": "ΔE‡",                     // 按实际：Ea/ΔH‡/ΔE‡/ΔG‡；源数据未注明则保持 null
  "barrier_reference": "central_complex",    // 统一口径
  "verification": "computed_by_us",          // 原 verified/partial/unverified → 改 computed_by_us
  "reference_doi": "<原值保留,作交叉核对,不作 ground truth>",
  "computed_by_us": true                     // 原 false → true
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
- 多步网络：**建议逐边记录**能垒（便于 graph/self-consistency 层校验）——每条边对应的 TS 能垒写进边或单独日志，RDS 值写 `barrier_kcal_mol`。

---

## 3. P0 分配题单（task_id 列表）

> 工作分模型：`题分 = Σ(TS数 × 体系重原子数)`，family 为不可分单元。P0 总计 ~420。

### normal（17 题，最重）
| family | task_id | TS 数 | 备注 |
|:--|:--|:--|:--|
| H | NH1, NH2, NH3, NH5 | 4+4+4+1 | NH1=试点题，最重族 |
| R | NR1, NR2, NR3 | 3+5+1 | |
| O | NO2, NO3, NO4, NO5 | 1+4+1+3 | |
| I | NI1, NI3 | 2+5 | |
| Y | NY2, NY3 | 4+3 | |
| Q | NQ2, NQ3 | 1+3 | |

### hard（7 题，立体化学核心）
| family | task_id | TS 数 | 选择性 |
|:--|:--|:--|:--|
| L | HL1, HL4 | 5+2 | 无 |
| A | HA1, HA2, HA6 | 2+2+2 | 有（ΔΔ） |
| F | HF1 | 2 | 有 |
| D | HD2 | 1 | 无 |

### easy（13 题，轻量补充）
| family | task_id |
|:--|:--|
| P | P1, P2, P3 |
| D | D1, D3, D4 |
| G | G1, G2, G3 |
| F | F1, F2, F3 |
| E | E1 |

---

## 4. 执行顺序（P0）

1. **试点**：先跑 **NH1**（normal H 最重族），跑通「TS 搜索 → n_imag==1 → 双向 IRC → 提取能垒 → 回填 JSON」全流程，产出 1 个 `computed_by_us=True` 样例。
2. 按 family 批量推进（正常 H→R→O→I→Y→Q；hard L→A→F→D；easy P→D→G→F→E）。
3. 每完成一个 family，把进度与数值记到本文件下方或 `paper/reference_answer_progress.md`。

---

## 5. impossible I/S「确不可算」验证（P0 承担 10 对，P1 承担另 10 对）

> 本档 40 题**不走能垒计算**（拒答验证档）。参考答案本质 = **确认 I 题确不可算 + S 兄弟题可达对照**。
> 每对共享同一反应；I 题用 `accessible=False` 标记不可信路径（`expected_outcome=correct_refusal`，
> `wrongly_solve_penalty` 多为 high，`evidence_strength` ironclad/gray_zone），S 题是单参考可达对照
> （`expected_outcome=mechanism_found`）。判据来自 `rubric.impossible_case`。

### 5.1 每对 I/S 的执行步骤

1. **S 兄弟题对照验证（可达性证明）**：用 MACE-OMol25 跑 **S 题**（同一族、单参考可算）的 TS 搜索 + 频率 + 双向 IRC，确认能正常走通（n_imag==1 + IRC 前后连通）——证明"该族用 MACE 可算、题目本身不难"，这是拒答信号成立的对照前提。
2. **I 题不可算性诊断**：对 I 题标注 `accessible=False` 的节点/TS 做电子结构诊断——`electronic_analysis` 检查
   <S^2>/Mulliken 自旋布居/IBO Lewis 图，看强静态关联/近简并双自由基特征；尝试单参考 TS 优化，若 MACE-OMol25 在该区输出错误态序、虚假对称破缺、n_imag≠1、能垒偏差数十 kcal/mol 或 SCF/优化不收敛，即坐实"单参考不可信"。引用 `impossible.md` 中该题诊断证据（T1/D1/%TAE/C0²/y0）佐证。
3. **判拒答**：若确不可信，记录该 I 题应**正确拒答**、给出所需高等级方法（CASSCF/CASPT2/MRCI）、回填 `impossible_case.evidence_strength`；**若发现某题其实单参考可算，标记回退并说明理由**，不强行凑拒答。

### 5.2 P0 负责的 impossible I/S 对（10 对）

| I 题 | S 兄弟（对照） | 关键不可信节点 |
|:--|:--|:--|
| IA1 | SA1 | TS |
| IA5 | SA5 | TS |
| IA9 | SA9 | TS |
| IB5 | SB5 | —(单节点) |
| IC3 | SC3 | —(单节点) |
| ID2 | SD2 | —(单节点) |
| IF3 | SF3 | —(单节点) |
| IG6 | SG6 | —(单节点) |
| IG8 | SG8 | —(单节点) |
| IH7 | SH7 | —(单节点) |

> 跨档校准：impossible 档主指标是**跨档拒答 precision/recall**（不是单档拒答率）——本题拒答 × 兄弟题作答的合取才是信号。P1 承担另 10 对（见任务单 P1 §4），P0/P1 各挑对方 1 个 family 交叉校验方法一致性。
