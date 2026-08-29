---
key: t42370
title: ��centos 7�Ϸ���򵥵ر���cp2k 2023.2�汾�ķ���
url: http://bbs.keinsci.com/thread-42370-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 13
---

# ��centos 7�Ϸ���򵥵ر���cp2k 2023.2�汾�ķ��� — 知识卡片

## 1. 编译环境与版本兼容性

在 CentOS 7 (Release 7.9.2009) 系统下使用 gfortran 编译器编译 CP2K 的 toolchain 可以成功构建 2023.2 版本。CentOS 8 系统下使用 ifort 编译器在优化该版本结构时会卡住，单点计算也会卡住。1.6 版本在不同体系下计算差异较大，但用户不会卡住。

---

## 2. 并行效率比较

使用 MPICH 的 MPI 并行编译生成的 psmp 版本，与 Intel 编译器编译的版本计算结果相同，误差在 1% 以内。

---

## 3. 编译准备与目录创建

解压 cp2k.2023.2 版本源码包，进入解压后的目录，并创建新目录 `./tools/toolchain/build`。编译所需的依赖包需要下载到 `./tools/toolchain/build` 目录下。

---

## 4. 依赖包下载说明

编译过程总共需要 28 个依赖包文件，下载速度较快。除了手动下载外，脚本也可以自动下载这些依赖包。

---

## 5. 执行安装脚本

在 `./tools/toolchain/build` 目录下执行命令 `./install_cp2k_toolchain.sh --install-all` 来开始安装依赖包。

---

## 6. 环境变量设置

安装脚本执行完毕后，根据屏幕提示执行命令 `source /解压目录/tools/toolchain/install/setup` 来设置环境变量。

---

## 7. CP2K 编译命令

查看 arch 目录下的文件，选择 Linux-gnu-x86_64.psmp 配置执行编译命令 `make ARCH=Linux-gnu-x86_64 VERSION="psmp"`。

---

## 8. 编译结果测试

编译完成后执行命令 `make -j 64 ARCH=Linux-gnu-x86_64 VERSION=psmp test` 以验证安装是否正确。测试一般会执行 4605 个测试文件，遇到少量 warning 或 error 可以忽略，只要大部分通过即可保证可靠性。

---

## 9. CentOS 7 额外依赖包

CentOS 7 版本需要额外下载 5 个文件：`pexsi_v1.2.0.tar.gz`、`QUIP-0.9.10.tar.gz`、`scotch_6.0.0.tar.gz` 和 `superlu_dist_6.1.0.tar.gz`。若涉及 CUDA 显卡，还需要文件 `libtorch-cxx11-abi-shared-with-deps-1.12.1+cpu.zip`。

---

## 10. 通用依赖包列表

其余 26 个通用依赖文件包括：`gcc-13.1.0.tar.gz`、`mpich-4.0.3.tar.gz`、`cmake-3.26.3-linux-x86_64.sh`、`COSMA-v2.6.6.tar.gz`、`COSTA-v2.2.2.tar.gz`、`elpa-2022.11.001.tar.gz`、`fftw-3.3.10.tar.gz`、`gsl-2.7.tar.gz`、`hdf5-1.12.0.tar.bz2`、`libint-v2.6.0-cp2k-lmax-5.tgz`、`libvdwxc-0.4.0.tar.gz`、`libvori-220621.tar.gz`、`libxc-6.2.2.tar.gz`、`libxsmm-1.17.tar.gz`、`OpenBLAS-0.3.23.tar.gz`、`plumed-src-2.8.2.tgz`、`scalapack-2.2.1.tgz`、`SIRIUS-7.4.3.tar.gz`、`SpFFT-1.0.6.tar.gz`、`spglib-1.16.2.tar.gz`、`SpLA-1.5.5.tar.gz` 和 `Tiled-MM-v2.2.tar.gz`。

---

## 11. gfortran 编译适用性

在 CentOS 7 上不使用 Intel 编译器而使用 gfortran 编译 CP2K 2023.2 版本十分顺利。该版本在遇到长时间计算任务时能够通过检查点文件续算，而通过旧版文档方法编译的版本无法使用此功能。

---

## 12. 推荐安装参数

这种安装方式比较全面，推荐使用的安装参数包括：`omp`、`libint`、`fftw3`、`libxc`、`pexsi`、`elpa`、`parallel`、`scalapack`、`cosma`、`quip`、`xsmm`、`max_contr=4`、`plumed2`、`has_ieee_exceptions`、`spglib`、`sirius`、`libvori`、`libbqb` 和 `libvdwxc`。

---

## 13. 并行计算运行命令

运行计算时需要先执行环境设置和线程数设置命令 `source /解压目录/tools/toolchain/install/setup` 和 `export OMP_NUM_THREADS=1`。提交任务的具体命令示例为 `mpirun -np 64 /解压目录/exe/Linux-gnu-x86_64/cp2k.psmp -i opt.inp >opt.out`。
