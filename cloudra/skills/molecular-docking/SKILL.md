---
name: molecular-docking
description: Provide domain expertise for Molecular Docking workflows (e.g., AutoDock Vina, GNINA). Use when setting up docking protocols, preparing proteins/ligands, identifying binding sites, defining grid boxes, performing post-docking analysis (MM-GBSA), and experimental validation.
---

# 1. 本地工具链映射 (Toolchain Mapping)
在执行分子对接时，将理论流程映射到当前执行环境：
- **分子前处理**：使用 `CLOUDRA` 内部的 `Chemtool` 或调用 Python 环境（如 RDKit, OpenBabel）。对接前应确认可滴定基团的质子化状态，避免直接剥离 PDB 就开跑。
- **口袋预测与定义**：如果缺少共晶配体，优先调用 `fpocket` 等口袋预测工具，而不是手动盲设 XYZ。
- **任务分发**：调用 `submit_compute_job` 提交后台对接任务；高通量或海量构象打分通过 `is_async=True` 并行管理。
- **后处理验证**：编写或调用脚本计算 Top 1 Pose 与真实晶体构象的 RMSD，作为量化考核指标。

# 2. 限制与例外 (Constraints & Exceptions)
以下规则是常用最佳实践，但应根据研究目的灵活调整。

1. **盲对接**：高精度筛选推荐将 Grid Box 聚焦于共晶配体或预测口袋；把整个蛋白作为搜索框的“全蛋白盲对接”可用于探索性研究（如未知靶点、天然产物靶标垂钓），但结果需谨慎解读，并应结合口袋预测、生物学实验或分子动力学进一步验证。[CobDock blind docking](https://pmc.ncbi.nlm.nih.gov/articles/PMC10785400/) [Refining docking protocols](https://www.benchchem.com/pdf/Technical_Support_Center_Refining_Molecular_Docking_Protocols_for_Natural_Products.pdf)
2. **共价对接**：标准 Vina 不处理共价键。若研究共价抑制剂（如靶向 Cys），建议改用 AutoDock4、CovDock、GOLD 等支持共价对接的方法；Vina 可用于非共价预筛选，但不能作为共价结合模式的最终依据。
3. **金属配位**：Vina 的打分函数对 Zn²⁺、Fe³⁺ 等金属配位描述较弱，建议优先使用 AutoDock4Zn、GOLD、Glide 等专门方法。在数据有限且仅做快速排序时，Vina 结果仅作参考。
4. **水分子处理**：常规情况下删除结晶水以减少假阳性；若文献或预计算明确指出口袋存在关键的介导结构水（Bridging Water），则予以保留。

# 3. 科学知识库：配体与受体预处理 (Scientific Knowledge Base)
在投递对接任务前，以本节要求为前置确认标准。

## 3.1 蛋白质受体的极限准备
- **分辨率要求**：晶体结构分辨率优先 < 2.5 Å。
- **质子化状态 (Protonation States)**：生理 pH (~7.4) 下可滴定氨基酸的 pKa 必须预先预测。重点排查口袋附近的组氨酸（His），确认它是 HID, HIE 还是 HIP。
- **残基修复**：缺失的重原子应修复，否则力场计算会出现空位错误。

## 3.2 配体的参数化
- **3D 构象优化**：如果初始输入只有 SMILES，优先调用 `smiles_to_mol` 工具并设置 `generate_3d=True`。
- **生理状态电离**：确认分子在 pH=7.4 的状态（如 -COOH 会变为 -COO⁻）。
- **电荷要求**：普通 Vina 默认电荷即可；若后续转入 MM-GBSA，建议生成高精度的 **AM1-BCC 电荷**。

# 4. Agent 工作流：分子对接标准流水线 (Workflow State Machine)

**Step 1: 结合位点探测与盒子设定**
- *有共晶配体*：提取共晶配体的几何质心（Centroid）作为 Grid Box 中心。尺寸延伸设定为各加 5~10 Å（通常不超过 30×30×30 Å）。
- *无共晶配体*：调用预测工具（如 fpocket）打分最高的口袋为中心，最好结合生物学突变实验数据进行交叉验证。

**Step 2: 对接参数规划与执行**
- `exhaustiveness`（穷举度）：
  - HTVS（高通量）：设为 8。
  - 精细对接/大柔性分子：设为 32 ~ 64。更高不仅耗时增加，收益通常递减。
- 启动 `submit_compute_job` 异步执行。

**Step 3: 重对接验证金标准 (Re-docking Validation)**
- 在打分新配体前，建议先将原共晶配体重对接回去。
- 若 Top 1 Pose 的 **RMSD > 2.0 Å**，说明当前盒子或采样设置可能不合适，应返回 Step 1 调整盒子大小、提高 exhaustiveness、考虑柔性残基或更换对接程序，而不是直接认定全部结果无意义。

**Step 4: 后处理重打分 (Rescoring)**
- 提取 Top 构象作为起点，不应单纯信任 Vina 分数。
- 推荐工作流：导入 Amber/GROMACS 跑极短 MD 或通过 MM-GBSA 计算结合自由能，以引入溶剂化去极化效应（Desolvation Penalty）。

# 5. 异常诊断与排障断路器 (Circuit Breakers)
1. **结果分数全部极差 (>0 kcal/mol)**：
   - 检查配体与蛋白的加氢步骤是否发生严重空间碰撞。
   - 检查 Grid Box 是否偏离了口袋中心，导致配体被挤出。
2. **大分子的假阳性**：
   - Vina 分数具备尺寸叠加效应。若配体分子量过大，建议除以重原子数，使用“配体效率 (Ligand Efficiency, LE)”重新评估。
3. **关键相互作用缺失**：
   - 通过脚本或交互式反馈验证：若打分最高的姿态未能形成目标口袋已知的核心氢键，应质疑该对接姿态，但不必直接否决，可结合 MD 或重打分修正。

# 6. 最小可运行 Vina Python 示例
以下代码仅展示标准调用流程，参数需按实际体系调整。为避免解析问题，示例中不写注释。

```python
from vina import Vina

v = Vina(sf_name='vina')
v.set_receptor('receptor.pdbqt')
v.set_ligand_from_file('ligand.pdbqt')
v.compute_vina_maps(center=[10.0, 20.0, 30.0], box_size=[20, 20, 20])
energy = v.score()
v.dock(exhaustiveness=32, n_poses=9)
v.write_poses('output_poses.pdbqt', n_poses=5, overwrite=True)
```
