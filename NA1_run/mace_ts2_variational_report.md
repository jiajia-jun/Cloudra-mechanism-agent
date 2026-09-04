# NA1 TS2 (RDS C–C 亲核加成) — MACE 一阶鞍点 + 变分 ΔE‡ 报告（修订版）

## 结论（修订：鞍点可靠，但对 central_complex 的 ΔE‡ 不可交付）
**MACE-OMol25 (ORCA `! ExtOpt`) 在 NA1 的 TS2（乙醛自羟醛缩合 RDS，C–C 亲核加成，Burgi–Dunitz）上成功收敛出真正的一阶鞍点**（`n_imag == 1`）。这一半是**扎实的、变分的**。

**但“ΔE‡ 相对于 central_complex”无法在 MACE PES 上严谨给出**：MACE（与 xtb）在该 floppy 离子–偶极体系上**不存在一个结合的、预组织的 central_complex 极小值**——2.82 Å 复合物自由优化（job 39）即被拉到 3.75 Å 分离态并收敛为驻点。

因此：
- 表中 **+8.92 kcal/mol** 是对**非驻点约束参考帧**的表观能垒（与 xtb 被批的单坐标扫描伪峰同属一类错误）——**无效，不作交付**。
- **+11.39 kcal/mol** 才是唯一**全变分**的 MACE 数（TS2 鞍点 − MACE 优化极小值 3.75 Å），但它的参考是**分离态**，**不是**任务定义的“结合的 central_complex”，故它**也不是**“对 central_complex 的 ΔE‡”。

**主结论修订：TS2 鞍点可靠（n_imag=1）；对 central_complex 的 ΔE‡ 在 MACE/xtb 上不可交付。**

| 量 | 数值 | 来源/证据 | 有效性 |
|---|---|---|---|
| TS2 鞍点能量 E_MACE(TS2) | −383.528446704 Eh | job 36 `! ExtOpt OptTS` 收敛 + FINAL SP (stationary point) | 可靠 |
| TS2 虚频 | **−365.09 cm⁻¹**（模式 6，`***imaginary mode***`） | job 38 `! ExtOpt Freq NumFreq` 数值 Hessian | 可靠 |
| TS2 虚频数 n_imag | **1** | job 38 频率表仅模式 6 一个虚频；job 36 末段 `Hessian has 1 negative eigenvalues`（eigenvalue −0.00710790）双重确认 | 可靠 |
| TS2 几何 | C1–C8=1.948 Å, C1=C2=1.414 Å, C8=O9=1.263 Å | job 36/38 收敛帧；Burgi–Dunitz 特征 | 可靠 |
| I1 central_complex 参考 | E=−383.542659210 Eh（**约束 2.82 Å 帧**） | MACE 松弛扫描 job 35 `relaxscanact.dat` 首行 | **非驻点** |
| 表观能垒（2.82 Å 约束帧参考） | **+8.918 kcal/mol** | E(TS2) − E(2.82Å 约束帧)=0.014213 Eh × 627.509 | ⚠️ 参考非驻点 → **无效** |
| I1 自由 MACE 优化（唯一 reactant 驻点） | E=−383.546592904 Eh，几何弛豫至 **C1–C8=3.753 Å**（分离态） | job 39 `! ExtOpt Opt` 收敛 | 可靠（但为分离态） |
| **全变分 ΔE‡（MACE TS2 鞍点 − MACE 优化极小值 3.75 Å）** | **+11.387 kcal/mol** | 0.018146 Eh × 627.509 | 变分；参考为分离态，**非**任务定义的 central_complex |

