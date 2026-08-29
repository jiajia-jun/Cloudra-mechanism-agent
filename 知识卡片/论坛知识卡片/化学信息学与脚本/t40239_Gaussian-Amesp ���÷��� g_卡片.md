---
key: t40239
title: Gaussian-Amesp ���÷��� gamesp.py
url: http://bbs.keinsci.com/thread-40239-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2023
cards: 9
---

# Gaussian-Amesp ���÷��� gamesp.py — 知识卡片

## 1. Gaussian-Amesp 接口简介

Gaussian-Amesp 是一个开源工具，用于在 Gaussian 中调用 Amesp 进行计算。该工具支持利用 Amesp 的 Hessian 计算结果，帮助 Gaussian 更好地优化过渡态结构，其源代码已在 GitHub 上以 BSD 2-Clause License 协议开源。

---

## 2. Amesp 软件功能概述

Amesp (Atomic and molecular electronic structure program) 是一款基于 GTO 基组的开源量子化学计算软件，使用 Fortran 语言编写。该软件支持多种 WFT 和 DFT 方法，可进行几何优化、频率分析及过渡态搜索，并支持计算核磁共振以及色散效应，同时具备 RI 和 COSX 等加速算法接口。

---

## 3. Gaussian-Amesp 支持的计算类型

Gaussian-Amesp 接口目前支持在 Gaussian 的计算流程中使用 Amesp 支持的任何计算层级。具体支持的任务类型包括结构优化、频率计算、过渡态搜索以及内禀反应坐标(IRC)计算。

---

## 4. Amesp 配置文件设置

使用 Gaussian-Amesp 前，需准备一个名为 template.aip 的 Amesp 配置文件。该文件需包含并行参数、内存核心数限制以及计算方法等关键信息，例如指定 B3LYP-D3BJ/6-31G* 方法、设置 10 个并行进程和 2000MB 的单核最大内存。

---

## 5. Gaussian 输入文件基本写法

在 Gaussian 输入文件中调用 Amesp 时，需在路由行中使用 `external="python3 -u /path/to/gamesp.py"` 关键字。路径 `/path/to/gamesp.py` 应替换为脚本 gamesp.py 的实际存放位置，且建议直接使用绝对路径。

---

## 6. 过渡态优化与频率验证的输入写法

进行过渡态优化和频率验证时，Gaussian 输入文件通常分为两段。第一段执行频率计算，第二段通过 `--link1--` 分隔，读取前一步的 checkpoint 文件，并执行带有 `opt=(ts,rcfc,noeigen,nomicro)` 参数的过渡态优化。

---

## 7. 过渡态优化参数说明

在过渡态优化的 Gaussian 路由行中，`ts` 表示搜索过渡态，`rcfc` 表示读取力常数矩阵，`nomicro` 用于禁用微迭代。设置这些参数旨在利用 Amesp 计算的 Hessian 矩阵来辅助优化过程，以提高搜索效率和稳定性。

---

## 8. IRC 计算的输入写法

若需进行 IRC (内禀反应坐标) 计算，需使用 `oldchk` 指定包含已优化过渡态结构的 checkpoint 文件。在路由行中使用 `external="python3 -u /path/to/gamesp.py" irc=(rcfc) geom=allcheck` 命令，即可利用 Amesp 启动 IRC 计算。

---

## 9. 当前版本的功能限制

当前 Amesp 1.1 dev 版本通过 Gaussian-Amesp 接口已支持过渡态优化和 IRC 计算。计算完成后，生成的结果文件可以使用 GaussView 等可视化软件直接打开查看。
