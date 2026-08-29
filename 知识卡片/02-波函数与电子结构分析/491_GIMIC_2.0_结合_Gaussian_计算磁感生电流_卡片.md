---
id: 491
title: 考察分子磁感生电流的程序GIMIC 2.0的使用（含24分钟演示视频）
domain: 波函数与电子结构分析
topic: GIMIC_2.0_结合_Gaussian_计算磁感生电流
cards: 14
---

## 1. GIMIC 2.0简介与主要用途
GIMIC主要用于基于量子化学程序的输出信息计算分子的磁感生电流，这对考察芳香性尤为重要。GIMIC可以给出电流矢量、电流矢量的模，还可以对穿越特定截面的电流密度进行积分来定量考察电流的强度。GIMIC 2.0版本已可以结合主流的量子化学程序Gaussian使用。

---

## 2. GIMIC 2.0在CentOS系统下的安装步骤
在CentOS 7.6系统中依次运行命令安装依赖：`yum install epel-release`、`yum install cmake`、`yum install conda`。创建并初始化conda环境：`conda create --name myconda`、`conda init bash`。在~/.bashrc末尾加入`conda activate myconda`。重新进入终端后安装Python库：`conda install cython numpy pyparsing`。解压GIMIC源码包，进入目录运行`./setup --omp`、`cd build`、`make install`。最后在~/.bashrc末尾加入`export PATH=$PATH:/sob/gimic/build/bin`。

---

## 3. GIMIC 2.0的基本运行命令
运行`gimic test.inp |tee gimic.out`可启动程序读取test.inp进行运算，信息输出到gimic.out并显示在屏幕上。如果当前目录下有名为gimic.inp的文件，直接输入`gimic`即可计算，程序将其视为默认输入文件。

---

## 4. 使用Gaussian生成GIMIC所需的输入文件
对于Gaussian09，运行包含`# B3LYP/6-311G* Int=NoBasisTransform IOp(10/33=2) NMR`关键词的任务，将chk文件转换为fchk文件。将gimic/tools/g092gimic目录下的BasisSet.py和Gaussian2gimic.py拷到当前目录，运行`./Gaussian2gimic.py --input=test.fchk`，即可生成XDENS和MOL文件。如果是开壳层体系，关键词应使用`gfprint pop=full Int=NoBasisTransform IOp(10/33=2) NMR`，并用Gaussian2gimic.py处理log文件。

---

## 5. ParaView的下载、安装与设置
ParaView是用于可视化GIMIC结果的体数据可视化程序，可在官网免费下载。安装后进入Edit - Setting，点击齿轮图标，勾选Auto Apply和Enable Auto MPI，Auto MPILimit设为实际物理核数。在Camera标签页将左键、中键、右键分别设为Rotate、Pan、Roll。在Tools - Manage Plugins里展开SurfaceLIC、StreamLinesRepresentation、StreamingParticles，开启Auto Load并重启ParaView。

---

## 6. GIMIC产生ParaView绘图所需文件的输入文件设置
输入文件应设置calc=cdens以产生格点数据，指定basis和xdens路径，设置magnet外磁场方向。Grid部分需定义type=even、origin原点坐标、ivec和jvec方向矢量、lengths边长及grid_points格点数。Advanced部分必须设置spherical=off，diamag和paramag设为on。Essential部分开启acid和jmod以输出相应的vti文件。

---

## 7. GIMIC输出的主要文件及分子结构CML文件的生成
GIMIC运算完成后会生成mol.xyz（分子结构）、grid.xyz（带盒子顶点的结构）、acid.vti（ACID函数数据）、jmod.vti（电流矢量模）、jvec.vti（电流矢量）。为了在ParaView中正确显示分子结构，需使用OpenBabel将mol.xyz转换为mol.cml，并利用awk脚本将坐标单位转换为Bohr，生成mol-bohr.cml文件。

---

## 8. 使用Multiwfn辅助确定盒子参数
利用Multiwfn载入fch/fchk文件，依次输入5、100、1，屏幕会显示盒子原点坐标和终点坐标及格点间距。根据这些信息可以确定GIMIC输入文件中合适的origin（原点）和lengths（边长）参数。

---

## 9. 绘制感生电流的模的等值面
基于GIMIC输出的jmod.vti文件，可以在ParaView中绘制感生电流的模的等值面。分子外围蓝色部分是diatropic电流的等值面（等值面数值为0.05），内部红色部分是paratropic电流的等值面（等值面数值为-0.05）。也可以通过Multiwfn将jmod.vti转换为cube文件，再用VMD绘制效果更佳的等值面图。

---

## 10. 绘制ACID等值面图与向量场图
基于acid.vti和jvec.vti文件，可以在ParaView中同时绘制ACID等值面图和电流向量场图。这种图可以展现整个三维空间中各个位置的电流方向，配合ACID等值面可以更清晰地观察在分子平面上方、下方以及外围的diatropic电流情况。

---

## 11. 绘制感生电流的三维流线图
基于jvec.vti文件，在ParaView中可以绘制感生电流的三维流线图。流线图的起点通过设置球形范围定义，球形位置、半径、流线长度和方向均可调节。流线根据矢量的模着色，能够清晰展现环电流的路径。将Integration Direction设置为FORWARD或BACKWARD可以生成单一方向的流线。

---

## 12. 计算穿越特定截面的电流积分值的输入文件设置
进行截面积分计算时，输入文件需设置calc=integral。Grid(bond)部分需设置type=gauss、gauss_order=9、bond定义键轴原子、distance（截面距离第一个原子的距离）、fixpoint（固定点原子序号）、grid_points（截面上两个方向的点数）、height和width（截面的延展距离）。Advanced部分需设置lip_order=5，spherical=off，diamag=on，paramag=on。

---

## 13. 电流积分结果的解读与注意事项
GIMIC输出结果包含感生电流数值（单位au和nA/T，转换因子为28.179409），以及正、负贡献部分。环电流积分的正负号取决于键轴定义的方向，若交换bond中的原子顺序，积分值符号会改变。积分值为正说明diatropic电流占主导，体现芳香性。每次积分后应检查生成的grid.xyz以确认截面位置设置正确。

---

## 14. GIMIC与AICD及SYSMOIC的比较
GIMIC的优点是可以给出三维空间中各个位置的环电流矢量和模，结合ParaView绘图灵活且美观；缺点是无法将环电流分解为不同轨道（如sigma和pi）的贡献。AICD可以标记AICD等值面上的电场方向箭头，且方便考察非平面体系，二者高度互补。SYSMOIC自带可视化功能，使用方便，且在键截面上做感生电流积分比GIMIC更方便。
