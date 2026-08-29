---
key: t43811
title: ���ڳ�������spack��װcp2k 2024.1�Ĺ���
url: http://bbs.keinsci.com/thread-43811-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 10
---

# ���ڳ�������spack��װcp2k 2024.1�Ĺ��� — 知识卡片

## 1. Rocky Linux 系统环境与编译器限制

目标系统为 Rocky Linux 8.9，未使用 module 系统，仅预装了 Intel oneAPI 工具套件及 GCC 8.5.0。系统自带的 OpenMPI 是基于 GCC 8.5.0 编译的，无法满足 CP2K 2024.1 对 GCC 版本（仅支持 8.3 和 8.4，而非 8.5）的特定要求，必须自行解决编译环境依赖。

---

## 2. 使用 CP2K toolchain 脚本首次编译

首次尝试使用 CP2K 自带的 toolchain 脚本安装依赖并编译，命令为 `./install_cp2k_toolchain.sh --with-gcc=install --with-openmpi=install --with-plumed=install --with-sirius=no --with-intel=no --with-intelmpi=no`。此方法虽然能安装 GCC 13.2.0 和 OpenMPI 4.1.5，但在后续运行中会遇到 ELPA 相关警告。

---

## 3. ELPA 警告与计算卡顿问题

编译完成后运行 CP2K 会出现 `*** WARNING in fm/cp_fm_elpa.F:522 :: Setting real_kernel for ELPA failed ***` 警告。此警告被证实会影响计算稳定性，导致 AIMD 模拟在运行一段时间后节点卡死且无输出，该现象在 AMD 9554 CPU 节点上尤为明显。

---

## 4. 首次尝试的 PBS 提交脚本配置

首次编译失败前的 PBS 任务提交脚本设置如下，加载了 toolchain 生成的 setup 环境变量，并将 CP2K 可执行文件路径加入 PATH，线程数设为 4，使用 `mpirun --hostfile $PBS_NODEFILE -np 128 cp2k.popt` 启动 128 核并行计算。

---

## 5. 使用 Spack 安装 CP2K 的环境准备

第二次尝试改用 Spack 安装 CP2K，需先在 `~/.bashrc` 中配置环境变量，包括设置 `SPACK_ROOT` 并执行 `source ${SPACK_ROOT}/share/spack/setup-env.sh`。通过 `spack --help` 或查看返回的 usage 信息确认 Spack 已成功安装并可用。

---

## 6. 使用 Spack 检查与安装编译器

通过 `spack compiler find` 和 `spack compilers` 命令查看系统当前可用的编译器版本。若缺少适合 CP2K 的编译器，需使用 `spack install gcc@13.2.0` 安装 GCC 13.2.0，安装完成后使用 `spack load gcc@13.2.0` 加载并通过 `gcc -v` 验证版本。

---

## 7. 使用 Spack 安装 OpenMPI

利用 `spack info openmpi` 和 `spack versions openmpi` 查看可用的 OpenMPI 版本。选择 OpenMPI 5.0.2 版本，并指定使用刚刚安装的 GCC 13.2.0 进行编译，安装命令为 `spack install openmpi@5.0.2 %gcc@13.2.0`，完成后用 `spack find openmpi` 确认。

---

## 8. 使用 Spack 安装 CP2K 及其依赖

Spack 中 CP2K 的首选版本为 2024.1，安装命令需指定编译器、开启 plumed 和 elpa 选项，并链接特定版本的 OpenMPI。完整的安装命令为 `spack install cp2k %gcc@13.2.0 +plumed +elpa ^openmpi@5.0.2`，安装完成后使用 `spack load cp2k` 加载模块。

---

## 9. Spack 安装 CP2K 的 PBS 提交脚本

使用 Spack 版 CP2K 的 PBS 提交脚本需先设置 `SPACK_ROOT` 并加载 Spack 环境，随后执行 `spack load cp2k`。计算命令使用 `mpirun --hostfile $PBS_NODEFILE -np 64 cp2k.psmp cubic.inp > cubic.out` 启动 64 核并行计算，并设置 `OMP_NUM_THREADS=4`。

---

## 10. Spack 安装方法的最终验证

尽管使用 Spack 安装的 CP2K 在运行中仍会出现 ELPA 警告，但实际 AIMD 模拟不会出现卡死现象，计算可以正常进行。使用 Spack 安装 CP2K 被证明是非常省时且简单的方法，能够有效解决依赖冲突和版本兼容问题。
