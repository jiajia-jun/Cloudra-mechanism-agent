---
key: t57997
title: ʹ��MolAICal���е�����-�ķ��ӶԽӽ̡̳�Ҳ�����ڵ�����-�����ʶԽ�
url: http://bbs.keinsci.com/thread-57997-1-1.html
domain: 其他量化软件
source: keinsci
year: 2026
cards: 10
---

# ʹ��MolAICal���е�����-�ķ��ӶԽӽ̡̳�Ҳ�����ڵ�����-�����ʶԽ� — 知识卡片

## 1. MolAICal 与 LightDock 结合流程概述

MolAICal 支持集成开源对接程序 LightDock，并通过 MM/GBSA 或 MM/PBSA 方法提升蛋白-蛋白、蛋白-多肽等体系对接结果的准确性。LightDock 采用基于萤火虫群优化(GSO)算法的对接策略，适用于处理包含构象柔性、残基侧链柔性或需要考虑静电作用的复杂体系。MolAICal 内部包含该教程案例，以 GLP-1R 和多肽 exendin-4 (PDB ID: 7LLL.pdb) 为示例演示操作步骤。

---

## 2. 外部软件环境要求

本教程的操作流程需在 Linux 环境下完成，Windows 版本的 MolAICal 不支持该特定流程。所需的外部软件包括 NAMD (CPU 版本)、PyMol 和 VMD。若使用 NAMD 3.x 等高版本，需将教程命令中的 "namd2" 替换为 "namd3"。

---

## 3. MolAICal 容器环境配置

Linux 版本的 MolAICal 提供内部 Shell 环境，用于解决依赖问题及安装外部软件。进入内部 Shell 环境的命令为 `molaical.exe -eset shell in`，退出命令为 `exit`。若需退出环境同时保留容器内计算结果，可使用 `molaical.exe -eset sys run molaical`。

---

## 4. 拷贝外部软件至 MolAICal 环境

在进入 MolAICal 内部 Shell 后，需将宿主机上的 VMD 和 NAMD 安装文件拷贝至容器内部路径 (如 `/root/soft`)。操作命令示例为 `cp /home/user/<源文件> /root/soft`，其中源文件路径位于宿主机，目标路径位于容器内部。

---

## 5. 在 MolAICal 环境中安装 NAMD

解压 NAMD 文件后，需使用 `molaical.exe -call set -n NAMD -p "/root/soft/namdcpu/namd3"` 命令将其路径告知 MolAICal。为确保 MM/GBSA 计算的可重复性，建议使用 NAMD 的 CPU 版本而非 CUDA 版本，因为 CUDA 版本中的 seed 参数可能导致结果差异。

---

## 6. 在 MolAICal 环境中安装 VMD

VMD 的安装包括解压文件、修改 `configure` 文件中的安装路径 (`$install_bin_dir` 和 `$install_library_dir`)、执行 `./configure LINUXAMD64` 以及 `make install`。安装完成后，使用 `molaical.exe -call set -n VMD -p "/root/soft/vmd193/bin/vmd"` 命令注册 VMD 路径。

---

## 7. 蛋白-蛋白对接设置与膜环境参数

进入教程文件目录后，使用 LightDock 生成对接构象的命令包含 `-membrane` 参数以处理膜蛋白体系。`-membrane` 标志会使生成的粒子群分布在 Z 轴上，模拟膜环境下的对接情况，命令示例如 `molaical.exe -call run -c ldock -i lightdock3_setup.py mempro.pdb P_peptide.pdb -membrane --noxt --noh --now -sp -rst restraints.list`。

---

## 8. LightDock 对接模拟命令参数

执行对接模拟使用 `molaical.exe -call run -c ldock -i lightdock3.py setup.json 100 -s fastdfire -c 12 -min` 命令。其中 `-c ldock` 指定使用 LightDock 模块；`-s fastdfire` 设置打分函数为 fastdfire；`-c 12` 指定使用的 CPU 核心数；`-min` 选项启用 SciPy 的 `fmin_powell` 算法对每次群优化的最优解进行局部最小化。

---

## 9. 模型聚类、排序与过滤参数

使用 `molaical.exe -call run -c sfile -i lrank.sh ...` 命令调用脚本对模型进行聚类、排序和过滤。关键参数包括：`1::=` 和 `2::=` 分别指定受体和配体路径；`3::=` 和 `4::=` 指定链 ID；`6::=` 指定约束文件；`13::=` 设置过滤阈值 (默认 0.4，示例中设为 0.7)，用于根据关键原子距离筛选结构。

---

## 10. 结果输出与过滤说明

过滤和聚类完成后，会生成一个名为 "filtered" 的目录，其中包含默认 70% 过滤标准的预测结构。目录中的 "rank_filtered.list" 文件记录了经过 LightDock DFIRE (fastdfire) 打分后筛选出的结构及其对应排名。
