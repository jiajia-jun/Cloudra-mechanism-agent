---
id: 637
title: ORCA结合Multiwfn计算RESP、RESP2和1.2*CM5原子电荷的懒人脚本
url: http://sobereva.com/637
domain: 化学信息学与脚本
topic: ORCA结合Multiwfn计算RESP与CM5电荷脚本
cards: 6
---

# ORCA结合Multiwfn计算RESP与CM5电荷脚本 — 知识卡片

## 1. ORCA结合Multiwfn计算原子电荷的脚本

作者提供了Linux shell脚本用于自动调用ORCA和Multiwfn程序，实现一键计算RESP、RESP2和1.2*CM5原子电荷。这些脚本包含在2022年3月8日及以后更新的Multiwfn程序文件包中，路径分别为examples\RESP\RESP_ORCA.sh、examples\RESP\RESP2_ORCA.sh和examples\scripts\1.2CM5_ORCA.sh。脚本主要服务于使用ORCA程序且未购买Gaussian的用户，便于进行经典力场分子动力学模拟所需的电荷计算。

---

## 2. 脚本路径与参数设置

运行脚本前需用文本编辑器打开，将ORCA=和orca_2mkl=后的内容修改为当前机器上ORCA和orca_2mkl工具的实际路径。用户需将nprocs=后的值改为计算时调用的CPU核心数，并将maxcore=后的值（每个并行进程的内存使用量MB上限）与nprocs的乘积设定为明显小于空余物理内存量。计算几百个原子的大体系需适度加大maxcore，内存不足则需减小maxcore或nprocs。

---

## 3. RESP脚本的优化级别差异

RESP_ORCA.sh和RESP2_ORCA.sh脚本默认使用ORCA支持的B97-3c级别进行结构优化，以兼顾速度和准确度。由于ORCA与Gaussian在溶剂模型实现上的差异，且优化级别与基于Gaussian的脚本不同，计算得到的RESP或RESP2电荷数值可能有零点零几的差别。这种微小差异属于合理范围，无需在意。

---

## 4. 溶剂名称书写规则

使用脚本时需参照ORCA手册中“solvents in the SMD library”列表来书写溶剂名称。若ORCA内置的溶剂名包含空格，必须用双引号将溶剂名括住，例如在计算乙酸乙酯溶剂时需写为./RESP2_ORCA.sh HF.pdb 0 1 "ETHYL ETHANOATE"。

---

## 5. 跳过结构优化的脚本版本

若输入结构文件中的结构已经足够好且无需再次优化，可分别使用examples\RESP\目录下的RESP_ORCA_noopt.sh和RESP2_ORCA_noopt.sh脚本。这两个脚本的用法与标准版本完全一致，但省略了结构优化步骤以节省时间。

---

## 6. 引用规范与术语准确性

使用这些脚本计算原子电荷发表文章时，必须在文中恰当引用Multiwfn，具体引用方式见《Multiwfn FAQ》。在提问或描述情况时，应明确表述为“使用本文提供的脚本，用Multiwfn基于ORCA产生的波函数计算RESP或RESP2电荷”，严禁表述为“ORCA计算了RESP电荷”，因为ORCA程序本身不具备计算RESP电荷的功能。
