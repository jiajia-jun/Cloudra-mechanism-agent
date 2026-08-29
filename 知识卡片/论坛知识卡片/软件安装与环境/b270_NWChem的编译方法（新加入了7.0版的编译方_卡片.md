---
key: b270
title: NWChem的编译方法（新加入了7.0版的编译方法介绍）
url: http://sobereva.com/270
domain: 软件安装与环境
source: blog
year: 2020
cards: 12
---

# NWChem的编译方法（新加入了7.0版的编译方法介绍） — 知识卡片

## 1. NWChem 7.2.3 的 OpenMPI 库编译

编译 NWChem 7.2.3 前需先编译 OpenMPI 库，从官网下载 OpenMPI 4.1.1 源码并解压，运行配置命令指定安装路径，再执行 make 安装。
- 命令：`./configure prefix=/sob/openmpi411`、`make all install -j`
- 安装后可将 OpenMPI 源码目录删除

---

## 2. NWChem 7.2.3 编译前的环境变量配置

编译 NWChem 7.2.3 需设置特定环境变量以指定路径、目标平台、模块及 MPI 选项，同时建议设置 OpenMPI 的环境变量。
- 命令：`export NWCHEM_TOP=/sob/nwchem-7.2.3`、`export NWCHEM_TARGET=LINUX64`、`export NWCHEM_MODULES=all`、`export BLAS_SIZE=8`、`export USE_MPI=y`、`export USE_MPIF=y`、`export USE_MPIF4=y`、`export USE_INTERNALBLAS=y`

---

## 3. NWChem 7.2.3 可选模块的编译启用

NWChem 默认不编译不常用的模块，若需编译多参考耦合簇或高级耦合簇代码，需设置对应的环境变量。
- 命令：`export MRCC_METHODS=y`（编译多参考耦合簇）、`export CCSDTQ=y`（编译 CCSDTQ 和 EOM-CCSDTQ）

---

## 4. NWChem 7.2.3 源码编译流程

下载并解压 NWChem 7.2.3 源码后，进入源码目录执行配置和 make 命令进行编译，可使用 -j 参数进行并行编译以加快速度。
- 命令：`cd /sob/nwchem-7.2.3/src`、`make nwchem_config`、`make -j`

---

## 5. NWChem 7.2.3 环境变量设置与测试

编译完成后需将可执行文件路径加入 PATH 环境变量，通过运行 B3LYP/cc-pVTZ 级别下 N2 分子优化的输入文件进行串行和并行测试。
- 测试输入命令：`nwchem test.nw`、`mpirun -np 4 nwchem test.nw`
- 路径设置：`export PATH=$PATH:/sob/nwchem-7.2.3/bin/LINUX64`

---

## 6. NWChem 6.6 在 Redhat Enterprise 6 下的 OpenMPI 编译

在 Redhat Enterprise 6 Update 1 64bit 系统下编译 NWChem 6.6，需先下载 OpenMPI 1.6.5 源码，配置并安装到指定目录。
- 命令：`./configure prefix=/sob/openmpi165`、`make all install -j`

---

## 7. NWChem 6.6 在 Redhat Enterprise 6 下的编译配置

编译 NWChem 6.6 需设置一系列环境变量，包括 NWChem 顶层目录、目标平台、MPI 路径及库链接参数等。
- 命令：`export NWCHEM_TOP=/sob/nwchem-6.6`、`export NWCHEM_TARGET=LINUX64`、`export MPI_LOC=/sob/openmpi165`、`export LIBMPI="-lmpi_f90 -lmpi_f77 -lmpi -ldl -Wl,--export-dynamic -lnsl -lutil"`

---

## 8. NWChem 6.6 可选高级功能模块编译

NWChem 6.6 支持通过环境变量开启多种不常用的高级计算模块，包括多参考耦合簇、高阶耦合簇、线性响应及电离能/电子亲和能计算。
- 命令：`export MRCC_METHODS=y`、`export CCSDTQ=y`、`export CCSDTLR=y`、`export IPCCSD=y`、`export EACCSD=y`

---

## 9. NWChem 6.6 在 Redhat Enterprise 6 下的编译与测试

在 Redhat Enterprise 6 下编译 NWChem 6.6 不建议使用 -j 参数，编译完成后需设置 PATH 并通过 N2 分子优化任务测试。
- 命令：`cd /sob/nwchem-6.6/src`、`make nwchem_config`、`make`

---

## 10. NWChem 6.6 在 CentOS 7.2 下的依赖安装

在 CentOS 7.2 64bit 系统下编译 NWChem 6.6，可使用 yum 命令直接安装 EPEL 源和 openmpi 开发包。
- 命令：`yum install epel-release`、`yum install openmpi-devel openmpi`

---

## 11. NWChem 6.6 在 CentOS 7.2 下的编译环境配置

在 CentOS 7.2 下编译 NWChem 6.6 需设置基础环境变量及系统自带 OpenMPI 的库路径和二进制路径，若需额外功能需设置对应变量。
- 命令：`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/lib64/openmpi/lib/`、`export PATH=$PATH:/usr/lib64/openmpi/bin/`

---

## 12. NWChem 6.6 在 CentOS 7.2 下的最终配置与运行

NWChem 6.6 在 CentOS 7.2 下编译完成后，需在 ~/.bashrc 中设置 PATH、LD_LIBRARY_PATH 及 mpirun 别名以支持 root 用户运行。
- 别名设置：`alias mpirun='mpirun --allow-run-as-root'`
- 运行命令：`mpirun -np 4 nwchem test.nw`
