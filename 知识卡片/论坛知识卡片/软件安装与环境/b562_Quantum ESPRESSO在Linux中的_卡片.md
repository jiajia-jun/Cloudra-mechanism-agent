---
key: b562
title: Quantum ESPRESSO在Linux中的安装方法
url: http://sobereva.com/562
domain: 软件安装与环境
source: blog
year: 2020
cards: 10
---

# Quantum ESPRESSO在Linux中的安装方法 — 知识卡片

## 1. Quantum ESPRESSO简介与编译环境准备

Quantum ESPRESSO (QE) 是广泛使用的开源免费第一性原理程序。在 CentOS 7.x 系统下安装 QE 6.5 可基于 OpenMPI 库、MKL 库和 gfortran/gcc 编译器进行。此编译方式为纯 CPU 版本，不支持 GPU 加速。若系统中未安装 gcc 和 gfortran，需先使用 yum install gcc 命令进行安装。

---

## 2. OpenMPI的安装与配置

OpenMPI 4.0.3 版本经测试与 QE 6.5 完全兼容。下载并解压 OpenMPI 后，在目录下运行 `./configure --prefix=/sob/openmpi` 和 `make all install` 将其编译安装到指定目录。需在 ~/.bashrc 文件中添加 `export PATH=$PATH:/sob/openmpi/bin` 和 `export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/openmpi/lib`，运行 mpiexec -V 确认版本无误。

---

## 3. MKL库的安装

安装 MKL 数学库可显著提升 QE 计算速度。在 CentOS 下可通过添加 Intel 源 `yum-config-manager --add-repo https://yum.repos.intel.com/mkl/setup/intel-mkl.repo` 并运行 `yum install -y intel-mkl` 进行安装。该库会被安装到 /opt/intel 目录下，若之前已安装 Intel 编译器并包含 MKL，则无需重复安装。

---

## 4. QE源码编译命令

下载 QE 源码包（如 qe-6.5-ReleasePack.tgz）并解压后，运行 `./configure --prefix=/sob/qe65 -enable-openmp` 进行配置。使用 `make all install -j` 进行编译，可执行文件将被安装到 /sob/qe65/bin 目录下。若需更改默认编译器（gfortran、gcc、mpif90），需修改 make.inc 文件中的相关设置。

---

## 5. QE环境变量设置

编译完成后需在 ~/.bashrc 中设置环境变量以运行 QE。添加的内容包括 OpenMPI 相关权限设置 `export OMPI_ALLOW_RUN_AS_ROOT=1` 和 `export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1`，以及路径设置 `export PATH=$PATH:/sob/qe65/bin`。还需根据实际路径添加 MKL 库目录，例如 `export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/intel/compilers_and_libraries_2020.2.254/linux/mkl/lib/intel64_lin`。

---

## 6. QE扩展模块编译

默认编译过程不包含 EPW、PLUMED、Wannier90、WanT、YAMBO、GIPAW 等程序。如需编译这些扩展模块，可参考 Quantum ESPRESSO 官方文档 User's Guide 中的 2.5 节说明。保留源代码解压目录有助于后续使用特定命令（如 make epw）单独编译这些程序。

---

## 7. QE并行运行模式测试

QE 采用 MPI 和 OpenMP 混合并行方式，实际并行核数为 MPI 进程数与每个进程下属 OpenMP 线程数的乘积。纯 MPI 并行测试时，设置 `export OMP_NUM_THREADS=1` 并运行 `mpirun -n 4 pw.x < pwscf.in |tee pwscf.out`。纯 OpenMP 并行测试时，设置 `export OMP_NUM_THREADS=4` 并直接运行 `pw.x < pwscf.in |tee pwscf.out`。

---

## 8. QE自带测试集使用

QE 源码包包含自带的测试集，位于解压目录下的 test-suite 子目录中。运行 `make run-tests-parallel` 可对所有任务进行并行测试。若只需测试 PWscf 模块，可运行 `make run-tests-pw-parallel`。测试集各项目的具体含义可查阅该目录下的 README 文件。

---

## 9. CentOS下yum安装QE方法

在 CentOS 系统下使用 root 账户可运行 `yum install epel-release` 和 `yum install quantum-espresso-openmpi` 安装 QE 6.5。此方法会自动安装 OpenMPI、OpenBLAS 和 ScaLapack 等依赖包。安装后需在 ~/.bashrc 中添加 `export PATH=$PATH:/usr/lib64/openmpi/bin/` 及相关权限设置。

---

## 10. yum预编译版QE的局限性

使用 yum 安装的预编译版 QE 为保证兼容性，未使用高性能的 MKL 库（替代为 OpenBLAS/ScaLapack/FFT）且编译选项较为保守，性能可能逊于自行编译的版本。预编译版可执行文件带有 _openmpi 后缀（如 pw.x_openmpi）。自行编译允许自定义安装位置并包含源代码，便于查阅文档和编译扩展模块。
