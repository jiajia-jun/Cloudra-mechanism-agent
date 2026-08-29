---
key: b451
title: 量子化学程序ORCA的安装方法
url: http://sobereva.com/451
domain: 软件安装与环境
source: blog
year: 2018
cards: 22
---

# 量子化学程序ORCA的安装方法 — 知识卡片

## 1. ORCA 程序简介

ORCA 是一款对学术用户免费但不开源的量子化学程序。该程序发展迅速且流行度不断提高，目前资料对应的版本为 ORCA 6。虽然存在 Mac 版本，但由于使用极小众，相关安装方法通常不作介绍。

---

## 2. ORCA 程序获取途径

ORCA 官网与论坛合二为一，网址为 https://orcaforum.kofo.mpg.de。用户需在网站上注册并登录，随后点击页面顶部的 Download 按钮，即可下载可执行程序和手册。

---

## 3. ORCA 测试输入文件示例

为测试 ORCA 安装后是否能正常运行，可使用以下内容作为输入文件（如保存为 test.inp）。该任务设定为使用 4 核并行计算：
! BLYP def2-SVP pal4
 * xyz 0 1
  C 0.00000000 0.00000000 -0.56221066
  H 0.00000000 -0.92444767 -1.10110537
  H -0.00000000 0.92444767 -1.10110537
  O 0.00000000 0.00000000 0.69618930
 *

---

## 4. ORCA Windows 版系统要求

ORCA 的 Windows 版本仅提供 64bit 版本。若使用 32bit Windows 系统，无法直接安装 Windows 版，需安装 64bit Windows 或在虚拟机中运行 Linux 版 ORCA。

---

## 5. Windows 版 ORCA 的并行依赖

ORCA 在 Windows 下基于 MPI 方式进行并行运算，依赖于 Microsoft MPI (MSMPI) 库。ORCA 6 可以搭配 MSMPI 10.0 运行，需下载并安装该版本的 MSMPI。

---

## 6. Windows 版 ORCA 安装步骤

从 ORCA 论坛下载“ORCA [版本号], Windows, 64bit, Installer”对应的压缩包并解压。运行解压后的 Orca[版本号].Win64.exe 安装程序，选择 Complete 方式进行安装。ORCA 6.0.0 安装完成后将占用约 13GB 硬盘空间。

---

## 7. Windows 下 ORCA 运行测试

将测试输入文件放置在目录下，进入 Windows cmd 界面。假设 ORCA 安装在 D:\study\ORCA_6.0.0，输入命令 `D:\study\ORCA_6.0.0\orca H2CO.inp > H2CO.out` 执行计算。并行运行时必须使用 ORCA 的绝对路径。若输出正常且显示 ****ORCA TERMINATED NORMALLY****，则安装成功；若输出混乱交错，则说明并行协同存在问题。

---

## 8. ORCA autoCI 模块的安装

部分后 HF 和多参考计算功能（如 FIC-MRCI、CCSDT）需要 autoCI 模块支持。需在官方论坛下载页面下载“ORCA [版本号], Windows, 64bit, autoci / parallel part”压缩包，并将其解压到 ORCA 安装目录下。安装 autoCI 模块后，ORCA 6 目录大小将达到约 30GB。

---

## 9. 使用 cmder 便捷运行 ORCA

cmder 是一个第三方文本终端，可简化 Windows 下 ORCA 的使用。下载 cmder Full 版并解压，在命令行输入 `Cmder.exe /REGISTER ALL` 注册右键菜单。通过设置，cmder 可模拟 Linux Bash 环境（支持 awk、vi 等工具）。在配置文件 user_profile.sh 中添加别名（如 `alias oo='D:/study/orca600/orca'`），即可使用简短命令调用 ORCA，并利用 `|tee` 同时输出到屏幕和文件。

---

## 10. Linux 下 ORCA 并行环境要求

ORCA 在 Linux 下通过 OpenMPI 库实现并行，运行前需先编译 OpenMPI 库。ORCA 安装包文件名中体现了所需的 OpenMPI 版本（如 openmpi416 代表 OpenMPI 4.1.6），虽然通常兼容其它版本，但建议使用匹配版本。OpenMPI 源代码可在 https://www.open-mpi.org 下载。

---

## 11. Linux 下 OpenMPI 编译前置条件

