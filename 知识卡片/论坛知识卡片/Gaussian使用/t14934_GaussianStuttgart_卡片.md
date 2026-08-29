---
key: t14934
title: Gaussian����Stuttgart���Ƽ���118��Ԫ��һ��
url: http://bbs.keinsci.com/thread-14934-1-2.html
domain: Gaussian使用
source: keinsci
year: 2019
cards: 4
---

# Gaussian����Stuttgart���Ƽ���118��Ԫ��һ�� — 知识卡片

## 1. Gaussian 超重元素基组选择

Gaussian 计算第 118 元素等超重元素推荐使用 Stuttgart 系列赝势基组，例如 ECP92MDF。该基组可配合 def2-TZVP 等基组使用。

---

## 2. Gaussian 版本对超重元素的限制

Gaussian 软件在 A.03 及之后版本停止了对原子序数超过 112 号元素的计算支持。对于这些受限元素，部分计算功能可能无法直接调用。

---

## 3. 超重元素 DFT 计算符号问题

针对特定超重元素（如 Og 等）进行 DFT 计算时，元素符号可能无法被程序直接识别。需使用原子序号体系中的符号表示法替代元素符号。

---

## 4. 超重元素初始猜测设置

在大部分常规路径下，若无法正常调用超重元素进行计算，建议添加 `guess=core` 关键字以设置初始猜测。
