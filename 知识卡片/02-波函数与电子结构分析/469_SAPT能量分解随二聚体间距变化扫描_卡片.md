---
id: 469
title: 考察SAPT能量分解的能量项随分子二聚体间距变化的简单方法
url: http://sobereva.com/469
domain: 波函数与电子结构分析
topic: SAPT能量分解随二聚体间距变化扫描
cards: 20
---

# SAPT能量分解随二聚体间距变化扫描 — 知识卡片

## 1. 推荐使用sobEDA方法进行能量项扫描

如今推荐使用sobEDA方法做能量项随二聚体间距离变化的扫描，sobEDA比SAPT普适得多，速度快得多且内存消耗少得多。具体做法在《使用sobEDA和sobEDAw方法做非常准确、快速、方便、普适的能量分解分析》中提到的sobEDA原文附带的教程里给出了，提供的脚本做扫描极为方便。

---

## 2. dimerscan程序实现SAPT能量项随距离扫描

dimerscan程序结合Gaussian可以非常容易地实现二聚体间距的刚性扫描，具体详见《详谈使用Gaussian做势能面扫描》。对于单一结构做SAPT分析，详见《使用PSI4做对称匹配微扰理论(SAPT)能量分解计算》。

---

## 3. SAPT能量分解分析简介

对称匹配微扰理论(SAPT)是评估分子间相互作用能的严格且有用的方法，更重要的是SAPT相互作用能可以分解为各种物理项，这对于理解相互作用本质非常有用。PSI4因其免费、快速且相对易用，被认为是进行SAPT计算的最佳代码。

---

## 4. 复杂二聚体SAPT扫描的通用方法

大多数实际情况下（例如扫描水二聚体中的O...H距离），仅通过单个PSI4输入文件难以容易地实现扫描SAPT相互作用项随分子二聚体距离变化的目的。本文介绍了一种简单且通用的方法来获得随分子间距离变化的所有SAPT项，该方法包含三个步骤：生成SAPT输入文件、在批处理模式下运行PSI4、提取数据并绘制成曲线图。

---

## 5. 扫描参数的定义与实例

本文所说的“距离”是指两个单体间一对原子的间距，在变化过程中单体的取向和结构保持固定。以水二聚体为例，将H2-O4距离从1.5埃变到3.5埃，步长为0.2埃，因此共有10步。

---

## 6. 相关研究文献引用

本文介绍的扫描方法已在关于氢键的系统性研究中被采用，强烈建议阅读：Exploring Nature and Predicting Strength of Hydrogen Bonds: A Correlation Analysis Between Atoms-in-Molecules Descriptors, Binding Energies, and Energy Components of Symmetry-Adapted Perturbation Theory, J. Comput. Chem., 40, 2868–2881 (2019) DOI: 10.1002/jcc.26068。

---

## 7. dimerscan程序的获取与引用

dimerscan代码用于生成各种分子间距离下的PSI4 SAPT输入文件，可从此页面下载：http://sobereva.com/soft/dimerscan。如果在工作中使用了dimerscan，请引用如下格式：Tian Lu, dimerscan program, http://sobereva.com/soft/dimerscan (accessed month day, year)。

---

## 8. dimerscan程序包内容说明

dimerscan程序包中，“dimerscan.exe”是Windows下的可执行文件，“dimerscan”是Linux下的可执行文件，“SAPT_template.inp”是PSI4 SAPT任务的模板输入文件。用户可以在该文件中手动更改内存规格、基组和SAPT任务的关键字，除非有特殊原因，其他部分应保持不变。

---

## 9. SAPT计算级别的推荐设置

在模板文件中，SAPT级别为SAPT2+(3)dmp2/aug-cc-pVTZ。根据J. Chem. Phys., 140, 094106 (2014)中的基准测试，该级别能够以极高的精度（通常接近CCSD(T)/aug-cc-pVTZ）预测结合能，因此强烈推荐用于小分子二聚体。

---

## 10. 单体结构优化的输入文件格式

需要先在合理水平（例如B3LYP-D3(BJ)/def2-TZVP）下优化水二聚体结构，然后创建一个纯文本文件。第一行是单体1和单体2的原子数，第二行是单体1和单体2的净电荷和自旋多重度，从第3行开始是二聚体坐标（单位为埃）。

---

## 11. dimerscan程序的运行参数设置

将SAPT_template.inp文件放入dimerscan可执行文件所在的文件夹中，启动dimerscan，输入H2Odimer.txt的路径，然后依次输入：原子对索引（如2,4表示单体1的H2和单体2的O4）、初始距离（如1.5）、步数（如10）和步长（如0.2）。

---

## 12. dimerscan生成文件的内容与用途

运行dimerscan后，当前文件夹下会生成总共11个.inp文件，其中0000.inp是初始距离下的PSI4 SAPT输入文件，0001.inp到0010.inp对应扫描步骤1到10的结构。当前文件夹还会生成一个名为scan.xyz的轨迹文件，包含所有11个几何结构，可加载到VMD可视化程序中检查几何变化是否符合预期。

---

## 13. PSI4输入文件示例中的变量定义

生成的PSI4输入文件（如0002.inp）中，任务使用高达2000MB的内存，当前的H2-O4距离由“dimerdist”变量表示。在完成SAPT2+(3)dmp2能量评估后，各项能量被赋值给用户定义的变量，并按特定格式一起打印到输出文件中。

---

## 14. PSI4输出文件中的能量项单位转换

在PSI4输入文件中，通过命令`E_disp = get_variable('SAPT DISP ENERGY') * psi_hartree2kcalmol`等语句，将SAPT总能量、静电项、交换项、色散项和诱导项从哈特里单位转换为kcal/mol，并打印出包含距离和各项能量的汇总结果。

---

## 15. 批量运行PSI4输入文件的脚本操作

将生成的所有.inp文件放入用于运行PSI4计算的文件夹中，并将psi4all.sh脚本放入该文件夹。用文本编辑器打开该文件，将-n参数后的值更改为实际要使用的CPU核心数，然后进入该文件夹并运行命令：./psi4all.sh。

---

## 16. psi4all.sh脚本的功能说明

psi4all.sh脚本将调用“psi4”命令依次执行当前文件夹中的所有.inp文件，并生成具有相同名称但包含.out后缀的输出文件。

---

## 17. 从输出文件中提取数据的命令

所有SAPT计算完成后，运行命令`grep "R= " *.out > result.txt`即可将输出文件中的数据提取到result.txt文件中。

---

## 18. result.txt文件的数据列含义

result.txt文件中的数值依次对应：距离、总结合能、静电项、交换项、色散项和诱导项。例如，第一行数据表示H2-O4距离为1.500埃时，总结合能为0.536 kcal/mol，静电项为-20.989 kcal/mol等。

---

## 19. 数据绘图与物理意义分析

将result.txt拖入Origin程序导入数据并绘制各项SAPT项随距离变化的Line+Symbol图。从图中可以看出，水二聚体的最小值点出现在R(H2-O4)=1.9埃附近；静电、色散和诱导项起吸引作用，排斥效应纯粹来自交换项；所有项随H2-O4间距增加平滑收敛于零。

---

## 20. 水二聚体氢键的主导作用

数据清晰表明，无论二聚体间距如何，水二聚体中的氢键完全由静电相互作用主导。
