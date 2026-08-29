---
key: b457
title: GROMACS的安装方法（含全程视频演示）
url: http://sobereva.com/457
domain: 软件安装与环境
source: blog
year: 2019
cards: 16
---

# GROMACS的安装方法（含全程视频演示） — 知识卡片

## 1. GROMACS的运行环境与安装版本适用性

GROMACS分子动力学程序通常在Linux下运行，资料Linux下的编译安装方法，同时Windows下亦可完美编译和运行。以下安装方法以GROMACS 2018.8版为例进行说明，经测试完全适用于GROMACS 2018及之后的各个版本（至少到2025.x版）。资料安装环境基于CentOS 7.6，实测对CentOS/RockyLinux 8、9也完全适用，对于其它Linux系统安装方法可能有所差异。

---

## 2. 编译器与工具版本要求

从GROMACS 2020版本开始，要求gcc编译器版本必须大于等于5，而CentOS 7.x自带的gcc版本为4.8.5，因此无法直接安装，需升级gcc或使用更高版本的CentOS/RockyLinux。从GROMACS 2021版本开始，要求cmake版本必须大于等于3.17，CentOS/RockyLinux 8软件源中的cmake版本偏老，需手动安装。从GROMACS 2025版本开始，要求gcc版本为11，cmake版本必须大于等于3.28，RockyLinux 9的软件源cmake版本可能偏老，需手动安装。

---

## 3. 编译环境版本不兼容问题

如果系统gcc版本较新而GROMACS版本较老，可能导致编译无法通过，例如Rocky Linux 9自带的gcc 11.2.1编译GROMACS 2018.8时会失败。资料安装的是纯CPU运算、单精度、能单机并行但不能跨节点并行的版本，若需GPU加速或跨节点并行需参考文末附注。编译过程中使用make -j选项进行并行编译以降低耗时，但在虚拟机下可能导致卡住，届时需去掉-j选项重试。

---

## 4. 使用yum安装cmake 3.x

GROMACS 2018编译需要系统中有cmake 3.x，CentOS 7.6自带版本过老需先行安装。首先运行命令`yum install epel-release`添加EPEL源，然后输入`yum install cmake3`进行安装，安装过程中遇到提示输入y。安装完成后输入`cmake3 -V`命令，若显示3.x版本号则说明安装成功。若yum安装出现异常，重启操作系统往往可解决问题。

---

## 5. 手动编译安装cmake 3.x

若无管理员权限或软件源cmake版本过老，可从cmake官网下载Source distributions源码包。解压后进入目录，依次运行`./bootstrap --prefix=/sob/cmake3 -- -DCMAKE_USE_OPENSSL=OFF`、`make -j`、`make install`。安装完成后会在/sob目录下生成cmake3目录，之后需在~/.bashrc文件中加入`export PATH=/sob/cmake3/bin:$PATH`，重新进入终端后cmake命令即可使用。

---

## 6. 安装FFTW依赖库

GROMACS 2018依赖于快速傅立叶变换库FFTW 3.3.8，需下载源码包并解压。进入解压目录后运行配置命令`./configure --prefix=/sob/fftw338 --enable-sse2 --enable-avx2 --enable-float --enable-shared`，该命令将FFTW安装到/sob/fftw338目录。若CPU较老不支持AVX2指令集，需将`--enable-avx2`改为`--enable-avx`。配置完成后运行`make install -j`开始编译。

---

## 7. GROMACS源码编译与安装步骤

下载GROMACS 2018.8压缩包并拷贝至/sob目录解压，进入解压目录后依次创建并进入build目录。设置环境变量`export CMAKE_PREFIX_PATH=/sob/fftw338`，随后运行cmake命令进行配置，指定安装路径如`-DCMAKE_INSTALL_PREFIX=/sob/gmx2018.8`（CentOS 8或手动编译cmake时使用cmake而非cmake3）。配置后需检查屏幕提示确认CPU支持的SIMD指令集是否正确识别，最后运行`make install -j`完成编译安装。

---

## 8. 配置环境变量与验证安装

