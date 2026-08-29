---
key: b126
title: GauMD2xyz：将Gaussian的从头算动力学轨迹转换为xyz轨迹的程序
url: http://sobereva.com/126
domain: 化学信息学与脚本
source: blog
year: 2020
cards: 3
---

# GauMD2xyz：将Gaussian的从头算动力学轨迹转换为xyz轨迹的程序 — 知识卡片

## 1. GauMD2xyz 程序功能

GauMD2xyz 是用于将 Gaussian 的 BOMD 或 ADMP 任务产生的轨迹转化为多帧 .xyz 格式的程序。转换后的 .xyz 文件可被动力学可视化程序（如 VMD）读取以进行进一步分析。该程序的最新版本为 1.2，提供 Windows 可执行文件（.exe）和 Linux 可执行文件（无后缀）。

---

## 2. GauMD2xyz 使用步骤

使用该程序前需先在 Gaussian 中执行 BOMD 或 ADMP 任务。启动程序后，需输入 fch/fchk 文件名或 Gaussian 输出文件名（必须以 .out 或 .log 为后缀）。随后输入要产生的 .xyz 文件路径即可完成转换。

---

## 3. 多轨迹处理

如果 BOMD 任务的 ntraj 参数设定为大于 1，即计算了多条轨迹，程序会提示用户选择读入哪条轨迹。程序文件包中的 test 目录内包含了一些使用示例。
