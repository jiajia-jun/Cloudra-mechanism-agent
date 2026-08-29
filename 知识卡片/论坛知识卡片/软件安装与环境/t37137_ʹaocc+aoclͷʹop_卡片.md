---
key: t37137
title: ʹ��aocc+aocl��ͷ����ʹ��openmpi��vasp6
url: http://bbs.keinsci.com/thread-37137-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 8
---

# ʹ��aocc+aocl��ͷ����ʹ��openmpi��vasp6 — 知识卡片

## 1. AOCC 与 AOCL 版本对应关系

AMD 官方 Spack 编译 VASP 速度较慢，因此撰写了使用 AOCC 和 AOCL 编译 VASP 的教程。AOCC 3.2.0 版本可用于编译 VASP 6.3.2 及之后版本，而 4.1/4.0 版本则适用于编译 VASP 6.3.2 之前的版本。

---

## 2. 编译器环境变量设置

安装 AOCC 和 AOCL 后，必须将相关路径添加至环境变量中，确保系统可正确使用 flang 和 clang 编译器。AOCL 的版本通常需要与下载的 AOCC 版本保持一致。

---

## 3. OpenMPI 编译配置参数

在编译 OpenMPI 时，为了避免冲突，configure 过程中必须指定编译器参数。具体的配置命令为 CC=clang CXX=clang++ FC=flang。

---

## 4. VASP 的 makefile 路径修改

在编译 VASP 时，需修改 makefile 中的路径参数，将预置路径 `/opt/apps/amd/aocl/3.2.0` 替换为用户实际安装的 AOCL 路径。

---

## 5. VASP 编译的 CPU 架构优化

在 VASP 的 makefile 中，可通过修改 `VASP_TARGET_CPU ?= -march=znver2` 参数来针对特定 CPU 架构进行优化。用户应根据实际 CPU 类型（如 Zen 1/2/3/4 架构）设置相应的数值。

---

## 6. VASP 模块编译限制

在 AOCC 环境下，VTST、VASPsol、Wannier90 和 HDF5 模块可以正常编译，但 DFT-D4 方法无法编译通过。具体细节有待后续补充。

---

## 7. 新版 OpenMPI 的绝对路径配置

在使用较新的 OpenMPI 版本时，configure 命令中必须使用绝对路径指定编译器位置，否则会报错。配置示例为 `./configure CC=$安装路径/aocc-compiler-4.1.0/bin/clang CXX=$安装路径/aocc-compiler-4.1.0/bin/clang++ FC=$安装路径/aocc-compiler-4.1.0/bin/flang --prefix=$安装路径`。

---

## 8. AOCC 4.1.0 与 OpenMPI 5.0.x 兼容性

实际测试表明，AOCC 4.1.0 编译的 OpenMPI 5.0.x 可以在系统 GNU 工具链版本较老（如 GCC 11）的情况下正常运行并进行编译。
