---
key: b458
title: GROMACS的原生Windows版的编译和安装方法
url: http://sobereva.com/458
domain: 软件安装与环境
source: blog
year: 2019
cards: 11
---

# GROMACS的原生Windows版的编译和安装方法 — 知识卡片

## 1. Windows下运行GROMACS的方式对比

在Windows下运行GROMACS主要有四种方式：使用VMware安装Linux虚拟机、在Cygwin下编译、使用Win10的Linux子系统（WSL）以及编译原生Windows版。前三种方式虽然在原理上会使计算性能降低约10~15%，但主要的共同缺点是不能支持GPU加速（WSL2除外）。原生Windows版GROMACS不仅不需要额外运行环境，还能支持GPU加速，是Windows下运行GROMACS的完美方式。

---

## 2. GROMACS可用的FFT库选择

GROMACS需要利用FFT（快速傅立叶变换）库，主要有三种选择：FFTW库、MKL库和fftpack库。FFTW库是最佳选择，效率高；MKL库效率与FFTW差不多但安装较麻烦且占用硬盘空间；fftpack库是GROMACS自带的，使用最方便，但实测效率比基于FFTW库低百分之十几。

---

## 3. 编译原生Windows版GROMACS的Visual Studio环境要求

编译原生Windows版GROMACS需要安装Visual Studio，版本示例为Visual Studio 2019 Community（免费）。安装时必须选择“使用C++的桌面开发”工作负载，并确保在“安装详细信息”中选中“用于CMake的Visual C++工具”。编译环境需通过开始菜单中的“Developer PowerShell for VS 2019”进入。

---

## 4. 基于fftpack的纯CPU版GROMACS编译命令

编译基于fftpack库的纯CPU版GROMACS，需在Developer PowerShell中依次执行命令创建build目录并运行cmake。编译命令包含指定安装路径、FFT库类型及生成器，随后执行构建安装。默认情况下，编译出的程序会根据当前CPU支持的最高指令集进行优化，因此在不同指令集的CPU间移植可能会导致运行崩溃。

---

## 5. CMake编译参数与配置说明

cmake的-G选项用于设置Generator，指定编译环境，如“Visual Studio 16 2019”代表VS2017的64位平台。Visual Studio自带cmake，也可使用官网独立版本，但命令行操作比图形界面（cmake-gui）更省事。构建时使用--target INSTALL会将编译好的程序安装到CMAKE_INSTALL_PREFIX指定的目录，--config Release则用于启用发布模式的代码优化。

---

## 6. 基于FFTW的纯CPU版GROMACS编译步骤

编译基于FFTW的版本需要先下载并编译FFTW库。在FFTW源码目录运行cmake命令指定安装路径、开启SSE2/AVX支持及单精度浮点，将其安装到指定目录（如C:\fftw338）。随后在GROMACS源码目录运行cmake，指定FFTW库路径进行编译。编译完成后需手动将C:\fftw338\bin下的fftw3f.dll拷贝至GROMACS安装目录的bin文件夹下。

---

## 7. 支持CUDA加速的GROMACS编译方法

编译支持CUDA加速的版本需先安装CUDA Toolkit，并按上一节方法编译好FFTW库。cmake命令中需增加-DGMX_GPU=ON参数，并指定CUDA工具包根目录（如-DCUDA_TOOLKIT_ROOT_DIR=D:/CUDA_toolkit）。编译完成后，同样需要将fftw3f.dll拷贝至安装bin目录。若目标机器未安装CUDA Toolkit，还需将cufft64_10.dll等库文件一并拷贝。

---

## 8. CUDA版GROMACS的运行环境要求

运行CUDA版GROMACS需要机子具备支持CUDA加速的GPU，且显卡驱动版本需满足当前CUDA Toolkit的最低要求。若GPU不满足要求或驱动过旧，程序将自动退化为纯CPU计算。各版本CUDA Toolkit所需的最低驱动版本号可在NVIDIA官方文档中查询。对于GPU加速场景，使用fftpack库与fftw库对计算耗时影响很小。

---

## 9. 预编译Windows版GROMACS的安装与环境变量配置

使用预编译的Windows版GROMACS需将解压后的bin目录路径添加到系统Path环境变量中。在Windows 7中，可通过“控制面板-系统-高级系统设置-环境变量”进行编辑，在Path变量值末尾添加分号和路径。配置完成后，在命令行输入gmx命令应出现提示信息。若缺少Visual C++ Redistributable，需从微软官网下载安装。

---

## 10. 预编译CUDA GPU加速版的使用注意事项

提供的预编译CUDA GPU加速版不需要在本地安装CUDA Toolkit，只需确保nVidia显卡驱动版本足够新即可使用。如果驱动过旧无法运行，应前往NVIDIA官网下载并安装最新驱动。GROMACS是命令行程序，不能通过双击gmx.exe图标运行。若要在Windows下顺利使用GROMACS，用户需掌握基本的命令行操作，如dir和cd命令。

---

## 11. Windows版与Linux版GROMACS的计算性能对比

在双路E5 2696v3（36核）机子上对三万原子蛋白质+水盒体系的测试表明，Windows下纯CPU版的GROMACS计算速度约为Linux下纯CPU版的60%。这主要归因于微软编译器与gcc编译器的差异。因此，如果仅使用CPU进行计算，建议优先使用Linux系统。
