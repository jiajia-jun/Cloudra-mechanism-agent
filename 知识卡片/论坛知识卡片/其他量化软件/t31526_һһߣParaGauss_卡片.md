---
key: t31526
title: һ��һ��ߣParaGauss
url: http://bbs.keinsci.com/thread-31526-1-1.html
domain: 其他量化软件
source: keinsci
year: 2022
cards: 14
---

# һ��һ��ߣParaGauss — 知识卡片

## 1. ParaGauss 程序简介

ParaGauss 是基于 LCAO-GTO 形式的 DFT 计算程序，与 ADF 类似。该项目自 4.0 版本后主要开发已停止，目前处于停滞状态。2014 年有一些版本被发布至 Github，部分实现了开源，但并未进行伪代码转换或脚本更新，原开发者不再提供任何技术支持。

---

## 2. GNU Guile 库安装

编译 ParaGauss 需预先安装 GNU Guile 库，建议使用版本 2.2 以匹配 2014 年左右的 ParaGauss 代码。在 Ubuntu 系统下可使用命令 `sudo apt-get install guile-2.2-dev` 安装，并需设置头文件路径环境变量：
`export C_INCLUDE_PATH=/usr/include/guile/2.2:$C_INCLUDE_PATH`

---

## 3. OpenMPI 安装与配置

ParaGauss 支持并行计算，需安装 OpenMPI（兼容 Intel 或 GNU 编译器）。配置编译环境时需添加 `--enable-mpi-fortran` 和 `--enable-static` 选项。环境变量设置示例如下（需替换 `$openmpi_install_dir`）：
```bash
export PATH=$openmpi_install_dir/bin:$PATH
export LIBRARY_PATH=$openmpi_install_dir/lib:$LIBRARY_PATH
export LD_LIBRARY_PATH=$openmpi_install_dir/lib:$LD_LIBRARY_PATH
export CPATH=$openmpi_install_dir/include:$CPATH
```

---

## 4. BLAS 与 LAPACK 库配置

使用 GNU 编译器链时需安装 BLAS 和 LAPACK 库。在 Ubuntu 下使用命令：
`sudo apt-get install libblas-dev liblapack-dev`
并配置环境变量指向库文件路径：
```bash
export LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/blas:/usr/lib/x86_64-linux-gnu/lapack:$LIBRARY_PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/blas:/usr/lib/x86_64-linux-gnu/lapack:$LD_LIBRARY_PATH
```

---

## 5. 源码获取与准备

ParaGauss 源码可从 Github 仓库 (https://github.com/alexei-matveev/paragauss-gpl) 下载。解压后进入目录 `paragauss-gpl-master`，需在目录下创建并配置 `machine.mk` 文件以指定编译器和环境参数。

---

## 6. Intel 编译器配置 (machine.mk)

使用 Intel 编译器时，将 `make/ifc13local.mk` 复制为 `./machine.mk`。需编辑该文件中的 `MPIINCLUDE` 和 `MPILIBS` 变量，例如：
```makefile
MPIINCLUDE = -I$openmpi_install_dir/include
MPILIBS = -lmpi_usempif08 -lmpi -lmpi_mpifh
```

---

## 7. GNU 编译器配置 (machine.mk)

使用 GNU 编译器时，将 `make/krsk-gfortran-openmpi.mk` 复制为 `./machine.mk`。编辑文件需删除 Fortran 编译标志中的 `-x f95`，并删除 `BLASLIBS` 中不存在的 `-lf77blas` 和 `-latlas` 选项。需在 `COMMINCLUDE` 前添加 `MPIINCLUDE` 定义。

---

## 8. GNU Guile 接口修改 (machine.mk)

若启用 Guile（`WITH_GUILE=1`），需在 `machine.mk` 末尾将相关配置块替换为：
```makefile
ifeq ($(WITH_GUILE),1)
LIBS += $(shell guile-config link)
CINCLUDE += $(shell guile-config compile)
LINKFLAGS += -Wno-main
endif
```
若不启用 Guile，需在顶层 Makefile 中将 `WITH_GUILE = 1` 改为 `WITH_GUILE = 0`。

---

## 9. 源码语法错误修正 (molmech 模块)

需修改 `molmech/hess_and_opt_module.f90` 文件第 1087-1089 行的语法错误。将变量 `str` 声明修正为 `str_s` 以匹配后续调用：
```fortran
str_s=rstep(nvar+1:nvar+3)
call use_vect_s()
call renew_slab(str_s)
```

---

## 10. Intel 编译器兼容性修正 (xc_func 模块)

使用 Intel 编译器时，需修改 `modules/xc_func.f90` 文件第 1388 行以避免内部编译错误。原代码 `f = scm_list (f, f1, f2)` 需改为使用临时变量 `f0`：
```fortran
type(scm_t) :: f1, f2, f0
f0 = f
f = scm_list (f0, f1, f2)
```

---

## 11. 编译产物说明

执行 `make` 命令进行编译。编译成功后，若启用 Guile 将生成可执行文件 `guile-qm` 及脚本 `runqm`；若未启用 Guile 将生成可执行文件 `mainscf_V3.2.1-yyyyymmdd`（后缀为编译日期）。

---

## 12. 启用 Guile 的运行脚本

启用 Guile 时，运行脚本 `run.sh` 需设置 OpenMPI 和 ParaGauss 的路径环境变量。串行计算使用 `runqm job-1`，并行计算使用 `mpirun -np 4 runqm job-1`。

---

## 13. 禁用 Guile 的运行脚本

禁用 Guile 时，运行脚本 `run.sh` 需将输入文件复制为 `input`。串行计算直接运行可执行文件，并行计算使用 `mpirun -np 4 mainscf_V3.2.1-yyyyymmdd`。输入文件示例可在 `paragauss-gpl-master/qa` 目录中查找。

---

## 14. Intel MKL 环境变量设置

若使用 Intel 编译器及 MKL 数学库，需在运行脚本 `run.sh` 中加载对应环境变量：
```bash
source $intel_compilers_path/bin/compilervars.sh intel64
source $intel_compilers_path/mkl/bin/mklvars.sh intel64
```
