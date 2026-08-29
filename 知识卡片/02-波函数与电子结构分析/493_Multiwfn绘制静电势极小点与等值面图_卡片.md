---
id: 493
title: 绘制静电势全局极小点+等值面图展现孤对电子位置的方法
domain: 波函数与电子结构分析
topic: Multiwfn绘制静电势极小点与等值面图
cards: 9
---

## 1. 静电势全局极小点与孤对电子定位
使用静电势全局极小点位置可以展现孤对电子区域，这种方法能合理地展现孤对电子出现区域且与化学直觉一致。考察孤对电子位置还可以通过轨道定域化分析看对应孤对电子的轨道质心位置，或通过ELF/LOL函数绘图及临界点位置考察。参考Suresh的文章及J. Comput. Chem., 39, 488 (2018)中的图示，极小点连同周围的静电势等值面共同展现了该区域。
参考文献：,, J. Comput. Chem., 39, 488 (2018)

---

## 2. 计算设置与输入文件准备
以乙硫醛为例，使用Gaussian在B3LYP/def2-TZVP级别下对结构进行优化并产生波函数文件（fch格式）。为了加快静电势计算，建议让Multiwfn调用本机Gaussian中的cubegen工具。Multiwfn应使用官网最新版本，VMD推荐使用1.9.3版。
- 计算级别：B3LYP/def2-TZVP
- 软件：Multiwfn (官网最新版), VMD 1.9.3

---

## 3. 使用盆分析获取静电势极小点
在Multiwfn中输入波函数文件，选择主功能17（盆分析）、子功能1（生成盆并获得极值点）、函数12（静电势）。若精度要求不高，选择Low quality grid即可；若调用cubegen，Intel四核机器下计算不超过一分钟。屏幕将输出极值点的X,Y,Z坐标（Angstrom）和Value（a.u.）。
- 命令路径：17 -> 1 -> 12
- 输出单位：坐标(Angstrom), 数值(a.u.)

---

## 4. 静电势极小点坐标与数值示例
对乙硫醛进行盆分析后，得到两个关键的静电势极小点，其坐标与数值分别为：点1坐标(-0.31737088, -2.08489274, -0.05291772)，数值-0.04389250 a.u.；点2坐标(2.64602171, -0.17985465, -0.05291772)，数值-0.04492940 a.u.。乘以627.51换算为kcal/mol后，数值分别为-27.5 kcal/mol和-28.2 kcal/mol。
- 换算系数：1 a.u. = 627.51 kcal/mol
- 点1：-0.04389250 a.u. (-27.5 kcal/mol)
- 点2：-0.04492940 a.u. (-28.2 kcal/mol)

---

## 5. Multiwfn中绘制静电势等值面
在盆分析界面选择0观看极值点，点击Attractor labels取消标签。输入-10返回主菜单，选择13（处理格点数据），选择-2（观看等值面）。在图形窗口的Isosurface Value文本框中输入Vmin+10/627.51计算出的数值，按回车后点击Show both sign以避免显示相反符号的等值面。在Isosurface style里选Mesh，最后保存图像并标注极值点数值。
- 等值面数值公式：Vmin + 10/627.51
- 设置步骤：Show both sign -> Isosurface style: Mesh

---

## 6. Multiwfn导出格点数据用于VMD
退出Multiwfn图形窗口，在主功能13界面中选择0，输入文件名（如ESP.cub）将内存中的静电势格点数据导出为cube文件。该文件可用于在VMD中进行更高质量的绘制。
- 操作路径：Main function 13 -> 0 -> Input filename

---

## 7. VMD绘制原子与等值面设置
启动VMD载入ESP.cub文件，进入Graphics - Representation，将Drawing Method切换为CPK，Sphere Resolution设为22。点击Create Rep创建新的表示，设置绘制方法以显示等值面。
- Drawing Method: CPK
- Sphere Resolution: 22

---

## 8. VMD中绘制静电势极小点
在VMD命令行窗口输入`color Display Background white`切换为白背景。使用`draw color orange`设置颜色，并使用`draw sphere`命令在极小点坐标处绘制半径0.1、分辨率15的桔黄色小球。
- 命令示例：`draw sphere { -0.31737088 -2.08489274 -0.05291772 } radius 0.1 resolution 15`
- 小球参数：radius 0.1, resolution 15

---

## 9. 静电势拓扑分析的高精度替代方案
原用盆分析方法得到静电势极小点位置和数值，但使用Multiwfn的拓扑分析功能可实现同样目的且精度更高。若对精度有较高要求，应当用拓扑分析代替盆分析。
参考文献：《使用Multiwfn对静电势和范德华势做拓扑分析精确得到极小点位置和数值》。