GROMACS编译安装完成后位于/sob/gmx2018.8目录，需修改用户目录下的.bashrc文件，在末尾添加`source /sob/gmx2018.8/bin/GMXRC`并保存。关闭并重新打开终端窗口，输入`gmx -version`命令，若输出GROMACS相关信息则说明安装成功。安装成功后可删除源码压缩包和解压目录以节省空间。

---

## 9. GROMACS运行时的SIMD指令集警告处理

使用`gmx mdrun`运行任务时，若出现WARNING提示使用慢速plain C kernels，说明编译时未利用CPU的SIMD指令集，会导致运行速度比理想情况慢很多。此时需重新编译，在cmake步骤中明确指定指令集，例如对于支持AVX2指令集的CPU（如XEON v3系列及之后），需添加`-DGMX_SIMD=AVX2_256`选项。

---

## 10. 编译支持CUDA GPU加速的版本

GROMACS支持通过CUDA方式对nVidia GPU进行加速，需先下载并安装CUDA toolkit到默认路径。编译方法与前述基本一致，但在cmake步骤需额外添加`-DGMX_GPU=CUDA -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda`（以实际安装路径为准）。对于GROMACS 2021之前的版本，参数`-DGMX_GPU=CUDA`应改为`-DGMX_GPU=ON`。

---

## 11. GPU版本的使用与CPU强制运行

编译好CUDA版本的GROMACS后，运行`gmx mdrun`时若检测到nVidia GPU并安装了驱动，会自动使用GPU加速。若需强制只使用CPU运算，可在mdrun命令后加上`-nb cpu -pme cpu -bonded cpu`参数。或者编译一个不含`-DGMX_GPU`参数的纯CPU版本置于不同路径，并在.bashrc中source该版本的GMXRC；若自动检测到CUDA toolkit，可添加`-DGMX_GPU=OFF`强制编译为CPU版本。

---

## 12. GROMACS编译时自动安装FFTW库

安装GROMACS时可以通过设置`-DGMX_BUILD_OWN_FFTW=ON`选项自动下载并编译FFTW库，从而省略手动安装FFTW的步骤。但由于国内网络环境访问FFTW官网服务器速度较慢，自动下载过程容易卡死或耗时极长，因此建议仍采用手动方式安装FFTW库。使用自动安装方式时，无需设置CMAKE_PREFIX_PATH环境变量。

---

## 13. 编译双精度版本GROMACS

一般计算使用单精度版本即可，但若模拟开始即崩溃，使用双精度版本可能解决问题，且做正则振动分析时通常也需要双精度以确保数值精度。编译双精度版本需在编译FFTW时去掉`--enable-float`选项，并在cmake命令中添加`-DGMX_DOUBLE=ON`。双精度版本可执行文件名为gmx_d，可与单精度的gmx共存于同一目录，但双精度版本不支持GPU加速且计算速度较慢。

---

## 14. 安装MPI库以支持跨节点并行

编译支持跨节点并行的MPI版GROMACS前需先安装MPI库，如OpenMPI。下载OpenMPI源码解压后，运行`./configure --prefix=/sob/openmpi`指定安装路径，随后运行`make all install -j`进行编译安装。安装完成后需在.bashrc中添加`export PATH=$PATH:/sob/openmpi/bin`和`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/openmpi/lib`，并重新进入终端使配置生效。

---

## 15. 编译与运行MPI版GROMACS

安装好MPI库后，在cmake编译GROMACS步骤中添加`-DGMX_MPI=ON`选项，编译出的可执行文件名为gmx_mpi。运行MPI版本时需使用mpirun命令，例如`mpirun -np 16 gmx_mpi mdrun`。对于root用户，OpenMPI执行mpirun时需携带`-allow-run-as-root`选项，可通过修改OpenMPI源代码来避免此限制。

---

## 16. AVX512指令集的编译处理

若CPU支持AVX512指令集但gcc版本过老不支持，编译GROMACS时会报错。此时可根据屏幕提示更新gcc版本，或者在cmake步骤中添加`-DGMX_SIMD=AVX2_256`选项，强制使用AVX2指令集进行编译以避开AVX512支持问题。
