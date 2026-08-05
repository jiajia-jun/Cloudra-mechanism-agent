---
name: first-principles-calculation
description: Provide domain expertise for periodic DFT / first-principles calculations (VASP, CP2K, Quantum ESPRESSO). Use when setting up INCAR parameters, optimizing k-points and ENCUT, configuring DFT+U, calculating surfaces/adsorption, troubleshooting SCF convergence, or handling charged periodic systems (background charge / Makov-Payne / PSOLVER), CP2K input generation, and CP2K convergence tuning order.
---

# 1. 本地工具链映射 (Toolchain Mapping)
在规划与执行周期性第一性原理计算（VASP / CP2K）时，应依托 `CLOUDRA` 的本地环境：

## 1.1 VASP 工具链
- **配置文件生成与结构操作**：优先使用 ASE (Atomic Simulation Environment) 库。通过编写轻量级 Python 脚本使用 ASE 的 `ase.io` 和对应的计算器（Calculators）模块来自动化处理晶体结构和生成 POSCAR、INCAR、KPOINTS。避免使用 shell `echo` 盲目手敲和拼接输入文件，这容易导致参数遗漏和拼写错误；但在极简单的单点测试或一次性调试中，可酌情使用。
- **写 ASE 脚本前必读参考**：不要凭记忆默写 ASE API。先通过 `getskill("first-principles-calculation", other="ase-guide.md")` 获取完整代码模式库（bulk/surface/adsorbate 建模、FixAtoms 约束、Vasp/GPAW 计算器、BFGS/MD/NEB、结构校验与调试），并通过 `getskill("first-principles-calculation", other="examples")` 查看 `examples/` 下的可运行完整脚本（吸附能 `adsorption_energy.py`、晶格优化 `lattice_optimization.py`、NEB 势垒 `neb_barrier.py`），在其基础上改编。速查可用 `other="ase-quick-reference.md"`。
- **任务投递**：统一调用 `submit_compute_job`，并将 `job_type` 指定为 `vasp`。因为 VASP 计算通常非常耗时，应设置 `is_async=True`。
- **结果解析与状态监控**：避免直接 `cat` 读取巨大的 `OUTCAR`。优先使用本地系统中的日志解析器或编写 Python 代码解析 `vasprun.xml` / `OUTCAR`（如读取最终能量、收敛步数、磁矩）；在快速查看收敛状态时，可读取 OUTCAR 的末尾摘要。

## 1.2 CP2K 工具链
- **输入文件生成**：推荐用 **Multiwfn** 便捷创建 CP2K 的 `.inp` 输入文件（较新版本；`sobereva.com/587` 有详细教程），其默认参数（如 `EPS_SCF 2.0E-06`、`MAX_SCF 128`、OT/对角化选择、`&OUTER_SCF` 等）对大多数体系都是合适值，**不了解 CP2K 时不要乱改**。用 ASE 的 `CP2K` calculator 生成亦可，但默认值不如 Multiwfn 贴合成体系。
- **任务投递**：调用 `submit_compute_job`，`job_type` 指定为 `cp2k`（输入为 `.inp` 文件），长任务 `is_async=True`。
- **结果解析**：CP2K 的 `.out` 文件中关注 `SCF run converged` / `*** WARNING ... SCF run NOT converged ***`、`Total energy`、几何优化步的 `MAX gradient` / `MAX force` 等；用 `text_reader` 分段读取或 Python 正则解析，不要整文件 `cat`（大体系 .out 可能数百 MB）。

# 2. 限制与例外 (Constraints & Exceptions)
以下规则是 VASP 计算的常见最佳实践，但在特定场景下存在合理例外。遇到矛盾时，优先以**当前体系的收敛性测试和文献惯例**为准。

