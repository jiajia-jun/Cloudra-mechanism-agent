---
key: t59389
title: Lys��Asp����������ͨ��pdb2gmx�Զ�����
url: http://bbs.keinsci.com/thread-59389-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2026
cards: 5
---

# Lys��Asp����������ͨ��pdb2gmx�Զ����� — 知识卡片

## 1. Lys-Asp 异构化交联结构参数获取

计算 Lys 和 Asp 形成异构化交联结构的准确参数可采用 JohnCase 提供的残基模板，对应的残基命名分别为 LYZ 和 ASZ。
- 这一组 RTP 文件和构型文件可直接获取使用。
- 参考：http://bbs.keinsci.com/thread-57309-1-1.html

---

## 2. 交联残基 RTP 文件生成方法

使用 Sobereva 提供的 ORCA 脚本生成 chg 文件后，结合 sobtop 工具可以生成 LYZ 和 ASZ 的 RTP 文件及相关执行文件。
- 该流程用于生成 GROMACS 所需的拓扑参数。
- 参考：http://原作者.com/637

---

## 3. GROMACS 特殊键定义修改

将 LYZ 和 ASZ 的 RTP 文件及相关文件放入 GROMACS 2025.03 版本使用的 AMBER19SB 力场目录中，需要修改 GROMACS 的 specbond.dat 文件。
- 添加的定义条目为：LYS NZ 1 ASP CG 1 0.15 LYZ ASZ。
- 此步骤旨在让程序识别特定的交联关系。

---

## 4. 交联结构构建流程

在 PyMOL 中构建好 Lys 和 Asp 的交联结构并保存为 PDB 文件后，使用 pdb2gmx 进行处理。
- 经过上述参数和配置修改后，pdb2gmx 能够自动生成交联结构的拓扑文件。
- 该过程实现了基于自定义残基的自动化拓扑生成。

---

## 5. 交联键参数识别与调整

在定义 LYS NZ 和 ASP CG 之间的特殊键时，原始默认的键长参数为 0.18 nm，但这会导致成键失败，无法识别原始原子对。
- 将该参数数值调整为 0.15 nm 后，程序能够正确识别并形成交联键。
- 1.34 为该交联键在特定情况下的参考数值（可能是实际键长或另一临界值）。