## 为什么 8.92 不可用，正确的量是 11.39
- 任务定义的 ΔE‡ 参考是 **central_complex / I1**：一个**结合的、预组织的** enolate·H₂O·乙醛 离子–偶极络合物，期望是可稳定的极小值。
- **但 MACE 势能面上没有这个极小值**：job 39 把 2.82 Å 复合物自由优化，直接弛豫到 **C1–C8=3.753 Å（分离的离子–偶极对）** 并收敛为驻点。所谓“2.82 Å central_complex”只是 job 35 松弛扫描的第 0 帧——C1–C8 **被约束**在 2.82 Å 的扫描帧，**不是驻点**。
- 所以 **8.92 = E(TS2, 真鞍点) − E(2.82 Å 非驻点帧)**。拿一个被约束的非驻点帧当反应物参考去算 ΔE‡，与 xtb 的“单坐标约束扫描伪峰 +63.4”是**同一类错误**（子代理批评 xtb 用约束帧算能垒，就应同样否定自己这片 2.82 Å 参考）。
- 沿 C–C 的 MACE 松弛扫描（job 35）在 2.82 Å 之上确有内部极大（C1–C8=1.941 Å，E=−383.52846，scan barrier≈+8.91 自洽）——那只能证明**在 C1–C8 被约束的路径上存在一个极大**，**不能**证明“对 central_complex 的活化能”，因为路径起点（2.82 Å 帧）本身就不是 MACE 的反应物极小值。
- **唯一全变分的 MACE 量** = E(TS2, −383.5284467) − E(自由 MACE 极小值 3.75 Å, −383.5465929) = **+11.39 kcal/mol**。两端都是 MACE 驻点，这个数站得住。**但它参考的是分离态，不是任务定义的“结合的 central_complex”，所以它也不是“对 central_complex 的 ΔE‡”。**

## 对比表（修订）
| 方法 | ΔE‡ (kcal/mol) | 性质 | 可信度 |
|---|---|---|---|
| gold（文献锚） | ≈5 | reference_computation.barrier_kcal_mol=5.0 | 参考（非评分门） |
| xtb 自身（C–C 约束扫描） | +63.4 | 单坐标约束伪峰；xtb 自身在该 floppy 离子–偶极体系定量不可信 | 低 |
| xtb 几何 + MACE 单点 | +3.12 | 混合，非变分（xtb TS2 几何非 MACE 鞍点） | 中（近似） |
| MACE 表观（2.82 Å 约束参考帧） | +8.92 | 参考非驻点，类扫描伪峰 | **无效（不交付）** |
| **MACE 全变分（真鞍点 − MACE 优化极小值 3.75 Å）** | **+11.39** | 两端均驻点，变分；但参考为分离态，非任务定义的 central_complex | 中（非“对 central_complex 的 ΔE‡”） |

## 物理解读（修订）
8.92 与 11.39 的差距**不是“PES 不同”，而是拿谁当参考**——8.92 用了**非驻点的约束帧**（无效），11.39 才用了**MACE 真实驻点**。更深层的事实是：MACE 与 xtb 在该 floppy 离子–偶极体系上**都找不到一个结合的、预组织的 central_complex 极小值**（xtb 直接滚到成键产物、MACE 直接拉到 3.75 Å 分离态）。因此“对 central_complex 的 ΔE‡”在这两种方法上**无法严谨定义**；gold 参考（≈5 kcal/mol）对应的 central_complex 是高阶方法 PES 上的真实结合复合物，MLIP/半经验未复现。

**真正闭合的文献级“对 central_complex 的 ΔE‡”仍需白名单外方法（ORCA DFT ωB97M-V/B3LYP-D3BJ + def2-TZVPD）在该 PES 上把预组织复合物优化成真极小值后，与 TS2 比较 + IRC**——仅作方法建议，不作证据。

## 可靠性证据
- **数值收敛**：TS2（job 36）`THE OPTIMIZATION HAS CONVERGED` + `FINAL ENERGY EVALUATION AT THE STATIONARY POINT` + `ORCA TERMINATED NORMALLY`；log_parser `opt_converged=true`, `normal_termination=true`。（协调层已对日志复核确认。）
- **鞍点完整性**：job 38 数值 Hessian 给出 **恰 1 个虚频 −365.09 cm⁻¹**，其余 40 模全为实频（24.56…3879.86 cm⁻¹）；job 36 OptTS 末段 `Hessian has 1 negative eigenvalues`（TS 模式 eigenvalue −0.00710790），两证据吻合。
- **几何判据**：internal_coordinates 复核 C1–C8=1.941→1.948 Å（forming），C1=C2=1.415 Å（enolate C=C 拉长），C8=O9=1.264 Å（C=O 拉长）→ Burgi–Dunitz 反应坐标。
- **方法**：MACE-omol-0-extra-large-1024 model，charge −1，singlet，gas，`! ExtOpt OptTS/Freq NumFreq`，nprocs 4，mem 4GB。全部在白名单 ['mace-omol25'] 内；**未使用任何 B3LYP/DFT/MP2**，未用 bash 手写 QM 输入。

