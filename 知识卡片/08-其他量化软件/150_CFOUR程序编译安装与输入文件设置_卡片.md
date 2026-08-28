---
id: 150
title: CFOUR程序的编译和使用方法简介
url: http://sobereva.com/150
domain: 其他量化软件
topic: CFOUR程序编译安装与输入文件设置
cards: 15
---

# CFOUR程序编译安装与输入文件设置 — 知识卡片

## 1. CFOUR程序概述与功能特点

CFOUR是由ACESII-MAB改名而来的从头算程序，特别适合微扰和耦合簇的大规模并行计算，支持HF、微扰、CI、QCI计算但不支持DFT。CFOUR的耦合簇最高能做到CCSDT，且在这样的级别下还能支持二阶解析导数，对GIMIC, MRCC, DIRAC, NEWTON-X程序提供了接口。CFOUR是免费开源程序，需在主页下载授权表签字后通过传真或实体邮件发送给开发者才能获得，比ACESII相对更user-friendly但仍不适合初学者。
- 官方主页：http://www.cfour.de
- 在线手册：http://slater.chemie.uni-mainz.de/cfour/index.php?n=Main.Manual

---

## 2. CFOUR支持的计算方法与属性

CFOUR可以执行单点、几何优化、寻找过渡态、算激发态（EOM-CC）、算红外、拉曼、NMR、g张量、静态/含频极化率和超极化率等多种任务。CFOUR单点计算支持R/U/ROHF,TCSCF,MP2/3/4,CC2/3,CCD,CCSD,CCSD+T,CCSD(T),CCSDT,CCSDT-n (n=1-4),Brueckner-CCD (B-CCD),B-CCD(T),Orbital-optimized CC (OO-CC),CID,CISD,QCISD,QCISD(T)等方法。
- 支持一阶解析梯度的方法包括：HF-SCF,TCSCF,MP2/3/4,CC2/3,QCISD,QCISD(T),CCD,CCSD,CCSD(T),CCSDT-n (n=1-4),CCSDT
- 支持二阶解析梯度的方法包括：HF-SCF (RHF, UHF),MP2/3/4 (RHF, UHF),CCD,CCSD,CCSD(T) (RHF, UHF),CCSDT-n (n=1-4),CCSDT (RHF)

---

## 3. CFOUR串行版本的编译方法

在64bit Linux平台下编译CFOUR串行版本，需解压源代码包并进入目录，运行./configure FC=ifort（如果未安装ifort则改为FC=gfortran），然后执行make。编译出的文件会出现在bin目录下，最后需要将export PATH=$PATH:/[cfour目录]/bin加入到当前用户的.bashrc文件中并使其生效。
- 注意：如果使用ifort 12.x，由于bug，在./configure生成make.config文件后，必须将文件中的-O3都改为-O2才能继续编译。

---

## 4. CFOUR并行版本（含MKL和GIMIC接口）的编译方法

编译CFOUR并行版本（支持mpich2+MKL+GIMIC接口），需安装ifort和mpich2到默认路径，并设置MKLPATH环境变量。在CFOUR源代码目录下，执行带有--enable-gimic、--with-blas（含MKL库链接参数）、--enable-mpi=mpich等选项的./configure命令，之后运行make。最后同样需要将bin目录路径加入环境变量PATH中。
- 典型配置命令：`./configure FC=ifort MPIFC=mpif90 --enable-gimic --with-blas="$MKLPATH/libmkl_solver_ilp64.a -Wl,--start-group $MKLPATH/libmkl_intel_ilp64.a $MKLPATH/libmkl_intel_thread.a $MKLPATH/libmkl_core.a -Wl,--end-group -openmp -lpthread" --enable-mpi=mpich --with-mpirun="mpirun -np \$CFOUR_NUM_CORES" --with-exenodes="mpirun -np \$CFOUR_NUM_CORES"`

---

## 5. CFOUR运行前的文件准备与启动命令

运行CFOUR前必须将CFOUR目录下basis文件夹里的GENBAS基组文件拷贝到ZMAT所在目录下，如果使用赝势也要拷贝ECPDATA文件。输入文件必须命名为ZMAT，在ZMAT所在目录下输入xcfour命令即可开始运算。运行过程信息输出到屏幕，当前目录下会产生大量文件，计算新任务前应将其删除。
- 启动命令：xcfour

---

## 6. CFOUR并行计算的环境变量设置与效率优化

使用并行+MKL版本运行CFOUR前需设定CFOUR_NUM_CORES和MKL_NUM_THREADS环境变量，前者控制MPI进程数（资源消耗成倍增加），后者控制每个MPI进程的MKL线程数（不增加资源消耗）。对于四核机器，通常CFOUR_NUM_CORES设为4、MKL_NUM_THREADS设为1比设为1/4快很多，但由于后HF计算硬盘I/O瓶颈，2/2的设置可能比4/1更快。
- 设置示例：`export CFOUR_NUM_CORES=4` 和 `export MKL_NUM_THREADS=2`
- 运行时直接输入xcfour，程序会自动加上mpirun指令，不要手动在命令行添加mpirun。

---

## 7. CFOUR并行计算的关键词要求与MP2并行策略

CFOUR支持MPI并行的功能主要是耦合簇计算，输入文件中必须包含CC_PROGRAM=ECC和ABCDTYPE=AOBASIS关键词（即使不并行，带上它们也比默认情况快）。对于不支持MPI并行的任务如MP2，若要并行化，只能依靠MKL_NUM_THREADS，此时应使用串行版本并在编译./configure步骤中加上MKL库支持。
- MKL编译选项串：`--with-blas="$MKLPATH/libmkl_solver_ilp64.a -Wl,--start-group $MKLPATH/libmkl_intel_ilp64.a $MKLPATH/libmkl_intel_thread.a $MKLPATH/libmkl_core.a -Wl,--end-group -openmp -lpthread"`