1. **K点维度限制**：对于二维材料、表面或 Slab 模型，真空层方向（通常是 Z 轴）的 K 点**通常应设为 1**（例如 `5 5 1`）。仅在计算某些层间耦合性质时，才可能需要少量增加。
2. **展宽（ISMEAR）选择**：
   - **金属/半金属**：通常使用 `ISMEAR = 1` 或 `2`（Methfessel-Paxton），`SIGMA` 取 0.1~0.2 eV，并检查 `entropy TS` 是否 < 1 meV/atom。
   - **较大带隙半导体/绝缘体**：高精度单点能/DOS 推荐 `ISMEAR = -5`（四面体法），但要求至少 4 个 k 点形成四面体。
   - **小带隙半导体或未知带隙体系**：当 k 点较疏、价带顶/导带底跨越费米面导致 SCF 振荡或带结构出现锯齿时，可使用 `ISMEAR = 0`（Gaussian）并配合小 `SIGMA`（0.03~0.05 eV）稳定收敛，必要时外推到 σ→0。这正是 ChemBench 等题目中"small artificial smearing and extrapolate to zero smearing"的物理依据。
   - 若已知体系为绝缘体/半导体且 k 点足够，优先使用 `ISMEAR = -5` 而非 Gaussian smearing。
3. **POTCAR 拼接限制**：合并 POTCAR 时，应按照 POSCAR 中的元素顺序拼接，避免乱序；不同版本 POTCAR 不可混用。
4. **强关联体系（DFT+U）**：当体系包含**开放壳层的过渡金属氧化物/硫化物、稀土/镧系化合物**时，纯 GGA（如 PBE）通常会低估电子关联，**应评估**是否开启 `LDAU = .TRUE.`。对于金属单质、简单金属间化合物或主族元素体系，通常不需要 +U。

# 3. 科学知识库 (Scientific Knowledge Base)

## 3.1 截断能与展宽机制
- **ENCUT**：
  - 常规结构优化（体积不变）：ENCUT 取各元素 POTCAR 中最高 `ENMAX` 的 1.0~1.3 倍通常足够，具体需通过收敛测试确认。
  - **晶胞体积优化（ISIF=3）**：VASP 官方建议 ENCUT ≥ 1.3 × max(ENMAX)，以减少 Pulay 应力。若计算资源允许，可进一步提高至 1.5 倍或做 ENCUT 收敛测试。
  - 注意：ENCUT 过大不仅浪费算力，还可能导致 `PSMAXN too small` 等赝势相关错误。
- **ISMEAR 与 SIGMA**：
  - **金属**：`ISMEAR = 1` 或 `2`，`SIGMA` 取 0.1~0.2。
  - **半导体绝缘体**：默认 `ISMEAR = 0`，`SIGMA = 0.05`；但也可以先用 `ISMEAR = -5` 测试。
  - **高精度单点能/DOS**：使用 `ISMEAR = -5`（四面体法）。如果体系带隙很小、SCF 难以收敛或 k 点极稀疏，可改用 `ISMEAR = 0` 配合小 SIGMA，再外推到零展宽。
  - **不确定带隙时**：VASP 官方推荐先用 `ISMEAR = 0` + `SIGMA = 0.03~0.1` 进行高通量/初算，稳定后再切换更精确方法。

## 3.2 强关联体系 (DFT+U)
- **参数设置 (`LDAUTYPE=2`)**：必须按照 POSCAR 元素顺序设定 `LDAUL`, `LDAUU`, `LDAUJ`。
- **LMAXMIX**：加上 U 后，必须开启 `LMAXMIX = 4` (对 d 电子) 或 `6` (对 f 电子) 以保证空间混合的正确性，否则极易陷入亚稳态。

