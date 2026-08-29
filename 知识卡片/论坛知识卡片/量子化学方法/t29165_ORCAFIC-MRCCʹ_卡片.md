---
key: t29165
title: ORCA��FIC-MRCCʹ������
url: http://bbs.keinsci.com/thread-29165-1-1.html
domain: 量子化学方法
source: keinsci
year: 2022
cards: 7
---

# ORCA��FIC-MRCCʹ������ — 知识卡片

## 1. PBE0/aug-pcseg-2 结构优化与单点计算方法

针对某体系的构型优化和几何结构计算，采用 PBE0/aug-pcseg-2 方法。在计算单点能及电子态时，使用 UKS 处理开壳层体系及对称性破缺问题。

---

## 2. FIC 系列高精度方法的近似类型

FIC-MRCC、FIC-MRCI 和 FIC-NEVPT2 方法类似于 RI 和 DLPNO 近似。FIC-CASPT2 方法类似于 RI 近似。SORCI 和 CASSCF 也被提及于参考方法中。

---

## 3. 参考态与基组的设置

参考态计算涉及自旋翻转，相关数据选取自旋态 2 和 2。所有计算均使用 cc-pVTZ 基组。

---

## 4. DFT 方法列表与态设置

DFT 方法计算激发态时使用 UKS。涉及的泛函包括 B2PLYP、PWPB95、PBE0、M06-2X、wB97M-V、BLYP、PBE 和 MN15L。

---

## 5. 高精度波函数方法列表

涉及的波函数方法包括 QCISD(TQ)、CCSD(T)、CCSD、MP2、DLPNO-CCSD(T) 和 DLPNO-CCSD。参考态采用 UHF 开壳层。

---

## 6. ORCA 与 Gaussian 软件的方法支持情况

QCISD(TQ) 方法除 Gaussian 外主要由 ORCA 支持。涉及 QCISD(TQ) 的数据均使用 ORCA 5 进行计算。

---

## 7. 计算误差与精度对比

以 FIC-MRCC 为基准值，各计算方法的误差按数值大小顺序排列。由于仅针对一个化学反应应用，误差偶然性较大，所得结果仅具有限参考价值。
