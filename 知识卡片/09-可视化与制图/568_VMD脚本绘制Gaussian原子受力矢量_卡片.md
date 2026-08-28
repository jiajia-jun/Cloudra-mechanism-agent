---
id: 568
title: 在VMD中显示Gaussian计算的原子受力
url: http://sobereva.com/568
domain: 可视化与制图
topic: VMD脚本绘制Gaussian原子受力矢量
cards: 6
---

# VMD脚本绘制Gaussian原子受力矢量 — 知识卡片

## 1. VMD显示Gaussian原子受力的准备步骤

使用VMD通过笔者自写的tcl脚本将Gaussian计算的原子受力直观地通过箭头展现出来。需要从指定链接下载绘图脚本和示例文件，将forcevec.tcl和drawarrow.tcl复制到VMD目录下。本文使用VMD 1.9.3和Gaussian G16 A.03。

---

## 2. forcevec.tcl脚本配置参数说明

脚本forcevec.tcl开头包含几个关键设置：set filename设置载入的Gaussian输出文件路径；set sclfac设置原子受力矢量乘以该系数（a.u.）作为箭头长度，需根据实际图像效果反复尝试；set rad设置箭头粗细；set color设置箭头颜色名；set crit设置系数，若原子受力小于最大受力乘以该系数则不绘制箭头，默认为0.1。

---

## 3. 例1：联苯基态极小点结构在S1势能面上的受力分析

例1使用biphenyl_S1force.out文件，这是在优化过的联苯基态极小点结构下用TDDFT算的S1激发态原子受力输出文件。将结构载入GaussView保存为pdb文件并载入VMD，修改脚本set filename为biphenyl_S1force.out，set sclfac改为20，运行source forcevec.tcl绘制箭头。图像显示在Franck-condon点位置，联苯中央的C-C键倾向于缩短，且其它原子也有显著受力。

---

## 4. 例2：晕苯与富勒烯复合物的受力分析

例2使用complex_force.out和complex_force.pdb，这是在优化的复合物结构基础上人为拉远距离后用PM6-D3计算的输出文件。载入pdb文件并将out文件复制到VMD目录，将脚本set filename设为complex_force.out。由于弱相互作用对应的原子间相互作用很弱，set sclfac需设为较大值（文中用1500）。图像显示由于色散吸引作用，挨得较近的原子上出现了令二者距离进一步拉近的力。

---

## 5. 例3：外电场下18碳环的受力可视化应用

例3展示了外电场对18碳环几何结构影响的研究，相关论文发表于ChemPhysChem。图中用不同颜色箭头展示左、右及上、下两侧原子的总体受力，原子颜色体现ADCH方法算的原子电荷。图(a)显示受力造成键长改变倾向；图(b)显示结构弛豫后受力倾向于使碳环沿电场方向拉长、垂直方向压扁；图(c)显示撤去电场后碳环有恢复成圆形的倾向。

---

## 6. 绘制一批原子总受力的TCL代码

若要绘制一批原子的总受力，可在运行source forcevec.tcl后，将特定代码拷入VMD文本窗口。示例中atmleft "4 5 6 7 8"是被计算总受力的原子序号，代码会累加这些原子的受力分量并输出总受力矢量及模。绘制箭头时，为了位置舒适，箭头中心位置取的是$atmleft 3 9 2 10的几何中心。
