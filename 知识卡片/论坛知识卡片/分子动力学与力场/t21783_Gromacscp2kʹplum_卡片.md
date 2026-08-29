---
key: t21783
title: Gromacs��cp2k����ʹ��plumed��QM/MM��ǿ����
url: http://bbs.keinsci.com/thread-21783-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2021
cards: 17
---

# Gromacs��cp2k����ʹ��plumed��QM/MM��ǿ���� — 知识卡片

## 1. GROMACS CP2K QMMM 接口与 Plumed 增强

GROMACS 2022 版本已正式发布，其中包含与 CP2K 进行 QMMM 模拟的官方接口。该接口允许结合 GROMACS 的分子动力学能力与 CP2K 的量子化学计算功能，同时支持通过 Plumed 模块进行增强采样。

---

## 2. CP2K 安装依赖工具链

编译 CP2K 8.1 需提前解压源码至指定目录，并进入 tools/toolchain 目录执行工具链安装脚本。该步骤会配置并安装 libxsmm、elpa、libxc、libint、scalapack、fftw 等必要依赖库。

---

## 3. CP2K 工具链安装命令

使用 install_cp2k_toolchain.sh 脚本时可指定多种库的来源与安装选项，其中部分库选择系统预装版本，部分选择脚本安装。参考命令如下：
./install_cp2k_toolchain.sh --with-libxsmm=install --with-elpa=install --with-libxc=install --with-libint=install --with-gsl=no --with-libvdwxc=no --with-spglib=no --with-hdf5=no --with-spfft=no --with-cosma=no --with-libvori=no --with-sirius=no --with-scalapack=install --with-openblas=system --with-fftw=install --with-openmpi=system --with-plumed=system

---

## 4. CP2K 编译配置

完成工具链安装后，需将生成的 arch 目录下文件复制至 CP2K 源码的 arch 目录，并 source 环境设置文件。为配合 GROMACS 调用，需编译生成 libcp2k 静态库。

---

## 5. CP2K 编译命令

执行 make 命令编译 CP2K 库文件以供 GROMACS 链接使用。
make ARCH=local VERSION="ssmp psmp" libcp2k

---

## 6. Plumed 安装版本与路径

Plumed 建议安装 2.7.2 版本，该版本支持 GROMACS 对应的接口功能。下载源码并解压至 /Users/formidable/src/plumed2-2.7 后进行配置与安装。

---

## 7. Plumed 安装命令

在 Plumed 源码目录下执行 configure 指定安装前缀，随后进行多线程编译与安装。
./configure --prefix=/usr/local/plumed/2.7.2
make -j24
make install

---

## 8. Plumed 模块文件配置

安装完成后，可将 Plumed 的 modulefile 复制到用户私有模块目录以便环境加载。
cp /usr/local/plumed/2.7.2/lib/plumed/modulefile ~/privatemodules/plumed/2.7.2

---

## 9. GROMACS QMMM 源码获取

GROMACS 的 QMMM 功能需使用特定的源码分支，可通过 GitLab 获取 2021.2-qmmm 分支的代码。将源码解压至 /Users/formidable/src/gromacs-2021.2-qmmm 准备编译。

---

## 10. GROMACS Plumed 补丁应用

在编译 GROMACS 之前，需要先应用 Plumed 提供的补丁以启用增强采样接口。
plumed patch -p

---

## 11. GROMACS CP2K 接口 CMake 配置

GROMACS 编译需开启双精度、关闭 API 构建选项，并指定 CP2K 的库文件路径及依赖库链接参数。CMake 命令如下：
cmake .. -DBUILD_SHARED_LIBS=OFF -DGMXAPI=OFF -DGMX_INSTALL_NBLIB_API=OFF -DGMX_DOUBLE=ON -DGMX_FFT_LIBRARY=fftw3 -DGMX_CP2K=ON -DCP2K_DIR="/Users/formidable/src/cp2k-8.1/lib/local/psmp" -DCP2K_LIBS="-Wl,--enable-new-dtags -pthread -L'/Users/formidable/src/cp2k-8.1/tools/toolchain/install/fftw-3.3.8/lib' -L'/Users/formidable/src/cp2k-8.1/tools/toolchain/install/libint-v2.6.0-cp2k-lmax-5/lib' -L'/Users/formidable/src/cp2k-8.1/tools/toolchain/install/libxc-4.3.4/lib' -L'/Users/formidable/src/cp2k-8.1/tools/toolchain/install/libxsmm-1.16.1/lib' -L'/Users/formidable/src/cp2k-8.1/tools/toolchain/install/scalapack-2.1.0/lib' -L'/Users/formidable/src/cp2k-8.1/tools/toolchain/install/elpa-2020.05.001/lib' -lelpa_openmp -lscalapack -lxsmmf -lxsmm -ldl -lpthread -lxcf03 -lxc -lint2 -lfftw3_mpi -lfftw3 -lfftw3_omp -lmpi -lopenblas -lstdc++" -DGMX_MPI=on -DCMAKE_INSTALL_PREFIX=/usr/local/gromacs/2021.2_QMMM

---

## 12. GROMACS 编译安装

执行 CMake 配置后，使用 make 命令进行多线程编译并安装至指定前缀目录。
make -j24
make install

---

## 13. QM 原子组定义

使用 gmx make_ndx 工具创建量子力学区域的索引组，通常命名为 QMatoms。该索引组将在 MDP 文件中用于指定哪些原子进行 QM 计算。

---

## 14. QMMM MDP 参数设置

在 GROMACS 的 MDP 文件中需设置激活 QMMM 并指定 QM 区域的参数，包括电荷与多重度。目前支持的基组与泛函组合包括 PBE/DZVP-MOLOPT 和 BLYP/DZVP-MOLOPT。

---

## 15. QMMM MDP 配置示例

激活 QMMM 并使用 PBE 泛函计算 QMatoms 组的参数配置示例如下：
; CP2K QMMM parameters
qmmm-active = true
qmmm-qmgroup = QMatoms
qmmm-qmmethod = PBE
qmmm-qmcharge = 0
qmmm-qmmultiplicity = 1

---

## 16. 自定义 CP2K 输入文件

若默认生成的 CP2K 输入参数不符合需求，可在 MDP 文件中将 qmmm-qmmethod 设置为 INPUT，并通过 qmmm-qminputfile 指定自定义的 cp2k.inp 文件路径。

---

## 17. 自定义 QMMM MDP 配置示例

使用外部自定义 CP2K 输入文件的 MDP 配置示例如下：
; CP2K QMMM parameters
qmmm-active = true
qmmm-qmgroup = QMatoms
qmmm-qmmethod = INPUT
qmmm-qminputfile = cp2k.inp
