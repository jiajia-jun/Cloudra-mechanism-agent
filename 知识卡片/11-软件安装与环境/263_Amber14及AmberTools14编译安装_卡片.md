---
id: 263
title: Amber14安装方法
url: http://sobereva.com/263
domain: 软件安装与环境
topic: Amber14及AmberTools14编译安装
cards: 1
---

# Amber14及AmberTools14编译安装 — 知识卡片

## 1. Amber14与AmberTools14的模块构成关系

Amber14仅包含PMEMD一个模块，曾经最核心的sander模块及其它所有模块已被移至免费的AmberTools14中。仅依靠AmberTools14即可进行动力学模拟，若需要更快的速度和GPU加速才需购买Amber。
- 引用自《Amber14安装方法》

## Amber14安装所需的编译环境与依赖
编译环境为RHEL6U1-64bit，硬件为Core 2 Q6600和GTX770。需要安装ifort和icc 12.1.0到默认路径，并编译OpenMPI 1.6.5。配置OpenMPI时运行命令 `./configure CC=icc CXX=icpc FC=ifort F77=ifort; make all install`，此时OpenMPI相关文件会被装到/usr/local目录下。
- 引用自《Amber14安装方法》

## Amber14的环境变量配置
需要在.bashrc文件中添加环境变量：`export AMBERHOME=/sob/amber14`、`export PATH=$PATH:$AMBERHOME/bin`、`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$AMBERHOME/lib`。配置后运行bash使环境变量生效。
- 引用自《Amber14安装方法》

## Amber14的文件解压与准备
将AmberTools14.tar.bz2和Amber14.tar.bz2在/sob目录下解压，后者会合并目录并覆盖部分文件。解压后amber14目录下应包含Ambertools、src、benchmarks等目录，安装期间需保持联网以自动应用官网补丁。
- 引用自《Amber14安装方法》

## Amber14串行版本的编译与测试
进入/sob/amber14目录，运行 `./configure intel`，检测到补丁时输入y。运行 `make install` 进行编译，耗时约20多分钟；运行 `make test` 进行测试，耗时约2小时。
- 引用自《Amber14安装方法》

## Amber14串行版本测试的注意事项
测试内容包括面向第三方量化程序的QMMM接口，会调用机子上的gaussian、orca、terachem等程序。测试日志汇总在/sob/amber14/logs目录下，部分与orca有关的failure无关紧要。
- 引用自《Amber14安装方法》

## Amber14并行版本(MMPI)的编译与测试
运行 `./configure -mpi intel` 和 `make install`，会在bin目录下生成MMPBSA.py.MPI、pmemd.amoeba.MPI、pmemd.MPI、sander.LES.MPI、sander.MPI等后缀为.MPI的文件。测试时设置 `export DO_PARALLEL="mpirun -np 4"` 并运行 `make test`，四核机子约半小时完成。
- 引用自《Amber14安装方法》

## Amber14 OpenMP并行版NAB和Cpptraj的编译
运行 `./configure -openmp intel` 和 `make openmp`，编译出来的程序名称仍为nab和cpptraj。
- 引用自《Amber14安装方法》

## Amber14 GPU版PMEMD的环境配置
需安装CUDA toolkit到默认路径（版本为5.5），并在.bashrc中添加：`export CUDA_HOME=/usr/local/cuda-5.5`、`export PATH=$PATH:$CUDA_HOME/bin`、`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$CUDA_HOME/lib64`。运行bash使之生效。
- 引用自《Amber14安装方法》

## Amber14 GPU版PMEMD的编译方法
进入/sob/amber14目录，依次运行 `./configure -cuda intel` 和 `make install` 编译串行版，运行 `./configure -cuda -mpi intel` 和 `make install` 编译并行版。编译完成后bin目录下产生pmemd.cuda和pmemd.cuda.MPI。
- 引用自《Amber14安装方法》

## Amber14 GPU版PMEMD的精度版本说明
默认编译的GPU版PMEMD为SPFP版本，是精度和速度的最佳平衡。另一种DPFP版本精度更高但计算消耗也明显更高，编译时将-cuda改为-cuda_DPFP即可，一般没必要使用。
- 引用自《Amber14安装方法》

## Amber14 GPU版PMEMD的测试与结果分析
运行 `make test.cuda` 测试串行版，设置 `export DO_PARALLEL="mpirun -np 4"` 后运行 `make test.cuda_parallel` 测试并行版。由于GPU跑动力学的重现性比CPU低，容易产生接近半数的Possible failure，但这通常是探索相空间不同区域导致的偏差，不代表结果不合理。
- 引用自《Amber14安装方法》
