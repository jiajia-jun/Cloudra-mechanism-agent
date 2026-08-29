---
key: t24661
title: ˫ԭ�ӷ��ӹ��׳�����ϳ���vibrot�������棩
url: http://bbs.keinsci.com/thread-24661-1-1.html
domain: 激发态与光谱
source: keinsci
year: 2021
cards: 5
---

# ˫ԭ�ӷ��ӹ��׳�����ϳ���vibrot�������棩 — 知识卡片

## 1. 双原子分子振动转动能级计算

双原子分子振动转动能级的计算可使用 R.J. Le Roy 编写的 Level 程序或 Molcas 软件包中的 vibrot 模块。这些工具能够获得双原子分子的振动转动能级。Level 程序下载地址为 http://leroy.uwaterloo.ca/programs.html，vibrot 模块的相关讨论见于 http://bbs.keinsci.com/thread-5614-1-1.html。

---

## 2. Level 程序的输入格式与局限性

Level 程序的输入基于自由格式，要求填写较多参数。若参数设置不当，可能导致计算结果不符合预期或运行报错。对于弱束缚双原子体系、极深势阱或需要激发态预测的体系，Level 程序在使用上存在一定困难。

---

## 3. vibrot 模块的功能与适用性

vibrot 模块不存在 Level 程序中关于参数繁琐和特定体系报错的问题。该模块适用于弱束缚双原子体系、极深势阱体系以及激发态的预测。vibrot 足够健壮，能够处理 Level (16版) 在特定条件下可能报错的情形。

---

## 4. vibrot 对 Molcas 环境的依赖问题

vibrot 是 Molcas (OpenMolcas) 内置的模块，其运行依赖于 Molcas 的底层支持。在 Windows 系统下使用 vibrot 需要配置 cygwin 或 msys 环境，而 Molcas 底层由 Python 重写，vibrot 原代码由 Perl 编写。这种语言差异导致在 cygwin/msys 环境下调用 vibrot 可能出现兼容性问题。

---

## 5. vibrot 的授权情况

vibrot 模块随 OpenMolcas 以 LGPL 协议开源发布，因此该模块不存在版权限制问题。
