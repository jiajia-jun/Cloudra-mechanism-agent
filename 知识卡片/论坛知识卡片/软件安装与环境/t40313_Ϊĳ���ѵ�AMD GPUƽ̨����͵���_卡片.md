---
key: t40313
title: Ϊĳ���ѵ�AMD GPUƽ̨����͵���LAMMPS��GROMACS
url: http://bbs.keinsci.com/thread-40313-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 9
---

# Ϊĳ���ѵ�AMD GPUƽ̨����͵���LAMMPS��GROMACS — 知识卡片

## 1. ROCm 软件栈及 AMD GPU 驱动安装

ROCm 软件栈与 AMD GPU 内核驱动可通过 `amdgpu-install` 元数据包自动安装。为避免 `apt` 下载异常，推荐先手动下载 `.deb` 包至 `/var/cache/apt/archives` 目录，再执行安装。安装完成后，需将使用 GPU 的用户加入 `render` 组，并重启系统。验证安装成功的标志是普通用户可执行 `rocminfo` 命令。
- `apt install ./amdgpu-install_5.7.50700-1652687.22.04_all.deb`
- `amdgpu-install --usecase=rocm,hiplibsdk`
- `usermod -a -G render [用户名]`

---

## 2. AMD 平台 LAMMPS 编译环境配置

在 AMD GPU 上编译 LAMMPS 需使用新版 Kokkos (4.1.0) 替换官方源码 `lib/kokkos` 目录中的旧版本。修改 `cmake/CMakeLists.txt` 第 146、147 行中的版本号从 14 改为 17。新版 Kokkos 可从 GitHub 官方仓库发布的 Release 中获取。
- 修改路径: `cmake/CMakeLists.txt`

---

## 3. 基于 HIP 的 LAMMPS 编译步骤

在 AMD 平台上使用 HIP 后端编译 LAMMPS 需指定 `GPU_API=HIP` 和显卡架构（如 `gfx1030`）。编译过程依赖预设文件 `basic.cmake` 和 `kokkos-hip.cmake`，并需设置 `CMAKE_CXX_COMPILER` 为 `hipcc`。使用 `cmake --build` 进行多线程编译，生成的可执行文件位于构建目录中。
- `cmake -C ../cmake/presets/basic.cmake -C ../cmake/presets/kokkos-hip.cmake -D GPU_API=HIP -D HIP_ARCH=gfx1030 -D CMAKE_CXX_COMPILER=hipcc -D HIP_PATH=/opt/rocm/hip/bin ../cmake`
- `cmake --build . -j24`

---

## 4. LAMMPS AMD 平台运行环境变量优化

在 AMD 平台上运行 LAMMPS 需正确设置 OpenMP 线程数及 CPU 亲和性以获得最佳性能。对于 Ryzen 5900X (12核24线程)，建议根据绑定的 GPU 数量分配 CPU 核心，并设置 `OMP_NUM_THREADS` 和 `GOMP_CPU_AFFINITY`。若单 GPU 绑定核心 6-11，则设置 `OMP_NUM_THREADS=6`；若四 GPU 运行，则每个进程分配 3 个线程并指定对应的核心范围。
- `export OMP_NUM_THREADS=[每个MPI进程的CPU线程数]`
- 单 GPU 示例: `GOMP_CPU_AFFINITY=6-11`
- 四 GPU 示例: `OMP_NUM_THREADS=3`, `GOMP_CPU_AFFINITY` 分别为 `0-2`, `3-5`, `6-8`, `9-11`

---

## 5. WSL 环境下 LAMMPS 的 NVIDIA GPU 编译

在 WSL 环境下为 NVIDIA GPU 编译 LAMMPS 需预装 CUDA Toolkit。编译时使用官方预设 `basic.cmake`，并设置 `GPU_API=CUDA` 和对应的 GPU 架构（如 RTX 4060 的 `sm_89`）。WSL 环境下不使用 Kokkos 加速。
- `cmake -C ../cmake/presets/basic.cmake -D GPU_API=CUDA -D GPU_ARCH=sm_89 ../cmake`

---

## 6. WSL 环境 CPU 线程限制与性能

WSL 环境下无法直接控制 CPU 亲和性，建议设置 `OMP_NUM_THREADS=2` 以让 Windows 系统进行线程调度。对于拥有双 CCD 的 Ryzen 7945HX 处理器，WSL 进程可能被分配在第二个 CCD 上。在该环境下进行 MD 模拟的速度可能比原生 Linux 环境慢约 50%。
- `export OMP_NUM_THREADS=2`

---

## 7. AdaptiveCpp (hipSYCL) 编译配置

AdaptiveCpp (原 hipSYCL) 需配置 ROCm 后端进行编译，并指定 ROCm 路径及 LLVM 工具链。编译选项中需开启 `WITH_ROCM_BACKEND=ON` 并关闭 SSCP 编译器 (`WITH_SSCP_COMPILER=OFF`)。安装路径可自定义，便于后续 GROMACS 编译调用。
- `cmake -D CMAKE_INSTALL_PREFIX=/opt/AdaptiveCppDev20231011.rocm570 -D CMAKE_C_COMPILER=/opt/rocm/llvm/bin/clang -D CMAKE_CXX_COMPILER=/opt/rocm/llvm/bin/clang++ -D WITH_ROCM_BACKEND=ON -D ROCM_PATH=/opt/rocm -D LLVM_DIR=/opt/rocm/llvm/lib/cmake/llvm -D WITH_SSCP_COMPILER=OFF ..`
- `make -j24 install`

---

## 8. GROMACS 基于 SYCL 的 AMD GPU 编译

编译支持 AMD GPU 的 GROMACS 需使用 AdaptiveCpp 提供的 SYCL 实现。CMake 配置需指定 AdaptiveCpp 的前缀路径、ROCm 的编译器，并开启 `GMX_GPU=SYCL` 及 `GMX_SYCL_HIPSYCL=ON`，同时设定目标 GPU 架构。建议开启 `GMX_BUILD_OWN_FFTW=ON` 以构建自带 FFTW 库。
- `cmake -D CMAKE_PREFIX_PATH=/opt/AdaptiveCppDev20231011.rocm570 -D CMAKE_INSTALL_PREFIX=/opt/gmx2023.2_sycldev20231011_rocm570_gfx1030 -D CMAKE_C_COMPILER=/opt/rocm/llvm/bin/clang -D CMAKE_CXX_COMPILER=/opt/rocm/llvm/bin/clang++ -D GMX_GPU=SYCL -D GMX_SYCL_HIPSYCL=ON -D HIPSYCL_TARGETS=hip:gfx1030 -D GMX_BUILD_OWN_FFTW=ON ..`
- `source /opt/gmx2023.2_sycldev20231011_rocm570_gfx1030/bin/GMXRC`

---

## 9. GROMACS 运行参数推荐

在 AMD 平台上运行 GROMACS 推荐将键合计算分配给 GPU (`-bonded gpu`) 并开启线程绑定 (`-pin on`)。针对 Ryzen 5900X 硬件，建议设置单 MPI 进程 (`-ntmpi 1`) 配合 23 个 OpenMP 线程 (`-ntomp 23`)。使用此参数运行 STMV-GMX 体系速度可达 15ns/day。
- `gmx mdrun -v -deffnm [tpr文件名] -pin on -bonded gpu -pinoffset 0 -pinstride 1 -ntmpi 1 -ntomp 23 -gpu_id 0`
