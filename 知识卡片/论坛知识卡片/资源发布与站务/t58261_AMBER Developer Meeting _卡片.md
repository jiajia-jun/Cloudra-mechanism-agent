---
key: t58261
title: AMBER Developer Meeting 2026�ʼ�
url: http://bbs.keinsci.com/thread-58261-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2026
cards: 26
---

# AMBER Developer Meeting 2026�ʼ� — 知识卡片

## 1. AMBER 2026 开发者会议

AMBER 2026 开发者会议及其更新内容涉及分子动力学计算、机器学习、力场开发、水模型等多个领域的进展。

---

## 2. ff25sb 力场特性

ff25sb 力场由 Carlos Simmerling 开发，是继 ff19sb 之后 AMBER 力场库中一次重要的更新。
该力场增强了对 OPC 水模型的匹配度，并支持对 D-氨基酸的处理。

---

## 3. ff25sb 与 CMAP 项的关系

ff25sb 中包含了 CMAP 项，这与参考 CHARMM 思路的 ff19sb 不同。
目前关于 ff25sb 中的 CMAP 项是否与 ff19sb 中的项存在对应关系尚不明确。

---

## 4. ff19sb 力场局限性

ff19sb 引入了基于 CHARMM 思路的 CMAP 修正项，但在实际应用中存在二面角能量大于参考值的缺陷，且观察到了键长波动过大的现象。

---

## 5. AMBER 力场版本选择建议

在 ff19sb 稳定性问题完全解决之前，建议继续使用 ff14sb 或在 ff14sb 和 ff25sb 之间进行选择。
ff14SB 已移除对应的 CMAP 版本。

---

## 6. GROMACS 对 AMBER 力场的支持

GROMACS 已官方支持 ff14sb 和 ff19sb 力场。
ff14sb 被视为一个稳定的通用力场选择。

---

## 7. 木质素力场开发

Holger Gohlke 和 Stephan Schott-Verdugo 报告了木质素力场的开发进展。
该力场致力于描述木质素的复杂结构，关注大分子、小分子及片段的扩展性，以支持相关化学与材料学研究。

---

## 8. modXNA 核心功能

modXNA 是备受关注的扩展模块，允许用户以核苷酸为构建基元进行非经典核酸的模拟。
该工具可与 GAFF 力场体系协同工作。

---

## 9. modXNA 适用范围

modXNA 支持用户根据相关文献手动拼接 tRNA、siRNA 等非经典核酸分子。
这对研究非经典核酸体系提供了重要补充，弥补了 GAFF 对此类分子模拟能力的不足。

---

## 10. 小分子参数优化方法

Zeke Piskulich 介绍了小分子的参数优化方法，重点在于对小分子的二面角参数进行优化。
该方法旨在提高小分子模型的准确性。

---

## 11. Antechamber 更新内容

Antechamber 更新增加了对 CIF 格式的支持。
同时推出了 ABCG2 作为部分通用默认电荷，与 RESP 电荷相比具有效率较高的优势。

---

## 12. GAFF3 与 ABCG2

GAFF3 计划将 ABCG2 设为默认部分电荷。
对于原子数量较多、RESP 计算耗时较长的体系，ABCG2 可作为通用小分子电荷的解决方案。

---

## 13. GAFF 版本状态

GAFF2.3 目前仍是一个小版本更新。

---

## 14. 金属离子力场支持

Milana Bazayeva 报告了对 Mn、Co、Ni、Cu、Zn 等过渡金属以及 Pd 的支持情况。
这些金属离子可通过 12-6-4 模型进行描述，并在 cpptraj 和 parmed 工具中得到支持。
相关教程可参考 ambermd.org/tutorials/advanced/tutorial20/。

---

## 15. pGM LJ 参数优化

Taoyu Niu 报告了对基于 pGM 模型的 Lennard-Jones 参数进行的优化工作。

---

## 16. AMBER 极化模型进展

Darrin York 报告了 AMBER 极化模型的更新，主要包括 AMOEBA 力场和新的极化方法。
AMOEBA 已被正式集成至 AMBER 软件体系中。

---

## 17. 极化计算方法的互操作性

AMBER 目前致力于实现与其他极化计算方法（如 NAMD、OpenMM、GROMACS、CHARMM）的互操作性。
这些软件正在建立一套通用的文件格式规范。

---

## 18. Tinker 与 AMOEBA

虽然 Tinker 是 AMOEBA 的原生实现品，但 AMBER 集成后的易用性更高。
Tinker 主要面向专家用户，对普通用户的实际应用影响有限。

---

## 19. AMBER 机器学习模块

AMBER 新增了 QM/MM deltaMLP 模块、DeepMD-GNN 接口以及 FE-Toolkit 自由能计算工具。
这些工具丰富了 AMBER 在机器学习和自由能计算方面的功能。

---

## 20. OPC3-Pol 水模型

Alexey Onufriev 介绍了结合 Drude 模型的 OPC3-Pol 极化水模型。
该模型将扩展至 AMBER 中，配合 Drude 模型进行使用。

---

## 21. Drude 模型集成状态

Drude 模型在 AMBER 中的实现目前仍处于系统调试阶段。
此外，确定了 ff19sb 与 OPC 水模型的匹配性，并基于此常识改进了 GB 模型，有望提升 GB/SA 计算精度。

---

## 22. DEGAUSS 与 pGM 集成

Larry Huang 报告了 DEGAUSS 程序与 pGM 模型的集成及最新扩展。

---

## 23. 机器学习势函数应用现状

尽管机器学习势函数发展迅速，但在药物研发等实际应用场景中仍面临挑战。
目前需要在计算速度、精度与各自领域的特定优势之间取得平衡。

---

## 24. SIRAH 粗粒化模型

SIRAH 粗粒化模型已正式并入 AMBER。
该模型被视为除 MARTINI 之外的另一种 CG 模型选择。

---

## 25. SIRAH 模型组件与工具

SIRAH 提供了对 DNA 模型的支持以及配套的 GUI 辅助工具。

---

## 26. SYCL 支持与 Intel GPU

Andy Goetz 报告了 AMBER 对 SYCL 生态的更新，增加了对 Intel GPU 的支持。
这一更新扩展了 AMBER 可运行的硬件平台范围。
