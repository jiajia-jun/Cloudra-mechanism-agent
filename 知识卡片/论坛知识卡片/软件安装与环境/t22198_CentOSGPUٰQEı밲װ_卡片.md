---
key: t22198
title: CentOS��GPU���ٰ�QE�ı��밲װ
url: http://bbs.keinsci.com/thread-22198-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 14
---

# CentOS��GPU���ٰ�QE�ı��밲װ — 知识卡片

## 1. 禁用 nouveau 开源驱动

安装 Cuda Toolkit 前必须先禁用 Linux 系统自带的 nouveau 开源显卡驱动。执行 `lsmod |grep nouveau` 查看驱动状态，若存在则需将其列入黑名单并强制更新 initramfs。
- 创建或编辑 `/etc/modprobe.d/blacklist.conf` 文件，写入 `blacklist nouveau` 和 `options nouveau modeset=0`。
- 执行 `dracut --force` 更新配置，然后重启系统。
- 重启后再次执行 `lsmod |grep nouveau`，若无输出则表示禁用成功。
- 若安装前系统处于图形界面模式，建议通过 `systemctl set-default multi-user.target` 切换至文本模式以避免安装冲突。

---

## 2. 安装 dkms 依赖

安装 Cuda Toolkit 前需要确保系统中已安装 dkms (Dynamic Kernel Module Support) 包。
- 使用 `dnf install -y epel-release` 启用 EPEL 仓库。
- 执行 `dnf install -y dkms` 安装该依赖包。

---

## 3. 下载 Cuda 11.2 安装包

从 Nvidia 官方网站下载与系统匹配的 Cuda Toolkit 版本，资料以 11.2 版本为例。使用 wget 命令将安装包下载至 `/tmp` 目录。
- 下载命令示例：`wget https://developer.download.nvidia.com/compute/cuda/11.2.2/local_installers/cuda_11.2.2_460.32.03_linux.run`。

---

## 4. 安装与配置 Cuda Toolkit

运行下载的 run 文件进行安装，并配置环境变量以使系统识别 CUDA。
- 赋予安装包执行权限并运行：`sudo chmod +x cuda_11.2.1_460.32.03_linux.run` 和 `sudo sh cuda_11.2.1_460.32.03_linux.run`。
- 安装过程中输入 `accept` 接受协议，选择 `install` 开始安装。
- 将 CUDA 环境变量写入 `.bashrc`：`export CUDA_HOME=/usr/local/cuda-11.2`、`export PATH=$PATH:$CUDA_HOME/bin`、`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$CUDA_HOME/lib64`。
- 执行 `source ~/.bashrc` 刷新环境，并通过 `nvcc --version` 验证安装版本。

---

## 5. 编译与运行 Cuda 测试样例

编译 CUDA Samples 中的 `deviceQuery` 程序以验证 GPU 是否正常工作。
- 进入用户目录下的 Samples 文件夹（如 `~/NVIDIA_CUDA-11.2_Samples/`），执行 `make` 进行编译。
- 编译完成后进入 `bin/x86_64/linux/release` 目录，运行 `./deviceQuery`。
- 若结果显示 `pass`，则表示 CUDA 环境配置正确。

---

## 6. 下载 NVIDIA HPC SDK

NVIDIA HPC SDK 用于编译 Quantum ESPRESSO 的 GPU 版本，资料操作基于 21.1 版本。使用 wget 将安装包下载至 `/tmp` 目录。
- 下载命令示例：`wget https://developer.nvidia.com/hpc-sdk/21.1/nvhpc_2021_211_Linux_x86_64_cuda_11.2.tar.gz`。

---

## 7. 安装 NVIDIA HPC SDK

解压并运行 NVIDIA HPC SDK 安装脚本，配置相关环境变量。
- 解压文件：`tar -xvf nvhpc_2021_211_Linux_x86_64_cuda_11.2.tar`。
- 进入解压目录执行 `./install`，按回车确认默认安装路径 `/opt/nvidia/hpc_sdk`，按 `1` 选择单节点安装。
- 安装完成后，将编译器路径加入环境变量：`export NVCOMPILERS=/opt/nvidia/hpc_sdk`、`export PATH=$NVCOMPILERS/$NVARCH/21.1/compilers/bin:$PATH`。
- 执行 `source ~/.bashrc` 并通过 `pgcc --version` 检查编译器版本是否正确。

