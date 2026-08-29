---
key: t26775
title: QE GPU�汾ʹ�á��������¡�
url: http://bbs.keinsci.com/thread-26775-1-1.html
domain: 其他量化软件
source: keinsci
year: 2021
cards: 7
---

# QE GPU�汾ʹ�á��������¡� — 知识卡片

## 1. Quantum Espresso GPU 版本获取方式

从 Quantum Espresso 6.6a1 版本开始，用户可以从 NVIDIA NGC 目录（目前最新为 qe-7.0）获取预编译的 QE GPU 版本容器。该方式支持通过 Singularity、Docker 或 Slurm 等方式进行部署，具体步骤可参考 NGC 页面 Overview 中的说明。

---

## 2. QE GPU 版源码编译环境要求

编译 QE GPU 版源码推荐使用 NVIDIA HPC SDK，因为构建过程涉及修改通信库接口并对接数学库。HPC SDK 包含了编译所需的 nvfortran 编译器、CUDA 环境、cuFFT、cuBLAS、cuSolver、OpenMPI 等组件。

---

## 3. NVIDIA HPC SDK 安装步骤

在 NVIDIA 官网下载 HPC SDK 安装包后，依次执行解压和安装脚本。例如下载 `nvhpc_2021_219_Linux_x86_64_cuda_11.4.tar.gz` 后，运行 `tar xpzf` 解压，并执行解压目录下的 `install` 程序，根据提示选择安装路径即可。

---

## 4. QE GPU 版源码下载与配置命令

使用 Git 克隆 QEF 的 q-e-gpu 仓库并指定分支（如 qe-gpu-6.8），加载 HPC SDK 模块并设置 CUDADIR 路径后运行配置脚本。配置命令需指定 CUDA 路径、运行时版本、计算能力（如 70）、开启 OpenMP 以及禁用 ScaLAPACK，并链接相关数学库路径。

---

## 5. QE GPU 版编译与运行命令

配置完成后，使用 `make pw -j 8` 命令进行编译。运行程序时，通过 `mpirun` 指定进程数（通常对应 GPU 数量）并调用编译生成的 `pw.x` 可执行文件读取输入文件。

---

## 6. QE GPU 版编译参数优化选项

为获得更好的计算性能，可修改生成的 `make.inc` 文件，将 `DFLAGS` 中的 `-D__FFTW` 替换为 `-D__FFTW3`，并添加 `-D__GPU_MPI` 选项。

---

## 7. QE GPU 版运行环境设置

在运行 QE GPU 版本时，建议通过 `export OMP_NUM_THREADS=8` 设置环境变量以指定 OpenMP 线程数。对于使用共享 GPU 资源（如 V100）的情况，推荐启用 MPS（Multi-Process Service）以提升性能。
