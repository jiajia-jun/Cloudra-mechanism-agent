---
key: t59940
title: win10+wsl2+rocky10.2ƽ̨�±��밲װkokkosbn�汾��lammps
url: http://bbs.keinsci.com/thread-59940-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2026
cards: 24
---

# win10+wsl2+rocky10.2ƽ̨�±��밲װkokkosbn�汾��lammps — 知识卡片

## 1. 硬件测试环境配置

测试平台配置为 AMD 5700X3D 处理器、RTX 5060 显卡以及 2 条 16GB 3600MHz 内存。此环境用于评估 LAMMPS 在 GPU 与 CPU 模式下的计算性能差异。

---

## 2. GPU 模式运行性能

在指定硬件环境下运行 LAMMPS GPU 模式，使用命令 `mpirun --allow-run-as-root -np 1 lmp-mixed -k on g 1 -sf kk -in in.eam`。测试结果显示性能为 430.244 ns/day，995.936 timesteps/s，CPU 占用率为 86.8%（1 MPI 任务 x 1 OpenMP 线程）。

---

## 3. CPU 模式运行性能

在相同硬件环境下运行 LAMMPS CPU 模式，使用命令 `mpirun --allow-run-as-root -np 8 lmp-mixed -in in.eam`。测试结果显示性能为 71.470 ns/day，165.440 timesteps/s，CPU 占用率为 98.9%（8 MPI 任务 x 1 OpenMP 线程）。

---

## 4. 基础开发库安装

在编译 LAMMPS 及相关工具前，需安装基础数学库和编译工具。使用命令 `sudo dnf install blas-devel lapack-devel` 和 `sudo dnf install -y fftw-devel` 安装数学库，使用 `sudo dnf install gcc gcc-c++ gcc-gfortran` 安装 GCC/G++ 编译器套件。

---

## 5. CUDA 版本与 GCC 版本兼容性

在安装 CUDA Toolkit 和 GCC 时，需注意两者版本之间的兼容性。不匹配的版本组合可能导致编译失败或运行时错误。

---

## 6. OpenMPI 编译配置

下载 OpenMPI 源码并解压后，执行 `./configure --prefix=/usr/local/openmpi` 进行配置。若配置输出显示 `CUDA support: no`，则表明当前环境未正确识别 CUDA，需在安装 CUDA 后重新编译 OpenMPI 以启用支持。

---

## 7. CUDA Toolkit 依赖安装

编译 OpenMPI 之前，需先安装 libtool、autoconf 和 zlib 等依赖工具。可使用命令 `sudo dnf groupinstall "Development Tools" -y && sudo dnf install zlib-devel -y` 进行安装。

---

## 8. 通过 nvidia-smi 确认 CUDA 版本

安装 CUDA Toolkit 前，应通过 `nvidia-smi` 命令查看显卡驱动所支持的 CUDA 最高版本。根据显示的版本选择合适的 CUDA Toolkit 进行下载和安装。

---

## 9. CUDA Toolkit 源安装方法

对于支持的系统，可通过添加 NVIDIA 官方仓库并使用包管理器安装 CUDA Toolkit。命令示例为：`sudo dnf config-manager --add-repo <repo-url>`，随后执行 `sudo dnf clean all` 和 `sudo dnf -y install cuda-toolkit-13-0`。

---

## 10. CUDA Toolkit 本地包安装方法

若在线安装失败，可下载 RPM 本地包进行安装。使用 `wget` 下载 rpm 文件后，执行 `sudo rpm -i <package.rpm>` 导入 GPG key 和仓库，最后运行 `sudo dnf -y install cuda-toolkit-13-0` 完成安装。

---

## 11. CUDA 环境变量配置

安装 CUDA Toolkit 后，需配置环境变量 `PATH` 和 `LD_LIBRARY_PATH`。通过命令 `echo 'export PATH=/usr/local/cuda-13.0/bin:$PATH' >> ~/.bash_profile` 和库路径设置将路径加入配置文件，并执行 `source ~/.bash_profile` 生效。

---

## 12. WSL 2 环境下的 CUDA 约束

在 WSL 2 环境中，直接安装 Linux NVIDIA 显卡驱动是无效的，应使用 Windows 系统下的显卡驱动。WSL 2 会将 Windows 中的 `libcuda.so` 动态映射到内部使用。

