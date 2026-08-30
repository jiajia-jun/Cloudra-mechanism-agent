---
key: t35960
title: 2023��3��MD benchmark������ƪ����4090���ı����
url: http://bbs.keinsci.com/thread-35960-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 15
---

# 2023��3��MD benchmark������ƪ����4090���ı���� — 知识卡片

## 1. RTX 4090 与 Ada Lovelace 架构

Ada Lovelace 架构针对分子动力学（MD）模拟进行了优化。基于该架构的 RTX 4090 在 MD 模拟性能上可能取得显著提升。RTX 4090 于发布后约 5 个月内被用于测试其 MD 模拟性能。

---

## 2. 测试平台硬件与软件环境

测试平台基于 Ubuntu 22.04.2 LTS Desktop 和 Linux 5.19.0-35-generic x86_64 内核。编译环境采用 GNU 11.3、CUDA Toolkit 12.1 / 11.8 以及 NVIDIA GPU Driver 530.30.02。

---

## 3. GROMACS 编译版本信息

测试使用了多个 GROMACS 版本，包括 2023 版（CUDA runtime V12.1）、2022.5 版（CUDA runtime V12.1）、2022.5 版（CUDA runtime V11.8）和 2022.3 版（CUDA runtime V12.1）。

---

## 4. LAMMPS 编译配置

LAMMPS 版本为 8Feb2023，使用 cmake 预设 basic.cmake 和 kokkos-cuda.cmake 进行编译。编译列表中将 Kokkos_ARCH_PASCAL60 修改为 Kokkos_ARCH_ADA89，并添加了 REAXFF 支持参数 -D PKG_REAXFF=on。

---

## 5. AMBER22 与 NAMD3 编译情况

AMBER22 为源码编译， cmake 脚本被修改以支持 SM89 架构 flags。尽管尝试使用 NVCC 12.1.66 编译，但最终实际测试使用的是 NVCC 11.8.89 编译版本。NAMD3 在过去 10 个月内未更新，使用了与上次测试相同的版本。

---

## 6. RTX 4090 MD 性能总体提升

与 10 个月前的测试相比，RTX 4090 在 4 个 MD 软件中的平均性能提升约为 19%。对于 GROMACS，GPU-resident 模式下的性能提升较为显著。

---

## 7. GROMACS 性能提升细节

在 GROMACS 中，使用 GPU-resident 模式可达到 19% 的性能提升，平均提升为 12%。Bonded 计算从 CPU 迁移到 GPU 也能带来平均 7% 的性能提升。在 A-2 体系中，bonded 计算量较大；在 B-TI 模式下，因 CPU 需要处理自由能相关的计算，CPU 瓶颈较明显。

---

## 8. AMBER22 与 NAMD3 性能表现

AMBER22 和 NAMD3 由于没有更新，性能变化非常微小。AMBER22 是唯一成功编译支持 RTX 4090 GPU 计算的 AMBER 版本。

---

## 9. LAMMPS 性能提升细节

在 LAMMPS 中，Tersoff 模型显示出较大的性能优化，提升幅度达到 27.5%。第 2 个模型的提升幅度较小。ReaxFF/C 模型可以成功运行，但相比 10 个月前的数据有所缺失。

---

## 10. CUDA 版本对 GROMACS 性能的影响

对于 GROMACS 2022.3，即使使用更新的 CUDA 或 GPU 版本，性能提升也只有约 3%。GROMACS 2022.5 即使配合 RTX 4090 发布时的 CUDA 11.8 版本，相比 2022.3 版本改进也不大。

---

## 11. GROMACS 2023 优化特性

GROMACS 2023 引入了多项优化，包括 CUDA PME decomposition、CUDA Graphs 和 VkFFT。Update 步骤默认运行在 GPU 上，不再依赖 CPU。

---

## 12. 性能提升原因总结

RTX 4090 性能提升的主要原因包括 NVIDIA GPU 对 MD 的底层优化、CUDA 11.8 及以后版本对 Ada 架构的优化、以及软件（GROMACS 2023）的算法改进。

---

## 13. 编译 Flags 优化建议

对于 GROMACS 和 LAMMPS 的新版本，需确保 NVCC 编译 flags 指向 Ada 架构对应的 SM89 目标。在 CUDA 11.8 及以后版本中，这通常是默认配置，可通过 gmx -version 命令检查 "CUDA compiler flags"。

---

## 14. MD 参数调整建议

GROMACS 2023 的性能优化使得手动指定 nsttcouple 和 nstpcouple 为 2 steps 的必要性降低。默认值 10 steps 已足够，性能限制通常受限于 nlist 更新频率。

---

## 15. 原始测试数据来源

本次性能测试的原始数据（xlsx 格式）可通过阿里云盘链接获取，提取码为 15fd。
