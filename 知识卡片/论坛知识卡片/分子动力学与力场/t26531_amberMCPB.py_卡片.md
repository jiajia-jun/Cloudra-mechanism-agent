---
key: t26531
title: ����amber��MCPB.py�������������ӵ��׵���������
url: http://bbs.keinsci.com/thread-26531-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2021
cards: 16
---

# ����amber��MCPB.py�������������ӵ��׵��������� — 知识卡片

## 1. 金属中心参数化工具 MCPB.py 简介

AmberTools 中的 Metal Center Parameter Builder (MCPB) 是一种半自动化参数化流程，用于加速含金属中心体系的力场参数生成过程。MCPB.py 是 MCPB 的 Python 版本，集成了优化后的键合模型计算和实现 RESP 拟合电荷参数执行的接口。该工具自 AmberTools 15 起可用，支持常见 80 种金属中心和 AMBER 力场类型，适用于基于 Gaussian 或 GAMESS-US 的量子化学计算。

---

## 2. 准备配体 mol2 文件与氢原子

使用 reduce 工具为提取出的配体 PDB 文件（如 HBI.pdb）加氢，并输出处理后的文件（如 HBI_H.pdb）。随后检查 3D 结构，删除因加氢产生的多余或不需要的氢原子。使用 antechamber 将加氢后的 PDB 转换为 mol2 格式，并指定净电荷和电荷模型。

---

## 3. Antechamber 与 GAFF 力场参数生成

使用 antechamber 生成配体的 mol2 文件时，通常采用 AM1-BCC 电荷模型和 GAFF 原子类型。使用 `-nc` 参数指定正确的净电荷对于生成准确的电荷至关重要。随后使用 parmchk2 根据生成的 mol2 文件生成 frcmod 参数补全文件。

---

## 4. 金属离子 mol2 文件准备

从 PDB 文件中提取金属离子（如 FE）的信息生成单独的 PDB 文件。使用提供的 `metalpdb2mol2.py` 脚本将该 PDB 文件转换为 mol2 文件，并通过 `-c` 参数指定金属离子的电荷数。

---

## 5. 晶格水 mol2 文件准备

为避免晶格水丢失，需将晶格水复制到单独的 PDB 文件中，并使用 tleap 加载 TP3 水模型后保存加氢的 PDB 文件。使用 antechamber 将处理后的晶格水 PDB 转换为 mol2 文件，注意将 atomtype 修改为 AMBER 格式的 HW 和 OW。

---

## 6. 蛋白质 PDB 文件加氢与残基命名

使用 H++ Web Server 或 AMBER 工具（如 ambpdb）为蛋白质 PDB 文件添加氢原子，确保组氨酸等残基的质子化状态正确（如 HID, HIE, HIP）。需根据具体情况手动修改质子化状态（例如将 HIP 改为 HID 并删除多余的 HE2 原子），以匹配配位环境。

---

## 7. MCPB.py 输入文件配置

MCPB.py 的输入文件（如 1mlw.in）需指定原始 PDB 文件名、体系名称、截断距离、金属离子 ID、离子与配体的 mol2 文件路径以及 frcmod 文件。通过 `software_version` 参数可选择 Gaussian09 (g09)、Gaussian16 (g16) 或 GAMESS-US (gms) 作为 QM 计算后端。

---

## 8. MCPB.py 步骤 1：模型构建与预处理

运行 `MCPB.py -i 1mlw.in -s 1` 将生成小模型、标准模型和大模型的 PDB 及 fingerprint 文件。此步骤还会产生用于后续高斯计算的输入文件，并可根据 `large_opt` 设置（1 或 0）决定是否优化大模型或仅优化键合原子。

---

## 9. Fingerprint 文件与原子类型定义

指纹文件（如 1mlw_standard.fingerprint）包含标准模型中原子的原子类型信息，支持以 M、Y、Z 开头的自定义金属或配位原子类型。用户可根据 QM 计算结果手动修改该文件，调整金属周围原子的键合类型或添加 LINK 信息以修正配位键。

---

## 10. Gaussian 计算执行

执行 MCPB.py 生成的 Gaussian 脚本，包括小模型的几何优化（`small_opt`）和频率计算（`small_fc`），以及大模型的单点计算（`large_mk`）用于生成 RESP 电荷。为了确保找到势能面最小值，可对优化后的结构进行多次多步优化，或在 `1mlw.in` 中调整 `large_opt` 选项。

---

## 11. MCPB.py 步骤 2 与 3：键合模型与电荷拟合

运行 `MCPB.py -i 1mlw.in -s 2` 生成键合模型参数文件（如 1mlw_mcpbpy.frcmod）。运行 `MCPB.py -i 1mlw.in -s 3` 使用 ChgModB 执行 RESP 电荷拟合，并输出包含电荷信息的 mol2 文件。

---

## 12. MCPB.py 步骤 4：生成 TLEAP 输入文件

运行 `MCPB.py -i 1mlw.in -s 4` 生成新的 PDB 文件和 tleap 输入脚本（如 1mlw_tleap.in）。生成的脚本包含加载力场、定义原子类型（如 M1, Y1）、加载 mol2 文件和 frcmod 参数以及建立配位键（bond 命令）的指令。

---

## 13. 使用 TLEAP 构建体系与生成拓扑文件

在 tleap 脚本中，需手动添加自定义原子类型定义（`addAtomTypes`），加载必要的力场文件（如 ff14SB, gaff）和生成的参数文件。使用 `bond` 命令建立金属中心与配位原子之间的连接，最后通过 `solvatebox` 和 `addions` 进行溶剂化和离子平衡，输出拓扑和坐标文件。

---

## 14. 处理非标准残基库文件报错

若在 tleap 中遇到非标准残基原子类型缺失的错误（如 FATAL: Atom does not have a type），需使用 tleap 手动为该残基（如 HBI）生成 lib 库文件。通过 `loadmol2` 加载 mol2 文件并使用 `saveoff` 保存为 lib 文件，然后在主 leap 脚本中加载该库。

---

## 15. 模型体系验证标准

使用 VMD 和 cpptraj 检查结构和原子索引，配合 parmed 打印金属中心的键、角、二面角参数。合理的参数标准通常包括：键力常数大于 200 kcal/(mol*Angstrom^2)，平均键长小于 2.8 Å；角力常数大于 100 kcal/(mol*Rad^2)；涉及金属的二面面势垒常数为 0；RESP 电荷动态范围通常在 +1 以内；金属离子的 LJ 半径通常在 1.0 左右。

---

## 16. AMBER 到 GROMACS 文件格式转换

使用 Python 的 parmed 模块加载 AMBER 生成的 prmtop 和 inpcrd 文件。通过 `save` 方法分别输出 GROMACS 格式的拓扑文件（.top）和坐标文件（.gro），从而完成从 AMBER 力场到 GROMACS 格式的转换。
