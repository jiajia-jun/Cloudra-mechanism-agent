---
key: t53149
title: ˫��ʹ��GaussView��xyz/trj�ļ���Сtrick
url: http://bbs.keinsci.com/thread-53149-1-1.html
domain: 可视化与制图
source: keinsci
year: 2025
cards: 3
---

# ˫��ʹ��GaussView��xyz/trj�ļ���Сtrick — 知识卡片

## 1. xyz2gau.exe 工具功能

xyz2gau.exe 是一款用于将坐标文件转换为 Gaussian 输入文件的工具。该程序能够批量处理 xyz 文件及 trj 轨迹文件（包含非标准/多帧 xyz 格式）。默认处理方式为按顺序打开文件并进行转换，操作简便。

---

## 2. 环境变量配置要求

使用 xyz2gau.exe 工具前需设置环境变量。具体操作为正确配置 GAUSS_EXEDIR 环境变量，并确保其添加在系统路径的顺序中，以保证程序能被正确调用和执行。

---

## 3. xyz2gau.py 源码与特性

xyz2gau.py 是 xyz2gau.exe 工具的 Python 源代码。该脚本基于 原作者 和 OfakeG 的成果编写，除了完成转换功能外，还支持在转换完成后自动调用 gview 程序查看结果。
