---
id: 458
title: GROMACS的原生Windows版的编译和安装方法（支持GPU加速）
url: http://sobereva.com/458
domain: 软件安装与环境
topic: GROMACS原生Windows版编译与GPU加速
cards: 17
---

# GROMACS原生Windows版编译与GPU加速 — 知识卡片

## 1. 原生Windows版GROMACS编译适用范围

本文以2019.1版为例说明编译过程。纯CPU版编译方法经测试适用于GROMACS 2018、2019各版本，编译CUDA GPU加速版的方法经测试适用于GROMACS 2019.1及之后的2019.x版、2020.x版。本文仅涉及编译单精度版、单节点并行、64bit版本的情况。

---

## 2. Windows下使用GROMACS的三种非原生方式

Windows下使用GROMACS的非原生方式包括使用VMware装Linux虚拟机、在Cygwin下编译、以及使用Win10的Linux子系统（WSL）。这三种方法都会使计算性能打约10~15%的折扣，且共同的严重缺点是不能支持GPU加速（WSL2除外）。

---

## 3. 原生Windows版GROMACS的优势

直接编译原生的Windows版GROMACS不需要装额外运行环境，不会对CPU性能打折扣，而且可以像Linux下一样使用GPU加速。编译出的程序可以拿到任何其它Windows机子上直接用。

---

## 4. GROMACS编译所需FFT库的选择

GROMACS需要利用FFT库，有三种选择：FFTW库是最佳选择，效率高；MKL库效率和FFTW差不多，但需要额外安装且占不少硬盘；fftpack库是GROMACS自带的，效率比基于FFTW库低百分之十几，但图省事可以用。

---

## 5. Visual Studio的安装要求

编译原生Windows版GROMACS需要安装Visual Studio，最低可使用免费的community版。安装时必须选择“使用C++的桌面开发”，并确认“安装详细信息”中“用于CMake的Visual C++工具”是已选中的状态。

---

## 6. 基于fftpack的纯CPU版编译步骤

将gromacs-2019.1.tar.gz源代码包解压到如C:\gromacs-2019.1。在Developer PowerShell for VS 2019中依次输入命令：
cd C:\gromacs-2019.1
mkdir build
cd build
cmake .. -DCMAKE_INSTALL_PREFIX=C:/gmx2019.1 -DGMX_FFT_LIBRARY=fftpack -G "Visual Studio 16 2019"
cmake --build . --target INSTALL --config Release

---

## 7. 编译产物的CPU指令集兼容性

编译出的GROMACS默认基于当前机子CPU支持的最高指令集。如果编译机CPU支持AVX2指令集，编译出的程序拿到只支持到AVX指令集的CPU上运行时，mdrun会崩溃。

---

## 8. 基于fftw的纯CPU版之FFTW库编译

下载FFTW 3.3.8库并解压，在Developer PowerShell for VS 2019中进入解压目录，运行：
cmake . -DCMAKE_INSTALL_PREFIX=C:\fftw338 -DENABLE_SSE2=ON -DENABLE_AVX=ON -DENABLE_FLOAT=ON -DBUILD_SHARED_LIBS=ON -G "Visual Studio 16 2019"
cmake --build . --target INSTALL --config Release
若CPU支持AVX2指令集，建议将-DENABLE_AVX=ON改为-DENABLE_AVX2=ON。

---

## 9. 基于fftw的纯CPU版之GROMACS编译步骤

将FFTW库编译并安装到C:\fftw338后，在Developer PowerShell for VS 2019中依次输入：
cd C:\gromacs-2019.1
mkdir build
cd build
cmake .. -DCMAKE_INSTALL_PREFIX=C:/gmx2019.1 -DGMX_FFT_LIBRARY=fftw3 -DCMAKE_PREFIX_PATH=C:/fftw338 -G "Visual Studio 16 2019"
cmake --build . --target INSTALL --config Release
编译完成后，需手动将C:\fftw338\bin里的fftw3f.dll拷到C:\gmx2019.1\bin目录下。

---

## 10. CUDA toolkit的安装与目录设置

下载CUDA toolkit时只需选择安装CUDA分类里的Development、Runtime和Visual Studio Integration。编译CUDA版GROMACS的机子不需要非得有可实现CUDA加速的GPU，只要装了CUDA toolkit即可编译。文中假定CUDA toolkit安装到了D:\CUDA_toolkit目录。

---

## 11. 基于fftw且支持CUDA加速版本的编译步骤

安装好CUDA toolkit并编译FFTW库后，在Developer PowerShell for VS 2019中运行：
cd C:\gromacs-2019.1
mkdir build
cd build
cmake .. -DCMAKE_INSTALL_PREFIX=C:/gmx2019.1_GPU -DGMX_FFT_LIBRARY=fftw3 -DCMAKE_PREFIX_PATH=C:/fftw338 -G "Visual Studio 16 2019" -DGMX_GPU=ON -DCUDA_TOOLKIT_ROOT_DIR=D:/CUDA_toolkit
cmake --build . --target INSTALL --config Release
编译后需将fftw3f.dll拷到C:\gmx2019.1_GPU\bin目录下。

---

## 12. CUDA版GROMACS的DLL依赖与迁移

如果编译出的GROMACS要拿到其它没有装CUDA toolkit或装了老版本CUDA toolkit的机子上用，应当先把D:\CUDA_toolkit\bin\cufft64_10.dll（数字视CUDA toolkit版本而定）也拷到C:\gmx2019.1_GPU\bin目录下，然后再拷贝到其它机子上使用。

---

## 13. CUDA版GROMACS的运行条件

如果机子里有支持CUDA加速的GPU且驱动版本号足够新，CUDA版GROMACS会自动识别并利用GPU运算。如果GPU不满足要求或驱动太老，程序会纯粹用CPU运行。GPU驱动最低版本号要求可在NVIDIA官网的CUDA toolkit release notes页面查询。

---

## 14. 预编译版GROMACS的获取与版本信息

博主提供了预编译的GROMACS Windows 64bit版，包括2018.8 CPU版（AVX）、2019.6 CUDA GPU加速版（AVX）、2020.3 CUDA GPU加速版（AVX）和2020.6 CUDA GPU加速版（AVX2，需驱动>=471.11版）。

---

## 15. 预编译版GROMACS的环境变量配置

使用预编译版前必须将bin目录加入Path环境变量。在Win7下，进入“控制面板”-“系统”-“高级系统设置”-“环境变量”，编辑用户变量中的Path，在变量值最后加上分号和bin目录路径，如;C:\gmx2019.6\bin\。

---

## 16. 预编译版GROMACS的运行库依赖

如果机子里没有装Visual Studio或装了比2019老的版本，需下载并安装Visual C++ Redistributable (VC_redist.x64.exe) 以提供必备的运行环境。对于CUDA GPU加速版，使用者不需要安装CUDA toolkit，只需确保nVidia显卡驱动足够新。

---

## 17. Windows纯CPU版与Linux版的性能对比

经测试，在2*E5 2696v3（36核）机子上运行三万多原子体系，Windows下纯CPU版的计算速度只有Linux版的60%，估计是微软编译器不如gcc所致。如果只用CPU跑计算，建议使用Linux系统。
