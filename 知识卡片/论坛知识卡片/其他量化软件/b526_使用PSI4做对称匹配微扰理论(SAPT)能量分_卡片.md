---
key: b526
title: 使用PSI4做对称匹配微扰理论(SAPT)能量分解计算
url: http://sobereva.com/526
domain: 其他量化软件
source: blog
year: 2019
cards: 22
---

# 使用PSI4做对称匹配微扰理论(SAPT)能量分解计算 — 知识卡片

## 1. SAPT0与sobEDAw方法的适用性建议

sobEDAw能量分解方法在计算耗时、内存及硬盘需求方面远低于SAPT0，且精度可达到较高阶SAPT水平，建议作为SAPT的替代方案。
- 原文提到sobEDAw方法非常方便，精度明显优于SAPT0。

---

## 2. 对称匹配微扰理论(SAPT)的基本原理

SAPT是将片段间相互作用能分解为静电、交换、色散、诱导等物理成分的方法，也是一种无基组叠加误差(BSSE)的相互作用能计算方法，仅适用于弱相互作用研究。
- SAPT基于片段间微扰思想，不适用于化学键等强相互作用体系。

---

## 3. SAPT能量分解的物理成分

SAPT将相互作用能分解为静电项、交换项、色散项和诱导项，其中交换项为正值，其余各项通常为负值。
- 静电项描述经典库仑作用，交换项描述近程排斥，色散项体现吸引作用，诱导项体现电荷极化与转移。

---

## 4. SAPT计算级别与精度关系

SAPT计算精度随微扰阶数增加而提高，精度顺序为SAPT0 < SAPT2 < SAPT2+ < SAPT2+(3) < SAPT2+3。
- 高阶SAPT(如SAPT2+(3))计算量较大，适用于小体系；SAPT0适用于中等及偏大体系。

---

## 5. SAPT计算中的δ项修正

PSI4中的SAPT0包含δHF项以体现高阶诱导作用，高阶SAPT可加入δMP2项考虑诱导与色散的高阶耦合。
- δ项数值通常较小，物理意义不明确且无法进一步划分，一般归入诱导项。

---

## 6. 推荐的SAPT计算组合

J. Chem. Phys. 140, 094106 (2014) 推荐三种主要组合：sSAPT0/jun-cc-pVDZ（铜级）、SAPT2+/aug-cc-pVDZ（银级）、SAPT2+(3)δMP2/aug-cc-pVTZ（金级）。
- 这三种组合耗时依次升高，精度也依次升高，SAPT2+(3)δMP2/aug-cc-pVTZ与CCSD(T)相对误差仅约3%。

---

## 7. sSAPT0的使用限制

sSAPT0是对SAPT0交换项的经验校正版本，仅推荐与jun-cc-pVDZ基组结合使用。
- 将sSAPT0与更大基组（如aug-cc-pVTZ）结合会导致误差抵消效果变差，结果精度下降。

---

## 8. PSI4程序在SAPT计算中的优势

PSI4是开源免费且速度快的量子化学程序，支持高阶SAPT2+3计算，输入文件相对简单。
- 相比Molpro仅支持SAPT0且收费昂贵，PSI4功能更强且更适合做SAPT计算。

---

## 9. PSI4的安装与配置

PSI4可通过官网下载installer包或使用conda安装，安装后需在环境配置文件中设置PATH和PSI_SCRATCH变量。
- 安装器会向~/.bashrc写入配置，用户可手动清理并设置正确的路径和临时文件目录。

---

## 10. 使用Multiwfn生成PSI4的SAPT输入文件

Multiwfn支持生成PSI4的SAPT任务输入文件，用户需指定计算级别及两个片段的原子序号。
- 该功能适用于Multiwfn支持的各类结构文件，如.xyz、.mol2、.pdb等。

---

## 11. PSI4的SAPT输入文件参数设置

PSI4输入文件中需设置内存大小、分子结构（以--分隔片段）、基组及计算方法，建议开启freeze_core以加速计算。
- scf_type DF默认开启密度拟合加速，无需额外指定df_basis_sapt。

---

## 12. PSI4计算SAPT的运行命令

