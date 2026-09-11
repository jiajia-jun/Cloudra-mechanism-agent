# M1 初猜（xTB MTD 路径最高帧）能不能直接当 TS 初猜——实测证据

**结论分两层，第二层才是要害。**

1. **SOP 当时交出来的那个初猜不能直接用**：它是 xTB 路径**被截断**时采到的帧，几何上落在反应物
   自己的盆地里（自由弛豫即回到反应物极小值），交给 ORCA `OptTS` 后 56 个几何循环一路滑回极小值，
   从未收敛到任何鞍点。
2. **但根因不是"MTD 不适合这类题"，而是机时上限**：xTB 的路径是**迭代精修**的，内建上限只有 3 轮，
   3 轮后打印的 `terminated because max. # cycles reached` 是**截断**而不是收敛。把上限放开让引擎
   跑到自己的收敛判据（第 31 轮），**同一对端点**立刻给出可用初猜：barrier 18.299 kcal/mol、最高帧
   落在扭转极大上（θ=−5.7°，平面构型），拿去 ORCA `OptTS` **9 轮即收敛到一阶鞍点**
   （+16.03 kcal/mol，全程稳定 1 个负本征值）。见第 6 节与 `refinement_sweep/`。

本目录只放**实测证据**：逐字的引擎输入/输出（三个引擎日志都是全文，不裁剪）、可重跑的脚本、
从原始文件算出来的派生表。
"观察事实"与"根因假设"分开写（沿用 `tests/fixtures/chemtool_issue33/README.md` 的写法）。

- 题目：`ideapool/tasks/easy/M1.json`（2,2'-二甲基联苯，两端 SMILES 相同 `Cc1ccccc1-c1c(C)cccc1`，
  声明 `product_geometry = rotate_about_bond(atoms, 180°)`，题池锚点 13.0 kcal/mol，
  `computed_by_us: false`）
- 原子编号（0 基，构造器输出序，28 原子）：`C0` 甲基碳（挂 `C1`）；环 A = `C1..C6`；
  联苯轴键 = `C6–C7`；环 B = `C7, C8, C10, C11, C12, C13`；`C8` 的邻位甲基碳 = `C9`；
  `C0` 上的 H = 14/15/16，`C9` 上的 H = 21/22/23
- 扭转坐标 `θ = 二面角(C1, C6, C7, C8)` —— 两个邻位取代碳（各自带一个甲基）之间的二面角，
  0° = 两个甲基同侧重叠，±90° = 两环垂直，180° = 两个甲基异侧重叠

---

## 1. 复现材料清单

