---
key: b290
title: 在VMD中计算RMSD衡量两个结构间的差异以及叠合两个结构
url: http://sobereva.com/290
domain: 可视化与制图
source: blog
year: 2020
cards: 10
---

# 在VMD中计算RMSD衡量两个结构间的差异以及叠合两个结构 — 知识卡片

## 1. RMSD的定义与应用场景

RMSD（Root mean square displacement/deviation）用于衡量两个结构间的整体几何偏差，适用于比较两种极小点构型的差异、电子激发/电离/外加电场前后几何结构的整体改变程度以及形成复合物后单体结构的变化等。相比于逐个比较键长键角，计算RMSD是用一个值衡量整体结构改变程度最恰当且省事的方法。

---

## 2. RMSD的计算公式

RMSD通过循环计算所有原子的坐标差值平方和的平均值再开方得到，其中x_i和x_i'分别是第i个原子在第一个结构和第二个结构中的x坐标，y、z坐标计算方式相同。该公式量化了两个结构在三维空间中的位置差异。

---

## 3. 结构叠合的必要性

计算两个结构间的RMSD之前必须先进行叠合，即通过平移和旋转其中一个结构来最小化两个结构之间的RMSD。若不进行此步骤，直接计算的RMSD包含了平移和旋转带来的偏差，无法准确衡量两个结构内部的几何差异。

---

## 4. 计算丙烷中性与阳离子结构RMSD的文件准备

使用VMD计算丙烷在中性和+1阳离子状态优化结构间的RMSD时，需准备两个xyz文件：neutral.xyz和cation.xyz。文件第一行写原子数（如11），第二行为注释行，随后按顺序列出各原子的元素符号及x、y、z坐标数值。

---

## 5. Gaussian输出文件转xyz格式的方法

若使用Gaussian进行优化，可利用Multiwfn将输出文件最后一帧结构转化为xyz格式。操作步骤为：将Multiwfn的settings.ini文件里的iloadGaugeom设为1，载入Gaussian输出文件，选择主功能100的子功能2，即可找到导出xyz文件的选项。

---

## 6. 在VMD中计算RMSD及叠合结构的操作步骤

启动VMD并载入两个结构文件后，通过Extensions - Analysis - RMSD Calculator打开工具。将左上角文本框内容改为all，取消选择Backbone only复选框，先点击Align进行结构叠合，再点击RMSD按钮，窗口下方显示的Total RMSD即为两个结构间的RMSD值。

---

## 7. VMD中计算特定原子集合RMSD的方法

在RMSD Calculator工具的文本框中可以输入特定的选择语句来指定计算范围。例如输入serial 2 to 4 8，则Align操作和RMSD计算将仅针对序号为2、3、4、8的原子进行。

---

## 8. VMD中双结构差异化显示的设置方法

为了直观比较两个结构，可在Graphics - Representation中分别对两个分子进行设置：将Coloring Method设为Color ID并选择不同颜色（如13 Mauve和蓝色），将Thickness设为4以加粗线条。在文本窗口输入color Display Background white命令可将背景改为白色。

---

## 9. 局部结构RMSD计算的原子顺序要求

对两个分子的局部区域（如苯环）进行叠合并计算RMSD时，被叠合部分必须满足两个条件：(1)原子数相同；(2)原子顺序一致。若原子顺序不一致（如交错排列），需在叠合前编辑结构文件，调整原子顺序以满足条件。

---

## 10. VMD叠合算法局部极小点的解决方法

当VMD的叠合算法落入局部极小点导致结构未能正确叠合时，可手动调节结构以提供更好的初猜。操作方式为：选择Mouse - Move - Molecule，按住alt键并用鼠标左键拖动可平移体系，按住alt+shift并用鼠标左键或右键拖动可旋转分子或沿屏幕旋转，调节后再次点击Align即可实现正确叠合。
