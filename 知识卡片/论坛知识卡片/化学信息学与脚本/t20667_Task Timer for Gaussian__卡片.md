---
key: t20667
title: Task Timer for Gaussian/ORCA jobs
url: http://bbs.keinsci.com/thread-20667-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 2
---

# Task Timer for Gaussian/ORCA jobs — 知识卡片

## 1. Python 脚本统计 Gaussian16/ORCA 计算耗时

Python 脚本 Task_Timer.py 可用于统计当前目录及子目录下所有 Gaussian16 或 ORCA 输出文件中的 CPU 时间。该工具旨在汇总 2020 年度所有计算任务的累计耗时，以便掌握计算资源的使用情况。

---

## 2. 脚本运行命令

在终端中执行 `./Task_Timer.py` 命令即可启动统计程序。程序会自动扫描当前目录及其子目录下的 Gaussian 和 ORCA 计算文件。
