---
id: 457
title: GROMACS的安装方法（含全程视频演示）
domain: 软件安装与环境
topic: GROMACS_Linux下编译安装及依赖配置
cards: 17
---

## 1. GROMACS在Linux下的安装概述与适用性
本内容介绍GROMACS 2018.8在Linux下的编译和安装方法，该方法对GROMACS 2018及之后的各个版本（经测试一直到2025.x版）均完全适用。该安装方法基于CentOS 7.6系统，实测对CentOS/RockyLinux 8、9也完全适用，安装目录默认为/sob，编译使用系统自带的gcc编译器。对于GROMACS在Windows下的编译安装，请参阅《GROMACS的原生Windows版的编译和安装方法》。

---

## 2. GROMACS各版本对编译器和系统环境的最低要求
从GROMACS 2020开始要求gcc编译器版本>=5，CentOS 7.x自带的gcc 4.8.5无法直接安装，需升级gcc或使用CentOS/RockyLinux >=8.0版。从GROMACS 2021开始要求cmake版本>=3.17，CentOS/RockyLinux 8软件源里的cmake版本偏老，必须手动安装cmake。从GROMACS 2025开始要求gcc 11和cmake>=3.28，CentOS/RockyLinux 8的gcc太老而无法安装，RockyLinux 9的cmake可能需要手动安装。

---

## 3. 使用yum安装cmake 3.x
GROMACS 2018需要cmake 3.x才能编译，CentOS 7.6自带版本太旧需更新。首先运行`yum install epel-release`添加EPEL源，然后运行`yum install cmake3`下载安装，安装完成后输入`cmake3 /V`命令，若显示3.x版本号则说明安装成功。

---

## 4. 手动编译安装cmake 3.x
若无管理员权限或系统源cmake版本太老，需去。解压后进入目录，运行`./bootstrap --prefix=/sob/cmake3 -- -DCMAKE_USE_OPENSSL=OFF`，接着运行`make -j`和`make install`。安装后需在~/.bashrc中加入`export PATH=/sob/cmake3/bin:$PATH`，重新进入终端后即可使用cmake命令。

---

## 5. 编译安装FFTW库
GROMACS 2018依赖FFTW 3.3.8库，可从。解压后进入目录，运行`./configure --prefix=/sob/fftw338 --enable-sse2 --enable-avx2 --enable-float --enable-shared`进行配置，其中若CPU较老不支持AVX2指令集需将--enable-avx2改为--enable-avx。配置完成后运行`make install -j`进行编译安装，最终程序安装在/sob/fftw338目录。

---

## 6. GROMACS源码的编译与安装步骤
下载GROMACS 2018.8压缩包并解压到/sob目录。进入解压目录后依次运行：`mkdir build`、`cd build`、`export CMAKE_PREFIX_PATH=/sob/fftw338`、`cmake3.. -DCMAKE_INSTALL_PREFIX=/sob/gmx2018.8`（CentOS 8+或手动编译cmake时命令为cmake）、`make install -j`。编译安装完成后程序位于/sob/gmx2018.8目录。

---

## 7. 配置环境变量与验证GROMACS安装
修改用户目录下的.bashrc文件，在末尾加入`source /sob/gmx2018.8/bin/GMXRC`。保存并关闭终端重新打开，输入`gmx -version`命令，若输出GROMACS的相关信息则说明安装成功。

---

## 8. GROMACS编译时的并行注意事项与SIMD指令检测
使用make -j进行并行编译可降低耗时，但在虚拟机下可能卡住，若出错请去掉-j选项。运行cmake命令后需仔细查看屏幕提示，确认当前CPU支持的SIMD指令集是否被正确判断，若CPU较新而GROMACS版本较老导致SIMD未被识别，会导致mdrun运行速度非常慢。

---

## 9. GROMACS运行速度慢的排查与手动指定SIMD指令
使用gmx mdrun运行任务时若提示WARNING: Using the slow plain C kernels，说明编译时未利用CPU的SIMD指令集，导致运行速度比理想情况慢N倍。解决方法是重新编译，在使用cmake3时明确指定指令集，例如对于支持AVX2指令集的CPU（XEON v3系列及之后）加上`-DGMX_SIMD=AVX2_256`。

---

## 10. 编译支持CUDA GPU加速的GROMACS版本
GROMACS支持nVidia GPU通过CUDA加速，需先下载CUDA toolkit并安装到默认路径。编译方法与前述相同，但在cmake步骤需额外加上`-DGMX_GPU=CUDA -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda`（若安装GROMACS < 2021版，-DGMX_GPU=CUDA应改为-DGMX_GPU=ON）。

---

## 11. 控制GROMACS是否使用GPU加速的方法
安装了GPU版GROMACS后，运行gmx mdrun时会自动检测并使用nVidia GPU。若不使用GPU加速，可在mdrun命令后加上`-nb cpu -pme cpu -bonded cpu`强制只使用CPU计算；或者编译一个不带GPU支持的版本（加上`-DGMX_GPU=OFF`）并source对应的GMXRC。

---

## 12. 在GROMACS安装过程中自动安装FFTW库
FFTW库可不手动安装，在编译GROMACS时自动下载安装。方法是在cmake步骤中忽略FFTW路径设置，并加上`-DGMX_BUILD_OWN_FFTW=ON`选项。由于国内访问FFTW官网速度较慢可能导致下载卡住，通常仍建议手动安装FFTW库。

---

## 13. 编译GROMACS双精度版本的目的与代价
双精度版本可解决模拟初期崩溃问题，或在正则振动分析（能量极小化和对角化Hessian矩阵）时确保数值精度。双精度版本计算比单精度慢近一倍，trr/edr等文件体积大一倍，且不支持GPU加速。

---

## 14. GROMACS双精度版本的编译方法
先按前文编译单精度版本，再重复一遍过程：编译FFTW时去掉--enable-float选项，在使用cmake3命令时加上`-DGMX_DOUBLE=ON`选项。双精度版本可执行文件名为gmx_d，与单精度的gmx可共存于同一目录。

---

## 15. GROMACS MPI版本的编译依赖与OpenMPI安装
GROMACS跨节点并行需MPI库（支持OpenMPI>=1.6、MPICH>=1.4.1）。下载OpenMPI最新版并解压，进入目录运行`./configure --prefix=/sob/openmpi`，然后运行`make all install -j`。安装后需在~/.bashrc末尾添加`export PATH=$PATH:/sob/openmpi/bin`和`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/openmpi/lib`，重新进入终端生效。

---

## 16. GROMACS MPI版本的编译与运行
安装好OpenMPI后，编译GROMACS时在cmake步骤加上`-DGMX_MPI=ON`选项。编译出的可执行文件为gmx_mpi，运行时使用`mpirun -np 16 gmx_mpi mdrun`形式的命令。单机并行使用MPI版效率低于基于thread-MPI和OpenMP的默认方式，不建议单机用户安装MPI版。

---

## 17. 处理AVX512指令集编译报错的方法
若CPU支持AVX512但gcc版本太老不支持，编译时会报错。解决方法是更新gcc，或者在cmake步骤加上`-DGMX_SIMD=AVX2_256`选项降级使用AVX2指令集。
