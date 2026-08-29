---
key: t23143
title: ��centos 7.6�±���amber18 & AmberTools18 openmpi 1.8.8���а�ȫ��¼
url: http://bbs.keinsci.com/thread-23143-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 14
---

# ��centos 7.6�±���amber18 & AmberTools18 openmpi 1.8.8���а�ȫ��¼ — 知识卡片

## 1. Amber18 安装前的系统依赖安装

使用 yum 安装编译 Amber18 及其工具所需的系统库和编译器。若使用 CentOS 等 RedHat 系 Linux 发行版，执行指定命令安装 tcsh、make、gcc、gfortran、flex、bison 等基础工具及 libXt-devel、libXext-devel 等图形库。
- 命令: `yum -y install tcsh make gcc gcc-gfortran gcc-c++ which flex bison patch bc libXt-devel libXext-devel perl perl-ExtUtils-MakeMaker util-linux wget bzip2 bzip2-devel zlib-devel tar`

---

## 2. 编译器版本一致性检查

确认系统中的 gcc、g++ 和 gfortran 编译器版本完全一致。版本不匹配可能导致编译过程出错或程序运行异常，需在安装前逐一检查版本号。
- 命令: `gcc -v`、`g++ -v`、`gfortran -v`

---

## 3. Amber18 源码包解压

将 Amber18 和 AmberTools18 的源码压缩包解压至用户目录下。建议解压路径为 `/home/username/Desktop/` 或其他非系统目录，避免因使用 root 用户安装至 `/usr/local` 等系统目录而带来的权限问题。
- 命令: `cd /home/username/Desktop/`、`tar jxvf AmberTools18.tar.bz2`、`tar jxvf Amber18.tar.bz2`

---

## 4. 环境变量配置与生效

在 `.bashrc` 配置文件中添加 Amber 的环境变量设置，并立即执行 source 命令使其生效。无论安装过程中是否出现报错，都应尝试重新加载配置文件，若仍无法解决，可考虑删除安装文件重新开始。
- 命令: `test -f /home/username/Desktop/amber18/amber.sh && source /home/liuyaoze/Desktop/amber18/amber.sh`、`source ~/.bashrc`

---

## 5. 串行版本配置与编译

运行 configure 脚本配置编译环境，使用 gnu 编译器进行串行版本安装。配置过程中若出现 Warning 应予以关注；如果不需要更新或自带 Python 导致冲突，可添加 `--no-updates` 参数跳过更新。
- 命令: `./configure gnu`、`make install`

---

## 6. 串行版本测试

在 Amber18 安装目录下执行环境变量脚本，随后运行测试套件以验证串行安装是否成功。建议使用普通用户而非 root 用户执行测试，确保程序在常规用户权限下功能正常。
- 命令: `source amber.sh`、`make test`

---

## 7. OpenMPI 安装路径与解压

进入 AmberTools 源码目录，将 openmpi-1.8.8 的安装包上传或放置于该目录下并进行解压。OpenMPI 需在配置并行版本的 Amber 之前完成安装。
- 路径/命令: `cd $AMBERHOME/AmberTools/src`、`tar jxvf openmpi-1.8.8.tar.bz2`

---

## 8. OpenMPI 编译配置

在 AmberTools 的 src 目录下执行专用的 OpenMPI 配置脚本，使用 gnu 编译器进行构建。确保仅在当前目录进行此配置操作，且版本号需与教程一致。
- 命令: `./configure_openmpi gnu`

---

## 9. MPI 环境变量设置

安装 OpenMPI 后，需在用户 `.bashrc` 文件中设置 MPI 相关的环境变量。将 `MPI_HOME` 指向 AmberTools 目录，并将其 bin 和 lib 路径分别添加至 `PATH` 和 `LD_LIBRARY_PATH`，随后重新加载配置文件。
- 配置内容:
  ```bash
  export MPI_HOME=$AMBERHOME/AmberTools
  export PATH=$PATH:$MPI_HOME/bin
  export LD_LIBRARY_PATH=$MPI_HOME/lib:$LD_LIBRARY_PATH
  ```
- 命令: `source ~/.bashrc`

---

## 10. Amber18 并行版本配置与编译

配置 Amber18 的并行版本，禁用自动更新并启用 MPI 支持，随后进行安装。此步骤依赖于 OpenMPI 的正确安装及环境变量配置。
- 命令: `./configure --no-updates -mpi gnu`、`make install`

---

## 11. 并行版本测试设置与执行

设置并行运行的环境变量 `DO_PARALLEL`，指定使用 8 个核心通过 mpirun 运行，最后执行测试。测试建议在普通用户权限下进行，以验证并行功能的正确性。
- 命令: `export DO_PARALLEL="mpirun -np 8"`、`make test`

---

## 12. MPI 版本冲突处理

OpenMPI 和 MPICH 均使用 `mpirun` 命令，若系统中同时安装两者可能导致命令冲突。解决方法是修改当前用户的 `~/.bashrc` 文件，调整 PATH 变量的顺序，将希望使用的 MPI 版本路径置于另一版本之前。
- 验证命令: `echo $PATH`

---

## 13. Miniconda 与 Python 环境冲突

Amber18 自带的 Miniconda 可能会与系统原有的 Python 环境产生冲突。这种冲突可能较难排查且影响深远，安装过程中需特别注意 Python 环境的配置。

---

## 14. 权限与安装目录选择

安装过程建议避免使用 root 用户，推荐将 Amber18 安装在 `/home/username/` 等用户目录下。若必须安装至 `/usr/local` 等系统目录，需使用 `sudo` 修改目录权限，且不能直接安装到 local 根目录，必须在 local 下创建子目录以免覆盖系统文件。
- 权限命令示例: `sudo chmod 777 /usr/local`