| 文件 | 内容 | 来源（工作区内的原始路径） |
|---|---|---|
| `xtbpath.xyz` | **逐字**：xTB MTD 路径 48 帧（注释行 = 相对 kcal/mol） | `.tscheck/ts/ts_0001/path/xtb_path_runs/guess_0001/xtbpath.xyz` |
| `xtbpath_ts.xyz` | **逐字**：SOP 认定的 TS 候选帧（= 路径第 10 帧，同一下标） | 同上目录 `xtbpath_ts.xyz` |
| `path_reactant.xyz` / `path_product.xyz` | **逐字**：喂给 MTD 的两端几何 | 同上目录 `reactant.xyz` / `product.xyz` |
| `xtb_path_command.txt` | **逐字**：MTD 命令行 | 同上目录 `command.txt` |
| `path_frames.csv` | 派生：48 帧的 θ / 环共面性 / 甲基间距 / 轴键长 / RMSD | 由 `path_analysis.py` 从 `xtbpath.xyz` 生成 |
| `path_analysis.py` | 派生脚本（可重跑：`python3 path_analysis.py`） | 本次分析所写 |
| `xtb_scan.csv` / `xtb_scan_transcript.txt` | **逐字/派生**：19 点弛豫二面角扫描（目标角、实达角、绝对能量、相对能、收敛标志） | 由 `xtb_scan_driver.py` 生成 |
| `scan_points/point_NNN.xyz` | 每个扫描点优化后的几何（19 个） | 同上 |
| `xtb_scan_driver.py` / `xtb_scan_constraint.inp` | 扫描驱动脚本与约束块逐字 | 本次分析所写 |
| `xtb_scan_block_probe.inp` / `xtb_scan_block_probe.out` | **逐字**：`$scan` 块支持度探测的输入与输出（全文） | `.tscheck/m1_eval/probe/` |
| `strain_decomposition.py` / `strain_decomposition_summary.txt` | 驱动脚本 + 输出：那 47 kcal/mol 到底在哪（3.4 节） | `.tscheck/m1_eval/decomp/` |
| `rigid_reference.xyz` | **构造**：弛豫反应物绕联苯轴刚性转到同一二面角（物理上干净的参考） | 同上 |
| `h_only.xyz` / `relaxed_from_guess.xyz` | **构造**：初猜骨架冻结+氢用 MMFF 弛豫 / 初猜自由弛豫末帧 | 同上 |
| `xtbtopo.mol` | **逐字**：xTB 写出的拓扑（MMFF 探针用，原子序与帧一致） | `.tscheck/m1_eval/probe/xtbtopo.mol` |
| `xtb_guess_basin_check.py` / `basin_check_summary.txt` | 驱动脚本 + 输出：初猜到底是不是"反应物自己"（3.3 节） | `.tscheck/m1_eval/basin/` |
| `free_relax.out` / `free_final.xyz` | **逐字**：初猜的自由弛豫输出与末帧几何 | 同上 |
| `hold_relax.out` / `hold_final.xyz` | **逐字**：钳住初猜自己扭转角的弛豫输出与末帧几何 | 同上 |
| `xtb_single_points.py` / `sp_frame{00,10,46}.out` | 驱动脚本 + **逐字**：三个路径帧的 xTB 单点输出（3.2 节的绝对能量锚） | `.tscheck/m1_eval/sp2/` |
| `refinement_sweep/run_nrun{10,30,100}.out` | **逐字**：把精修上限放到 10 / 30 / 100 的完整日志（第 6 节） | `.tscheck/mtd_probe/` |
| `refinement_sweep/converged_path.xyz` / `converged_ts_candidate.xyz` | **逐字**：收敛路径（47 帧）与它的 TS 候选帧 | 同上 |
| `refinement_sweep/orca_optts_from_converged_guess.{inp,log}` | **逐字**：拿收敛初猜跑的 ORCA `OptTS` 输入与完整日志（9 轮收敛） | 同上 |
| `refinement_sweep/orca_optts_final_geometry.xyz` | **逐字**：该 `OptTS` 的末帧几何 | 同上 |
| `refinement_sweep/water_never_converges_1000cycles.log` | **逐字**：一个**永远收敛不了**的路径（水 O–H 拉伸，1000 轮仍在触顶） | 同上 |
| `xtb_refinement_sweep.py` | 扫描脚本（可重跑：`python3 xtb_refinement_sweep.py <workdir> <r.xyz> <p.xyz> 3 10 30 100`） | 本次分析所写 |
| `verify_claims.py` | 自查脚本：把本文件引用的每个数值从上面的逐字文件重算并断言（当前 **56/56 通过**） | 本次分析所写 |
| `optts_refine.inp` | **逐字**：真正跑起来的 ORCA `OptTS` 输入 | `.tscheck/ts/ts_0001/jobs/job_0002/refine.inp` |
| `optts_cycle_table.txt` | **逐字抽取**：56 个循环的能量、Hessian 负本征值个数、被跟随的 TS 模本征值（左列为原始行号） | 同目录 `refine.stdout.log`（48,938 行） |
| `optts_header.txt` / `optts_last_40_lines.txt` | **逐字**：输入回显头部 / 被杀前的末尾 | 同上 |
| `optts_trajectory.xyz` | **逐字**：ORCA 写的 55 帧轨迹 | 同目录 `refine_trj.xyz` |
| `optts_final_geometry.xyz` | **逐字**：被杀时磁盘上的当前几何（第 56 帧） | 同目录 `refine.xyz` |
| `refmin_b3lyp.inp` / `refmin_b3lyp_geometry.xyz` | **逐字**：B3LYP/def2-SVP 参考极小值的输入与末帧几何 | `.tscheck/m1_eval/min_frame0/{min.inp,min.xyz}` |
| `refmin_summary.txt` | **逐字抽取**：该作业的循环能量与终止标记 | 同目录 `min.stdout.log` |
| `first_attempt_keyword_error.txt` | **逐字抽取**：SOP 自己产出的第一个输入被 ORCA 关键词校验拒掉 | `.tscheck/ts/ts_0001/jobs/job_0001/` |
| `versions.txt` | **逐字**：xtb / ORCA / CREST 版本与主机信息 | 本机 `xtb --version` 等 |
| `xtb_path_stdout.log` | **逐字（全文 1,472 行）**：MTD 运行日志（含 xTB 自报的路径试验表） | 同上目录 `stdout.log` |
| `optts_stdout.log` | **逐字（全文 48,938 行，2.4 MB）**：ORCA OptTS 完整日志；`optts_cycle_table.txt` 的行号即指向此文件 | `.tscheck/ts/ts_0001/jobs/job_0002/refine.stdout.log` |
| `refmin_stdout.log` | **逐字（全文 6,871 行）**：B3LYP 参考极小值完整日志 | `.tscheck/m1_eval/min_frame0/min.stdout.log` |

三个引擎日志都是**全文逐字**放进来的（不裁剪），所以摘录里的每个行号都能在本目录内就地回查；
摘录脚本见第 6 节。

## 2. 环境与逐字命令

