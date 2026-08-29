---
id: 463
title: 量子化学程序Dalton的编译方法和运行方式简介
url: http://sobereva.com/463
domain: 其他量化软件
topic: Dalton程序编译安装与运行基础
cards: 19
---
## 1. Dalton程序简介

Dalton是开源免费的量子化学程序，虽然使用复杂但对新手不友好，但由于擅长计算响应性质（如磷光速率、双光子吸收截面、CASSCF下磁属性等），具有其它程序难以取代的独特地位。此处介绍的Dalton指Dalton suite中从1983年开始发展的程序，而非从其分化的线性标度版LSDalton。相关教程详见北京科音高级量子化学培训班。

---

## 2. Intel编译环境准备

此处基于Intel Fortran/C++编译器、MKL数学库和Intel MPI进行编译，需先下载安装Intel oneAPI Base Toolkit（含DPC++/C++ Compiler和Math Kernel Library）及Intel HPC Toolkit（含Fortran Compiler和MPI Library）。需在用户目录下的.bashrc文件中加入source /opt/intel/oneapi/setvars.sh > /dev/null并重新进入终端使环境生效。

---

## 3. Dalton编译注意事项

原则上Dalton可用gfortran/gcc+OpenMPI编译，但不建议如此，因为编译出的代码比用ifort/icc慢，且可能因个别文件的语法兼容性问题导致编译失败。Intel编译器环境下的AMFI方式旋轨耦合计算存在严重bug（见issue 186），若需进行AMFI计算应改用gcc编译，但运行速度会比Intel版本慢几倍。

---

## 4. 安装cmake 3.x

Dalton 2020.1要求cmake版本为3.x，若系统自带版本过低（如CentOS 7.2自带的2.8版），需在联网情况下运行yum install cmake3安装。需将旧版cmake备份为cmake2，并将新装的cmake3建立符号链接为cmake，命令为mv /usr/bin/cmake /usr/bin/cmake2和ln -s /usr/bin/cmake3 /usr/bin/cmake。

---

## 5. Dalton源码下载

在Linux命令行运行git clone --recursive https://gitlab.com/dalton/dalton.git可将包含external目录完整内容的最新版本下载到当前目录dalton。不要直接在网页点击download下载压缩包，因为那样会缺少external目录下的外部project文件。下载后建议将目录改名为dalton_src，特定版本（如2020.1）可使用-b Dalton2020.1参数下载。

---

## 6. Dalton MPI并行版编译

Dalton主要靠MPI并行，应链接串行版MKL库。在dalton_src目录下依次运行./setup --fc=mpiifort --cc=mpiicx --cxx=mpiicpx --mkl=sequential --prefix=/sob、cd build、make install -j进行编译，安装目录为/sob/dalton。编译完成后需在.bashrc中设置PATH、DALTON_TMPDIR（如/sob）和DALTON_LAUNCHER（如mpirun -np 96）环境变量。

---

## 7. Dalton测试与失败处理

在dalton_src/build目录下运行ctest可进行测试，Dalton 2020.1版约570个测试。若出现Failed结果，通常不是编译问题，可能是开发者提供的参考文件问题或测试项目本身问题（如不支持MPI并行），可在临时文件目录查看输出文件一探究竟。

---

## 8. Dalton串行+MKL并行版编译

对于不支持MPI并行的功能（如耦合簇），可编译串行版但链接并行版MKL库以利用多核。运行./setup --fc=ifort --cc=icx --cxx=icpx --mkl=parallel --prefix=/sob，编译后在.bashrc中注释掉DALTON_LAUNCHER并加入export OMP_NUM_THREADS=96设置线程数。能用MPI并行的任务建议用MPI并行版，耗时通常更低。

---

## 9. Dalton并行运行选择

MKL并行版可以跑所有任务，而MPI并行版只能跑支持MPI并行的任务。凡是能用MPI并行的任务建议使用MPI并行版，因为Dalton中调用MKL数学库的代码本身很有限，MKL并行版耗时一般比MPI版更高，但不排除个别反例，建议实测。

---

## 10. Dalton运行基本格式

