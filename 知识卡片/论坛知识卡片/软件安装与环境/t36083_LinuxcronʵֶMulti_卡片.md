---
key: t36083
title: Linux������cronʵ�ֶ�Multiwfn���Զ���ʱ����
url: http://bbs.keinsci.com/thread-36083-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 11
---

# Linux������cronʵ�ֶ�Multiwfn���Զ���ʱ���� — 知识卡片

## 1. Multiwfn 自动更新脚本应用场景

Multiwfn 提供了用于自动更新程序的脚本，适用于需要定期检查并更新 Multiwfn 版本的情况。使用 cron 定时任务调度该脚本，可以实现无人值守的自动更新，从而节省手动操作的时间。

---

## 2. 检查 cron 服务状态

在使用 cron 定时任务前，需要确认系统中的 crond 服务处于开启状态。可以使用命令 `service crond status` 来查看服务是否正在运行。

---

## 3. 设置 cron 定时任务

使用 `crontab -e` 命令编辑 cron 任务表，并在文件末尾添加任务指令。添加的指令格式为 `0 10 * * * bash /脚本路径 >> /日志路径`，该示例表示每天 10 点执行指定路径下的更新脚本，并将输出重定向到指定日志文件中。

---

## 4. 脚本路径配置要求

在配置 cron 任务时，脚本路径和日志信息路径必须使用绝对路径。例如，脚本路径可写为 `/mnt/d/Multiwfn_Linux/Multiwfn_Updater/AutoUpdate4Multiwfn.sh`。

---

## 5. AutoUpdate4Multiwfn.sh 路径参数设置

在 "AutoUpdate4Multiwfn.sh" 脚本中，需要在 "Basic settings" 区域配置各类程序的可执行文件路径。必须设置的路径参数包括 `Multiwfnpath`、`gaupath`、`cubegenpath`、`formchkpath` 以及 `orca_2mklpath`。

---

## 6. 路径参数示例值

脚本中各路径参数的示例配置值分别为：`Multiwfnpath=/mnt/d/Multiwfn_Linux/Multiwfn_3.8_dev_bin_Linux/Multiwfn`、`gaupath=/mnt/d/Gaussian16_Linux/g16/g16`、`cubegenpath=/mnt/d/Gaussian16_Linux/g16/cubegen`、`formchkpath=/mnt/d/Gaussian16_Linux/g16/formchk`、`orca_2mklpath=/mnt/d/ORCA_Linux/orca-5.0.4/orca_2mkl`。

---

## 7. 自动更新日志记录机制

当 cron 任务正确配置并运行脚本后，操作记录会被写入 "AutoUpdate4Multiwfn.log" 日志文件。日志文件会记录每次执行时的本地版本、在线最新版本以及更新操作的具体结果。

---

## 8. 日志版本检查条目

日志文件中会显示本地 Multiwfn 版本和在线最新版本信息，例如 "Local version of Multiwfn: 3.8(dev) 2023-Mar-11" 和 "Latest online version of Multiwfn: 3.8(dev) 2023-Mar-26"。

---

## 9. 发现新版本时的日志内容

若检测到有新版本发布，日志会记录发现新版本的提示，并显示下载和更新的过程。条目示例包括 "New verison of Multiwfn 3.8(dev) released at 2023-Mar-26 is found!"、"Downloading the latest version of Multiwfn..." 以及 "Multiwfn has been updated to the latest version"。

---

## 10. 配置文件自动更新参数

脚本执行更新后，会同步更新 Multiwfn 的 settings.ini 文件，并在日志中列出关键参数。日志中显示的参数包括 `iloadGaugeom= 1`、`nthreads= 6`、`ompstacksize= 2267867272`、`isilent= 1` 以及各类外部程序路径。

---

## 11. 版本已是最新时的日志反馈

如果本地版本已是最新，日志将记录 "The local version of Multiwfn is already up-to-date!"，此时不会执行下载更新操作。