```
xtb     6.7.1 (edcfbbe)
ORCA    Program Version 6.1.1 - RELEASE -    （/Users/cloudrayyy/opt/orca_6_1_1/orca）
CREST   Version 2.12, Thu 19. Mai 16:32:32 CEST 2022
host    Darwin 25.3.0 arm64; ncpu=18
```

```bash
# 1) 前段（declare→build→map→assemble→guess→validate）由 SOP 阶段函数实跑，MTD 命令行逐字见
#    xtb_path_command.txt；产物目录 .tscheck/ts/ts_0001/

# 2) 真正跑起来的 TS 精修（本次实验手工发起，不是 SOP 的 submit 路径）
cd .tscheck/ts/ts_0001/jobs/job_0002
nohup "$(realpath "$(which orca)")" refine.inp > refine.stdout.log 2>&1 &   # PID 7028

# 3) 同级别参考极小值（B3LYP/def2-SVP，起点 = 路径第 0 帧）
cd .tscheck/m1_eval/min_frame0
nohup "$(realpath "$(which orca)")" min.inp > min.stdout.log 2>&1 &

# 4) `$scan` 块支持度探测（结论：本 build 静默忽略，见第 5 节第 4 条）
cd .tscheck/m1_eval/probe
xtb start.xyz --input xtb_scan_block_probe.inp --opt > xtb_scan_block_probe.out 2>&1

# 5) 弛豫二面角扫描（19 点）
python3 docs/evidence/ts_guess_mtd_artifact/xtb_scan_driver.py <workdir>

# 6) 关键帧绝对能量单点（逐字输出 = 本目录 sp_frame*.out）
python3 docs/evidence/ts_guess_mtd_artifact/xtb_single_points.py <workdir>

# 7) 初猜是不是"反应物自己"：自由弛豫 + 钳住自身扭转角弛豫（3.3 节）
python3 docs/evidence/ts_guess_mtd_artifact/xtb_guess_basin_check.py <workdir>

# 8) 把 README 引用的每个数值从逐字文件重算并断言
python3 docs/evidence/ts_guess_mtd_artifact/verify_claims.py

# 9) 停止 OptTS（按 PID，精确到本次实验自己起的进程）
kill 7028
```

## 3. 观察事实

### 3.0 MTD 运行本身（逐字，`xtb_path_stdout.log`）

命令行逐字（`xtb_path_command.txt`）：

```
xtb reactant.xyz --path product.xyz --chrg 0 --uhf 0
```

- 两端 RMSD：`reactant product RMSD :    4.961`（第 370 行）——两端确实是"转 180°"这种大位移。
- xTB 自报的路径试验表（第 395–399 行逐字）：

  ```
   path trials (see xtbpath_*.xyz), energies in kcal/mol
  run 1  barrier: 218.50  dE:  -1.78  product-end path RMSD:   0.028
  run 2  barrier: 149.44  dE:   8.18  product-end path RMSD:   4.128
  path  1 taken with  121 points.
  screening points ...
  new # points : 48
  ```

- 整个 MTD 运行 17.7 秒（第 1461 行 `wall-time: 0 d, 0 h, 0 min, 17.724 sec`）。
- **路径第 0 帧 == 喂进去的 `reactant.xyz`（坐标一致，1e-8 内，`verify_claims.py` 会重算）**，
  即路径起点是**未弛豫**的建模几何：
  它的单点比 xTB 自由优化极小值高 2.535 kcal/mol（见 3.2 表）。
- **xTB 自报的 barrier（218.50 / 149.44 kcal/mol）与该路径保存帧的真实单点最大值（44.865）
  差 1–2 个数量级**。此处只记录事实；"xTB 打印的那个 barrier 到底是什么量"列入第 5 节未验证项。

### 3.1 初猜 = MTD 路径的最高帧，而该帧几乎没转向

`path_frames.csv`（48 帧全表）。摘录：

| 帧 | 相对能 (kcal/mol) | θ (°) | 环 A 共面性 (Å) | 环 B 共面性 (Å) | C0···C9 (Å) | 甲基间最小 H···H (Å) | 轴键 C6–C7 (Å) | 相对第 0 帧最大原子位移 (Å) |
|---|---|---|---|---|---|---|---|---|
| 0（起点） | 0.000 | −86.62 | 0.0012 | 0.0012 | 4.053 | 2.685 | 1.474 | 0.000 |
| 10（**初猜**） | **44.865** | **−108.03** | 0.0513 | 0.0567 | 3.050 | **1.932** | 1.443 | **1.292** |
| 33 | 32.031 | 0.94 | 0.0116 | 0.0572 | 5.393 | 4.931 | 1.497 | 2.936 |
| 46 | −2.079 | 85.67 | 0.0158 | 0.0127 | 3.978 | 2.608 | 1.487 | 4.290 |
| 47（末帧） | −1.779 | 92.15 | 0.0030 | 0.0032 | 3.854 | 2.406 | 1.492 | 4.418 |

要点（全部来自上表，未做任何拟合）：

