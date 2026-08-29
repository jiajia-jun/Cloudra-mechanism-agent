---
id: 207
title: Multiwfn结合VMD绘制AIM拓扑分析图
url: http://sobereva.com/207
domain: 波函数与电子结构分析
topic: Multiwfn结合VMD绘制AIM拓扑分析图
cards: 15
---
## 1. Multiwfn与VMD结合绘制AIM图的简化脚本

建议先阅读《使用Multiwfn+VMD快速地绘制高质量AIM拓扑分析图》，该资料通过脚本极大简化了操作过程，仅需不到前者1/20的时间即可绘制出相同效果的图像，文章链接为http://原作者.com/445。

---



---

## 2. Multiwfn中实空间函数的拓扑分析

电子密度及其拉普拉斯函数的拓扑分析是AIM分析的核心，ELF、LOL的拓扑分析在分析成键方式、芳香性等问题上也有重要应用，这些在Multiwfn中均可通过主功能2实现。

---

## 3. Multiwfn拓扑分析的基本概念与操作参考

关于实空间函数拓扑分析的基本概念和在Multiwfn里的操作细节，可参考文章《使用Multiwfn做拓扑分析以及计算孤对电子角度》，链接为http://原作者.com/108。

---



---

## 4. 在Multiwfn中搜索临界点并生成键径

启动Multiwfn后依次输入examples\PhenolDimer.wfn、2（主功能2）、2（以原子核位置作为初猜）、3（以每两个原子的中点作为初猜）、0（查看结果），确认找全临界点且Poincare-Hopf关系满足后，选8生成(3,-3)和(3,-1)临界点之间的键径。

---

## 5. 在Multiwfn中导出临界点为PDB文件

在Multiwfn中选-4进入临界点修改/导出界面，然后选6 Export CPs as pdb file in current folder，临界点即被导出到当前目录下的CPs.pdb中。

---

## 6. PDB文件中原子类型与临界点类型的对应关系

在导出的CPs.pdb文件中，不同元素的原子对应不同类型的临界点，其中碳/氮/氧/氟原子分别对应(3,-3)/(3,-1)/(3,+1)/(3,+3)临界点。

---

## 7. 在Multiwfn中导出拓扑路径为PDB文件

选0退回到拓扑分析主菜单，进入选项-5，选6 Export paths as paths.pdb file in current folder，拓扑路径即被导出到当前目录下的path.pdb中，路径由一连串紧挨着的点表示。

---

## 8. paths.pdb文件中残基编号的含义

在导出的path.pdb文件中，构成键径的点对应于一个个碳原子，每个原子所属残基编号对应于拓扑路径的编号。

---

## 9. 在VMD中显示不同类型的临界点

将CPs.pdb拖入VMD，通过Graphics-Representation修改显示方式：(3,-3)选name C用紫色显示，(3,-1)选name N，(3,+1)选name O，(3,+3)选name F，可分别设置Drawing Method为Points并调整Size和ColorID。

---

## 10. 在VMD中显示键径

将paths.pdb拖入VMD Main窗口，在Graphics-Representation中确认Selected Molecule已切换至paths.pdb，将Drawing Method改为Points，Size改为1，颜色改为青色。

---

## 11. 在VMD中区分显示分子内与分子间键径

为区分键径，可在Selected atoms框中通过resid筛选，例如输入all not resid 35 36 55 56 49 50仅显示分子内键径，再创建新Representation并设为resid 35 36 55 56 49 50以特定颜色显示分子间键径。

---

## 12. 通过VMD命令行调整键径显示质感

在VMD中选File - Log Tcl Commands to Console，修改Sphere Scale获取命令格式如mol modstyle 0 0 VDW 0.200000 12.000000，将数值改为0.02等小值并粘贴回文本窗口，可将键径Drawing Method设为VDW且使Sphere Scale小于界面最小值0.1。

---

## 13. 结合CPK模式考察分子间相互作用

将体系结构以CPK方式显示（PDB结构文件可通过Multiwfn主功能100子功能2导出），可遮盖住化学键的键径，从而只显示分子间相互作用的键径。

---

## 14. RDG填色等值面与AIM图的结合

在VMD中可将RDG填色等值面图和临界点、键径图显示在一起以丰富弱相互作用信息，RDG填色等值面介绍见Multiwfn手册3.22.1节，绘制RDG+AIM图的例子见手册4.20.1节。

---

## 15. Multiwfn与VMD结合绘图的扩展案例

其他Multiwfn与VMD结合绘图的例子包括《通过键级曲线和ELF/LOL/RDG等值面动画研究化学反应过程》（http://原作者.com/200）和《使用Multiwfn结合VMD分析和绘制分子表面静电势分布》（http://原作者.com/196）。
