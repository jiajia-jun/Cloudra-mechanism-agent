---
id: 195
title: 宇宙学模拟程序GADGET 2.0.7安装方法
domain: 软件安装与环境
topic: 宇宙学模拟程序GADGET_2.0.7编译安装
cards: 10
---

## 1. GADGET-2程序简介
GADGET-2 (GAlaxies with Dark matter and Gas intEracT) 是基于多体方法和光滑粒子流体动力学(SPH)的宇宙学模拟程序，可以模拟银河间相互作用及宇宙大尺度结构形成。该程序由Volker Springel教授开发，使用C语言编写并利用MPI实现并行，开源免费，出处见Mon. Not. R. Astron. Soc. 364, 1105–1134 (2005)。

---

## 2. 安装MPI库
即便只进行串行计算，GADGET-2也需要安装MPI库，此处下载mpich2-1.4.1p1.tar.gz。在解压后的目录下依次运行 `./configure`、`make`、`make install` 完成安装，安装完成后可删除源码目录。

---

## 3. 安装GNU scientific library (GSL)
下载gsl-1.9.tar.gz解压，在目录下运行 `./configure CC=icc` 指定编译器，随后运行 `make` 和 `make install`，安装完成后可删除源码目录。

---

## 4. 安装FFTW快速傅里叶变换库
GADGET-2需要FFTW2系列而非最新版FFTW3，建议使用最后一个FFTW2系列版本2.1.5。下载fftw-2.1.5.tar.gz后，运行 `./configure --enable-mpi --enable-type-prefix --enable-float --prefix=/sob/fftw215`，随后执行 `make` 和 `make install`，库将被安装到/sob/fftw215下。

---

## 5. GADGET-2 Makefile配置步骤
打开/sob/Gadget-2.0.7/Gadget2/Makefile，注释掉 `OPT += -DHAVE_HDF5` 和 `OPT += -DPMGRID=128`；若不需要周期边界条件则注释掉 `OPT += -DPERIODIC`。将ifeq ($(SYSTYPE),"MPA")至endif之间的内容修改为特定编译器、路径及优化选项配置。

---

## 7. 编译GADGET-2及环境变量设置
保存Makefile后，在/sob/Gadget-2.0.7/Gadget2/目录下运行 `make` 生成可执行文件Gadget2。需将 `export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib` 加入当前用户的.bashrc文件并运行bash命令使之生效，除非该路径已在环境变量中。

---

## 8. 运行GADGET-2自带的银河碰撞测试
进入Gadget-2.0.7目录，创建galaxy目录并复制参数文件：运行 mkdir galaxy、cp Gadget2/parameterfiles/galaxy.param galaxy/。使用命令 mpirun -np 4./Gadget2/Gadget2 galaxy/galaxy.param 启动测试，其中-np 4 根据实际计算条件调整，直接调用Gadget2则进行串行计算。

---

## 9. GADGET-2输出文件说明
模拟过程中会在输出目录下生成各种文件，其中snapshot_xxx文件类似于分子动力学程序中的轨迹帧，记录了特定时刻的数据，可用于后续可视化分析。

---

## 10. 安装SPLASH可视化工具
先运行 `locate cairo.h` 检查系统，若未找到则运行 `yum install cario-devel` 安装Cairo库。下载splash-2.2.2.tar.gz解压，进入目录运行 `make SYSTEM=ifort` 和 `make install`。

---

## 11. 使用SPLASH可视化GADGET-2结果
编译SPLASH会产生多个可执行文件，其中 `gsplash` 是专门用于GADGET-2的工具。使用 `gsplash` 载入GADGET-2输出的snapshot_xxx文件即可进行可视化分析。
