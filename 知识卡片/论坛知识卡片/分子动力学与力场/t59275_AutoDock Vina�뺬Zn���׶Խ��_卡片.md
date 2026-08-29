---
key: t59275
title: AutoDock Vina�뺬Zn���׶Խ����̾������
url: http://bbs.keinsci.com/thread-59275-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2026
cards: 17
---

# AutoDock Vina�뺬Zn���׶Խ����̾������ — 知识卡片

## 1. AutoDock Vina 含锌金属蛋白对接概述

AutoDock Vina 原生不直接支持含金属配合物如 Zn²⁺ 的对接，需通过特定参数和脚本实现处理。官方建议使用 AutoDock4Zn 及其提供的 AutoGrid4 生成 AD4Zn affinity maps，并在 Vina 中使用 --scoring ad4 进行对接。该方法通过定义锌伪原子及扩展力场参数，可处理锌配位配体的对接。

---

## 2. 金属对接环境依赖安装

通过 Conda 安装对接所需工具包，包括 Python 绑定版 Vina、Meeko、RDKit、AutoGrid 等依赖。推荐创建独立环境并统一使用 conda-forge 源进行安装，以避免版本冲突。
- 命令：`conda create -n vina_clean -c conda-forge python=3.10 numpy scipy rdkit vina meeko gemmi autogrid prody molscrub -y`

---

## 3. 解决 Conda 服务协议报错

在非交互式安装 Conda 包时，若出现 `condaTosNonInteractiveError`，需手动执行命令接受服务协议。此步骤适用于环境创建受阻时的强制许可确认。
- 命令：`conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main`
- 命令：`conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r`

---

## 4. ADFRsuite 安装与调用

ADFRsuite 包含 AutoGrid4 和用于金属对接的 Python 脚本，需独立下载安装而非通过 Conda 管理。调用其内部工具时应使用绝对路径或配置环境变量，避免与 Conda 环境中的 Python 版本冲突。
- 路径示例：`~/ADFRsuite-1.0/bin/pythonsh`、`~/ADFRsuite-1.0/bin/autogrid4`

---

## 5. 金属对接官方脚本获取

从 AutoDock-Vina 官方 GitHub 仓库下载示例代码，获取处理锌金属所需的专用脚本。核心文件包括锌伪原子生成脚本、GPF 生成脚本以及 Zn 专用参数文件，需存放于工作目录中。
- 关键文件：`zinc_pseudo.py`、`prepare_gpf4zn.py`、`AD4Zn.dat`

---

## 6. 受体预处理与加氢

受体蛋白需去除水分子并添加氢原子，使用 Meeko 的 `mk_prepare_receptor.py` 将其转换为 Vina 可读取的 PDBQT 格式。若过程出现 FPP 残基模板警告，只要最终生成 PDBQT 文件即可忽略。
- 命令：`mk_prepare_receptor.py -i proteinH.pdb -o protein -p`

---

## 7. 锌伪原子 (TZ) 定位

使用 ADFRsuite 中的 `zinc_pseudo.py` 脚本在受体中定义锌伪原子 (TZ)，占据锌离子的坐标位置。该步骤为后续生成亲和力图谱做准备。
- 命令：`~/ADFRsuite-1.0/bin/pythonsh zinc_pseudo.py -r protein.pdbqt -o protein_tz.pdbqt`

---

## 8. 配体预处理与结构优化

配体需先经 `scrub.py` 进行质子化和 UFF 力学优化，随后使用 `mk_prepare_ligand.py` 转换为 PDBQT 格式。此过程确保配体结构合理并符合对接输入要求。
- 命令：`scrub.py 1s63_ligand.sdf -o 1s63_ligandH.sdf`
- 命令：`mk_prepare_ligand.py -i 1s63_ligandH.sdf -o 1s63_ligand.pdbqt`

---

## 9. 金属对接 GPF 文件生成

