---
id: 22
title: gromacs和amber处理环肽的办法
url: http://sobereva.com/22
domain: 分子动力学与力场
topic: GROMACS与AMBER环肽模拟端基处理
cards: 4
---

# GROMACS与AMBER环肽模拟端基处理 — 知识卡片

## 1. AMBER环肽模拟的残基处理

AMBER模拟环肽时需避免将PDB首尾氨基酸识别为N端或C端残基，因为这两种端基残基与中段残基的原子组成、原子类型和电荷均不同。使用loadpdbusingseq命令可按指定序列读取PDB文件，强制程序将所有残基按照普通中段氨基酸残基来处理，从而避免端基自动加氢或加氧的问题。
- 操作步骤示例：
  temp={ARG ARG TYR TYR ALA PHR}
  b=loadpdbusingseq /sob/t/cycli/cycli.pdb temp
  bond b.1.N b.6.C

---

## 2. GROMACS环肽模拟的端基设置

GROMACS通过力场目录下的tdb文件（如ffG43a1p-n.tdb和ffG43a1p-c.tdb）定义端基氨基和羧基的处理方式。为了防止pdb2gmx给环肽首尾残基添加多余原子或修改原子类型，在运行pdb2gmx时应使用-ter选项，手动将N端和C端氨基酸的处理方式均选为none，即保持原样不做改动。

---

## 3. GROMACS环肽端基肽键补氢方法

若环肽PDB无氢或开启了-ignh选项且端基选择了none，导致头尾相连的肽键缺失氢原子，需修改力场tdb文件（如ffG43a1p-n.tdb）添加自定义补氢规则。添加的内容包括[cycliN]定义项和[add]操作项，指定添加氢原子H连接在N上，并设置其质量为1.008、电荷为0.28（该电荷值对所有氨基酸通用）。
- 需添加的配置内容：
  [cycliN]
  [add]
  1 4 H N CA C
  H 1.008 0.28

---

## 4. GROMACS环肽成键后处理

在GROMACS中完成环肽PDB处理和端基设置后，必须在生成的.top文件中手动补全连接首尾氨基酸肽键所需的bond、angle和dihedral信息，以确保环肽结构的拓扑参数完整。
