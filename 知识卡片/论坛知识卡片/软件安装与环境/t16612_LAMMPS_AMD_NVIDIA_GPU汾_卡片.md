---
key: t16612
title: LAMMPS_AMD/NVIDIA_GPU�汾�����̽ ����ͬ��OPENCL �汾��
url: http://bbs.keinsci.com/thread-16612-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2020
cards: 7
---

# LAMMPS_AMD/NVIDIA_GPU�汾�����̽ ����ͬ��OPENCL �汾�� — 知识卡片

## 1. LAMMPS 在 AMD ROCm 3.1 环境下的编译背景

LAMMPS 的官方论坛已有关于 AMD GPU 编译的介绍，资料主要补充在 AMD ROCm 3.1 环境下编译 LAMMPS GPU 模块的具体细节。所使用的测试硬件为 AMD Radeon VII (gfx906)。推荐使用的操作系统为 Ubuntu 18.4。

---

## 2. 软件依赖与源码版本

编译过程涉及的软件版本包括：GNU 9.2、HIP 10.0 (基于 clang)、ROCm 3.1 和 CUB 1.8.0。LAMMPS 源码选用 eokuznetsov 的 HIP 移植版本，可通过 wget 命令从指定 GitHub 链接下载 (https://codeload.github.com/eokuznetsov/lammps/zip/gpu_hip_port)。

---

## 3. HIP 简介

HIP 是一种 C++ 运行时 API 和内核语言，允许开发者通过单一源代码创建适用于 AMD 和 NVIDIA GPU 的可移植应用程序。官方说明文档位于 GitHub ROCm-Developer-Tools/HIP 仓库。

---

## 4. AMD 生态与 HIP 兼容性

AMD 深度学习框架 TensorFlow 支持 ROCm，且 HIP 与 ROCm 关系密切。虽然 Gaussian 询问是否迁移到 HIP，但考虑到 Gaussian 对 GPU 加速的依赖及 HIP 优化可能带来的性能提升，HIP 是重要的开发方向。

---

## 5. 编译步骤：环境与库准备

编译前需确保 HIP/ROCm 环境已正确安装。需要下载 CUB 库并确认对应的 hipcub 已安装完成。

---

## 6. 编译步骤：LAMMPS GPU 库配置

进入 LAMMPS 源码包下的 lib/gpu 目录。执行 `make -f Makefile.hip -j8` 命令进行编译。需修改 Makefile.hip 文件中 hipcub 目录的 value 参数，将其从默认的 `-I./` 修改为 CUB 的实际解压路径。

---

## 7. 编译步骤：生成可执行文件

进入 src 目录。执行 `make -j8` 命令进行编译。编译完成后，在 src 目录下会生成名为 lmp_hip 的可执行文件。
