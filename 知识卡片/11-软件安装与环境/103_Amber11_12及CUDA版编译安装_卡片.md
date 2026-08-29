---
id: 103
title: Amber11+AmberTools1.5及CUDA版安装方法，以及Amber12安装方法
url: http://sobereva.com/103
domain: 软件安装与环境
topic: Amber11_12及CUDA版编译安装
cards: 15
---

# Amber11_12及CUDA版编译安装 — 知识卡片

## 1. 安装Intel编译器环境

Amber11安装需要Intel C++ (icc) 和 Fortran (ifort) 编译器，版本示例为2011.6.233。非商业用户可从Intel官网申请一年有效期的授权，将收到的.lic文件存入/sob/licenses，安装时选择通过license文件激活并取消Intel Debugger组件，最后将`source /opt/intel/composer_xe_2011_sp1.6.233/bin/compilervars.sh intel64`添加到.bashrc。
- 若安装器提示找不到libstdc++库，需先安装libstdc++-4.4.5-6.el6.i686.rpm。

---

## 2. 配置CUDA Toolkit环境

安装CUDA Toolkit 4.0对应RedHat Enterprise Linux 6.0的版本，运行./cudatoolkit_4.0.17_linux_64_rhel6.0.run。需在.bashrc中设置环境变量：`export PATH=$PATH:/usr/local/cuda/bin`，`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/cuda/lib64:/usr/local/cuda/lib`，`export CUDA_HOME=/usr/local/cuda`。

---

## 3. 编译安装MPICH2

解压MPICH2 1.4.1p1，使用配置命令`./configure FC=ifort CC=icc`，随后执行make和make install。若运行mpd命令报错"'MPD' object has no attribute 'myIP'"，需在/etc/hosts文件末尾添加"127.0.0.1 主机名 主机名"。
- 当前版本MPICH2运行"mpirun -np x"前无需像旧版那样启动MPD。

---

## 4. Amber11安装前准备与补丁应用

设置环境变量`export AMBERHOME=/sob/amber11`，解压Amber11.tar.bz2和AmberTools-1.5.tar.bz2到该目录。分别从官网下载AmberTools1.5的bugfix.all和Amber11的bugfix包(如bugfix.1to17.tar.bz2)及apply_bugfix.x，通过`patch -p0 -N < bugfix.all`和`./apply_bugfix.x bugfix.1to17.tar.bz2`应用补丁。

---

## 5. 编译AmberTools 1.5串行版

进入/sob/amber11/AmberTools/src，执行`./configure intel`配置，使用`make install`编译，约耗时20分钟。编译完成后进入../test目录执行`make test`进行测试，可到/sob/amber11/AmberTools/test/logs/test_at_serial查看.diff文件结果。
- 禁止使用-j选项加速编译。

---

## 6. 编译Amber11串行版

先在/sob/amber11目录运行`./AT15_Amber11.py`打补丁，进入src目录执行`make serial`编译，耗时约5分钟。进入/sob/amber11/test目录执行`make test`测试，结果日志位于/sob/amber11/test/logs/test_amber_serial。
- PMEMD无需像旧版那样单独编译。

---

## 7. 编译PMEMD CUDA版本

进入/sob/amber11/AmberTools/src，执行`make clean`和`./configure -cuda intel`；返回/sob/amber11运行`./AT15_Amber11.py`；再进入src目录执行`make clean`和`make cuda`。生成的pmemd.cuda位于/sob/amber11/bin，运行./test_amber_cuda.sh测试，耗时约1分16秒。
- 测试中tip4pew_box_npt和tip4pew_oct_nvt可能报错，但.diff文件显示差异极小(BOND项0.0001)，可忽略。

---

## 8. 编译AmberTools 1.5并行版

进入/sob/amber11/AmberTools/src，执行`make clean`、`./configure -mpi intel`和`make install`。此步骤会生成pbsa.MPI、ptraj.MPI、mpinab等程序，若不常用并行版AmberTools可跳过此步骤。

---

## 9. 编译Amber11并行版

在/sob/amber11目录运行`./AT15_Amber11.py`，进入src目录执行`make clean`和`make parallel`，耗时约6分钟，生成pmemd.MPI、sander.MPI等。测试时需设置环境变量`export DO_PARALLEL="mpirun -np 4"`，然后在/sob/amber11/test目录运行`make test.parallel`。

---

## 10. 编译多GPU版PMEMD

仅当安装了多块GPU时才执行此步骤。配置时使用`./configure -cuda -mpi intel`，执行`make cuda_parallel`，生成pmemd.cuda_SPDP.MPI。最后通过运行./test_amber_cuda_parallel.sh进行测试。

---

## 11. Amber11 GPU与CPU性能对比测试

使用官方基准包测试：GB模型(2492原子)下，pmemd.cuda耗时3分11秒(22.6ns/day)，4核pmemd.MPI耗时36分29秒(1.97ns/day)，加速比10.5倍；显式溶剂PME模型(23558原子，NVT)下，pmemd.cuda耗时2分11秒(13.2ns/day)，4核pmemd.MPI耗时5分18秒(5.4ns/day)，加速比不明显。

---

## 12. Intel MKL库对性能的影响

编译过程中未使用Intel MKL库，因为MKL对显式溶剂模型下的模拟性能(CPU或CUDA版)无影响。仅CPU版在GB模型下使用MKL可提升约25%的效率；若需使用，配置前需设置`export MKL_HOME=/opt/intel/mkl`，且MKL 12.0及以上版本需将configure中的"em64t"替换为"intel64"。

---

## 13. Amber12串行版编译

解压AmberTools12.tar.bz2和Amber12.tar.bz2，设置AMBERHOME并添加bin到PATH。导出`export SSE_TYPES=SSE4.2`，运行`./configure intel`，联网情况下选择'y'自动下载并应用补丁。执行`make install`同时编译AmberTools和Amber12，耗时约24分钟；`make test`耗时较长，rism1d测试可能会卡住。

---

## 14. Amber12并行版编译

执行`./configure -mpi intel`配置，运行`make install`生成MMPBSA.py.MPI、pmemd.amoeba.MPI、pmemd.MPI、sander.LES.MPI、sander.MPI。设置`export DO_PARALLEL="mpirun -np 4"`，运行`make test`进行测试，四核机器约半小时内完成19个测试且全部通过。

---

## 15. 编译Amber12的OpenMP版程序

在已配置的环境中，执行`make openmp`可编译OpenMP并行版的NAB和Cpptraj。编译生成的程序名称仍为nab和cpptraj，与串行版本名称相同。
