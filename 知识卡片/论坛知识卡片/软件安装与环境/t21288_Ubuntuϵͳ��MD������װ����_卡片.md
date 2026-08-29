---
key: t21288
title: Ubuntuϵͳ��MD������װ����
url: http://bbs.keinsci.com/thread-21288-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 12
---

# Ubuntuϵͳ��MD������װ���� — 知识卡片

## 1. Ubuntu 20.04 系统安装准备与硬件要求

Ubuntu 20.04 适用于大多数计算化学软件环境。制作启动盘需要 8G 以上 U 盘和 UltraISO 软件，硬盘需预留至少 200G 可用空间。若移动硬盘存在无法删除的 EFI 分区，需使用 diskpart 命令将其 ID 设置为 ebd0a0a2-b9e5-4433-87c0-68b6b72699c7 以转换为普通数据分区。
- U 盘制作通过 UltraISO 写入硬盘映像，写入方式默认为 USB-HDD+。
- 系统下载地址为 https://ubuntu.com/download/desktop。

---

## 2. Ubuntu 磁盘分区方案

在安装类型中选择 "Something else" 进行手动分区，需预留 200G 空间。将 Boot 引导加载程序安装位置设置为 /boot 所在分区，可确保 Windows 系统能正常启动并引导 Ubuntu。
- 根目录 / 分配 50G，主分区，Ext4 文件系统。
- Swap 交换空间分配 8G。
- /boot 分区分配 10G，逻辑分区，Ext4 文件系统。
- /home 分区使用剩余全部空间，逻辑分区，Ext4 文件系统。

---

## 3. CMake 安装

CMake 是编译 GROMACS 等软件的必要工具。在 Ubuntu 终端中使用 apt-get 命令可直接安装。
- 安装命令：`sudo apt-get install cmake`

---

## 4. FFTW 3.3.9 编译安装

FFTW (Fastest Fourier Transform in the West) 需开启相关优化选项进行编译。下载版本为 3.3.9，安装路径需自定义。
- 配置命令：`./configure --prefix=/home/zehua/software/fftw339 --enable-sse2 --enable-avx --enable-avx2 --enable-float --enable-shared`
- 编译安装命令：`make -j install`

---

## 5. OpenMPI 4.1.0 编译安装

安装 OpenMPI 前需预装 gcc、g++ 和 build-essential。下载 OpenMPI 4.1.0 版本源码进行编译。
- 预安装依赖命令：`sudo apt-get install gcc / g++ / build-essential`
- 配置命令：`./configure -prefix=/home/zehua/software/openmpi`
- 编译安装命令：`make all install -j`
- 环境变量设置：在 .bashrc 末尾添加 `export PATH=$PATH:/home/zehua/software/openmpi/bin` 和 `export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/home/zehua/software/openmpi/lib`。
- 验证命令：`mpicc -o hello_c hello_c.c` 和 `mpirun -np 6 ./hello_c`

---

## 6. GROMACS 2018.8 MPI 版本编译安装

GROMACS 推荐安装 MPI 版本以利用多核并行计算。编译前需设置 CMAKE_PREFIX_PATH 指向 FFTW 安装目录。
- 配置命令：`export CMAKE_PREFIX_PATH=/home/zehua/software/fftw339`
- CMake 命令：`cmake .. -DGMX_MPI=ON -DCMAKE_INSTALL_PREFIX=/home/zehua/gmx2018.8`
- 编译安装命令：`make install -j`
- 环境变量设置：在 .bashrc 末尾添加 `source /home/zehua/software/gmx2018.8/bin/GMXRC`。
- 验证方法：终端输入 `gmx_mpi` 并按 Tab 键，若补全显示相关命令则表示安装成功。

---

## 7. VMD 1.9.4 安装

VMD 安装需下载 LINUX_64 OpenGL 版本。解压后需执行 configure 和 make install 命令完成编译安装。
- 配置命令：`sudo ./configure LINUXAMD64` 和 `sudo ./configure`
- 编译安装命令：`cd src` 后执行 `sudo make install`
- 验证方法：终端输入 `vmd` 启动程序。

---

## 8. Packmol 安装与配置

Packmol 用于分子堆积建模，直接编译源码即可。若直接 make 失败，则需先运行 configure。
- 编译命令：`make` 或 `./configure` 后 `make`
- 环境变量设置：在 .bashrc 中添加 `export PATH=$PATH:/home/zehua/software/packmol`。
- 验证方法：新终端输入 `packmol` 查看版本提示信息。

---

## 9. AmberTools 20 预安装依赖

在 Ubuntu 19.04 或 20.04 系统上安装 AmberTools 20 需预装一系列编译和图形库依赖。
- 安装命令：`sudo apt -y install tcsh \ make \ gcc \ gfortran \ flex \ bison \ patch \ bc \ xorg-dev \ libbz2-dev \ wget`

---

## 10. AmberTools 20 编译安装

AmberTools 20 使用 CMake 构建系统。进入源码 build 目录执行脚本进行编译安装。
- 编译命令：`cd amber20_src/build` 后执行 `./run_cmake`，接着执行 `make install`。
- 环境变量设置：在 .bashrc 末尾添加 `source /home/zehua/software/amber20/amber.sh`。
- 验证方法：新终端输入 `antechamber` 查看版本信息。

---

## 11. Moltemplate 安装与 Python 环境配置

Moltemplate 依赖于 Python 3，需通过 pip3 安装。若系统仅识别 python3 命令，需修改 moltemplate.sh 脚本以适配环境。
- Python 环境安装：`sudo apt install python3-pip`
- Moltemplate 安装：在解压目录下执行 `pip3 install . --user`。
- 环境变量设置：在 .bashrc 中添加 moltemplate 及 scripts 目录路径。
- 脚本修复：打开 moltemplate.sh，将检测部分的 `python` 替换为 `python3`。

---

## 12. VASP 5.4.4 编译准备与环境模块

VASP 编译需准备 Intel 编译器环境。复制对应的 makefile.include 文件并加载正确的环境模块是编译成功的前提。
- 配置文件复制：`cp arch/makefile.include.linux_intel_cuda ./makefile.include`
- 环境模块加载：`module load intel/parallelstudio/2019` (替代旧版本 intel 18.0.2-fast)。
- 编译命令：`make all`
