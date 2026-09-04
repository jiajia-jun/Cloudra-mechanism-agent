# NA1 — xtb 几何 + MACE 单点能量混合方案：TS2 能垒的 MACE 估计

- 会话：2026-09-04，小分子 (a-4) small_mol
- 工作目录：`/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_run`
- 前一环节：`NA1_run/xtb_diagnostic_report.md`（xtb 已确认几何收敛 + 找到 n_imag=1 的 TS2 鞍点，但 xtb 量化能垒为 +63 kcal/mol 伪峰）
- 本环节：在 **xtb 几何** 上用 **MACE**（MACE-omol-0-extra-large-1024，经 ORCA `! ExtOpt` 纯单点）估 TS2 能垒，判断 MACE 层面是否比 xtb 更接近 gold。

## 结论

用 MACE（MACE-omol-0-extra-large-1024，OMol25 系基础模型）在 xtb 优化几何上做单点，得到 **TS2 能垒 ΔE‡(MACE) ≈ +3.12 kcal/mol**，比 xtb 自身的 **+63.4 kcal/mol** 更加合理，且与 **gold ≈ 5 kcal/mol** 仅差 **~1.9 kcal/mol**。这是一个可信度中等的**单点估计**（非变分 MACE 鞍点），但足以说明 xtb 的 +63 是单坐标约束扫描伪峰——MACE 恢复了小而为正的能垒，方向与量级都接近 gold。

- ΔE‡(MACE, TS2 − central_complex) = **+3.122 kcal/mol**
- ΔE(MACE, product − central_complex) = **−4.267 kcal/mol**（放热）
- 与 gold ~5 kcal/mol 对比：MACE 偏差 ~1.9 kcal/mol；xtb 偏差 ~58 kcal/mol（13×）。**MACE 明显优于 xtb。**

**谨慎点（如实说明）**：几何是 xtb 的（xtb-PES 的鞍点 / 约束扫描帧），MACE 只是这些几何上的单点能量；TS2 的 xtb 几何是 xtb PES 上的一阶鞍点（n_imag=1, −127 cm⁻¹），但**未必是 MACE PES 上的鞍点**——MACE 单点是「MACE 能量差」，不是变分求得的 MACE 能垒。若 xtb 与 MACE 的 PES 相差大，这个能垒仍是近似。本混合方案给出的 ΔE‡ 应作为「指示性」数值，**不能当作已闭合的定量能垒**；要闭合需在 MACE 或 DFT 层面重优化 TS 并做 IRC。

## 计算参数

| 项 | 值 |
|---|---|
| 几何来源 | xtb（GFN2-xTB, gas-phase, charge −1, singlet） |
| 单点势能 | MACE-omol-0-extra-large-1024（OMol25 基础模型） |
| 引擎 | ORCA 6.1.1 `! ExtOpt`（纯单点，无 Opt/无 Freq） |
| 模型路径 | `/Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model` |
| MACE 可执行 | `/Users/cloudrayyy/miniconda3/envs/chemai/bin/mace` |
| Ext_Params | `--model <上述 model> --device cpu --dtype float64` |
| charge / mult | −1 / singlet（`* xyz -1 1`） |
| 并行/内存 | %pal nprocs 4, %maxcore 1024（→ cpus=4, mem=4GB） |
| 提交 | `submit_compute_job(job_type='orca')`，异步 |

## 选定的三个几何（已用 internal_coordinates 复核 C2–C6）

1. **central_complex（反应物侧离子–偶极络合物）** = `scanframe_2.75.xyz`（xtb 约束扫描的收敛帧，**C2–C6 = 2.822 Å**）。
   - 依据任务指引「选 C2–C6≈2.82 的收敛帧，勿用 2.90 非收敛伪帧」。扫描剖面 `scan_profile.csv` 中 target 2.90 → converged=False（伪帧，比邻帧低 21 kcal/mol）；下一个收敛帧 target 2.75 → 实际 C2–C6=2.822，E_xtb=−25.46327 Eh——前一轮能垒表正是以它为 central_complex 参考，故本混合同用它以保证可比。
   - **未使用** `central_complex.xyz`（这是 2.886 Å 的预组织初猜，非收敛驻点；xtb 自由弛豫会一路滚到产物，故不是稳定的 reactant 参考）。已在文件内注明。
   - 复核：C2=C3=1.348（烯醇 C=C 未断），C6=O7=1.218（羰基 C=O 未断），3 个片段（离子–偶极络合物未共价结合）。✓

2. **TS2（鞍点）** = `ts2_xtb_guess.xyz`（xtb 松弛约束扫描能量极大帧，**C2–C6 = 2.439 Å**，n_imag=1, ω=−127.21 cm⁻¹，E_xtb=−25.36228 Eh）。
   - 复核：C2=C3=1.361（拉长），C6=O7=1.225（拉长）——C–C 成键所伴生的耦合畸变，符合 RDS 过渡态特征。✓

