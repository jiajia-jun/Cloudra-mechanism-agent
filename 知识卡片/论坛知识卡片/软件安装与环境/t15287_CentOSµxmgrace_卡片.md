---
key: t15287
title: CentOS�������µ�xmgrace���ϼ��������
url: http://bbs.keinsci.com/thread-15287-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2019
cards: 2
---

# CentOS�������µ�xmgrace���ϼ�������� — 知识卡片

## 1. CentOS 系统 xmgrace 启动报错解决方法

xmgrace 软件在 CentOS 系统下启动时报错，尝试使用 `yum reinstall xmgrace` 重新安装或删除源码重装通常无法解决问题。根据 Redhat 官方论坛的信息，此故障原因是系统目录 `/usr/share/fonts/default/Type1/` 下的系统字体文件被误删或损坏。

---

## 2. 修复 xmgrace 启动故障的具体操作步骤

解决该故障的方法是将系统字体文件恢复至 `/usr/share/fonts/default/Type1/` 目录下，恢复文件后 xmgrace 即可正常运行。为方便他人复现，已将 xmgrace 所需的 Type1 目录下的文件打包，有需要的用户可下载后自行解压恢复。
