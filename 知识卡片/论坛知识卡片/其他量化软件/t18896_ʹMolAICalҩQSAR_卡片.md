---
key: t18896
title: ʹ��MolAICal����ҩ���QSAR����
url: http://bbs.keinsci.com/thread-18896-1-1.html
domain: 其他量化软件
source: keinsci
year: 2020
cards: 13
---

# ʹ��MolAICal����ҩ���QSAR���� — 知识卡片

## 1. MolAICal 药物 QSAR 教程资源

MolAICal 官方主页网址为 https://molaical.github.io，其软件介绍论文 DOI 为 10.1093/bib/bbaa161。软件的中文教程页面位于 https://molaical.github.io/cntutorial.html，相关博客信息可在 https://qblab.blogspot.com 获取。教程以 STAT3 抑制剂为例，演示了如何利用 MolAICal 进行定量构效关系 (QSAR) 研究。

---

## 2. QSAR 研究背景

定量构效关系 (QSAR) 是一种通过回归分析和分类方法研究药物结构与活性关系的手段。STAT3 是肿瘤抑制中的重要靶点，本教程以 STAT3 抑制剂为研究对象，旨在通过 QSAR 方法预测药物活性并辅助靶点药物设计。

---

## 3. DRAGON 软件使用限制

DRAGON 是用于计算药物分子描述符的软件之一，但其使用存在版权限制。商业用途需获取商业许可，且该软件禁止在任何学术研究中使用任何非商业许可版本的计算结果。

---

## 4. 教程文件下载地址

本教程相关的示例文件和资源存储在 GitHub 仓库中。获取路径为 https://github.com/MolAICal/tutorials/tree/master/006-QSAR。

---

## 5. 输入分子文件格式要求

使用 DRAGON 进行分子描述符计算时，输入分子文件需放置在 006-QSAR/ligands 目录下。本教程使用的输入文件格式为 .hin，这是 HyperChem 几何优化后的默认文件格式。若使用其他软件，需将分子进行几何优化并保存为 Sybyl Mol2 格式文件以供后续处理。

---

## 6. 药物分子数据来源

药物分子的结构数据可从公共数据库中获取，例如 IUPHAR/BPS Guide to PHARMACOLOGY 数据库 (www.guidetopharmacology.org/)。

---

## 7. 分子描述符计算结果保存

将计算得到的药物分子描述符结果进行保存，并重命名为 QSARMolDes.txt 文件。该文件将作为后续 QSAR 模型构建的输入数据。

---

## 8. QSAR 模型训练集与测试集设置

使用 Excel 打开 QSARMolDes.txt 文件，可对数据集进行划分和参数设置。数据需按特定格式排列：第一列为标签，第二列第一个单元格输入 "on" 指定自定义的训练集和测试集划分。在第二列对应位置标记 "1" 表示该样本为训练集，标记 "2" 表示测试集。

---

## 9. QSAR 模型留一法验证设置

如果在 QSARMolDes.txt 文件的第二列第一个单元格输入 "off"，则不进行自定义划分，MolAICal 将默认使用留一法 (LOO) 进行交叉验证。在 LOO 模式下，训练集和测试集的划分列可省略，参考示例文件名为 QSARMolDes_LOO.txt。

---

## 10. 实验值数据列设置

在 Excel 中整理 QSAR 数据时，分子的实验值 (如 pKd) 必须包含在数据列中。确保实验值与对应的分子描述符数据正确对齐，如图 3 所示。

---

## 11. MolAICal 运行 QSAR 命令

在命令行中执行以下命令可运行 QSAR 计算：`molaical.exe -qsar GA -i QSARMolDes.txt`。若使用留一法验证的文件，命令为：`molaical.exe -qsar GA -i QSARMolDes_LOO.txt`。

---

## 12. QSAR 计算过程控制

教程设置运行 10 代 (population) 进行演示。如果 Q2 评价指标已达到研究目标，可通过键盘快捷键 Ctrl + C 提前终止 MolAICal 程序的运行。

---

## 13. QSAR 计算结果输出

MolAICal 运行结束后，计算结果将保存在 QSAROutFile.dat 文件中。该文件包含生成的 QSAR 模型信息及相关详细数据。
