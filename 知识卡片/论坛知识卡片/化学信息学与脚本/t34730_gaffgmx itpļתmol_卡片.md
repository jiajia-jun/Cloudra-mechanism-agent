---
key: t34730
title: gaff����gmx itp�ļ�ת��moltemplate lt�ļ���С�ű�
url: http://bbs.keinsci.com/thread-34730-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2023
cards: 4
---

# gaff����gmx itp�ļ�ת��moltemplate lt�ļ���С�ű� — 知识卡片

## 1. LAMMPS 与 GROMACS 的功能差异

LAMMPS 的功能比 GROMACS 强大，部分特殊需求或复杂计算场景需要使用 LAMMPS 完成。

---

## 2. 脚本功能概述

提供的脚本能够将由 sobtop 生成的 GAFF 力场 ITP 文件转换为 moltemplate 所需的 LT 文件，便于构建模拟系统。

---

## 3. 脚本修改与调整依据

使用脚本前需要修改源 ITP 文件中的原子名称、原子直径以及键合参数（如键长、键角、二面角等），以确保参数符合具体的分子体系要求。

---

## 4. 脚本执行命令

脚本的执行命令格式为 `moltemplate.sh -atomstyle full -pdb file.pdb system.lt`，其中 `file.pdb` 为体系的 PDB 文件。