1. 路径确实是绕联苯轴转了一圈：θ 从 −86.62° 经 −108°、0.94° 到 +92.15°。
2. **路径最高帧（第 10 帧）的 θ 只比起点转了 21°**，而它的相对能是 44.865 kcal/mol。
3. 同一帧的形变信号（**只列数值，不做解释**，解释见 3.4）：两个甲基之间的最短 H···H 从
   2.685 Å 变成 1.932 Å，甲基碳间距 4.053 → 3.050 Å，两个芳环的共面性偏差从 0.0012 Å 涨到
   0.051/0.057 Å，联苯轴键由 1.474 缩到 1.443 Å；最大单原子位移 1.292 Å，发生在甲基氢上。
   **注意 H···H 这个数不能当"对撞"的证据**：3.4 节里同一二面角上弛豫良好的结构 H···H 只有
   1.683 Å（更短），总能量却只比极小值高 3.949 kcal/mol。
4. 第 47 帧的 θ 与第 0 帧相差 178.8°，即"转 180°"这个声明操作；两端相对第 0 帧的原子位移最大
   4.42 Å。两端是同一个构造（同 SMILES），差别只是弛豫程度（第 0 帧比 xTB 极小值高 2.535、
   第 46 帧只高 0.456 kcal/mol）。这次 180° 转动在立体化学上把分子送到哪一个具体构象
   （是否跨过手性轴的 P/M 关系），本目录**没有**判定。

### 3.2 同一扭转角上，弛豫后的代价只有 ~0.3 kcal/mol

`xtb_scan.csv`（19 点，步长 10°，`$constrain dihedral ... force constant=5.0`）；CSV 里的
`rel_kcal_mol` 列是**相对该扫描第一个点**（目标角 0°）的值，下表另给绝对能量与统一的基准。
绝对能量的锚：

| 参考量 | 能量 (Eh) | 说明 |
|---|---|---|
| xTB 自由优化极小值 | −37.106620806097 | `xtb start.xyz --opt`（起点 = 路径第 0 帧） |
| 扫描最低点 | −37.106600646 | 实达角 +80.01°；比上面的自由极小值高 0.013 kcal/mol（扫描分辨率下限） |
| 扫描在 \|θ\|≈110° 附近 | −37.106138676（实达 +109.99°） | 与初猜的 \|θ\|=108.03° 同一扭转区 |
| 扫描在 \|θ\|≈180° 端 | −37.077413237（实达 −179.45°） | 平面端 |
| 扫描在 \|θ\|≈0° 端 | −37.083889026（实达 +0.49°） | 另一平面端 |
| 扫描最高点 | −37.068613380（实达 +170.60°） | |
| MTD 路径第 0 帧 | −37.102580393726 | 比自由极小值高 2.535 kcal/mol |
| MTD 路径第 10 帧（初猜） | −37.031083940468 | 比自由极小值高 **47.400** kcal/mol |
| MTD 路径第 46 帧 | −37.105894270113 | 比自由极小值高 0.456 kcal/mol |

由此：

（以下所有相对能一律以**自由优化极小值** −37.106620806097 Eh 为基准；扫描自身的最低点比它高
0.0127 kcal/mol，即扫描对 ~0.01 kcal/mol 的差别没有分辨力。）

- **同一个扭转角**（\|θ\| ≈ 108–110°）上，弛豫结构的代价是 **+0.303 kcal/mol**（实达 109.99°）
  到 +0.161 kcal/mol（实达 70.02°），即这条坐标上几乎不花能量；
- MTD 初猜帧却比极小值高 **47.400 kcal/mol**。→ 那 44.865 kcal/mol 的"路径势垒"里，约 **47 kcal/mol
  是非扭转型形变**（甲基 H···H 对撞 + 芳环畸变），只有 ~0.3 kcal/mol 属于这条扭转坐标。
- 扭转坐标的真实极大在**平面端**：+14.264（\|θ\|≈0.49°）/ +18.328（\|θ\|≈179.45°），扫描采样到的
  最高点是 +23.850（\|θ\|≈170.60°）kcal/mol。**离初猜 70–110°**。

### 3.3 初猜落在反应物自己的盆地里（自由弛豫即回到反应物极小值）

`basin_check_summary.txt`（脚本 `xtb_guess_basin_check.py`，全部 xTB/GFN2 单点与弛豫）：

| 量 | 反应物（第 0 帧） | 初猜（第 10 帧） | 初猜**自由弛豫** | 钳住初猜自身扭转角后弛豫 |
|---|---|---|---|---|
| θ (°) | −86.62 | −108.03 | **−84.33（回到反应物极小值）** | −107.90 |
| 甲基间最小 H···H (Å) | 2.685 | **1.932** | 2.690 | 2.188 |
| E − xTB 极小值 (kcal/mol) | +2.535 | **+47.400** | **−0.008（同一个极小值）** | **+0.994** |