---

## 8. CFOUR输入文件基本格式与行宽限制

CFOUR输入文件必须命名为ZMAT，第一行为注释，接着是分子坐标（默认单位为埃，元素名顶头写），然后是变量定义，最后是*CFOUR()关键词部分及特殊任务输入。每行不得超过80个字符，关键词行若超长可分多行书写，换行处末尾不加逗号但必须保留一个空格。
- 示例：
```text
Water CC-LR/DZP at experimental equilibrium geometry
O
H 1 R
H 1 R 2 A
R=0.958
A=104.5
*CFOUR(CALC=CCSD,BASIS=DZP,EXCITE=EOMEE)
```

---

## 9. CFOUR几何优化的输入设置

在CFOUR输入文件中，若想优化分子结构，不需要专门写关键词，只需在相应的内坐标变量上打星号即可。
- 示例：
```text
O
H 1 R*
H 1 R* 2 A*
```

---

## 10. CFOUR内存与SCF相关常用关键词

CFOUR通过EMORY关键词设置可用内存，单位默认为INTEGERWORDS（32/64位平台需乘以4/8转换为KB），可用MEM_UNIT改变单位。SCF相关设置包括收敛标准SCF_CONV、阻尼SCF_DAMPING（设500有助于解决不收敛）、最大迭代次数SCF_MAXCYC、DIIS外推SCF_EXTRAPOLATION、高斯函数类型SPHERICAL、对称性SUBGROUP以及输出级别PRINT。
- 常用设置：
  - `SCF_CONV=N`：密度矩阵最大变化小于10^-N停止，默认7
  - `SCF_DAMPING=500`：解决SCF不收敛
  - `SCF_MAXCYC`：最大迭代次数，默认150
  - `PRINT=1`：输出更多细节信息

---

## 11. CFOUR几何优化与过渡态寻找关键词

CFOUR中GEO_METHOD=TS用于寻找过渡态，GEO_CONV=N设定优化收敛限为N Hartree/bohr，GEO_MAXCYC设定最大优化步数（默认50），GEO_MAXSTEP设定几何优化的最大步长（单位millibohr，默认300）。EVAL_HESS=N用于设定每隔N个优化步计算一次精确Hessian，默认为从不（使用准牛顿法）。
- 关键词：
  - `GEO_METHOD=TS`：寻找过渡态
  - `GEO_CONV=N`：优化收敛限
  - `EVAL_HESS=N`：每隔N步算一次精确Hessian

---

## 12. CFOUR激发态、并行加速与属性计算关键词

CFOUR使用EXCITE设定EOM-CC/LR-CC类型（EOMEE计算激发态，EOMIP计算离子化态，EOMEA计算电子附着态）。建议对最高至CCSD(T)的计算加上ABCDTYPE=AOBASIS以加快速度。CC_PROGRAM建议设为ECC以加速CCSD, CCSD+T, CCSD(T)等计算。PROPS、RAMAN_INT、RELATIVISTIC、DBOC、VIBRATION等关键词用于控制各种属性和频率计算。
- 关键词设置：
  - `EXCITE=EOMEE`：计算激发态
  - `ABCDTYPE=AOBASIS`：加速计算
  - `CC_PROGRAM=ECC`：控制CC计算程序
  - `PROPS=NMR`：计算NMR
  - `VIBRATION=ANALYTIC`：用解析二阶导数计算谐振频率

---

## 13. CFOUR轨道冻结、参考波函数与收敛控制关键词

CFOUR在post-HF中默认不冻芯，FROZEN_CORE=ON可冻结内核轨道，DROPMO可具体指定冻结哪些轨道（如1>10-55-58>64）。HFSTABILITY=ON进行SCF波函数稳定性测试，REFERENCE选择参考波函数（RHF/UHF/ROHF/TCSCF）。RESTART_CC=1重启CC计算，CC_CONV=N设定CC收敛标准（系数最大改变值小于10^-N，默认7）。
- 关键词：
  - `FROZEN_CORE=ON`：post-HF中冻结内核轨道
  - `DROPMO=1>10-55-58>64`：指定冻结轨道
  - `CC_CONV=N`：CC收敛标准

---

## 14. CFOUR支持的基组列表（BASIS关键词）

CFOUR的BASIS关键词支持多种基组，包括Pople系列（如6-31G*）、Dunning系列（如cc-pVDZ）、极化与弥散基组（如AUG-PVTZ）等。参数对大小写敏感。
- 部分列举：
  - STO-3G, 3-21G, 6-31G*, 6-311G**
  - DZ, DZP, TZ, TZP, TZ2P
  - PVDZ, PVTZ, PVQZ, PV5Z, PV6Z
  - AUG-PVDZ, AUG-PVTZ, AUG-PVQZ
  - cc-pVDZ, cc-pVTZ, cc-pVQZ, cc-pCVTZ
  - ANO0, ANO1, ANO2

---

## 15. CFOUR支持的计算方法列表（CALC关键词）

CFOUR的CALC关键词支持SCF(HF)、微扰理论(MP2/3/4)、耦合簇(CCSD, CCSD(T), CCSDT-n, CC2, CC3)、QCISD、CI(CID, CISD)等多种方法。部分高级方法如CCSDTQPH需要外挂MRCC程序实现。
- 支持的方法：
  - SCF (or HF), MBPT(2) (or MP2), MBPT(3) (or MP3), MBPT(4) (or MP4)
  - CCD, CCSD, CCSD(T), CCSDT-1a, CCSDT-2, CCSDT-3, CCSDT-4, CCSDT
  - CC2, CC3, QCISD, QCISD(T), CID, CISD