## 3.3 k 点网格与布里渊区采样
- **六方/三角晶格、二维材料**：优先使用 **Γ-centered + 奇数 k 点**（如 `11 11 1`、`13 13 1`）。这是因为 Monkhorst-Pack 偶数网格可能不包含 Γ 点或高对称点 K，导致沿 Γ-K 方向出现周期性数值振荡。
- **正交/立方晶格**：Monkhorst-Pack 和 Γ-centered 均可，通常以能量/应力收敛测试结果为准。
- **采样不足 vs 网格类型 vs 展宽问题**：
  - 加密 k 点后振荡明显减小或消失 → 采样不足，继续增加密度。
  - 加密 k 点后振荡减轻但不消失，且体系带隙较大、振荡表现为沿高对称方向的周期性网格伪影 → 更可能是网格类型或晶格对称性问题，尝试 Γ-centered 奇数网格。
  - 小带隙/近金属体系在费米面附近出现锯齿状振荡，且加密 k 点仍不消失 → 优先使用 Gaussian/Methfessel-Paxton smearing 并外推到零展宽，而不是立即换网格。这正是 ChemBench 等题目中"small artificial smearing and extrapolate to zero smearing"的物理依据。

## 3.4 Slab 模型与吸附
- **真空层厚度**：至少 15 Å；对于高度极化或长程相互作用的体系，建议 20 Å 以上。
- **偶极校正**：若单侧吸附或上下表面不对称，建议开启 `LDIPOL = .TRUE.` 和 `IDIPOL = 3`。
- **色散校正**：算吸附能通常需要开启色散校正，首选 DFT-D3(BJ) (`IVDW = 12`)。

## 3.5 杂化泛函与 HSE06
- **适用场景**：HSE06 / PBE0 主要用于修正带隙、改善电子局域化描述。**它们不会消除 k 点采样伪影**。
- **使用顺序**：先用 GGA 优化结构并测试 k 点收敛，再算 HSE06 单点/能带。
- **关键参数（VASP）**：`LHFCALC = .TRUE.`，`HFSCREEN = 0.2`，`AEXX = 0.25`；`ALGO` 常用 `Damped` 或 `All`；可读取 PBE 的 `WAVECAR`/`CHGCAR` 作为初猜。
- **注意**：杂化泛函计算量远大于 GGA，且对 k 点密度要求更高。

# 4. Agent 工作流：VASP 计算流水线 (Workflow State Machine)
**Step 1: 结构建立与 K/E 收敛测试**
- 优先查阅在线晶体数据库（如 Materials Project）获取基础 CIF 文件，并用 ASE 读取处理。
- 正式计算前，建议编写基于 ASE 的自动化脚本对 ENCUT 和 KPOINTS 进行收敛性遍历测试（标准：能量变化 < 1~2 meV/atom）。

**Step 2: 几何优化 (Relaxation)**
- 根据体系选择 `ISIF`：
  - `ISIF=2`：用于 Slab 模型或二维材料平面内优化（固定体积）。
  - `ISIF=3`：用于三维体相材料的全面优化。
- 若包含未成对电子（特别是过渡金属），必须开启自旋极化 (`ISPIN=2`) 并赋予合理的初始磁矩 (`MAGMOM`)。

**Step 3: 高精度计算 (Static/DOS/Band)**
- 优化完成后，提取 `CONTCAR` 覆盖 `POSCAR`。
- 将 `NSW` 设为 0，调整 `ISMEAR=-5` 进行高精度单点计算。

# 5. 异常诊断与排障断路器 (Circuit Breakers)
当 VASP 电子步（SCF）发散或达到 `NELM` 仍不收敛时，执行以下排查：
1. **结构崩溃排查**：检查第一个离子步能量是否大得离谱（如 1E5 eV）。若是，说明原子有严重重叠，立刻停止计算并重新检查结构建模代码。
2. **混合参数调整（金属/磁性体系杀手锏）**：
   - 动态修改 INCAR：`AMIX = 0.2`, `BMIX = 0.0001`, `AMIX_MAG = 0.8`, `BMIX_MAG = 0.0001`。
3. **展宽调节**：若为金属体系，临时将 `SIGMA` 调大（如 0.2），待粗收敛后读取 `WAVECAR` 再调小重算。
4. **算法降级**：将 `ALGO` 从 `Fast` 降级为 `Normal`，若仍发散尝试 `All` 或 `Damped`。
*重要：若上述尝试 2 次后仍发散，必须停止调用并上报用户。*

