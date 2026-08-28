---
id: 701
title: 使用Multiwfn做Hirshfeld surface分析直观展现分子晶体和复合物中的相互作用
url: http://sobereva.com/701
domain: 波函数与电子结构分析
topic: Multiwfn进行Hirshfeld表面分析
cards: 16
---

# Multiwfn进行Hirshfeld表面分析 — 知识卡片

## 1. Hirshfeld surface分析的定义与基本功能

Hirshfeld surface分析是展现分子晶体中特定分子与周围分子间相互作用的方法，也可用于孤立体系中特定片段与周围原子间的相互作用。HS分析通过构造Hirshfeld表面（即分子权重函数数值为0.5的等值面）并将电子密度等实空间函数映射到表面上，直观考察分子间相互作用特征。
- 起源文献：Chem. Phys. Lett., 267, 215 (1997)；综述见Acta Cryst., B60, 627 (2004)和CrystEngComm, 11, 19 (2009)
- 构造算法：Marching Tetrahedron，见J. Mol. Graph. Model., 38, 314 (2012)

---

## 2. Hirshfeld surface的定义与权重函数

Hirshfeld surface由Hirshfeld权重函数定义，即分子中所有原子的Hirshfeld权重函数加和等于0.5的等值面。Hirshfeld权重函数基于孤立原子的球对称化电子密度定义，数值在0到1之间平滑变化，描述空间位置属于原子的程度。
- 原理出处：Theoret. Chim. Acta (Berl.), 44, 129 (1977)

---

## 3. Hirshfeld surface上常见的映射函数

HS分析常将特定三维实空间函数映射到Hirshfeld surface上，以分析相互作用特征。常用函数包括：
- d_i：表面内部（中心分子）原子到表面点的最近距离
- d_e：表面外部（环境分子）原子到表面点的最近距离
- d_norm：归一化接触距离，由d_i、d_e和范德华半径计算，数值越小暗示相互作用越强
- shape index（形状指数）：范围[-1,1]，负值越小说明表面越凹
- curvedness（曲度）：范围[-4,0.4]，-4对应完全平坦，正值越正越凸

---

## 4. 电子密度着色的优势

推荐使用电子密度对Hirshfeld surface进行着色以展现相互作用。电子密度越大的地方体现相互作用越强，效果比d_norm着色更平滑、物理意义更强且无范德华半径选取的任意性。实际计算中仅需使用耗时极低的准分子近似电子密度（由孤立原子电子密度叠加得到）。
- 准分子电子密度效果与量子化学计算电子密度相近

---

## 5. 指纹图（Fingerprint plot）的定义与作用

指纹图是将Hirshfeld surface上顶点的d_i和d_e值作为横纵坐标绘制的散点图。根据散点分布位置可讨论中心分子和周围分子间的相互作用特征，例如氢键给体和受体在图上会呈现特定的尖峰。
- 指纹图常结合局部接触分析使用

---

## 6. 局部接触分析

局部接触分析指定在HS分析中仅考虑中心分子的特定原子与周围分子的特定原子间的相互作用。该方法可以了解特定相互作用（如O...H）在Hirshfeld surface上的区域位置和面积占比。
- 可通过设置内部和外部原子范围来定义局部接触

---

## 7. Becke surface分析

Becke surface分析是用Becke权重函数的0.5等值面定义表面，是本文作者提出的概念。它与HS分析的区别在于可以在电子密度为0的区域（无法定义Hirshfeld权重）构造表面，除此之外一般使用Hirshfeld surface即可。
- Becke权重函数定义见《密度泛函计算中的格点积分方法》

---

## 8. Multiwfn做HS分析前的簇模型构建

使用cif文件进行分子晶体HS分析前，通常需要先利用Multiwfn的自动挖团簇功能构造“中心分子+周围一圈分子”的簇模型，因为cif文件记录的晶胞原子中分子往往被截断不完整。对于分子二聚体等孤立体系，则可直接提供坐标文件。
- 操作路径：主功能300 -> 7 -> 25
- 阈值建议：周围分子与中心分子最近原子对距离小于两者范德华半径和的1.2倍时纳入

---

## 9. 使用Multiwfn绘制Hirshfeld surface图的步骤

启动Multiwfn载入簇模型文件，进入主功能12，选择定义表面方式为Hirshfeld surface，输入中心分子原子序号，开始分析。在后处理菜单导出surf.cub（表面权重）和mapfunc.cub（映射函数数据），配合VMD脚本hirsh_rho.vmd进行作图。
- 作图命令：VMD文本窗口输入source hirsh_rho.vmd
- 脚本默认色彩刻度：0.0到0.015，蓝-白-红(BWR)渐变

---

## 10. 使用Multiwfn提取Hirshfeld surface极值点

Multiwfn可以导出Hirshfeld surface上被映射函数的极值点位置和数值，用于定量对比。在后处理菜单选择选项8导出extrema.pqr文件，其中碳原子记录极大点，氧原子记录极小点。
- 查询方法：在VMD中点击极值点球体获取index，在extrema.pqr中对应行倒数第3列为数值

---

## 11. 使用Multiwfn绘制指纹图

在主功能12后处理菜单选择20进入指纹图与局部接触分析，选择0开始分析，再选0在屏幕显示或选1保存为PDF文件。指纹图上点密度采用viridis配色，越密越黄，越疏越紫。
- 指纹图尖峰特征：d_i小d_e大对应氢键给体，反之对应氢键受体

---

## 12. 调整Hirshfeld surface格点密度

在主功能12分析前可以通过选择选项3“Spacing of grid points for generating molecular surface”修改格点间距。格点间距越小，Hirshfeld surface上的点越多，指纹图也越密。

---

## 13. 使用Multiwfn统计不同元素间接触面积

在指纹图与局部接触分析菜单中，选择选项3“Calculate contact area between different elements”，可一次性输出中心分子与周围分子每一对元素之间的局部接触面积及其占总表面积的百分比。
- 输出包含区分内外元素和不区分内外元素两种统计结果

---

## 14. 解决Hirshfeld surface等值面截断问题

如果Hirshfeld表面延伸超出计算盒子的范围导致表面出现窟窿，需要增大确定盒子延展距离的范德华半径倍数。默认倍数为1.7，可在主功能12的高级选项（选项4）中修改。
- 操作路径：主功能12 -> 4 -> 1 -> 输入更大的倍数（如2.3）

---

## 15. 孤立体系HS分析的几何预处理

对于孤立的分子复合物，HS分析生成的表面通常是开放的。若片段方向倾斜导致盒子和表面开口方向不美观，建议先进行几何变换将感兴趣的片段平面（如环平面）旋转至平行于XY平面。
- 操作路径：主功能300 -> 7 -> 11

---

## 16. DNA双螺旋结构的Becke surface分析实例

对于DNA双螺旋这种可能涉及电子密度极低区域接触的体系，应使用Becke surface分析。设置Becke surface时，可将盒子延展距离倍数设为0以避免表面延伸过大。由于计算量较大，建议使用多核并行或增大格点间距进行预览。
- 实例耗时：i9-13980HX笔记本16核并行耗时约15分钟
