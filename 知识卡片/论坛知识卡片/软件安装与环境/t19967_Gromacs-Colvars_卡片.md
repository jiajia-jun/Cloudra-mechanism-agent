---
key: t19967
title: ����Gromacs-Colvars���������ܼ���
url: http://bbs.keinsci.com/thread-19967-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2020
cards: 12
---

# ����Gromacs-Colvars���������ܼ��� — 知识卡片

## 1. GROMACS 2021 编译参数修正

GROMACS 2021 编译时启用 GPU 支持的参数需要调整。原有的 `-DGMX_GPU=on` 参数应更改为 `-DGMX_GPU=cuda`。

---

## 2. Colvars 模块功能概述

Colvars 是一种集合变量模块，常用于增强采样分子动力学模拟。该模块实现了伞形采样、eABF、Metadynamics、SMD 等多种增强采样计算方法。相较于 Plumed，Colvars 在 GROMACS 中具有更高的计算效率和更细致的控制能力。

---

## 3. Colvars 对 GROMACS 的支持

Colvars 模块现已支持 GROMACS，不再仅限于与 NAMD 或 LAMMPS 配合使用。这使得在 GROMACS 中利用 Colvars 进行复杂模拟成为可能。

---

## 4. 推荐版本与源码获取

GROMACS 与 Colvars 联合编译的推荐版本为 GROMACS 2020.4 和 Colvars 的 master 分支。源码可分别从 GROMACS 官方文档网站和 Colvars 的 GitHub 仓库下载。

---

## 5. 源码解压命令

下载源码压缩包后，需分别解压 Colvars 和 GROMACS 源码。命令为 `unzip colvars-master.zip` 和 `tar xvf gromacs-2020.4.tar.gz`。

---

## 6. Colvars 补丁应用命令

需将 Colvars 补丁应用到 GROMACS 源码目录中。执行命令为 `sh ./colvars-master/update-colvars-code.sh ./gromacs-2020.4`。

---

## 7. GROMACS 编译配置命令

进入 GROMACS 源码目录并创建 build 目录后，使用 cmake 进行配置。配置命令包含开启 FFTW、GPU 支持及指定安装路径，如 `cmake .. -DGMX_BUILD_OWN_FFTW=ON -DGMX_GPU=on -DCMAKE_INSTALL_PREFIX=xxx`。

---

## 8. GROMACS 编译与安装命令

配置完成后，执行 `make -j12` 进行多核编译，随后执行 `make install` 完成安装。安装后需通过 `source xxxxxxx/GMXRC` 命令加载环境变量。

---

## 9. 运行带 Colvars 的模拟

在 GROMACS 中使用 Colvars 功能，需要在 `gmx mdrun` 命令中添加 `-colvars xxxx.dat` 参数，其中 `xxxx.dat` 为 Colvars 配置文件。

---

## 10. 模拟运行命令示例

一个完整的运行示例命令为 `gmx mdrun -v -ntmpi 1 -ntomp 2 -gpu_id 0 -deffnm step5 -colvars colvars.dat`。

---

## 11. 断点续接参数

若需从之前的 Colvars 状态文件继续模拟，需在命令中同时指定配置文件和状态文件。参数格式为 `-colvars xxxx.dat -colvars_restart test.colvars.state.dat`。

---

## 12. GROMACS 中 Colvars 配置要求

在 GROMACS 中使用 Colvars 时，配置文件开头必须包含 `units gromacs` 声明，以确保单位兼容性。
