---
key: b586
title: CP2K第一性原理程序在CentOS中的简易安装方法
url: http://sobereva.com/586
domain: 软件安装与环境
source: blog
year: 2021
cards: 29
---

# CP2K第一性原理程序在CentOS中的简易安装方法 — 知识卡片

## 1. CP2K程序概述

CP2K是功能强大且开源免费的第一性原理计算程序，计算速度快，尤其适用于中、大周期性体系。该程序支持自行编译以充分利用CPU指令集和架构优化，从而获得比预编译版本更好的性能。

---

## 2. 推荐操作系统与编译器选择

Rocky Linux（推荐）、CentOS Stream、Fedora或RedHat系统适合用于安装CP2K。编译过程需要系统具备Fortran和C/C++编译器，通常使用Linux系统自带的gcc/gfortran，要求gcc版本必须>=5.5。

---

## 3. 编译依赖库：toolchain脚本（2026.2及以后版本）

安装CP2K依赖库最便捷的方法是使用自带的toolchain脚本，该脚本可自动下载、解压并编译所需的库。执行命令为 `./install_cp2k_toolchain.sh --with-openmpi=install -j [CPU物理核心数]`，安装内容默认包含CP2K运行所需的重要库。

---

## 4. toolchain脚本中的OpenMPI配置选项

toolchain脚本中的 `--with-openmpi=install` 选项表示自动安装OpenMPI库以支持MPI并行计算。如果系统中已经安装了OpenMPI，为避免冲突，应使用 `--with-openmpi=system` 选项直接调用系统现有库。

---

## 5. toolchain脚本中的tblite与DFT-D4配置

`--with-tblite=install` 选项会编译tblite库，使CP2K能够进行GFN2-xTB计算，并自动附带安装支持DFT-D4色散校正的dftd4库。若不需要GFN2-xTB功能，可使用 `--with-tblite=no` 跳过安装；若不安装tblite但需使用D4校正，则需明确加上 `--with-dftd4=install`。

---

## 6. toolchain脚本中的SIRIUS与PLUMED配置

`--with-sirius=install` 选项允许CP2K基于平面波+赝势进行计算。`--with-plumed=install` 选项用于安装PLUMED库，以增强CP2K在分子动力学增强采样方面的功能支持。

---

## 7. toolchain安装故障处理（编译失败）

若toolchain运行过程中某个库编译失败，可进入 `toolchain/build` 目录下对应库的文件夹中查看log文件并搜索error信息进行分析。重新运行toolchain脚本时，会自动跳过已下载和编译成功的库，从失败处继续。

---

## 8. toolchain安装故障处理（下载卡顿）

若安装过程中某个库一直卡住且CPU无编译活动，通常是因为网速过慢导致压缩包下载困难。解决方法包括使用网络加速工具，或者提前在联网环境下下载所需的压缩包放入 `toolchain/build` 目录进行离线安装。

---

## 9. CP2K编译步骤（2026.2及以后版本）

完成依赖库安装后，在 `tools/toolchain` 目录下运行 `./build_cp2k.sh -j [CPU物理核心数]` 即可开始编译CP2K。编译成功后，可执行文件（如cp2k.psmp）将存放在 `/sob/cp2k-2026.2/install/bin` 目录下。

---

## 10. CP2K环境变量配置（2026.2及以后版本）

编译完成后，需将 `source /sob/cp2k-2026.2/install/cp2k_env` 添加到 `~/.bashrc` 文件末尾。重新进入终端后，即可直接通过 `cp2k.psmp` 命令运行程序，使用 `-v` 参数可查看版本及编译配置信息。

---

## 11. CP2K并行模式概述

CP2K支持MPI并行、OpenMP并行以及两者混合的并行模式（MPI进程数*OpenMP线程数=总核心数）。通常情况下，纯MPI并行的速度最快，但内存消耗最大；纯OpenMP并行速度最慢，但最省内存；混合并行则介于两者之间。

---

## 12. CP2K并行运行命令示例

使用MPI并行时，进程数由 `mpirun -np` 指定；使用OpenMP并行时，需设置环境变量 `OMP_NUM_THREADS`。例如，16核纯MPI运行命令为 `mpirun -np 16 cp2k.popt test.inp |tee test.out`，混合并行（如4进程*4线程）需先设置 `export OMP_NUM_THREADS=4` 再运行 `mpirun -np 4 cp2k.psmp test.inp`。

---

## 13. CP2K并行优化建议

对于大多数计算任务，建议采用纯MPI并行方式以获得最高效率。对于振动分析、NEB任务以及杂化泛函计算等内存需求巨大的场景，建议结合使用MPI与OpenMP并行以避免内存不足崩溃。

---

## 14. CP2K旧版toolchain依赖库安装（<=2025.2）

