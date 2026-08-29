---
key: b582
title: 用Multiwfn计算过渡金属的d-band center（d带中心）
url: http://sobereva.com/582
domain: 波函数与电子结构分析
source: blog
year: 2021
cards: 8
---

# 用Multiwfn计算过渡金属的d-band center（d带中心） — 知识卡片

## 1. d-band center与PDOS的关系及Multiwfn适用版本

d-band center与投影态密度（PDOS）密切相关，可通过绘制PDOS图计算其位置。计算时需使用Multiwfn程序，且必须使用2021年1月14日及之后更新的版本以支持相关功能。此方法既适用于孤立团簇体系，也适用于通过CP2K产生波函数文件的周期性体系。

---

## 2. Hammer和Nørskov的d-band center模型

该模型用于解释和预测不同过渡金属表面的催化活性，其核心在于过渡金属d带与吸附小分子轨道的混合。d带相对于Fermi能级越高，反键态被占据程度越低，化学结合作用越强。d-band center（$\varepsilon_d$）定义为d态PDOS中心位置与Fermi能级的差值，可作为衡量化学吸附能力的描述符。

---

## 3. Multiwfn计算d-band center的原理

Multiwfn主功能10在绘制PDOS时，会根据用户定义的片段和作图范围，通过积分公式计算并输出PDOS的中心位置。计算d-band center时，需将片段定义为过渡金属的D基函数，并使作图范围覆盖d带出现的能量区间。最终结果为输出的中心位置减去Fermi能级值，对于孤立体系通常直接取HOMO能级作为Fermi能级。

---

## 4. 定义d轨道片段的Multiwfn操作步骤

在Multiwfn主功能10（绘制DOS）界面中，选择-1定义片段，通过条件方式（cond）选择基函数。设置时需选择D型基函数（D），不限制原子序号范围（a）和基函数序号范围（a），保存片段（q）并返回DOS绘制界面。

---

## 5. d-band center计算示例参数设置

以Cu13团簇为例，在DOS绘制界面中，需将单位切换为eV（8），设置横坐标范围为-13到0 eV（2, -13,0,2）。此范围充分覆盖了d带出现的区间，能够确保计算得到的中心位置具有化学意义。

---

## 6. Cu13团簇d-band center计算结果验证

使用HOMO能级（-4.16932 eV）作为Fermi能级时，Cu13团簇的d-band center计算值为PDOS中心（-6.510656 eV）减去HOMO能级，即-2.34 eV。该结果与文献（J. Clust. Sci., 29, 867 (2018)）中给出的-2.33 eV数值相符。

---

## 7. 作图横坐标范围对计算结果的影响

作图横坐标范围需合理选取以涵盖d带，下限适当降低（如至-20 eV）不影响结果，因更低能量处无d带贡献。上限不宜过高，避免包含高能区域无化学意义的非价层态（如使用扩展基时>10 eV的态），否则会导致计算出的中心位置（如10.373 eV）失去意义。

---

## 8. 开壳层体系自旋态的选择注意事项

对于非限制性方法计算的开壳层体系，Alpha和Beta自旋的d-band center位置不同。Multiwfn默认计算Alpha轨道的PDOS中心，若需考察Beta轨道或两者兼顾，必须在DOS绘制界面中选择6（Choose orbital spin）进行相应设置（Beta或Both），并在文献报道中明确说明所考察的自旋状态。
