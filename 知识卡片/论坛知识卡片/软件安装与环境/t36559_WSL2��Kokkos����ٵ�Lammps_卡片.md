---
key: t36559
title: WSL2��Kokkos����ٵ�Lammps��cmake����
url: http://bbs.keinsci.com/thread-36559-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 9
---

# WSL2��Kokkos����ٵ�Lammps��cmake���� — 知识卡片

## 1. ReaxFF在LAMMPS中使用GPU加速的要求

ReaxFF反应力场在LAMMPS中启用GPU加速需要安装和配置Kokkos库。

---

## 2. 系统环境配置

构建环境可采用Win11系统下的WSL2，其中运行Ubuntu 18.04.5。
显卡驱动需在Windows宿主系统中先行安装，并禁用WSL、VM及Hyper-V相关冲突。

---

## 3. 基础编译工具安装

Ubuntu系统需安装基础编译工具及依赖库，包括gcc、g++、gfortran、libfftw3*和mpi-default-*。
安装命令为：`sudo apt-get install gcc`、`sudo apt-get install g++`、`sudo apt-get install gfortran`、`sudo apt-get install libfftw3*`、`sudo apt-get install mpi-default-*`。

---

## 4. CMake手动安装步骤

需手动安装cmake-3.21.5版本，默认安装位置为/usr/local。
安装步骤包括解压源码、执行`./configure`、`make`及`make install`。
安装前需执行`sudo apt-get -y install libssl-dev`。

---

## 5. CUDA Toolkit安装与配置

需下载并安装适用于WSL-Ubuntu的CUDA Toolkit（示例版本为12.1.0）。
安装涉及下载pin文件、移动至指定目录、安装deb包及更新apt。
环境变量配置需添加PATH和LD_LIBRARY_PATH，指向/usr/local/cuda-12.0/bin和/usr/local/cuda-12.0/lib64。
安装后若出现optix或libcuda.so.1符号链接错误可忽略，不影响ReaxFF计算资源使用。

---

## 6. LAMMPS源码准备与构建目录

下载LAMMPS稳定版源码包lammps-stable.tar.gz。
需创建独立的构建目录build-kokkos-cuda并进入该目录。

---

## 7. LAMMPS CMake预设配置

执行CMake配置时需加载基础和Kokkos CUDA预设文件。
命令为：`cmake -C ../cmake/presets/basic.cmake -C ../cmake/presets/kokkos-cuda.cmake ../cmake`。
需修改kokkos-cuda.cmake文件中的架构设置（如MAXWELL50）以匹配实际显卡的Arch-ID。

---

## 8. LAMMPS编译参数与包启用

编译时需启用MPI及大量功能包，包括PKG_REAXFF、PKG_KSPACE、PKG_MOLECULE等。
GPU相关参数设置为-D GPU_API=cuda -D GPU_ARCH=sm_75（需根据显卡调整）。
完整编译命令包含大量的`-D PKG_XXX=on`参数以开启相应支持。

---

## 9. LAMMPS编译与执行

执行`make -j 24`进行多线程编译。
编译完成后生成lmp可执行文件。
运行ReaxFF计算需使用Kokkos加速选项，命令示例为：`lmp -in in.RDX -k on g 1 -sf kk -pk kokkos neigh half newton on`。
