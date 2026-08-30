---
key: t37412
title: ABACUS-3.2�İ�װ����
url: http://bbs.keinsci.com/thread-37412-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 26
---

# ABACUS-3.2�İ�װ���� — 知识卡片

## 1. ABACUS 编译环境概述

ABACUS (AB initio Calculation of Atomic Structure) 是一款密度泛函理论计算软件，支持使用 cp2k-toolchain 工具链进行依赖库的安装与编译。目前主流的编译环境分为基于 Intel oneAPI 的 Intel-u 环境和基于 OpenMPI+OpenBLAS 的 GNU 环境。

---

## 2. 编译环境选择与性能对比

在 Intel 架构服务器上，Intel oneAPI 编译的 ABACUS 运行效率通常优于 GNU 版本约 10%，且对 MPI+OMP 混合并行支持较好。在 AMD 架构服务器上，Intel oneAPI 版本运行效率优于 GNU 版本约 50%；GNU 环境下编译的 ABACUS 稳定性较高，速度较慢。

---

## 3. DeePKS 与 DeePMD 支持的编译要求

若需支持 DeePKS 功能，编译时必须链接 MKL 库。若需支持 DeePMD 功能，需预先安装 DeePMD-python，且 GCC 版本需大于等于 11.1 以支持 libstdc++.so.6.29。

---

## 4. cp2k-toolchain 自定义安装路径

使用 cp2k-toolchain 安装依赖库时，可通过修改相关脚本中的 `pkg_install_dir` 变量来自定义安装路径。默认安装路径通常位于 toolchain 目录下，修改时应同步更新 install_lock_file 路径。

---

## 5. CMake 安装配置

CMake 版本需为 3.25.1。在 cp2k-toolchain 脚本 `install_cmake.sh` 中，可针对不同架构（如 x86_64 或 arm64）指定对应的架构类型和 sha256 校验值，并将安装目录重定向至指定路径。

---

## 6. OpenMPI 安装配置

推荐使用 OpenMPI 4.1.4 版本。在 cp2k-toolchain 脚本 `install_openmpi.sh` 中，需修改 `pkg_install_dir` 变量以设定安装目录，也可独立进行源码安装。

---

## 7. OpenBLAS 安装配置

推荐使用 OpenBLAS 0.3.21 版本。在 cp2k-toolchain 脚本 `install_openblas.sh` 中，需修改 `pkg_install_dir` 变量将库安装至指定目录，如 `/data/libraries/openblas/`。

---

## 8. FFTW3 双版本安装

ABACUS 3.2 需要同时安装 FFTW3 的 float（单精度）和 double（双精度）版本。需分别运行 configure 和 make 命令，float 版本需添加 `--enable-float` 选项，两个版本的编译参数均需包含 `--enable-openmp --enable-mpi --enable-shared --enable-static --enable-avx2 --enable-avx --enable-threads --enable-fma`（double 版本不含 float 相关选项）。

---

## 9. LibXC 安装配置 (GNU 环境)

LibXC 推荐使用 6.0.0 版本。在 GNU 环境下可使用 CMake 编译，需指定编译器为 gcc 和 gfortran，并开启 `-DBUILD_SHARED_LIBS=YES` 和 `-DENABLE_FORTRAN=ON` 等选项。

---

## 10. LibXC 安装配置 (Toolchain)

通过 cp2k-toolchain 安装 LibXC 时，需在 `install_openmpi.sh` (实际为 install_libxc.sh 脚本逻辑) 中去掉 `--disable-lxc` 选项，并添加 `--enable-shared` 以确保生成共享库供 ABACUS 识别。

---

## 11. ScaLAPACK 安装配置

通过 cp2k-toolchain 安装 ScaLAPACK 时，需修改脚本中的 CMake 选项，将 `-DBUILD_SHARED_LIBS` 设置为 `YES`（默认为 NO），并指定正确的安装前缀和库目录。

---

## 12. ELPA 版本兼容性问题

ABACUS 编译时对 ELPA 版本有特定要求，目前需使用 elpa-2021.11.002 版本而非较新的 2022.11.001，因后者存在接口变更或兼容性问题。需手动从 CP2K 官网下载指定版本的源码包。

---

## 13. ELPA 安装与目录软链接

安装 ELPA 时，需在 configure 脚本中设置 `--enable-shared=yes`。安装完成后，为方便 ABACUS 识别头文件，需在 elpa/include 目录下创建软链接，命令为 `ln -s ./elpa_openmp-2021.11.002 ./elpa`。

---

## 14. cp2k-toolchain 综合安装脚本 (GNU)

在 GNU 环境下，可使用 toolchain 脚本批量安装 CMake、OpenMPI、OpenBLAS、ScaLAPACK、ELPA、Libint 和 Libxc。FFTW 和 Plumed 建议使用系统已安装版本（--with-fftw=system），其余库选择安装（install）。

---

## 15. CEREAL 库处理

CEREAL 是一个仅含头文件的库，只需下载源码包解压即可。在 ABACUS 编译配置中，通过 `-DCEREAL_INCLUDE_DIR` 指定其 include 目录路径。

