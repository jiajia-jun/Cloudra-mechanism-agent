---
id: 74
title: 谈谈NBO中用bndidx关键词输出的三种键级
domain: 波函数与电子结构分析
topic: NBO程序bndidx键级定义与适用性辨析
cards: 11
---

## 1. NBO键级分析的推荐工具与相关阅读
一般没必要用NBO算键级。Multiwfn支持非常全面的键级计算方法，Gaussian用户只要提供fch文件即可。使用方法见Multiwfn手册4.9节，原理见3.11节。可参考《谈谈原子间是否成键的判断问题》一文。

---

## 2. bndidx关键词输出的三种键级矩阵
使用bndidx关键词后，NBO程序会输出三种键级矩阵：1. Wiberg bond index matrix in the NAO basis；2. Atom-atom overlap-weighted NAO bond order；3. MO bond order。矩阵中(i,j)元素对应i、j原子间的键级。经常被提及的“NBO键级”说法很不严格，因为NBO还有LMO键级、NRT键级，且NBO占据数本身也可衡量键级，不应使用含糊不清的“NBO键级”一词。

---

## 3. NAO基下的Wiberg键级定义与计算
Wiberg键级定义来自Tetrahedron 24,1083：$W_{AB}=\sum_{i \in A}\sum_{j \in B}P(i,j)^2$，其中P为密度矩阵，此定义只适合正交基。NBO基于自然原子轨道(NAO)分析，NAO是正交基，故可直接使用Wiberg键级，即NBO输出的"Wiberg bond index matrix in the NAO basis"。

---

## 4. 推荐使用的键级类型
在NBO输出的三种键级中，唯一推荐的是"Wiberg bond index matrix in the NAO basis"。该键级可由NAO密度矩阵DMNAO计算得出，例如H-H键级为DMNAO(6,7)^2=(-0.0623)^2=0.00388，O-H键级为$\sum_{i=1,2,3,4,5}\text{DMNAO}(i,7)^2=0.95513$。

---

## 5. NAO基下的Mayer键级定义
Mayer键级定义来自CPL 97,270，适合非正交基：$A、B$间键级定义为$\sum_{i \in A}\sum_{j \in B}PS(i,j) \cdot PS(j,i)$，$PS(i,j)$是P和重叠矩阵S做矩阵乘所得矩阵的(i,j)元素。当使用正交基后，$S$为单位矩阵，公式变为$\sum_{i \in A}\sum_{j \in B}P(i,j) \cdot P(j,i)$，因P对称，还原为Wiberg键级。Mayer键级数值符合一般化学观念，如单键约1，三键约3，苯C-C键约1.5。

---

## 6. 第二种键级的定义与缺陷
第二种键级"Atom-atom overlap-weighted NAO bond order"定义为$\sum_{i \in A}\sum_{j \in B}P(i,j) \cdot S'(i,j)$，其中$P$用NAO的，$S'$却用PNAO重叠矩阵。这种定义缺乏依据，是一种既不完全是NAO、也不完全是PNAO的Mulliken键级（Mulliken键级含$2P(i,j)S(i,j)$），且少乘了2，结果不好，不要使用。

---

## 7. 第二种键级的数值验证
使用SPNAO关键词输出PNAO重叠矩阵$S'$，计算$T(i,j)=\text{DMNAO}(i,j) \cdot S'(i,j)$，则O-H键的该种键级为$\sum_{i=1,2,3,4,5}T(i,7)=0.53985$。该计算结果与NBO程序输出一致，验证了其定义。

---

## 8. NPA电荷的计算原理
所谓NPA电荷（常被误称为NBO电荷），是以NAO为基获得的Mulliken电荷。A原子布居数$=\sum_{i \in A}\sum_{j}P(i,j)S(i,j)$，因NAO正交（$S(i,j)=\delta(i,j)$），等于$\sum_{i \in A}P(i,i)$。例如氧的布居数为$\sum_{i=1,2,3,4,5}\text{DMNAO}(i,i)=8.4045$，净电荷为$8-8.4045=-0.4045$。

---

## 9. 第三种键级的定义与荒诞性
第三种键级"MO bond order"定义为$A、B$间键级$\sum_{i \in A}\sum_{j \in B}P(i,j)$。此定义理论上无根据，实际结果荒诞，如典型sigma键O-H3键级为$0.4113+0.7001-0.5439=0.5675$（正值），而等价的O-H2键级却为$0.4113-0.7001-0.5439=-0.8327$（负值），从应用看毫无意义。

---

## 10. 使用PNAO计算Mayer键级的尝试与失败
理论上可用非正交基PNAO做Mayer键级分析代替NAO下的Wiberg键级，需利用GENNBO5.0输出PNAO密度矩阵。但NBO5.0输出的PNAO密度矩阵存在bug，导致所得Mayer键级数值极大且不合理（如O-H键级达7.23），且$\text{Tr}(PS)$计算结果为16.22606912（应等于总电子数），表明该方法虽原理合理但受限于程序错误。

---

## 11. 键级矩阵的原子总价输出
在NBO输出键级矩阵之后，会输出"Wiberg bond index, Totals by atom"，指的是每个原子形成键级的总和，也称为原子价。这一规则对于第一种、第二种和第三种键级矩阵的输出均适用。
