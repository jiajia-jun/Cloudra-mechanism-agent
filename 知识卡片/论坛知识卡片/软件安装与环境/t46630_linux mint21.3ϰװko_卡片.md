---
key: t46630
title: ��linux mint21.3�ϰ�װ��kokkos�Լ�deepmd��lammps & 4090��reaxff����
url: http://bbs.keinsci.com/thread-46630-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 19
---

# ��linux mint21.3�ϰ�װ��kokkos�Լ�deepmd��lammps & 4090��reaxff���� — 知识卡片

## 1. Linux Mint 与 Ubuntu 环境兼容性

Linux Mint 21.3 基于 Ubuntu 22.04 开发，在此系统上安装 LAMMPS 等软件的过程与在 Ubuntu 22.04 上基本一致。安装过程中的依赖项和命令行操作可直接参考 Ubuntu 22.04 的相关教程。

---

## 2. CUDA 与 AOCC 基础环境安装

在 Linux 环境下进行高性能计算需预先安装 CUDA、cuDNN、AOCC 和 AOCL。推荐使用的软件版本为 CUDA 12.2 和 cuDNN 8.9.7，安装完成后可通过 `nvidia-smi` 和 `nvcc -V` 命令验证环境是否正常。

---

## 3. DeePMD-kit Conda 安装方式

DeePMD-kit 及 LAMMPS 接口可通过 Conda 快速安装。执行 `conda create -n deepmd deepmd-kit=*=*gpu libdeepmd=*=*gpu lammps cudatoolkit=11.8 horovod -c https://conda.deepmodeling.com -c defaults` 命令即可创建包含必要组件的环境。

---

## 4. DeePMD-kit 源码编译环境准备

若需从源码编译，首先需安装 TensorFlow 并配置 Python 虚拟环境。建议使用 Miniconda3 安装 Python 3.8，通过 virtualenv 创建独立环境并升级 pip，最后安装 TensorFlow 软件包。

---

## 5. TensorFlow 安装验证

完成 TensorFlow 安装后，可通过 Python 命令 `python -c "import tensorflow as tf;print(tf.reduce_sum(tf.random.normal([1000, 1000])))"` 进行测试。该命令若能正常输出数值，表明 TensorFlow 已安装成功且可用。

---

## 6. DeePMD-kit Python 接口源码安装

安装 TensorFlow 后，需从 GitHub 获取 DeePMD-kit 源码并编译其 Python 接口。执行 `git clone https://github.com/deepmodeling/deepmd-kit.git` 下载源码，并在源码目录下使用 `pip install .` 完成安装，过程中需确保 pip 版本为最新。

---

## 7. Horovod 与 MPI 并行库安装

为支持多 GPU 并行，需安装 Horovod、mpi4py 及 NCCL。安装命令为 `HOROVOD_WITHOUT_GLOO=1 HOROVOD_WITH_TENSORFLOW=1 HOROVOD_GPU_OPERATIONS=NCCL HOROVOD_NCCL_HOME=/path/to/nccl pip install horovod mpi4py`，需指定 NCCL 的安装路径。

---

## 8. DeePMD-kit C++ 接口编译

编译 DeePMD-kit C++ 接口需先使用源码目录下的 `source/install/build_tf.py` 脚本安装 TensorFlow C++ 库。随后创建 build 目录，使用 CMake 进行配置，参数需包含 `-DUSE_TF_PYTHON_LIBS=TRUE`、`-DLAMMPS_SOURCE_ROOT=/opt/dp_lammps/lammps-stable_2Aug2023_update1` 等，最后执行 `make` 和 `make install`。

---

## 9. LAMMPS 与 DeePMD 模块 Builtin 集成

将 DeePMD 模块以 Builtin 方式集成到 LAMMPS 中，需在编译 DeePMD-kit C++ 接口后执行 `make lammps`。在 LAMMPS 源码的 CMake 配置文件中需添加 `include(/opt/dp_lammps/deepmd-kit/source/lmp/builtin.cmake)` 指令。

