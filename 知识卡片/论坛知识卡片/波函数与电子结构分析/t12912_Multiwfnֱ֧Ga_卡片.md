---
key: t12912
title: Multiwfn����֧��ֱ������Gaussian��.chk�ļ�
url: http://bbs.keinsci.com/thread-12912-1-1.html
domain: 波函数与电子结构分析
source: keinsci
year: 2019
cards: 3
---

# Multiwfn����֧��ֱ������Gaussian��.chk�ļ� — 知识卡片

## 1. Multiwfn 直接读取 Gaussian .chk 文件

旧版本 Multiwfn 无法直接读取 Gaussian 的 .chk 文件，需手动通过 formchk 将其转换为 .fch/.chk 格式。新版本仅需修改 settings.ini 文件，将 formchkpath 设置为实际 Gaussian 目录下的 formchk 可执行文件路径，即可直接读取 .chk 文件。

---

## 2. 读取 .chk 文件的自动转换流程

Multiwfn 直接读取 .chk 文件时，会自动调用 formchk 进行格式转换。转换完成后，程序会自动删除临时的 .fch/.chk 文件，此过程完全模拟了 GaussView 读取 .chk 文件的处理机制。

---

## 3. 配置 formchk 路径

为启用 Multiwfn 对 .chk 文件的直接读取功能，用户需在 settings.ini 配置文件中正确设置 formchkpath 参数，指向 Gaussian 安装目录下的 formchk 执行程序。
