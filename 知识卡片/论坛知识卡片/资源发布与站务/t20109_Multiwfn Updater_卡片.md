---
key: t20109
title: Multiwfn Updater
url: http://bbs.keinsci.com/thread-20109-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2020
cards: 5
---

# Multiwfn Updater — 知识卡片

## 1. Multiwfn 开发版更新频率

Multiwfn 开发版更新频率较高，手动更新需要频繁下载最新版并替换旧文件，操作较为繁琐。为简化这一流程，相关社区成员开发了自动更新脚本，适用于 Windows 和 Linux 平台。

---

## 2. Multiwfn 自动更新参考方案

论坛中曾出现多种 Multiwfn 自动更新方案，例如利用 Notepad++ 结合 Multiwfn 更新日志的方式，以及专用的 Multiwfn 更新管理工具。这些方案为用户提供了避免手动重复下载替换的参考。

---

## 3. Multiwfn Updater 脚本功能

Multiwfn Updater 是一款自动化脚本，旨在简化 Multiwfn 的更新流程。该脚本的主要功能包括检查并更新 Linux 版本的 Multiwfn、检查并更新 WSL 平台上的 Windows 版 Multiwfn，以及下载 Multiwfn 手册到指定路径。

---

## 4. 脚本在 Linux 环境下的使用准备

在 Linux 环境下使用该脚本前，需将 Multiwfn 目录以及 Gaussian (g16/g09) 或 ORCA 相关程序路径添加至环境变量中。通常通过修改 `~/.bashrc` 文件实现，确保脚本可以通过 `which` 命令正确定位程序位置。

---

## 5. 脚本在 WSL 环境下的使用准备

在 WSL 平台使用该脚本更新 Windows 版 Multiwfn 前，需将 `Multiwfn.exe` 及计算化学程序（如 `g16.exe`、`g09.exe`、`orca_2mklpath.exe`）所在目录添加至系统 Path 环境变量。配置完成后，即可在 WSL 平台运行该脚本进行自动更新。
