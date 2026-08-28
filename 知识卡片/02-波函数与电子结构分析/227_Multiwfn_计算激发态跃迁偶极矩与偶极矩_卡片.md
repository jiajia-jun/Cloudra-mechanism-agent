---
id: 227
title: 使用Multiwfn计算激发态间的跃迁偶极矩和各个激发态的偶极矩
url: http://sobereva.com/227
domain: 波函数与电子结构分析
topic: Multiwfn_计算激发态跃迁偶极矩与偶极矩
cards: 9
---

# Multiwfn_计算激发态跃迁偶极矩与偶极矩 — 知识卡片

## 1. Gaussian计算激发态的IOp设置

Gaussian的CIS、TDHF、TDA-DFT、TDDFT计算中，必须设置IOp(9/40=x)关键词以输出足够多的组态系数供Multiwfn使用，x设得越大结果越准确但耗时也越大，通常设为3或4即可，IOp(9/40=4)代表输出系数绝对值大于0.0001的组态。
- 推荐输入写法：# B3LYP/6-31+G(d) TD(nstates=10) IOp(9/40=4)
- 推荐输入写法：# CIS(nstates=10)/6-31+G(d) IOp(9/40=4)

---

## 2. Multiwfn计算激发态跃迁和偶极矩的输入文件

使用Multiwfn计算激发态间跃迁偶极矩及激发态偶极矩，需要Gaussian等程序产生的输出文件(.out/.log)以及记录基函数定义和基态轨道信息的.fch/.fchk文件。
- Gaussian用户需使用formchk将.chk文件转换为.fch文件
- 该功能也支持ORCA、GAMESS-US等程序，详见Multiwfn手册3.21.A节

---

## 3. Multiwfn计算激发态跃迁偶极矩的操作步骤

启动Multiwfn后载入.fch文件，选择主功能18（电子激发分析）下的子功能5，并输入Gaussian输出文件路径，即可计算所有态（含基态和激发态）之间的跃迁电偶极矩。
- 命令序列示例：载入fch文件 -> 18 -> 5 -> 输入out文件路径
- 计算后可选1将结果输出至屏幕，或选2输出至transdipmom.txt文件

---

## 4. 激发态汇总信息的指标解读

Multiwfn输出包含N_pairs（组态数量）、Multi.（自旋多重度）和Normalization（归一化常数）等指标，Normalization越接近理想值（闭壳层0.5，开壳层1.0）说明结果精度越高，若偏差大应增大Gaussian的IOp(9/40)参数。
- IOp(9/40=x)中x越大，N_pairs越多
- 理想Normalization值：闭壳层0.5，开壳层1.0

---

## 5. 激发态间跃迁电偶极矩的电子贡献含义

在Multiwfn输出的激发态间跃迁电偶极矩矩阵中，对角元数值(i=j)对应第i激发态偶极矩中由电子贡献的部分，不等于该态的总偶极矩，因为还缺少原子核电荷的贡献。
- 对应物理量：<i|-r|i>
- 总偶极矩还需加上原子核电荷贡献

---

## 6. Gaussian验证激发态偶极矩的方法

在Gaussian中使用TD(root=n)和density=rhoci关键词可以输出第n个激发态的偶极矩，其中rhoci关键词确保传递非弛豫密度，计算结果与Multiwfn给出的电子贡献部分相符合。
- 示例关键词：# b3lyp/6-311G* TD(root=3,nstates=5) density=rhoci
- 对应物理量：非弛豫密度下的激发态偶极矩

---

## 7. 跃迁磁偶极矩的计算与定义

在Multiwfn功能18的子功能5中先选0再选Magnetic，可计算态间的跃迁磁偶极矩，程序输出值对应<i|r×▽|j>部分，定义式为-i<i|r×▽|j>，与Gaussian输出文件形式相同。
- Multiwfn输出部分：<i|r×▇|j>
- 完整定义：-i<i|r×▇|j>

---

## 8. 激发态总偶极矩的获取方法

在Multiwfn功能18的子功能5中选择4，可直接输出包含核与电子贡献的各个激发态总电偶极矩到dipmom.txt文件中。
- 输出文件：dipmom.txt
- 内容：Ground state dipole moment 和 Excited state electric dipole moments (a.u.)

---

## 9. 原点选择对激发态偶极矩数值的影响

当Gaussian将体系原点放置在核电荷中心位置时，原子核对偶极矩的贡献恰好为0，导致Multiwfn输出的包含核贡献的总偶极矩数值与仅含电子贡献的数值相同。
- 前提条件：Gaussian默认将原点置于核电荷中心
- 结果：核贡献为0，总偶极矩等于电子贡献偶极矩
