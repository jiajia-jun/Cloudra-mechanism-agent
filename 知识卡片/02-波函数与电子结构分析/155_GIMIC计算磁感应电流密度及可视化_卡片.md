---
id: 155
title: 使用GIMIC计算和分析磁感应电流密度
url: http://sobereva.com/155
domain: 波函数与电子结构分析
topic: GIMIC计算磁感应电流密度及可视化
cards: 22
---

# GIMIC计算磁感应电流密度及可视化 — 知识卡片

## 1. GIMIC程序的现状与适用性

GIMIC程序用于计算和分析磁感应电流密度，基于GIAO方法并利用磁性质计算产生的密度矩阵及其导数矩阵。相比AICD程序，GIMIC支持任何使用GIAO方法计算磁性质的量子化学程序（如CFOUR、Turbomole），能直接输出格点数据便于后续分析，且使用GIAO方法使基组收敛速度优于CSGT方法。GIMIC方法的原文见JCP,121,3952，综述见PCCP,13,20500。

---

## 2. GIMIC支持的计算程序

GIMIC原则上支持任何使用GIAO方法计算磁性质的量子化学程序，但目前版本仅支持CFOUR、ACESII和Turbomole程序。CFOUR是免费开源的，支持HF及高精度耦合簇级别但不支持DFT；ACESII支持DFT但难以使用；Turbomole为商业软件。

---

## 3. GIMIC的输出功能

GIMIC可以输出空间范围或指定平面上均匀分布格点上的电子密度、电流密度及其模和散度，也可以输出自定义批点上的这些性质。此外，GIMIC还能对电流密度在指定平面上做积分，得到穿过相邻两个原子的净电流。

---

## 4. 磁性质计算中的规范不变性问题

在磁性质计算中，矢量势A与规范原点R_o的选取在有限基组下会影响计算结果，需满足“规范不变性”。GIAO方法在高斯函数中引入复数因子，使计算结果不依赖于测量原点选择，是绝大多数量化程序默认的方法。CSGT方法结果随基组收敛速度比GIAO慢。

---

## 5. GIMIC代码修改：cubeplot.f90

需修改cubeplot.f90以生成标准cube文件：将输出循环改为每行写6个数据且格式为1PE13.5，将第35行的0改为1，并在第38行后添加写入氢原子坐标信息的代码`write(fd,"(i5,4f12.6)") 1,1D0,0D0,0D0,0D0`。

---

## 6. GIMIC代码修改：jfield.f

需修改jfield.f以符合标准cube格式：在第610行后添加换行逻辑代码，搜索`write(fd, '(i5,3f12.6)') 0, origin`将0改为1，并在`write(fd, '(i5,3f12.6)') npts(3), 0.d0, 0.d0, step(3)`后添加`write(fd,"(i5,4f12.6)") 1,1D0,0D0,0D0,0D0`。

---

## 7. GIMIC代码修改：gimic.in

需在gimic.in文件中将`print "Error: either spacing or grid_points must be specified"`这一行后面的`sys.exit(1)`删除，否则无法计算自定义批点上的电流密度。

---

## 8. 编译GIMIC的前提与步骤

编译GIMIC前需确保CFOUR已编译并带有`--enable-gimic`选项以生成xcpdens程序。编译GIMIC时运行`./configure FC=ifort`，注释Makefile中的`INST_PROGS+=xcpdens`，执行`make`生成gimic.x，修改工具脚本中的路径，最后运行`make install`并拷贝脚本到bin目录。

---

## 9. 运行GIMIC所需的文件

运行GIMIC需要三个文件：包含分子坐标和基组信息的mol文件、包含密度矩阵及其导数的XDENS文件、以及设定关键词的gimic.inp输入文件。

---

## 10. 使用CFOUR生成GIMIC输入文件

建立CFOUR输入文件ZMAT，必须设定`SYMMETRY=ON`。运行`xgimic2.sh --scf`（微扰用`--mbpt`，耦合簇用`--cc`）生成XDENS文件。然后运行`MOL2mol.sh`生成无对称性的mol文件。

