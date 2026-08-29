---
key: t48964
title: ubuntu ��װ Dalton
url: http://bbs.keinsci.com/thread-48964-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 24
---

# ubuntu ��װ Dalton — 知识卡片

## 1. Dalton 程序简介

Dalton 是一款开源量子化学程序包，专门用于分子电子结构计算与研究分子性质。该程序支持多种高级电子结构计算方法（如 MCSCF、密度泛函理论等），并提供丰富的分子性质分析功能，适用于光谱学和力学性质研究。此外，Dalton 支持并行计算算法，适合处理大型体系，并具备开源特性供用户参考和修改。

---

## 2. 环境准备：目录创建

安装前需要建立下载目录、安装路径及临时文件目录。相关命令如下：创建下载目录 `$HOME/Downloads`，创建安装目录 `$HOME/Software/dalton2020`，以及创建临时目录 `$HOME/Software/dalton2020/scratch`。

---

## 3. 工具安装：tmux

为了防止网络中断或窗口关闭导致安装进程丢失，建议使用 tmux 保持终端会话。安装命令为 `sudo apt install tmux -y`，创建新会话使用 `tmux new -s dalton`，重新连接会话使用 `tmux attach -t dalton`。

---

## 4. 基础工具：cmake 与 git

编译 Dalton 需要 cmake 和 git 工具。安装命令为 `sudo apt install cmake git -y`，可通过 `cmake --version` 命令验证安装是否成功。

---

## 5. 依赖库安装：通用库

系统需要安装一系列通用开发库。安装命令包括 `sudo apt install libhwloc-dev libevent-dev -y`、`sudo apt install libhdf5-dev libeigen3-dev libboost-dev -y` 以及 `sudo apt install libopenblas-dev gfortran gcc g++ -y`。

---

## 6. 编译器验证

安装完成后需验证编译器版本。可使用 `gfortran --version`、`gcc --version`、`g++ --version` 检查 GNU 编译器，使用 `mpif90 --version`、`mpicc --version`、`mpicxx --version` 检查 MPI 编译器。

---

## 7. OpenMPI 安装

Dalton 支持并行计算，需安装 OpenMPI。安装命令为 `sudo apt install openmpi-bin openmpi-common libopenmpi-dev -y`，安装后可通过 `mpirun --version` 进行验证。

---

## 8. Python 环境检查

Dalton 构建过程依赖 Python，建议确认系统中的 Python 版本。使用 `python -V` 和 `python3 -V` 分别检查 Python 2 和 Python 3 版本，若缺失或版本不匹配可能需要通过软链接将 python 指向 python3。

---

## 9. 数学库安装与验证

系统需安装 BLAS 和 LAPACK 数学库。安装命令为 `sudo apt-get install libblas-dev liblapack-dev -y`，验证命令为 `dpkg -l | grep blas` 和 `dpkg -l | grep lapack`。

---

## 10. Dalton 源码获取

获取 Dalton 源码需使用 git 命令。在下载目录执行 `git clone --recursive https://gitlab.com/dalton/dalton.git` 即可下载完整源代码及子模块。

---

## 11. Dalton 编译配置：setup 脚本

setup 脚本用于配置编译选项，常用参数包括指定编译器、开启 MPI、设置数学库路径等。标准配置命令示例为 `./setup --prefix=$HOME/Software/dalton2020 --mpi --blas=auto --lapack=auto`，其中 `--prefix` 定义安装路径，`--mpi` 启用 MPI，`--blas=auto` 和 `--lapack=auto` 自动查找数学库。

---

## 12. 编译配置错误处理

若 setup 执行出错或需修改配置，需删除 build 目录下的 CMakeCache.txt 文件。删除命令为 `rm ./build/CMakeCache.txt`，之后可重新运行 setup 命令。

---

## 13. 配置选项查看

确认配置选项是否正确可使用 `./setup --show` 命令。该命令会打印当前的配置摘要，供用户核对编译器、路径及开关设置。

---

## 14. Dalton 编译与安装

配置完成后，进入 build 目录进行编译和安装。编译命令为 `cd build` 后执行 `make -j`，安装命令为 `make install`。

---

## 15. 环境变量设置：int32 版本

安装 int32 版本后需设置环境变量以方便调用。设置命令包括 `export PATH=$HOME/Software/dalton2020/dalton:$PATH`、`export DALTON_TMPDIR=$HOME/Software/dalton2020/scratch` 以及 `export OMP_NUM_THREADS=96`（根据 CPU 核心数修改数值）。

---

## 16. 安装测试：ctest

在 build 目录下运行 `ctest` 可执行测试套件。共有约 500 个测试，若有约 144 个失败而其余通过，通常视为安装成功（对应已知基组限制或特定测试失败）。

---

## 17. int32 版本局限性

int32 版本的 Dalton 在内存使用上存在限制，单个计算任务内存上限约为 16 GB。对于需要更大内存的体系，应安装 int64 版本。

---

## 18. int64 版本源码修改：替换 MPI 头文件

启用 int64 支持需修改 `dalton/DALTON/gen1int` 目录下的四个文件：`gen1int_matrix.F90`、`gen1int_host.F90`、`gen1int_shell.F90`、`gen1int_api.F90`。需将这些文件中的 `#include "mpif.h"` 替换为 `#include "mpi_mod.h"` 和 `#include "mpi_header.h"`，以支持 64 位整数类型。

---

## 19. int64 版本源码修改：自动化脚本

可使用 sed 命令批量替换 gen1int 目录下指定文件的 MPI 头文件引用。脚本内容为循环遍历文件列表，执行 `sed -i 's/#include "mpif.h"/#include "mpi_mod.h"\n#include "mpi_header.h"/g' "$file"`。

---

## 20. int64 版本 MPI 头文件创建：mpi_header.h

在 build 目录下需创建 mpi_header.h 文件以兼容旧接口。文件内容为条件编译指令：`#if defined(VAR_MPI) && !defined(USE_MPI_MOD_F90)` 后包含 `#include "mpif.h"`。

---

## 21. int64 版本 MPI 头文件创建：mpi_mod.h

在 build 目录下需创建 mpi_mod.h 文件以启用 MPI 模块。文件内容为条件编译指令：`#if defined(VAR_MPI) && defined(USE_MPI_MOD_F90)` 后包含 `use mpi`。

---

## 22. int64 版本编译配置

int64 版本的 setup 命令需明确指定 `--int64` 参数及具体的数学库路径。命令示例为 `./setup --prefix=$HOME/Software/dalton2020_int64 --int64 --mpi --blas=/usr/lib/x86_64-linux-gnu/libblas.so --lapack=/usr/lib/x86_64-linux-gnu/liblapack.so`。

---

## 23. 环境变量设置：int64 版本

安装 int64 版本后，需更新环境变量指向新的安装路径。设置命令为 `export PATH=$HOME/Software/dalton2020_int64/dalton:$PATH` 和 `export DALTON_TMPDIR=$HOME/Software/dalton2020_int64/scratch`。

---

## 24. int64 版本测试结果

int64 版本运行 `ctest` 时，预计有 8 个测试失败，其余通过。该结果与 int32 版本相比失败数量减少，表明 int64 版本安装正确且兼容性更好。
