---
key: t17394
title: ���߰汾��Gaussian IOps Reference����pdf�汾����
url: http://bbs.keinsci.com/thread-17394-1-1.html
domain: Gaussian使用
source: keinsci
year: 2020
cards: 7
---

# ���߰汾��Gaussian IOps Reference����pdf�汾���� — 知识卡片

## 1. IOp 参数查询工具 giop 介绍

giop 是一个基于 Python 的工具，用于从 Gaussian 软件相关的 HTML 文件中查询 IOp (Internal Option) 参数。该工具项目托管于 GitHub 仓库，发布于 2020 年 6 月 10 日，提供 txt、md 及 pdf 版本的文档下载。

---

## 2. 数据来源与文件准备

该工具使用 BeautifulSoup 库提取 HTML 内容。Gaussian 16 版本对应的 HTML 文件已包含在项目的 G16html 目录下，无需手动下载；若需替换，也可以使用其他版本的 HTML 文件。

---

## 3. 命令行查询用法

查询特定的 IOp 参数（如 IOp(3/33)）可以使用命令 `python get_iop.py 3 33` 运行脚本。支持设置 alias（别名），例如输入格式为 `giop 3 33`。

---

## 4. IOp(3/33) 参数定义

IOp(3/33) 用于控制 Integral package printing（积分包打印）。可选参数值含义如下：0 表示不打印积分；1 表示打印单电子积分；3 表示以标准格式打印双电子积分；4 表示以 debug 格式打印双电子积分；5 表示组合打印 1 和 3；6 表示组合打印 1 和 4。

---

## 5. 系统兼容性

该工具支持在 Windows 和 Linux 系统下运行。在 Linux 环境下，可使用 MinGW 或 Termux 进行操作。

---

## 6. 已知软件缺陷与修复

由于 Gaussian 官方 HTML 源文件较为杂乱，当前 giop 版本存在较多 bug。已修复的问题包括：<span> 标签下的 bug、<sup> 标签下的 bug（网页显示为 ^）、IOp(5/5) 源文件错误（原文"5id"修正为"id"）以及 giop 目录中的部分 bug。

---

## 7. 未来开发计划

项目的待办事项（TODO）包括：支持 "IOp(7/60-62)" 这种连续区间的查询、补全缺失的 IOp 数据、将查询方式从直接解析 HTML 改为写入数据库以加快查询速度。
