---
key: t28480
title: �����JDFTx��Centos7������ϵİ�װ����
url: http://bbs.keinsci.com/thread-28480-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 13
---

# �����JDFTx��Centos7������ϵİ�װ���� — 知识卡片

## 1. JDFTx 简介

JDFTx 是计算化学领域的一个软件包，基于密度泛函理论（DFT）开发。该软件特别适用于进行联合密度泛函理论（JDFT）计算，能够处理固定电势下的电极化学系统，并支持自动化计算。

---

## 2. YUM 环境准备与基础依赖安装

使用 YUM 包管理器可以搜索并安装编译所需的基础工具。安装 wget、gcc-c++、gcc-gfortran、cmake、gsl-devel、openmpi-devel、fftw-devel、atlas-devel、openssl-devel、python3、SDL-devel 等库是编译前的必要步骤。建议执行 `sudo yum -y groupinstall "Development Tools"` 以安装开发工具组，并同步系统时间。

---

## 3. 系统环境验证命令

在安装依赖包后，可以使用组合命令验证关键工具的版本及状态。验证命令包括 `clear&&date&&echo&&openssl version&&echo&&cmake --version&&echo&&gcc --version`，用于确认系统时间、OpenSSL 版本、CMake 版本和 GCC 版本。

---

## 4. Intel oneAPI 2021 下载

Intel oneAPI 2021 的安装包可通过 wget 命令从 Intel 官方注册中心下载。需要下载 Base Toolkit（文件名示例：l_BaseKit_p_2021.1.0.2659_offline.sh）和 HPC Toolkit（文件名示例：l_HPCKit_p_2021.1.0.2684_offline.sh），安装过程需要预留约 3.5 GB 的下载空间和 23.3 GB 的磁盘空间。

---

## 5. Intel oneAPI 2021 静默安装

下载完成后，使用 `sh` 命令配合参数进行静默安装。安装命令为 `sh l_BaseKit_p_2021.1.0.2659_offline.sh -f /tmp -s -a --silent --eula accept` 和 `sh l_HPCKit_p_2021.1.0.2684_offline.sh -f /tmp -s -a --silent --eula accept`，安装路径默认位于 `/opt/intel/oneapi`。

---

## 6. Intel 编译器环境配置

安装 Intel oneAPI 后，需将环境变量脚本写入配置文件并生效。执行 `echo "source /opt/intel/oneapi/setvars.sh" >> ~/.bashrc` 和 `source ~/.bashrc`，重新登录终端后，可通过 `which icc ifort icpc mpiifort mpirun` 验证编译器环境是否正确配置。

---

## 7. Intel MKL FFTW 接口编译

JDFTx 编译需要构建 Intel MKL 的 FFTW 接口库。需进入目录 `/opt/intel/oneapi/mkl/latest/interfaces/fftw3xf`，执行 `make libintel64` 进行编译，随后通过 `find / -name libfftw3xf_intel.a` 确认生成的库文件位置。

---

## 8. JDFTx CPU 版本源码编译

JDFTx CPU 版本通过 CMake 进行构建。在解压源码并创建 build 目录后，执行 `cmake ../jdftx-1.6.0/jdftx` 和 `make -j4` 进行编译安装，之后可运行 `make testclean && make test` 执行测试。

---

## 9. JDFTx CPU 版本环境配置与运行

编译完成后，需将构建目录添加到 PATH 环境变量中。在 `~/.bashrc` 中添加 `export PATH="/opt/build:$PATH"` 并生效后，使用命令 `jdftx -i water.in | tee water.out` 运行计算任务。

---

## 10. JDFTx GPU 版本 CMake 配置参数

编译 GPU 版本时，需在 CMake 命令中指定 CUDA 相关参数。根据 GPU 架构（如 6.1 或 7.5）设置 `CUDA_ARCH` 和 `CUDA_CODE`，并开启 `EnableCUDA`、`CudaAwareMPI`、`ForceFFTW` 和 `EnableMKL` 选项，同时指定 MKL 路径（例如 `-D MKL_PATH=/opt/intel/oneapi/mkl/2021.1.1`）。

---

## 11. JDFTx GPU 版本编译与测试

GPU 版本的 CMake 配置命令示例为 `CC=gcc CXX=g++ cmake -D EnableCUDA=yes -D CUDA_ARCH=compute_61 -D CUDA_CODE=sm_61 -D CudaAwareMPI=yes -D ForceFFTW=yes -D EnableMKL=yes -D MKL_PATH=/opt/intel/oneapi/mkl/2021.1.1 ../jdftx-1.6.0/jdftx`。配置完成后执行 `make -j8` 进行编译，并运行 `make testclean && make test` 进行测试。

---

## 12. JDFTx GPU 版本环境变量设置

运行 GPU 版本需要设置特定的环境变量以支持 CUDA 和 MPI。需在 `~/.bashrc` 中设置 `export MPICH_GPU_SUPPORT_ENABLED=1`、`export JDFTX_LAUNCH=""`、`export JDFTX_SUFFIX="_gpu"` 以及 PATH 变量，同时可根据需要调整 `JDFTX_MEMPOOL_SIZE`（单位为 MB）。

---

## 13. JDFTx GPU 版本运行命令与内存估算

GPU 版本的可执行文件名为 `jdftx_gpu`，运行命令示例为 `jdftx_gpu -i water.in | tee water.out`。验证 GPU 资源利用情况的有效测试是调整 `nstate`（离散态）数量，显存需求估算公式为 `Memory > nstate * nbasis * nbands * 16 *(4 or 5)/1073741824`（单位为 GB）。
