---
id: 290
title: 在VMD中计算RMSD衡量两个结构间的几何偏差
url: http://sobereva.com/290
domain: 可视化与制图
topic: VMD计算结构RMSD及叠合操作
cards: 2
---

# VMD计算结构RMSD及叠合操作 — 知识卡片

## 1. RMSD的定义与应用场景

RMSD（Root mean square displacement/deviation）是衡量任意两个结构间整体几何改变程度的指标，适用于比较极小点构型差异、电子激发/电离/外加电场前后的结构变化以及复合物形成后的单体结构变化。计算RMSD之前必须先进行叠合，即通过平移和旋转一个结构来最小化两个结构之间的RMSD，否则计算结果无法有效衡量内部差异。

## RMSD计算公式
RMSD通过计算两个结构中对应原子坐标差的平方的平均值的平方根获得，公式定义如下：RMSD = sqrt[ (1/N) * sum_i ( (x_i - x_i')^2 + (y_i - y_i')^2 + (z_i - z_i')^2 ) ]。其中i循环所有原子，x_i和x_i'分别是第i个原子在第一个结构和第二个结构中的x坐标，y、z坐标同理。

## 丙烷中性与阳离子结构的坐标文件准备
准备VMD能识别的xyz格式文件，第一行写原子数11，第二行写注释（如Neutral或Ionized），随后按元素符号和xyz坐标列出原子数据。neutral.xyz包含优化后的中性丙烷坐标，cation.xyz包含优化后的阳离子丙烷坐标，坐标值必须精确保留小数点后六位。

## Gaussian输出文件转换为xyz格式的操作
若使用Gaussian，利用Multiwfn程序将优化任务最后一帧结构转化为xyz格式最简单。操作步骤为：将settings.ini文件里的iloadGaugeom设为1，载入Gaussian输出文件，选择主功能100的子功能2，选择导出xyz文件的选项。

## VMD中计算整体RMSD的操作步骤
启动VMD并载入neutral.xyz和cation.xyz，选择Extensions - Analysis - RMSD Calculator。将左上角文本框内容改为all，取消选择Backbone only复选框，点击Align进行叠合，然后点击RMSD按钮。窗口下方显示的Total RMSD即为结构间的RMSD值，本例计算结果为0.093埃。

## VMD中指定原子计算RMSD的方法
在RMSD Calculator的左上角文本框中输入特定原子选择语句（如serial 2 to 4 8），点击Align将仅根据指定原子进行叠合，点击RMSD将仅计算这些原子的RMSD。若不熟悉VMD的选择语句，可参考相关语法文档。

## VMD中双色绘制叠合结构的可视化设置
选择Graphics - Representation，在Selected Molecule中分别选中两个体系，将Coloring Method设为Color ID并分别选择不同颜色（如13 Mauve和蓝色），将Thickness设为4以加粗显示。在文本窗口输入color Display Background white命令将背景改为白色，即可清晰直观地看到结构差异。

## 局部结构叠合的原子顺序要求
对两个分子的局部区域进行叠合和RMSD计算时，被叠合的部分必须满足两个条件：原子数相同且原子顺序一致。若原子顺序不一致（如交错排列），需在叠合前编辑结构文件调整原子顺序以满足条件。

## VMD叠合算法局部极小点问题的解决
若点击Align后结构未正确叠合，通常是算法陷入局部极小点导致，需手动调节分子初猜。操作方法为：选Mouse - Move - Molecule，按住alt键用鼠标左键拖动原子平移体系，按住alt+shift并用鼠标左键或右键拖动原子旋转分子或沿屏幕旋转。调整至接近位置后再次点击Align即可成功叠合。

---

## 2. 不同取代苯体系局部RMSD的计算结果

以苯酚和间硝基苯腈为例，仅对苯环部分的碳原子（serial 1 to 6）进行叠合和RMSD计算。经过手动旋转调整初猜并正确叠合后，计算得到的苯环碳原子间RMSD仅为0.013埃，说明苯环非常刚硬，取代基对其结构的影响可以忽略不计。
