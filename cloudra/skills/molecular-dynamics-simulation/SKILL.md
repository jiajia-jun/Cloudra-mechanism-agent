---
name: molecular-dynamics-simulation
description: Provide domain expertise for classical molecular dynamics (MD) simulations using GROMACS, AMBER, etc. Use when selecting force fields, configuring MDP parameters, determining equilibration/production protocols, setting up enhanced sampling or free energy calculations, and diagnosing trajectory issues.
license: MIT
metadata: {"original-skill": "molecular-dynamics", "source": "https://github.com/K-Dense-AI/scientific-agent-skills", "adapted-by": "Cloudra"}
---

# 1. 本地工具链映射 (Toolchain Mapping)
在执行分子动力学（MD）模拟时，你必须将底层理论映射为可执行的代码链路：
- **拓扑与配置生成**：优先利用 Python 脚本生成复杂的 MDP 文件。针对特定的力场（如 CHARMM36m）或系统配置，严禁使用盲目的全局正则替换，必须使用专门的配置解析库处理键值对。
- **OpenMM 工具链**：若使用 OpenMM，可用 `pdbfixer` 修复 PDB、`Modeller.addHydrogens` 加氢、`Modeller.addSolvent` 加溶剂盒、`ForceField.createSystem` 创建体系。OpenMM 支持 CUDA / OpenCL / CPU 自动回退，并可用 `StateDataReporter`、`DCDReporter`、`CheckpointReporter` 输出日志、轨迹和检查点。
- **任务分发**：所有 MD 步骤（EM, NVT, NPT, Production）极度消耗算力，必须调用 `submit_compute_job` 设置 `is_async=True` 提交至后台执行。
- **轨迹监控与状态判断**：禁止直接读取原始的大型二进制 `.trr` / `.xtc` 文件。应当使用本地包裹脚本提取热力学参量（如 `gmx energy` 的提取物），或使用 `MDAnalysis` 程序化分析 RMSD、RMSF、接触矩阵等，进行密度、温度、能量收敛性的程序化自动判断。

# 2. 限制与例外 (Constraints & Exceptions)
以下规则是 MD 模拟的常用最佳实践，但存在合理例外。遇到矛盾时，优先以**当前力场版本的官方说明和体系特性**为准。

1. **力场绑定红线**：水模型、离子参数应与所选生物力场配套使用。混用参数可能引入系统误差，但并非所有混用都会"彻底摧毁体系"。
   - AMBER (如 ff19SB) 常见搭配：OPC、TIP3P-FB 或 TIP4P-Ew。
   - CHARMM (如 CHARMM36m) 常见搭配：CHARMM-modified TIP3P (mTIP3P)。
   - 若必须混用（如小分子 GAFF 配体 + CHARMM 蛋白），需通过文献或基准测试验证，并谨慎解释结果。
2. **控温控压红线**：
   - **生产相（Production）**：推荐使用能给出正确系综分布的控压器，如 `Parrinello-Rahman`、`C-rescale` 或 `MTTK`；恒温器推荐 `Nosé-Hoover` 或 `v-rescale`。
   - **预平衡阶段**：`Berendsen` 恒温/恒压浴因收敛快、稳定性高，仍常用于初始弛豫，但应意识到它**不严格对应任何系综**。GROMACS 官方已明确建议新生产模拟不要用 Berendsen。
   - 若体系对压力耦合敏感（如膜/界面、含位置限制的体系），可先用 `Berendsen` 或 `C-rescale` 稳定，再切换到 `Parrinello-Rahman`。
3. **离子模型选择**：
   - 对于高电荷密度且存在紧密配位的过渡金属离子（如 Zn²⁺、Mg²⁺、Mn²⁺ 在酶活性位点），标准 12-6 Lennard-Jones 模型可能同时高估/低估水合自由能与配位距离，此时应考虑 **12-6-4 模型**或 **Bonded Model**。
   - 对于稀溶液中的简单一价离子或弱配位环境，12-6 模型通常足够。

# 3. 科学知识库：力场与参数深水区 (Scientific Knowledge Base)

## 3.1 截断与长程相互作用设定
- **PME (Particle Mesh Ewald)**：静电计算的标准方法，几乎总是推荐。
- **截断距离**：
  - AMBER 系列：常用 `0.8` ~ `1.0` nm，具体以力场版本说明为准。
  - CHARMM36/CHARMM36m 系列：传统上常用 `1.2` nm，并配合 force-switch（`vdw-modifier = Force-switch`, `rvdw-switch = 1.0`）。但 CHARMM36m 的更新文献也有使用 `1.0` nm 或调整 switch 起点的做法，因此最好按官方/基准论文设置。
