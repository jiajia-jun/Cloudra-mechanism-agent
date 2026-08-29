---
key: t18904
title: ʹ��MolAICal������Ӻϳɿ�����Ԥ�⡢��ҩ��ԭ���PAINS�Ľ̳�
url: http://bbs.keinsci.com/thread-18904-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 11
---

# ʹ��MolAICal������Ӻϳɿ�����Ԥ�⡢��ҩ��ԭ���PAINS�Ľ̳� — 知识卡片

## 1. MolAICal 简介

MolAICal 是用于药物合成可及性预测、Lipinski 规则五（类药性）和 PAINS 过滤的软件工具。相关教程和说明文档可通过官方主页、中文教程页面、Blogspot 以及发表在《Briefings in Bioinformatics》的文献获取。该软件主要用于药物化学领域的化合物性质评估与筛选。

---

## 2. Lipinski 规则五（RO5）概念

Lipinski 规则五（Rule of Five，RO5）是评估化合物是否具有类药性的一种方法，也被称为类药原规则。它主要用于判断化合物是否具备成为口服药物的潜在特性。

---

## 3. PAINS 概念与分类

PAINS 全称为 Pan Assay Interference Compounds，指在各类筛选实验中表现活跃的干扰化合物。此类化合物通常分为两类：第一类化合物在测试浓度下无法溶解，易产生聚集体或沉淀，导致无法与靶点真实结合，从而产生假阳性；第二类化合物能通过化学反应与蛋白质或其他成分形成共价键，表现出非特异性的干扰活性。在药物化学研究（如投稿至《Journal of Medicinal Chemistry》）中，必须对 PAINS 进行排查。

---

## 4. 合成可及性（SA）预测命令

MolAICal 支持通过 SMILES 字符串计算合成可及性（SA）值。计算单个 SMILES 的命令为 `molaical.exe -tool sa -i "SMILES字符串"`；计算文件中所有 SMILES 的命令为 `molaical.exe -tool sa -i SmilTest.smi`。SA 值越大，表示该化合物的合成难度越大。

---

## 5. 单个分子的 RO5 检测

MolAICal 可对单个分子文件进行 Lipinski 规则五检测。使用 mol2 格式文件进行检测的命令为 `molaical.exe -tool ruleoffive -f mol2 -n zinc_1879871.mol2`。

---

## 6. 批量 RO5 检测文件准备

批量处理 RO5 时，需先在当前目录生成包含文件名的列表文件。在 Linux 终端使用命令 `ls > mol2List.dat`，在 Windows DOS 终端使用命令 `dir /b > mol2List.dat`。生成的 mol2List.dat 文件中应仅保留待计算文件的名称。

---

## 7. 批量 RO5 检测执行

利用准备好的列表文件进行批量 RO5 检测的命令为 `molaical.exe -tool ruleoffive -f mol2list -i mol2List.dat -o result.dat`。计算结果将保存在 result.dat 文件中，包含各分子的 RO5 值及详细细节。

---

## 8. 单个分子的 PAINS 检测

MolAICal 支持对 SMILES 或 mol2 格式的单个分子进行 PAINS 检测。检测 SMILES 字符串的命令为 `molaical.exe -tool pains -f smi -n "c1ccccc1N=Nc1ccccc1"`；检测 mol2 文件的命令为 `molaical.exe -tool pains -f mol2 -n ZINC00154323.mol2`。

---

## 9. 批量 PAINS 检测（SMILES 格式）

批量进行 SMILES 格式 PAINS 检测的命令为 `molaical.exe -tool pains -f smilist -i painsTest.txt -o smiResult.txt`。

---

## 10. 批量 PAINS 检测（Mol2 格式）准备与执行

批量处理 mol2 格式的 PAINS 检测前，同样需要使用 `ls > mol2List.dat`（Linux）或 `dir /b > mol2List.dat`（Windows）生成文件名列表。执行检测的命令为 `molaical.exe -tool pains -f mol2list -i mol2List.dat -o mol2Result.txt`。结果将保存在 mol2Result.txt 文件中，包含各分子的 PAINS 信息。

---

## 11. PAINS 检测注意事项

在使用 MolAICal 进行 PAINS 筛选时，建议优先使用 SMILES 格式进行计算。