---

## 13. WSL 2 的 CUDA Toolkit 安装注意事项

在 WSL 2 中安装 CUDA Toolkit 时，应下载专门针对 WSL-Ubuntu 的版本。安装时需取消勾选默认自带的驱动程序（如 `cuda-drivers`），仅安装 `cuda-toolkit` 组件，以免与 Windows 主机驱动冲突。

---

## 14. WSL 2 下 nvidia-smi 路径修复

若 WSL 2 环境下无法直接使用 `nvidia-smi` 命令，可尝试手动将 `/usr/lib/wsl/lib/` 路径添加到环境变量中。编辑 `~/.bash_profile` 添加 `export PATH="$PATH:/usr/lib/wsl/lib"` 并重新加载配置。

---

## 15. 启用 CUDA 支持的 OpenMPI 编译

在 CUDA 环境配置完成后，需重新配置和编译 OpenMPI 以启用 CUDA 支持。配置命令示例为 `./configure --prefix=/usr/local/openmpi-cuda13.0 --with-cuda=/usr/local/cuda-13.0`，成功时应显示 `CUDA support: yes`。

---

## 16. 编译 OpenMPI

OpenMPI 配置完成后，使用命令 `make -j$(nproc)` 开始多核编译。编译完成后使用 `sudo make install` 将程序安装到指定目录。

---

## 17. LAMMPS 编译前环境检查

开始编译 LAMMPS 前，需验证编译器和依赖库版本。关键检查命令包括 `gcc --version`、`g++ --version`、`mpirun --version`、`nvcc -V` 以及 `nvidia-smi`。

---

## 18. 查询 GPU 架构与计算能力

在配置 LAMMPS 编译选项时，需通过 `nvidia-smi --query-gpu=name,compute_cap --format=csv` 查询显卡名称和计算能力。示例显示 NVIDIA GeForce RTX 5060 的计算能力为 12.0。

---

## 19. LAMMPS Kokkos 版本 CMake 配置

使用 CMake 编译 LAMMPS Kokkos 版本时，需指定预设文件、安装路径及 GPU 架构。配置命令包含 `-D Kokkos_ARCH_BLACKWELL120=ON`（针对 RTX 5060）和 `-D KOKKOS_PREC=mixed`（混合精度）等参数。

---

## 20. KOKKOS_PREC 精度设置

在 CMake 配置 LAMMPS Kokkos 时，`-D KOKKOS_PREC` 参数用于设置计算精度。可选值包括 `mixed`（混合精度）、`double`（双精度）和 `single`（单精度）。

---

## 21. LAMMPS 编译与安装

CMake 配置完成后，执行 `make -j$(nproc)` 进行编译。编译结束后运行 `make install` 将相关文件转移至指定的安装路径（如 `/chens/lammps/lammps-kokkos-mixed`）。

---

## 22. 创建 LAMMPS 执行命令软链接

为了方便调用，可将编译生成的 LAMMPS 可执行文件链接到系统 PATH 目录下。使用命令 `ln -sf /chens/lammps/lammps-kokkos-mixed/bin/lmp /usr/local/bin/lmp-mixed` 创建名为 `lmp-mixed` 的软链接。

---

## 23. 验证 LAMMPS 安装与 Kokkos 配置

通过执行 `lmp-mixed -h` 可查看 LAMMPS 帮助信息以验证安装是否成功。使用 `KOKKOS_PRINT_CONFIGURATION=yes lmp-mixed -k on g 1 -in <(echo "info")` 可打印 Kokkos 运行时配置详情，包括线程和设备信息。

---

## 24. LAMMPS 运行命令参数详解

运行命令 `mpirun --allow-run-as-root -np 1 lmp-mixed -k on g 1 -sf kk -in in.eam` 中各参数含义如下：`--allow-run-as-root` 允许 root 用户直接运行 OpenMPI；`-np 1` 指定进程数（GPU 模式通常为 1）；`-k on g 1` 启用 Kokkos 加速并使用 1 块 GPU；`-sf kk` 自动加载 Kokkos 风格的原子对样式；`-in in.eam` 指定输入文件。