编译 OpenMPI 前必须检查并安装 gcc 和 gfortran 编译器（例如在 CentOS 或 Rocky Linux 下使用 `yum install gcc` 和 `yum install gcc-gfortran`）。若仅安装 gcc 而缺少 gfortran，OpenMPI 虽能编译通过，但因缺少 Fortran 接口会导致 ORCA 无法正常并行运行。

---

## 12. Linux 下 OpenMPI 编译命令

使用 `tar -xf openmpi-4.1.6.tar.bz2` 解压源码包，进入目录后运行以下命令将 OpenMPI 安装到 `/sob/openmpi416` 目录：
`./configure --prefix=/sob/openmpi416 --disable-builtin-atomics`
`make all install -j`
若编译报错，可去掉 `-j` 参数重试。

---

## 13. Linux 下 OpenMPI 环境变量配置

对于使用 Bash shell 的系统（如 CentOS、Rocky Linux），需在用户目录下的 `.bashrc` 文件末尾添加以下内容：
`export PATH=$PATH:/sob/openmpi416/bin`
`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/openmpi416/lib`
保存后重新打开终端，运行 `mpiexec -V` 显示版本号即说明安装成功。

---

## 14. Linux 版 ORCA 安装文件选择

Linux 版 ORCA 安装包文件名包含指令集标识（如 avx2）。文件名含 avx2 代表 CPU 必须支持 AVX2 指令集方可使用，较老的 CPU 若不支持应下载不带 avx2 字样的安装包。目前主流 CPU 均支持 AVX2 指令集。

---

## 15. Linux 下 ORCA 安装与路径配置

下载并使用 `tar -xf` 命令解压 ORCA 安装包（如 orca_6_0_0_linux_x86-64_avx2_shared_openmpi416.tar）。假设解压目录为 `/sob/orca600/`，需在 `.bashrc` 文件中添加：
`export PATH=$PATH:/sob/orca600`
`export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/orca600`
重新进入终端后即可运行 ORCA。

---

## 16. Linux 下 ORCA 并行运行与别名设置

并行运行 ORCA 时必须输入可执行文件的绝对路径，例如 `/sob/orca600/orca test.inp > test.out`。为简化操作，可在 `.bashrc` 中添加别名 `alias orca='/sob/orca600/orca'`，之后即可直接使用 `orca` 命令。

---

## 17. Linux 系统自带 orca 程序冲突处理

部分 Linux 系统（如 CentOS）自带名为 orca 的屏幕阅读器程序，直接输入 `orca` 会启动该程序。应使用 `rpm -e orca` 命令卸载系统自带的 orca 程序以避免冲突。

---

## 18. root 用户运行 OpenMPI 的配置

在 root 用户下使用 ORCA 时，OpenMPI 要求每次执行命令时必须带 `-allow-run-as-root` 选项。为避免此繁琐操作，可在 `.bashrc` 中添加：
`export OMPI_ALLOW_RUN_AS_ROOT=1`
`export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1`

---

## 19. 多 MPI 库共存时的路径优先级处理

若系统中存在其它 MPI 库或 OpenMPI 版本，且 `which mpiexec` 指向了错误路径，ORCA 可能无法正常并行。解决方法包括：修改或注释掉旧 MPI 库在 `.bashrc` 中的配置，或调整环境变量顺序，将新安装的 OpenMPI 路径（如 `/sob/openmpi416/bin`）置于 `$PATH` 之前，以确保被优先调用。

---

## 20. ORCA 计算结果转换为 Molden 文件

ORCA 自带 `orca_2mkl` 工具，功能类似于 Gaussian 的 formchk。运行命令 `orca_2mkl xxx -molden` 可将 ORCA 计算产生的 `xxx.gbw` 文件转化为 `xxx.molden.input` 文件，后者可直接作为波函数分析程序 Multiwfn 的输入文件。

---

## 21. Multiwfn 直接读取 ORCA 文件设置

若将 Multiwfn 目录下 `settings.ini` 文件中的 `orca_2mklpath` 参数设置为当前机器中 `orca_2mkl` 可执行文件的实际路径，Multiwfn 可以直接载入 ORCA 的 `.gbw` 文件，无需手动转换。

---

## 22. Windows 下 ORCA 输出文件的编码问题

在 Windows 下运行 ORCA 时，不应使用 PowerShell，因为其通过重定向产生的输出文件默认为 Unicode 编码，Multiwfn 等工具无法读取。建议使用 cmd 或 cmder 运行 ORCA 以生成正确编码的输出文件。
