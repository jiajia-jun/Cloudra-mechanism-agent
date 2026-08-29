---
key: t27675
title: CentOS7ϵͳ����CP2K 9.1������GCC+Intel MKL+Intel MPI��
url: http://bbs.keinsci.com/thread-27675-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 11
---

# CentOS7ϵͳ����CP2K 9.1������GCC+Intel MKL+Intel MPI�� — 知识卡片

## 1. CentOS 7 下编译 CP2K 的环境配置

编译环境配置为 CentOS 7.9 操作系统，配合 GCC 8.4.0 编译器与 Intel Parallel Studio XE 2020 Update 2。目标编译方案为 CP2K toolchain 联合 GNU 编译器、Intel MKL 数学库以及 Intel MPI 并行库。此组合适用于 CP2K 9.1 版本的源码编译。

---

## 2. GCC 8.4.0 及依赖库安装与配置

GCC 8.4.0 编译需要依赖 GMP 6.2.0、MPFR 4.1.0 和 MPC 1.2.0 版本库。安装完成后需在 shell 中设置 PATH 和 LD_LIBRARY_PATH 环境变量，指向 GCC、GMP、MPFR 和 MPC 的安装目录。执行 `gcc -v && g++ -v && gfortran -v` 命令可验证编译器是否安装成功。

---

## 3. Intel Parallel Studio XE 2020 环境变量加载

Intel Parallel Studio XE 2020 Update 2 安装过程较为简单，运行安装程序即可完成。安装完成后需执行 source 命令加载 mklvars.sh 和 mpivars.sh 脚本，以配置 Intel MKL 和 Intel MPI 的环境变量。

---

## 4. Intel MPI 与 GCC 编译器适配验证

配置环境后执行 `mpicc -v`、`mpicxx -v` 和 `mpif90 -v` 应显示 Intel MPI 调用 GNU 编译器的信息。输出信息中应包含 GCC 版本号（如 gcc version 8.4.0）以及配置参数中包含的 GMP、MPFR、MPC 路径。

---

## 5. CP2K 源码获取与预处理

从 GitHub releases 页面下载 cp2k-9.1.tar.bz2 源码包并使用 `tar xjf` 解压。需进入解压后目录的 tools/toolchain 文件夹，修改 scripts/stage1/install_intelmpi.sh 脚本，将 mpiicc 替换为 mpicc，mpiifort 替换为 mpif90，以适配 GNU 编译器。

---

## 6. CP2K Toolchain 编译命令

在 toolchain 目录下执行 install_cp2k_toolchain.sh 脚本，需指定 `--math-mode=mkl`、`--with-intelmpi=system`、`--with-scalapack=no`、`--with-sirius=no` 和 `--with-plumed=install` 等参数。编译完成后需复制 arch 文件并执行 setup 脚本，最后在源码根目录运行 `make -j ARCH=local VERSION="psmp"`。

---

## 7. CP2K 编译结果验证

编译完成后将生成 psmp 版本的 CP2K 可执行文件。建议在 bin 目录下运行测试算例，或下载官方测试集进行验证以确认编译成功。若编译过程中缺少特定库，可从 CP2K 官网下载对应的预编译 toolchain/build 文件。

---

## 8. ELPA 库在 CP2K 8.2 中的 Bug 及修复

在 CP2K 8.2 版本中使用 toolchain 默认的 ELPA 库存在 Bug，可通过修改 toolchain/scripts/stage5/install_elpa.sh 使用 elpa-2021.05.002_bugfix 版本进行修复。ELPA 库对计算速度有显著影响，CP2K 9.1 版本已修复此问题。

---

## 9. Intel MPI 版本与内存泄漏问题

在 CP2K 8.2 及以上版本使用 Intel Parallel Studio XE 2020 Update 2 的 Intel MPI 时存在内存泄漏问题。测试表明使用 2017 Update 8 版本的 Intel MPI 可以解决此内存泄漏问题，建议在相关版本 CP2K 中采用该版本 MPI。

---

## 10. Intel MPI 版本导致的计算卡死问题

在 CP2K 8.2 及以上版本中，使用 2020 Update 2 的 Intel MPI 可能导致 CPU 计算核心卡死，而 2017 Update 8 版本无此现象。该问题与 Intel MPI 内部机制有关，混合使用不同版本的 Intel MPI 或混用 OpenMPI 也可能导致计算异常或卡死。

---

## 11. Intel MPI 版本对并行效率的影响

在 CP2K 8.2 及以上版本中使用 Intel Parallel Studio XE 2017 Update 8 的 Intel MPI 时，小规模并行（如 36 核）效率较高。但在更低的核心数（如 24 或 32 核）下，计算速度可能反而低于较高核心数下的表现，具体性能受 CPU 型号（如 Gold 6139ES）影响。
