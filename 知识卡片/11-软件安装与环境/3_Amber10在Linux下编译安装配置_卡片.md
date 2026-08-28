---
id: 3
title: Amber10安装方法
url: http://sobereva.com/3
domain: 软件安装与环境
topic: Amber10在Linux下编译安装配置
cards: 12
---

# Amber10在Linux下编译安装配置 — 知识卡片

## 1. Amber10基础编译环境配置

Amber10安装需预先配置Intel编译器和数学库环境，若缺少libstdc++.so.5文件需下载指定rpm包安装。在/root/.bashrc中添加ifort路径并设置环境变量FC，安装MKL并设置MKL_HOME及LD_LIBRARY_PATH指向em64t库目录。
- 需安装intel fortran compiler 10.1.015至/opt/intel/fce/10.1.015
- 需安装intel-MKL-10.0.4.023至/opt/intel/mkl/10.0.4.023
- 缺失文件地址：ftp://fr2.rpmfind.net/linux/opensuse/distribution/10.3/repo/oss/suse/x86_64/compat-libstdc++-5.0.7-86.x86_64.rpm

---

## 2. MPICH2并行环境安装方法

下载mpich2-1.0.7源码包并解压，通过configure、make及make install命令编译安装至默认路径。需创建/etc/mpd.conf文件并设置权限，写入secretword，若遇到主机名解析错误需修改/etc/hosts文件。
- 下载地址：http://www.mcs.anl.gov/research/projects/mpich2/
- 配置文件内容示例：secretword=ltwd
- 主机文件示例格式：192.168.2.3 f7 f7

---

## 3. LAM-MPI并行环境安装方法

下载lam-7.1.4源码包，解压后进入目录依次执行configure、make及make install完成安装。
- 下载地址：http://www.lam-mpi.org/7.1/download.php

---

## 4. Intel MPI环境安装方法

从Intel官网下载评估版或从VeryCD下载无限制版Intel Cluster Toolkit Compiler V3.1.1，将授权文件放入目录后执行install.sh脚本。安装后需将impi的bin目录加入PATH环境变量。
- 评估版需.lic文件
- 无限制版目录不能包含空格，需执行chmod 777 -R *
- 环境变量添加：export PATH=$PATH:/opt/intel/impi/3.1/bin

---

## 5. Amber10环境变量与源码准备

在/root/.bashrc中设置MPI_HOME、AMBERHOME及PATH变量，并将AmberTools-1.2和amber10压缩包解压至同一目录。需下载最新的Amber和AmberTools补丁文件至AMBERHOME目录并重命名，随后应用补丁。
- MPI_HOME设置：mpich2/lam为/usr/local，intel mpi为/opt/intel/impi/3.1
- AMBERHOME设置：/sob/amber10
- Amber补丁：http://amber.scripps.edu/bugfixes/10.0/bugfix.all (重命名为bugfixab.all)
- AmberTools补丁：http://amber.scripps.edu/bugfixes/AmberTools/1.2/bugfix.all (重命名为bugfixat.all)

---

## 6. Amber10 AmberTools编译配置

进入src目录执行configure_at gcc脚本，修改config.h文件将FC改为ifort，优化参数FFLAGS由-O1改为-O3并加上-axT，同时删除-fno-automatic，最后执行make命令。
- 命令：./configure_at gcc
- 修改项：FC=ifort, FFLAGS加入-axT, 删除-fno-automatic

---

## 7. Amber10串行版本编译配置

执行configure_amber ifort脚本，修改config_amber.h中FOPTFLAGS的-axWP为-axT，运行make serial编译。若使用intel mpi出现netcdf相关错误，执行make clean后重新make serial。
- 命令：./configure_amber ifort
- 修改项：FOPTFLAGS中-axWP改为-axT

---

## 8. Amber10并行版本编译配置

执行带MPI参数的configure脚本，修改config_amber.h中FOPTFLAGS的-axWP为-axT，运行make parallel编译。根据使用的MPI类型选择不同的参数：mpich2用-mpich2，lammpi用-lam，intel mpi用-intelmpi。
- 命令示例：./configure_amber -mpich2 ifort
- 修改项：FOPTFLAGS中-axWP改为-axT

---

## 9. PMEMD模块编译安装

进入src/pmemd目录，执行configure脚本指定平台、编译器和MPI环境及bintraj选项。修改config.h中F90_OPT_HI的-xP为-axT，最后执行make install。
- 命令：./configure linux_em64t ifort mpich2 bintraj
- 修改项：F90_OPT_HI中-xP改为-axT

---

## 10. Amber10安装后测试

串行版本执行make test和make test.serial.QMMM；并行版本需先启动MPI守护进程，设置DO_PARALLEL变量指定进程数，然后执行make test.parallel和make test.parallel.QMMM。
- MPI启动命令：mpich2用mpd&，lammpi用lamboot，intel mpi用mpdboot
- 并行变量设置：export DO_PARALLEL='mpirun -np 2'

---

## 11. Amber10简化安装方法（自带LAM）

此方法使用Amber自带的lam-7.1.3，无需手动安装LAM或设置MPI_HOME。在完成串行编译及清理后，执行configure_amber -lamsource ifort和configure_lam，最后make parallel。
- 配置命令：./configure_amber -lamsource ifort
- 编译前需修改config_amber.h中FOPTFLAGS的-axWP为-axT

---

## 12. Amber10编译与性能优化经验

Intel CPU必须使用ifort编译器以获得高性能，MKL库可提升约1/6性能。优化选项-axT针对Core2架构，不同CPU应参考Intel文档选择对应选项，推荐使用RHEL5U1或Fedora7系统。
- C语言部分若不使用NAB长时间模拟一般无需icc
- 不使用半经验方法时Ambertools用gfortran性能损失不大
- 选项文档路径：/opt/intel/fce(or cce)/10.1.015/doc/Doc_index.htm
