---
key: b455
title: VASP最简单的安装方法（含全程视频演示）
url: http://sobereva.com/455
domain: 软件安装与环境
source: blog
year: 2019
cards: 8
---

# VASP最简单的安装方法（含全程视频演示） — 知识卡片

## 1. VASP安装的系统环境要求

VASP 5.4.4 推荐在 CentOS 7.6 系统下使用 Intel Parallel Studio XE 2019 Update 1（包含 ifort 19.0.1 编译器）进行编译。Intel 编译器需获取试用版，CentOS 系统因其免费、稳定及良好的兼容性被视为适合计算化学研究的操作系统。若使用不同版本的系统、程序或编译器，安装步骤可能需要相应调整。

---

## 2. Intel编译器与依赖库的安装组件

安装 Intel Parallel Studio XE 时需选择特定组件，包括 Intel Fortran Compiler、Intel C++ Compiler、Intel Math Kernel Library (MKL) 中的核心库及集群支持、Intel MPI Library 以及 Intel Threading Building Blocks (TBB)。安装过程中无需安装 IA32 版组件，若提示缺少 32 位库可忽略并继续安装。

---

## 3. Intel编译器环境配置与MKL库编译

安装完成后需在用户目录下的 .bashrc 文件末尾添加 `source /opt/intel/parallel_studio_xe_2019/psxevars.sh` 以配置环境变量。之后需进入 `/opt/intel/compilers_and_libraries_2019.1.144/linux/mkl/interfaces/fftw3xf` 目录，运行 `make libintel64` 命令生成 libfftw3xf_intel.a 库文件。

---

## 4. VASP编译的makefile配置

解压 VASP 5.4.4 源码包后，需将 arch/makefile.include.linux_intel 文件拷贝至源码根目录并重命名为 makefile.include。为优化计算性能，应在该文件的 OFLAG 参数中加入 `-xhost` 选项，使程序自动利用 CPU 支持的最高指令集。

---

## 5. VASP的编译与可执行文件生成

在 VASP 源码目录下运行 `make all` 命令开始编译，编译过程通常持续半小时到一小时。编译完成后在 bin 目录下会生成 vasp_gam (Gamma only版)、vasp_ncl (非共线版) 和 vasp_std (标准版) 三个可执行文件。

---

## 6. VASP运行路径配置

为方便调用 VASP，可将最常用的 vasp_std 可执行文件重命名为 vasp。同时在 ~/.bashrc 文件末尾添加 `export PATH=$PATH:/sob/vasp.5.4.4/bin`，将 bin 目录加入系统环境变量 PATH 中。

---

## 7. VASP安装正确性测试

下载含 50 个 Hg 原子的标准测试任务包并解压，使用 IN-short 作为 INCAR 文件。在终端输入 `mpirun -np 4 vasp` 调用四个核心执行测试任务，通过检查生成的 OUTCAR 文件内容是否正常来验证安装是否成功。

---

## 8. 运行异常时的堆栈内存设置

如果运行用户自建任务出现异常，可在 ~/.bashrc 文件中加入 `ulimit -s unlimited` 命令。该命令用于解除操作系统对堆栈内存可用尺寸的过严限制，解决潜在的运行问题。
