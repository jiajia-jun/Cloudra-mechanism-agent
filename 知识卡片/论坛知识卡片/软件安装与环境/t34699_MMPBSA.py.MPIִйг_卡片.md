---
key: t34699
title: MMPBSA.py.MPIִ�й����г���could not import mpi4py package����취
url: http://bbs.keinsci.com/thread-34699-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 8
---

# MMPBSA.py.MPIִ�й����г���could not import mpi4py package����취 — 知识卡片

## 1. AmberTools MMPBSA.py.MPI 报错 Could not import mpi4py package

在使用 AmberTools 的 MMPBSA.py.MPI 进行多线程计算 MM-PBSA/GBSA 时，可能会遇到报错提示 "Could not import mpi4py package"。该报错通常表示 Python 环境中未正确安装或无法加载 mpi4py 模块。

---

## 2. mpi4py 缺失原因排查

mpi4py 模块可能未随 Amber 一起安装，且用户使用的 Miniconda 环境中也可能未包含该模块。通过 Amber 自带的 Python 执行 `python -c 'import mpi4py'` 命令，若无法执行，说明 mpi4py 未实际安装。

---

## 3. ImportError: libmpi.so.12 错误

在解决安装问题后，执行 `python -c 'from mpi4py import MPI'` 时可能会报错 "importError: libmpi.so.12: cannot open shared object file...."。原因是系统无法找到动态链接库 libmpi.so.12。

---

## 4. 解决方案：安装高版本 OpenMPI

安装高版本的 OpenMPI 可以解决 libmpi.so.12 缺失的问题。Open MPI 4.1 版本是目前较新的稳定版（如 openmpi-4.1.4），可直接从官网下载或通过 wget 命令获取。

---

## 5. OpenMPI 源码编译安装

下载并解压 OpenMPI 文件后，在解压目录下执行配置与编译命令：`./configure --prefix=(openmpi安装位置)` 以及 `make install -j XXX`。

---

## 6. 配置环境变量

安装完成后需设置用户环境变量，包括 `export MPI_HOME=<openmpi安装位置>`、`export PATH=${MPI_HOME}/bin:${PATH}`、`export LD_LIBRARY_PATH=${MPI_HOME}/lib:${LD_LIBRARY_PATH}` 和 `export MANPATH=${MPI_HOME}/share/man:${MANPATH}`。

---

## 7. 验证 mpi4py 与 MPI 支持

配置完环境变量后，再次执行 `python -c 'from mpi4py import MPI'` 会发现执行成功，此时环境已满足所需依赖。

---

## 8. 重新编译 Amber 解决依赖

配置好 OpenMPI 和 mpi4py 后，需要重新编译 Amber。重新编译后运行 MMPBSA.py.MPI，可发现程序已能成功运行。
