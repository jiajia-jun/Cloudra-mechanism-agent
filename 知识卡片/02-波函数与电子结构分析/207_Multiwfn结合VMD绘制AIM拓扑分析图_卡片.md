---
id: 207
title: Multiwfn结合VMD绘制AIM拓扑分析图
url: http://sobereva.com/207
domain: 波函数与电子结构分析
topic: Multiwfn结合VMD绘制AIM拓扑分析图
cards: 2
---

# Multiwfn结合VMD绘制AIM拓扑分析图 — 知识卡片

## 1. 推荐使用脚本简化AIM绘图

建议阅读《使用Multiwfn+VMD快速地绘制高质量AIM拓扑分析图》，该文利用脚本将操作过程极大简化，绘制相同效果图像的时间缩短至本文方法的1/20。
- 文献链接：http://sobereva.com/445

## Multiwfn拓扑分析功能概述
Multiwfn的主功能2用于实空间函数的拓扑分析，涵盖电子密度、拉普拉斯函数、ELF、LOL等函数，适用于AIM分析、成键方式及芳香性研究。
- 详细概念及操作介绍见：http://sobereva.com/108

## Multiwfn中生成临界点和键径
在Multiwfn中输入波函数文件，依次选择主功能2、初猜选项2和3，然后选择0查看结果并确认Poincare-Hopf关系满足；选择8生成(3,-3)和(3,-1)临界点间的键径（拓扑路径）。
- 示例输入文件：examples\PhenolDimer.wfn

## Multiwfn临界点颜色对应规则
在Multiwfn图形窗口中，紫/橙/黄/绿小球分别代表核临界点/键临界点/环临界点/笼临界点；勾选"Paths labels"可显示每条键径的序号。

## 导出临界点为PDB文件
在Multiwfn拓扑分析界面选-4进入修改/导出界面，再选6将临界点导出为当前目录下的CPs.pdb文件；不同元素原子对应不同类型临界点，碳/氮/氧/氟分别对应(3,-3)/(3,-1)/(3,+1)/(3,+3)。

## 导出拓扑路径为PDB文件
在Multiwfn拓扑分析主菜单选-5进入路径界面，再选6将拓扑路径导出为当前目录下的paths.pdb文件；路径由一连串紧挨着的点表示，对应文件中的碳原子，残基编号对应路径编号。

## VMD中显示(3,-3)核临界点
在VMD中加载CPs.pdb，通过Graphics-Representation设置：Selected Atoms输入name C，Drawing Method选Points，Coloring Method选ColorID并指定紫色，调整Size参数。
- 示例Size值：11或20

## VMD中显示其他类型临界点
在VMD中新建显示方式，分别输入name N（对应(3,-1)键临界点）、name O（对应(3,+1)环临界点）、name F（对应(3,+3)笼临界点），并分别设置颜色和尺寸。

## VMD中显示拓扑路径（键径）
在VMD中加载paths.pdb，确认Selected Molecule切换为paths.pdb；在Graphics-Representation中设置Drawing Method为Points，Size为1，颜色设为青色。

## VMD中区分分子间与分子内键径
根据本文第一张图确定分子间键径编号（如35 36 55 56 49 50），在Selected Atoms输入all not resid [编号]来仅显示分子内键径；新建显示方式并输入resid [编号]来单独显示分子间键径（可设为红色）。

## 使用Tcl命令调整VDW显示半径
在VMD中开启File - Log Tcl Commands to Console记录命令，获取如mol modstyle 0 0 VDW 0.200000 12.000000的指令；修改其中的半径值（如0.2改为0.02）并在控制台执行，可实现比界面最小值更小的VDW半径显示。
- 示例命令：mol modstyle 0 0 VDW 0.02 12.000000

## 结合CPK模型与键径研究分子间相互作用
将体系结构以CPK方式显示以遮盖化学键键径，仅保留分子间相互作用键径；临界点也可用VDW方式显示（Sphere Scale设为0.07），结构文件可通过Multiwfn主功能100子功能2导出。

## 结合RDG等值面与AIM图
在VMD中可以将RDG填色等值面图与临界点、键径图同时显示，以更丰富地展现弱相互作用信息；相关绘制方法见Multiwfn手册3.22.1节和4.20.1节。

---

## 2. Multiwfn与VMD结合绘图的其他应用

Multiwfn导出数据结合VMD绘图的例子包括《通过键级曲线和ELF/LOL/RDG等值面动画研究化学反应过程》和《使用Multiwfn结合VMD分析和绘制分子表面静电势分布》。
- 文献链接：http://sobereva.com/200
- 文献链接：http://sobereva.com/196
