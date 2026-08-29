---
key: t31999
title: molcas intel��������װ̤�Ӽ�
url: http://bbs.keinsci.com/thread-31999-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 13
---

# molcas intel��������װ̤�Ӽ� — 知识卡片

## 1. OpenMolcas 软件获取

OpenMolcas 源代码可直接从 Gitlab 下载，当前使用的版本为 v22.06-85-g4b62d07。

---

## 2. HDF5 编译安装要求

编译 HDF5-1.10.4 时必须开启 `--enable-cxx` 选项，否则后续 NEVPT2 计算无法通过。ALPS 模块检测到并行(MPI) HDF5 会发出警告，推荐使用标准版本。

---

## 3. HDF5 编译安装参数

HDF5 的编译命令需指定 Intel 编译器及优化参数，完整配置如下：
```bash
./configure --prefix=/public/software/hdf5-1.10.4 --enable-cxx --enable-fortran --enable-shared --with-pic CC=icc FC=ifort CXX=icpc CFLAGS="-fPIC -O3 -xHost -ip -fno-alias -align" FCFLAGS="-fPIC -O3 -xHost -ip -fno-alias -align" CXXFLAGS="-fPIC -O3 -xHost -ip -fno-alias -align"
```

---

## 4. HDF5 环境变量配置

HDF5 安装完成后，需将以下环境变量追加至 `~/.bashrc`：
```bash
export HDF5_DIR=/public/software/hdf5-1.10.4
export PATH=/public/software/hdf5-1.10.4/bin:$PATH
export HDF5_LIBRARIES=/public/software/hdf5-1.10.4/lib:$HDF5_LIBRARIES
export HDF5_INCLUDE_DIRS=/public/software/hdf5-1.10.4/include:$DF5_INCLUDE_DIRS
```

---

## 5. Global Arrays 编译安装参数

Global Arrays (ga-5.8.1) 的编译配置需启用 i8、sockets、CXX 及 MPI 支持，并链接 MKL 中的 ScaLAPACK 和 BLAS：
```bash
./configure MPICXX=mpiicpc MPIF77=mpiifort MPICC=mpiicc --prefix=/public/software/ga-5.8.1 --enable-i8 --with-sockets --with-blas8="-L$MKLROOT/lib/intel64 -lmkl_intel_ilp64 -lmkl_intel_thread -lmkl_core -liomp5 -lpthread -lm" --with-scalapack8="-L$MKLROOT/lib/intel64 -lmkl_scalapack_ilp64 -lmkl_intel_ilp64 -lmkl_intel_thread -lmkl_core -lmkl_blacs_intelmpi_ilp64 -liomp5 -lpthread -lm" --enable-cxx -with-mpi
```

---

## 6. Global Arrays 环境变量配置

Global Arrays 安装完成后，需将以下环境变量追加至 `~/.bashrc`：
```bash
export GAROOT=/public/software/ga-5.8.1
export PATH=/public/software/ga-5.8.1/bin:$PATH
```

---

## 7. OpenMolcas 编译环境准备

编译 OpenMolcas 前需使用 `conda activate` 切换至 python3 环境，并确保 GA 和 HDF5 的环境变量已加载。

---

## 8. OpenMolcas 基础编译命令

在 build 目录下，使用 CMake 配置并编译 OpenMolcas（Intel 编译器版本）：
```bash
cmake -DCMAKE_Fortran_COMPILER=ifort -DCMAKE_C_COMPILER=icc -DGA=ON -DLINALG=MKL -DCMAKE_INSTALL_PREFIX=/public/software/OpenMolcas_v22.06 ../OpenMolcas
make -j8
```

---

## 9. OpenMolcas 链接错误修复

编译至 98% 时若出现 `undefined reference to _gfortran_getarg_i8` 错误，需检查 `CMakeCache.txt` 中的 link FLAGS。解决方法为删除当前的 `CMakeCache.txt`，修改相关配置后退出目录并重新执行编译。

---

## 10. DMRG 和 NEVPT2 模块依赖

启用 QCMaquis 需安装 Boost 库，版本要求大于等于 1.56，当前环境可安装 boost-1.57。

---

## 11. Intel 编译器兼容性问题

NEVPT2 模块与 Intel 编译器兼容性不佳。系统自带的 GCC-4.8.5 版本过低，运行 DMRG 时存在 `regex.h` 的 bug。

---

## 12. GCC-7 环境安装步骤

为解决编译器兼容性问题，需通过 yum 安装 devtoolset-7 以使用 GCC-7：
1. 下载阿里云 yum 源：`wget -O /etc/yum.repos.d/CentOS-Base-aliyun.repo https://mirrors.aliyun.com/repo/Centos-7.repo`
2. 安装 devtoolset-7：`yum install devtoolset-7-gcc*`
3. 启用环境：`scl enable devtoolset-7 bash`

---

## 13. OpenMolcas 全功能编译命令 (GCC-7)

使用 GCC-7 编译包含 DMRG 和 NEVPT2 支持的 OpenMolcas：
```bash
cmake -DCMAKE_C_COMPILER=/opt/rh/devtoolset-7/root/usr/bin/cc -DCMAKE_CXX_COMPILER=/opt/rh/devtoolset-7/root/usr/bin/c++ -DCMAKE_CXX_COMPILER=/opt/rh/devtoolset-7/root/usr/bin/c++ -DCMAKE_C_COMPILER=/opt/rh/devtoolset-7/root/usr/bin/cc -DCMAKE_Fortran_COMPILER=/opt/rh/devtoolset-7/root/usr/bin/gfortran -DGA=ON -DLINALG=MKL -DCMAKE_INSTALL_PREFIX=/public/software/OpenMolcas_GNU -DNEVPT2=ON -DDMRG=ON -DOPENMP=ON ../OpenMolcas
make
make install
```
