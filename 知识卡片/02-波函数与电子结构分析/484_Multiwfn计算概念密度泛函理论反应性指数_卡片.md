---
id: 484
title: 使用Multiwfn超级方便地计算出概念密度泛函理论中定义的各种量
url: http://sobereva.com/484
domain: 波函数与电子结构分析
topic: Multiwfn计算概念密度泛函理论反应性指数
cards: 13
---
## 1. 概念密度泛函理论定义量计算功能

概念密度泛函理论（CDFT）也称密度泛函反应性理论，是用于预测和解释化学物质反应活性与反应位点的重要工具。Multiwfn程序主功能22可以通过极简单的步骤，一次性自动计算CDFT框架内常见的实空间函数、局部指数和全局指数。计算需要N、N+1、N-1电子态的波函数和能量，其中N指体系最稳定状态（如中性）的电子数。此功能避免了手动逐一计算的繁琐和错误，适用于广泛的研究需求。
- 引用文献：Tian Lu, Qinxue Chen, Realization of Conceptual Density Functional Theory and Information-Theoretic Approach in Multiwfn Program. In Conceptual Density Functional Theory, WILEY-VCH GmbH: Weinheim (2022); pp 631-647. DOI: 10.1002/9783527829941.ch31

---

## 2. Multiwfn可计算的CDFT指标类别

Multiwfn主功能22可计算的量分为全局指数、实空间函数和原子指数三大类。全局指数包括垂直电离能、垂直电子亲和能、Mulliken电负性、化学势、硬度、软度、亲电指数、亲电指数ωcubic、亲电描述符ε和亲核指数。实空间函数包括福井函数、双描述符、局部软度、局部亲电指数和局部亲核指数。原子指数包括简缩福井函数、简缩双描述符、简缩局部软度、简缩局部超软度、相对亲电/亲核指数、简缩局部亲电/亲核指数及简缩局部ωcubic亲电指数。
- 所有原子指数基于Hirshfeld电荷计算，不建议使用NPA等其它电荷。
- 参考：《TCA上的一篇对比不同原子电荷预测反应位点、亲电/亲核性的文章》

---

## 3. 计算CDFT量的输入文件准备流程

使用Multiwfn主功能22计算前，需准备N.wfn、N+1.wfn和N-1.wfn文件。对于Gaussian用户，可在Multiwfn中载入含优化后结构的文件（如phenol.xyz），选择主功能22，再选子功能1产生波函数文件。程序默认使用B3LYP/6-31G*级别，默认电荷和自旋多重度分别为0 1（N）、-1 2（N+1）和1 2（N-1）。这将生成N.gjf、N+1.gjf和N-1.gjf输入文件，计算后生成对应的wfn文件。
- 若settings.ini中路径已设置，Multiwfn可自动调用Gaussian计算并清理中间文件。

---

## 4. ORCA程序产生CDFT输入文件的方法

若使用ORCA而非Gaussian，需在Multiwfn主功能22下选择-2 Choose the quantum chemistry program used in option 1并选2。选择子功能1产生输入文件时，将生成N.inp、N+1.inp和N-1.inp文件。手动计算这些输入文件后，将在当前目录下产生所需的N.wfn、N+1.wfn和N-1.wfn文件。
- 若settings.ini中orcapath已设置，Multiwfn可自动调用ORCA计算并清理多余文件。

---

## 5. 计算CDFT各种指数的操作步骤

准备好N.wfn、N+1.wfn和N-1.wfn文件后，在Multiwfn主功能22中选择子功能2 Calculate various quantitative indices。程序将自动载入波函数文件，读取能量和波函数信息，计算Hirshfeld电荷，并输出所有指数到当前目录下的CDFT.txt文件中。计算过程迅速，且无需手动处理。
- 输出文件包含全局指数、原子电荷、简缩福井函数、简缩双描述符及局部亲电/亲核指数等。

---

## 6. CDFT计算结果中的亲核指数说明

