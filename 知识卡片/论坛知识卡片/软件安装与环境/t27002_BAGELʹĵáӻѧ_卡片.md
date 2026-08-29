---
key: t27002
title: ��BAGELʹ���ĵá����ӻ�ѧ����BAGEL�İ�װ
url: http://bbs.keinsci.com/thread-27002-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 10
---

# ��BAGELʹ���ĵá����ӻ�ѧ����BAGEL�İ�װ — 知识卡片

## 1. BAGEL 软件概述

BAGEL 是由 Toru Shiozaki 团队开发的一款专注于电子结构计算的量子化学程序。该软件的特色功能是 CASPT2 计算，能够基于 CASSCF 的结果读取自然轨道。BAGEL 的 CASPT2 功能可处理较大的非动态相关能体系，适合计算多达 32 个电子的相关体系。其官方网站和 GitHub 代码仓库分别位于 https://nubakery.org/ 和 https://github.com/qsimulate-open/bagel。

---

## 2. Intel 编译器安装要求

安装 BAGEL 需要使用 Intel 全家桶编译环境，推荐使用 2021 及以上版本以避免 2019 版本中存在的 Bug。安装 BaseKit 和 HPCKit 后，需要执行 `[Intel安装路径]/setvars.sh` 脚本以自动配置用户环境变量。验证安装是否成功可通过检查 `mpicc`、`mpicxx`、`mpirun` 命令以及 `$MKLROOT` 环境变量是否指向 Intel 安装目录下的路径。

---

## 3. Intel 编译器安装命令

Intel BaseKit 2021.4.0 版本的离线安装可通过下载并执行以下命令完成：`wget https://registrationcenter-download.intel.com/akdlm/irc_nas/18236/l_BaseKit_p_2021.4.0.3422_offline.sh` 和 `sh l_BaseKit_p_2021.4.0.3422_offline.sh -a -s --install-dir [Intel安装路径] --eula accept`。Intel HPCKit 2021.4.0 版本的离线安装可通过下载并执行以下命令完成：`wget https://registrationcenter-download.intel.com/akdlm/irc_nas/18211/l_HPCKit_p_2021.4.0.3347_offline.sh` 和 `sh l_HPCKit_p_2021.4.0.3347_offline.sh -a -s --install-dir [Intel安装路径] --eula accept`。

---

## 4. Boost 库版本要求

BAGEL 编译依赖 Boost 库，需注意不能使用 1.77 版本，否则在 configure 阶段会报错或出现 Regex 相关错误。经测试推荐使用 1.71 版本的 Boost。安装完成后需设置环境变量：`export BOOST_ROOT=[Boost安装路径]`、`export PATH=$BOOST_ROOT/bin:$PATH` 以及 `export LD_LIBRARY_PATH=$BOOST_ROOT/lib:$LD_LIBRARY_PATH`。

---

## 5. BAGEL 源码获取

获取 BAGEL 源码应从 GitHub 官方仓库克隆，即执行 `git clone https://github.com/nubakery/bagel.git`。为保证稳定性，建议切换到 v1.2.2 的 release 版本，因为最新 master 分支可能包含未修复的 bug。进入源码目录后，建立 `obj` 目录作为编译文件夹，并将 `bagel_beta` 作为自定义的安装路径。

---

## 6. BAGEL 编译环境准备

编译 BAGEL 前需运行 Automake 工具链生成配置文件，依次执行 `glibtoolize` (或 `libtoolize`)、`aclocal`、`autoconf`、`autoheader` 和 `automake -a`。执行 `automake -a` 时若提示找不到 patch，需安装 patch 工具（如 `yum -y install patch`）并将其路径加入 PATH。若提示缺少 Perl Thread::Queue 模块，可下载相关 rpm 包解压并将路径通过 `export PERLLIB=$PERLLIB:[解压Thread文件夹的路径]` 加入环境变量。

---

## 7. BAGEL 编译配置与安装

在 obj 目录下执行 configure 进行配置，命令示例为：`MPICC=mpicc MPICXX=mpicxx CC=mpicc CXX=mpicxx ../configure CXXFLAGS="-DNDEBUG -std=c++11 -lstdc++" --enable-mkl --with-boost=$BOOST_ROOT --with-mpi=intel --prefix=[刚才创建的bagel_beta文件夹]`。配置完成后，运行 `make -j` 进行编译，最后运行 `make install` 完成安装。

---

## 8. BAGEL 环境变量配置

编译安装完成后，需将 BAGEL 的可执行文件路径和库文件路径加入环境变量才能使用。设置命令为：`export PATH=[刚才创建的bagel_beta文件夹]/bin:$PATH` 和 `export LD_LIBRARY_PATH=[刚才创建的bagel_beta文件夹]/lib:$LD_LIBRARY_PATH`。每次使用 BAGEL 前需确保这些环境变量已生效。

---

## 9. BAGEL 运行脚本配置

运行 BAGEL 计算任务时，需编写脚本按顺序加载必要的运行时环境。首先加载 Intel 环境 `. [Intel安装路径]/setvars.sh`，随后依次设置 Boost 环境变量、patch 路径（如有）、Perl Thread 路径（如有）以及 BAGEL 安装路径。最终通过 MPI 并行命令提交任务，例如：`mpirun -np 16 BAGEL $input_file > $output_file`。

---

## 10. BAGEL 几何优化策略

BAGEL 虽然支持 CASPT2 的梯度计算，但其内置的几何优化算法效率较低。推荐结合外部优化策略，例如使用 Multiwfn 进行几何结构优化，利用其优异的优化效率提升计算速度。相关的 Gaussian external 接口脚本和优化方法详情可参考特定技术论坛的发布页面。
