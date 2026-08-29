---
id: 263
title: Amber14安装方法
domain: 软件安装与环境
topic: Amber14及AmberTools14编译安装
cards: 10
---

## 1. Amber14版本构成与功能分布
Amber14仅包含PMEMD模块，曾经核心的sander模块及其它所有模块均已移至免费开源的AmberTools14中。光靠AmberTools已足以进行动力学模拟，若需要更快的速度和GPU加速才需要购买付费的Amber。
- 编译环境：RHEL6U1-64bit, root, bash
- 硬件：Core 2 Q6600，GTX770
- 安装路径：/sob/amber14

---

## 2. 历史版本安装方法参考
Amber11及AmberTools、Amber12、Amber10的安装方法可参考相关安装文章。

---

## 3. 编译器与OpenMPI环境准备
安装ifort和icc 12.1.0到默认路径，MKL对性能影响很小故不使用。编译OpenMPI 1.6.5（或更新版本），解压后进入目录运行 `./configure CC=icc CXX=icpc FC=ifort F77=ifort; make all install`，将可执行文件等安装到/usr/local目录下。

---

## 4. 环境变量设置与解压
在.bashrc中添加环境变量：`export AMBERHOME=/sob/amber14`，`export PATH=$PATH:$AMBERHOME/bin`，`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$AMBERHOME/lib`。运行bash使环境变量生效，在/sob目录下解压AmberTools14.tar.bz2和Amber14.tar.bz2，保持联网以便安装程序自动应用补丁。

---

## 5. 串行版本编译与测试
在/sob/amber14目录运行 `./configure intel`，检测到补丁时输入y。运行 `make install` 编译（耗时20多分钟），运行 `make test` 测试（耗时约两小时）。测试结果汇总在/sob/amber14/logs目录，部分与orca等程序有关的failure可以忽略。

---

## 6. 并行版本编译与测试
运行 `./configure -mpi intel` 和 `make install`，在bin目录生成MMPBSA.py.MPI、pmemd.amoeba.MPI、pmemd.MPI、sander.LES.MPI、sander.MPI等文件。设置 `export DO_PARALLEL="mpirun -np 4"` 后运行 `make test`，四核机子半小时内完成。

---

## 7. OpenMP并行版NAB和Cpptraj编译
运行 `./configure -openmp intel` 和 `make openmp` 编译OpenMP并行版，生成的程序名仍为nab和cpptraj。

---

## 8. GPU版编译环境配置
下载并安装CUDA toolkit到默认路径（如5.5版本）。在.bashrc中添加：`export CUDA_HOME=/usr/local/cuda-5.5`，`export PATH=$PATH:$CUDA_HOME/bin`，`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$CUDA_HOME/lib64`，运行bash生效。

---

## 9. GPU版PMEMD编译步骤
依次运行 `./configure -cuda intel`、`make install`、`./configure -cuda -mpi intel`、`make install`。bin目录下产生pmemd.cuda和pmemd.cuda.MPI，默认为SPFP版本（精度和速度最佳平衡）。若需更高精度可改用-cuda_DPFP编译DPFP版本，但计算消耗明显更高。

---

## 10. GPU版PMEMD测试
运行 `make test.cuda` 测试串行版，设置 `export DO_PARALLEL="mpirun -np 4"` 后运行 `make test.cuda_parallel` 测试并行版。测试中可能出现半数左右的Possible failure，这是由于GPU动力学重现性低于CPU导致与参考值偏差，不代表设备结果不合理。