3. **product I2（C–C 成键烷氧负离子）** = `NA1_run/product_i2.xyz`（由 `product_xtb.log` 的 `final structure:` 块原文转写，**C2–C6 = 1.668 Å**，n_imag=0，E_xtb=−25.51989 Eh）。
   - `xtbopt.xyz` **不是**产物 I2——它是 6 原子的孤立烯醇（E=−10.02130 Eh），后被 enolate 运行覆盖，故产物几何取自 `product_xtb.log`。
   - 复核：C2–C6=1.668（成键，键序 1），C8 为 R 手性碳；2 个片段（C–C 使烯醇+乙醛合并为一个碎片，水独立）。✓

> 三个几何均为 C4H9O3⁻（16 原子），同一组成 → MACE 能量差有物理意义（MLIP 绝对值零点是任意的，仅同组成间的相对能量可比）。

## MACE 单点能量与诊断

| 物种 | 几何文件 | C2–C6 (Å) | MACE E (Eh) | 作业 | 日志 | normal_termination |
|---|---|---|---|---|---|---|
| central_complex (reactant) | scanframe_2.75.xyz | 2.822 | **−383.5374531426** | job 31 | .cloudra/calc-31.out.log | true (job_types=sp) |
| TS2 | ts2_xtb_guess.xyz | 2.439 | **−383.5324772798** | job 32 | .cloudra/calc-32.out.log | true (job_types=sp) |
| product I2 | product_i2.xyz | 1.668 | **−383.5442528247** | job 33 | .cloudra/calc-33.out.log | true (job_types=sp) |

- 每个日志**恰好 1 条** `FINAL SINGLE POINT ENERGY (From external program)`（纯单点），`log_parser` 返回值与手动 grep 完全一致；`job_types=["sp"]`、`normal_termination=true`、无 `did not converge`/`ERROR`。charge −1 通过 `* xyz -1 1` 正确传入 MACE。
- 空队列提交，作业 31/32/33 均 done。

## ΔE‡ / ΔE（1 Eh = 627.509 kcal/mol）

| 量 | Eh | kcal/mol | 意义 |
|---|---|---|---|
| ΔE‡ = E(TS2) − E(complex) | +0.004976 | **+3.122** | C–C 加成（RDS）能垒 |
| ΔE = E(product) − E(complex) | −0.006800 | **−4.267** | 反应放热 |
| ΔE = E(product) − E(TS2) | −0.011776 | −7.389 | 产物相对 TS 更稳定 |

## 与 gold / xtb 对比

| 方法 | ΔE‡(kcal/mol) | 说明 |
|---|---|---|
| **gold** | **≈ 5** | 基准（RDS C–C 加成） |
| **MACE（本混合）** | **+3.12** | 与本轮结果；与 gold 差 ~1.9 |
| xtb（GFN2，约束扫描） | +63.4 | 单坐标约束伪峰（~13× 过估） |
| xtb（自由弛豫） | ~0（barrierless） | 自由优化直接滚到产物 |

**判断**：MACE 在 xtb 几何上的单点能垒（+3.12 kcal/mol）**远比 xtb 自身的 +63（或 barrierless 0）更接近 gold ~5 kcal/mol**。MACE 恢复了一个小而为正、量级正确的能垒，支撑「xtb +63 是单坐标约束扫描伪峰」的结论；同时 MACE 的放热性只有 −4.3 kcal/mol（xtb 为 −35.5），说明 xtb 与 MACE 的 PES 在该 floppy 带电体系确有实质差异，因此本值仍是近似。

## 每个数值的可信度评级

| 数值 | 评级 | 依据 |
|---|---|---|
| 三个 MACE 单点能量 | **高** | normal_termination=true；job_types=["sp"]；每日志恰 1 条 FINAL SP 且 log_parser 与手动 grep 完全一致；charge −1 正确传入；无报错 |
| ΔE‡ = +3.12 kcal/mol（作为单点估计） | **中高** | 同一 C4H9O3⁻ 组成间的 MACE 能量差，物理可比；几何为该物种且 C2–C6 已复核 |
| ΔE‡ = +3.12 kcal/mol（作为“真实”能垒） | **中** | 几何为 xtb PES 驻点/约束帧；xtb TS 几何未必是 MACE PES 鞍点，未在 MACE/DFT 层面重优化、无 IRC 验证 |
| ΔE = −4.27 kcal/mol（放热） | **中** | MACE 几何上同组成差；但与 xtb（−35.5）差异大，提示几何未在 MACE 层面优化、PES 差异存在 |
| 与 gold 的接近程度 | **中高** | 方向与量级都接近 gold；但为单点估计，不足以闭合定量能垒 |

## Bash 绕过 / 工具缺口（本环节全部，如实记录）

