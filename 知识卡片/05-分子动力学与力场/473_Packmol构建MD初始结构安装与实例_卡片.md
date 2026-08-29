---
id: 473
title: 分子动力学初始结构构建程序Packmol的使用
domain: 分子动力学与力场
topic: Packmol构建MD初始结构安装与实例
cards: 24
---

## 1. Packmol简介与功能
Packmol 是一款流行的构建分子动力学模拟初始结构的免费工具，通过优化算法将指定数目的分子堆积到满足约束条件的区域中，且保持分子结构刚性。该程序仅考虑空间因素，不考虑能量和电荷分布，产生的结构可用于 GROMACS、AMBER 等主流 MD 程序。网站提供源代码、预编译版本及示例。

---

## 2. Linux下Packmol的编译
在Linux下编译Packmol需要先安装Fortran编译器（如通过yum install gfortran安装），解压源码包后在目录下输入make命令即可编译。编译完成后会生成名为packmol的可执行文件。

---

## 3. Linux下Packmol的环境变量配置
编译完成后需修改用户目录下的.bashrc文件，在末尾添加export PATH=$PATH:/目录路径（如/sob/packmol-18.169）以配置环境变量。保存后重新进入终端，输入packmol命令检查是否能正常启动。

---

## 4. Windows下Packmol的获取与运行
Windows下应直接下载官网提供的64位预编译可执行文件，无需自行编译。在cmd命令行环境下输入packmol < test.inp命令运行，若可执行文件不在当前目录则需使用绝对路径或将其加入Path环境变量。程序不支持双击图标运行。

---

## 5. Packmol运行命令格式
Packmol通过命令行运行，使用格式为packmol < 输入文件名（例如packmol < test.inp）。输出文件将生成在当前目录下。

---

## 6. Packmol输入文件要求
使用Packmol需要提供两类文件：输入文件（定义分子分布和数量，文件名随意）和分子结构文件（一般使用pdb格式）。输入文件中的关键词详情可在官网用户指南中查阅。

---

## 7. Packmol全局设定tolerance与output
全局设定中，tolerance [数值]用于规定原子间最小距离，单位为埃，一般设为2.0；output [文件名]用于指定输出文件的路径。

---

## 8. Packmol全局设定filetype、seed与add_box_sides
全局设定中，filetype [类型]定义输出文件格式（默认为pdb）；seed -1设定每次运行产生不同结构；add_box_sides [数值]在输出pdb中增加CRYST1字段定义盒子，盒子尺寸对应原子最大最小坐标，并可额外增加指定埃数的边长。

---

## 9. Packmol分子设定基本语法
分子设定使用structure字段定义一种分子的分布，基本格式为：structure [分子结构文件]、number [分子数]、[分子规则]、end structure。输入文件中可包含无数个此类字段。

---

## 10. Packmol分子空间范围设定inside
分子规则中inside关键词可用于限制分子出现的空间范围，包括inside cube [xmin ymin zmin d]（立方体）、inside box [xmin ymin zmin xmax ymax zmax]（矩形盒子）、inside sphere [x y z r]（圆球）以及inside cylinder（圆柱）。inside可替换为outside以表示排除区域。

---

## 11. Packmol分子位置平面约束与旋转限制
分子规则中，over plane [a b c d]要求分子位置满足ax+by+cz-d>=0（可用below反转）；constrain_rotation [x/y/z 平均值 最大偏差]用于限制分子绕特定轴的旋转角度，如constrain_rotation x 20 5表示绕x轴旋转范围在15~25度之间。

---

## 12. Packmol分子固定位置设定
使用fixed [x y z a b c]可以直接定义分子的位置和朝向，表示将分子坐标平移并绕x,y,z轴旋转指定弧度。若配合center关键词，则表示将分子中心置于指定坐标后再旋转。

---

## 13. Packmol原子设定语法
Packmol允许对特定原子设定约束，格式为在structure字段内添加atoms [原子序号]、[原子规则]、end atoms。原子规则的语法和关键词与分子规则完全一致，且可对多批原子分别设定。

---

## 14. Packmol构建甲醇盒子实例
构建5*5*5 nm^3甲醇盒子的输入文件需设置tolerance 2.0、add_box_sides 1.2，并将1000个甲醇分子置于边长50埃的立方体内（inside cube 0. 0. 0. 50.）。运行后可用VMD查看，若想更致密可逐步增加分子数直至产生失败。

---

## 15. Packmol构建气液界面体系实例
构建水+甲醇（1:1）气液界面体系时，先用Packmol构建4*4*5 nm^3的溶液盒，再在VMD中将盒子Z方向设为11nm并利用moveby命令将溶液层沿Z轴平移3nm至中间。若后续模拟中溶液层厚度偏离预期，可适当增加分子数或调整Z方向盒子大小。

---

## 16. Packmol构建溶剂球+富勒烯实例
构建半径1.5nm的溶剂球（氯仿和甲醇各占半球）且中心固定富勒烯时，可利用inside sphere限制溶剂分子在球内，利用inside box分隔上下半球。富勒烯使用center和fixed [20. 20. 20. 0. 0. 0.]定位于球心（单位埃），此孤立体系不使用add_box_sides。

---

## 17. Packmol构建水球+表面活性剂实例
构建水球+SDS'体系时，利用atoms设定约束SDS'的头部（如钠离子）在距离中心15埃以内，尾部末端碳原子在距离中心30埃以外。由于原子间距略大于范围差，此设定可使SDS'链垂直于水球界面分布，形成海胆状结构。

---

## 18. Packmol建模的约束与收敛问题
Packmol通过循环尝试堆积结构，约束条件越复杂或越矛盾，循环次数和耗时越高，甚至无法收敛。若出现反复循环或失败，应适当放宽、简化约束条件或减少分子数。

---

## 19. Packmol构建体系的密度与模拟建议
Packmol构建的体系通常比较松散，密度显著低于真实密度，应先在NPT系综下进行MD模拟以调节盒子尺寸。直接用Packmol结构做NVT模拟通常无意义，因为分子会自发紧密聚集导致产生真空区。

---

## 20. 蛋白质/核酸溶剂化建议
虽然可用Packmol为蛋白质/核酸加溶剂，但因其产生的水密度偏低、分布与体相水差别大，可能导致NPT模拟后盒子剧烈收缩。建议使用GROMACS自带的gmx solvate命令，利用预平衡的溶剂盒（如spc216.gro）填充，效果更理想。

---

## 21. GROMACS insert-molecules与Packmol对比
GROMACS的gmx insert-molecules命令功能远不如Packmol灵活，且在相同盒子范围内，Packmol通过优化算法能插入更多分子，得到更紧凑的结构。gmx insert-molecules在分子数过多时只能插入部分分子。

---

## 22. 磷脂膜与膜蛋白建模建议
Packmol虽然可以构建磷脂双分子膜或膜蛋白体系，但设置复杂、耗时且结果常有空隙。构建磷脂膜推荐使用genmixmem程序，膜蛋白推荐使用GROMACS的membed方法。

---

## 23. 团簇初始构型工具推荐
若建模目的是分子团簇用于构型搜索，推荐使用genmer工具而非Packmol。genmer一次可产生大量构型，且输入文件更简便。

---

## 24. GROMACS拓扑文件与结构文件原子顺序匹配
若使用Packmol建模后用GROMACS模拟，必须保证结构文件中的原子顺序与拓扑文件[molecules]字段展开后的顺序一致。为此，用于Packmol的分子结构文件中的原子顺序必须预先与拓扑信息[atoms]字段对应。