# 6. CP2K 计算要点与常见雷区
以下内容综合自计算化学公社（bbs.keinsci.com）与思想家公社（sobereva.com）的实战经验。遇到 CP2K 计算问题时，按本节顺序排查。

## 6.1 CP2K 输入文件与基础参数
- **基组与赝势必须配对**：CP2K 中 MOLOPT 系列基组与 GTH 赝势是配套使用的（`.inp` 里 `&KIND` 需同时给出 `BASIS_SET` 和 `POTENTIAL`）。
  - 常规精度：`DZVP-MOLOPT-SR-GTH`；高精度/算相互作用能：`TZV2P-MOLOPT-GTH`（其 BSSE 问题很小，通常可以不用 counterpoise）。
  - **不要用老式的 `TZV2P-GTH`**（非 MOLOPT 系列）——过时且结果明显更差。
- **CUTOFF / REL_CUTOFF**：需要做收敛性测试（尤其算相互作用能/吸附能时，收敛性测试比总能量更有意义）。注意 `REL_CUTOFF` 默认 60 左右通常起步偏低，Multiwfn 生成时会给出较合理的组合。
- **MAX_SCF 默认 50 太小**：CP2K 默认 `MAX_SCF = 50` 经常不够，Multiwfn 生成的文件默认 128。跑长任务或难收敛体系务必调大。
- **k 点**：CP2K 通过 `&KPOINTS` 支持 k 点采样，但**DFT+U 不支持 k 点**（加 U 时只能用 Γ 点）；且 CP2K 不利用晶格对称性节约 k 点，等效于更贵的采样，k 点密度要按此预算。
- **自旋**：自旋极化体系必须写 `UKS`，否则即使设了 `MULTIPLICITY > 1`，CP2K 也会按闭壳层计算，结果完全错误。

## 6.2 带电周期性（重点雷区）
- **三维周期性带电体系**：CP2K 会自动加入**均匀补偿背景电荷**（jellium/补偿电荷）来中和净电荷，`CHARGE` 关键字设的是**体系净电荷**（不是"背景电荷"），例如带 +2 的晶胞写 `CHARGE 2`。
- **Makov-Payne 校正**：CP2K **没有内置** Makov-Payne（或 SCPC）校正（VASP 6.2+ 才有 SCPC）。三维周期性带电体系的绝对能量需要**手动做 Makov-Payne 类校正**，其作用是让能量随盒子尺寸更快收敛。因此：
  - 三维带电体系必须做**盒子尺寸收敛测试**，报告能量时说明盒子大小与校正方式。
  - 若当三维周期性算带电 slab 吸附，必须考虑 Makov-Payne 之类校正（否则吸附能会严重失真，例如金属表面吸附 Zn²⁺ 算出 -26 eV 的离谱值）。
- **二维周期性是 CP2K 相对 VASP/QE 的极大优点**：带电 slab 吸附、或吸附带电物质，**都建议当二维周期性计算**（`&POISSON` 用 `PSOLVER MT`）。计算被吸附物、slab 自身时也应当用和吸附体系**同样的盒子**，使得能量求差（吸附能）时误差尽可能抵消。
- **PSOLVER MT 的硬性要求**：非周期性方向的盒子尺寸**至少是电子密度分布跨度的两倍**（否则会出现成键诡异、体系解体等明显错误结果）。
- **一维带电体系**：可完全当作一维周期性计算（`PSOLVER ANALYTIC`）；或者用 `PSOLVER PERIODIC` 结合三维周期性再考虑 Makov-Payne 校正，具体看体系细节、净电荷分布和要算的性质。
- **带电缺陷体系**：先想清楚该不该带电、带多少电荷（中性缺陷 vs 带电缺陷）。带电缺陷的绝对能收敛性差，必须做盒子尺寸收敛测试；带电体系只做几何优化时无需额外校正（力不受补偿背景电荷的均匀场影响）。
- **离子吸附能**：气相下离子吸附的静电作用太强，吸附能会异常偏大；要得到合理值通常需要溶剂效应（隐式或显式）。注意 CP2K 的隐式溶剂模型（SCCS）支持不佳、经常不收敛，必要时换 QE 等程序。计算吸附能时确保各模型（吸附体系/被吸附物/slab）盒子完全一致。

