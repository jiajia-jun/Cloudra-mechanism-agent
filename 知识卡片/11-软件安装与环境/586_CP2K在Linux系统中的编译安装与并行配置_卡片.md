---
id: 586
title: CP2K第一性原理程序在Linux中的安装方法
url: http://sobereva.com/586
domain: 软件安装与环境
topic: CP2K在Linux系统中的编译安装与并行配置
cards: 16
---
## 1. CP2K程序简介与编译建议

CP2K是开源免费的第一性原理程序，计算中、大周期性体系的速度极快，优于基于平面波的程序如VASP和Quantum ESPRESSO。建议使用自行编译的标准安装方式，因为预编译版本为兼容性无法充分利用CPU指令集和架构优化，性能不如自己编译。CP2K从2026.1版本开始编译方式发生重大变化，此处针对>=2026.2版本和<=2025.2版本分别介绍安装方法。

---

## 2. CP2K 2026.2版本系统与编译器要求

安装CP2K 2026.2版本建议使用Rocky Linux 9或10系统，CentOS Stream、Fedora、Redhat也可直接使用，不建议使用更老系统。CP2K基于Fortran编写但依赖C/C++库，需安装gcc和gfortran编译器，若未安装可运行dnf install gcc和dnf install gcc-gfortran。CP2K默认使用OpenBLAS库，虽Intel MKL可能更快但此处为省事不使用MKL；GPU加速仅对昂贵专业显卡有效，消费级显卡无效故不涉及。

---

## 3. CP2K 2026.2版本依赖库安装

下载源码包cp2k-2026.2.tar.bz2并解压，进入tools/toolchain/目录运行./install_cp2k_toolchain.sh --with-openmpi=install -j [CPU物理核心数]自动安装依赖库。该脚本将库文件安装到toolchain/install目录，编译最耗时的是libint。若系统已有OpenMPI，应改用--with-openmpi=system以避免冲突；若不需要GFN2-xTB可写--with-tblite=no避免安装tblite。

---

## 4. CP2K 2026.2版本toolchain安装细节

toolchain脚本默认安装重要库，运行./install_cp2k_toolchain.sh --help可查看选项并调整。默认开启--with-tblite=install以支持GFN2-xTB和DFT-D4，安装SIRIUS需加--with-sirius=install，安装PLUMED需加--with-plumed=install。安装后toolchain/build目录可删除以节省硬盘；若编译失败可查看build目录下对应库的log文件分析报错，重新运行脚本会自动跳过已成功的库。

---

## 5. CP2K 2026.2版本toolchain网络与离线问题

若toolchain运行中卡顿且CPU未编译，通常是网速慢导致库压缩包无法下载，可通过VPN加速解决。离线安装方法是在网络通畅的机器上运行一次安装，将build目录下的.tgz、.tar.gz、.tar.bz2压缩包拷贝到目标机器的build目录；或直接从https://www.cp2k.org/static/downloads/下载所需包放入build目录。若完全无网，应加上--with-tblite=no，因为tblite安装可能需联网下载额外内容。

---

## 6. CP2K 2026.2版本程序编译与环境配置

在tools/toolchain/目录下运行./build_cp2k.sh -j [CPU物理核心数]开始编译CP2K。编译成功后会提示可执行文件位于/sob/cp2k-2026.2/install/bin目录，包含关键的cp2k.psmp。修改~/.bashrc文件，加入source /sob/cp2k-2026.2/install/cp2k_env并重新进入终端，即可通过cp2k.psmp命令运行程序，使用cp2k.psmp -v可查看版本和编译信息。

---

## 7. CP2K并行方式与性能对比

cp2k.psmp支持MPI和OpenMP混合并行，MPI并行速度通常快于OpenMP并行，但内存消耗更高。例如16核机器，MPI进程数=16、OpenMP线程数=1时速度最快且内存最大；MPI进程数=1、OpenMP线程数=16时速度最慢且内存最小。MPI进程数由mpirun -np指定，OpenMP线程数由环境变量OMP_NUM_THREADS指定，cp2k.popt是纯MPI并行的符号链接。

---

## 8. CP2K 2026.2版本运行测试示例

