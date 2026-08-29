---
key: t40792
title: AOCC��AOCl 4.0 ��װVASP 6.4.2
url: http://bbs.keinsci.com/thread-40792-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 15
---

# AOCC��AOCl 4.0 ��װVASP 6.4.2 — 知识卡片

## 1. AMD EPYC 9654 优化编译方案

AMD EPYC 9654 (Zen4 架构) 服务器平台编译 VASP 推荐使用 AMD 官方提供的 AOCC 和 AOCL 编译器与数学库。AMD 官方提供了基于 AOCC 和 AOCL 的 `makefile.include` 模板文件供用户参考。

---

## 2. VASP 6.4.2 编译准备

VASP 6.4.2 编译工作需要准备用户授权、管理员权限以及源代码。源代码获取通常需要联系代理商，且价格通常不会超过 20 万元人民币。

---

## 3. 系统环境依赖

编译环境需要安装最新版的 AOCC、AOCL 以及 GLIBC 2.27 或更高版本。如果 GLIBC 版本过低，需要升级到系统发行版的最新版本，否则编译可能失败或运行时出现 Bug。

---

## 4. 容器化编译建议

对于宿主系统环境老旧或缺乏 root 权限的环境，推荐使用 Singularity 容器进行安装。这种方式可以避免系统环境不一致带来的问题，且只需在镜像制作阶段拥有一次 root 权限。

---

## 5. AOCC 安装步骤

AOCC 的安装流程为解压安装包后运行 `./install.sh`，随后执行 `source setenv_AOCC.sh` 配置环境。安装成功后，可通过 `which clang` 命令验证编译器路径是否正确。

---

## 6. AOCL 安装步骤

AOCL 的安装流程为解压后运行 `./install.sh -t /opt/xxx` 将其安装到指定目录。安装完成后需进入安装路径执行 `source amd-libs.cfg` 以加载 AOCL 的环境变量。

---

## 7. OpenMPI 编译配置

OpenMPI 需使用 `./configure CC=clang CXX=clang++ FC=flang --prefix=/xxxx` 进行配置，随后执行 `make && make install`。注意 `CC=clang...` 等参数必须写在 `./configure` 命令的最前面，否则可能会导致 OpenMPI 编译时找不到 clang。

---

## 8. OpenMPI 环境变量设置

OpenMPI 编译完成后需设置环境变量，包括 `MPI_HOME=/usr/local`，以及更新 `PATH`、`LD_LIBRARY_PATH` 和 `MANPATH`。具体命令为 `export PATH=${MPI_HOME}/bin:$PATH`，`export LD_LIBRARY_PATH=${MPI_HOME}/lib:$LD_LIBRARY_PATH`，`export MANPATH=${MPI_HOME}/share/man:$MANPATH`。

---

## 9. VASP 编译前检查

在开始编译 VASP 之前，建议检查 `which mpirun` 和 `which clang` 等命令，确保 MPI 和编译器路径正确。

---

## 10. Makefile.include 模板修改

VASP 编译需复制并修改 `makefile.include` 模板文件（如 `makefile.include.aoccxxxx`）。修改内容包括将 AOCL 的路径填入文件，并设置 `VASP_TARGET_CPU ?= -march=znver4`。

---

## 11. 数学库路径配置

Makefile 中需正确配置 BLAS、LAPACK、scalAPACK 和 FFTW 的根目录路径，路径应指向 AOCL 安装目录下的具体位置。示例写法为 `AMDSCALAPACK_ROOT ?= /opt/amd/aocl.4.1.0/4.1.0/aocc`。

---

## 12. 并行编译注意事项

使用 `make all` 进行编译时，不建议直接使用多线程（如 `make -j20`），否则可能会报错。推荐单线程编译或使用少量线程，若必须使用多线程，建议控制并发数（如 `make all -j4`）。

---

## 13. 屏幕会话保持建议

编译过程（特别是 OpenMPI）可能耗时较长（超过 1 小时），为防止网络断开导致中断，建议使用 `screen` 保持会话。若编译过程中断，可执行 `make veryclean` 清理后重新运行 `make all`。

---

## 14. Ubuntu 22.04 环境准备

在拥有 root 权限的 Ubuntu 22.04 系统上，建议先更新系统并使用 `apt-get install` 更新 `gfortran`、`gcc` 等必要的编译工具和库。完成基础工具更新后即可开始 VASP 的安装流程。

---

## 15. AMD 平台运行参数差异

在 AMD 平台上运行 VASP 时，MPI 参数可能对性能影响显著，且与 Intel 平台表现不同。具体的 MPI+OpenMP 混合并行参数设置方法及性能优化技巧，可参考 AMD EPYC 9754 & 9654 标准测试报告或相关网络资源。
