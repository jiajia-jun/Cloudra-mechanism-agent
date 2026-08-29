---
key: b440
title: 基于OpenBabel批量产生特定基团以任意方式接到苯上的结构的方法
url: http://sobereva.com/440
domain: 化学信息学与脚本
source: blog
year: 2018
cards: 5
---

# 基于OpenBabel批量产生特定基团以任意方式接到苯上的结构的方法 — 知识卡片

## 1. SMILES字符串定义与特点

SMILES是一种格式简单的描述分子结构的字符串，主要记录原子间的连接关系，在化学信息学中具有重要地位。大部分分子可以通过SMILES字符串描述，但复杂的笼状体系不太适合使用此格式。通常记录SMILES字符串的文件后缀为.smi。

---

## 2. OpenBabel软件功能与用途

OpenBabel是一款知名的化学文件格式转换程序，支持基于力场的几何优化、加氢/去氢、合并/拆分文件、相似性对比、结构排序/对齐等操作。该程序可以基于SMILES字符串通过CORINA算法快速、近似产生分子三维结构。OpenBabel生成的三维结构虽然粗糙，但适合作为几何优化的初猜结构。

---

## 3. 取代苯SMILES字符串生成代码原理

在了解SMILES字符串定义规则的前提下，可以通过编程代码生成特定基团以随机方式连接到苯环六个位点的SMILES字符串。代码中定义了8种取代基（CH3、H、CN、F、Cl、Br、I、OH）及其SMILES表示形式，通过随机数决定每个位点的取代基。程序循环生成指定数量的分子SMILES字符串，并输出到屏幕及当前目录下的subben.smi文件中。

---

## 4. OpenBabel批量生成三维结构命令

将生成的subben.smi文件置于当前目录，在命令行模式下输入obabel subben.smi -O out.pdb --gen3d -m，可批量生成三维结构文件。命令中的--gen3d参数代表自动产生三维结构，-m参数代表将文件中的多个分子拆分。执行后会在当前目录下生成out1.pdb、out2.pdb等一系列文件。

---

## 5. OpenBabel结合力场优化生成结构

若在生成三维结构的同时希望通过MMFF94高精度有机小分子力场进行优化，可运行命令obabel subben.smi -O out.pdb --gen3d -m --minimize --ff MMFF94。此命令生成的pdb文件中的结构均为经过力场优化后的构型。
