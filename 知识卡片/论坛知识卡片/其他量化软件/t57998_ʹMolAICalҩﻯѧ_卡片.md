---
key: t57998
title: ʹ��MolAICal����ҩ�ﻯѧ������MCFs��MCE-18������
url: http://bbs.keinsci.com/thread-57998-1-1.html
domain: 其他量化软件
source: keinsci
year: 2026
cards: 19
---

# ʹ��MolAICal����ҩ�ﻯѧ������MCFs��MCE-18������ — 知识卡片

## 1. MCFs 与 PAINS 定义及功能

MCFs（Medicinal Chemistry Filters，药物化学过滤器）用于药物化学数据分析，可消除非药性结构或显示结构警示，以便进行结构元素过滤或化学空间限定。PAINS（Pan-Assay Interference Compounds，泛干扰化合物）指易产生假阳性或表现出非特异性反应的化合物结构，常包含反应活性片段（如迈克尔受体、亲电试剂）。MolAICal 软件集成了 MCFs 功能，并支持涉及 MCFs 与 PAINS 的相关结构检测。

---

## 2. MCE-18 描述符定义与来源

MCE-18 是基于药物化学数据集（2018年）提出的原子级描述符，用于描述原子的化学环境，能有效预测化合物的类药性和药效团特征。该描述符涉及多种结构参数，具体计算公式由 MolAICal 软件实现。

---

## 3. MCE-18 描述符参数含义

MCE-18 涉及的具体参数包括：AR（芳香环是否存在，0=无，1=有）、NAR（脂环是否存在，0=无，1=有）、CHIRAL（手性是否存在，0=无，1=有）、SPIRO（螺原子是否存在，0=无，1=有）、sp³（sp³ 杂化碳原子比例，范围 0-1）、Cyc（sp³ 杂化的环状碳原子比例，范围 0-1）、Acyc（sp³ 杂化的非环状碳原子比例，范围 0-1）、NCSPTR（参数值，计算公式为 sp³ + Cyc - Acyc）以及 Q¹（描述结构复杂程度的指标）。

---

## 4. MolAICal 软件资源链接

MolAICal 的官方主页和下载地址分别为 https://molaical.github.io 和 https://molaical.gitlab.io。相关的教程文件和示例数据（如 024-mcf_mce18）可从 Gitee 仓库获取。

---

## 5. MolAICal 计算单个分子 MCFs 命令

使用 MolAICal 计算单个 SMILES 字符串的 MCFs，命令格式为 `molaical.exe -tool mcf -s "SMILES字符串"`。例如计算阿司匹林的命令为：`molaical.exe -tool mcf -s "CC(=O)OC1=CC=CC=C1C(=O)O"`。

---

## 6. MolAICal 计算分子 MCFs 并关闭属性显示

若需计算单个 SMILES 字符串的 MCFs 但不显示属性细节，可使用 `-p false` 参数。命令示例：`molaical.exe -tool mcf -s "CC(=O)OC1=CC=CC=C1C(=O)O" -p false`。

---

## 7. MolAICal 输出 MCFs 为指定格式文件

将单个分子的 MCFs 计算结果输出为指定格式（如 text、json 或 csv），需使用 `-o` 和 `-f` 参数。命令示例（输出为 CSV）：`molaical.exe -tool mcf -s "CC(=O)OC1=CC=CC=C1C(=O)O" -o result.csv -f csv`。

---

## 8. MolAICal 输出 MCFs 文件并关闭属性显示

将 MCFs 结果输出为指定文件格式且不显示属性，需组合使用 `-o`、`-f` 和 `-p false` 参数。命令示例：`molaical.exe -tool mcf -s "CC(=O)OC1=CC=CC=C1C(=O)O" -o result.csv -f csv -p false`。

---

## 9. MolAICal MCFs 输出字段含义

MCFs 计算结果默认包含多个字段：SMILES（输入的 SMILES 字符串）、Valid（结构是否有效）、Passes filters（是否通过 MCFs 过滤）、LogP（脂水分配系数）、SA Score（合成可及性评分，1-10，值越小越易合成）、NP Score（类天然产物评分）、QED（类药性指数，范围 [0,1]）以及 Molecular weight（分子量）。

---

## 10. MolAICal 批量计算文件中分子的 MCFs

对包含多个 SMILES 字符串的文件（每行一个）进行批量 MCFs 计算，使用 `-i` 指定输入文件，`-o` 和 `-f` 指定输出。命令示例：`molaical.exe -tool mcf -i molecules.smi -o result.csv -f csv`。

---

## 11. MolAICal 批量计算 MCFs 并关闭属性

批量计算文件中分子的 MCFs 且不显示属性，需在批量计算命令基础上添加 `-p false` 参数。命令示例：`molaical.exe -tool mcf -i molecules.smi -o result.csv -f csv -p false`。

---

## 12. MolAICal 计算单个分子 MCE-18 命令

使用 MolAICal 计算单个 SMILES 字符串的 MCE-18 描述符，命令格式为 `molaical.exe -tool mce18 -s "SMILES字符串"`。示例命令：`molaical.exe -tool mce18 -s "CC(=O)OC1=CC=CC=C1C(=O)O"`。

---

## 13. MolAICal 获取单个分子 MCE-18 值

若需仅获取单个 SMILES 对应的 MCE-18 数值，需添加 `-sm true` 参数。命令示例：`molaical.exe -tool mce18 -s "CC(=O)OC1=CC=CC=C1C(=O)O" -sm true`。

---

## 14. MolAICal 输出单个分子 MCE-18 到 CSV 文件

将单个 SMILES 的 MCE-18 计算结果输出为 CSV 文件，使用 `-o` 参数指定输出文件。命令示例：`molaical.exe -tool mce18 -s "CC(=O)OC1=CC=CC=C1C(=O)O" -o output.csv`。

---

## 15. MolAICal 输出 MCE-18 详细数据到 CSV

输出单个分子 MCE-18 到 CSV 文件并包含详细数据，需组合使用 `-o` 和 `-q true` 参数。命令示例：`molaical.exe -tool mce18 -s "CC(=O)OC1=CC=CC=C1C(=O)O" -o output.csv -q true`。

---

## 16. MolAICal 输出 MCE-18 值与 SMILES 到 CSV

将单个 SMILES 及其 MCE-18 值输出到 CSV 文件，需组合使用 `-o` 和 `-sm true` 参数。命令示例：`molaical.exe -tool mce18 -s "CC(=O)OC1=CC=CC=C1C(=O)O" -o output.csv -sm true`。

---

## 17. MolAICal 批量计算 MCE-18 并输出 CSV

对包含多个 SMILES 的文件进行批量 MCE-18 计算并输出为 CSV 文件，使用 `-i` 指定输入文件。命令示例：`molaical.exe -tool mce18 -i molecules.smi -o results.csv`。

---

## 18. MolAICal 批量计算 MCE-18 值并输出 CSV

批量计算文件中 SMILES 的 MCE-18 值并输出结果到 CSV，需在批量计算命令中添加 `-sm true`。命令示例：`molaical.exe -tool mce18 -i molecules.smi -o results.csv -sm true`。

---

## 19. MCE-18 数值范围与化学性质解读

在实际应用中，MCE-18 的数值范围通常在 45-78 之间。数值小于 45 提示分子结构简单、类药性低，可能无法通过药效团匹配；数值在 45-78 之间提示类药性足够，符合当前药物化学标准（45-63 为常见药物结构，63-78 为药企专利结构）；数值大于 78 提示可能存在反应活性基团或非药物性质，复杂度较高。
