---
key: b516
title: 关于为什么Multiwfn算的出RESP电荷与Antechamber的有所差异
url: http://sobereva.com/516
domain: 其他量化软件
source: blog
year: 2019
cards: 9
---

# 关于为什么Multiwfn算的出RESP电荷与Antechamber的有所差异 — 知识卡片

## 1. RESP电荷计算结果差异的主要原因

Multiwfn 计算出的 RESP 电荷与 Antechamber 计算结果存在差异的主要原因有两点：(1) 拟合点的分布不同；(2) 等价约束设置不同。这两个因素均会影响最终拟合得到的原子电荷数值。

---

## 2. 拟合点分布差异的影响

Multiwfn 在 3.6 和 3.7 版本默认使用 MK 方式设置拟合点，具体位置由 Multiwfn 自身代码确定。Antechamber 则从 Gaussian 输出文件中直接读取 MK 拟合点坐标和静电势。尽管 MK 方法定义了分布规则，但不同程序在球面点生成算法、点密度及接缝处去密等细节处理上存在差异，这导致电荷结果产生轻微差别。

---

## 3. Gaussian 输出拟合点的关键参数

Antechamber 读取 Gaussian 计算结果以获取拟合点时，需要在 Gaussian 输入行中包含 `Pop=MK iop(6/33=2) iop(6/42=6)` 关键字。其中 `iop(6/33=2)` 用于将拟合点位置和静电势数值打印到输出文件中，而 `iop(6/42=6)` 用于将拟合点密度设为高于默认值。

---

## 4. Multiwfn 与 Antechamber 的乙醇 RESP 电荷对比

使用 Multiwfn 默认设置计算乙醇分子的标准两步式 RESP 电荷时，甲基上的氢原子电荷为 -0.091298，羟基氢原子电荷为 0.407135。Antechamber 计算的对应结果分别为 -0.086155 和 0.410526，两者差异通常在 0.01 以内。

---

## 5. Multiwfn 复现 Antechamber 电荷的方法

若要使 Multiwfn 计算的 RESP 电荷与 Antechamber 精确一致，需在 Multiwfn 的 RESP 计算界面中选择选项 8。通过输入 Gaussian 输出文件路径，Multiwfn 将直接读取文件中的拟合点位置和静电势数值，从而消除因拟合点分布差异导致的结果偏差。

---

## 6. 等价约束设置差异示例：苯甲醛

对于苯甲醛体系，即便 Multiwfn 使用与 Antechamber 相同的拟合点信息，计算结果仍会有差异。这是因为 Antechamber 在第一步拟合中自动对苯环上的对称原子施加了等价性约束（如原子 4=2、8=6），而 Multiwfn 默认情况下不施加此类对称性约束。

---

## 7. Antechamber 的对称性等价约束规则

Antechamber 对苯甲醛等分子计算 RESP 电荷时，会自动将结构上对称的原子（如苯环对位或间位的碳、氢）电荷约束为相同。这种规则并非 RESP 电荷原始文献定义的标准做法，而是 Amber 开发者自行定义的设置。

---

## 8. 在 Multiwfn 中定义等价约束

Multiwfn 支持通过文资料件自定义等价性约束。用户可创建包含成对原子索引的文件（如内容为 `4,2` 表示约束原子 4 和 2 等价），并在 RESP 计算前选择读取该文件，即可在拟合过程中施加与 Antechamber 相同的约束。

---

## 9. 对称性约束对拟合误差的影响

对苯环上对称原子施加等价性约束会增加静电势重现性误差。以苯甲醛为例，不施加约束时的 RMSE 为 0.001373，施加 Antechamber 风格的对称约束后 RMSE 升至 0.002020。Multiwfn 允许用户根据需要决定是否使用此类约束，并支持利用结构对称性自动生成约束文件。