- **色散校正 (dispcorr)**：
  - 均相溶剂体系可开启 `EnerPres`。
  - 脂膜、界面或非均相体系通常**关闭**，因为色散校正可能改变界面张力。

## 3.3 OpenMM 与 Python 分析工具链

*本节部分代码示例与最佳实践改编自 K-Dense-AI/scientific-agent-skills（MIT License）。原始 skill 面向 OpenMM + MDAnalysis；这里结合 Cloudra 的 GROMACS/AMBER/CHARMM 工作流进行了改写和补充。*

### 力场与体系快速选型

| System | Recommended Force Field | Water Model |
|--------|------------------------|-------------|
| Standard proteins | AMBER14 (`amber14-all.xml`) | TIP3P-FB |
| Proteins + small molecules | AMBER14 + GAFF2 / OpenFF | TIP3P-FB |
| Membrane proteins | CHARMM36m | mTIP3P / TIP3P |
| Nucleic acids | AMBER99-bsc1 or AMBER14 | TIP3P |
| Disordered proteins | ff19SB or CHARMM36m | OPC / TIP4P-Ew |

*注：CHARMM 蛋白体系应优先使用 CHARMM36m + mTIP3P；AMBER 蛋白体系可搭配 OPC、TIP3P-FB 或 TIP4P-Ew。小分子配体常用 GAFF2 或 OpenFF，参数化后务必检查电荷与可旋转键。*

### OpenMM 最小可运行 EM → NVT → NPT 示例

以下示例展示 OpenMM 的完整平衡流程，参数需按实际体系调整。

```python
from openmm.app import *
from openmm import *
from openmm.unit import *

# 1. 准备体系
pdb = PDBFile('cleaned.pdb')
forcefield = ForceField('amber14-all.xml', 'amber14/tip3pfb.xml')
modeller = Modeller(pdb.topology, pdb.positions)
modeller.addHydrogens(forcefield)
modeller.addSolvent(forcefield, model='tip3p', padding=10*angstroms,
                    ionicStrength=0.15*molar)

system = forcefield.createSystem(
    modeller.topology,
    nonbondedMethod=PME,
    nonbondedCutoff=1.0*nanometer,
    constraints=HBonds,
    rigidWater=True,
    ewaldErrorTolerance=0.0005
)

# 2. 平台选择：CUDA -> OpenCL -> CPU
for platform_name, props in [('CUDA', {'DeviceIndex': '0', 'Precision': 'mixed'}),
                             ('OpenCL', {}),
                             ('CPU', {})]:
    try:
        platform = Platform.getPlatformByName(platform_name)
        properties = props
        break
    except Exception:
        continue

# 3. 能量极小化
integrator = LangevinMiddleIntegrator(300*kelvin, 1/picosecond, 0.002*picoseconds)
simulation = Simulation(modeller.topology, system, integrator, platform, properties)
simulation.context.setPositions(modeller.positions)
simulation.minimizeEnergy(maxIterations=1000)

# 4. NVT 平衡（100 ps）
simulation.context.setVelocitiesToTemperature(300*kelvin)
simulation.reporters = [
    StateDataReporter('nvt_log.txt', 1000, step=True, temperature=True,
                      potentialEnergy=True, speed=True),
    DCDReporter('nvt_traj.dcd', 1000)
]
simulation.step(50000)

# 5. NPT 产生相（1 ns）
system.addForce(MonteCarloBarostat(1.0*bar, 300*kelvin, 25))
simulation.context.reinitialize(preserveState=True)
simulation.reporters = [
    StateDataReporter('npt_log.txt', 5000, step=True, temperature=True,
                      density=True, potentialEnergy=True, speed=True),
    DCDReporter('npt_traj.dcd', 5000),
    CheckpointReporter('npt_checkpoint.chk', 50000)
]
simulation.step(500000)
```

### MDAnalysis 轨迹分析示例

