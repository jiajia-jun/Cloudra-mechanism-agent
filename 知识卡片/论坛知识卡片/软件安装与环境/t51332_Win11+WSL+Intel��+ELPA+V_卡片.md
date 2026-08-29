---
key: t51332
title: Win11+WSL+Intel��+ELPA+VASP��װ
url: http://bbs.keinsci.com/thread-51332-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2025
cards: 13
---

# Win11+WSL+Intel��+ELPA+VASP��װ — 知识卡片

## 1. Windows11+WSL与Linux文件交互

Windows11 系统结合 WSL 可实现 Linux 文件系统的直接访问与便捷编辑，兼顾 Windows 的易用性与 Linux 的计算环境优势。Windows 资源管理器可访问 Linux 文件目录，支持文件的直接复制粘贴和文本编辑。Win11 系统底层实现了虚拟化，Linux 运行效率较高；相比纯 Linux 系统，Windows + WSL 方案的性能损耗极小（约 3%），完全可以接受。

---

## 2. ELPA库对VASP计算效率的提升

在 VASP 计算中集成 ELPA 库可显著提升计算速度，相关测试表明其加速能达到 25%。ELPA 库的优化效果明显，适合作为 VASP 的加速解决方案。该库的引入需要编译 VASP 时进行相应的配置链接。

---

## 3. Windows11系统WSL安装准备

在 Windows11 LTSC 等不包含 Microsoft Store 的系统中，可通过 PowerShell 命令安装 WSL。使用 `wsreset -i` 命令可尝试重置商店应用或进行相关初始化操作。建议在“电源模式”中将处理器电源管理模式设置为“最佳性能”。

---

## 4. Debian系统源更换为阿里云镜像

在 WSL 安装的 Debian 系统中，为提高软件包下载速度，可将默认源更换为阿里云镜像。使用 `sed` 命令替换 `/etc/apt/sources.list` 文件中的 `deb.debian.org`、`security.debian.org` 和 `ftp.debian.org` 为 `mirrors.aliyun.com`。更换源后需执行 `apt update` 和 `apt upgrade` 更新软件包列表和系统。

---

## 5. WSL基础依赖工具安装

在 WSL 环境中进行编译前，需安装基础构建工具和依赖库。使用命令 `apt-get install rsync build-essential python3` 安装 rsync、构建工具链及 Python3 环境。这些工具是后续编译 Intel oneAPI 和 VASP 的基础。

---

## 6. Intel oneAPI HPC Toolkit静默安装

Intel oneAPI 2025 版本整合了 Base Toolkit 和 HPC Toolkit，通过下载离线安装包可进行静默安装。执行安装命令需包含 `--silent --cli --eula accept` 参数以自动接受协议并进入命令行静默模式。离线安装包文件名为 `intel-oneapi-hpc-toolkit-2025.0.1.47_offline.sh`。

---

## 7. Intel编译器环境变量配置

Intel oneAPI 安装完成后，需将环境变量写入 `/etc/profile` 文件以确保全局生效。需添加 `source /opt/intel/oneapi/setvars.sh intel64` 以初始化环境变量。同时需手动设置 `LD_LIBRARY_PATH`，添加 `/opt/intel/oneapi/2025.0/lib` 路径。若 `/etc/profile` 文件无写入权限，需在 Linux 中使用 `chmod 777 /etc/profile` 修改权限后，再通过 Windows 编辑器修改。

---

## 8. ELPA库下载与解压

为编译 ELPA 加速库，需从官方源下载对应版本的源码包。ELPA 2024.05.001 版本的下载链接为 `https://elpa.mpcdf.mpg.de/software/tarball-archive/Releases/2024.05.001/elpa-2024.05.001.tar.gz`。下载后需解压并进入源码目录准备编译。

---

## 9. ELPA库编译配置参数

ELPA 编译配置需指定 Intel 编译器套件（mpiicx, mpiicpx, mpiifx）及 MKL 路径。若 CPU 不支持 avx512 指令集，需在配置命令中加入 `--disable-avx512` 选项。安装路径可通过 `--prefix` 自定义，示例中使用 `/opt/elpa-2024.05.001`。

---

## 10. ELPA库编译与安装

ELPA 库的编译与安装过程通过 `make` 命令完成。配置完成后，依次执行 `make -j` 进行多线程编译，以及 `make install` 将库安装到指定目录。安装完成后需将 ELPA 的库路径加入 `LD_LIBRARY_PATH` 环境变量。

---

## 11. VASP makefile.include配置修改

编译 VASP 前需将 `arch/makefile.include.intel` 复制为当前目录的 `makefile.include` 并针对新编译器进行修改。将文件中的编译器 `mpiifort` 替换为 `mpiifx`，`icc` 替换为 `icx`，`icpc` 替换为 `icpx`。在文件末尾添加 ELPA 相关的编译标志和路径链接。

---

## 12. VASP编译命令

在配置好 `makefile.include` 后，使用 `make` 命令进行编译。执行 `make DEPS=1 -j18 all`，其中 `-j18` 指定使用 18 个线程进行并行编译。该命令会同时处理依赖关系并编译所有 VASP 可执行文件。

---

## 13. VASP运行命令别名设置

为方便调用 VASP，可在 `/etc/profile` 中设置环境变量别名。将 `vasp_std`、`vasp_gam`、`vasp_ncl` 分别定义为使用 18 核 MPI 运行对应可执行文件的命令。设置后执行 `source /etc/profile` 即可直接通过别名启动计算。