## 6.3 SCF 不收敛：排查顺序与调参顺序
**第 0 步：分清是"SCF 不收敛"还是"几何优化不收敛"**。几何优化不收敛要用几何优化不收敛的解决方法（调 `OPTIMIZER`、`MAX_ITER`、`TRUST_RADIUS`、几何收敛判据），**改 SCF 设置毫无意义**；把 `EPS_SCF` 改糙（如 2.0E-06 → 2.0E-04）只会导致几何优化震荡，更妨碍收敛。按以下顺序排查：

1. **检查结构**：原子是否重叠？晶胞尺寸是否合理（PBC 下原子是否挨得太近，如长链分子伸出盒子）？低维体系是否设对了周期性方向（如把 2D 材料设成三维真空盒会带来悬键问题）？真空层是否够？
2. **检查设置**：UKS/自旋、净电荷（`CHARGE`）、多重度、k 点密度、`CUTOFF`/`REL_CUTOFF` 是否合理？泛函是否合适（HF 成分大的泛函 HOMO-LUMO gap 大，更容易收敛）？
3. **换初猜（性价比最高的一步）**：
   - `SCF_GUESS RESTART` + `WFN_RESTART_FILE_NAME` 读取已收敛的 `.wfn`/`.kp` 文件。
   - 先用小基组（如 DZVP）算到收敛，再读取初猜换大基组继续。
   - 先用杂化泛函算收敛，再读初猜换纯泛函（杂化泛函必须配合 `SCREEN_ON_INITIAL_P` 且读之前收敛的波函数，否则结果无意义且难收敛）。
   - 磁性体系：在 `&KIND` 里设 `MAGNETIZATION`，或用 `&BS` 精细指定原子组态（如离子性晶体给 Na⁺/Cl⁻ 组态、反铁磁给 Fe1=3/Fe2=-3 之类）。
   - DFT+U 有时能帮助 SCF 收敛（注意不支持 k 点）。
4. **提高数值精度**：增大 `CUTOFF`/`REL_CUTOFF`，减小 `EPS_DEFAULT`，或切换 `GPW`↔`GAPW`。
5. **对角化算法（&SCF 内）**：
   - 金属/无带隙体系：用 smearing（如 Fermi-Dirac）+ `ADDED_MOS` 增加占据轨道。
   - `LEVEL_SHIFT` 0.3~0.4 Hartree 移动能级，稳定难收敛体系。
   - `MIXING`：`DIRECT_P_MIXING` 表现极差；默认 `BROYDEN_MIXING`；难收敛时把 `ALPHA` 从 0.4 降到 0.1~0.3，`NBROYDEN` 从默认 4 加大到 8~12；`PULAY` 作备选。
   - GAPW 下可试 `GMIX_P`（配 `MAX_GVEC_EXP 3.0`）——**仅对 GAPW 有效**（社区实测经验）。
   - 经验配方（对角化难收敛）：`MODIFIED_BROYDEN_MIXING`，`ALPHA 0.2`、`BETA 1.5`、`NBROYDEN 24`、`GMIX_P`、`MAX_GVEC_EXP 3.0`、`N_SIMPLE_MIX 16`。
6. **OT 算法（&SCF 内，OT=T）**：
   - 开 `&OUTER_SCF`（Multiwfn 默认开，对收敛帮助极大）。
   - preconditioner 选 `FULL_ALL` 通常最好；预算紧时用 `FULL_SINGLE_INVERSE`/`FULL_KINETIC`。
   - `ALGORITHM` 从 `STRICT` 换成 `IRAC` 更稳健。
   - `MINIMIZER` 从 `DIIS` 换成 `CG` + `LINESEARCH 3PNT` 更稳。
   - OT 收敛后的波函数可保存为对角化计算的初猜。