---

## 10. LAMMPS CPU 模式编译配置

编译仅支持 CPU 的 LAMMPS 可执行文件时，CMake 配置需开启常规计算包（如 KSPACE、MANYBODY、REAXFF 等）并设置 `-D LAMMPS_MACHINE=cpu`。编译生成的可执行文件名为 `lmp_cpu`，安装路径由 `CMAKE_INSTALL_PREFIX` 指定。

---

## 11. LAMMPS GPU 模式 Makefile 配置

编译 GPU 模式 LAMMPS 前需修改 `lib/gpu/Makefile.linux` 文件。关键参数包括设置 `CUDA_HOME` 为 `/usr/local/cuda`，`CUDA_PRECISION` 为 `-D_SINGLE_DOUBLE`，以及根据显卡型号修改 `CUDA_ARCH`（例如 RTX 4090 对应 `-arch=sm_89`）。

---

## 12. LAMMPS GPU 模式 CMake 编译

配置 GPU 模式 LAMMPS 需在 CMake 命令中添加 `-D PKG_GPU=on`、`-D GPU_API=cuda` 和 `-D GPU_ARCH=sm_89`。其余软件包开启选项与 CPU 模式一致，编译完成后生成 `lmp_gpu` 可执行文件。

---

## 13. Kokkos CUDA 包编译 CUFFT 路径修复

在使用 CUDA 12 编译 LAMMPS Kokkos 包时，可能无法自动找到 `libcufft.so`。解决方法是在 CMake 命令中显式添加 `-D CUFFT_LIBRARY=/usr/local/cuda-12.2/lib64/libcufft.so` 参数以指定库文件路径。

---

## 14. Kokkos 架构适配文件修改

为适配特定显卡（如 RTX 4090），需修改源码中的 `kokkos-cuda.cmake` 文件。将文件中的 `MAXWELL50` 等旧架构名称替换为与目标显卡兼容的架构值（如 ADA_LOVELACE），可参考 LAMMPS 官方文档中的架构列表。

---

## 15. LAMMPS Kokkos GPU 模式编译命令

编译基于 Kokkos 的 GPU 版 LAMMPS 需使用预设文件 `kokkos-cuda.cmake` 并开启 GPU 包。完整的 CMake 命令需包含 `-D PKG_KOKKOS=on`、`-D PKG_GPU=on` 以及 `-D CUFFT_LIBRARY` 参数，最终生成支持 Kokkos 加速的可执行文件。

---

## 16. 环境变量配置与执行路径

编译完成后需将 LAMMPS 可执行文件所在目录添加至系统 PATH 环境变量。可在 `~/.bashrc` 文件中添加 `export PATH=$PATH:/opt/dp_lammps/dp/bin`，执行 `source ~/.bashrc` 后即可直接调用 `lmp`、`lmp_cpu` 或 `lmp_gpu`。

---

## 17. CPU 并行线程绑定设置

在多核 CPU 上运行 LAMMPS 时，建议通过环境变量绑定 CPU 核心以优化性能。可设置 `export OMP_NUM_THREADS=16` 指定线程数，并设置 `export GOMP_CPU_AFFINITY=0-31` 限定核心范围，实际数值需根据硬件配置调整。

---

## 18. 不同 LAMMPS 版本运行命令对比

不同后端的 LAMMPS 运行命令存在差异：CPU 版本使用 `mpirun --bind-to core -np 16 lmp_cpu -in in.reaxc`；GPU 版本使用 `lmp_gpu -in in.reaxc -sf gpu -pk gpu 1`；Kokkos 版本使用 `lmp -in in.reaxc -k on g 1 -sf kk -pk kokkos`。

---

## 19. ReaxFF 计算性能对比 (CPU vs GPU)

基于 ReaxFF 势函数的 1000 原子体系测试显示，单张 RTX 4090 的计算速度远超双路 AMD EPYC 9654 CPU。在测试案例中，GPU 加速比显著，4090 的速度约为 16 核 9654 CPU 的 5 倍。
