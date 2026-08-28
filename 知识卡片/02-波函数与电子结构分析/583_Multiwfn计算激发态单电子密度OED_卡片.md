---
id: 583
title: 使用Multiwfn计算odd electron density考察激发态单电子分布
url: http://sobereva.com/583
domain: 波函数与电子结构分析
topic: Multiwfn计算激发态单电子密度OED
cards: 2
---

# Multiwfn计算激发态单电子密度OED — 知识卡片

## 1. OED概念及适用场景

OED（odd electron density）是用于考察单电子分布的实空间函数，适用于任何能产生密度矩阵的理论方法（如CASSCF），弥补了某些方法（如TDDFT）无法直接计算激发态自旋密度的不足。
- OED不像自旋密度那样能通过正负号体现自旋方向，但足以讨论单电子分布的实际问题。

## OED的理论定义与计算公式
OED基于无自旋自然轨道计算，其定义为各自然轨道贡献的加和：$\rho_{odd}(r) = \sum_k \min(2-n_k, n_k) \rho_k(r)$。
- $n_k$是第$k$个自然轨道的占据数，$\rho_k(r)$是轨道波函数概率密度。
- 体系总的（有效）单电子数公式为：$N_{odd} = \sum_k \min(2-n_k, n_k)$。
- 该定义源自Yamaguchi等人（Theor. Chim. Acta, 48, 175 (1978)）及后续Head-Gordon（Chem. Phys. Lett., 372, 508 (2003)）和Nakano等人（Theor. Chem. Acc., 130, 711 (2011)）的工作。

## 计算TDDFT激发态OED的Gaussian输入示例
计算TDDFT激发态T1的OED时，需使用Gaussian进行TDDFT计算产生自然轨道并导出为wfn文件。
- 输入文件关键词示例：`# PBE1PBE/6-31g(d) TD(triplet) out=wfn`。
- 文件末尾需指定输出文件名（如`TDDFT_T1.wfn`），此时wfn文件记录的是T1态的自然轨道。
- 若使用Gaussian 09 C.01以前版本，关键词需额外加上`density`。

## 计算高阶激发态OED的Gaussian关键词
计算TDDFT不同激发态的OED时，需调整Gaussian输入关键词以匹配目标态。
- 计算S1态使用关键词：`# PBE1PBE/6-31g(d) TD out=wfn`。
- 计算T3态使用关键词：`# PBE1PBE/6-31g(d) TD(triplet,root=3,nstates=5) out=wfn`。

## 使用Multiwfn将轨道占据数转化为单电子数
在Multiwfn中载入记录自然轨道的wfn文件后，需通过主功能6将轨道占据数转化为OED定义的单电子数。
- 操作路径：启动Multiwfn -> 载入文件 -> 输入`6`（修改波函数） -> 输入`26`（修改轨道占据数） -> 输入`0`（选择所有轨道） -> 输入`odd`。
- 输入`odd`后，占据数被转化为`min(2-n_k, n_k)`，此时后续对电子密度的分析等同于对OED的分析。

## 使用Multiwfn绘制OED等值面图
将轨道占据数转化为单电子数后，利用Multiwfn主功能5可以绘制OED的等值面图。
- 操作步骤：输入`5`（计算格点数据） -> 输入`1`（电子密度） -> 输入`3`（高质量格点） -> 输入`-1`（观看等值面）。
- 建议将等值面数值设为`0.01 a.u.`以便观察。

## 使用Multiwfn计算OED的原子贡献
OED分布可以进行定量考察，利用Multiwfn的模糊空间分析功能可计算各原子对OED的贡献。
- 在完成占据数转化后，操作步骤：输入`15`（模糊空间分析） -> 输入`1`（对实空间函数在各个原子空间进行积分） -> 输入`1`（电子密度）。
- 可通过选项`-1`选择Becke、Hirshfeld或Hirshfeld-I等不同的原子空间划分方式。

## 考察自然轨道对OED的贡献
在Multiwfn中将轨道占据数转化为单电子数后，可通过主功能0查看各轨道的贡献，识别哪些自然轨道主导了OED。
- 在轨道观看界面选择`Orbital info. - Show all`，查看各轨道的占据数（即有效单电子数）。
- 只有原先占据数偏离0和2较大的自然轨道，其有效单电子数才较大。

---

## 2. OED在CASSCF双自由基体系中的应用

CASSCF计算双自由基体系时无法获得自旋密度，需要利用OED来考察单电子分布。
- 操作过程为：先产生记录CASSCF自然轨道的wfn文件，然后按照TDDFT示例中的步骤操作绘制OED图。
- Multiwfn手册4.A.6.1节提供了丁烷双自由基的OED计算示例。

## OED与电子相关效应及FOD函数的关系
OED可以用来考察体系电子相关效应的强弱，因为轨道占据数偏离整数源于电子相关效应。
- OED特征与Grimme提出的FOD (fractional occupation number weighted density) 函数（Angew. Chem. Int. Ed., 54, 1 (2015); Chem. Eur. J., 23, 6150 (2017)）颇为相似，但FOD利用的是有限温度DFT的占据数。

## OED计算对输入文件格式的要求
使用Multiwfn计算OED不限于Gaussian产生的wfn文件，只要格式支持且记录的是自然轨道即可。
- 支持的波函数文件格式包括molden、fch、wfn等，详见《详谈Multiwfn支持的输入文件类型、产生方法以及相互转换》（http://sobereva.com/379）。
