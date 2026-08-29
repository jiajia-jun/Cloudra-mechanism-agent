---
id: 290
title: 在VMD中计算RMSD衡量两个结构间的几何偏差
domain: 可视化与制图
topic: VMD计算结构RMSD及叠合操作
cards: 7
---

## 1. RMSD的定义与用途
RMSD（Root mean square displacement/deviation）用于衡量两个结构间的整体几何偏差，适用于比较极小点构型差异、电子激发/电离/外加电场前后几何结构改变或形成复合物后的单体结构变化。RMSD定义公式为$\sqrt{\frac{1}{N}\sum_{i=1}^N [(x_i-x_i')^2 + (y_i-y_i')^2 + (z_i-z_i')^2]}$，其中i循环所有原子，x_i和x_i'分别是第i个原子在两个结构中的坐标。计算RMSD前必须先进行叠合（align），即通过平移和旋转一个结构来最小化RMSD，否则结果无法有效衡量内部差异。

---

## 2. 使用VMD计算RMSD的操作步骤
启动VMD并将两个结构文件拖入载入，选择Extensions - Analysis - RMSD Calculator；将左上角文本框内容改为all，取消选择Backbone only复选框，点击Align进行叠合，随后点击RMSD按钮，窗口下方显示的Total RMSD即为两个结构间的RMSD值。若只需计算指定原子，可在文本框输入对应的选择语句（如serial 2 to 4 8），Align和RMSD操作将仅针对这些原子进行。

---

## 3. 丙烷体系结构文件的数据格式
创建名为neutral.xyz和cation.xyz的文该资料件，第一行写原子数11，第二行为注释行，后续各行依次为元素符号、x、y、z坐标。中性丙烷坐标数据示例如下：C 0.000000 1.277193 -0.259856、H 0.884678 1.321887 -0.907445等；阳离子丙烷坐标数据示例如下：C 1.249671 -0.343789 0.000081、H 1.315464 -0.947246 0.909976等。

---

## 4. Gaussian输出文件转换为xyz文件的方法
如果使用Gaussian进行优化，将最后一帧结构转化为xyz格式的最简单方法是使用Multiwfn。操作步骤为：将Multiwfn的settings.ini文件里的iloadGaugeom设为1，用Multiwfn载入Gaussian输出文件，选择主功能100的子功能2，即可找到并选择导出xyz文件的选项。

---

## 5. VMD中直观显示结构差异的绘图设置
选择Graphics - Representation，在Selected Molecule中分别选择两个体系，将Coloring Method设为Color ID并分别选择颜色（如13 Mauve和蓝色），将Thickness设为4以加粗显示。在VMD文本窗口输入color Display Background white命令将背景改为白色，即可在图形窗口清晰直观地看到两个叠合结构的差异。

---

## 6. 局部区域RMSD计算的原子顺序要求
对两个主体结构相同但局部不同的分子（如苯酚和间硝基苯腈）计算局部区域RMSD时，被叠合部分必须满足两个条件：(1)原子数相同，(2)原子顺序一致。若原子顺序不一致（如交错排列），需在叠合前自行编辑结构文件调整原子顺序。

---

## 7. 解决VMD叠合算法局部极小问题的方法
若VMD的Align算法未能实现理想叠合（类似落入局部极小点），可手动调节分子位置以提供更好的初猜。操作方法为：选Mouse - Move - Molecule，按住alt键并用鼠标左键拖动某原子可平移整个体系，按住alt+shift并用鼠标左键拖动可旋转整个分子，按住alt+shift并用鼠标右键拖动可令整个分子沿屏幕旋转；调节接近后再次点击Align按钮即可完成正确叠合。