对于CP2K 2025.2及更早版本，使用toolchain安装依赖库的命令为 `./install_cp2k_toolchain.sh --with-sirius=no --with-openmpi=install --with-plumed=install`。该过程会自动下载并编译库文件，其中编译libint库通常耗时最长。

---

## 15. 旧版CP2K编译与环境配置（<=2025.2）

完成toolchain安装后，需将 `tools/toolchain/install/arch/` 下的文件拷贝至 `arch` 目录，并运行 `source /sob/cp2k-8.1/tools/toolchain/install/setup`。编译命令为 `make -j 4 ARCH=local VERSION="ssmp psmp"`，编译成功后需将toolchain的setup脚本路径加入 `~/.bashrc` 并将可执行文件目录加入PATH环境变量。

---

## 16. CP2K官方预编译版使用方法

官方提供的预编译版（如ssmp版本）无需编译，下载并改名后放入目录即可使用。配置环境变量时需在 `~/.bashrc` 中添加 `export PATH=$PATH:[目录路径]` 和 `export CP2K_DATA_DIR=[目录路径]/data`。

---

## 17. MKL数学库的配置与使用

CP2K默认使用OpenBLAS，若需改用Intel MKL数学库以提升潜在性能，需先安装MKL并确保 `MKLROOT` 环境变量被正确指向。toolchain脚本检测到该环境变量后会自动调用MKL进行编译。

---

## 18. DFT-D4色散校正支持（旧版）

从CP2K 2024.2版本开始支持DFT-D4色散校正。若需使用此功能，在运行旧版toolchain脚本时必须额外加上 `--with-ninja --with-dftd4` 选项。

---

## 19. CP2K_DATA_DIR 环境变量的作用

CP2K输入文件中的BASIS_SET_FILE_NAME和POTENTIAL_FILE_NAME等关键词若仅定义文件名而未指定路径，程序会先在当前目录搜索，找不到则去CP2K_DATA_DIR指定的目录搜索。编译时该变量对应CP2K源码目录下的data路径，通常与实际运行环境不符，需通过export命令将其修改为本机实际的data目录路径。

---

## 20. CP2K 运行测试输入文件

测试使用了一个由Multiwfn生成的2*2*2金刚石超胞进行PBE/DZVP-MOLOPT-SR-GTH单点计算的输入文件。

---

## 21. CP2K ssmp 版运行方法

将测试输入文件test.inp置于当前目录，执行命令`cp2k.ssmp test.inp |tee test.out`可运行ssmp版，输出信息会显示在屏幕并写入test.out文件。默认情况下所有CPU核心用于OpenMP并行，若需限制为4核，需先执行`export OMP_NUM_THREADS=4`，此时进程CPU占用率应在300~400%。

---

## 22. CP2K popt 版运行方法

使用4核通过MPI并行运行popt版时，执行命令`mpirun -np 4 cp2k.popt test.inp |tee test.out`。在top中会观察到4个cp2k.popt进程在运行，且每个进程的CPU占用率均接近100%。

---

## 23. CP2K 版本选择与别名设置

自行编译CP2K时建议默认使用popt版而非ssmp版，因为前者在某些情况下运行效率远高于后者（尽管部分任务差异不大）。为简化操作，建议在~/.bashrc中添加别名`alias cp2k='mpirun -np 4 cp2k.popt'`，配置生效后输入`cp2k test.inp |tee test.out`即等价于完整的MPI运行命令。

---

## 24. CP2K sopt 与 popt 版的线程设置

运行sopt版或popt版时，无论是否设置OMP_NUM_THREADS或设置为何值，该变量都会被强制视为1。

---

## 25. CP2K 并行方式特点

CP2K支持MPI和OpenMP两种并行方式，纯MPI并行内存消耗较高，纯OpenMP并行通过共享数据更节省内存但部分任务速度可能较慢且高核数下效率略低。混合并行（如9个MPI进程配4个OpenMP线程）能兼顾效率与内存，特别适用于杂化泛函计算，通过in-core方式避免迭代中重算双电子积分。

---

## 26. CP2K 并行方式的适用范围

MPI或MPI+OpenMP混合并行支持跨节点并行，而纯OpenMP基于共享内存技术，仅限于单机（节点内）并行。

---

## 27. CP2K 四种版本的定义

根据支持的并行方式，CP2K分为sopt（仅单机单核）、ssmp（单机OpenMP并行）、popt（MPI并行，支持单机或跨节点）、psmp（MPI+OpenMP混合并行，支持单机或跨节点）。

---

## 28. CP2K 版本间的等价关系

sopt版严格等价于ssmp版结合OMP_NUM_THREADS=1的设置，popt版严格等价于psmp版结合OMP_NUM_THREADS=1的设置。

---

## 29. CP2K 调试版本

CP2K还存在sdbg和pdbg调试版本，分别相当于ssmp和psmp结合debug设置，仅用于开发者调试程序。
