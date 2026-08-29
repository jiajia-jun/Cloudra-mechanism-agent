---
id: 29
title: Gromacs 4.0.3、4.5.5版安装方法
domain: 软件安装与环境
topic: Gromacs_4.0.3_与_4.5.5_版本编译安装
cards: 17
---

## 1. Gromacs 4.0.3 编译器及环境变量配置
安装Gromacs 4.0.3前需指定编译器及优化选项，适用于gcc 4.1.2和core2架构；export CC=gcc，export CXX=g++，export CFLAGS="-O3 -msse -msse2 -msse3 -mssse3 -march=core2"，export CXXFLAGS="-O3 -msse -msse2 -msse3 -mssse3 -march=core2"，export FFLAGS="-O3 -axT"。

---

## 2. MPICH2 1.0.7 安装与配置
复制mpich2-1.0.7.tar.gz到/sob，解压后进入目录运行./configure、make、make install；运行touch /etc/mpd.conf和chmod 700 /etc/mpd.conf；将secretword=<secretword>加入mpd.conf。

---

## 3. FFTW 3.1.2 安装配置
解压fftw3.1.2压缩包到/sob下，进入fftw-3.1.2目录；运行./configure --enable-float --with-gcc-arch=core2；运行make和make install；默认安装在/usr/local/include(lib)下。

---

## 4. Gromacs 4.0.3 基础编译安装
解压gromacs-4.0压缩包到/sob下，进入gromacs-4.0目录；运行./configure --prefix=/sob/gromacs --enable-mpi -enable-fortran；运行make和make install；在/root/.bashrc中添加PATH=$PATH:/sob/gromacs/bin和MANPATH=$MANPATH:/sob/gromacs/share/man。

---

## 5. Gromacs 4.0.3 MOPAC7 QMMM支持编译
下载dcart.f和mopac7.tar.gz；解压mopac7.tar.gz并用dcart.f替换原文件，删除mopac.f、moldat.f、deriv.f；运行ifort -O2 -c *.f、ar rcv libmopac.a *.o、ranlib libmopac.a；将libmopac.a放到/lib下；设置export CPPFLAGS=-DUSE_MOPAC和export LIBS=-lmopac；运行./configure --prefix=/sob/gromacs --enable-mpi -enable-fortran --with-qmmm-mopac；运行make和make install。

---

## 6. Gromacs 4.0.3 MKL库编译方法
使用MKL需先修改./configure文件，将两处LIBS="-lmkl $LIBS"改为LIBS="-lmkl_intel_lp64 -lmkl_sequential -lmkl_core $LIBS"；运行./configure --prefix=/sob/gromacs4mkl --enable-mpi -enable-fortran --with-fft=mkl CPPFLAGS=-I/opt/intel/mkl/10.0.4.023/include LDFLAGS=-L/opt/intel/mkl/10.0.4.023/lib/em64t。

---

## 7. Gromacs 4.0.3 MKL库编译注意事项
MKL编译下串行版本比fftw有提升，但并行版本相对fftw没有提升；32bit平台需将-lmkl_intel_lp64改为lmkl_intel，并将.../lib/em64t改为.../lib/32。

---

## 8. Gromacs 共享库编译选项
硬盘空间紧张时可在./configure时加入--enable-shared；使用共享库生成的bin非常小(gmx4.0中只有2.3MB，远小于静态库的172.65MB)；需添加环境变量LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/gromacs/lib；使用静态库或动态库对运行速度基本没有影响。

---

## 9. Fortran内核编译性能影响
Gromacs内核有C语言和Fortran两套版本，默认是C语言编译；使用-enable-fortran选项对gmx3.3.x性能提升不大，但对gmx 4.0.x性能提升明显；./configure时可加F77=xxx指定Fortran编译器，建议用ifort，用gfortran可能会报错。

---

## 10. Gromacs 编译器选择经验
没必要用icc，性能相比用gcc不会有丝毫提升。

---

## 11. Gromacs 重新编译步骤
如果已经make过了，之后想./configure接新的选项重新编译，应当先执行make distclean。

---

## 12. Gromacs 程序名后缀区分
--program-suffix=[suffix]可给程序名加后缀以区分单双精度或串并行版本；先不加--enable-mpi编译一遍，make distclean，再加--enable-mpi和--program-suffix=_mpi编译一遍；没有必要单独编译串行版本，单CPU使用可当成-np 1。

---

## 13. Gromacs 双精度编译选项
--disable-float或--enable-double可以编译成双精度版本(默认单精度)；双精度版本速度约为单精度60%；常规分子动力学单精度足够，简正振动分析等除外。

---

## 14. Gromacs 4.0.x 版本已知问题修复
gmx4.0.0开-enable-fortran编译出错需把src/gmxlib/libxdrf.c的第1156行#define XDR_INT_SIZE 4挪到第68行；编译得到的g_spatial和g_cluster完全一样需把src/tools/g_spatial.c里面的gmx_cluster改成gmx_spatial(gmx4.0.3已修正)。

---

## 15. Gromacs 4.5.5 MPICH2 安装
在mpich2 1.4.1文件夹中运行./configure、make、make install；安装完成后可删除mpich2 1.4.1文件夹。

---

## 16. Gromacs 4.5.5 FFTW 3.3 安装配置
在fftw-3.3目录下运行./configure --enable-threads --enable-single --enable-sse2 --enable-avx F77=ifort --prefix=/sob/fftw3.3；运行make -j 4和make install；安装完成后可删除fftw-3.3文件夹。

---

## 18. Gromacs 4.5.5 MPI并行与Fortran内核
如果使用MPI并行化，需在configure命令中添加--enable-mpi；如果想用Fortran编译内核，先export F77=ifort并在./configure中加上--enable-fortran；使用Fortran内核性能不会有丝毫提升甚至略微下降；threads并行和MPI并行在单机上效率差不多。
