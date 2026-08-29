---
key: t12385
title: ����VASP��SSAdNDP����ͼ򵥲���
url: http://bbs.keinsci.com/thread-12385-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2019
cards: 11
---

# ����VASP��SSAdNDP����ͼ򵥲��� — 知识卡片

## 1. AdNDP 简介

AdNDP (Adaptive Natural Density Partitioning) 由 Boldyrev 等人于 2008 年提出，该方法基于 NBO 思想，能够分析多中心键（如 3c-2e、4c-2e、5c-2e、6c-2e 等多原子键）的成键模型。AdNDP 方法可以将分子或周期性体系中的电子结构自动分解为定域键和孤对电子的形式。相关方法论文发表在 Phys. Chem. Chem. Phys., 2008, 10, 5207–5217。

---

## 2. AdNDP 分析原理

AdNDP 的计算流程首先需要进行原子轨道基组线性组合得到自然原子轨道（NAO），这一步与 NBO 的初始化过程完全一致。随后，体系被依次搜索并定义为以下类型：孤对电子需要占据的轨道数值（如 ~2.00 e），2c-2e 键需要占据的轨道数值，3c-2e 键需要占据的轨道数值，以此类推直至 4c-2e、5c-2e、6c-2e 等。每一步搜索完成后，已找到轨道的成分会从 P(NAO) 中剔除，以避免影响后续轨道的搜索。

---

## 3. AdNDP 与 ssAdNDP 的区别

在分子体系中进行 AdNDP 分析常使用 Multiwfn 或 Boldyrev 开发的程序，其中 Multiwfn 的功能较为完善。在周期性体系中进行 AdNDP 分析需要使用 ssAdNDP 程序，该程序由 Alexander I. Boldyrev、J. R. Schmidt 以及 periodic NBO 的开发者共同编写。ssAdNDP 程序是处理周期性体系电子结构分析的有效工具。

---

## 4. ssAdNDP 程序编译准备

ssAdNDP 的编译方法参考 periodic NBO 的编码方式，需要使用 Intel 2013 编译器环境。编译过程涉及两个主要步骤：第一步是编译 periodic NBO 的 projection.exe，需要修改 makefile 中的 MKLROOT 路径（如 MKLROOT=/opt/intel/composer_xe_2013_sp1.2.144/mkl/）；第二步是编译 ssAdNDP 核心程序。

---

## 5. ssAdNDP 编译命令

编译 ssadndp.exe 需要使用 mkmf 工具和 Makefile。具体操作步骤为：修改 Makefile.template 中的 intel mkl 路径；赋予 mkmf 执行权限（chmod +x mkmf）；生成 Makefile（./mkmf -t Makefile.template -p ssadndp.exe）；执行编译（make）。此外，可视化工具 visual.exe 可通过命令 ifort visual.f90 -o visual.exe 编译生成。

---

## 6. ssAdNDP 分析策略

ssAdNDP 的分析策略通常从分子体系文件开始，或者直接从周期体系的文件开始。在分析过程中，AdNDP 的搜索顺序至关重要，通常建议优先搜索孤对电子或化学键；如果先搜索了化学键，后续再寻找孤对电子可能会导致占据数偏低。AdNDP 结果不具有唯一性，只要结果能够合理解释体系的化学性质，即视为分析成功。

---

## 7. MgB2 体系分析流程 (1-3步)

针对 MgB2 体系的分析包括五个步骤：第一步从 materials project 网站下载 MgB2 结构（如 mp-763）；第二步使用 VASP 优化结构；第三步进行 MgB2 计算，得到 projection 所需的 wavefunction.dat 文件。计算完成后需要删除 CONTCAR 文件中的注释部分，以获得 VASP4 格式的波函数文件，这与 periodic NBO 的要求完全一致。

---

## 8. MgB2 体系分析流程 (4-6步)

第四步是从 EMSL 下载并准备 basis.inp 基组文件（如 Mg 和 B 使用 6-31g* 基组）；第五步运行投影命令 ./projection.exe basis.inp wavefunction.dat NBO.out，生成 NBO.out、NBO_mat.out、band_spillover.out 和 spillover.out 文件。注意必须使用 ssAdNDP 自带的 projection.exe，periodic NBO 自带的版本可能无法成功运行。

---

## 9. MgB2 体系分析流程 (7-8步)

第六步是准备 SSAdNDP.inp 输入文件并运行 ./ssadndp.exe SSAdNDP.inp；第七步根据上一步输出的提示文件（如 SSAdNDP.chk），不断修改输入文件并重新运行 ./ssadndp.exe SSAdNDP-UD.inp SSAdNDP.chk 进行手动选择。该过程直到剩余的占据数（<<2）非常小或找到合理的化学键模型为止。

---

## 10. MgB2 分析结果示例

在 MgB2 体系分析中，先找到了一个 2c-2e 键（NO=1.72）和一个 6c-2e 键（NO=1.48），但剩余占据数为 1.21，这表明模型尚不完善。经过后续分析，在原层中找到了 8c-2e 键，成功解释了体系中 8 个价电子的分布（2 个 B 原子和 1 个 Mg 原子，价电子数分别为 3 和 2）。

---

## 11. ssAdNDP 可视化命令

ssAdNDP 生成的轨道分布可以使用 VESTA 进行可视化。可视化命令格式为 ./visual.exe vis_gs_2c-bonds.out 50 50 50。执行后会生成 gs_2c-bond_1.cube 和 lattice_vec.cube 文件，将这些文件载入 VESTA 即可查看电子结构分布图。
