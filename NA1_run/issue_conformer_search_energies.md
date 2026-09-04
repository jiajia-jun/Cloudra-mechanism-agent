## Bug: `conformer_search` 对带电多碎片输入输出全零相对能量与原子重叠几何

### Summary
`conformer_search` (Chemtool) 对一个带 -1 电荷的多碎片输入（`[O-]C=C.O.CC=O`）报告 `is_success=True`，但产出的构象几何**原子重叠**（碎片叠放在一起），且**所有构象的 MMFF 相对能量全部为 0.000**、Boltzmann 布居全部 25%。distance_filters 因此永远不通过（reactive_rescued=0），下游拿到的"反应性构象候选"是垃圾几何。

### Repro
```
conformer_search(smiles="[O-]C=C.O.CC=O", charge=-1, num_confs=40,
                 distance_filters=[{"atoms":[2,6],"min_ang":2.8,"max_ang":3.9}],
                 output_dir="confs_reactant")
```
输出：
```
conf_id  rel E (kcal/mol)  Boltzmann %  RMSD to conf0 (Å)  pass_filters
      0           0.000        25.0              0.000         False
      1           0.000        25.0              1.625         False
      2           0.000        25.0              0.969         False
      3           0.000        25.0              1.303         False
counts: generated=40 optimized=40 within_window=40 clusters=4 retained=4 passing_filters=0 reactive_rescued=0
```
从落盘的 `confs_reactant.xyz`（4 帧，原子顺序 O C C O C C O H...）实际量距：
- r(C2–C6) ≈ **0.255 / 1.488 / 0.407 / 1.403 Å**（0.25–0.4 Å 是原子叠放）
- r(C2–water O4) ≈ 0.715–0.868 Å（真实 C–O 键约 1.4 Å）

这些结构无法用于 TS 猜构象，也会让下游 QM 直接发散或给无意义结果。

### 根因
`cloudra/tools/Chemtool/conformer_search.py` `_run_rdkit`：
1. `AllChem.EmbedMultipleConfs(ETKDGv3)` 对**多碎片**输入（enolate + water + aldehyde 三个互不相连碎片）只做逐碎片嵌入并随机摆放，碎片经常**互相叠放**，得到重叠几何。
2. 能量取 `AllChem.MMFFOptimizeMoleculeConfs(mol)` 返回的第二个值 `e`（元组 `(success, E)`），**不检查 `success`**；MMFF 参数缺失/优化失败时 `E` 为 0.0，于是 `e_min=0`，所有 `rel_energy_kcal = E - e_min = 0`，相对能量表与 Boltzmann 布居全部退化。
3. 工具在产出垃圾几何+全零能量的情况下仍返回 `is_success=True`，没有失败即报错。

### 影响
- 无法用 conformer_search 为离子/多碎片反应体系找反应性构象（如 NA1 乙醛自醇醛加成的离子-偶极络合物）。
- 全零能量让"最低能量构象"不可信，距离过滤恒不通过，`_select_cluster_representatives` 的"reactive_rescued"路径也失效。
- 与 MEMORY 中"MLIP barrier 用 conformer_search 定位反应物络合物"的工作流冲突。

### 建议修复
- `MMFFOptimizeMoleculeConfs` / `UFFOptimizeMoleculeConfs` 返回后检查每个 `(success, E)` 的 success 标志；任一优化失败时应报错或回退，不要把 0.0 当能量。
- 多碎片/带电体系 ETKDG 嵌入后做**碎片间去重叠**（如把碎片按最小间距互斥分隔，或用 mmff/uff 充分优化后校验不存在 <1.0 Å 的原子对），几何非物理时失败即报错。
- 或对碎片数 >1 的输入直接改用 `backend='crest'`（GFN2-xTB 可处理弱相互作用络合物）。

### 环境
- cloudra 当前工作树（2026-09-04），`conformer_search.py`（RDKit 后端，MMFF）。
- 复现文件：`NA1_run/confs_reactant/confs.xyz`
