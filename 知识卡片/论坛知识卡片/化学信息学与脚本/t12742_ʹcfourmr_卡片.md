---
key: t12742
title: ������������ʹ��cfour��mrcc�Ľű�
url: http://bbs.keinsci.com/thread-12742-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2019
cards: 3
---

# ������������ʹ��cfour��mrcc�Ľű� — 知识卡片

## 1. CFOUR与MRCC程序的高精度耦合

CFOUR 与 MRCC 程序均适用于高精度计算。CFOUR 的 CCSD(T) 计算速度较快，而 MRCC 提供更为丰富的 CC 和 CI 方法及变分功能。
- 将两者结合可以实现 CFOUR 与 MRCC 的协同使用。
- 原文链接为 http://bbs.keinsci.com/thread-6701-1-1.html。

---

## 2. 协同使用的文件管理问题

在协同使用过程中，输入输出文件名通常是固定的，这会导致文件覆盖问题。MRCC 的输入文件为 MINP，CFOUR 的输入文件为 ZMAT。
- 由于 CFOUR 运行时需要将相关文件链接到当前目录，这会在当前目录下产生大量临时文件。
- 这些临时文件需要用户手动删除，否则占用磁盘空间并影响后续计算体验。

---

## 3. 自动化脚本 cmrcc 与 cfour

cmrcc 和 cfour 是为解决上述文件管理问题而编写的脚本工具。cmrcc 用于调用 MRCC 模块，cfour 脚本则用于替代 CFOUR 的标准执行方式以避免文件名冲突。
- 使用 cfour 脚本时，命令格式为 `cfour 1.inp > 1.out`，计算结果会输出到 1.out 文件中。
- 若仅执行 `cfour 1.inp` 而不重定向输出，所有结果将直接打印在屏幕上。
- cfour 脚本中涉及复制文件路径的部分，需要根据实际环境修改为用户本地 CFOUR 的安装目录，而 cmrcc 脚本则无此修改要求。
