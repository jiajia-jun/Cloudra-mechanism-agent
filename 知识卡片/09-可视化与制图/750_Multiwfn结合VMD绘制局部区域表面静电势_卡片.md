---
id: 750
title: 使用Multiwfn结合VMD绘制分子局部区域表面静电势的方法
url: http://sobereva.com/750
domain: 可视化与制图
topic: Multiwfn结合VMD绘制局部区域表面静电势
cards: 7
---

# Multiwfn结合VMD绘制局部区域表面静电势 — 知识卡片

## 1. 绘制苯环碳原子区域表面静电势的操作步骤

启动Multiwfn载入phenol.wfn文件，依次输入12选择定量分子表面分析，输入0开始分析（默认电子密度0.001 a.u.的等值面），随后输入12选择对特定片段做定量分子表面分析，输入1-6指定苯环碳原子序号，输入y导出locsurf.pqr文件。在后处理菜单输入5将分子结构导出为mol.pdb文件。

---

## 2. 分子表面静电势色彩刻度范围设置

根据Multiwfn分析得到的整个分子表面的静电势最小值-0.042242 a.u.和最大值0.083100 a.u.,作图时使用的色彩刻度范围建议设为-0.05到0.05 a.u.。

---

## 3. locsurf.pqr文件的数据含义

locsurf.pqr文件中每个原子对应于分子表面上的一个顶点，pqr文件倒数第三列记录被映射的函数值即以a.u.为单位的静电势，残基号那一列为1和为0分别对应表面顶点属于和不属于自定义的片段。

---

## 4. 在VMD中显示苯环碳原子区域静电势的设置

将mol.pdb载入VMD，Graphics - Representation里把Drawing Method设成CPK；载入locsurf.pqr，Graphics - Representation里把选择语句设成resid 1，Drawing Method设Points，Size设10左右，Coloring Method用Charge。在Trajectory标签页把色彩刻度范围设成-0.05到0.05，Graphics - Colors - Color Scale里把Method设BWR。

---

## 5. 绘制氧原子区域表面静电势的操作步骤

在Multiwfn主功能12的后处理菜单选择11 Output surface properties of each atom，输入y导出locsurf.pqr文件。此时残基号直接对应于相应表面顶点对应的原子序号。

---

## 6. 在VMD中显示氧原子区域静电势的设置

按照苯环区域方式绘制，将locsurf.pqr载入VMD，把显示表面顶点的representation的选择语句改成serial 12（氧原子序号），即可展示氧原子区域的静电势分布。

---

## 7. 局部表面静电势图的视觉优势

相较于绘制整个分子表面的静电势填色图，绘制局部区域表面静电势图可以把自己真正感兴趣的区域的静电势专门展现清楚，而不受到其它区域的视觉干扰。
