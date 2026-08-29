---
key: t40402
title: ��LAMMPS��ʹ��CHGNet
url: http://bbs.keinsci.com/thread-40402-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2023
cards: 12
---

# ��LAMMPS��ʹ��CHGNet — 知识卡片

## 1. CHGNet 简介

CHGNet 是一种基于图神经网络的通用机器学习原子间势函数，相关研究发表于 *Nature Machine Intelligence* volume 5, pages 1031–1041 (2023)。该项目已提供 LAMMPS 接口，目前网络上缺乏详细的使用教程，记录相关的配置和使用过程具有参考价值。该教程同时也涉及 M3GNet 和 MatGL 接口的使用说明。

---

## 2. 安装依赖与 Anaconda 环境

CHGNet 使用 Python 实现，使用前需确保系统已安装 Python 环境，推荐安装 Anaconda 进行环境管理。安装 Anaconda 可参考官方文档，Python 环境准备就绪后，需要使用 pip 安装 chgnet 包。安装命令为 `pip install chgnet`。

---

## 3. 获取 LAMMPS 源代码

集成了 CHGNet 接口的 LAMMPS 源代码需从 GitHub 获取，仓库地址为 https://github.com/advancesoftcorp/lammps。用户应选择 2Aug2023 或更新版本的源代码进行下载并解压，LAMMPS 提供 CMake 和 make 两种编译方式，本教程使用 make 进行编译。

---

## 4. 修改 Makefile 启用 OpenMP

在获取源码后，需进入 `./src/MAKE` 目录找到 Makefile 文件进行修改以启用 OpenMP。根据 LAMMPS 官方文档，使用 OpenMP 需要修改 compiler/linker settings 的值，在 CCFLAGS 和 LINKFLAGS 中添加 `-fopenmp`。若使用 Intel 编译器，需将 `-fopenmp` 替换为 `-qopenmp`，并在 CCFLAGS 中添加 `-restrict`，在 LINKFLAGS 中替换为 `-qopenmp`。

---

## 5. 配置 Python 路径变量

在 Makefile 中 `build rules and dependencies` 之前的位置，需添加 Python 库和头文件的路径配置。`your_path/anaconda3` 需替换为实际的 Python 安装路径，`python3.x` 需替换为实际的 Python 版本号（如 python3.11），可以通过 `find` 命令查找。若系统存在多个 Python 环境，需确保使用安装了 CHGNet 的环境路径。配置内容如下：
```makefile
# Python library and includes (for conda)
PYTHON_INC = -I/your_path/anaconda3/include/python3.x
PYTHON_LIB = -L/your_path/anaconda3/lib -lpython3.x
```

---

## 6. 更新 Makefile 编译标志

在 Makefile 的 `build rules and dependencies` 部分，需要将定义的 `$(PYTHON_INC)` 和 `$(PYTHON_LIB)` 分别添加到 `EXTRA_INC` 和 `EXTRA_LIB` 变量中。修改后的具体配置如下：
```makefile
EXTRA_INC = $(LMP_INC) $(PKG_INC) $(MPI_INC) $(FFT_INC) $(JPG_INC) $(PYTHON_INC) $(PKG_SYSINC)
EXTRA_LIB = $(PKG_LIB) $(MPI_LIB) $(FFT_LIB) $(JPG_LIB) $(PYTHON_LIB) $(PKG_SYSLIB) $(DYN_LIB)
```

---

## 7. 启用 LAMMPS 编译选项

LAMMPS 编译时需要启用相应的软件包，使用命令 `make yes-name` 来开启特定包，`make no-name` 用于删除包。针对本教程，需要启用 OPENMP 和 ML-CHGNET 包，使用的具体命令为：
```bash
make yes-OPENMP
make yes-ML-CHGNET
```

---

## 8. 执行编译生成可执行文件

在完成 Makefile 修改和包启用后，回到 `./src` 目录执行编译命令。编译命令为 `make serial -jN`，其中 N 需替换为实际使用的 CPU 核心数。如果之前编译过其他版本，建议先执行 `make clean-all` 清理旧文件。编译成功后，`src` 目录下会生成名为 `lmp_serial` 的可执行文件，可将其复制到常用目录以便使用。

---

## 9. 配置 LAMMPS 输入脚本中的势函数

在 `./examples/CHGNET` 目录下提供的输入脚本 `inp.lammps` 中，需要设置 `pair_style` 和 `pair_coeff`。`pair_style` 支持多种形式，如 `chgnet`、`chgnet/d3`、`chgnet/gpu` 等，路径需指向 potentials/CHGNET。`pair_coeff` 用于指定模型和元素，可以使用预训练模型 `MPtrj-efsm` 或用户自定义模型路径 `./users_model.pt`，后跟元素符号（如 Zr O）。

---

## 10. 运行 LAMMPS 与环境变量设置

运行命令 `env OMP_NUM_THREADS=N lmp_serial -sf omp -in inp.lammps` 可以使用 N 个 OpenMP 线程执行模拟。如果在集群作业系统中提交任务，需要在作业脚本中设置 `LD_LIBRARY_PATH`，将 Makefile 中配置的实际 Python 目录（如 `/your_path/anaconda3/lib`）添加到环境变量中：
```bash
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/your_path/anaconda3/lib
```

---

## 11. 常见问题：OpenMP 警告

若 LAMMPS 运行时出现警告 `WARNING: OpenMp support not enabled during compilation: using 1 thread only.`，需要检查 Makefile 中是否正确添加了 `-fopenmp`，以及是否执行了 `make yes-OPENMP` 命令。

---

## 12. 常见问题：Python 初始化错误

若 LAMMPS 运行时报错 `ERROR: Cannot initialize python for pair_coeff of CHGNet`，说明 CHGNet 的 Python 环境未正确配置，需要重新检查 Python 环境及路径设置。