下载测试输入文件test.inp，完全MPI并行运行：mpirun -np 16 cp2k.popt test.inp |tee test.out。混合并行运行（如4进程4线程）：先export OMP_NUM_THREADS=4，再运行mpirun -np 4 cp2k.psmp test.inp |tee test.out。纯OpenMP并行运行：先export OMP_NUM_THREADS=16，再运行cp2k.psmp test.inp |tee test.out。可在mpirun中用-x参数临时定义OMP_NUM_THREADS，或在.bashrc中设置alias简化命令。

---

## 9. CP2K并行方式选择建议

若无特殊情况建议完全通过MPI方式并行，效率最高。对于振动分析、NEB任务等需要运行大量副本的情况，恰当利用OpenMP并行可避免内存不足崩溃。杂化泛函计算周期性大体系时，双电子积分量巨大，为在内存中储存积分避免重复计算，往往也需要MPI与OpenMP结合以节约内存。

---

## 10. CP2K <=2025.2版本系统与编译器要求

CP2K <=2025.2版本在Rocky Linux 9上测试通过，建议使用该系统。程序基于Fortran编写但依赖C/C++库，若使用gcc+gfortran编译，gcc版本必须>=5.5，CentOS 7自带4.8.5需升级系统或编译器。toolchain运行需联网且网速不能太慢，建议加速对外网访问；若使用Intel MKL数学库需先安装并设置MKLROOT环境变量，toolchain检测到后会自动调用MKL。

---

## 11. CP2K <=2025.2版本离线安装MKL方法

在线安装MKL运行dnf config-manager和dnf install intel-mkl命令。离线安装可下载Intel OneAPI base toolkit，仅选择MKL安装，随后将source /opt/intel/oneapi/mkl/[版本号]/env/vars.sh加入~/.bashrc。若遇到COSMA库编译失败，需在toolchain命令后加上--with-cosma=no，这对性能影响甚微。

---

## 12. CP2K <=2025.2版本toolchain库安装

下载源码包如cp2k-8.1.tar.bz2并解压，进入tools/toolchain/目录运行./install_cp2k_toolchain.sh --with-sirius=no --with-openmpi=install --with-plumed=install。该命令不安装SIRIUS库，安装OpenMPI和PLUMED库。若报错找不到gfortran需先运行dnf install gcc-gfortran；若需DFT-D4校正需额外带上--with-ninja --with-dftd4；编译完成后build目录可删除以节省空间。

---

## 13. CP2K <=2025.2版本编译CP2K程序

将toolchain/install/arch/下所有文件拷到cp2k源码的arch目录，运行source /sob/cp2k-8.1/tools/toolchain/install/setup加载环境，然后运行make -j 4 ARCH=local VERSION="ssmp psmp"进行编译。若报错cannot find -lz需运行dnf install zlib-devel。编译产生的可执行文件位于exe/local目录，包含cp2k.ssmp和cp2k.psmp等，可将source和export PATH命令加入~/.bashrc以便直接调用。

---

## 14. CP2K <=2025.2版本预编译版使用

下载cp2k-8.1.tar.bz2解压，并下载预编译版cp2k-8.1-Linux-x86_64.ssmp改名为cp2k.ssmp放入解压目录。在~/.bashrc中添加export PATH=$PATH:/sob/cp2k-8.1和export CP2K_DATA_DIR=/sob/cp2k-8.1/data。设置CP2K_DATA_DIR是因为输入文件若只定义文件名未给路径，程序会在该环境变量指定的目录下搜索基组和势文件。

---

## 15. CP2K <=2025.2版本运行测试

使用test.inp测试文件，运行ssmp版：cp2k.ssmp test.inp |tee test.out，默认使用所有核心，可通过export OMP_NUM_THREADS=4限制核心数。运行popt版：mpirun -np 4 cp2k.popt test.inp |tee test.out。建议默认使用popt版，可在.bashrc中设置alias cp2k='mpirun -np 4 cp2k.popt'简化操作，运行sopt、popt版时OMP_NUM_THREADS会被视为1。

---

## 16. CP2K四种版本的定义与特点

CP2K根据并行方式分为四个版本：sopt只能单机单核；ssmp支持OpenMP单机多核；popt支持MPI单机或跨节点并行；psmp支持MPI+OpenMP混合单机或跨节点并行。sopt等价于ssmp设OMP_NUM_THREADS=1，popt等价于psmp设OMP_NUM_THREADS=1。混合并行（如9MPI进程*4OpenMP线程）在利用36核时，比纯MPI省内存，比纯OpenMP效率高，适合杂化泛函等高内存消耗任务。