---

## 11. GIMIC输入文件的全局设定

gimic.inp文件中一般需要自行设置`openshell`（是否开壳层）和`calc`（任务列表）。calc可选任务包括：cdens（计算格点电流密度）、divj（计算电流密度散度）、edens（计算电子密度）、integral（计算平面电流积分）。

---

## 12. GIMIC格点设定参数

在grid(base) {...}段落中设定格点分布：`origin`设定格点原点，`ivec`和`jvec`设定格点的前两个方向向量，`lengths`设定三个方向的总长度，`spacing`设定格点间距，`grid_points`设定格点数（spacing与grid_points只能设其一）。

---

## 13. GIMIC积分任务参数设定

integral任务需设定磁场矢量`magnet`和`spin`。在grid(bond) {...}中设定积分平面：通过`bond=[1,2]`或`coord1/coord2`确定两点连线及平面垂直方向，`distance`设定平面距离第一点的垂直距离，`up/down/in/out`设定平面范围，`grid_points`设定积分点密度。

---

## 14. GIMIC输出文件：jmod.cube与jmod_quasi.cube

`jmod.cube`记录感应电流密度的模，是diatropic和paratropic模的总和，恒为正值。`jmod_quasi.cube`将diatropic和paratropic感应电流密度的模分别用正值和负值记录。

---

## 15. 电流密度模的可视化分析

使用VMD加载`jmod_quasi.cube`，设置两个显示方式：isovalue为0.05显示蓝色（正值，diatropic电流），isovalue为-0.05显示红色（负值，paratropic电流）。蓝色区域出现在苯环中部和外侧，由sigma轨道外侧部分和pi轨道贡献；红色区域在苯环内侧，由sigma轨道内侧部分产生。

---

## 16. 指定平面电流密度向量图的绘制

`JVEC.txt`包含指定平面各点的xyz坐标及电流密度矢量分量。在Sigmaplot中导入文件，运行变换`col(7)=col(1)+2*col(4)`和`col(8)=col(2)+2*col(5)`计算向量末端坐标（乘以2为放大显示），使用Vector Plot (XYXY) 绘制。

---

## 17. 苯分子平面电流密度向量图分析

在苯分子平面上，C-C键、C-H键及碳原子核区域出现局部diatropic环流。整体上，苯环内侧感应电流逆时针，外侧顺时针，这是局部环流组合的结果。sigma电子的diatropic和paratropic环电流在环内外互相抵消，无法形成整体净环流。

---

## 18. 苯分子环上方平面的电流密度

将origin设为`[-8.0, -8.0, 1.8896]`（即平面上1埃）可绘制pi电子效应图。此时形成整体diatropic环流，表明苯环的环电流由diatropic主导，因此苯是芳香性分子。若paratropic主导则为反芳香性，若两者抵消则为非芳香性。

---

## 19. 电流密度散度图绘制与分析

`DIVJPLT`文件包含平面上的电流密度散度数据。在Sigmaplot中导入，取散度绝对值绘制Filled Contour图。散度为0的区域（如sigma键环流中心）电流无发散或收缩趋势，核附近散度极大（像旋转洒水机）。

---

## 20. 积分任务的输出与解读

integral任务输出屏幕信息显示净电流（au和nA/T）、正值贡献（diatropic）和负值贡献（paratropic）。以苯C1-C2键为例，净电流为0.461991 a.u. (13.018629 nA/T)，转换因子为28.179409。

---

## 21. 积分任务的几何可视化

integral任务输出`integral.xyz`文件，包含分子结构及用4个X原子标出的积分平面区域。在VMD中连接X原子可查看积分平面框。

---

## 22. 自定义数据点位置的设置

若要在自定义位置计算数据，需编辑一个文本文件（如extgrd）记录坐标（Bohr），并在gimic.inp中将原格点设定替换为`grid(file) { file=extgrd }`。输出文件如JVEC.txt将记录这些位置的值。
