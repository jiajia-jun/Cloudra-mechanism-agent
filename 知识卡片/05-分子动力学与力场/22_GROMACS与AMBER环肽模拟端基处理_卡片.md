---
id: 22
title: gromacs和amber处理环肽的办法
url: http://sobereva.com/22
domain: 分子动力学与力场
topic: GROMACS与AMBER环肽模拟端基处理
cards: 1
---

# GROMACS与AMBER环肽模拟端基处理 — 知识卡片

## 1. AMBER环肽模拟的残基处理原理

环肽模拟需将首尾氨基酸视为普通中段氨基酸，避免程序将其当作N端或C端残基进行特殊加氢或加氧处理。AMBER库中N打头残基比普通残基多氨基氢，C打头残基多羧基氧，原子类型和电荷也不同，需特殊指令防止错误修改。

## AMBER使用loadpdbusingseq读取环肽
在AMBER的leap中，使用loadpdbusingseq命令读取环肽pdb文件，使每个残基都按照所设序列为参照来读取，从而避免首尾残基被错误识别。示例命令为：temp={ARG ARG TYR TYR ALA PHR} 和 b=loadpdbusingseq /sob/t/cycli/cycli.pdb temp。

## AMBER中构建环肽首尾肽键
在AMBER中完成环肽PDB读取后，需使用bond命令手动将首尾氨基酸连接成肽键以闭环。具体命令为：bond b.1.N b.6.C，即将pdb开头的氨基酸和pdb末尾的氨基酸相连，之后按常规方法添加电荷和溶剂。

## GROMACS环肽端基处理原理
GROMACS通过力场目录下的tdb文件（如ffG43a1p-n.tdb和ffG43a1p-c.tdb）定义端基氨基和羧基的处理方式，如删除、添加或替换原子。默认使用[NH3+]和[COO-]，模拟环肽时需阻止程序对首尾添加多余基团。

## GROMACS使用-ter选项处理环肽端基
在GROMACS中使用pdb2gmx处理环肽时，加上-ter选项手动指定端基处理方式，将N端和C端氨基酸都选为none。这样程序就不会给环肽pdb开头和结尾的氨基酸添上多余的东西。

## GROMACS修改tdb文件为环肽加氢
若pdb2gmx时选none导致头尾肽键缺失氢，需修改力场文件（如ffG43a1p-n.tdb）添加[cycliN]定义。具体添加内容为：[cycliN]、[add]、1 4 H N CA C、H 1.008 0.28，这样在pdb2gmx时选择cycliN项即可为肽键加上氢。

## GROMACS中环肽氢原子电荷规则
GROMACS中不同氨基酸的肽键上的氢的电荷都是0.28，因此修改tdb文件添加氢时，设置电荷为0.28对所有氨基酸通用，不会造成体系总电荷不为整数。

## GROMACS中补全环肽拓扑参数
在GROMACS中通过修改tdb文件为环肽添加氢后，需手动在.top文件中补上这个肽键的bond、angle、dihedral的信息，以完成环肽的拓扑参数定义。
