---
name: first-principles-calculation
description: Provide domain expertise for periodic DFT / first-principles calculations (VASP, CP2K, Quantum ESPRESSO). Use when setting up INCAR parameters, optimizing k-points and ENCUT, configuring DFT+U, calculating surfaces/adsorption, or troubleshooting SCF convergence.
---

# 1. 本地工具链映射 (Toolchain Mapping)
在规划与执行周期性第一性原理计算（如 VASP）时，应依托 `CLOUDRA` 的本地环境：
- **配置文件生成与结构操作**：优先使用 ASE (Atomic Simulation Environment) 库。ASE 的接口高度统一，适合智能体进行程序化调用。通过编写轻量级 Python 脚本使用 ASE 的 `ase.io` 和对应的计算器（Calculators）模块来自动化处理晶体结构和生成 POSCAR、INCAR、KPOINTS。避免使用 shell `echo` 盲目手敲和拼接输入文件，这容易导致参数遗漏和拼写错误；但在极简单的单点测试或一次性调试中，可酌情使用。
- **写 ASE 脚本前必读参考**：不要凭记忆默写 ASE API。先通过 `getskill("first-principles-calculation", other="ase-guide.md")` 获取完整代码模式库（bulk/surface/adsorbate 建模、FixAtoms 约束、Vasp/GPAW 计算器、BFGS/MD/NEB、结构校验与调试），并通过 `getskill("first-principles-calculation", other="examples")` 查看 `examples/` 下的可运行完整脚本（吸附能 `adsorption_energy.py`、晶格优化 `lattice_optimization.py`、NEB 势垒 `neb_barrier.py`），在其基础上改编。速查可用 `other="ase-quick-reference.md"`。
- **任务投递**：统一调用 `submit_compute_job`，并将 `job_type` 指定为 `vasp`。因为 VASP 计算通常非常耗时，应设置 `is_async=True`。
- **结果解析与状态监控**：避免直接 `cat` 读取巨型的 `OUTCAR`。优先使用本地系统中的日志解析器或编写 Python 代码解析 `vasprun.xml` / `OUTCAR`（如读取最终能量、收敛步数、磁矩）；在快速查看收敛状态时，可读取 OUTCAR 的末尾摘要。

# 2. 限制与例外 (Constraints & Exceptions)
以下规则是 VASP 计算的常见最佳实践，但在特定场景下存在合理例外。遇到矛盾时，优先以**当前体系的收敛性测试和文献惯例**为准。

1. **K点维度限制**：对于二维材料、表面或 Slab 模型，真空层方向（通常是 Z 轴）的 K 点**通常应设为 1**（例如 `5 5 1`）。仅在计算某些层间耦合性质时，才可能需要少量增加。
2. **展宽（ISMEAR）选择**：
   - **金属/半金属**：通常使用 `ISMEAR = 1` 或 `2`（Methfessel-Paxton），`SIGMA` 取 0.1~0.2 eV，并检查 `entropy TS` 是否 < 1 meV/atom。
   - **较大带隙半导体/绝缘体**：高精度单点能/DOS 推荐 `ISMEAR = -5`（四面体法），但要求至少 4 个 k 点形成四面体。
   - **小带隙半导体或未知带隙体系**：当 k 点较疏、价带顶/导带底跨越费米面导致 SCF 振荡或带结构出现锯齿时，可使用 `ISMEAR = 0`（Gaussian）并配合小 `SIGMA`（0.03~0.05 eV）稳定收敛，必要时外推到 σ→0。这正是 ChemBench 等题目中"small artificial smearing and extrapolate to zero smearing"的物理依据。
   - 若已知体系为绝缘体/半导体且 k 点足够，优先使用 `ISMEAR = -5` 而非 Gaussian smearing。
3. **POTCAR 拼接限制**：合并 POTCAR 时，应按照 POSCAR 中的元素顺序拼接，避免乱序；不同版本 POTCAR 不可混用。
4. **强关联体系（DFT+U）**：当体系包含**开放壳层的过渡金属氧化物/硫化物、稀土/锕系化合物**时，纯 GGA（如 PBE）通常会低估电子关联，**应评估**是否开启 `LDAU = .TRUE.`。对于金属单质、简单金属间化合物或主族元素体系，通常不需要 +U。

# 3. 科学知识库 (Scientific Knowledge Base)

## 3.1 截断能与展宽机制
- **ENCUT**：
  - 常规结构优化（体积不变）：ENCUT 取各元素 POTCAR 中最高 `ENMAX` 的 1.0~1.3 倍通常足够，具体需通过收敛测试确认。
  - **晶胞体积优化（ISIF=3）**：VASP 官方建议 ENCUT ≥ 1.3 × max(ENMAX)，以减少 Pulay 应力。若计算资源允许，可进一步提高至 1.5 倍或做 ENCUT 收敛测试。
  - 注意：ENCUT 过大不仅浪费算力，还可能导致 `PSMAXN too small` 等赝势相关错误。
- **ISMEAR 与 SIGMA**：
  - **金属**：`ISMEAR = 1` 或 `2`，`SIGMA` 取 0.1~0.2。
  - **半导体弛豫**：默认 `ISMEAR = 0`，`SIGMA = 0.05`；但也可以先用 `ISMEAR = -5` 测试。
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
