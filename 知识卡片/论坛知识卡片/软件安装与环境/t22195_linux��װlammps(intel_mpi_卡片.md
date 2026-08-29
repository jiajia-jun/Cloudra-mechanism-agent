---
key: t22195
title: linux��װlammps(intel_mpi)���deepmd
url: http://bbs.keinsci.com/thread-22195-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 6
---

# linux��װlammps(intel_mpi)���deepmd — 知识卡片

## 1. LAMMPS 稳定版源码下载

LAMMPS 稳定版源码可从官方或 GitHub Releases 页面获取。下载命令需使用 `wget` 并添加 `--no-check-certificate` 参数以忽略证书检查。下载完成后需使用 `tar` 命令解压文件。
- wget https://lammps.sandia.gov/tars/lammps-stable.tar.gz --no-check-certificate
- tar -xzf lammps-stable.tar.gz

---

## 2. 编译环境变量配置

编译 LAMMPS 前需配置 Intel 编译器环境和高版本 GCC 环境。Intel 编译器环境通过执行 `psxevars.sh` 脚本加载。GCC 环境推荐使用 module 方式加载（示例版本为 v7.5.0），以兼容 Makefile 中的 GNU make。
- source /opt/intel/parallel_studio_xe_2018/psxevars.sh
- module load GCC/7.5.0

---

## 3. DeePMD-kit LAMMPS 模块集成

若通过 conda 安装了 deepmd-kit，需将其包含的 LAMMPS 模块文件复制到 LAMMPS 源码的 `src/` 目录下。复制命令中的路径变量 `$CONDA_PATH` 指代 Anaconda 或 Miniconda 安装路径，`$ENV_NAME` 指代 conda 安装 deepmd-kit 的虚拟环境名称。
- cp -r $CONDA_PATH/envs/$ENV_NAME/share/USER-DEEPMD .

---

## 4. LAMMPS 软件包安装基础命令

LAMMPS 提供特定命令用于安装、卸载及查看软件包状态。常用命令包括查看当前已安装包状态 (`package-status`/`ps`)、安装标准包 (`yes-std`)、安装用户包 (`yes-user`) 等。部分软件包安装可能需要额外库或外部库支持，需参考官方文档处理依赖。
- make package-status
- make ps
- make yes-all
- make no-all
- make yes-std
- make no-std
- make yes-user
- make no-user
- make yes-lib
- make no-lib
- make yes-ext
- make no-ext

---

## 5. 针对 DeePMD 的 LAMMPS 软件包选择

仅安装 deepmd-kit 相关功能时，需启用 `kspace` 和 `user-deepmd` 包。若需安装其他包，可使用 `make yes-<package-name>` 命令或组合使用标准包安装与库包卸载命令 (`make yes-std && make no-lib`)。示例组合包含长程静电 (`kspace`)、多体势 (`manybody`) 和分子 (`molecule`) 包。
- make yes-kspace
- make yes-user-deepmd
- make yes-kspace yes-manybody yes-molecule
- make yes-std && make no-lib

---

## 6. LAMMPS 编译命令

进入解压后的 `lammps-29Oct20/src/` 目录即可执行编译。编译命令使用 `make`，`-j` 参数指定并行编译的 CPU 核心数（示例为 12），目标文件名为 `intel_cpu_intelmpi`。若之前编译失败，重新编译前建议执行清理命令。
- make -j 12 intel_cpu_intelmpi
- make clean-all
