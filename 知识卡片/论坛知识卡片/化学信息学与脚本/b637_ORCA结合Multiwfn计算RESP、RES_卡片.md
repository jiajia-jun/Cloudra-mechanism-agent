---
key: b637
title: ORCA结合Multiwfn计算RESP、RESP2和1.2*CM5原子电荷的懒人脚本
url: http://sobereva.com/637
domain: 化学信息学与脚本
source: blog
year: 2022
cards: 6
---

# ORCA结合Multiwfn计算RESP、RESP2和1.2*CM5原子电荷的懒人脚本 — 知识卡片

## 1. ORCA结合Multiwfn计算原子电荷的Linux脚本

Multiwfn程序文件包自2022年3月8日及以后的版本中包含了三个Linux shell脚本，用于自动调用ORCA和Multiwfn程序计算RESP、RESP2和1.2*CM5原子电荷。这些脚资料件分别为examples\RESP\RESP_ORCA.sh、examples\RESP\RESP2_ORCA.sh和examples\scripts\1.2CM5_ORCA.sh。这些脚本旨在方便未购买Gaussian但使用ORCA程序的用户进行经典力场分子动力学模拟所需的原子电荷计算。

---

## 2. 脚本运行前的路径与参数配置

在运行脚本之前，需使用文本编辑器打开脚资料件并将ORCA=和orca_2mkl=后的内容修改为当前机器中ORCA和orca_2mkl工具的实际路径。脚本中的nprocs=参数值需要设定为计算时调用的CPU核心数，maxcore=参数值定义了ORCA每个并行进程的内存使用量上限（单位为MB）。maxcore与nprocs的乘积必须明显小于空余物理内存量，默认值一般适用，若内存不足需减小该值，计算大体系时需适当增大。

---

## 3. ORCA脚本与Gaussian脚本的差异

RESP_ORCA.sh和RESP2_ORCA.sh脚本默认使用ORCA支持的B97-3c级别进行几何优化，该级别优化速度快且准确度较好。由于ORCA与Gaussian在溶剂模型实现上的差异以及优化级别的不同，基于ORCA和基于Gaussian的脚本计算得到的RESP或RESP2电荷值可能存在零点零几以内的偏差，这些偏差属于合理范围。

---

## 4. 脚本中溶剂名的书写规范

使用脚本时需查阅ORCA手册中关于“solvents in the SMD library”的列表来确定可直接使用的溶剂名称。如果ORCA中的溶剂名称包含空格，则在输入时必须用双引号将溶剂名括起来，例如在运行RESP2_ORCA.sh时输入“ETHYL ETHANOATE”。

---

## 5. 跳过几何优化的脚本版本

如果输入的结构文件中的结构已经足够好，不需要脚本自动进行几何优化以节省时间，可以使用examples\RESP\目录下的RESP_ORCA_noopt.sh和RESP2_ORCA_noopt.sh脚本。这两个脚本的用法与RESP_ORCA.sh和RESP2_ORCA.sh完全一致，唯一的区别是带_noopt后缀的脚本不包含优化步骤。

---

## 6. 脚本使用时的引用与术语规范

使用这些脚本计算原子电荷并发表文章时，必须在文中恰当引用Multiwfn，具体的引用方式详见《Multiwfn FAQ》。在网上提问或描述情况时，应明确表述为“使用提供的脚本，用Multiwfn基于ORCA产生的波函数计算RESP或RESP2电荷”，因为ORCA程序自身不具备计算RESP电荷的功能。
