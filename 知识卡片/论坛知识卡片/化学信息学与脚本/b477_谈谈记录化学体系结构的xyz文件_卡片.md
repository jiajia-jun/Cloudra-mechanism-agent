---
key: b477
title: 谈谈记录化学体系结构的xyz文件
url: http://sobereva.com/477
domain: 化学信息学与脚本
source: blog
year: 2019
cards: 18
---

# 谈谈记录化学体系结构的xyz文件 — 知识卡片

## 1. xyz文件的定义与结构

xyz是一种记录化学体系结构的文本型文件格式。文件第一行为原子数，第二行为标题行（内容随意），后续各行依次记录各原子的元素名及X、Y、Z笛卡尔坐标，单位为埃。该格式为自由格式，整数位和小数位随意，且坐标记录精度无上限。

---

## 2. 多帧xyz文件

xyz文件可以通过将多个构象的信息简单合并来记录多帧数据，各帧的原子数通常应当相同。这种格式常用于记录如阿斯巴甜的多个构象或分子动力学轨迹。

---

## 3. 支持打开xyz文件的可视化程序

Multiwfn、VMD、CYLView、Chimeria、ChemCraft、VESTA等程序可以直接载入并可视化xyz文件。Chem3D（至少16.0版）、GaussView（至少6.0.16版）、Material Studio（至少2018版）不支持直接读取xyz文件。

---

## 4. 利用GaussView和Multiwfn产生xyz文件

在GaussView中建模并保存为gjf文件后，可手工将其修改为xyz格式。或者将含有结构信息的文件（如pdb、mol、fch、gjf等）载入Multiwfn程序，选择主功能100下的子功能2（Output current structure to .xyz file）输出xyz文件。

---

## 5. 利用VMD和OpenBabel产生xyz文件

在VMD程序中，将支持的文件拖入主窗口，右键点击相应项选择Save Coordinates，将File type选为xyz即可保存。也可以使用OpenBabel工具进行格式转换，例如运行命令 `obabel 1.pdb -O 1.xyz` 即可将1.pdb转换为1.xyz。

---

## 6. xyz文件中原子名与元素名的差异

xyz文件标准应当记录元素名，但若使用VMD打开某些分子动力学程序产生的轨迹并保存为xyz，文件中可能记录的是原子名。这种包含原子名而非元素名的xyz文件往往无法被其他程序正常读取。

---

## 7. 多帧xyz文件在动力学轨迹记录中的局限性

多帧xyz文件可用于记录动力学轨迹，但因格式不够紧凑，记录同样轨迹时文件体积比程序私有格式大很多，载入速度也较慢。因此一般动力学程序不直接支持输出此格式，通常通过VMD等工具转换保存特定帧。

---

## 8. Molclus程序对xyz文件的使用

分子构象与团簇构型搜索程序Molclus中，genmer和gentor模块产生的初始构型与构象均通过多帧xyz格式记录，且程序的运行基于名为traj.xyz的文件。

---

## 9. Multiwfn程序基于xyz的分析功能

Multiwfn支持直接使用xyz格式作为输入进行多种仅需结构信息的分析，包括基于力场的能量分解、Hirshfeld surface分析、IGM分析、基于promolecular密度的NCI分析、分子体积与形状参数计算、HOMA芳香性指数计算及配位数计算等。

---

## 10. xyz2QC工具的应用

xyz2QC工具能够将多帧xyz文件转化为包含多步任务的Gaussian程序输入文件，该工具在利用Gaussian进行势能面扫描的任务中常被使用。

---

## 11. GauIRC2xyz与MOPAC2XYZ工具

GauIRC2xyz工具可将Gaussian计算的IRC轨迹转换为xyz格式，以便利用VMD或CYLView进行分析和动画制作。MOPAC2XYZ工具则可将MOPAC几何优化任务的输出文件转换为多帧xyz文件，用于在VMD中观看优化过程。

---

## 12. Material Studio轨迹转换为xyz

通过特定方法可将Material Studio的xtd轨迹文件导出为xyz轨迹文件。这使得Material Studio用户能够利用VMD程序灵活且强大的功能来分析和处理轨迹。

---

## 13. 常用计算程序对xyz格式的支持

Grimme开发的dftd3、dftd4、xtb等程序均支持以xyz文件作为输入运行。ORCA程序进行几何优化产生的.trj文件实际上就是xyz格式，修改后缀名后即可直接拖入VMD中观看。

---

## 14. extended xyz格式概述

extended xyz是由ASE程序开发者定义的格式，旨在使xyz文件能够记录更多信息。原本支持标准xyz的程序也可以读取extended xyz文件，但无法利用其中额外记录的信息。

---

## 15. extended xyz格式的晶胞信息记录

extended xyz格式通过Lattice标签在第二行记录晶胞信息，顺序为v1x v1y v1z v2x v2y v2z v3x v3y v3z，单位为埃。这解决了标准xyz格式无法记录周期性结构晶胞参数的问题。

---

## 16. extended xyz格式的Properties标签

Properties标签用于定义文件中原子信息的数据类型和列数，例如species:S:1表示species属性为字符串占一列，pos:R:3表示pos属性为浮点数占三列（即坐标）。该格式还可扩展记录原子速度、电荷、半径等信息。

---

## 17. extended xyz格式的自由度与扩展性

extended xyz格式与标准xyz一样为自由格式，数据记录精度无上限。除了Lattice和Properties标签，用户还可以自定义如Time等标签记录帧时间等信息，若标签内容含有空格则需用双引号括住。

---

## 18. Multiwfn对extended xyz的支持

Multiwfn程序从2023年6月14日版本开始支持从extended xyz文件中载入晶胞信息。
