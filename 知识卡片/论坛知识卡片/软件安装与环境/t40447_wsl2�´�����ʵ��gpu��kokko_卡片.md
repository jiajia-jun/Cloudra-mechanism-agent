---
key: t40447
title: wsl2�´�����ʵ��gpu��kokkos����lammps��װ����
url: http://bbs.keinsci.com/thread-40447-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 13
---

# wsl2�´�����ʵ��gpu��kokkos����lammps��װ���� — 知识卡片

## 1. LAMMPS 编译工具选择

LAMMPS 编译过程如果遇到 `make` 命令无法识别 `quip_root` 等问题，推荐使用 `cmake` 进行构建以解决相关报错。该方法能够有效规避使用 `make` 时可能遇到的依赖缺失或路径识别错误。

---

## 2. FFTW 依赖安装

安装 FFTW 依赖时，若使用系统包管理器无法成功安装所需版本，可直接使用 LAMMPS 源码附带的版本。在实际操作中，使用命令 `sudo apt-get install libfftw3*` 通常能够完成所需库文件的安装。

---

## 3. MPICH 安装与配置

在 Windows 11 的 WSL2 环境下，若命令 `sudo apt-get install mpi-default-*` 无法成功安装 MPICH，可选择手动下载源码包安装。下载 mpich4.1.3 压缩包并解压移动到安装位置后，需注意将安装路径添加到系统环境变量中，以确保系统能正确找到 MPICH。

---

## 4. CUDA Windows 驱动安装

在 WSL2 环境安装 CUDA 之前，必须先在 Windows 系统上安装显卡驱动，驱动下载地址为 NVIDIA 官网。安装时需注意选择 Windows 11 系统对应的版本，并务必勾选“精简安装”选项，避免因安装默认版本导致驱动更新失效或无法被 WSL 识别。

---

## 5. CUDA WSL 版本下载

WSL-Ubuntu 环境下 CUDA 安装包需选择 Linux 系统下的 WSL-Ubuntu 2.0 版本，安装格式建议选择 `deb(local)`，不要选择 `runfile(local)` 格式。按照此流程操作通常可以顺利完成 CUDA 的安装。

---

## 6. CUDA 环境变量验证

安装 CUDA 后需在 `.bashrc` 文件中加入环境变量，随后执行 `nvcc -V` 命令检查版本以确认安装成功。需要注意的是命令中的 `V` 为大写，若使用小写可能会报错或显示不正确，若仍提示未找到命令则说明环境变量配置可能存在问题。

---

## 7. Kokkos GPU 架构配置

编译带有 Kokkos GPU 包的 LAMMPS 时，若需指定显卡架构，不应直接修改 `kokkos-cuda.cmake` 文件。正确的做法是在使用 `cmake` 命令编译时，直接将参数中的 `GPU_ARCH=sm_75` 等数值修改为与自身显卡对应的数字代号。

---

## 8. libcuda.so.1 报错解决

编译过程中若出现 `libcuda.so.1 is not a symbolic link` 报错，可参考相关网络教程中的方法进行修复。该问题通常是由于符号链接丢失或配置错误导致的。

---

## 9. cannot find -lpthreads 报错解决

若编译时出现 `/usr/bin/ld: cannot find -lpthreads` 错误，系统可能缺少相关依赖库。安装 `libpthread-stubs0-dev` 库通常可以解决该链接错误。

---

## 10. 编译内存不足

编译过程中若出现 `c++: fatal error: Killed signal terminated program cc1plus` 错误，通常是因为系统内存不足。解决方法包括增加 swap 分区或减少 `make -j` 命令中的并行编译线程数。

---

## 11. CMake 运行时库路径警告

在 CMake 生成阶段若出现关于 `libcuda.so.1` 在 `/usr/local/cuda-12.3/.../lib/stubs` 可能被 `/usr/lib/wsl/lib` 隐藏的警告，这通常属于路径重复提示。在实际运行中该警告一般不影响程序的正常功能。

---

## 12. CUDA 12.5 CUFFT 库路径错误

在 Ubuntu 24.04 配合 CUDA 12.5 环境下，使用 `cmake` 预设文件编译时可能会报错找不到 cuFFT 库。这是因为 CUDA 12.5 安装目录下缺少 `lib64` 文件夹，而 `cufft` 文件位于 `/usr/local/cuda-12.5/targets/x86_64-linux/lib/` 目录中。

---

## 13. 手动指定 CUFFT 库路径

针对 CUDA 12.5 cuFFT 库找不到的问题，可以在 `cmake` 命令中手动指定库路径来解决。具体方法是在命令中加入 `-DCUFFT_LIBRARY=/usr/local/cuda-12.5/targets/x86_64-linux/lib/libcufft.so` 参数。
