---
key: t27603
title: WSL2��gpu��lammps������ϸ��
url: http://bbs.keinsci.com/thread-27603-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 10
---

# WSL2��gpu��lammps������ϸ�� — 知识卡片

## 1. WSL2 对计算化学的适用性

WSL2 可在 Windows 11/10 系统中运行 Linux 环境，适合进行计算化学模拟。WSL2 支持调用 GPU，能够满足 LAMMPS 等程序对算力的需求。对于仅使用 CPU 的传统计算任务，WSL2 也是一个可行的选择。

---

## 2. Windows 驱动与系统版本要求

在 WSL2 中使用 GPU 需要在 Windows 端安装支持 CUDA 的 NVIDIA 驱动（如 510.06）。安装驱动后，需在 WSL2 终端中执行 `nvidia-smi` 以验证 GPU 可用性。系统版本建议更新至 Windows 10 21H2 或更高版本以确保兼容性。

---

## 3. 安装基础编译工具与依赖库

LAMMPS 编译需要 gcc、g++、gfortran、MPI 及 FFTW 库支持。在 Ubuntu 环境下，可通过以下命令安装必要组件：
```bash
sudo apt-get install gcc
sudo apt-get install g++
sudo apt-get install gfortran
sudo apt-get install mpi-default-*
sudo apt-get install libfftw3*
```
GROMACS 等其他软件通常也依赖这些基础库。

---

## 4. CUDA Toolkit 在 WSL2 中的安装

CUDA Toolkit 版本应与 `nvidia-smi` 显示的驱动版本相匹配（如 11.6），且需下载 WSL-Ubuntu 专用版本。安装命令如下：
```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-wsl-ubuntu.pin
sudo mv cuda-wsl-ubuntu.pin /etc/apt/preferences.d/cuda-repository-pin-600
wget https://developer.download.nvidia.com/compute/cuda/11.6.0/local_installers/cuda-repo-wsl-ubuntu-11-6-local_11.6.0-1_amd64.deb
sudo dpkg -i cuda-repo-wsl-ubuntu-11-6-local_11.6.0-1_amd64.deb
sudo apt-key add /var/cuda-repo-wsl-ubuntu-11-6-local/7fa2af80.pub
sudo apt-get update
sudo apt-get -y install cuda-toolkit-11-6
```

---

## 5. 配置 CUDA 环境变量

CUDA Toolkit 安装完成后，需将路径添加至环境变量中。编辑 `~/.bashrc` 文件添加以下内容：
```bash
export PATH=$PATH:/usr/local/cuda-11.6/bin
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/cuda-11.6/lib64
```
配置完成后，通过 `nvcc -V` 或 `nvcc --version` 命令验证安装成功。

---

## 6. LAMMPS 源码下载与准备

LAMMPS 源码可通过官方链接下载并解压：
```bash
wget https://download.lammps.org/tars/lammps-stable.tar.gz
tar -xzf lammps-stable.tar.gz
```
进入源码目录后，需创建 build 文件夹并切换至该分支（建议切换至 master 分支）。

---

## 7. 使用 Cmake 编译 LAMMPS GPU 版本

编译 LAMMPS 需启用 MPI 及 GPU 支持，并指定计算架构。CMake 配置命令示例如下：
```bash
cmake -D BUILD_MPI=yes -D PKG_GPU=on -D GPU_API=cuda -D GPU_ARCH=sm_80 -DCMAKE_LIBRARY_PATH=/usr/local/cuda/lib64/stubs ../
```
`GPU_ARCH` 参数（如 sm_80）需根据显卡型号设置，具体可参考 NVIDIA 维基百科或查阅 `lammps/lib/gpu/Makefile.linux`。如需更改配置，建议先清理 build 目录。

---

## 8. 编译生成 LAMMPS 可执行文件

执行 `make -j` 进行编译。通过 CMake 编译生成的可执行文件名为 `lmp`，而非传统方式下的 `lmp_mpi` 或 `lmp_serial`。编译完成后，建议将 `lmp` 所在路径添加至 `~/.bashrc` 的 PATH 环境变量中。

---

## 9. LAMMPS MPI 与 GPU 运行效率对比

在 10900K + 3060 的硬件配置下测试 `examples/shear` 算例：使用 10 核心 MPI 运行速度约为 285.512 ns/day；使用 GPU 加速（`lmp -sf gpu -in`）速度约为 368.660 ns/day。GPU 加速模式在该体系下表现优于纯 MPI 模式。

---

## 10. 体系规模对计算效率的影响

对于原子数较少的体系（如 2 万原子以下），计算速度可能受限且性价比不高。提升原子规模至 5-6 万个可显著提升加速比和计算效率。高性能显卡（如 3080Ti）能进一步提升计算效果。
