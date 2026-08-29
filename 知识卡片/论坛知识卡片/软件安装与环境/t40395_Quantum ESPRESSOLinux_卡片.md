---
key: t40395
title: Quantum ESPRESSO��Linux����intel����
url: http://bbs.keinsci.com/thread-40395-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 17
---

# Quantum ESPRESSO��Linux����intel���� — 知识卡片

## 1. 安装环境与前置条件

安装环境基于 AMD EPYC 7v12 (128核) 处理器和 Rocky Linux 9.1 系统。为解决 GCC 编译时的 warning 问题并提升性能，采用 Intel 编译器与数学库 (MKL) 编译 Quantum ESPRESSO 7.0 (QE-7.0) 的 MPI 版本。

---

## 2. Intel oneAPI HPC Toolkit 安装文件

需下载 Intel oneAPI HPC Toolkit 的离线安装包，文件名为 l_HPCKit_p_2023.2.0.49440_offline.sh。该工具包包含编译器等基础组件，是构建编译环境的基础。

---

## 3. Intel oneAPI MKL 安装文件

需下载 Intel oneAPI MKL 的离线安装包，文件名为 l_onemkl_p_2023.2.0.49497_offline.sh。MKL (Math Kernel Library) 是 Intel 提供的高性能数学库，用于加速计算。

---

## 4. 执行 Intel 安装脚本权限设置

在运行安装脚本前，需使用 chmod 命令赋予脚本执行权限。命令格式为 `chmod +x <脚资料件名>`，需分别对 HPC Toolkit 和 MKL 的安装脚本执行此操作。

---

## 5. Intel HPC Toolkit 安装步骤

赋予执行权限后，运行 `./l_HPCKit_p_2023.2.0.49440_offline.sh` 启动图形化安装界面。在安装选项中选择“Modify”以自定义安装，确保勾选所需的编译器组件。

---

## 6. Intel MKL 安装步骤

赋予执行权限后，运行 `./l_onemkl_p_2023.2.0.49497_offline.sh` 安装 MKL 数学库。安装过程与 HPC Toolkit 类似，需按提示完成操作。

---

## 7. Intel 安装目录结构

默认安装路径位于用户目录下的 /home/llc/intel/oneapi/。在该目录下可以找到 `modulefiles-setup.sh` 和 `setvars.sh` 等环境配置脚本。

---

## 8. 配置 Intel 环境变量

在 /home/llc/intel/oneapi/ 目录下运行 `./modulefiles-setup.sh` 可生成 modulefiles 文件夹。执行 `source ./setvars.sh` 命令可立即在当前 shell 中加载环境变量。

---

## 9. 验证 Intel 编译器安装

执行 `source ./setvars.sh` 后，可通过查看版本号验证编译器是否安装成功。相关验证命令包括 `icc --version`、`icpc --version` 和 `ifort --version`。

---

## 10. 验证 MPI 与 MKL 安装

加载环境变量后，可通过 `mpirun --version` 检查 MPI 版本，通过 `echo $MKLROOT` 检查 MKL 根目录环境变量是否设置正确。

---

## 11. QE-7.0 源码获取与解压

从 GitHub 发布页下载 qe-7.0-ReleasePack.tgz 压缩包。使用命令 `tar -zvxf qe-7.0-ReleasePack.tgz` 进行解压，解压后进入 qe-7.0 目录。

---

## 12. QE-7.0 配置与编译

在 qe-7.0 目录下执行 `./configure` 进行配置，可添加 `--disable-parallel` 等参数（参考官方教程）。配置完成后，运行 `make all install -j` 进行多线程编译和安装。

---

## 13. QE-7.0 编译成功标志

编译成功后，在 qe-7.0/bin/ 目录下会生成多个以 .x 结尾的可执行文件。这些文件即为 Quantum ESPRESSO 的各种功能模块。

---

## 14. 临时设置环境变量

若要临时使用 QE，需在终端中手动加载 Intel 环境并添加 QE 路径。命令依次为 `source /home/llc/intel/oneapi/setvars.sh` 和 `export PATH=$PATH:/home/llc/software/qe-7.0/bin/`。

---

## 15. 配置别名切换环境

为了避免与 GCC 环境冲突，可在 ~/.bashrc 中设置别名 `qe70`，用于触发 Intel 编译环境及 QE 路径的加载。同时定义一个条件判断逻辑，仅当变量 `useqe70` 为 "Y" 时执行导出操作。

---

## 16. 环境切换脚本逻辑

在 ~/.bashrc 中添加如下逻辑：定义别名 `qe70='export useqe70=Y;source ~/.bashrc'`。随后设置 `if [ "$useqe70" == "Y" ]` 判断，若条件成立，则执行 `export PATH=$PATH:/home/llc/software/qe-7.0/bin/` 和 `source /home/llc/intel/oneapi/setvars.sh`。

---

## 17. 使用环境切换命令

新开终端时默认不加载 Intel 环境。仅在需要时输入命令 `qe70`，此时会自动加载 Intel 编译器、MKL 库以及 QE-7.0 的可执行文件路径。
