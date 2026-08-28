---
id: 738
title: 计算IGMH等值面的面积和体积的方法
url: http://sobereva.com/738
domain: 波函数与电子结构分析
topic: 计算IGMH等值面面积与体积
cards: 5
---

# 计算IGMH等值面面积与体积 — 知识卡片

## 1. 计算IGMH等值面面积和体积的两种方法

计算IGMH等值面面积和体积有两种方法：一是使用Multiwfn的定量分子表面分析（主功能12），适合仅存在一个目标等值面的情况；二是结合ChimeraX程序载入Multiwfn产生的cub文件，可测量图中任意一个等值面的面积和体积，且普适于IRI函数、范德华势等各种函数。计算IGMH前需在settings.ini里将iuserfunc设为91以启用δg_inter函数。IGMH等值面指IGMH方法里定义的δg_inter函数的等值面，其面积与pi-pi相互作用强度存在正相关性。

---

## 2. Multiwfn计算单等值面面积体积的参数设置

在Multiwfn目录下的settings.ini里将iuserfunc设为91，代表把用户自定义函数设为IGMH方法的δg_inter函数。启动Multiwfn载入波函数文件后，需定义片段范围，选择主功能12定量分子表面分析，设置等值面数值（如0.002 a.u.）并开始分析。进入主功能12时选项3 "Spacing of grid points for generating molecular surface" 用于设置格点间距，默认为0.25 Bohr，数值越小计算耗时越高而统计精度越高。

---

## 3. Multiwfn计算单等值面面积体积的操作步骤

启动Multiwfn并载入波函数文件后，依次输入：1000（隐藏功能）、16（定义片段）、2（定义两个片段）、输入各片段原子序号范围、12（定量分子表面分析功能）、1（设置用于定义表面的函数）、2（某个实空间函数）、100（用户自定义函数）、输入等值面数值（如0.002）、6（开始分析）。程序计算后屏幕将显示体积（如10.24465 Angstrom^3）和总表面积（如90.55182 Angstrom^2）。在后处理菜单选-3可观看当前等值面，选-2可将格点数据导出为surf.cub。

---

## 4. Multiwfn结合ChimeraX计算多等值面面积体积的流程

针对存在多个等值面的情况，需先用Multiwfn生成δg_inter的cub文件和结构的xyz文件。在Multiwfn中对波函数文件依次选择弱相互作用可视化分析（20）、IGMH分析（11）、定义片段、设置格点间距（如0.2 Bohr）、导出格点数据（3）以获得dg_inter.cub。退回主菜单输入xyz并回车，输入文件名导出结构xyz文件。随后在ChimeraX中载入xyz和cub文件，设置等值面数值，使用Tools - Volume Data - Measure and Color Blobs功能，按住Alt键点击目标等值面，界面右下角将显示其体积和面积。

---

## 5. ChimeraX测量等值面的操作细节

启动ChimeraX并将xyz和cub文件拖入界面载入，拖动红箭头所示的竖杠激活等值面设置，在蓝箭头所示的文本框里输入等值面数值（如0.01）。选择Tools - Volume Data - Measure and Color Blobs，按住Alt键并点击要考察的等值面，该等值面会被自动着色，且界面右下角显示其体积（如0.31 Å^3）和面积（如3.28 Å^2）。ChimeraX和Multiwfn产生等值面的算法不同，导致面积和体积会有轻微差异（如面积相差0.7%）。

---
