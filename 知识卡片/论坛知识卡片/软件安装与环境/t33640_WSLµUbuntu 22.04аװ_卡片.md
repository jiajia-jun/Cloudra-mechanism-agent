---
key: t33640
title: ��WSL�µ�Ubuntu 22.04�а�װVASP 6.3.2��CP2K v2022.2
url: http://bbs.keinsci.com/thread-33640-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 14
---

# ��WSL�µ�Ubuntu 22.04�а�װVASP 6.3.2��CP2K v2022.2 — 知识卡片

## 1. 系统环境与硬件配置

计算化学软件 VASP 和 CP2K 的安装记录基于 Windows 11 22H2 操作系统和 WSL 下的 Ubuntu 22.04 环境。硬件环境包括 AMD 6800HS CPU 和小新 Air14 Plus 笔记本电脑。该过程参考了 原作者 的博客笔记以及 VASP wiki 的官方安装指南。

---

## 2. Win11 下安装 Ubuntu 22.04

在 Windows 11 管理员权限终端中执行 `wsl --install` 命令，系统会自动下载并安装 WSL 及 Ubuntu 22.04。安装完成后需重启系统，系统弹出 Ubuntu 窗口时需设置 Linux 用户名及密码。

---

## 3. Ubuntu 系统初始化配置

Ubuntu 安装完毕后，需执行 `sudo apt update` 和 `sudo apt upgrade` 更新系统源和软件包。为方便使用，可将 Windows 终端默认配置文件设置为 Ubuntu，右键点击文件夹即可在当前路径打开 Linux 终端窗口。

---

## 4. 创建用户 bin 目录

在 Ubuntu 系统中建立 bin 目录用于存放后续安装的软件源码和编译文件。执行 `cd ~` 进入用户主目录，随后执行 `mkdir bin` 创建目录。

---

## 5. VASP 编译依赖库安装

编译 VASP 6.3.2 前需通过 `apt` 安装必要的依赖库，包括 `build-essential`、`gfortran`、`libopenblas-dev`、`libopenmpi-dev`、`libscalapack-openmpi-dev`、`libfftw3-dev`、`libhdf5-openmpi-dev`、`libfftw3-mpi-dev`、`cmake` 和 `pkg-config`。安装这些库也有助于后续编译 CP2K。

---

## 6. VASP 源码解压与 makefile 配置

将 Windows 系统下的 VASP 源码压缩包复制到 Ubuntu 系统的 `~/bin/` 目录下并解压。复制 `vasp.6.3.2/arch/makefile.include.gnu_omp` 文件到 `vasp.6.3.2` 目录下并重命名为 `makefile.include`，以此作为编译配置文件的基础。

---

## 7. VASP makefile.include 参数修改

需参照 VASP Wiki 修改 `makefile.include` 文件中 `## Customize as of this point!` 之后的部分。配置内容包括设置 `BLASPACK` 为 `-lopenblas`，`SCALAPACK` 为 `-lscalapack-openmpi`，链接 FFTW 和 HDF5 库，并添加相应的头文件路径（INCS）。

---

## 8. VASP 编译过程

保存 `makefile.include` 文件后，进入 `~/bin/vasp.6.3.2` 目录执行编译命令 `make DEPS=1 -j`。在 AMD 6800HS 硬件环境下编译速度较快且未报错，编译完成后可执行文件将生成于 `vasp.6.3.2/bin` 目录中。

---

## 9. VASP 环境变量配置

编译生成的 `vasp_gam`、`vasp_ncl`、`vasp_std` 位于 `vasp.6.3.2/bin` 目录。需在 `~/.bashrc` 文件末尾添加环境变量，包括将 bin 目录加入 PATH、设置 `ulimit -s unlimited` 以及设置 `export OMP_NUM_THREADS=1`。

---

## 10. CP2K 源码准备

从 GitHub 下载 `cp2k-2022.2.tar.bz2` 源码包并复制到 Ubuntu 的 `~/bin/` 目录。执行解压命令 `tar jxvf cp2k-2022.2.tar.bz2`，随后进入 `cp2k-2022.2/tools/toolchain/` 目录进行工具链构建准备。

---

## 11. CP2K 工具链安装

执行 `install_cp2k_toolchain.sh` 脚本配置编译环境，参数包括 `--with-sirius=no`、`--with-plumed=install`、`--with-cmake=system`、`--with-openblas=system`、`--with-fftw=system`。该过程利用系统已安装的 gcc、openmpi、cmake、openblas 和 fftw，等待直至显示 Done!。

---

## 12. CP2K 编译前配置

将工具链生成的配置文件从 `cp2k-202.2/tools/toolchain/install/arch/` 目录复制到 `cp2k-2022.2/arch/` 目录。执行 `source ~/bin/cp2k-2022.2/tools/toolchain/install/setup` 命令加载编译所需的环境变量。

---

## 13. CP2K 编译与执行文件

进入 `~/bin/cp2k-2022.2/` 目录，执行 `make -j 8 ARCH=local VERSION="ssmp psmp"` 进行编译。编译完成后，可执行文件 `cp2k.ssmp`、`cp2k.sopt`、`cp2k.psmp`、`cp2k.popt` 将生成于 `cp2k-2022.2/exe/local/` 目录。

---

## 14. CP2K 环境变量配置

需在 `~/.bashrc` 文件末尾添加 CP2K 的环境变量配置。配置内容包括执行 `source ~/bin/cp2k-2022.2/tools/toolchain/install/setup` 以及将 `~/bin/cp2k-2022.2/exe/local` 目录加入 PATH 环境变量。