Multiwfn输出的全局和局部亲核指数依赖于四氰基乙烯（TCE）的HOMO能量。程序默认使用B3LYP/6-31G*级别下预先计算好的TCE HOMO值（-0.335198 Hartree）。若用户当前使用的计算级别不是B3LYP/6-31G*，为了获得严格结果，应自行在当前级别下计算TCE的HOMO值，并手动根据定义修正亲核指数。
- 默认值在CDFT.txt输出中有注明：E(HOMO) of TCE used for evaluating nucleophilicity index is the value evaluated at B3LYP/6-31G* level。

---

## 7. ωcubic和亲电描述符ε的计算要求

ωcubic和亲电描述符ε是比传统亲电指数ω更严格的形式，涉及超硬度项，计算时需要额外的N-2态能量。在Multiwfn主功能22中，需先输入-1开启计算ωcubic和ε的选项，随后选择子功能1产生波函数文件。此时程序会生成N-2.gjf，计算得到N-2.wfn后，即可在CDFT.txt输出中获得体系整体的ωcubic、简缩ωcubic以及ε。
- 参考：J. Phys. Chem. A, 124, 2090 (2020) (ωcubic); Int. J. Quantum Chem., 124, e27366 (2024) (ε)。

---

## 8. 计算福井函数和双描述符格点数据

在Multiwfn主功能22中选择子功能3 Calculate grid data of Fukui function, dual descriptor and related functions。程序将载入三个电子态的wfn文件计算电子密度格点数据，用户可选择格点质量（如小分子选Medium quality）。随后可通过菜单选项直接可视化f+、f-、f0福井函数和双描述符的等值面图。
- 等值面数值示例：0.007。

---

## 9. 导出福井函数及局部软度立方体文件

在福井函数和双描述符计算菜单中，选择选项6可导出特定类型福井函数的cube文件（如f-.cub）。若要导出局部软度等乘以系数的量，需先选择-1设置比例因子（例如全局软度2.613235 Hartree^-1），再导出相应的福井函数cube文件，所得文件即对应局部软度数据。
- 也可使用VMD加载cube文件进行高质量渲染，参考《在VMD里将cube文件瞬间绘制成效果极佳的等值面图的方法》。

---

## 10. 超软度立方体文件的生成方法

超软度定义为双描述符乘上全局软度的平方，具有尺寸一致性。在Multiwfn主功能22的格点数据计算界面中，利用-1选项将比例因子设为全局软度的平方。随后选择8 Export grid data of scaled dual descriptor as DD.cub in current folder，生成的DD.cub文件即对应超软度的格点数据。
- 参考：J. Math. Chem., 62, 461 (2024)。

---

## 11. 不同电子态的电荷与自旋多重度设定

使用该方法时，N、N+1、N-1状态的净电荷和自旋多重度需根据体系电子数确定。对于中性自由基，N状态为0 2，N+1状态为-1 1，N-1状态为1 1。对于+1电荷阳离子自由基，N为1 2，N+1为0 1，N-1为2 1。对于-1电荷阴离子自由基，N为-1 2，N+1为-2 1，N-1为0 1。
- 此规则假设N+1和N-1状态不涉及高自旋简并，过渡金属配合物需通过能量比较确定最低自旋态。

---

## 12. 闭壳层离子的电荷与自旋多重度设定

对于闭壳层带电体系，电荷与自旋多重度的设定规则如下：若体系为+1电荷闭壳层阳离子，N状态为1 1，N+1状态为0 2，N-1状态为2 2。若体系为-1电荷闭壳层阴离子，N状态为-1 1，N+1状态为-2 2，N-1状态为0 2。
- 规则基于电子增减引起的净电荷变化及自旋配对原理。

---

## 13. 亲核和亲电超离域度计算

Multiwfn支持计算亲核和亲电超离域度，这是一种能量权重的基于轨道计算的福井函数，广泛用于构建QSAR方程。用户需提供含基组信息的文件（如fch、molden、mwfn），进入主功能22后选择选项8即可得到各个原子的超离域度。Multiwfn使用的计算形式是对原始半经验方法形式的广义化，适用于HF和DFT波函数。
- 参考：Multiwfn手册3.25.5节；Environ. Toxicof. Chem., 9, 417 (1990)。
