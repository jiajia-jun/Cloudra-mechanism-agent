---
key: b491
title: 考察分子磁感生电流的程序GIMIC 2.0的使用（含24分钟演示视频）
url: http://sobereva.com/491
domain: 其他量化软件
source: blog
year: 2019
cards: 25
---

# 考察分子磁感生电流的程序GIMIC 2.0的使用（含24分钟演示视频） — 知识卡片

## 1. GIMIC程序概述

GIMIC基于量子化学程序输出信息计算分子磁感生电流，主要用于考察芳香性。该程序可输出电流矢量、电流矢量模，并能对穿越特定截面的电流密度进行积分以定量考察电流强度。

---

## 2. GIMIC 2.0新特性

GIMIC 2.0版本已支持结合主流量子化学程序Gaussian进行使用，用法与旧版本有较大差异。

---

## 3. GIMIC依赖环境安装

在CentOS系统中安装GIMIC 2.0需先安装EPEL源、cmake和conda，随后创建并初始化conda环境，最后安装cython、numpy和pyparsing等Python库。

---

## 4. GIMIC编译安装

GIMIC 2.0源码解压后，需运行`./setup --omp`，进入build目录执行`make install`进行编译，并将编译后的bin目录路径添加至系统环境变量PATH中。

---

## 5. GIMIC基本运行命令

运行`gimic test.inp |tee gimic.out`可启动程序并读取test.inp进行运算，信息输出至屏幕及gimic.out文件。若当前目录存在gimic.inp，直接输入`gimic`即可默认读取该文件。

---

## 6. Gaussian闭壳层计算准备

使用Gaussian结合GIMIC 2.0进行闭壳层计算时，需包含`Int=NoBasisTransform IOp(10/33=2) NMR`关键词。计算完成后需将chk文件转换为fchk文件。

---

## 7. Gaussian数据转换脚本

将gimic/tools/g092gimic目录下的BasisSet.py和Gaussian2gimic.py拷至当前目录，运行`./Gaussian2gimic.py --input=test.fchk`可生成GIMIC所需的XDENS和MOL文件。

---

## 8. Gaussian开壳层体系处理

对于开壳层体系，Gaussian计算关键词应包含`gfprint pop=full Int=NoBasisTransform IOp(10/33=2) NMR`。转换数据时需使用log文件作为输入，即运行`./Gaussian2gimic.py --input=test.log`。

---

## 9. 输入文件基本结构

GIMIC输入文件需指定XDENS和MOL文件路径，并设置`openshell`参数（开壳层为true，闭壳层为false）及外磁场方向`magnet`。

---

## 10. 生成格点数据的输入设置

任务类型设为`calc=cdens`可生成格点数据用于可视化。需定义Grid模块，设置格子类型为均匀分布，并指定原点、方向矢量、长度及格点数。

---

## 11. 3D可视化数据输出文件

运行GIMIC的格点数据计算后，将生成acid.vti（ACID函数）、jmod.vti（电流矢量模）和jvec.vti（电流矢量场）文件，这些文件可被ParaView直接读取。

---

## 12. ParaView安装与设置

安装ParaView后需在设置中开启Auto Apply和Enable Auto MPI，并调整鼠标操作习惯使其符合GaussView逻辑。在Manage Plugins中需开启SurfaceLIC、StreamLinesRepresentation等插件的自动加载。

---

## 13. ParaView坐标文件转换

ParaView载入分子结构需使用以Bohr为单位的cml文件。利用OpenBabel将mol.xyz转换为mol.cml后，需通过awk脚本将坐标单位从埃转换为Bohr，生成mol-bohr.cml。

---

## 14. 绘制感生电流模的等值面

在ParaView中载入jmod.vti文件，通过等值面功能可绘制感生电流的模的等值面，分子外围蓝色部分代表diatropic电流，内部红色部分代表paratropic电流。

---

## 15. VMD绘制高质量等值面

利用Multiwfn载入jmod.vti文件并导出为cube文件，随后可使用VMD绘制效果更佳的感生电流模的等值面图。

---

## 16. 绘制感生电流模的截面图

通过在ParaView中设置截面并映射jmod.vti的标量值，可绘制感生电流的模在不同平面的着色图，用以展示特定平面上的电流强度分布。

---

## 17. 绘制ACID等值面与向量场

在ParaView中同时载入acid.vti和jvec.vti，可绘制ACID等值面图并叠加电流向量场，直观展示三维空间中各位置的电流方向。

---

## 18. 绘制感生电流三维流线图

基于jvec.vti数据，在ParaView中可绘制三维流线图以展现环电流路径。流线起点可通过球形范围定义，流线颜色可按矢量模进行着色。

---

## 19. 定量计算截面积分值

将GIMIC输入文件中的任务类型设为`calc=integral`，并在Grid(bond)模块中定义积分截面，可计算穿越特定截面的电流强度积分值，用于定量考察芳香性。

---

## 20. 积分截面参数设置

定义积分截面需通过两个原子序号定义键轴，设置截面距离第一个原子的垂直距离（通常取键长的一半），并指定一个固定点（fixpoint）以唯一确定截面位置。

---

## 21. 积分结果解读

GIMIC输出的积分结果包含总感生电流数值及正负贡献部分，括号内为以nA/T为单位的数值。正值占主导表明diatropic电流较强，体现体系的芳香性。

---

## 22. 环面分子朝向调整

对于非平面环分子，建议使用VMD脚本alignplane将分子环调整至平行于XY平面。在Gaussian计算时必须添加nosymm关键词，防止程序自动改变分子朝向。

---

## 23. 借助Multiwfn确定盒子参数

利用Multiwfn载入fch文件，通过主功能100的子功能1可获取体系坐标范围和格点信息，据此设定GIMIC输入文件中的origin（原点）和lengths（边长）参数。

---

## 24. GIMIC与AICD的对比

GIMIC能提供三维空间中各位置的环电流矢量和模，绘图灵活；AICD则可在等值面上直观标记电场方向。两者在展现环电流角度上互补，无法相互替代。

---

## 25. GIMIC与SYSMOIC的对比

SYSMOIC是另一款考察感生电流的程序，自带可视化功能且使用方便，对键截面积分的处理比GIMIC更为简便。
