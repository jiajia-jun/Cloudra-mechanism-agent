---
id: 247
title: Gromacs 5.1.1与4.6.7编译方法
domain: 软件安装与环境
topic: Gromacs_5.1.1与4.6.7编译及GPU加速安装
cards: 13
---

## 1. Gromacs编译环境与依赖要求
Gromacs 5.0及以上版本编译必须使用cmake 2.8.8及以上版本。MKL、icc不是必需的，单机并行使用OpenMP无需MPI库，跨节点运行可使用OpenMPI 1.6及以上或MPICH 1.4.1及以上。如果cmake版本低于要求，需下载源代码运行./bootstrap;make -j;make install安装。

---

## 2. Cmake版本过低时的安装步骤
如果运行cmake -version显示版本低于2.8.8，需安装CMake。解压后进入目录，依次运行./bootstrap、make -j、make install，程序将被安装到/usr/local/bin下。

---

## 3. Gromacs 5.0标准单精度版本编译流程
解压gromacs-5.0.tar.gz并进入目录，创建build目录并进入。运行cmake.. -DGMX_BUILD_OWN_FFTW=ON -DCMAKE_INSTALL_PREFIX=/sob/gromacs50进行配置。接着运行make -j进行并行编译，最后运行make install。编译过程中Gromacs会自动下载并编译FFTW3.3.3。

---

## 4. 编译旧CPU兼容性的处理
如果使用的CPU较新（如支持AVX2）而编译器版本较老，cmake步骤可能会报错提示编译器不支持AVX2指令集。此时需要在cmake命令中加上-DGMX_SIMD=AVX_256来强制使用AVX1指令集。

---

## 5. Gromacs 5.0双精度版本编译方法
在cmake配置步骤中增加参数-DGMX_DOUBLE=ON即可编译双精度版本。双精度版本不兼容GPU加速，编译出来的可执行文件默认带有_d后缀，因此可以和单精度版安装到同一目录而不会冲突。

---

## 6. Gromacs 5.0支持CUDA的GPU加速编译
需先安装nVidia的CUDA toolkit到默认路径。cmake配置命令修改为cmake.. -DGMX_GPU=ON -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda-5.5 -DGMX_BUILD_OWN_FFTW=ON -DCMAKE_INSTALL_PREFIX=/sob/gromacs50。使用高端GeForce显卡配合4核CPU可加速3倍以上。

---

## 7. 离线环境手动安装FFTW的方法
若机器无法联网导致Gromacs无法自动下载FFTW，需安装FFTW3。解压进入目录后运行./configure --prefix=/sob/fftw333 --enable-sse2 --enable-float --enable-shared，随后执行make -j和make install。

---

## 8. Gromacs调用已安装FFTW的编译方法
在编译Gromacs的cmake步骤之前，需先运行export CMAKE_PREFIX_PATH=/sob/fftw333设置路径。cmake命令中去掉-DGMX_BUILD_OWN_FFTW=ON，其它步骤保持不变。注意--enable-float代表编译单精度FFTW，若用于双精度Gromacs应去掉该选项。

---

## 9. Gromacs 5.0 MPI并行版本编译方法
若需MPI版本，可从源码安装。解压进入目录后运行./configure及make all install进行安装。在编译Gromacs时，cmake命令需加上-DGMX_MPI=on。编译出的文件带有_mpi后缀，可与单节点版本共存。

---

## 10. Gromacs程序跨机器使用的注意事项
Gromacs编译时会自动检测CPU架构并采用适当的SIMD指令集优化以达到最佳性能。因此，如果不同机器的CPU架构不同，不能直接拷贝编译好的Gromacs程序使用，否则运行会出现问题。

---

## 11. Gromacs 4.6.7标准编译流程
Gromacs 4.6.7完全使用cmake编译，需cmake 2.8及以上。解压gromacs-4.6.7.tar.gz，创建build目录并进入。运行cmake.. -DGMX_BUILD_OWN_FFTW=ON -DCMAKE_INSTALL_PREFIX=/sob/gromacs467，接着执行make -j和make install。此版本会自动下载并编译FFTW3.3.2。

---

## 12. Gromacs 4.6.7双精度与GPU版本编译
编译双精度版本需在cmake时加上-DGMX_DOUBLE=ON，生成的可执行文件带有_d后缀且不兼容GPU加速。编译GPU版本需安装CUDA toolkit，cmake命令为cmake.. -DGMX_GPU=ON -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda-5.5 -DGMX_BUILD_OWN_FFTW=ON -DCMAKE_INSTALL_PREFIX=/sob/gromacs467gpu。

---

## 13. Gromacs 4.6.7手动指定FFTW编译
手动编译FFTW3.3.2时，运行./configure --prefix=/sob/fftw332 --enable-sse2 --enable-float --enable-shared，然后make和make install。在Gromacs的cmake步骤前运行export CMAKE_PREFIX_PATH=/sob/fftw332，cmake命令去掉-DGMX_BUILD_OWN_FFTW=ON。若用于编译双精度Gromacs，需去掉--enable-float。
