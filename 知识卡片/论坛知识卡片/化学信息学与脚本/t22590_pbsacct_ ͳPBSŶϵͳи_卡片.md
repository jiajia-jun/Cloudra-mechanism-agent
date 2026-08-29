---
key: t22590
title: pbsacct: ͳ��PBS�Ŷ�ϵͳ�и��û�ʹ�����
url: http://bbs.keinsci.com/thread-22590-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2021
cards: 8
---

# pbsacct: ͳ��PBS�Ŷ�ϵͳ�и��û�ʹ����� — 知识卡片

## 1. pbsacct 工具简介

pbsacct 是用于统计 PBS 队列系统中用户使用情况的工具。其源代码存放于 GitHub 仓库 Torque_tools 中，下载后解压即可使用。

---

## 2. 工具安装文件复制

将 pbsacct 文件夹中的 pbs* 和 mm2month 文件复制到 /usr/local/bin/ 目录下。此操作需要 root 权限，执行命令为 `cp pbs* mm2month /usr/local/bin/`。

---

## 3. 工具执行权限设置

为 /usr/local/bin/ 目录下的 pbs* 和 mm2month 文件添加可执行权限。需执行 `chmod +x pbs*` 和 `chmod +x mm2month` 命令。

---

## 4. server_priv 目录权限设置

修改 /var/spool/torque/server_priv 目录权限为 751。此操作需在 root 权限下执行，命令为 `chmod 751 /var/spool/torque/server_priv`。

---

## 5. accounting 文件权限设置

修改 /var/spool/torque/server_priv/accounting 文件权限为 755。此操作需在 root 权限下执行，命令为 `chmod 755 /var/spool/torque/server_priv/accounting`。

---

## 6. pbsacct 统计命令使用

使用 pbsacct 命令结合通配符可以统计特定月份的用户使用情况。例如，统计 2021 年 4 月数据的命令为 `pbsacct 202104*`，该命令需在 accounting 文件所在目录执行。

---

## 7. 统计输出结果列含义

pbsacct 输出的统计结果包含 Wallclock、Average days、Percent、Average #nodes、q-days 等列。这些数据分别代表总耗时、平均使用天数、使用占比、平均使用节点数以及队列等待时间。

---

## 8. 输出结果行数据解读

统计结果的每一行对应一个用户的详细信息。数据包括用户名、用户组、作业数、总 Wallclock 时间、占总时间的百分比、平均使用的核数以及队列等待时间。