## Artifact 路径
- TS2 OptTS 输入：`NA1_run/mace_ts2_optts2.inp`；日志：`NA1_run/.cloudra/calc-36.out.log`（job 36）
- TS2 收敛几何：`NA1_run/mace_ts2_optts2.xyz`
- TS2 NumFreq 输入：`NA1_run/mace_ts2_numfreq.inp`；日志：`NA1_run/.cloudra/calc-38.out.log`（job 38，n_imag=1）
- MACE C–C 松弛扫描：`NA1_run/mace_ts2_scan.inp`；日志 `NA1_run/.cloudra/calc-35.out.log`；剖面 `NA1_run/mace_ts2_scan.relaxscanact.dat`；TS guess `NA1_run/mace_ts2_scan_tsguess.xyz`
- I1 自由优化：`NA1_run/mace_i1_opt.inp`；日志 `NA1_run/.cloudra/calc-39.out.log`；几何 `NA1_run/mace_i1_opt.xyz`
- 方法参数：MACE-omol-0-extra-large-1024.model；`--device cpu --dtype float64`；ORCA 6.1.1；nprocs 4；charge −1；mult 1

## 本任务 Harness 验证结论（修复均已生效）
1. **GH#21（非收敛误判 done）已修复**：job 34（OptTS from xtb 猜）、job 35（MACE 扫描，1 帧达最大步数）均被正确标记为 **failed**（reason="ORCA 几何优化未收敛...结果不可信"）；job 36/39 收敛者 state=done 且 `opt_converged=true`。非收敛不再被当成功。
2. **GH#22（final_energy_hartree 取初始几何）已修复**：job 36 的 energy=−383.528446704（= FINAL SP at stationary point），job 39 的 energy=−383.546592904（= 收敛后 FINAL SP），均非初始几何；log_parser 返回与手动 grep 一致。
3. **GH#23（ts_guess scan_parse 对 ORCA 外部 MLIP 失败）已修复**：`ts_guess(mode=scan_parse, engine=orca, log_path=.cloudra/calc-35.out.log)` **成功解析** MACE 松弛扫描，正确识别内部极大（frame 9/1-based 10，C–C=1.941 Å）为 TS guess；而此前对 `calc-28.out.log` 报 `FINAL SINGLE POINT ENERGY not found`。
4. **GH#21/#22 作用域确认**：仅影响 Opt/OptTS（非收敛误判 done、取初始能量），**不影响**本轮的纯单点/纯 OptTS 正常收敛路径。
5. **无新 harness bug 阻断本结论**。唯一观察（非阻断、非本次新增）：`qm_input_writer` 的 `task_type=[{"opt":"TS,NumFreq"}]` 生成 `! ExtOpt OptTS`（**丢弃 NumFreq**），`task_type=[{"freq": null}]` 生成 `! ExtOpt Freq`（对外部 MLIP 退化为单点，需显式加 `extra_keywords="NumFreq"` 才触发数值 Hessian）。这是 ORCA 外部-MLIP 频率路径的一个**输入构造缺口**（不影响已获得的一阶鞍点证据，因 job 38 用 `extra_keywords=NumFreq` 补上了），已在工作中绕过，**未新提 issue**（交由协调层判断是否单列）。

## 本任务使用的 bash（合法的只读/绕过记录）
- 定位真实日志：`ls .cloudra/calc-*.out.log`（通知给的 `.out`/`.log` 路径不存在，真日志在 `.cloudra/calc-<id>.out.log`——GH#20 再复现；只读 grep/ls）。
- grep 核对收敛/终态：`grep -nE "THE OPTIMIZATION HAS CONVERGED|did not converge|ORCA TERMINATED NORMALLY|Hessian has 1 negative|FINAL SINGLE POINT ENERGY|VIBRATIONAL FREQUENCIES|imaginary mode"`（只读）。
- 能量换算/几何距离复核：python3 + numpy 读 xyz（C1–C8/C1=C2/C8=O9 距离、ΔE Eh→kcal/mol×627.509），只读。
- **未用** bash 写 QM 输入、未用 bash 跑白名单外方法；所有 QM 输入由 qm_input_writer 生成（`smiles:` 注释行由 edit 工具补上），全部经 submit_compute_job 走调度器。