```python
import MDAnalysis as mda
from MDAnalysis.analysis import rms, align, contacts
import numpy as np

u = mda.Universe('topology.pdb', 'npt_traj.dcd')

# RMSD（对齐后）
align.AlignTraj(u, u, select='backbone', in_memory=True).run()
R = rms.RMSD(u, select='backbone', ref_frame=0)
R.run()
rmsd_data = R.results.rmsd  # columns: frame, time, RMSD

# RMSF（按残基平均）
atoms = u.select_atoms('backbone')
RMSF = rms.RMSF(atoms)
RMSF.run(start=int(0.2 * u.trajectory.n_frames))  # 丢弃前 20%

# 蛋白-配体接触分析
protein = u.select_atoms('protein')
ligand = u.select_atoms('resname LIG')
contact_residues_per_frame = []
for ts in u.trajectory[int(0.2 * u.trajectory.n_frames):]:
    dist = contacts.contact_matrix(protein.positions, ligand.positions, radius=4.5)
    contact_residues_per_frame.append({protein.atoms[i].resid
                                        for i in range(dist.shape[0])
                                        if dist[i].any()})
```

### PDB 预处理（PDBFixer）

```python
from pdbfixer import PDBFixer
from openmm.app import PDBFile

def fix_pdb(input_pdb, output_pdb, ph=7.0):
    fixer = PDBFixer(filename=input_pdb)
    fixer.findMissingResidues()
    fixer.findNonstandardResidues()
    fixer.replaceNonstandardResidues()
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(ph)
    with open(output_pdb, 'w') as f:
        PDBFile.writeFile(fixer.topology, fixer.positions, f)
    return output_pdb
```

*注意：PDBFixer 的 `removeHeterogens(True)` 会删除水和小分子配体。若需要保留配体，请显式保留对应 residue，或改用其他参数化流程。*

### 小分子参数化（OpenFF / GAFF2）

```python
from openff.toolkit import Molecule
from openff.interchange import Interchange
from openff.toolkit import ForceField as OFFForceField

mol = Molecule.from_smiles('CCO')  # 示例：乙醇
mol.generate_conformers(n_conformers=1)
off_ff = OFFForceField('openff-2.0.0.offxml')
interchange = off_ff.create_interchange(mol.to_topology())
# 后续可导出为 OpenMM System 或 GROMACS 拓扑
```

## 3.4 通用最佳实践

- **Always minimize before MD**：Raw PDB 常有空间冲突，EM 必不可少。
- **Equilibrate before production**：NVT（50–100 ps）→ NPT（100–500 ps）→ Production。
- **Use GPU when available**：OpenMM 在 CUDA/OpenCL 上通常比 CPU 快 10–100 倍。
- **2 fs timestep with HBonds constraints**：标准设置；若使用 HMR（氢质量重分配）可尝试 4 fs。
- **Analyze only equilibrated trajectory**：通常丢弃前 20–50% 作为平衡期。
- **Save checkpoints**：MD 可能中断，检查点支持重启。
- **Periodic boundary conditions**：溶剂化体系必须正确处理 PBC。
- **PME for electrostatics**：带电体系优先使用 PME，而非简单截断。

## 3.5 参考资源

- [OpenMM documentation](https://openmm.org/documentation.html)
- [MDAnalysis user guide](https://docs.mdanalysis.org/)
- [GROMACS manual](https://manual.gromacs.org/)
- [NAMD](https://www.ks.uiuc.edu/Research/namd/)
- [CHARMM-GUI](https://charmm-gui.org/)
- [AmberTools](https://ambermd.org/AmberTools.php)
- Eastman P et al. (2017) PLOS Computational Biology. PMID: 28278240
- Michaud-Agrawal N et al. (2011) J Computational Chemistry. PMID: 21500218
- 原始 OpenMM/MDAnalysis skill: [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) (MIT License)

# 5. 异常诊断与排障断路器 (Circuit Breakers)
如果系统在运行前几纳秒内崩溃，必须通过日志排查以下经典死局：

1. **飞冰块效应 (Flying Ice Cube)**：
   - 现象：体系似乎冻结，但温度显示暴涨。
   - 修复：加上去质心平移：`comm-mode = Linear`，`nstcomm = 100`。
2. **真空泡与炸盒子 (Box Explosion)**：
   - 现象：NPT 刚跑几步就报 LINCS 断裂，原子猛烈碰撞。
   - 修复：通常是溶剂余量太小。回到溶剂化步骤增加盒子大小，或在 NVT/NPT 前期使用 0.5 fs 步长。
3. **配体疯狂逃逸出口袋**：
   - 现象：短时间内配体解离脱离蛋白。
   - 修复：核查 Antechamber 的配体电荷拟合，极大概率是配体电荷全错导致了静电排斥。
