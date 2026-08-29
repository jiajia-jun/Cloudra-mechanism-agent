---
key: t54981
title: Multiwfn��֧�ֻ���ORCA����CCSD(T)��CCSDT�ȸ߼���Ĳ�����
url: http://bbs.keinsci.com/thread-54981-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2025
cards: 3
---

# Multiwfn��֧�ֻ���ORCA����CCSD(T)��CCSDT�ȸ߼���Ĳ����� — 知识卡片

## 1. Multiwfn 处理 MRCC 和 PSI4 轨道的波函数分析功能

Multiwfn 支持直接读取 MRCC 和 PSI4 程序产生的波函数文件，以进行 CCSD 及更高级别后自洽场（post-SCF）计算的分析。该功能也可用于基于这些波函数进行更高精度的 CCSD 计算。

---

## 2. ORCA 6.1 版本的高级相关方法支持

ORCA 6.1 版本引入的 AUTOCI 模块已经支持包括 CCSD(T)、CCSDT 和 MP5 在内的许多高阶方法。这些方法计算量较大，适合对体系进行高精度的密度分析。

---

## 3. Multiwfn 对 ORCA 输出文件的密度矩阵读取与转换

Multiwfn 已支持通过 orca_2json 工具生成的 JSON 文件读取 ORCA 输出的密度矩阵。该功能可以将 ORCA 计算的高阶方法（如 CCSD(T)）产生的密度矩阵转换为 Multiwfn 可识别的格式，便于后续进行各种波函数分析。相关功能介绍见于 Multiwfn 手册的 4.A.8 节。
