---
key: t23574
title: Gaussian��ʶ���GAFF��GAFF2�����ļ�
url: http://bbs.keinsci.com/thread-23574-1-1.html
domain: Gaussian使用
source: keinsci
year: 2021
cards: 6
---

# Gaussian��ʶ���GAFF��GAFF2�����ļ� — 知识卡片

## 1. Gaussian 扫描与构型优化力场支持

Gaussian 的势能面扫描和构型优化功能支持指定力场进行计算。目前可用的力场仅限于 Amber、Dreiding 和 UFF。

---

## 2. 力场支持局限性与替代方案

Gaussian 原生支持的力场较少，无法直接使用 GAFF 等通用力场。Gromacs 或 AmberTools 具有广泛的力场支持与强大的计算功能，但仅对 Gaussian 输出文件进行能量重新计算无法完成完整的势能面扫描或构型优化。

---

## 3. 构型优化的力场选择策略

进行构型优化时，需根据体系特征选择合适的力场。若体系包含复杂原子类型或需要更精细的力场参数，Gaussian 自带力场的适用性可能有限，且部分力场中的原子类型默认半径可能较小。

---

## 4. GAFF 力场参数转换方法

通过编写 Python 脚本，可以将 AmberTools20 中的 GAFF 力场文件（如 gaff.dat 和 gaff2.dat）转换为 Gaussian 可识别的格式（参照 Gaussian16 源码中的 amber.prm）。此方法扩展了 Gaussian 对 GAFF 力场的支持。

---

## 5. 力场参数文件调用格式

使用外部力场参数文件时，需在 Gaussian 输入文件中通过外部文件读取卡指定力场参数文件名和存放路径。具体调用语法可参考相关文档，并在相应位置使用 @ 符号调用。

---

## 6. 扫描与优化关键词设置

在使用力场进行势能面扫描或构型优化时，必须在 Route Section 中加入 Opt=NoMicro 关键词。当使用 Amber 力场时，需额外加入 Amber=SoftOnly 关键词。
