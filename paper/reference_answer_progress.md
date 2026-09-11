# P1 参考能垒标定 — 进度与环境诊断

> 依据：`paper/reference_answer_task_P1.md`（计算者 P1 任务单）、`paper/reference_calc_plan.md`。
> 本文件记录 P1 的逐题进度与环境状态；数值结论以工具输出为准。

## 统一口径（must-follow）
- 方法：**MACE-OMol25**（唯一金标准，2026-08-25 决策）；驱动层等价二选一：ORCA `ExtOpt`（本机路径）/ Gaussian `external="mace"`（g16 环境）。
- 能垒基准：`central_complex`（TS 相对反应物/离子-偶极络合物）。
- 能垒类型：按题定义（Ea/ΔE‡/ΔH‡/ΔG‡），不明确保持 null。
- TS 验收：n_imag==1（排除 <100 cm^-1 伪低频）+ 双向 IRC 端点连通。
- 证据文件必须带 `smiles: <SMILES>` 注释行。
- 回填字段：`gold.reference_computation` = {level_of_theory:"MACE-OMol25", barrier_kcal_mol, barrier_type, barrier_reference:"central_complex", verification:"computed_by_us", computed_by_us:true}。
- easy/normal 权重 xTB 仅作构象/TS 猜测辅助，**不计入参考能垒**。

## P1 题单（43 题算能垒 + 10 对 impossible）
### normal（13）
- A 族：NA1, NA2, NA4, NA5, NA7（NA1=试点题）
- U 族：NU1, NU5, NU6, NU7
- X 族：NX1, NX2, NX3, NX4
### hard（13，立体化学，多数需 selectivity）
- E：HE1, HE2, HE3； I：HI1, HI4； G：HG1, HG2； J：HJ1, HJ2, HJ4； H：HH1； B：HB7； K：HK1
### easy（17）
- M：M1, M3, M6, M8, M10, M12, M14, M15, M16（M1 大体系）； L：L1, L2； C：C1, C2, C3； T：T1, T3； X：X1
### impossible I/S（10 对，不算能垒，走"确不可算"验证）
- IA11/SA11, IA7/SA7, IA8/SA8, IE2/SE2, IG7/SG7, IH8/SH8, II2/SI2, II8/SI8, IJ6/SJ6, IJ7/SJ7

## 执行顺序（P1）
1. 试点 NA1 → 2. normal A→U→X → 3. hard E→I→G→J→H→B→K → 4. easy M→L→C→T→X → 5. impossible I/S 验证。

## 环境诊断（2026-09-02 — 已过时；2026-09-03 已解决，见下方「计算栈验证」与「待决策」）
| 成分 | 状态 | 说明 |
|:--|:--|:--|
| mace python 包 | ✅ 0.3.16 | 需 `KMP_DUPLICATE_LIB_OK=TRUE` 规避 libomp 警告 |
| MACE-OMol25 权重 | ✅ | `~/.cache/mace/MACE-omol-0-extra-large-1024.model` → `/Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model`（repo 里的 `.md` 其实是论文，不是权重） |
| ASE | ✅ 3.29.0 | |
| xtb | ✅ | 辅助 |
| ORCA 6.1.1 | ✅ | `/Users/cloudrayyy/opt/orca_6_1_1/orca`；~~无 MACE/MLIP 支持，不能驱动 MACE~~（此为该时刻结论；2026-09-03 装 `orca-mlips-mace` 后经 `%method ProgExt` 可驱动，见下） |
| Gaussian g16 | ❌ 缺失 | 任务单原指定的 `external="mace"` 驱动；本机始终无 g16 |
| g16-mlips | ❌ 缺失 | 可 pip 装（g16_mlips-1.1.1），但运行时需 g16 |

