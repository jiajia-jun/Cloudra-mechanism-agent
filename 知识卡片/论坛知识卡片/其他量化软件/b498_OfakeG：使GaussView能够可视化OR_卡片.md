---
key: b498
title: OfakeG：使GaussView能够可视化ORCA输出文件的工具
url: http://sobereva.com/498
domain: 其他量化软件
source: blog
year: 2019
cards: 11
---

# OfakeG：使GaussView能够可视化ORCA输出文件的工具 — 知识卡片

## 1. OfakeG 程序功能概述

OfakeG 是一个将 ORCA 量子化学程序输出文件转换为 Gaussian 输出文件格式的工具。该转换过程使得 GaussView 图形界面能够直接读取并可视化 ORCA 的计算结果。此工具主要旨在解决 ORCA 缺乏如 GaussView 般理想图形界面的问题，特别是在几何优化轨迹和振动模式观看方面的需求。OfakeG 的开发灵感来源于 xtb 程序，属于合法的文件格式转换，不涉及对 GaussView 程序本身的篡改。

---

## 2. OfakeG 支持的计算类型与版本

OfakeG 目前支持处理 ORCA 的几何优化、振动分析以及优化+振动分析任务的输出文件。该程序对于 ORCA 4.x、5.x、6.x 版本经测试可用，对于其他版本的兼容性需用户自行尝试。单点能计算任务的输出文件不支持转换，因为其转换缺乏实际意义。

---

## 3. OfakeG 基本使用方法

OfakeG 的使用方式为将 ORCA 输出文件路径输入给程序并按回车，程序会在当前目录下生成后缀为 `_fake.out` 的伪造 Gaussian 输出文件。若输入文件名为 `yuri.out`，则输出文件名为 `yuri_fake.out`。在 Windows 系统下，可直接将 ORCA 输出文件拖拽至 `OfakeG.exe` 图标上运行。

---

## 4. GaussView 中的可视化操作

生成的 `_fake.out` 文件可直接载入 GaussView。对于几何优化或优化+振动分析任务，可以通过 GaussView 的 `results - Optimization` 功能播放优化过程动画并考察收敛情况。对于振动分析或优化+振动分析任务，可以通过 `results - Vibrations` 功能观看振动模式。

---

## 5. OfakeG 命令行调用方式

OfakeG 支持通过命令行参数运行，例如在 Linux 下执行 `./OfakeG Aika.out`，将在当前目录生成 `Aika_fake.out`。用户可以编写 shell 脚本利用此命令行功能批量转换 ORCA 输出文件。

---

## 6. ORCA 输出文件编码问题处理

若 OfakeG 处理文件时崩溃且生成的 `_fake` 文件仅含几行信息，通常是因为 ORCA 输出文件为 UTF-16 编码。OfakeG 仅能处理 UTF-8 编码的文件。Windows 的 CMD 和 PowerShell 重定向输出通常为 UTF-8，但旧版 PowerShell 可能输出 UTF-16，此时需用文本编辑器将其另存为 Unicode 或 UTF-8 编码后再处理。

---

## 7. 伪造 Gaussian 输出文件的格式细节

OfakeG 生成的伪造文件包含 GaussView 读取所需的 `basis functions`、`alpha electrons`、`beta electrons` 信息，但这些数值均设为 0。程序读取 ORCA 输出中的 `FINAL SINGLE POINT ENERGY` 作为当前计算级别的能量，并在伪造文件中将其输出为 `SCF Done` 标签以符合格式要求。

---

## 8. 优化步数信息的转换逻辑

ORCA 在满足收敛限后会预测下一步结构并计算其能量，但不计算受力。OfakeG 在转换时，会包含从第 1 步到最后预测步（i+1 步）的结构和能量信息。最后一次输出的收敛判断信息中，当前值会被全部设为 0 以进行占位。

---

## 9. 振动分析数据的转换限制

由于 ORCA 不提供约化质量和振动模式的力常数，伪造的 Gaussian 输出文件中也不包含这些信息，但不影响常规分析。ORCA 同样不给出振动模式的不可约表示，因此 OfakeG 将不可约表示统一输出为 `A`。

---

## 10. 热力学数据的转换

OfakeG 将 ORCA 振动分析输出的热力学数据转换为 Gaussian 的输出形式。转换后的文件中会额外显示一项 `Electronic energy=`，其数值对应于振动分析结构的电子能量。

---

## 11. 不支持的转换任务类型

OfakeG 目前不支持转换 ORCA 的 IRC 任务输出文件，主要因 ORCA 4.1.2 等版本的 IRC 功能较弱且不输出反应坐标。该程序也不支持转换 TDDFT 等电子激发任务的输出文件，因为 Multiwfn 可以直接基于 ORCA 的 TDDFT 输出绘制光谱并进行分析，且 ORCA 输出的是组态贡献而非系数，无法转换为 Gaussian 格式。