运行Dalton一般需要.dal文件（含计算任务说明）和.mol文件（含分子结构、基组定义）。运行格式为dalton [选项] [.dal] [.mol]，例如dalton DFT1 H2O代表使用DFT1.dal的设置计算H2O.mol的体系。运行完毕后当前目录下会产生输出文件（dal名_mol名.out）和包含molden.inp等零碎文件的.tar.gz压缩包。

---

## 11. 监控Dalton运算过程

运算期间屏幕不显示细节，可通过查看$DALTON_TMPDIR/DALTON_scratch_用户名/dal名_mol名_pid号/DALTON.OUT文件监控过程，或使用tail -f [文件名]命令实时同步输出最新信息。

---

## 12. Dalton运行常用选项

常用选项包括：-N 96（指定96个MPI进程，仅MPI版有效）、-omp 96（指定96个OpenMP线程，仅MKL版有效）、-mb 2500/-gb 5（设定每个MPI进程内存上限）、-noarch（不产生.tar.gz文件）、-nobackup（不备份旧输出文件）、-ow（输出文件直接写当前目录）、-o [文件名]（指定输出文件名）。注意MKL_NUM_THREADS环境变量优先级高于-omp选项。

---

## 13. 修改Dalton运行默认选项

dalton命令实际是调用dalton目录下的bash脚本，可通过修改该脚本（2020.1版在74行附近）来设定默认选项。例如将opt_nobackup和opt_noarch设为1，opto设为2，可将nobackup、noarch、ow设为默认启用。

---

## 14. 同时使用MPI和MKL并行版

若需同时使用MPI版（如/sob/dalton_MPI）和MKL版（如/sob/dalton），建议在.bashrc中不设DALTON_LAUNCHER和OMP_NUM_THREADS，但设置别名alias daltonmpi='/sob/dalton_MPI/dalton'。运行时可用dalton -omp 96 love live调用96核MKL版，用daltonmpi -N 96 love live调用96核MPI版。

---

## 15. Dalton输入文件基础知识

Dalton对基组大小写敏感（如aug-cc-pVDZ），默认使用球谐函数、不冻核、自旋多重度为1（闭壳层基态）。.dal文件中可用#或!进行注释。.mol文件格式较麻烦，需按原子类型分别定义，建议使用Multiwfn程序生成输入文件，支持从多种格式（如gjf、fch、xyz等）转换。

---

## 16. Dalton输入文件示例

CCSD(T)单点计算示例：.dal文件需包含**DALTON INPUT下的.RUN WAVE FUNCTIONS，**WAVE FUNCTIONS下的.CC，及*CC INPUT下的.CC(T)。B3LYP优化任务示例：需在**DALTON INPUT下设定.OPTIMIZE，在**WAVE FUNCTIONS下设定.DFT并输入B3LYPg（代表与Gaussian定义相同的B3LYP）。

---

## 17. Dalton .mol文件格式

.mol文件开头需用ATOMBASIS或BASIS指定基组方式，后接两行任意标题。需设定Atomtypes（原子类型数）、Angstrom（单位）、Nosymmetry（无对称性）、charge（电荷）。之后按原子类型列出Charge（核电荷）、Atoms（原子数）、Basis（基组名）及各原子坐标。Atomtypes指非等价原子种类数，使用Nosymmetry时直接对应元素数。

---

## 18. Dalton基组与赝势使用

Dalton基组库目录(dalton\basis)下的基组可通过basis或atombasis使用，基组名即为文件名。赝势位于basis/ecp_data目录，可通过ECP=xxx使用。示例：Basis=stuttgart_rlc_ecp ECP=stuttgart_rlc_ecp，要求基组名和赝势名在对应目录中有同名文件。

---

## 19. 使用Multiwfn生成Dalton输入文件

启动Multiwfn载入含结构信息的文件（如gjf、fch、xyz等），依次输入主功能100、子功能2、子功能19，并指定.dal和.mol文件名，即可生成Dalton输入文件（默认为B3LYP单点计算，6-31G*基组，无对称性）。若载入文件含波函数信息（如.fch），Multiwfn还可将轨道作为初猜写入.dal文件。
