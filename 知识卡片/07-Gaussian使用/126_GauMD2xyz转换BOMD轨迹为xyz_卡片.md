---
id: 126
title: GauMD2xyz：将Gaussian的从头算动力学轨迹转换为xyz轨迹的程序
url: http://sobereva.com/126
domain: Gaussian使用
topic: GauMD2xyz转换BOMD轨迹为xyz
cards: 3
---

# GauMD2xyz转换BOMD轨迹为xyz — 知识卡片

## 1. GauMD2xyz程序简介与版本

GauMD2xyz程序用于将Gaussian的BOMD或ADMP任务产生的轨迹转化为多帧.xyz格式，以便被VMD等动力学可视化程序分析。当前最新版本为1.2，下载地址为http://sobereva.com/soft/GauMD2xyz_1.2.zip。压缩包中带.exe后缀的是Windows版可执行文件，无后缀的是Linux版可执行文件。

---

## 2. 程序的操作步骤

首先在Gaussian中执行BOMD或ADMP任务，之后启动GauMD2xyz程序。用户需输入fch/fchk文件名或者Gaussian输出文件名（必须以.out或.log为后缀），然后输入要产生的.xyz文件路径。文件包中的test目录包含了一些例子可供参考。

---

## 3. 多轨迹轨迹选择

如果Gaussian中的BOMD任务参数ntraj设为大于1，即计算了多条轨迹，本程序会提示用户选择具体要读入并转换哪一条轨迹。
