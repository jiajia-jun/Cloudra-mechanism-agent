---
id: 461
title: 使用Multiwfn计算CVB指数考察氢键强度
url: http://sobereva.com/461
domain: 波函数与电子结构分析
topic: Multiwfn计算CVB指数考察氢键强度
cards: 10
---

# Multiwfn计算CVB指数考察氢键强度 — 知识卡片

## 1. CVB指数的定义与原理

CVB (core-valence bifurcation) 指数是基于电子定域化函数(ELF)拓扑分析定义的用于衡量氢键强度的指标，由Silvi等人最初在Theor. Chem. Acc., 104, 13 (2000)中提出。该指数定义为CVB index = ELF(C-V) - ELF(DH-A)，其中ELF(C-V)代表给体原子内核盆与价层盆之间的二分点数值，ELF(DH-A)代表V(D,H)与V(A)之间的二分点数值即(3,-1)型ELF临界点数值。CVB指数越负通常代表氢键越强，极强共价性氢键数值很负，中等强度在0附近，较弱氢键数值明显为正。

---

## 2. CVB指数的物理意义与关键因素

氢键越强，H和A之间距离越近且共价性越显著，导致ELF(DH-A)数值越大，从而使CVB index越负。CVB指数名称虽然侧重core-valence二分点数值，但真正关键的决定因素是ELF(DH-A)数值，不同氢键间ELF(DH-A)的差异远大于ELF(C-V)的差异。

---

## 3. Multiwfn中CVB指数的计算定义

Multiwfn（主功能200的子功能1）计算CVB指数的公式为CVB index = ELF(C-V,D) - ELF(DH-A)。该计算中ELF(DH-A)取H-A连线上ELF极小点的数值而非精确拓扑二分点，因精确二分点几乎就在H-A连线上，故这种近似几乎没有差异。ELF(C-V,D)直接取D-H连线上相应的ELF极小点数值，而非精确的core-valence二分点，以避免多原子二分点选取的任意性和计算复杂性。

---

## 4. CVB指数与氢键结合能的相关性

使用Multiwfn计算并在B3LYP-D3(BJ)/def2-TZVP下优化的氢键二聚体体系，以及高精度MP2/jul-cc-pVQZ结合counterpoise校正计算的氢键结合能显示，CVB指数和氢键结合能之间存在显著的线性关系。除去OC...HF这一例外，线性关系非常理想。

---

## 5. CVB指数分量与氢键强度的关系

CVB指数的两个组成部分ELF(C-V,D)和ELF(DH-A)自身也与氢键强度存在明显相关性。ELF(C-V,D)与结合能的线性关系很好，但物理意义解释困难且数值差异很小；由于“CVB指数 vs 结合能”的图与“ELF(DH-A) vs 结合能”相似，CVB指数的重点是ELF(DH-A)。

---

## 6. AIM理论键临界点电子密度与氢键强度的关系

对于测试的氢键二聚体，AIM理论里的键临界点(BCP)的电子密度ρ(BCP)与结合能具有良好的关系。BCP处势能密度与结合能的线性关系远没有ρ(BCP)好，相关研究见J. Chem. Theory Comput.文章介绍链接http://sobereva.com/513。

---

## 7. Multiwfn自动计算CVB指数的输入要求

只有在2019-Feb-5及之后更新的Multiwfn版本中才包含CVB指数自动计算功能。计算CVB指数需要输入包含波函数的文件，常见的.fch、.molden、.wfn等格式均可作为输入文件。

---

## 8. CVB指数计算实例：HF...HF

在Multiwfn中计算HF...HF二聚体的CVB指数，通过输入wfn文件并选择主功能200及子功能1，随后输入给体原子、氢原子、受体原子的序号（如2,1,3）即可自动计算。程序会输出ELF(C-V,D)、ELF(C-V,A)、ELF(DH-A)的数值、极小点与氢原子的距离以及最终的CVB index。

---

## 9. 极强氢键的特殊情况处理

对于极强氢键（如O-H-F体系），由于H和A之间存在显著共价特征，V(D,H)会二分为V(D)和V(H)，导致D-H连线上出现独立V(H)的ELF盆极小点。此时常规的Multiwfn自动计算CVB指数方法不适用，必须通过主功能3作图并手动计算，且应分别考察不同相互作用（如O-H...F和O...H-F）对应的CVB指数。

---

## 10. 非单原子受体氢键的CVB指数计算

当氢键受体不是单一原子（如pi-氢键）时，无法使用Multiwfn自动计算功能，需手动计算。以HF...乙烯为例，ELF(C-V,D)通过绘制F-H连线上的ELF曲线取极小点获得；ELF(DH-A)需通过ELF拓扑分析（主功能2）在H与pi电子区域之间寻找(3,-1)型ELF临界点得到其数值。
---
