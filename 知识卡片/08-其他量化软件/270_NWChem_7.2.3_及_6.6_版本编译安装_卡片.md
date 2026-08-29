---
id: 270
title: NWChem的编译方法
domain: 其他量化软件
topic: NWChem_7.2.3_及_6.6_版本编译安装
cards: 13
---

## 1. NWChem 7.2.3 编译 OpenMPI 库的步骤
下载 OpenMPI 4.1.1，解压到 /sob 目录下，进入其目录运行配置和安装命令；安装完成后可执行文件、库文件、头文件等位于 /sob/openmpi411 目录。
./configure prefix=/sob/openmpi411
make all install -j

---

## 2. NWChem 7.2.3 编译前的 OpenMPI 环境变量设置
在 ~/.bashrc 中加入 PATH 和 LD_LIBRARY_PATH 环境变量，保存后输入 bash 命令使环境变量生效。
export PATH=$PATH:/sob/openmpi411/bin
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/openmpi411/lib

---

## 3. NWChem 7.2.3 核心编译环境变量设置
运行以下命令设置 NWChem 编译所需的各类核心环境变量，包括路径、目标平台、模块选择、BLAS大小及MPI设置。
export NWCHEM_TOP=/sob/nwchem-7.2.3
export NWCHEM_TARGET=LINUX64
export NWCHEM_MODULES=all
export BLAS_SIZE=8
export USE_MPI=y
export USE_MPIF=y
export USE_MPIF4=y
export USE_INTERNALBLAS=y

---

## 4. NWChem 7.2.3 额外功能模块的编译选项
若需编译不常用的模块，需定义相应的环境变量；MRCC_METHODS 用于编译多参考耦合簇代码，CCSDTQ 用于编译 TCE 模块的 CCSDTQ 和 EOM-CCSDTQ 代码。
export MRCC_METHODS=y
export CCSDTQ=y

---

## 5. NWChem 7.2.3 源代码获取与编译命令
从 GitHub 发布页下载 NWChem 7.2.3 源代码并解压，进入 src 目录后运行配置和编译命令；使用 -j 选项可进行并行编译。
cd /sob/nwchem-7.2.3/src
make nwchem_config
make -j

---

## 6. NWChem 7.2.3 编译完成后的环境变量配置与测试
编译完成后可执行文件位于 /sob/nwchem-7.2.3/bin/LINUX64 目录，需将该目录加入 PATH 环境变量；测试时编写 B3LYP/cc-pVTZ 优化 N2 分子的输入文件，并分别运行串行和并行命令验证输出。
export PATH=$PATH:/sob/nwchem-7.2.3/bin/LINUX64
nwchem test.nw
mpirun -np 4 nwchem test.nw

---

## 7. NWChem 6.6 在 Redhat Enterprise 6 Update 1 下编译 OpenMPI 1.6.5
下载 OpenMPI 1.6.5 并解压到 /sob 目录，运行配置命令指定安装前缀为 /sob/openmpi165，然后执行安装。
./configure prefix=/sob/openmpi165
make all install -j

---

## 8. NWChem 6.6 在 Redhat Enterprise 6 Update 1 下的环境变量配置
在 ~/.bashrc 中配置 OpenMPI 的 PATH 和 LD_LIBRARY_PATH，并在命令行设置 NWChem 的编译环境变量及 MPI 相关路径和库。
export PATH=$PATH:/sob/openmpi165/bin
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/openmpi165/lib
export NWCHEM_TOP=/sob/nwchem-6.6
export NWCHEM_TARGET=LINUX64
export NWCHEM_MODULES=all
export USE_MPI=y
export USE_MPIF=y
export USE_MPIF4=y
export USE_INTERNALBLAS=y
export MPI_LOC=/sob/openmpi165
export MPI_LIB=/sob/openmpi165/lib
export MPI_INCLUDE=/sob/openmpi165/include
export LIBMPI="-lmpi_f90 -lmpi_f77 -lmpi -ldl -Wl,--export-dynamic -lnsl -lutil"

---

## 9. NWChem 6.6 在 Redhat Enterprise 6 Update 1 下的额外模块编译选项
除了 MRCC_METHODS 和 CCSDTQ 外，此版本还可通过环境变量开启 TCE 模块的线性响应、电离能和电子亲和能计算代码。
export CCSDTLR=y
export IPCCSD=y
export EACCSD=y

---

## 10. NWChem 6.6 在 Redhat Enterprise 6 Update 1 下的编译与测试
进入源码 src 目录运行 make nwchem_config 和 make 进行编译，可执行文件位于 bin/LINUX64 目录；最后通过运行 N2 分子优化的串行和并行任务进行测试。
cd /sob/nwchem-6.6/src
make nwchem_config
make

---

## 11. NWChem 6.6 在 CentOS 7.2 下通过 yum 安装 OpenMPI
运行 yum 命令添加 EPEL 源并安装 openmpi-devel 和 openmpi；此方法需要机器能够连接外网。
yum install epel-release
yum install openmpi-devel openmpi

---

## 12. NWChem 6.6 在 CentOS 7.2 下的编译环境变量与路径设置
设置 NWChem 核心编译环境变量，并配置系统 OpenMPI 的库路径和可执行文件路径；需注意不设置 USE_MPIF 和 USE_MPIF4。
export NWCHEM_TOP=/sob/nwchem-6.6
export NWCHEM_TARGET=LINUX64
export NWCHEM_MODULES=all
export USE_MPI=y
export USE_INTERNALBLAS=y
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/lib64/openmpi/lib/
export PATH=$PATH:/usr/lib64/openmpi/bin/

---

## 13. NWChem 6.6 在 CentOS 7.2 下的最终环境变量配置
编译完成后，在 ~/.bashrc 中添加 NWChem 可执行文件路径和 OpenMPI 路径，并设置 mpirun 别名以允许 root 用户运行。
export PATH=$PATH:/sob/nwchem-6.6/bin/LINUX64:/usr/lib64/openmpi/bin/
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/lib64/openmpi/lib/
alias mpirun='mpirun --allow-run-as-root'
