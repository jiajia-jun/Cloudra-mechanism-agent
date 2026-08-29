---
key: t41938
title: Quantum ESPRESSO 7.2 GNU��������INTEL�����������簲װ
url: http://bbs.keinsci.com/thread-41938-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 9
---

# Quantum ESPRESSO 7.2 GNU��������INTEL�����������簲װ — 知识卡片

## 1. Quantum ESPRESSO 系统环境与软件版本

软件编译运行的环境为 CentOS Linux release 7.9.2009，所需的构建工具包括 CMake version 3.27.9 和 git version 2.36.6。源码包版本为 q-e-latest.tar.gz（基于 7.2 版本），测试文件使用的是 diamond.zip。

---

## 2. GNU 编译环境下的依赖加载与解压

在 GNU 编译环境下，需依次加载 GCC-9.3.0、IntelMKL-19.0.5 和 OpenMPI-4.1.2 的环境变量脚本，并解压 q-e-latest.tar.gz 源码包。进入 q-e 目录后进行后续配置。
- source ~/scripts/gcc-9.3.0.sh;source ~/scripts/intelmkl-19.0.5.sh;source ~/scripts/openmpi-4.1.2-gcc9.3.0.sh
- tar -xavf q-e-latest.tar.gz
- cd q-e

---

## 3. GNU 环境下 Configure 配置参数

GNU 环境下执行 configure 时，通过 --prefix 指定安装路径为 /home/c7m/apps/qe/7.2/gcc-9.3.0，并使用 --enable-openmp 开启 OpenMP 支持。默认情况下 OpenMP 是关闭的，可通过 ./configure --help 查看所有可用选项。
- ./configure --prefix=/home/c7m/apps/qe/7.2/gcc-9.3.0 --enable-openmp

---

## 4. GNU 环境下核心模块编译命令

执行 make 命令编译核心模块时，指定 96 个并行任务，包含 pw、ph、hp、pwcond 等主要计算程序及部分插件。
- make -j96 pw ph hp pwcond neb pp pwall cp all_currents tddfpt gwl ld1 xspectra couple epw kcw gui

---

## 5. GNU 环境下扩展模块编译与安装

在编译核心模块后，继续编译 gipaw、w90、want、yambo、d3q 等扩展模块，最后执行 install 完成安装。若编译过程出现报错，建议去掉 -j 参数进行单线程编译调试。
- make gipaw w90 want yambo d3q
- make -j96 install

---

## 6. Intel 编译环境下的依赖加载与构建准备

在 Intel 编译环境下，需加载 Intel-19.0.5 的环境脚本，并确认 cmake 和 git 的版本。解压源码包并进入 q-e 目录后，需创建 build 目录作为构建目录。
- source ~/scripts/intel-19.0.5.sh
- cmake --version && git --version
- tar -xavf q-e-latest.tar.gz
- cd q-e
- mkdir build
- cd build

---

## 7. Intel 环境下 CMake 配置参数

使用 CMake 进行配置时，指定 C、C++ 和 Fortran 编译器分别为 icc、icpc 和 mpiifort，并设置编译器参数为 -xCORE-AVX512。安装路径设为 /home/c7m/apps/qe/7.2/intel-19.0.5，同时开启 OpenMP 和 ScaLAPACK 支持。
- cmake .. -DCMAKE_C_COMPILER=icc -DCMAKE_C_FLAGS:STRING=-xCORE-AVX512 -DCMAKE_CXX_COMPILER=icpc -DCMAKE_Fortran_COMPILER=mpiifort -DCMAKE_Fortran_FLAGS:STRING=-xCORE-AVX512 -DQE_ENABLE_OPENMP=ON -DQE_ENABLE_SCALAPACK=ON -DCMAKE_BUILD_TYPE:STRING=RELWITHDEBINFO -DCMAKE_INSTALL_PREFIX=/home/c7m/apps/qe/7.2/intel-19.0.5

---

## 8. Intel 环境下编译与安装

Intel 环境下使用 make 命令并行编译指定目标（如 all_currents, couple, cp, epw 等），随后执行 install 安装。
- make -j96 all_currents couple cp epw gwl hp ld1 neb ph pp pw pwall pwcond tddfpt upf xspectra
- make -j96 install

---

## 9. CentOS 7 系统下升级 Git 版本

CentOS 7 系统下默认 Git 版本较低，可通过安装 IUS 和 EPEL 仓库源来升级至 Git 2.3.6。操作步骤包括安装 rpm 包、移除旧版 git 并安装 git236。
- yum install https://repo.ius.io/ius-release-el7.rpm https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
- yum remove git
- yum install git236
