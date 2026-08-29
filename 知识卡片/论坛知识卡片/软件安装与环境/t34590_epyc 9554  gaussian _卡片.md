---
key: t34590
title: epyc 9554 ���� gaussian 16
url: http://bbs.keinsci.com/thread-34590-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 3
---

# epyc 9554 ���� gaussian 16 — 知识卡片

## 1. 测试环境硬件配置

测试平台搭载双路 AMD EPYC 9554 处理器，共计 128 核，主频约为 3.1GHz 至 3.55GHz。系统配备 1.5T 内存，以满足大规模计算需求。

---

## 2. 测试软件版本与编译选项

使用 Gaussian 16 C01 版本，编译时采用了 AVX2 指令集优化。输入文件名为 test0397，计算任务分配的内存设置为 %mem=1024GB。

---

## 3. 测试基准与方法

测试针对两种积分格网精度进行了对比，分别使用 Gaussian 16 默认精度和 g09default 精度。测试记录了不同设置下的计算耗时，时间单位为秒。
