---
key: t10805
title: NAMD�����ܼ���̡̳�1����eABF��WTM-eABF���ж�ά�����ܼ���
url: http://bbs.keinsci.com/thread-10805-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2018
cards: 20
---

# NAMD�����ܼ���̡̳�1����eABF��WTM-eABF���ж�ά�����ܼ��� — 知识卡片

## 1. NAMD 自由能计算教程更新记录

NAMD 自由能计算教程主要涵盖 eABF 和 WTM-eABF 多维自由能计算内容。教程更新记录显示，2025 年 9 月 27 日将名称更改为 "WTM-eABF" 并微调部分参数，同时补充了 Gromacs 相关说明；2020 年 5 月 28 日补充了 well-tempered-meta-eABF 使用方法及 NAMD 2.14b1 版本的 expandBoundaries 选项。

---

## 2. 自由能计算方法分类

自由能计算方法通常基于反应坐标或基于热力学积分进行分类。基于热力学积分的方法包括 FEP 和 TI，这些方法直接计算溶剂化自由能，但需要准确的力场参数；基于反应坐标的方法包括 ABF、Metadynamics、Umbrella Sampling 和 SMD。

---

## 3. NAMD 中的 ABF 方法优势

NAMD 软件中的 ABF 方法由开发者 Chris Chipot 等人集成在 Colvars 模块中。对于使用 NAMD 进行自由能计算的情况，推荐使用 ABF 类方法，因为 NAMD 对该方法的支援较好。

---

## 4. eABF 与 meta-eABF 概述

eABF (extended ABF) 的理论基础由 Tony Lelièvre 和 Wei Yang 等人提出，其在 NAMD 中的实现引入了 czar estimator (pABF)。meta-eABF 是 eABF 与 Metadynamics 的结合，引入了 well-tempered 特性后称为 WTM-eABF，在复杂体系如反应路径搜寻中被认为是最高效的方法之一。

---

## 5. eABF 与 meta-eABF 参考文献

eABF 的相关参考文献为 Fu et al. J. Chem. Theory Comput., 2016, 12(8), pp 3506–3513 和 Lesage et al. J. Phys. Chem. B, 2017, 121(15), pp 3676–3685；meta-eABF 的参考文献为 Fu et al. J. Phys. Chem. Lett., 2018, 9(16), pp 4738–4745；Well-tempered-meta-eABF 的参考文献为 Fu et al. Acc. Chem. Res. 2019, 52 (11), 3254–3264。

---

## 6. 示例体系：Alanine Dipeptide

NAMD 教程使用 Alanine dipeptide 作为示例体系来演示构象变化。该体系通常利用 Phi 和 Psi 两个二面角作为反应坐标来描述构象变化，通过计算这两个维度的自由能面来分析体系的稳定性。

---

## 7. NAMD 配置文件开启 Colvars 模块

在 NAMD 配置文件中，必须添加 `colvars on` 语句来启用 Colvars 模块。同时需要使用 `colvarsConfig colvarsA.in` 指定 Colvars 模块的配置文件名称为 colvarsA.in。

---

## 8. Colvars 输出与重启频率设置

在 Colvars 配置文件中，`colvarsTrajFrequency` 参数用于设置记录轨迹数据的频率，`colvarsRestartFrequency` 参数用于设置写入重启文件的频率。

---

## 9. Colvar 基本参数定义

在 Colvars 配置块中，`name` 用于定义集体变量名称，`width` 用于设置记录数据的精度（如 5.0），`lowerboundary` 和 `upperboundary` 用于设定变量的上下边界（如 -180 和 180）。

---

## 10. eABF 扩展拉格朗日参数设置

eABF 方法需要开启扩展拉格朗日量，设置 `extendedlagrangian on`。关键参数包括 `extendedFluctuation`（建议设置为与 width 相同，如 5.0）和 `extendedTimeConstant`（建议设置为 200），这些参数适用于任何体系。

---

## 11. 二面角 (Dihedral) 定义方法

Colvar 类型 `dihedral` 需要定义四个原子组，通过 `atomnumbers` 指定原子序号。教程示例中 Phi 二面角定义为原子 13-15-17-1，Psi 二面角定义为原子 3-1-17-15。

---

## 12. NAMD 2.14+ 版本的边界定义变更

NAMD 2.14 及之后的版本修改了边界定义方式，若需限制边界，需定义 `harmonicWalls` 块。该块包含 `colvars`（如 phi psi）、`lowerWalls`、`upperWalls` 和 `forceConstant`（如 1.0）参数，力常数单位会自动根据 width 值进行缩放。

---

## 13. ABF 计算块参数设置

ABF 计算块通过 `abf { ... }` 定义，其中 `colvars` 指定施加偏置的变量（如 phi psi）。`fullSamples` 参数建议设置为 500 到 2000 之间，表示每个 width 网格内的平均采样步数。

---

## 14. ABF 输出与 Czar Estimator 设置

在 ABF 配置中，`historyfreq` 用于设置写入 history 文件的频率。使用 `writeCZARwindowFile` 选项可以在使用 czar estimator 时输出一些中间文件。

---

## 15. eABF 计算结果

提交 eABF 计算作业运行约 50 ns 后，通常可以得到 converged 的结果。输出文件 `eabf.czar.pmf` 包含了计算得到的自由能面数据，可用于作图分析。

---

## 16. meta-eABF 配置特定选项

meta-eABF 配置在 eABF 基础上增加了 `subtractAppliedForce on` 和 `expandboundaries on` 选项。虽然 `expandboundaries` 源自 Metadynamics，但在此处写入有助于提升计算效率。

---

## 17. Metadynamics 偏置参数设置 (Hill)

meta-eABF 中的 `metadynamics` 块需设置 `hillwidth`（建议值为 3 或 5）和 `hillweight`（建议值为 0.05 或 0.1）。这些参数分别定义了高斯峰的宽度和高度，`colvars` 指定施加偏置的扩展自由度。

---

## 18. Well-Tempered Meta-eABF 参数设置

开启 Well-Tempered 算法需设置 `welltempered on`。`biastemperature` 参数决定了 Metadynamics 偏置势垒的残留高度，教程示例中使用的值为 4000。

---

## 19. meta-eABF 计算结果

提交 meta-eABF 计算作业运行约 10 ns 后，通常可以得到 converged 的结果。输出文件 `metaeabf.abf1.czar.pmf` 包含了计算得到的自由能面数据，可用于作图分析。

---

## 20. 自由能面结果应用

得到自由能面图后，可用于寻找体系反应路径或寻找稳定态极小值。关于如何利用这些结果寻找反应路径的详细方法，可参考相关的专门教程。
