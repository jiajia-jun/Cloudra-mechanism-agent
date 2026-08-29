---
key: t25776
title: ʹ��MolAICal ���з��ӶԽ�
url: http://bbs.keinsci.com/thread-25776-1-1.html
domain: 其他量化软件
source: keinsci
year: 2021
cards: 16
---

# ʹ��MolAICal ���з��ӶԽ� — 知识卡片

## 1. MolAICal 简介

MolAICal 是一款用于药物发现和对接研究的计算工具，提供了中文和英文教程及官方主页。相关文献介绍了该软件及其在分子对接方面的应用，例如使用 SARS-CoV-2 主蛋白酶(Mpro)作为靶点的对接案例。

---

## 2. MolAICal 与 Autodock Vina 的性能对比

在针对 SARS-CoV-2 Mpro 的 3130 个晶体结构复现实验中，MolAICal 的 Pearson 和 Spearman 相关系数分别为 0.5335 和 0.5489。这表明在同构对接测试中，MolAICal 的预测相关性优于 Autodock Vina。

---

## 3. 必要软件准备

进行本教程操作需要下载并安装 MolAICal 和 UCSF Chimera。MolAICal 可通过其官方主页或国内镜像站点获取，UCSF Chimera 可通过其官方网站下载。

---

## 4. 示例文件下载

本教程所需的示例文件（包括蛋白和配体文件）可从指定的 Gitee 仓库链接下载。

---

## 5. 准备受体蛋白文件

从 PDB 数据库下载 SARS-CoV-2 主蛋白酶结构（如 PDB ID: 6Y2F），使用 UCSF Chimera 的 File-->Open 功能打开。对蛋白结构进行必要处理后，将其保存为 `protein.pdb` 文件。

---

## 6. 准备配体文件

准备待对接的小分子配体结构，并在 UCSF Chimera 中进行相应处理。将处理后的配体结构保存为 `ligand.pdb` 文件。

---

## 7. 受体文件转换为 PDBQT 格式

使用命令行切换至 `protein.pdb` 所在目录，运行命令 `MolAICal-xxx\molaical.exe -dock receptor -i protein.pdb`。该操作将生成输出文件 `protein.pdbqt`。

---

## 8. 配体文件转换为 PDBQT 格式

使用命令行运行命令 `MolAICal-xxx\molaical.exe -dock ligand -i ligand.pdb`。该操作将生成输出文件 `ligand.pdbqt`。

---

## 9. 获取对接中心的质心坐标

在 UCSF Chimera 中同时打开 `protein.pdb` 和 `ligand.pdb`，通过 Favorites-->Command Line 打开命令行界面。输入命令 `define centroid mass false #1` 并按回车，记录显示的质心坐标（本例中为 x=10.879, y=-0.251, z=20.754）。

---

## 10. 确定对接盒子尺寸

通过 Tools-->Surface/Binding Analysis-->Autodock Vina 打开 AutoDock Vina 对接框设置工具。选择受体（`protein.pdb`）和配体（`ligand.pdb`），输入之前获取的质心坐标，并根据实际需要调整盒子尺寸。

---

## 11. 对接配置文件参数

创建配置文件 `conf.txt`，写入包含输出文件名、CPU 核数、受体文件名、对接中心坐标、盒子尺寸及构象数量等参数。例如设置 `center_x = 10.879`，`size_x = 20`，`num_modes = 3`，表示输出 3 个对接构象。

---

## 12. 执行分子对接

使用命令 `MolAICal-xxx\molaicald --config conf.txt --ligand ligand.pdbqt` 运行分子对接程序。若对接结果不理想，可通过指定 random seed（如 `--seed 555767984`）来重复对接并筛选结果。

---

## 13. 拆分对接结果文件

对接完成后，输出结果通常包含在 `all.pdbqt` 中。使用命令 `MolAICal-xxx\molaical.exe -tool pdbqt -i all.pdbqt -o ./` 将其拆分为独立的文件，如 `1.pdbqt`、`2.pdbqt` 和 `3.pdbqt`，其中 `1.pdbqt` 通常是得分最高的构象。

---

## 14. 结果文件格式转换与加氢

为便于在 UCSF Chimera 等软件中查看，需将 `pdbqt` 格式转换为 `pdb` 格式。首先执行 `MolAICal-xxx\molaical.exe -dock addh -i 1.pdbqt` 加氢，然后执行 `MolAICal-xxx\molaical.exe -dock pdbqt2pdb -i 1.pdbqt` 进行格式转换。

---

## 15. 对接结果可视化

在 UCSF Chimera 中打开受体蛋白 `protein.pdb` 和转换后的配体 `1.pdb` 等文件。通过 Favorites-->Model Panel 可以选择显示或隐藏特定的对接构象，以便观察和分析。

---

## 16. MM/GBSA 能量评估提示

对于得分最高的对接构象（如 `1.pdb`），建议使用 MM/GBSA 等分子力学方法进行结合自由能计算以评估稳定性。文中示例指出，原始晶体结构配体 N3 与 Mpro 的结合能计算值为 -84.70646297459386 kcal/mol。