使用 `prepare_gpf4zn.py` 生成网格参数文件 (GPF)，需指定配体、含 TZ 原子的受体、盒子中心及尺寸等参数。该脚本通过 AD4Zn.dat 参数文件处理锌相关的相互作用。
- 命令：`~/ADFRsuite-1.0/bin/pythonsh prepare_gpf4zn.py -l 1s63_ligand.pdbqt -r protein_tz.pdbqt -o protein_tz.gpf -p npts=40,30,50 -p gridcenter=18,134,-1 -p parameter_file=AD4Zn.dat`

---

## 10. 计算盒子实际尺寸

GPF 文件中的 `npts` 参数乘以默认间距 0.375 Å 即为对接盒子的实际边长。用户需根据计算结果确认盒子大小是否覆盖目标结合位点。
- 计算公式：边长 (Å) = npts × 0.375
- 示例：x=40, y=30, z=50 对应 15.0 Å × 11.25 Å × 18.75 Å

---

## 11. 生成亲和力图谱

运行 AutoGrid4 依据 GPF 文件计算能量图谱，生成一系列 .map 文件供 Vina 读取。这些图谱包含了包括锌原子位点在内的预计算相互作用能。
- 命令：`~/ADFRsuite-1.0/bin/autogrid4 -p protein_tz.gpf -l protein_tz.glg`

---

## 12. 执行锌金属对接

使用 Vina 进行对接时，需通过 `--scoring ad4` 指定使用 AutoDock4 打分函数，并利用 `--maps` 载入预生成的图谱。可调整详尽度、输出模式数及 CPU 数量以优化结果。
- 命令：`vina --ligand 1s63_ligand.pdbqt --maps protein_tz --scoring ad4 --exhaustiveness 32 --out 1s63_ligand_ad4_out.pdbqt`
- 常用参数：`--num_modes 20`、`--energy_range 5`、`--cpu 16`

---

## 13. AutoDock 原子支持范围

AutoDock 系列软件仅支持特定原子类型，包括 C, H, O, N, S, P 及卤素，以及部分金属如 Zn, Mg, Ca, Mn, Fe。若配体包含未支持的原子（如钾 K），可能在对接时引发报错，需考虑删除或替换。

---

## 14. 处理蛋白构象异构

受体 PDB 文件若包含占据度不为 1 的残基构象异构，需在预处理时指定保留的构象。未处理可能导致对接程序报错或结果不准确。
- 命令（保留所有 A 构象）：`mk_prepare_receptor.py -i 输入.pdb -o 输出 -p --default_altloc A`
- 命令（仅保留特定残基 A 构象）：`mk_prepare_receptor.py -i protein.pdb -o protein -p --wanted_altloc A:709=A`

---

## 15. 金属配合物加氢策略

含金属蛋白的加氢需考虑金属配位键的几何构型，推荐使用 ChimeraX 进行加氢操作。通过设置金属距离参数，可避免在金属配位原子上错误添加氢原子。
- 命令：`addh hbond true metalDist 3.95`

---

## 16. 小分子电荷与形式电荷处理

若小分子涉及特定电荷或复杂的质子化状态（如 DFT 优化结构），需明确设置形式电荷。Meeko 处理配体时要求显式氢原子且必须正确解析电荷，否则会报错。推荐使用 Avogadro 检查和调整形式电荷，确保 SDF/MOL2 文件包含正确的电荷信息。
- 报错提示：`RDKit molecule has implicit Hs. Need explicit Hs`

---

## 17. 检查与固定配体可旋转键

Meeko 转换配体时会自动识别可旋转键并构建扭转树，用户可通过 PDBQT 文件中的 BRANCH 和 TORSDOF 关键词检查旋转键数量。若需固定特定化学键（如酰胺键），可使用 SMARTS 模式指定固定原子。
- 检查命令：`grep -E "^(BRANCH|TORSDOF)" 文件名.pdbqt`
- 固定键命令：`mk_prepare_ligand.py -i 输入.sdf -o 输出_fixed.pdbqt --rigidify_bonds_smarts "[CX3](=O)[NX3]" --rigidify_bonds_indices 1 3`