几何距离（不做叠合）：全原子 RMSD **0.780 Å**、最大单原子位移 1.292 Å（甲基 H）；
**重原子 RMSD 0.534 Å、最大重原子位移 0.900 Å（甲基碳 C0）**；扭转只差 21.41°。

三条读数合起来就是答案：

1. **主体几何几乎就是反应物**——重原子最多挪 0.9 Å，扭转只转开 21°（而"转 180°"这个声明操作
   要求 178.8°），产物那一端离它有 158°。
2. **自由弛豫把它直接送回反应物极小值**（θ→−84.33，能量落在极小值上 0.008 kcal/mol 以内），
   没有停在任何鞍点附近。
3. **它的 47.4 kcal/mol 与扭转坐标无关**：钳住它自己的扭转角再弛豫，其余自由度立刻把
   47.400 卸到 **0.994**；把扭转放开就归零。

所以这个"TS 候选"不是鞍点，而是**被甲基对撞（H···H 1.93 Å）与芳环畸变顶在反应物盆地壁上的一根
形变弹簧**。把它与 3.1、3.2 并排看：真实扭转极大在平面端（θ≈0/180），初猜落在 θ≈−108°——
相差 70–110°，而该处的扭转代价接近 0。**"取路径最高帧当 TS 候选"在本例中取到的就是反应物自己
被挤变形的那一帧**。

### 3.4 那 47 kcal/mol 到底在哪：扭转只值 ~4，其余在重原子骨架上

`strain_decomposition_summary.txt`（脚本 `strain_decomposition.py`；全部相对同一个 xTB 极小值）：

| 构造 | 是什么 | E − xTB 极小值 (kcal/mol) |
|---|---|---|
| **A** 初猜帧本身（单点） | SOP 的"TS 候选" | **+47.400** |
| **B** 弛豫反应物**刚性转动**到同一二面角（θ=−108.03°） | 那条扭转上物理干净的参考 | **+3.949** |
| **C** 初猜重原子骨架 + 氢用 MMFF 弛豫（重原子位移 0.0000 Å 已核） | 分离"氢"与"骨架" | **+42.131** |
| **D** 初猜自由弛豫 | 它属于哪个盆地 | **−0.008**（θ→−84.33°，回到反应物极小值） |

读法：

- **扭转本身只值 ~4 kcal/mol**（B）：把已经弛豫好的反应物绕联苯轴刚转到初猜那个二面角，
  只付出 3.949。初猜的 47.400 里没有多少是"转过去"的代价。
- **氢的位置不是故事**（A − C = 5.269，而这条探针的方法偏差是 −2.064，见对照），更要紧的是
  **同一二面角上那条低能量参考结构的甲基间 H···H 只有 1.683 Å——比初猜的 1.932 Å 更短**，
  而它总能量只高 3.949。所以 **1.932 Å 这个数本身不构成任何证据**：它既不是初猜高能量的原因，
  也不是"对撞"的标志，它只是这条扭转把两个甲基带近以后的几何后果。
- **能量在重原子骨架上**（C − B = 38.182）：与同一二面角上的干净参考相比，初猜帧的骨架被
  整体挤歪了。逐项实测（初猜 vs 刚性参考）：

  | 内部坐标 | 初猜 | 刚性参考 |
  |---|---|---|
  | C1–C6–C7 / C6–C7–C8（联苯两侧键角） | **109.2° / 109.3°** | 120.4° / 120.4° |
  | C0–C1–C2 / C9–C8–C10（邻位角） | 129.1° / 129.5° | 121.0° / 121.0° |
  | 芳环共面性（环 A / 环 B） | 0.0513 / 0.0567 Å | 0.0011 / 0.0013 Å |
  | 带甲基碳相对所在环平面的偏移 | **0.460 / 0.480 Å** | 0.010 / 0.011 Å |
  | 联苯轴键 C6–C7 | 1.443 Å | 1.482 Å |
  | 甲基碳–芳碳 C0–C1 / C8–C9 | 1.530 / 1.532 Å | 1.499 / 1.499 Å |
  | 甲基碳间距 C0···C9 | 3.050 Å | 3.281 Å |
  | 环面夹角（fold） | 84.26° | 71.59° |

  即：**联苯两侧键角被压了 11°、邻位角被撑开 8°、两个环都被挤出共面（0.05 Å）、带甲基的碳
  相对环平面偏出 0.46–0.48 Å**——整副骨架被"压扁"了，而不是某一处局部对撞。
  （逐项能量份额本目录**没有**给出：GFN2 没有分项能量分解，用经验力常数估出来的数不构成证据。）

### 3.5 DFT 侧（B3LYP/def2-SVP）：初猜单点比极小值高 59.9 kcal/mol

- 参考极小值（`refmin_summary.txt`，起点 = 路径第 0 帧，已收敛）：
  `FINAL SINGLE POINT ENERGY -541.189617864318`、`*** OPTIMIZATION RUN DONE ***`、
  `****ORCA TERMINATED NORMALLY****`；末帧 θ = −87.99°（与 xTB 的 −86.62° 一致）。