7. **几何优化/MD 过程中的 SCF 不收敛**：
   - 优化中途偶尔 SCF 不收敛可以继续跑（2024.1 及之后版本需设 `IGNORE_CONVERGENCE_FAILURE=.TRUE.`）。
   - 优化初期 SCF 不收敛可先凑合跑，结构变合理后 SCF 自然变好收敛。
   - `EXTRAPOLATION ASPC` 是默认且通常最好；k 点下不支持外推时建议 `EXTRAPOLATION USE_PREV_P`。
   - MD 可减小 `TIMESTEP`；GEO_OPT 可减小 `TRUST_RADIUS`。
8. **走投无路**：放宽 `EPS_SCF`（几何优化 1E-5~1E-6 通常够，高精度单点 1E-6~1E-7），但不要为了"看起来收敛"把精度降得过低（如 1E-4），否则几何优化震荡、结果不可信。

## 6.4 CP2K 其他高频坑
- **杂化泛函**：用 ADMM 加速；`SCREEN_ON_INITIAL_P` 必须配合读取已收敛波函数（否则屏蔽项基于无意义的初始密度矩阵，结果错误且难收敛）。详见 sobereva.com/690。
- **能带计算**：纯泛函能带可用 band.bs 方法（`&BAND` + 高对称 k 点路径），结合 Multiwfn 后处理；见论坛精华帖（tid=44474）。
- **隐式溶剂**：CP2K 的 SCCS 溶剂模型支持不佳，经常不收敛；需要溶剂效应时评估换 QE（有 EnvSCCS 等更成熟实现）或用显式溶剂。
- **性能与内存**：GAPW 比 GPW 贵很多；`CUTOFF` 过大或 k 点过多容易内存不足；不要盲目堆精度。

# 7. 判例来源（计算化学公社 / 思想家公社）
关键论断的原始出处（供进一步查阅与复核）：
- **CP2K 中遇到 SCF 难收敛时的解决方法**（Sobereva 博文，含上述第 6.3 节完整方法论）：http://sobereva.com/665
- **CP2K 做杂化泛函计算的关键要点和简单例子**：http://sobereva.com/690
- **使用 Multiwfn 非常便利地创建 CP2K 程序的输入文件**：http://sobereva.com/587
- **关于 cp2k 对角化计算中 scf 难收敛的一些个人经验**（GMIX_P、MODIFIED_BROYDEN_MIXING 配方）：http://bbs.keinsci.com/forum.php?mod=viewthread&tid=59859
- **cp2k 对周期性带电+有偶极体系计算吸附能的思考和疑问**（三维带电自动 jellium 背景电荷、Makov-Payne 手动算、PCCP 2018 参考）：http://bbs.keinsci.com/forum.php?mod=viewthread&tid=44444
- **如何准确计算 Zn(100) 晶面吸附金属离子的能量**（带电 slab 用二维周期性、吸附能各模型同盒子、SCCS 隐式溶剂常不收敛）：http://bbs.keinsci.com/forum.php?mod=viewthread&tid=57736
- **PSOLVER MT 做二维周期性计算的要求**（非周期方向盒子 ≥ 电子密度分布跨度的两倍；TZV2P-MOLOPT-GTH 优于旧 TZV2P-GTH）：http://bbs.keinsci.com/forum.php?mod=viewthread&tid=58830
- **一维带电体系的 PSOLVER 选择**（ANALYTIC 或 PERIODIC + Makov-Payne）：http://bbs.keinsci.com/forum.php?mod=viewthread&tid=58999
- **cp2k 优化时几何构型优化不收敛**（几何优化不收敛 ≠ SCF 不收敛，改 SCF 设置毫无意义）：http://bbs.keinsci.com/forum.php?mod=viewthread&tid=31404
- **带电体系的计算问题之浅见**：http://bbs.keinsci.com/forum.php?mod=viewthread&tid=28546
- **cp2k 利用纯泛函进行能带计算的简单方法**（精华帖）：http://bbs.keinsci.com/forum.php?mod=viewthread&tid=44474