**（过时）核心阻塞**：~~任务单指定的金标准驱动是 Gaussian g16 + g16-mlips 经 `external="mace"`；本机无 g16。
唯一能在本机实际运行 MACE-OMol25 的驱动是 ASE 直驱 MACE（实测 H2O 单点 0.2s，float64 高精度可跑）。~~
→ 已由 2026-09-03 驱动选型解决（ORCA `ExtOpt` + orca-mlips-mace，见「待决策」与「计算栈验证」）。
仓库内"OMol25 权重"文件 `ideapool/mlp_benchmark/models/md_omol25/2025_levine_omol25/2025_levine_omol25.md` 实为 **arXiv:2505.08762 论文 Markdown**，不是模型权重；真实权重在 `/Users/cloudrayyy/opt/mace-omol25/`。

## 待决策
- [x] 驱动选型已于 2026-09-03 确定：**ORCA 6.1.1 经 ExtTool(ProgExt) + orca-mlips[mace] 插件直驱 MACE-OMol25**（Gaussian external 不可行：无 g16；ASE 直驱为备选）。

## 计算栈验证（2026-09-03，端到端跑通 ✅）
- `orca-mlips[mace]` 1.2.1 已装（chemai env），**未破坏**现有 mace 0.3.16 / e3nn 0.4.4 / torch 2.13.0；生成 `mace`/`orca-mlips-mace` 命令。
- **关键配置**：ORCA 的 `ProgExt` 必须给 **wrapper 完整路径**（仅写 `"mace"` 会报 `File mace not found`）。
- **输入模板**（几何优化）：
  ```
  ! ExtOpt Opt
  %pal nprocs 4 end
  %maxcore 1024
  %method
    ProgExt "/Users/cloudrayyy/miniconda3/envs/chemai/bin/mace"
    Ext_Params "--model /Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model --device cpu --dtype float64"
  end
  *XYZFILE 0 1 <geom>.xyz
  ```
- **运行所需环境**：`PATH` 加入 ORCA 目录 + openmpi-4.1.8/bin（否则 `mpirun not found`）；`KMP_DUPLICATE_LIB_OK=TRUE`（否则 libomp 冲突）。
- **验证结果**（H2O）：
  - `ExtOpt Opt`：ORCA TERMINATED NORMALLY，`External energy and gradient 99.9%`，优化后 E=-76.4336 Eh（与 ASE 单点 -2079.865 eV 一致），O-H 0.957 Å。
  - `ExtOpt NumFreq`：ORCA TERMINATED NORMALLY，`Numerical frequency calculation 94.3%`；水频率 1621.64 / 3817.73 / 3918.02 cm⁻¹（全正，无虚频 = 极小值）。
- **后续需验证**：TS 优化 `ExtOpt OptTS` 与 IRC 的可行性（预计在试点 NA1 中）。
- **cloudra 集成待办**：`submit_compute_job`(job_type='orca') 需能找到 orca、把上述环境变量/PATH 传给计算执行器；否则退化为直接调 `orca` 二进制。

## 试点准备（NA1）
下一步：对 NA1（normal A 族，最重族，含 3 个 TS 的 Cope/重排网络）跑通「构象预筛 → TS guess → OptTS → NumFreq(n_imag==1) → 双向 IRC → 能垒提取 → 回填」。
- NA1 任务定义：`ideapool/tasks/normal/NA1.json`。

## 2026-09-12 分工重排（60 题集）

- 背景：`7bb318d`（2026-09-09）把题集从 120 缩到 60（easy/normal/hard/impossible = 20/10/10/20），
  旧 P0/P1 任务单中 27/40 个 task_id 已失效；试点题 NA1 已删除。
- 已按当前 60 题重分：`paper/reference_answer_task_P0.md`（31 题，工作分 ~325）与
  `paper/reference_answer_task_P1.md`（29 题，~318）。工作分模型不变（Σ(TS数 × 体系重原子数)，
  family 不可分）；impossible 档 P0 承担非 A 族 5 对、P1 承担 A 族 5 对。
- 新试点：P0 先 X1（打通流程）再 NQ1（30.0 [partial] 锚点交叉校验）；P1 先 P3。
- 逐题完成数仍为 0（全部 `computed_by_us=false`）；计算栈状态不变（H2O Opt/NumFreq 已验证，
  OptTS/IRC 端到端待试点探明）。
- 注意：回填 JSON 后不要重跑 `gen_*_tasks.py`（确定性重生会覆盖手工回填，见两份任务单 §2 末尾）。
