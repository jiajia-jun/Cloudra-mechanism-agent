---
key: t14099
title: Gaussian�и��ӵ���ѡ��UnConAO
url: http://bbs.keinsci.com/thread-14099-1-1.html
domain: Gaussian使用
source: keinsci
year: 2019
cards: 7
---

# Gaussian�и��ӵ���ѡ��UnConAO — 知识卡片

## 1. 广义收缩基组的计算效率

广义收缩基组在Gaussian、Gamess、Orca等程序中的计算效率通常较低。以Molpro和Molcas中计算HF/ANO-RCC-VDZ基组下At2体系的单点能为例，计算时间可能从几小时延长至数天。相比之下，分段收缩基组的计算速度更快，常将耗时从数天缩短至数小时。

---

## 2. 分段收缩基组类型与特点

Turbomole和Orca程序广泛使用分段收缩基组，如def-、def2-、sarc-及x2c-系列。这类基组将内层电子（如1s、2p、3d）单独划分为一组，通常每组包含少于10个基函数。对于含重元素的体系，分段收缩基组在保证较高计算精度的同时，能显著提升计算效率，尽管仍可能比Pople型基组慢。

---

## 3. Gaussian中使用广义收缩基组的方法

在Gaussian程序中使用广义收缩基组，通常有两种方法：一是将基组编辑为分段收缩格式后通过gen关键字输入；二是使用`Int(UnConAO)`关键字直接读取原始基组。`Int(UnConAO)`既可以直接在输入文件中使用，也可以配合gen关键字使用，但在使用过程中可能存在一些问题。

---

## 4. Gaussian09中UnConAO的缺陷

在Gaussian09等较早版本中，`Int(UnConAO)`关键字不支持Pople型基组。当处理广义收缩基组时，即使未显式指定高斯函数，`UnConAO`有时会错误地保留未删除的高斯函数。此外，该功能在处理某些复杂基组时可能出现未知的错误。

---

## 5. Gaussian16中UnConAO的改进

Gaussian16修复了Gaussian09中`Int(UnConAO`）的许多错误，能够保证广义收缩基组积分计算的正确性。尽管程序在内存和磁盘存储方面的优化尚不完善，导致计算仍显笨重，但其功能已明显改进。

---

## 6. Gaussian16计算重元素基组的实测效率

在Gaussian16中使用`Int(UnConAO)`计算HF/ANO-RCC-VDZ基组下的At2体系，测试结果显示相较于旧版本有明显改进。通过`ghf/gen int=dkhso`等关键词调用DKH4相对论计算时，程序能自动检测并关闭对称性以完成计算。

---

## 7. 不同基组输入方式的耗时对比

针对同一计算任务，不同输入方式的耗时存在显著差异：使用`gen`输入分段收缩基组耗时约1小时；使用`gen`输入广义收缩基组配合`UnConAO`耗时约4小时，且需注意防止程序无响应；若仅使用`gen`输入广义收缩基组而不使用`UnConAO`，耗时则长达3天。
