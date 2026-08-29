---
key: t14038
title: Gaussian 16 C.01�ѷ���
url: http://bbs.keinsci.com/thread-14038-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2019
cards: 7
---

# Gaussian 16 C.01�ѷ��� — 知识卡片

## 1. Gaussian 16 C.01 版本更新概览

Gaussian 16 C.01 版本相较于 B.01 版本在功能上进行了更新，具体变更细节可查阅官方发布说明。主要更新包括支持 NBO 7、RESP 电荷计算以及多维势能面扫描数据的存储方式优化。此外，新版本增强了对 V100 GPU 的支持，并引入了针对实用程序的内存管理参数。

---

## 2. 实用程序的 -m 命令行参数

Gaussian 16 的实用程序现在支持使用 -m 命令行参数来指定该程序可用的内存大小。例如，通过命令 `formchk -m=1gb myfile` 可以指定 formchk 使用 1GB 的内存。在处理 fch 文件等操作时，该参数也可用于覆盖系统默认的环境变量内存限制。

---

## 3. V100 GPU 支持

Gaussian 16 [REV C] 版本新增了对 NVIDIA V100 GPU 加速计算的支持。相较于之前的官方 GPU 加速功能，新版本在 GPU 加速的性能方面有所提升，其性价比和实用性得到了改善。

---

## 4. NBO7 集成与关键词扩展

Gaussian 16 [REV C] 版本全面支持 NBO 7，并新增了一系列 Population 关键词选项。通过 Pop=NPA7、Pop=NBO7、Pop=NBO7Read 和 Pop=NBO7Delete 等关键词，可以直接调用 NBO 7 进行自然布居分析、完整自然键轨道分析、读取输入流的 NBO 分析以及删除相互作用的效应分析。这些删除和优化功能同时兼容 NBO6 和 NBO7。

---

## 5. NEDA 自然能量分解分析

[REV C] 版本引入了 Pop=NEDA 关键词，用于执行自然能量分解分析（NEDA）。该分析使用与 counterpoise 计算相同的片段输入信息，旨在分析分子间相互作用的能量分解。NEDA 属于基于 NBO 的能量分解方案，定位于填补 Gaussian 在能量分解分析方面的功能空白。

---

## 6. 多维松弛扫描数据存储

关于多维松弛扫描的信息现在以包含轴细节的结构化格式存储在格式化的检查点文件中，而非之前的扁平化存储。这种数据存储方式的更新使得多维扫描结果可以直接在 GaussView 和其他外部程序中正确显示和可视化。

---

## 7. RESP 电荷计算约束

Gaussian 16 [REV C] 版本在计算静电势导出电荷时增加了对 RESP（限制静电势）约束的支持。通过使用如 `Pop=(MK,Resp=N)` 的关键词组合，可以施加权重为 $N \times 10^{-6}$ Hartrees 的电荷平方约束，其中 N 的默认值为 2。此选项同样适用于其他静电势导出电荷方案，如 CHelp 和 HLY。
