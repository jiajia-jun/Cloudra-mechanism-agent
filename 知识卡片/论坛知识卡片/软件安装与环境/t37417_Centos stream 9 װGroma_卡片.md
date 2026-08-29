---
key: t37417
title: Centos stream 9 ��װGromacs 2023.1��GPU���ٰ棩�̳�
url: http://bbs.keinsci.com/thread-37417-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 23
---

# Centos stream 9 ��װGromacs 2023.1��GPU���ٰ棩�̳� — 知识卡片

## 1. 硬件兼容性与系统死机排查

计算化学设备运行 CentOS Stream 9 一段时间后出现无故死机且无系统日志的现象，通常与操作系统无关。此类问题需优先排除硬件故障，应重点检查内存、硬盘、CPU 等硬件部件，或尝试安装不同 Linux 发行版及 Windows 系统进行交叉测试。

---

## 2. CentOS Stream 9 与 Rocky Linux 9 稳定性验证

Rocky Linux 9.3 系统曾出现内存报错问题，排除硬件故障后 Centos stream 9 系统运行相当稳定。在 Rocky Linux 9.3 上可成功安装 Gromacs、Gaussian、xtb、ORCA、SVM 等计算化学软件，CentOS Stream 9 同样适用且运行良好。

---

## 3. 硬件配置清单

高性能计算化学工作站配置包括 AMD Ryzen 9 7950X CPU、GIGABYTE B650M AORUS Elite AX 主板、64GB DDR5 内存、ASUS RTX 4090 显卡、Seagate 8TB 硬盘及 1000W 电源。该配置参考了 原作者 老师的博文推荐，适合进行量化计算与分子模拟。

---

## 4. 远程连接与文件交互工具

在 Windows 10 系统下可通过 MobaXterm 终端远程登录 Linux 系统进行操作。利用该工具可以在本地与 Linux 服务器之间方便地进行命令行操作及文件传输。

---

## 5. Centos 7.6 内核兼容性问题

使用 UltroISO 制作 U 盘安装盘在较新硬件上安装 Centos 7.6 可能会导致 kernel panic not syncing 错误。这是由于 Centos 7.6 内核较旧不支持新型硬件驱动，尝试更换不同 U 盘或重制启动盘无法解决此问题。

---

## 6. 制作 Linux 启动盘的工具与方法

推荐使用 Win32 Disk Imager 制作 Linux 安装启动盘以避免报错。该工具制作的启动盘在安装过程中较为稳定，且安装完成后若需恢复 U 盘使用，可利用 Windows 磁盘管理工具清除 U 盘分区并重新格式化。

---

## 7. CentOS Stream 9 安装配置

安装 CentOS Stream 9 时推荐选择 Workstation 版本，磁盘分区可将 8T 硬盘分为 /home (2T)、/ (2T) 及数据存储区。系统安装完成后内核版本为 Linux 5.14.0-312.el9.x86_64。

---

## 8. 禁用 CentOS 默认 Nouveau 显卡驱动

为安装 NVIDIA 官方驱动，需先禁用系统自带的 Nouveau 开源驱动。通过 lsmod | grep nouveau 确认驱动加载情况，并修改 /usr/lib/modprobe.d/dist-blacklist.conf 和 /etc/default/grub 文件添加 blacklist 与禁用参数。

---

## 9. 重建 initramfs 与切换运行级别

禁用 Nouveau 驱动需备份原有 initramfs 镜像并使用 dracut 重建。通过 systemctl set-default multi-user.target 命令将系统切换至多用户文本模式，重启后若无输出则说明禁用成功，后续可重新启动图形界面服务。

---

## 10. NVIDIA 官方驱动安装

将下载的 NVIDIA-Linux-x86_64-525.116.04.run 文件上传至 Linux 系统，赋予执行权限后运行安装程序。安装过程中需根据提示选择选项，32 位兼容库在 64 位系统下可不选，安装完成后可通过 nvidia-smi 命令查看显卡状态。

---

