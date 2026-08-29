---
key: t57999
title: ʹ��MolAICal���ж�������ɸѡ�̳�-ͬ�������ڵ����ʺͺ��������ɸѡ
url: http://bbs.keinsci.com/thread-57999-1-1.html
domain: 其他量化软件
source: keinsci
year: 2026
cards: 13
---

# ʹ��MolAICal���ж�������ɸѡ�̳�-ͬ�������ڵ����ʺͺ��������ɸѡ — 知识卡片

## 1. MolAICal 虚拟筛选工作流

MolAICal 是一款针对药物设计的虚拟筛选软件，整合了配体生成、对接和基于 MM/GBSA 或 MM/PBSA 的重打分功能。该软件利用开源工具 LightDock 进行分子对接，并通过群智能优化算法实现高精度的配体-受体对接模拟。该工作流支持对多肽及小分子进行大规模并行筛选，适用于蛋白质-配体、蛋白质-多肽、蛋白质-RNA 及蛋白质-DNA 等相互作用研究。

---

## 2. LightDock 对接平台与算法

LightDock 是基于 GPL-3.0 协议的开源对接工具，支持蛋白质-配体、蛋白质-多肽、蛋白质-RNA 和蛋白质-DNA 的对接模拟。该软件利用萤火虫群优化算法（Glowworm Swarm Optimization, GSO）进行目标函数优化，能够有效处理结合能评分及受体表面的不规则形状。LightDock 特别适用于识别难以通过常规实验观察的结合位点以及探索蛋白-蛋白相互作用模式。

---

## 3. 虚拟筛选环境要求

本教程相关操作需要在 Linux 操作系统下进行。虚拟筛选过程需要预先安装 NAMD（CPU 版本）、PyMol、VMD 和 MolAICal。若使用 NAMD 3.x 版本，需将教程中命令里的 `namd2` 替换为 `namd3`，建议使用 CPU 版本以保证 MM/GBSA 计算的可重复性。

---

## 4. MolAICal 外部软件集成安装

在 MolAICal 容器内安装外部软件（如 NAMD 和 VMD）时，需先将安装包复制到容器目录（如 `/root/soft`），并在容器内部执行安装。安装 NAMD 后，使用 `molaical.exe -call set -n NAMD -p "[路径]"` 命令注册路径。安装 VMD 时，需修改 `configure` 文件中的安装目录路径（如 `/root/soft/vmd193/bin`），执行 `make install` 后，同样使用 `molaical.exe -call set -n VMD -p "[路径]"` 进行注册。

---

## 5. 虚拟筛选脚件说明

虚拟筛选过程依赖于一个 Docking Unit 脚资料件（如 `dock_u.sh`），该脚本定义了单个对接任务的具体操作。工作目录中需包含受体结构文件（如 `mempro.pdb`）和存放候选结构的目录（如 `linear`）。通过 Docking Unit 脚本，可以结合 MolAICal 的管道功能，同时筛选多个候选配体，实现高通量筛选。

---

## 6. 使用 MolAICal 生成线性多肽

使用 `molaical.exe -call run -c pepgen` 命令可生成线性多肽的 3D 结构。参数 `-l` 指定多肽含有的残基数，`-n` 指定生成的唯一结构数量，`-3d` 启用 pyPept 生成 3D 结构。若使用 DFIRE 评分函数，建议添加 `-nc` 参数以避免末端修饰（如乙酰化/酰胺化）导致的识别错误。

---

## 7. 使用 MolAICal 生成固定序列多肽

生成具有固定氨基酸序列和环化位置的多肽时，使用 `molaical.exe -call run -c pepgen -s [序列] -fix [位置]` 命令。参数 `-s` 指定起始序列，`-fix` 指定需要固定形成二硫键的半胱氨酸位置（如 `1 7`），`-d` 控制序列扩展方向。生成的 3D 结构保存在由 `-dir` 指定的目录中。

---

## 8. 使用 MolAICal 生成环状多肽

MolAICal 支持生成具有环状结构的多肽，包括首尾相连或侧链环化形式。生成环状多肽时需添加 `-cc` 参数，并使用 BILN/HELM 格式定义环化方式。示例命令为 `molaical.exe -call run -c pepgen -l 8 -n 3 -rc 3 -cc -3d -c 4 -dir cyclic`，其中 `-c` 指定使用的 CPU 核心数。

---

## 9. 启动线性或修饰多肽虚拟筛选

针对 `linear` 或 `mpep` 目录中的多肽进行筛选时，执行 `molaical.exe -call run -c sfile -i vs_ml.sh` 命令。关键参数包括：`1::=` 指定配体目录，`2::=` 指定受体文件，`5::=` 指定每个对接任务使用的 CPU 数量，`6::=` 指定筛选使用的管道数量。通过调整 `6::=` 的值，可以平衡硬件资源消耗与计算效率，建议使用单管道以避免内存溢出。

---

## 10. 启动环状多肽虚拟筛选

针对 `cyclic` 目录中的环状多肽进行筛选时，需在命令中指定专用的环状对接脚本 `dock_u_cyc.sh`。命令格式为 `molaical.exe -call run -c sfile -i vs_ml.sh 1::=cyclic 2::=mempro.pdb 3::=R 4::=Z 5::=8 6::=1 8::=0 9::=dock_u_cyc.sh 11::=cyc_result`。`8::=0` 表示直接在队列中运行，`11::=` 指定结果输出目录。

---

## 11. 筛选结果过滤与重打分

使用 `rank_ppn.py` 脚本可对筛选结果进行过滤和基于 MM/GBSA 的重打分。参数 `-p` 指定保留结果的比例（如 20），`-m` 指定模式（`filtered` 为仅过滤，`mmgbpbsa` 为仅重打分，`both` 为两者兼有）。输出目录分别由 `-fo`（过滤结果）和 `-mo`（重打分结果）指定。

---

## 12. 虚拟筛选任务的中断与恢复

若筛选任务中断，可使用 `molaical.exe -call run -c sfile -i vs_ml.sh ... 12::=continuevs` 命令恢复处理未完成的筛选任务。参数 `7::=` 决定是否使用 MM/GB/PB/SA 结果（1 为使用，0 为不使用）。恢复模式下，程序会跳过已处理文件，仅对剩余文件进行筛选，从而有效利用计算资源。

---

## 13. 筛选结果的文件管理

当筛选任务完成或通过恢复模式确认所有任务结束后，MolAICal 会自动将工作目录（如 `linear`）中筛选出的 PDB 文件移动到 `${work_dir}_complete_folder` 目录。此操作有助于区分已处理和未处理的文件，便于后续的结果分析和文件管理。