- 初猜帧的 B3LYP 单点（OptTS 第 1 个循环）：`-541.094225214` → 比极小值高 **+59.86 kcal/mol**。
- OptTS 输入逐字（`optts_refine.inp`）：`! OptTS b3lyp def2-SVP` + `%pal nprocs 4 end` +
  `%maxcore 1024` + `%geom Calc_Hess true`；起点几何 = `xtbpath_ts.xyz` 逐字（θ=−108.03°）。

### 3.6 DFT 侧：OptTS 从初猜出发，56 个循环滑回极小值

`optts_cycle_table.txt`（逐字抽取，左列可回查 48,938 行的原始日志）：

| 循环 | E (Eh) | 比 B3LYP 极小值高 (kcal/mol) | 该循环 Hessian 负本征值 |
|---|---|---|---|
| 1 | −541.094225214 | +59.86 | 4 |
| 2 | −541.142611875 | +29.49 | 3 |
| 3 | −541.165748228 | +14.98 | 3 |
| 4 | −541.179330888 | +6.45 | 3 |
| 5 | −541.186687251 | +1.84 | 1 |
| 10 | −541.186755668 | +1.80 | 1 |
| 20 | −541.187978 | +1.03 | 1 |
| 30 | −541.188225 | +0.87 | 1 |
| 40 | −541.188562 | +0.66 | 1 |
| 50 | −541.188587 | +0.65 | 1 |
| 56 | −541.188591245 | **+0.644** | （未打印，作业已被停） |

- 56 个单点，**从头到尾没有出现任何收敛横幅**；日志里反复出现
  `The optimization has not yet converged - more geometry cycles are needed`。
- 负本征值个数分布（55 次记录）：`4×1, 3×4, 2×5, 1×42, 0×3`——在能量已落到极小值附近 1 kcal/mol
  以内的第 5 循环之后，它绝大多数时候报"1 个负本征值"，但**同时有 3 次报 0 个**。被 ORCA 当作
  "TS 模"跟随的本征值从 −0.02279 一路变到 **+0.00038（正值）**——即它有时把正曲率模式当成 TS 模。
- 末帧几何（`optts_final_geometry.xyz`）：θ = **−99.31°**（起点 −108.03°，B3LYP 极小值 −87.99°），
  E 比极小值高 0.644 kcal/mol。第 5 循环后它一直在比极小值高 1.9 → 0.64 kcal/mol 的狭窄区间里
  游走，几何上离极小值只有几度到十几度的扭转差别。
- 该作业在循环 56 之后被 `kill 7028` 停止（本次实验自己起的进程），磁盘上留下 `refine.xyz`
  （第 56 帧）与 `refine_trj.xyz`（第 1–55 帧）。

### 3.7 旁证：SOP 持久化的 method 拼写被 ORCA 拒掉

`first_attempt_keyword_error.txt`：SOP 自己写出的第一个精修输入是 `! OptTS b3lyp def2svp`，
ORCA 直接报

```
INPUT ERROR
UNRECOGNIZED OR DUPLICATED KEYWORD(S) IN SIMPLE INPUT LINE
DEF2SVP
```

而 `process.json` 里持久化的正是 `method = 'b3lyp/def2svp'`；改成 `def2-SVP` 后同一条管线即可运行。
**没有任何环节把声明里的方法/基组拼写拿去和目标引擎核对**（既没在 declare 拦，也没在 submit 拦，
ORCA 的报错也没有被解析回这条声明）。这与本次"初猜可用性"是两件事，但同属"声明与引擎之间的
一致性"缺口，一并记录。

## 4. 根因假设（**不是**上面的观察事实）

> **本节第 1 条已被第 6 节推翻并保留在案**：我当时把"路径最高帧落在反应物盆地里"归因于
> `--path` 的 Cartesian 线性插值在 180° 转动下必然产生非法中间镜像。第 6 节的实测表明，
> 同样是这条路径、同样是这对端点，只把精修上限放开，最高帧就落到正确的扭转极大上——
> **根因是精修被 3 轮上限截断，不是方法本身**。下面第 2、3 条（管道没有独立校验、DFT 侧
> 顺着同一个错点走）仍然成立。

1. `product_geometry = rotate_about_bond` 这类声明的反应坐标是**绕该键的二面角**，而 xTB MTD
   `--path` 用的是两端 Cartesian 坐标的线性插值：两端在扭转上相差 180° 时，中间镜像本身就不是
   合法几何（环被拉向轴的"压扁"方式、甲基互相顶入），亚稳动力学爬到的高点只能是形变伪影。
   实测到的后果是：路径最高帧的 θ 只离起点 21°、重原子最多挪 0.9 Å（即它仍在反应物盆地里），
   而整个重原子骨架被挤歪——联苯两侧键角压到 109°，芳环出现 0.05 Å 量级的非共面畸变，
   带甲基的碳相对环平面偏出 0.46 Å（3.4 节）。这与"某处局部对撞"无关：同一二面角上的干净
   结构 H···H 反而更短（1.683 Å）而能量只高 3.9 kcal/mol。
