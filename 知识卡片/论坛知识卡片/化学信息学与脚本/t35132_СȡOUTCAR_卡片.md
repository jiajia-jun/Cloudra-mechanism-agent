---
key: t35132
title: С����������ȡOUTCAR����������
url: http://bbs.keinsci.com/thread-35132-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2023
cards: 1
---

# С����������ȡOUTCAR���������� — 知识卡片

## 1. 提取OUTCAR中的energy without entropy值

使用 Read_OUTCAR_beta0.2.exe 工具可从 VASP 计算输出的 OUTCAR 文件中提取 "energy without entropy" 数值。该程序支持自动扫描当前目录及所有子文件夹中的 OUTCAR 文件。提取到的数值会自动保存到对应目录下，并以该数值命名的 .txt 文件中。如果检测到 OUTCAR 文件未运行完成，则会生成一个名为 1-OUTCAR-unfinished.txt 的文件。程序执行结束后，可通过 read.log 文件查看详细的读取记录。
