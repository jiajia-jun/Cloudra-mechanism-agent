---
key: t23002
title: ����gnu��������cmake����ԭ��Windows��xtb
url: http://bbs.keinsci.com/thread-23002-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 11
---

# ����gnu��������cmake����ԭ��Windows��xtb — 知识卡片

## 1. Windows 下 xtb 6.4.1 编译环境准备

xtb 6.4.1 版本之后弃用了 Meson 和 Ninja 构建系统，转为使用 CMake，因此无需安装 Meson 和 Ninja。在 Windows 10 64 位 x86_64 系统上，需要准备 TDM-gcc-64bit 10.3.0、cmake-win64 3.22.1 和 Intel MKL 2022.0.0 作为编译依赖。

---

## 2. CMake 安装与配置

安装 cmake-3.22.1-windows-x86_64.msi 至 C:\cmake-3.22.1-win64-x64 目录。将 C:\cmake-3.22.1-win64-x64\bin 添加至系统环境变量 PATH 中，建议置于靠前位置以确保调用正确版本。

---

## 3. TDM-GCC 编译器安装与配置

安装 TDM-GCC-10.3.0-64bits 时需确保包含 gcc、g++、gfortran 和 openmp 组件，默认安装即可满足要求。安装目录设定为 C:\TDM-GCC-64，并将 C:\TDM-GCC-64 添加至 PATH 环境变量靠前位置；也可在 cmd 中执行 C:\TDM-GCC-64\mingwvars.bat 进行配置。需将 C:\TDM-GCC-64\bin 下的 mingw32-make.exe 复制一份并重命名为 make.exe。

---

## 4. Intel OneAPI 与 MKL 安装要求

Intel Parallel Studio XE 已停止更新，现统一使用 Intel OneAPI 工具套件。安装 Intel OneAPI 前需先安装 Microsoft Visual Studio 2019，暂不推荐使用 Visual Studio 2022，因为新版 OneAPI 可能存在兼容性问题。数学计算仅需安装 Intel oneAPI Base Toolkit（含 Intel C/C++ 编译器和 Intel MKL），若对 Fortran 和 Intel MPI 感兴趣可额外安装 Intel oneAPI HPC Toolkit。

---

## 5. Intel MKL 环境变量配置

将 C:\Program Files (x86)\Intel\oneAPI\mkl\latest\redist\intel64 和 C:\Program Files (x86)\Intel\oneAPI\mkl\latest\bin\intel64 添加至 PATH 环境变量靠前位置。需设置系统环境变量 MKLROOT 为 C:\Program Files (x86)\Intel\oneAPI\mkl\latest，设置 LIB 为 C:\Program Files (x86)\Intel\oneAPI\mkl\latest\lib\intel64。也可通过在 cmd 中执行 "C:\Program Files (x86)\Intel\oneAPI\mkl\latest\env\vars.bat" intel64 llp64 来完成配置。

---

## 6. xtb 源码获取与解压

通过 GitHub 下载 xtb-6.4.1 版本源码压缩包 xtb-6.4.1-src，下载后解压至本地目录。对于预编译版本，只需将压缩包内容解压至 C:\xtb-6.4.1 目录，并将 C:\xtb-6.4.1\bin 添加至 PATH 环境变量即可直接使用，无需手动编译。

---

## 7. xtb 编译命令步骤

在 cmd 中进入 xtb 源码解压目录，依次执行 set CC=gcc、set FC=gfortran、mkdir build 和 cd build。执行 cmake 配置命令：cmake .. -G "MinGW Makefiles" -DCMAKE_INSTALL_PREFIX=C:\xtb-6.4.1。执行 make -j 8 进行多线程编译，最后执行 make install 将程序安装至 C:\xtb-6.4.1 目录。

---

## 8. xtb 运行时环境变量配置

编译完成后，需将 C:\xtb-6.4.1\bin 添加至 PATH 环境变量，并设置用户环境变量 XTBPATH 为 C:\xtb-6.4.1\share\xtb。建议设置用户环境变量 OMP_NUM_THREADS=8,1 以控制线程数，设置 MKL_NUM_THREADS=8 指定 MKL 线程数，设置 OMP_STACKSIZE=4G 分配 4GB 内存栈空间以避免计算中断。

---

## 9. xtb 预编译版与自编译版区别

文中提供的预编译版本已将必要的动态链接库文件置于 xtb 的 bin 目录下，可直接运行。自编译版本依赖系统路径中的动态库，且可能因依赖其他 GNU 库导致“找不到库”的错误；若未将相关库路径加入 PATH，自编译的 xtb 可能无法正常运行。使用预编译版本可避免配置动态链接库路径的麻烦。

---

## 10. CMD 编码设置与目录跳转

若在 cmd 中操作时遇到中文乱码或不知道如何进入指定目录，可先执行 chcp 65001 切换编码页，再使用 cd 命令进入相应目录进行操作。

---

## 11. LAPACK 3.9.1 编译安装

下载 lapack-3.9.1 源码并解压，在 cmd 中进入解压目录。依次执行 set CC=gcc、set FC=gfortran、set CXX=g++、mkdir build 和 cd build。执行配置命令：cmake .. -G "MinGW Makefiles" -DLAPACKE=ON -DCBLAS=ON -DCMAKE_INSTALL_LIBDIR=C:\lapack-3.9.1\lib -DCMAKE_INSTALL_INCLUDEDIR=C:\lapack-3.9.1\include。最后执行 cmake --build . -j8 --target install 进行编译和安装，安装目录为 C:\lapack-3.9.1，并将 C:\lapack-3.9.1\lib 添加至 PATH 环境变量。