---

## 8. 获取 QE-GPU 6.7 源码

从 GitLab 官方仓库下载 Quantum ESPRESSO 的 GPU 版本源码（qe-gpu-6.7）。
- 下载地址为 `https://gitlab.com/QEF/qe-gpu/-/releases/qe-gpu-6.7`。
- 获取 `Source code (tar.gz)` 格式的文件 `q-e-gpu-qe-gpu-6.7.tar.gz`，并通过 sftp 上传至服务器目录（如 `/opt`）。

---

## 9. 配置 QE-GPU 编译选项

解压源码并使用 configure 脚本配置编译参数，需指定 CUDA 路径、版本及 GPU 架构代码。
- 解压并重命名文件夹：`gunzip -r q-e-gpu-qe-gpu-6.7.tar.gz`、`tar -xvf q-e-gpu-qe-gpu-6.7.tar`、`mv q-e-gpu-qe-gpu-6.7 qe-6.7-gpu`。
- 执行配置命令：`./configure --with-cuda=/usr/local/cuda-11.2 --with-cuda-runtime=11.2 --with-cuda-cc=75 --enable-openmp --with-scalapack=no`。
- `--with-cuda-cc=75` 对应 Turing 架构显卡（如 RTX 2060s）。

---

## 10. 编译 QE-GPU 核心模块

并非所有模块均支持 GPU 加速，仅编译 pw.x、cp.x 和 pp.x 模块。
- 使用 make 命令并行编译指定模块：`make pw -j8`、`make cp -j8`、`make pp -j8`。
- 编译完成后将二进制文件路径加入环境变量：`export PATH=$PATH:/opt/qe-6.7-gpu/bin`。
- 执行 `source ~/.bashrc` 使配置生效。

---

## 11. 编译 NVIDIA HPC SDK 版本的 OpenMPI

为了在 GPU 上高效运行并行任务，需使用 NVIDIA HPC SDK 自带的编译器编译 OpenMPI。
- 下载 openmpi-4.0.5 源码并解压至 `/tmp` 目录。
- 加载 NVIDIA HPC SDK 环境变量（如 `source /opt/scripts/evnvhpc.sh`）。
- 配置编译选项：`./configure --prefix=/opt/tools/openmpi-4.0.5-nv --disable-builtin-atomics CC=pgcc FC=pgfortran CXX=pgc++`。
- 执行 `make all install` 进行编译安装。
- 配置环境变量：`export PATH=$PATH:/opt/tools/openmpi-4.0.5-nv/bin` 和 `export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/tools/openmpi-4.0.5-nv/lib`。

---

## 12. 编译支持 MPI 的 QE-GPU

在已配置好 OpenMPI 环境的基础上重新配置和编译 QE-GPU，以支持多 GPU 并行。
- 执行 `./configure` 时脚本会自动检测已配置的 MPI 环境。
- 重新运行 make 命令编译支持 MPI 的可执行文件，该版本适用于多显卡环境。

---

## 13. QE-GPU 运行方式

GPU 版本的 Quantum ESPRESSO 运行命令与 CPU 版本基本一致，通过 mpirun 启动并行任务。
- 单机运行命令示例：`mpirun -np N pw.x < XXX.in > xxx.out`。
- 参数 `N` 对应 GPU 数量，可通过 `OMP_NUM_THREADS=M` 设置每个 MPI 进程的 OpenMP 线程数。

---

## 14. QE-GPU 性能测试结论

基于 RTX 2060s 显卡的性能测试表明，GPU 版本在特定计算体系上具有显著优势。
- 在石墨烯切面等大体系测试中，单张 RTX 2060s 的计算耗时与双路 CPU（2678v3）相近（约 23 分钟 vs 28 分钟）。
- 在 SCF 步骤较多的第一个输入文件测试中，GPU 版本耗时显著少于 CPU 版本（约 50 秒 vs 1 分 10 秒）。
- GPU 加速效果因计算体系大小和计算步骤而异，更强大的显卡或多卡互联预计能带来更高性能提升。
