---
id: 126
title: GauMD2xyz：将Gaussian的从头算动力学轨迹转换为xyz轨迹的程序
domain: Gaussian使用
topic: GauMD2xyz转换BOMD轨迹为xyz
cards: 3
---

## 1. GauMD2xyz程序简介与下载
GauMD2xyz程序用于将Gaussian的BOMD或ADMP任务产生的轨迹转化为多帧.xyz格式以便进行动力学可视化分析。当前程序最新版本为1.2。压缩包中带.exe后缀的文件为Windows版可执行文件，无后缀的文件为Linux版可执行文件。

---

## 2. GauMD2xyz程序操作步骤
使用GauMD2xyz程序需首先在Gaussian中执行BOMD或ADMP任务。启动本程序后，需要输入fch/fchk文件名或者Gaussian输出文件名（必须以.out或.log为后缀），然后输入要产生的.xyz文件路径。文件包中的test目录包含了一些示例文件。

---

## 3. 多轨迹处理机制
如果BOMD任务的参数ntraj被设置为大于1，即计算包含多条轨迹，本程序在运行过程中会提示用户选择要读入哪条轨迹。
