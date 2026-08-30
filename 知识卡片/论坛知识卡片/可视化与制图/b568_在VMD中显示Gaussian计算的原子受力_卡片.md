---
key: b568
title: 在VMD中显示Gaussian计算的原子受力
url: http://sobereva.com/568
domain: 可视化与制图
source: blog
year: 2020
cards: 6
---

# 在VMD中显示Gaussian计算的原子受力 — 知识卡片

## 1. 在VMD中可视化Gaussian原子受力

Gaussian程序通过force关键词计算原子受力后，可利用自写的tcl脚本在VMD中以箭头形式直观展示受力矢量。该方案弥补了GaussView仅能根据受力大小着色而无法绘制矢量箭头的不足，适用于各类需要分析原子受力的量子化学问题。VMD 1.9.3及Gaussian G16 A.03版本可用于实现此功能，绘图脚本及示例文件包含forcevec.tcl和drawarrow.tcl，需复制到VMD目录下。

---

## 2. 脚本参数设置说明

forcevec.tcl脚本开头包含若干可调整参数：set filename定义载入的Gaussian输出文件路径；set sclfac为原子受力矢量的缩放系数（a.u.单位），需根据图像效果尝试最佳值；set rad定义箭头粗细；set color定义箭头颜色；set crit设定阈值，若某原子受力小于最大受力乘以该系数，则不绘制箭头，默认为0.1。

---

## 3. 联苯S1态Franck-Condon点受力分析

在优化后的联苯基态极小点结构下计算S1激发态(TDDFT)原子受力，使用脚本set sclfac设为20进行绘制。图像显示联苯中央C-C键倾向于缩短，从受力情况可推断苯环结构将自发调整。PBE0/6-311G*级别下，S0态该键长为1.478埃，S1态优化后键长缩短至1.413埃，与受力分析结果一致。

---

## 4. 晕苯与富勒烯复合物弱相互作用受力分析

对于人为拉远结构的晕苯与富勒烯复合物(PM6-D3)，使用脚本set sclfac设为1500以突显弱相互作用力。绘制结果可见，靠近的原子间出现了令二者距离进一步拉近的力，体现了色散吸引作用。此方法适用于弱相互作用体系受力方向与大小的可视化分析。

---

## 5. 18碳环外电场受力分析脚本应用

在VMD文本窗口运行source forcevec.tcl后，可输入特定代码计算并绘制一批原子的总受力。代码通过原子序号列表（如4 5 6 7 8）累加受力分量，输出总受力矢量及模，并利用drawarrow在指定原子组的几何中心绘制箭头。此方法曾用于展示18碳环在电场下不同受力区域（左右侧、上下侧）的力学特性。

---

## 6. VMD绘图操作流程

将Gaussian输出文件载入GaussView并保存为pdb文件，随后将pdb文件载入VMD，并将输出文件移至VMD目录。修改forcevec.tcl中的filename和sclfac参数后，在VMD文本窗口输入source forcevec.tcl即可读取受力并绘制箭头，最终可在Graphics - Representation中将显示方式调整为Licorice。
