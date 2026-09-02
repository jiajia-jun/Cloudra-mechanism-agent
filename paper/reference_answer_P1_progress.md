# P1 参考答案能垒标定 — 进度与状态

> 对应任务单：`paper/reference_answer_task_P1.md`；总纲：`paper/reference_calc_plan.md`。
> 口径：全档以 **MACE-OMol25（经 Gaussian external="mace" + g16-mlips）** 为唯一物理计算金标准；
> xTB 仅做构象/结构预筛与 TS 猜测辅助，**不计入参考能垒**。参考基准统一 `central_complex`。

## 开工前提（2026-09 复查 — 部分就绪，需走 MACE-ASE 独立管线）

实际环境（`~/.zshrc` 配置，非交互 bash 未 source）：

| 组件 | 状态 | 说明 |
|:--|:--|:--|
| **g16 (Gaussian)** | ❌ 缺失 | 无任何 g16 二进制 / 目录；`external="mace"`(g16-mlips) 路线不可用 |
| g16-mlips 插件 | ❌ 缺失 | 同上 |
| **ORCA 6.1.1** | ✅ 有 | `~/opt/orca_6_1_1/orca`（+ `~/opt/openmpi-4.1.8`），可运行，但**无法驱动 MACE**（无 external MLIP 接口） |
| **OMol25 权重** | ✅ 有 | `~/opt/mace-omol25/MACE-omol-0-extra-large-1024.model`（422 MB，`MACE_OMOL_MODEL` env）；`MACE_DEVICE=cpu`(float64) 正确 |
| `mace` python 包 | ✅ 有 | chemai env；MACECalculator 加载模型 + 单点能量**实测通过**（乙醛 0.24s） |
| `ase` | ✅ 有 | 3.29.0；含 `RFO` 鞍点优化器 |
| `xtb` | ✅ 有 | chemai env（构象预筛用） |
| `sella` | ❌ 无 | 未装（ASE RFO 替代） |
| `mace_run` CLI | ❌ 无 | 用 ASE + MACECalculator 代替 |

**结论**：`qm_input_writer`(Gaussian `external="mace"`) → `submit_compute_job(job_type="gaussian")` 这条官方文档路线需 g16，**不可用**；
ORCA 也无法充当 MACE 宿主引擎。**唯一可行路径 = MACE-OMol25 独立运行（ASE + MACECalculator）**：
ASE `RFO` 做 TS 优化（需有限差分 Hessian 判 n_imag==1）+ 自写 steepest-descent 双向 IRC + 提取 E_TS − E_central_complex。
注：该方法不产出 Gaussian/ORCA 日志，但产出的是真正的 MACE-OMol25 金标准能垒与 TS/IRC 证据（用于参考标定）。

## 方法调用要点（来自 skills/dft-calculation/references/mlip-gaussian-external.md）

- `method="external"` + `basis_set=""`（占位），权威引擎选择是 `extra_keywords='external="mace"'`。
- `charge`/`multiplicity` 必须设对（这是转发给 MLIP 的唯一电荷信息）。
- MLIP PES 振荡不收敛时退 `nomicro`（`{"opt":"nomicro"}`）。
- 提交：`submit_compute_job(job_type="gaussian", input_file="...gjf")`，无其他管线变更。

## P1 题单（能垒标定；来自 reference_calc_plan.md PERSON 1，工作分 ~421）

| tier | family | 题号 | TS | 工作分 |
|:--|:--|:--|:--|:--|
| normal | A | NA1 NA2 NA4 NA5 NA7 | 21 | 91 |
| hard | E | HE1 HE2 HE3 | 6 | 62 |
| hard | I | HI1 HI4 | 6 | 50 |
| easy | M | M1 M10 M12 M14 M15 M16 M3 M6 M8 | 9 | 37 |
| hard | G | HG1 HG2 | 4 | 32 |
| normal | U | NU1 NU5 NU6 NU7 | 10 | 32 |
| hard | J | HJ1 HJ2 HJ4 | 4 | 26 |
| normal | X | NX1 NX2 NX3 NX4 | 4 | 21 |
| hard | H | HH1 | 1 | 20 |
| hard | B | HB7 | 2 | 14 |
| hard | K | HK1 | 2 | 10 |
| easy | L | L1 L2 | 2 | 10 |
| easy | C | C1 C2 C3 | 3 | 6 |
| easy | T | T1 T3 | 2 | 5 |
| easy | X | X1 | 1 | 5 |
| impossible | I/S | IA11/IA7/IA8/IE2/IG7/IH8/II2/II8/IJ6/IJ7 + S 兄弟 | 0（拒答验证） | — |

注意：`ideapool/tasks/easy/P1.json`(Cope 重排) 是**题名** P1（属 PERSON 0 的 easy P 族），
与本任务单的"计算者 P1"（人/角色）不同，勿混淆。

## 试点题 NA1（acetaldehyde self-aldol → 3-hydroxybutanal）

- 体系：`[OH-].CC=O.CC=O` → `[OH-].CC(O)CC=O`，charge −1，mult 1，dilute NaOH/water 0–25 °C。
- 3 条边（3 个 TS）：TS1 enolate 形成、TS2 C–C 加成（RDS）、TS3 烷氧负离子质子化。
- gold.reference_computation 现状：barrier=5.0（ΔE‡, literature anchor），computed_by_us=false → 需回填 MACE 自算值。
- bond_changes 已给：E1 break [[2,8],[3,4]] form [[1,8],[2,3]]；E2 break [[2,3],[6,7]] form [[2,6],[3,4]]；E3 break [[1,8]] form [[7,8]]。

## 下一步（待用户确认）

硬阻塞：计算栈未就绪。需确认：
1. 是否有**已装 g16 + g16-mlips + OMol25 权重**的计算节点可用（提供节点/注册表或访问）；
2. 还是**本地装栈**（需用户提供 g16 二进制 + OMol25 权重下载源）；
3. 还是先做**管线验证试点**（仅用现有 xTB 走构象/TS-guess/IRC，但不产出 MACE 金标准能垒，无法回填 computed_by_us）。
