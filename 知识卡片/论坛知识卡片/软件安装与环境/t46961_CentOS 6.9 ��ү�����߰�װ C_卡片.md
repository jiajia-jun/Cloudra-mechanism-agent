---
key: t46961
title: CentOS 6.9 ��ү�����߰�װ CP2K 2024.1
url: http://bbs.keinsci.com/thread-46961-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 7
---

# CentOS 6.9 ��ү�����߰�װ CP2K 2024.1 — 知识卡片

## 1. CentOS 6.9 编译 CP2K 的环境准备

CentOS 6.9 自带的 yum 源中 gcc 版本较低，需要通过 devtoolset 安装较高版本的 gcc。可在联网环境下利用 yum downloadonly 下载 devtoolset 的 rpm 包，再拷贝至离线环境进行安装，通过该办法成功安装了 gcc 9.1.1。

---

## 2. CP2K 2024.1 源码依赖处理

在编译 CP2K-2024.1 时，进入 toolchain/build 目录需要安装的软件包包括 gcc-13.2.0。将 gcc-13.2.0.tar.gz 解压并运行 ./contrib/download_prerequisites 下载必备依赖，随后重新打包该文件，放置于 CP2K 2024.1 档案中的指定位置。

---

## 3. glibc 与 CMake 版本限制

CentOS 6.9 系统自带的 glibc 版本过低，若使用 --with-cmake=install 选项会导致安装失败。需在外部环境预先编译并安装 cmake 3.25.2 供编译过程使用，同时需确认系统已安装可用的 Python3，因为部分辅助脚本依赖 Python3。

---

## 4. CP2K 工具链编译命令

准备好的 devtoolset（gcc-9.1.1）、自编译的 cmake 3.25.2 以及 Python3 可用于编译 toolchain。执行编译工具链的命令为：./install_cp2k_toolchain.sh --with-sirius=no --with-openmpi=install --with-plumed=install --with-gcc=install --with-intel=no --with-cmake=system。

---

## 5. CP2K 编译配置与参数设置

将 toolchain 生成的 arch file 复制到 arch 目录下，包括 local.psmp 和 local.ssmp。LIBS 变量中需要追加 -lrt，执行 make -j 32 ARCH=local VERSION="ssmp psmp" 即可完成编译。

---

## 6. CP2K 链接库参数

编译过程中使用的 LIBS 参数配置如下：-lsymspg -l:libplumed.a -ldl -lstdc++ -lz -ldl -lgsl -lelpa_openmp -lcosma_prefixed_pxgemm -lcosma -lcosta -lscalapack -lxsmmf -lxsmm -ldl -lpthread -llibgrpp -lxcf03 -lxc -lint2 -lfftw3_mpi -lfftw3 -lfftw3_omp -lmpi -l:libopenblas.a -lvori -lstdc++ -lstdc++ -lrt。

---

## 7. CP2K 性能测试数据

针对 H2O-64 体系的测试表明，双路 X5650 处理器单圈 SCF 耗时 1.7 秒，E5-2670 与 E5-2630v4 耗时约为 0.9 秒，6336Y 耗时为 0.3 秒。该结果展示了不同硬件平台下的计算性能差异。
