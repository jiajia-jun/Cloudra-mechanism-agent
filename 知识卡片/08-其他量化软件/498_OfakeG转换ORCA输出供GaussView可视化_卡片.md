---
id: 498
title: OfakeG：使GaussView能够可视化ORCA输出文件的工具
url: http://sobereva.com/498
domain: 其他量化软件
topic: OfakeG转换ORCA输出供GaussView可视化
cards: 8
---

# OfakeG转换ORCA输出供GaussView可视化 — 知识卡片

## 1. OfakeG工具简介与用途

OfakeG是笔者开发的程序，用于将ORCA的几何优化、频率分析及优化+频率分析任务的输出文件“伪造”成Gaussian的输出文件，从而可以使用GaussView直接可视化查看。该程序解决了ORCA用户在几何优化轨迹/收敛情况考察以及振动模式观看方面的不便，尤其适用于习惯使用GaussView的用户。演示视频可见《基于ORCA量子化学程序对分子做优化、振动分析、观看红外光谱、观看轨道的简单演示》。

---

## 2. OfakeG的下载地址与版本支持

OfakeG程序可在官方页面下载：http://sobereva.com/soft/OfakeG，其中带.exe后缀的是Windows版，不带后缀的是Linux版。此程序经测试支持ORCA 4.x、5.x、6.x版本，目前仅支持处理ORCA的opt、freq和opt freq任务的输出文件，不支持单点任务文件。

---

## 3. OfakeG的基本使用方法

启动OfakeG程序后输入ORCA输出文件路径，按回车即可在当前目录下产生伪造的Gaussian输出文件。如果输入文件名为yuri.out，输出文件将是yuri_fake.out，该文件可直接载入GaussView播放优化动画或观看振动模式。在Windows下还可以直接将ORCA输出文件拖到OfakeG.exe图标上运行，或在Linux下使用命令行（如./OfakeG Aika.out）。

---

## 4. OfakeG的故障排除与编码问题

若OfakeG处理文件崩溃且生成的_fake文件内容极少，可能是由于ORCA输出文件编码为UTF16所致。OfakeG无法处理UTF16编码，需用文本编辑器（如Ultraedit）将文件另存为Unicode或UTF8编码。在Windows下使用老版本PowerShell重定向输出可能导致UTF16编码，建议使用命令格式：`D:\study\orca\orca test.inp | out-file test.out -encoding utf8`。

---

## 5. OfakeG对Gaussian输出格式的简化处理

OfakeG生成的是能令GaussView正常读取的最简化Gaussian输出文件。虽然GaussView要求文件包含basis functions、alpha electrons、beta electrons信息，但ORCA不直接提供这些与观看优化和振动分析无关的信息，因此OfakeG在伪造文件开头将这些信息的数值统一设为0。

---

## 6. OfakeG处理优化任务的能量与收敛逻辑

OfakeG从ORCA输出文件中读取的能量是FINAL SINGLE POINT ENERGY，但在伪造的Gaussian输出文件中以SCF Done标签输出。ORCA在优化最后满足收敛限后还会预测下一步结构并计算能量但不计算受力，因此OfakeG输出的伪造文件中，最后一步的收敛信息里当前值会被设为0来占位。伪造文件中保留了能量变化作为收敛判断标准，尽管GaussView不会读取此项。

---

## 7. OfakeG处理振动分析数据的规则

由于ORCA不给出约化质量、振动模式的力常数以及振动模式的不可约表示，OfakeG在伪造的Gaussian输出文件中不包含前两项，并将不可约表示一律输出为A。OfakeG会将ORCA输出的热力学数据转换为Gaussian格式，并额外显示Electronic energy一项，其值为振动分析对应结构的电子能量。

---

## 8. OfakeG不支持的ORCA任务类型

OfakeG目前不支持处理ORCA的IRC任务输出文件，因为ORCA 4.1.2版的IRC功能较弱且不输出反应坐标，无法转换为Gaussian格式。OfakeG也不支持转换ORCA的TDDFT等电子激发任务输出文件，建议使用Multiwfn基于ORCA的TDDFT输出信息绘制电子光谱和进行分析。
---
