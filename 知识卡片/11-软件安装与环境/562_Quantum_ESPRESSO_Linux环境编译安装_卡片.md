---
id: 562
title: Quantum ESPRESSO在Linux下的安装方法
url: http://sobereva.com/562
domain: 软件安装与环境
topic: Quantum_ESPRESSO_Linux环境编译安装
cards: 9
---
## 1. Quantum ESPRESSO安装环境与基础

本卡片适用于CentOS 7.x系统下安装QE 6.5，基于OpenMPI库+MKL库+gfortran/gcc编译器编译纯CPU版本。安装使用root账户，普通用户需安装在有读写权限的目录；若未安装gcc和gfortran，需先用yum install gcc命令安装。更多编译细节详见QE手册[https://www.quantum-espresso.org/Doc/user_guide/node10.html](https://www.quantum-espresso.org/Doc/user_guide/node10.html)。

---

## 2. OpenMPI的安装与配置

需下载OpenMPI（如4.0.3版）并编译安装到指定目录，例如/sob/openmpi。编译命令为`./configure --prefix=/sob/openmpi`和`make all install`；安装后需在~/.bashrc中加入`export PATH=$PATH:/sob/openmpi/bin`和`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/openmpi/lib`。可通过运行`mpiexec -V`验证是否安装成功，并注意使用`which mpiexec`确认调用的MPI库是否正确。

---

## 3. MKL库的安装

为提升计算速度，需先安装MKL数学库，可通过添加intel源`yum-config-manager --add-repo https://yum.repos.intel.com/mkl/setup/intel-mkl.repo`并运行`yum install -y intel-mkl`进行安装。安装文件在/opt/intel目录下占3GB多（以2020-Jul-10下载版本为准）；若之前安装Intel编译器时已包含MKL，则无需重复安装。

---

## 4. QE源码的编译步骤

下载QE源码包（如qe-6.5-ReleasePack.tgz）并解压，运行`./configure --prefix=/sob/qe65 -enable-openmp`配置，再执行`make all install -j`进行编译。编译完成后可执行文件位于/sob/qe65/bin目录；若需修改默认编译器，需编辑make.inc文件。上述编译不包含EPW、PLUMED等程序，如需编译请查阅User's Guide 2.5节。

---

## 5. QE环境变量配置

编译完成后需在~/.bashrc中添加环境变量，root用户需加入`export OMPI_ALLOW_RUN_AS_ROOT=1`和`export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1`。所有用户均需添加`export PATH=$PATH:/sob/qe65/bin`以及`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/intel/compilers_and_libraries_2020.2.254/linux/mkl/lib/intel64_lin`，路径需根据实际情况调整。设置完毕后重新进入终端即可生效。

---

## 6. QE并行计算模式与测试

QE采用MPI和OpenMP混合并行，总并行核数为MPI进程数与每个进程OpenMP线程数的乘积。纯MPI并行测试可设置`export OMP_NUM_THREADS=1`并运行`mpirun -n 4 pw.x < pwscf.in |tee pwscf.out`。纯OpenMP并行测试可设置`export OMP_NUM_THREADS=4`并直接运行`pw.x < pwscf.in |tee pwscf.out`。若任务末尾显示JOB DONE则说明安装成功。

---

## 7. QE自带测试集的使用

可使用QE自带的测试集进行测试，进入解压目录下的test-suite子目录，运行`make run-tests-parallel`可在并行运算下测试所有任务。若只想测试PWscf模块，可运行`make run-tests-pw-parallel`。各项测试的具体含义可查阅test-suite目录下的README文件。

---

## 8. 使用yum安装QE的方法

在CentOS下（root用户）可运行`yum install epel-release`和`yum install quantum-espresso-openmpi`安装QE 6.5版（基于OpenMPI并行，不支持OpenMP）。此方法会自动安装OpenMPI、OpenBLAS、ScaLAPack等包，但若运行`yum install quantum-espresso`则只能安装串行版本。安装后需在~/.bashrc中添加`export PATH=$PATH:/usr/lib64/openmpi/bin/`，root用户还需添加允许root运行MPI的两个变量。

---

## 9. 预编译版QE的局限与建议

通过yum安装的预编译版QE位于/usr/lib64/openmpi/bin/目录，可执行文件带有_openmpi后缀（如pw.x_openmpi）。预编译版为兼容性和减少依赖，可能未使用MKL且编译选项保守，性能通常逊于自行编译的版本。建议自行编译以便自定义安装位置、优化性能以及通过make命令（如make epw）灵活编译安装其它相关程序。
