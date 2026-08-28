---
id: 103
title: Amber11+AmberTools1.5及CUDA版安装方法，以及Amber12安装方法
url: http://sobereva.com/103
domain: 软件安装与环境
topic: Amber11_12及CUDA版编译安装
cards: 1
---

# Amber11_12及CUDA版编译安装 — 知识卡片

## 1. Amber11 Intel编译器安装版本与路径

本文使用的Intel编译器版本为2011.6.233。安装时应将收到的.lic授权文件复制到/sob/licenses文件夹。在安装ifort和icc后，需将`source /opt/intel/composer_xe_2011_sp1.6.233/bin/compilervars.sh intel64`添加到/root/.bashrc文件中。
- 若安装程序提示找不到libstdc++库，需先安装libstdc++-4.4.5-6.el6.i686.rpm。

## Amber11所需MPICH2版本与编译参数
Amber11安装使用MPICH2 1.4.1p1版本。在mpich2源码文件夹内执行`./configure FC=ifort CC=icc`进行配置，随后执行`make`和`make install`。
- 若运行mpd命令报错`'MPD' object has no attribute 'myIP'`，需在/etc/hosts文件最后一行添加`127.0.0.1 ltwd ltwd`，其中ltwd为本地计算机名。

## Amber11环境变量设置与源码准备
Amber11安装前需在/root/.bashrc中设置`export AMBERHOME=/sob/amber11`。将Amber11.tar.bz2解压到/sob/amber11，再将AmberTools-1.5.tar.bz2解压到同目录覆盖文件。
- 下载AmberTools1.5的bugfix.all文件至/sob/amber11并执行`patch -p0 -N < bugfix.all`。
- 下载Amber11的补丁包bugfix.1to17.tar.bz2和apply_bugfix.x至/sob，执行`./apply_bugfix.x bugfix.1to17.tar.bz2`。

## Amber11串行版AmberTools编译与测试
进入/sob/amber11/AmberTools/src目录，执行`./configure intel`和`make install`。编译过程约需20分钟，严禁使用-j选项加速。
- 测试通过`cd ../test`和`make test`进行，测试日志位于/sob/amber11/AmberTools/test/logs/test_at_serial。

## Amber11串行版Amber11编译与测试
先执行/sob/amber11目录下的`./AT15_Amber11.py`以打补丁。进入src目录执行`make serial`，编译约需5分钟。
- 测试通过`cd /sob/amber11/test`和`make test`进行，测试日志位于/sob/amber11/test/logs/test_amber_serial。
- 需在.bashrc中添加`export PATH=$PATH:/sob/amber11/bin`。

## Amber11 CUDA版PMEMD编译与测试
Amber11中仅PMEMD支持CUDA，默认为SPDP模式。在/sob/amber11/AmberTools/src执行`make clean`、`./configure -cuda intel`，并在主目录和src目录重复打补丁和清理操作，最后执行`make cuda`。
- 编译生成的pmemd.cuda位于/sob/amber11/bin，测试脚本为`./test_amber_cuda.sh`。
- 测试中tip4pew_box_npt和tip4pew_oct_nvt可能报错，但.diff文件显示BOND项差异仅为0.0001，可安全忽略。

## Amber11并行版与多GPU版PMEMD编译
并行版AmberTools需在配置时使用`./configure -mpi intel`，并行版Amber11需执行`make parallel`。多GPU版本需配置`./configure -cuda -mpi intel`并执行`make cuda_parallel`。
- 并行版测试需设置`export DO_PARALLEL="mpirun -np 4"`并执行`make test.parallel`。
- 多GPU版测试执行脚本`./test_amber_cuda_parallel.sh`。

## Amber11 CUDA加速比性能测试数据
在包含2492个原子的GB模型测试中，CUDA版本耗时3分11秒（22.6ns/day），4核MPI版本耗时36分29秒（1.97ns/day），加速比为10.5倍。
- 在包含23558个原子的TIP3P水PME模型NVT测试中，CUDA版本耗时2分11秒（13.2ns/day），4核MPI版本耗时5分18秒（5.4ns/day）。

## Amber11编译中MKL库的性能影响
Amber11编译过程中未使用Intel Math Kernel Library (MKL)。MKL对显式溶剂模型下的模拟性能（CPU或CUDA版）无影响，仅能提升CPU版在GB模型下约25%的效率。
- 若需使用MKL，需配置`export MKL_HOME=/opt/intel/mkl`，且对于MKL 12.0及以上版本，需将configure文件中的"em64t"替换为"intel64"。

## Amber12安装前的环境与依赖
Amber12安装需预先安装ifort和icc 12.1.0到默认路径，以及mpich 1.4.1p1（使用`./configure FC=ifort CC=icc`编译）。在.bashrc中设置`AMBERHOME=/sob/amber12`和`PATH=$PATH:$AMBERHOME/bin`。
- 需将AmberTools12.tar.bz2和Amber12.tar.bz2依次解压到安装目录。

## Amber12串行版自动补丁与编译
Amber12编译设置环境变量`export SSE_TYPES=SSE4.2`。执行`./configure intel`时若保持联网，选择y可自动下载并应用补丁；若无联网需手动下载并用patch_amber.py应用。
- 执行`make install`将同时编译AmberTools12和Amber12，耗时约24分钟。

## Amber12并行版与OpenMP版编译
Amber12并行版通过`./configure -mpi intel`和`make install`编译，生成如pmemd.MPI等程序。测试需设置`export DO_PARALLEL="mpirun -np 4"`并执行`make test`。
- 执行`make openmp`可编译OpenMP并行版的NAB和Cpptraj，生成的程序名称与串行版相同。