使用命令 `psi4 输入文件 输出文件 -n 核数` 执行SAPT计算任务。
- 输出文件末尾若显示"Buy a developer a beer!"则表示运行正常，若提示买咖啡则说明任务失败。

---

## 13. SAPT结果输出解读

PSI4输出文件包含详细的能量分解项，并汇总为Electrostatics、Exchange、Induction、Dispersion四部分及总相互作用能。
- 输出结果同时提供不同级别的SAPT总能量及sSAPT0能量供参考。

---

## 14. 尿素晶体中的相互作用分析示例

使用sSAPT0/jun-cc-pVDZ计算尿素晶体中相邻尿素分子的相互作用能，结果约为-50.83 kJ/mol。
- 该结果对应两个中等强度氢键的能量，符合结构特征。

---

## 15. 凝聚相环境中的多体效应

在晶体或凝聚相环境中，计算两个分子间的相互作用能时，周围环境会产生多体耦合效应（如极化、电荷转移），导致二聚体作用能之和不等于三聚体作用能。
- 对于中性分子，此效应不致产生定性影响；若涉及离子，多体效应不可忽略。

---

## 16. 含重元素体系的SAPT基组选择

对于含第四周期之后元素的体系（如碘），若aug-cc-pVTZ未定义，应使用def2系列基组（如def2-QZVP）。
- def2系列会自动对重元素应用赝势，使用def2-QZVP可弥补缺失弥散函数带来的精度损失。

---

## 17. SAPT计算中的电荷转移(CT)贡献计算

在PSI4中将SAPT方法名后加上-ct后缀，或在Multiwfn选择相应选项，可计算显式的电荷转移对结合能的贡献。
- 启用CT计算会增加额外耗时，且此时无法使用δMP2进行修正。

---

## 18. SAPT 电荷转移分析输出结果

SAPT Charge Transfer Analysis 输出包含 SAPT Induction (Dimer Basis)、SAPT Induction (Monomer Basis) 和 SAPT Charge Transfer 三项能量数据及对应的毫哈特里、千卡/摩尔和千焦/摩尔单位数值。
- CT 部分贡献等于 Monomer basis 和 Dimer basis 下不考虑 δHF 贡献的 Induction 项的差值。
- 对于弱相互作用二聚体，电荷转移作用对结合能的贡献通常非常小。

---

## 19. SAPT 计算中的电荷转移定义

SAPT2+(3) 计算分别在 Dimer basis 和 Monomer basis 下进行。
- CT 能量对应于 Dimer basis 和 Monomer basis 下 Induction 项（不含 δHF）的差值。
- 在 Dimer basis 下的 SAP2+(3) 计算结果中，induction 作用能包含 δHF 在内，而 CT 贡献仅占其很小部分。

---

## 20. PSI4 SAPT 计算的波函数初猜设置

PSI4 默认使用 SAD 方式产生初猜波函数，若遇到难以收敛的情况，可以在 set { ... } 中写入 guess GWH 来更换初猜方式以尝试收敛。
- 使用 GWH 初猜有可能会收敛到非基态波函数，导致计算出的 SAPT 作用能明显异常。
- 为判断是否收敛至非基态，可将 HF 计算结果与 Gaussian 等程序进行对比。
- 在难收敛时也可以尝试加上 soscf true 和 soscf_max_iter 30 参数。

---

## 21. SAP2+(3)δMP2 冻核近似异常问题

使用 SAPT2+(3)δMP2 结合冻核近似时，诱导项里的 delta MP2,r (2) 项可能出现数量级异常大的情况，导致结合能明显偏离 SAPT2+(3) 的结果。
- 此种异常情况推测由 PSI4 冻核处理的 bug 引起。
- 出现该问题时应去掉 freeze_core True 设置以避免使用冻核近似（这会增加含较多周期靠后原子的体系的计算耗时）。

---

## 22. SAPT 计算中溶剂效应的处理方法

SAPT 不能直接结合隐式溶剂模型使用。
- 溶剂效应对结合能的贡献估计方法为：使用常规超分子方法分别在气相和溶剂模型下计算结合能，二者求差。
- 溶剂效应贡献作为一个独立项，不应纳入到 SAPT 的任何一个物理成分中。