2. `xtbpath_ts.xyz` 与"路径最高帧"是同一帧，所以管道里"取最高帧"和"读 TS 候选"两道防线都不构成
   独立校验——**只按路径形状挑点，没有任何一处检查该点是否位于所声明的那条扭转坐标的极大附近**。
3. DFT 侧的现象是上面这条的直接后果：初猜的 B3LYP 单点比极小值高 59.9 kcal/mol（xTB 单点高
   47.4 kcal/mol），P-RFO 在其余方向上全部下坡，只有那个被误判的"TS 模"在上坡——它强度太小
   （本征值 −0.023 → +0.0004），于是几何沿扭转慢慢漂，能量停在极小值上方 0.6 kcal/mol 处。

## 5. 未复现 / 未验证 / 解释不了的项

1. **ORCA 停在的那个点是不是真鞍点：未验证。** 作业从未收敛，也没有在该几何上跑频率/IRC。
   结论不依赖它：无论它是不是鞍点，它只比极小值高 0.644 kcal/mol，不可能是一个真实势垒在
   14–24 kcal/mol 量级过程的过渡态。
2. **扫描两端能量不对称：未解释。** 两个平面端相差 4.06 kcal/mol（+18.328 vs +14.264），且扫描
   采样到的最高点在 \|θ\|≈170.60°（+23.850）而非 180°。候选原因：甲基自身旋转异构体、
   第一个扫描点被一步拽了 93°（86.62°→179.45°）留下约束优化器滞后。本目录依赖的结论
   （初猜所在扭转角的弛豫代价、真实极大不在初猜附近）不依赖这一点，但**扫描势垒的精确数值
   在这一点澄清前不应被引用**。
3. **xTB 的约束角约定与常规二面角差 180°**：`$constrain dihedral: 2,7,8,9, t` 实达角约为
   `180 − t`（原始目标/实达角两列都在 `xtb_scan.csv` 里，可逐行核对）。这里只记录事实，
   不下结论说这是否是本 build 的 bug。
4. **`$scan` 块在本 build 被静默忽略**：探测输入 `xtb_scan_block_probe.inp`（原子序已用正确的
   2,7,8,9，避免"是不是索引写错才不扫"的疑问）逐字为

   ```
   $scan
      2, 7, 8, 9, 0.0, 180.0, 19
   $end
   ```

   运行 `xtb start.xyz --input xtb_scan_block_probe.inp --opt` 退出码 0、`normal termination of xtb`，
   输出里**没有任何扫描步骤**（全文只有 1 处出现 "scan"，就是命令行里的文件名），实际只做了一次
   普通优化：`*** GEOMETRY OPTIMIZATION CONVERGED AFTER 11 ITERATIONS ***`，`TOTAL ENERGY
   -37.106620806098 Eh`——这个值同时充当第 3.2 节的"自由极小值"锚点。故扫描只能由外部逐点约束
   优化驱动（`xtb_scan_driver.py`）。
5. **未做 DFT 扭转扫描**：DFT 侧的坐标只有两个点（B3LYP 极小值、以及 OptTS 轨迹），
   "真实势垒 14–24 kcal/mol" 全部来自 xTB 扫描，**不是** B3LYP 能垒。
6. **锚点 13.0 kcal/mol 未复核**：来自题池（`computed_by_us: false`，`verification: partial`），
   本目录不声称验证或推翻它。
7. **xTB 自报 barrier 的物理含义未验证**：`run 1 barrier: 218.50` 与同一路径保存帧的真实单点
   最大值 44.865 kcal/mol 差得离谱。它是亚稳动力学偏置能量、还是别的定义，本次**没有**去核实；
   这里只把两个数字并排记录。SOP 侧取的是 `xtbpath.xyz` 注释里的相对能（且已用单点交叉核对，
   见 3.2 表），没有用这个自报 barrier。
8. **我先前的一个解释被实测推翻（保留在案）**：我曾把初猜的高能量归因于"甲基 H···H 对撞"。
   3.4 节的对照直接否掉它——同一二面角上弛豫良好的结构 H···H 是 **1.683 Å（更短）**，总能量却只
   高 3.949 kcal/mol；初猜的氢位置按 MMFF 探针也只值 5.269（探针自身偏差 −2.064）。**"1.932 Å"
   这个数不构成任何证据。** 能量在重原子骨架上（38.182）。
