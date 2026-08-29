---
key: t53346
title: ֧��H3O+��OH-��Madrid 2019����
url: http://bbs.keinsci.com/thread-53346-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2025
cards: 4
---

# ֧��H3O+��OH-��Madrid 2019���� — 知识卡片

## 1. Madrid 2019 水模型对离子的兼容性

Madrid 2019 力场水模型基于 Vega 和 Gamez 等人发展的模型构建，并与 TIP4P/2005 水模型搭配使用效果较好。该力场最初不支持铵根离子、硝酸根离子和硫酸根离子。后续该力场已扩展支持 [NH4]+、[NO3]- 和 [SO4]2- 等离子。

---

## 2. Madrid 2019 力场对 H3O+ 和 OH- 的支持

此前 Madrid 2019 力场缺乏 H3O+ 和 OH- 参数，目前该力场已扩展包含这两种离子的参数。相关 H3O+ 和 OH- 的参数分别发表于 J. Chem. Phys., 162, 171101 (2025) 和 J. Phys. Chem. Lett., 15, 9411 (2024)。

---

## 3. 新增离子的电荷标度方法

新加入离子的原子所使用的电荷标度方法为 ADCH 原子电荷。该方法的相关介绍可参考 J. Theor. Comput. Chem., 11, 163 (2012) 及其详细解析链接。电荷缩放系数采用 0.85，即 ADCH 原子电荷乘以 0.85 得到最终力场电荷。

---

## 4. GROMACS 拓扑文件获取

Madrid 2019 力场包含 H3O+ 和 OH- 的 GROMACS 拓扑文件可在相关文章的补充材料中找到。这些参数文件可以直接下载使用。
