---
key: t44594
title: Rocky linux 9.3����intel oneAPI 2024.1����vasp6.4.2
url: http://bbs.keinsci.com/thread-44594-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 5
---

# Rocky linux 9.3����intel oneAPI 2024.1����vasp6.4.2 — 知识卡片

## 1. Intel oneAPI 2024.1.0 安装与环境配置

Intel oneAPI 2024.1.0 是 VASP 6.4.2 编译的基础环境，需下载并安装 Intel oneAPI Base Toolkit 和 Intel HPC Toolkit。安装完成后需配置环境变量，通过修改 `~/.bashrc` 文件并添加 `source /opt/intel/oneapi/setvars.sh intel64` 来加载相关库。

---

## 2. VASP 6.4.2 源码解压与 Makefile 配置

解压 `vasp.6.4.2.tar.gz` 后，需将 `arch/makefile.include.linux_intel` 复制至上一级目录并重命名为 `makefile.include`。在文件中需指定预处理器和编译器路径，例如设置 `PP = fpp -f_com=no -free -w0 $*$(FUFFIX) $*$(SUFFIX) $(CPP_OPTIONS)`，并将 Fortran 编译器 `FC` 和链接器 `FCL` 设为 `mpiifx`。

---

## 3. VASP 库文件编译参数设置

针对 vasp.5.lib 和解析库部分，需分别设置 C 和 Fortran 编译器参数。`CC_LIB` 设为 `icx`，`CXX_PARS` 设为 `icpx`，优化标志 `CFLAGS_LIB` 设为 `-O`，`FFLAGS_LIB` 设为 `-O1`，同时需链接 C++ 标准库 `LLIBS = -lstdc++`。

---

## 4. VASP Intel MKL 链接配置

编译 VASP 时需链接 Intel MKL 库以使用 FFTW、BLAS、LAPACK 和 scaLAPACK。设置 `MKLROOT = /opt/intel/oneapi/mkl/2024.0`，并在 `FCL` 中添加 `-mkl=sequential` 参数。若出现 `/bin/sh: line 1: -o: command not found` 错误，需确保该参数前无多余空格或换行符。

---

## 5. VASP 编译与运行环境配置

修改完 `makefile.include` 后，执行 `make all` 命令进行编译。编译成功后，需将二进制文件路径加入环境变量，在 `~/.bashrc` 中添加 `export PATH=$PATH:/opt/vasp.6.4.2/bin`。运行时使用 `mpirun -np 48 vasp` 命令调用 48 核进行计算。