## 11. NVIDIA 驱动安装后的内核检查

若驱动安装后系统运行异常，需检查当前内核版本与驱动版本是否一致。使用 rpm -qa | grep kernel 查询内核列表，若存在不一致的内核版本（如 kernel-5.14.0-362.el9.x86_64），需使用 yum remove 命令将其移除。

---

## 12. 单独安装 NVIDIA 驱动对 GROMACS 的影响

仅安装 NVIDIA 驱动而不安装 CUDA 工具包时，编译 GROMACS 2023.1 即使使用 -DGMX_GPU=CUDA 参数，GPU 支持仍会显示为 disabled 状态。要实现 GPU 加速必须正确安装 CUDA 环境。

---

## 13. CUDA 12.1 安装过程

从 NVIDIA 官网下载 CUDA 12.1 的 runfile (local) 安装包，使用 wget 命令下载并运行。因已安装 NVIDIA 驱动，安装过程中需取消勾选 Driver 选项，仅安装 Toolkit 组件，安装完成后需配置环境变量。

---

## 14. CUDA 环境变量配置

安装 CUDA 12.1 后需编辑 ~/.bashrc 文件添加 PATH 和 LD_LIBRARY_PATH 环境变量。具体添加的路径为 /usr/local/cuda-12.1/bin 和 /usr/local/cuda-12.1/lib64，保存后执行 source ~/.bashrc 使配置生效，并使用 nvcc -V 验证。

---

## 15. CMake 与编译工具安装

CentOS Stream 9 系统可直接通过 yum install cmake3 安装 cmake，或从官网下载源码使用 bootstrap 脚本编译安装。系统自带的 gcc 和 g++ 版本可满足 GROMACS 2023.1 的编译需求。

---

## 16. GROMACS 2023.1 编译参数说明

编译 GROMACS 2023.1 GPU 加速版时，cmake 命令需指定安装前缀、开启自带 FFTW 库、下载回归测试、设置 SIMD 指令集为 AVX2_256 并开启 GPU 支持。需正确设置 CUDA_TOOLKIT_ROOT_DIR 路径指向 CUDA 安装目录。

---

## 17. GROMACS 2023.1 编译安装步骤

下载并解压 GROMACS 2023.1 源码包后，创建 build 目录并执行 cmake 配置。配置完成后依次运行 make 进行编译、make check 进行测试以及 make install 进行安装，安装成功后需配置环境变量。

---

## 18. GPU 加速与 CPU 版本性能对比

在 AMD Ryzen 9 7950X 和 RTX 4090 硬件环境下，GPU 加速版 GROMACS 2023.1 性能约为 3208 ns/天。对比同平台 CPU 通用版（1325 ns/天）及笔记本 Win10 系统下 GROMACS 2020.6（428 ns/天），GPU 加速效果显著。

---

## 19. 旧工作站性能基准数据

旧款双路服务器（24 核）运行 GROMACS 2018.8 的速度约为每天 110 ns。该数据作为历史对比参考，显示了硬件升级与 GPU 加速带来的性能提升幅度。

---

## 20. 硬件配置对模拟速度的影响

模拟速度显著受到CPU与GPU组合的影响，性能提升主要依赖于强力的CPU与GPU配合。计算速度的提升幅度在硬件配置不同时存在明显差异。

---

## 21. GROMACS版本对模拟速度的影响

计算速度与GROMACS的软件版本紧密相关，不同版本之间的性能优化程度不同。在相同硬件环境下，升级到更新版本的软件通常能获得更高的模拟效率。

---

## 22. GROMACS 2022.5 的模拟速度表现

使用GROMACS 2022.5版本进行模拟时的速度测试结果为2556 ns/day。该数据可作为该特定版本性能表现的参考基准。

---

## 23. GROMACS 2023.1 的模拟速度表现

使用GROMACS 2023.1版本进行模拟时的速度测试结果为3208 ns/day。与2022.5版本相比，该版本在同等条件下展现了更快的模拟处理能力。