---

## 16. ABACUS 编译配置 (GNU 环境)

在 GNU 环境下编译 ABACUS 3.2.0 时，需设置 CXX=mpicxx，并通过 CMake 指定 LAPACK、SCALAPACK、ELPA、FFTW3、LibXC 等库的路径。核心开启选项包括 `-DENABLE_LCAO=ON`、`-DENABLE_LIBXC=ON`、`-DUSE_OPENMP=ON` 和 `-DUSE_ELPA=ON`。

---

## 17. ABACUS 内存泄漏检测选项

ABACUS 当前版本可能存在内存泄漏问题，编译时可开启 `-DENABLE_ASAN=ON` 选项以辅助调试，但在生产环境或追求计算速度时建议关闭此选项。

---

## 18. cp2k-toolchain 综合安装脚本

在 oneAPI 环境下，Libint 通常随 CP2K 安装或使用系统版本，toolchain 安装 ABACUS 依赖时不强制要求 Libint。配置脚本中需设置 `--with-intel=system`，关闭 GCC 相关选项，并设置 MKL、MPI 和编译器为系统版本。

---

## 19. LibXC 编译

LibXC 在 oneAPI 环境下需使用 Intel 编译器（icc/ifort/icpc）进行 CMake 编译，安装路径需独立命名以区分 GNU 版本，并开启共享库支持。

---

## 20. ABACUS 编译配置

在 oneAPI 环境下编译 ABACUS 时，需设置 CC=icc, CXX=icpc, F90=ifort，并加载 mkl、mpi、compiler 等模块。CMake 配置中需指定 `-DMKLROOT`，并确保 ELPA 和 LibXC 使用对应 oneAPI 版本的库路径。

---

## 21. ABACUS 编译性能总结

实际测试表明，在 AMD 架构服务器上使用 oneAPI 编译的 ABACUS 运行效果显著优于 OpenBLAS 版本。Intel oneAPI 环境对 ABACUS 的支持较为完善，推荐在 Intel 硬件上优先使用。

---

## 22. ABACUS GNU工具链下LibTorch与MKL的链接冲突

在GNU环境下使用OpenBLAS-OpenMPI编译ABACUS时，LibTorch依赖的Intel MKL库与当前环境不匹配会导致链接错误。报错信息通常为`cannot find -lmkl_intel_ilp64`、`cannot find -lmkl_intel_thread`或`cannot find -lmkl_core`，这是因为LibTorch自动寻找依赖的Intel MKL，而OpenBLAS环境未提供这些库。解决方法是在CMake配置之后、编译（build）阶段之前加载MKL环境模块，或者参考提供的Dockerfile重新构建GNU版本。

---

## 23. ABACUS DeepKS功能的GNU编译配置

编译带有DeepKS功能的ABACUS需要指定包含库和路径，其中LibTorch路径需导出至`CMAKE_PREFIX_PATH`。配置命令示例如下：设置`CXX=mpicxx`，通过`cmake -B build`指定安装前缀及各类库目录（如LAPACK、SCALAPACK、ELPA、FFTW3、CEREAL、Libxc、libnpy、LibTorch），并开启`-DENABLE_DEEPKS=1`、`-DENABLE_LCAO=ON`、`-DENABLE_LIBXC=ON`等选项。在执行`cmake --build`前需加载mkl模块以满足LibTorch的链接需求。

---

## 24. ABACUS DeepKS功能的Intel OneAPI编译配置

使用Intel OneAPI工具链编译支持DeepKS的ABACUS较为直接，需加载mkl、icc、mpi、compiler、elpa、libnpy、libxc等模块。配置时设置`CC=icc`、`CXX=icpc`、`F90=ifort`、`F77=ifort`，并在CMake命令中指定`-DMKLROOT=$MKLROOT`及`-DTorch_DIR`和`-Dlibnpy_INCLUDE_DIR`。若ELPA包含目录未找到，可能需要将`$ELPA/include/elpa-****/elpa`软链接至`$ELPA/include/elpa`。

---

## 25. ABACUS DeepMD功能的GNU编译环境要求

在GNU环境下编译支持DeepMD的ABACUS，GCC版本需为11.3或更高，以确保支持GLIBCXX-3.4.29。需加载cmake、openmpi、openblas、fftw、scalapack、libxc、libnpy等模块，并设置`CXX=mpicxx`。CMake配置中需额外添加`-DDeePMD_DIR=$DEEPMD`和`-DTensorFlow_DIR=$DEEPMD`，且同样需要在配置后加载mkl模块并执行编译安装。

---

## 26. ABACUS DeepMD功能的OneAPI编译警告

使用OneAPI工具链编译带有DeepMD支持的ABACUS时，CMake配置阶段可能会生成运行时库搜索路径冲突的警告。警告内容指出`libgomp.so.1`在系统GCC目录下可能被Conda DeepMD环境下的同名库隐藏，这可能导致部分库无法正确找到。尽管存在该Warning，但这并不一定阻止DeePMD支持功能的成功编译。
