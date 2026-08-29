---
key: t20070
title: mum: Multiwfn update manager
url: http://bbs.keinsci.com/thread-20070-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2020
cards: 6
---

# mum: Multiwfn update manager — 知识卡片

## 1. mum 工具简介

mum (Multiwfn's Update Manager) 是用于管理 Multiwfn 程序更新的脚本工具。该工具能够自动检测 Multiwfn 最新版、下载更新、管理备份版本以及下载用户手册和历史文件。

---

## 2. mum 脚本的功能特点

mum 脚本集成了多项自动化功能，包括检查更新、版本升级、版本回滚以及下载文档。脚本会自动识别是否安装了外部量子化学程序（如 ORCA、Gaussian），此过程仅需修改 settings.ini 文件即可。

---

## 3. 版本更新与检测机制

脚本对比 Multiwfn 最新版与本地版之间的差异，仅在发现不同时才执行更新操作。每次更新操作结束后，系统会自动进行备份，以便后续能够恢复到历史版本。

---

## 4. 下载历史文件与手册功能

通过 manual 选项，可将最新的 Multiwfn 手册下载到 Multiwfnpath 目录下。通过 fetch 选项，可将 Multiwfn 的历史文件从指定网址下载并解压到当前目录。

---

## 5. mum 脚本的使用方法

在赋予脚本执行权限后，输入 ./mum h 即可查看帮助信息。脚本支持的命令参数包括 check (检查更新)、update (更新到最新版)、list (列出备份版本)、roll (回滚到备份版本)、delete (删除所有备份)、manual (下载手册) 以及 fetch (下载历史文件)。

---

## 6. 脚本环境兼容性

mum 脚本已在 3.7dev-11-Aug-2019 版本的 Multiwfn 环境下测试通过，运行过程顺利。
