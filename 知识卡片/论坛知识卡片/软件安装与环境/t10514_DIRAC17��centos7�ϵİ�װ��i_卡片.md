---
key: t10514
title: DIRAC17��centos7�ϵİ�װ��intel15 and openmpi2.02��
url: http://bbs.keinsci.com/thread-10514-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2018
cards: 12
---

# DIRAC17��centos7�ϵİ�װ��intel15 and openmpi2.02�� — 知识卡片

## 1. DIRAC 程序简介与资源

DIRAC 是主要用于相对论量子化学计算的软件。官方网址为 http://www.diracprogram.org。DIRAC17 版本的文档地址为 http://www.diracprogram.org/doc/release-17/。相关学习资料包括 PhD course - Introduction to Relativistic Quantum Chemistry。

---

## 2. DIRAC 文档格式与安装说明

DIRAC 官方手册采用 reStructuredText 格式编写。文档中包含详细的安装说明和参数配置方法。安装过程通常采用命令行交互方式进行。配置时需将示例路径中的 XXX 替换为实际的用户名或路径。

---

## 3. DIRAC 系统依赖环境要求

Linux 环境下安装 DIRAC 需要满足特定的依赖库和编译器版本。推荐安装 Intel compilers 版本 13.0-15.0。推荐安装 OpenMPI 版本 1.6.2-1.8.5 或 IntelMPI 版本 4.1-5.0。

---

## 4. DIRAC 依赖的 Python 与构建工具

DIRAC 安装需要 anaconda python2.7 环境。构建工具推荐使用 cmake 版本 2.8.10-3.5。依赖的 boost 库推荐版本为 1.54.0-1.60.0。可以直接使用 yum 命令安装 boost、cmake、zlib 和 boost-devel。

---

## 5. DIRAC 对 PCMSolver 的依赖处理

DIRAC 编译需要依赖 PCMSolver。推荐使用 git clone 命令下载 PCMSolver 源码到本地。下载完成后会在默认目录下生成 '/home/XXX/pcmsolver' 文件夹。

---

## 6. DIRAC 源码解压与目录准备

下载 DIRAC 源码包后需使用 tar 命令解压。解压后需进入源码目录 DIRAC-17.0-Source。安装前需要创建目标安装目录。

---

## 7. DIRAC 安装配置命令

DIRAC 使用 setup 脚本进行安装配置。配置命令需指定 Fortran、C、C++ 编译器及 MPI 选项。示例配置命令为 `./setup --fc=mpif90 --cc=mpicc --cxx=mpicxx --mpi --mkl=sequential --prefix=/home/XXX/DIRAC17`。

---

## 8. 修改 PCMSolver 路径配置

需修改 src/pcm/CMakeList.txt 文件中的 PCMSolver 源地址。将默认的 GitHub 地址替换为本地下载路径 '/home/XXX/pcmsolver/'。可以使用 sed 命令批量替换文件中的路径字符串。

---

## 9. DIRAC 编译与构建步骤

进入 build 目录开始编译过程。执行 make 命令进行源码编译。编译时可使用 make -j n 启用多核并行编译。

---

## 10. DIRAC 安装测试环境设置

执行测试前需设置临时文件目录环境变量 DIRAC_TMPDIR。需设置 MPI 运行命令环境变量 DIRAC_MPI_COMMAND，例如 `mpirun -np 8`。使用 make test 命令执行安装测试。

---

## 11. DIRAC 安装收尾与环境变量配置

测试通过后执行 make install 完成安装。需将 DIRAC 的 bin 目录添加到 PATH 环境变量中。使用 source ~/.bashrc 命令使环境变量生效。

---

## 12. DIRAC 安装验证方法

安装完成后可使用 `pam-dirac -h` 命令验证程序是否正常。查看帮助信息以确认程序功能可用。