9. **xTB 本 build 没有可用的"冻结原子"能力**：`$fix`（斜杠列表与 `1-14` 两种写法）与
   `$constrain atoms:` 三种写法都实测过——重原子照样移动（0.24–0.40 Å），`$fix` 两条路径甚至
   不收敛。所以 3.4 节的"H 弛豫"是用 MMFF94 在冻结重骨架上做的（重原子位移 0.0000 Å 已核），
   并附了同一条探针作用在刚性参考上的**偏差对照**（−2.064 kcal/mol）。这是方法边界，不是等价替代。
10. **一个我先前口头给错、现已更正的数字**：我最初报告"环 B 共面性偏差 0.186 Å"，
   那是把甲基碳 `C9` 误当成环 B 原子算出来的；按正确环 B 原子序（`C7,C8,C10,C11,C12,C13`）
   应为 **0.0567 Å**（环 A 0.0513 Å）。表 3.1 与 `path_frames.csv` 是更正后的值。

## 6. 要害：这是机时上限的假象，放开上限就能拿到接近过渡态的初猜

`refinement_sweep/`（脚本 `xtb_refinement_sweep.py`，端点与 3.0 节完全相同）：

| `$path nrun` 上限 | 引擎结局（逐字） | 最后 barrier (kcal/mol) | 精修轮数 |
|---|---|---|---|
| 3（xTB 内建默认，SOP 当时用的） | `terminated because max. # cycles reached` | 44.865 | 3 |
| 10 | `terminated because max. # cycles reached` | 26.629 | 10 |
| 30 | `terminated because max. # cycles reached` | 18.290 | 30 |
| 100 | **`terminated because grad at TS <threshold`** | **18.299** | **31（引擎自判收敛后自行停止）** |

- **收敛路径的最高帧落在 θ = −5.7°（平面构型）**，正是 3.2 节独立弛豫扫描给出的扭转极大位置
  （扫描给出的极大在 +14.3 ~ +18.3 kcal/mol）；而旧默认（3 轮）的最高帧在 θ = −108°，差 100°。
- 把收敛路径的 TS 候选（`converged_ts_candidate.xyz`）交给 ORCA `OptTS b3lyp def2-SVP`：
  第 1 个循环单点 −541.157610909444 Eh（比 B3LYP 极小值高 **+20.09** kcal/mol），
  全程稳定 **1 个负 Hessian 本征值**（−0.0449，跨循环不漂），**第 9 个循环 `OPTIMIZATION RUN DONE`**
  （`ORCA TERMINATED NORMALLY`），末能量 −541.164070466540 Eh = 比极小值高 **+16.03 kcal/mol**。
  对照：旧（截断）初猜跑 56 轮不收敛、负本征值个数在 0/1 之间乱跳、末态只比极小值高 0.644。
- 因此本目录的主结论是：**"MTD 生成不了接近过渡态的初猜"是假象，根因是精修上限（内建 3 轮）
  被当成收敛**。修法不是换方法，而是：把上限显式交给引擎并跑引擎自己的收敛判据，同时把
  `converged` / `cycles_exhausted` 分开分类，触顶即报 `path_not_converged`、不许当可用初猜。

**代码改动（同批）**：`cloudra/tools/core/xtb_path_runner.py` 新增 `DEFAULT_REFINEMENT_RUNS`、
`build_path_input()`（命令行总是带 `--input path.inp`）、`RefinementTermination` 分类与
`path_not_converged` 终止原因；`ts_guess` 工具暴露 `refinement_runs` 并在触顶时给出补救文本；
SOP `guess` 阶段对触顶单独阻塞。

**未验证项**：频率作业（确认"恰好 1 个虚频"）已起但按用户指示中止，**没有**跑完，所以"是几阶鞍点"
只有 ORCA `OptTS` 自己的 Hessian 负本征值个数作为证据，没有独立虚频数据；IRC 未跑。
另：`refinement_sweep/` 里的三个 nrun 日志是**随机采样**（MTD 无固定种子），复跑的具体 barrier
数值会变，"是否触顶 / 引擎是否自判收敛"这两类结局是稳定的。

## 7. 摘录脚本（可对原始日志逐行复核）

```bash
# OptTS 循环表（左列 = refine.stdout.log 行号）
python3 - <<'PY'
log = open(".tscheck/ts/ts_0001/jobs/job_0002/refine.stdout.log", errors="replace").read().splitlines()
keys = ("GEOMETRY OPTIMIZATION CYCLE", "FINAL SINGLE POINT ENERGY", "Hessian has",
        "TS mode is mode number", "The optimization has not yet converged",
        "Lowest eigenvalues of the Hessian", "Current Energy", "Current gradient norm")
for i, l in enumerate(log):
    if any(k in l for k in keys) or l.strip().startswith(("Maximum allowed component",
                                                          "Current trust radius")):
        print("%6d: %s" % (i + 1, l.rstrip()))
PY
```

其余派生量（θ、环共面性、甲基间距、轴键长、位移）全部由同目录 `path_analysis.py`
从逐字保存的 `xtbpath.xyz` 重算，不依赖任何中间缓存。
