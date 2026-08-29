---
key: t46291
title: AMD Ryzen 7950X AMD RX 7900XT �� Debian 12 �°�װ GROMACS 2024.3
url: http://bbs.keinsci.com/thread-46291-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 12
---

# AMD Ryzen 7950X AMD RX 7900XT �� Debian 12 �°�װ GROMACS 2024.3 — 知识卡片

## 1. 安装 Spack 的依赖

在安装 Spack 之前，需要使用 apt 安装一系列基础构建工具和依赖库。这些依赖包括 build-essential、ca-certificates、coreutils、curl、environment-modules、gfortran、git、gpg、lsb-release、python3、python3-distutils、python3-venv、unzip 和 zip。
- apt update
- apt install build-essential ca-certificates coreutils curl environment-modules gfortran git gpg lsb-release python3 python3-distutils python3-venv unzip zip

---

## 2. 安装 Spack

Spack 可通过克隆 GitHub 仓库直接安装到指定目录（例如 /root/spack），安装后需在终端配置文件中设置环境变量并使其生效。建议在克隆仓库时启用 feature.manyFiles 配置以优化性能。
- export SPACK_ROOT=/root/spack
- git clone -c feature.manyFiles=true https://github.com/spack/spack.git ${SPACK_ROOT}

---

## 3. 配置 Spack 环境变量

安装 Spack 后，需将 SPACK_ROOT 环境变量和 Spack 的初始化脚本添加到 ~/.bashrc 文件中。完成配置后，需要重新登录终端或重新加载配置文件。
- export SPACK_ROOT=/root/spack
- source ${SPACK_ROOT}/share/spack/setup-env.sh

---

## 4. 添加系统默认编译器到 Spack

Spack 安装并配置环境变量后，可以使用 spack compiler find 命令自动搜索并将系统默认的编译器添加到 Spack 的编译器列表中。
- spack compiler find

---

## 5. 安装 AOCC

AMD Optimized C/C++ Compiler (AOCC) 可以通过 Spack 安装，安装时需要指定 +license-agreed 变量以同意许可协议。安装完成后，需要加载 AOCC 并将其作为编译器添加到 Spack 中。
- spack install aocc +license-agreed
- spack load aocc
- spack compiler find

---

## 6. 解决 ROCm 依赖 (libpython3.10)

在安装 ROCm 之前，系统需要具备 libpython3.10 等依赖库。对于不支持直接安装该库的系统（如 Debian 12），可以从 Ubuntu packages 网站下载 libpython3.10、libpython3.10-stdlib、libpython3.10-minimal 和 libmpdec3 的 .deb 包并手动安装。
- dpkg -i <package_name>

---

## 7. 安装 ROCm

安装完 Python 依赖后，可以使用 amdgpu-install 工具安装 ROCm（如版本 6.2.2），并指定使用 hiplibsdk 和 rocm 用例。安装完成后，需要将 root 用户添加到 render 组，并重启系统以使更改生效。
- amdgpu-install --usecase=hiplibsdk,rocm
- usermod -a -G render root
- reboot

---

## 8. 安装 AdaptiveCpp 的依赖

为支持 AdaptiveCpp 的编译，需要使用 Spack 安装 hip、llvm-amdgpu 和 rocm-openmp-extras，并指定使用 AOCC 编译器。此外，还需要安装 cmake、gmake 和 boost 等构建工具。
- spack install hip %aocc
- spack load hip llvm-amdgpu rocm-openmp-extras
- spack install cmake %aocc
- spack install gmake %aocc
- spack install boost %aocc
- spack load cmake gmake boost

---

## 9. 编译安装 AdaptiveCpp

在使用 ROCm 6.2.2 编译 AdaptiveCpp 时，需指定 CMake 前缀路径、C/C++ 编译器路径（指向 Spack 安装的 llvm-amdgpu 中的 clang 和 clang++）、启用 ROCm 后端，并设置 LLVM_DIR 路径。编译安装完成后，AdaptiveCpp 将被安装到 /opt/AdaptiveCpp 目录。
- cmake -D CMAKE_INSTALL_PREFIX=/opt/AdaptiveCpp -D CMAKE_C_COMPILER=/root/spack/opt/spack/linux-debian12-zen4/aocc-5.0.0/llvm-amdgpu-6.2.1-<hash>/bin/clang -D CMAKE_CXX_COMPILER=/root/spack/opt/spack/linux-debian12-zen4/aocc-5.0.0/llvm-amdgpu-6.2.1-<hash>/bin/clang++ -D WITH_ROCM_BACKEND=ON -D LLVM_DIR=/root/spack/opt/spack/linux-debian12-zen4/aocc-5.0.0/llvm-amdgpu-6.2.1-<hash>/lib/cmake/llvm -D WITH_SSCP_COMPILER=OFF ..
- make -j<cores> install

---

## 10. 安装 GROMACS 的数学库

编译 GROMACS 2024.3 之前，建议使用 Spack 安装 AMD 优化的数学库 amdblis 和 amdlibflame（分别对应 BLAS 和 LAPACK），并使用 AOCC 编译器。
- spack install amdblis %aocc
- spack install amdlibflame %aocc
- spack load amdblis amdlibflame

---

## 11. 编译安装 GROMACS (SYCL 版本)

下载并解压 GROMACS 源码后，使用 CMake 进行配置，需指定 AdaptiveCpp 的路径、C/C++ 编译器（同 AdaptiveCpp 的编译器），并开启 GPU 支持选项。关键配置包括设置 GMX_GPU=SYCL、GMX_SYCL=ACPP、ROCm 路径以及 HIPSYCL 目标架构（如 gfx1100 对应 RX 7900 系列），最终安装到 /opt/gmx。
- wget https://ftp.gromacs.org/gromacs/gromacs-2024.2.tar.gz
- tar -xzf gromacs-2024.3.tar.gz
- cd gromacs-2024.3
- mkdir build && cd build
- cmake -D CMAKE_PREFIX_PATH=/opt/AdaptiveCpp -D CMAKE_INSTALL_PREFIX=/opt/gmx -D CMAKE_C_COMPILER=/root/spack/opt/spack/linux-debian12-zen4/aocc-5.0.0/llvm-amdgpu-6.2.1-<hash>/bin/clang -D CMAKE_CXX_COMPILER=/root/spack/opt/spack/linux-debian12-zen4/aocc-5.0.0/llvm-amdgpu-6.2.1-<hash>/bin/clang++ -D GMX_GPU=SYCL -D GMX_SYCL=ACPP -D ACPP_ROCM_PATH=/opt/rocm/ -D HIPSYCL_TARGETS=hip:gfx1100 -D GMX_BUILD_OWN_FFTW=ON ..
- make -j<cores> install

---

## 12. 运行 GROMACS

每次运行 GROMACS 前，需要先加载 GROMACS 的环境变量脚本和 Spack 的 rocm-openmp-extras 依赖。运行 mdrun 命令时，可根据硬件配置设置 MPI 进程数、OpenMP 线程数并指定 GPU ID。
- source /opt/gmx/bin/GMXRC
- spack load rocm-openmp-extras
- gmx mdrun -s STMV-GMX.tpr -resetstep 5000 -nsteps 50000 -ntmpi 1 -ntomp 16 -gpu_id 0