1. **产品几何转写（坐标工具缺口，触发 handwritten-coordinates 警告）**：`product_xtb.log` 是 **xtb** 日志，`format_converter(input_format='log')` 只认 Gaussian/ORCA，`log_parser` 不抽几何（且不解析 xtb）→ 无法用工具抽取产物 I2 坐标。故从 `product_xtb.log` 的 `final structure:` 块原文转写到 `product_i2.xyz`，触发 harness「疑似手写坐标」警告。**坐标来自日志（非记忆），属合法但工具无法覆盖的回退**——已记录，建议后续为 format_converter 增加 xtb 日志支持。
2. **C2–C6 距离核对**用 `internal_coordinates`（工具）+ 一次只读 python 交叉核对（读 xyz，非 QM 绕过）。
3. **日志定位**：作业通知报的 `.out` 路径（`mace_sp_*.out`）不存在，真实日志在 `.cloudra/calc-<id>.out.log`（GH#20 再次复现；用 bash `ls/grep` 定位与抽行，属 GH#20 已知问题）。
4. **能量抽取确认**：`log_parser` 成功（无需手工 grep）；另用 `grep -c 'FINAL SINGLE POINT ENERGY'` 确认每日志仅 1 条（只读核对，非绕过，杜绝 GH#22 式取错）。
5. **ΔE 计算**用只读 python（1 Eh=627.509 cal 换算），非 QM 绕过。
6. **xtb 本身仍无调度器通道**（GH#26），本轮几何为前一轮 xtb 裸跑产物；本环节**未再跑任何 xtb**，仅做几何确认与 MACE 单点。

## Harness 问题清单（新增 / 已确认）

- **无新增独立 bug**。MACE`! ExtOpt` 纯单点路径在本环节**工作正常**：`submit_compute_job(job_type='orca')` 走调度器；`qm_input_writer(task_type=[{"single_point": None}])` 正确生成 `! ExtOpt` 纯 SP；`log_parser` 正确提取 `FINAL SINGLE POINT ENERGY (From external program)` 且 `job_types=["sp"]`、normal_termination=true；能量未被取错。
- **确认了既有问题的作用域**：
  - **GH#21（非收敛误判 done）**：只影响几何优化（Opt/OptTS）作业；**不适用**于纯单点。本环节单点全部收敛。
  - **GH#22（final_energy 取初始能量）**：只影响**非收敛** ORCA MACE Opt；**不适用**于纯单点（每日志仅 1 条 FINAL SP，log_parser 即所得）。本环节未触发。
  - **GH#23（scan_parse `_ORCA_SPE_RE` 不认 `(From external program)`）**：`log_parser` 无此问题（含兼容正则），本环节用 log_parser 直接抽到正确能量。GH#23 只限 ts_guess(scan_parse)。
  - **GH#20（log_path 不一致）**：通知报的 `.out` 路径不存在，真实日志在 `.cloudra/calc-<id>.out.log`——**再次复现**（本次查询用 log_parser 直接指向真实日志，未受影响）。
  - **GH#24（File 工具路径根不绑定任务沙箱）**：read 需用 `NA1_run/` 前缀（本环节用 `NA1_run/...` 相对路径成功）；internal_coordinates/format_converter 用绝对路径（工具描述即推荐绝对路径）。未新增。
  - **GH#19（conformer_search 对带电多碎片崩）**：本环节未用 conformer_search（几何来自 xtb），未触发。
- **记录为工具缺口（潜在新 issue 候选，未独立提报）**：`format_converter`/`log_parser` 不解析 **xtb** 日志，导致 xtb 日志中几何（如产物 final structure）只能手工转写。此与 GH#26（xtb 无工具通道）同源，为避免 issue 泛滥故并记于此、交由协调层决定是否单列。**可独立提 issue 若不嫌细**：`format_converter(input_format='log')` 仅支持 Gaussian/ORCA，对 xtb 日志报错/不解析。
- 综上，**本环节没有需要「立即」新建 issue 的新故障**；已确认问题均已在上文列出、并说明哪些已复现（#20）、哪些不适用（#21/#22/#23 于纯单点）。

## 产物文件（均在 NA1_run/）

- 几何：`scanframe_2.75.xyz`（reactant）、`ts2_xtb_guess.xyz`（TS2）、`product_i2.xyz`（product I2，由 product_xtb.log 转写）
- 输入：`mace_sp_central_complex.inp` / `mace_sp_ts2.inp` / `mace_sp_product.inp`（均 `! ExtOpt` 纯单点）
- 日志：`.cloudra/calc-31.out.log` / `calc-32.out.log` / `calc-33.out.log`
- 本报告：`NA1_run/mace_hybrid_report.md`；速记：`NA1_run/mace_hybrid_handoff.md`
- 相关先前件：`xtb_diagnostic_report.md`、`scan_profile.csv`、`product_xtb.log`、`progress.md`

## 后续建议
- 若需闭合定量能垒：在 MACE 或 (白名单外) DFT 层面**重优化 TS2 并对该几何再做单点 + IRC**；或做二维坐标扫描（C2–C6 成键 + C6=O7 断裂）以消除单坐标约束伪峰。
- 本混合方案已确认：**MACE 在 xtb 几何上的单点能垒 (+3.12) 比 xtb 自身 (+63/-barrierless) 更接近 gold (~5)**，可作为「xtb 伪峰」的佐证与 MACE 层面的指示性能垒。
