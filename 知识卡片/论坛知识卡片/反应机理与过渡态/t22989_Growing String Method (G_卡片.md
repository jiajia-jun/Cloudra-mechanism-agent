---
key: t22989
title: Growing String Method (GSM) - pyGSM ���b�������c����
url: http://bbs.keinsci.com/thread-22989-1-1.html
domain: 反应机理与过渡态
source: keinsci
year: 2021
cards: 19
---

# Growing String Method (GSM) - pyGSM ���b�������c���� — 知识卡片

## 1. 过渡态搜索与GSM方法的重要性

寻找过渡态(TS)是计算化学研究反应机理的关键步骤。传统的过渡态搜索方法往往需要先猜测结构并尝试不同构象才能得到。Growing String Method (GSM) 能够自动寻找反应路径并优化TS，减少了手动猜测结构的依赖。

---

## 2. String Method相关文献

String Method 及其变体在反应路径计算中有相关文献支持。主要参考文献包括 J. Chem. Phys. 120, 7877 (2004)、J. Chem. Theory Comput. 2013, 9, 3043–3050、J. Chem. Phys. 138, 184102 (2013) 和 Phys. Chem. Chem. Phys., 2018, 20, 27394。

---

## 3. GSM算法的基本原理

GSM算法通过设置驱动坐标，使反应物从局部最小值出发沿着能量爬坡方向寻找鞍点(TS guess)。算法通过节点增长和优化，将反应路径连接起来，最终通过Climb image得到精确的TS。

---

## 4. GSM算法的基本步骤

GSM算法执行包含七个主要步骤：设置驱动坐标、计算梯度和能量、添加节点、在节点间进行优化、优化字符串、执行爬坡图像以及从TS节点开始进行精细优化。

---

## 5. Freezing String Method (FSM)

Freezing String Method (FSM) 是GSM的一种变体，通过固定字符串进行优化来节省计算资源。FSM仅执行步骤1-4，不包含Climb image，主要适用于寻找反应路径和TS猜测结构。

---

## 6. pyGSM的安装步骤

pyGSM 的安装通过 conda 管理环境，需先创建名为 `gsm_env` 的 Python3 环境，随后克隆GitHub仓库并运行 `python setup install`。

---

## 7. pyGSM支持的计算软件

pyGSM 支持大部分主流量化计算软件，支持的列表包括 "QChem"、"Orca"、"Molpro"、"PyTC"、"TeraChemCloud"、"OpenMM"、"DFTB"、"TeraChem"、"BAGEL"、"xTB_lot"。若需使用 Gaussian，建议使用 C++ 版本的 molecularGSM。

---

## 8. Double-Ended GSM (DE-GSM) 模式

Double-Ended GSM (DE-GSM) 模式需要同时提供反应物和产物的结构作为输入。反应物和产物的几何构型通常需要经过GSM级别的理论方法(如xTB)预优化，且两者之间的原子顺序必须一致。

---

## 9. SE-GSM模式与驱动坐标

Single-Ended GSM (SE-GSM) 模式仅需反应物结构，但需要定义驱动坐标，如断键(ADD BREAK bond)、键长、键角或二面角等参数，以引导搜索向产物方向进行。

---

## 10. pyGSM的输出结果

pyGSM 运行结束后，会在输出目录生成能量剖面图(Energy profile)和名为 `TSNode.xyz` 的文件，后者包含TS初始猜测结构，可直接用于后续量化软件的TS优化。

---

## 11. GSM计算结果的可视化

计算过程中的轨迹文件位于 `scratch/opt_converged_000_000.xyz`，可使用 VMD 软件打开查看。该文件也可转换为 molden format 以便在其他可视化软件中展示。

---

## 12. TRIC坐标系类型

pyGSM 的 `coordinate_type` 默认为 TRIC (J. Chem, Phys. 144, 214108)，也可以设置为 DLC。TRIC 在处理簇体系或仅考虑分子内坐标时表现更好，且在处理接近180度的线性键角时优于DLC。

---

## 13. 节点数量参数设置

参数 `-num_nodes` 用于设置节点数量，对于 DE-GSM 通常建议设置为 9 或 11。该参数决定了路径的分辨率和计算的精细程度。

---

## 14. 线性搜索与容差参数

`-linesearch` 参数建议尝试 backtrack 模式。`-ADD_NODE_TOL` 控制节点添加的容差，推荐值为 0.001，使用较小的值可以使节点分布更加密集。

---

## 15. 步长控制参数

`-DQMAG_MAX` 参数控制步长比例，小体系建议设为 0.4，大体系建议设为 0.8，一般情况下取 0.6 可获得较好的效果。

---

## 16. 初始几何构型预处理的重要性

GSM 对初始几何构型的质量要求较高，预优化是获得成功结果的关键步骤。对于如 Diels-Alder 反应等体系，若初始结构堆积过于紧密或距离不当，可能会导致路径搜索失败。

---

## 17. Avogadro构建初始结构的步骤

使用 Avogadro 构建初始结构时，可利用其画图工具绘制分子片段。建议在构建完成后移除多余的氢原子，并使用力场优化结构，以获得合理的键长和原子位置。

---

## 18. DE-GSM的输入文件与命令

DE-GSM 运行需要包含反应物和产物的 xyz 文件，且原子顺序必须一一对应。使用 Q-Chem 或 Orca 时，需指定 level of theory 文件，例如命令：`gsm -xyzfile ./diels_alder.xyz -mode DE_GSM -package QChem -lot_inp_file qstart > status.log 2>&1`。

---

## 19. pyGSM与外部计算软件的交互

使用 Q-Chem 或 Orca 等外部软件时，可能需要添加 `!Engrad` 以强制计算梯度。若使用低层理论方法(如xTB)进行初步搜索，能够大幅减少计算时间。
