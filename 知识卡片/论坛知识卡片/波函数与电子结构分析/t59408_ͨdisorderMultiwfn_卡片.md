---
key: t59408
title: ͨ��disorder��Multiwfn����ʵ������Ԫ�ز���/��λ������ת���������ļ�
url: http://bbs.keinsci.com/thread-59408-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2026
cards: 10
---

# ͨ��disorder��Multiwfn����ʵ������Ԫ�ز���/��λ������ת���������ļ� — 知识卡片

## 1. disorder 软件功能概述

disorder 是一款开源软件，专门用于生成无序占位结构以研究掺杂体系。该软件通常与 Multiwfn 配合使用，进行结构文件格式转换，生成的结构可通过 CP2K 进行计算。处理无序体系时，相比于不切实际的手动建模，利用 disorder 建模能更好地保持体系的对称性和准确性。

---

## 2. disorder 软件安装方法

disorder 可在 Ubuntu 24.04 系统下通过 GitHub 源码安装。安装过程包括使用 git clone 命令下载源码、进入 bin 目录赋予执行权限，并将可执行文件路径添加至环境变量中。添加环境变量后需执行 source ~/.bashrc 使配置生效。

---

## 3. disorder 安装命令与配置

通过终端执行以下命令完成下载与权限设置：`git clone https://github.com/jichunlian/disorder.git`、`cd ~/disorder/bin`、`chmod +x disorder`。环境变量配置需编辑 `~/.bashrc` 文件，添加 `export PATH=/home/mila/disorder/bin/:${PATH}` (注意修改实际路径)，并运行 `source ~/.bashrc`。

---

## 4. disorder 安装验证

在终端输入 `disorder` 命令，若屏幕显示软件的 ASCII Logo 图形，即表示安装成功。该操作用于确认可执行文件已正确添加到系统路径中。

---

## 5. disorder 输入文件准备

disorder 运行需要两个核心文件：INDSOD 和 SPOSCAR。INDSOD 相当于 VASP 的 INCAR 文件，用于设置掺杂参数；SPOSCAR 是掺杂/空位前的结构文件，相当于 VASP 的 POSCAR 文件。在 Windows 系统编写这两个文件后需上传至 Linux 环境进行处理。

---

## 6. disorder 运行示例与输出

运行 `disorder` 命令后，程序会读取 INDSOD 和 SPOSCAR，显示原子种类与数量，并基于群论寻找不可约配置。程序最终会生成一个名为 `poscar` 的目录，其中包含筛选出的不可约结构文件（如 POSCAR-1 至 POSCAR-9）。

---

## 7. POSCAR 批量转 CIF 脚本

利用脚本 `POSCAR_to_cif.sh` 可批量将 disorder 生成的 POSCAR 文件转换为 CIF 格式。该脚本通过循环遍历当前目录下的 POSCAR-* 文件，调用 Multiwfn 的无 GUI 模式执行格式转换，最终生成同名的 .cif 文件。

---

## 8. 批量转换脚本执行步骤

首先需赋予转换脚本执行权限：`chmod +x POSCAR_to_cif.sh`。然后执行脚本：`./POSCAR_to_cif.sh`，脚本会依次显示转换进度（如 "Converting POSCAR-1 to POSCAR-1.cif ..."），直到处理完所有 9 个文件。

---

## 9. INDSOD 文件参数示例

INDSOD 文件定义了掺杂的具体细节，关键参数包括：`nsub = 2` 表示取代原子和被取代原子种类数之和为 2；`subs = 26,1` 表示在 27 个 Ti 位点中，26 个由 Ti 占据，1 个由掺杂原子占据；`symb = 'Ti','Sc'` 定义了取代原子和被取代原子的元素符号；`site = 2` 指定 SPOSCAR 中 Ti 位于第二位。

---

## 10. SPOSCAR 文件内容示例

SPOSCAR 文件记录了初始晶胞的结构信息，包含晶系名称、缩放因子（1.0）、晶格向量（如 11.8353996277 等）、元素种类（Sr Ti O）、原子数量（18 27 72）以及分数坐标格式的原子位置列表。该文件作为 disorder 生成掺杂结构的几何基础。
