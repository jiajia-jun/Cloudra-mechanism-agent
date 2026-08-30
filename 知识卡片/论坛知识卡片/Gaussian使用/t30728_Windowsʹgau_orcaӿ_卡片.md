---
key: t30728
title: ��Windows��ʹ��gau_orca�ӿڵļ򵥷���
url: http://bbs.keinsci.com/thread-30728-1-1.html
domain: Gaussian使用
source: keinsci
year: 2022
cards: 5
---

# ��Windows��ʹ��gau_orca�ӿڵļ򵥷��� — 知识卡片

## 1. Windows 下 ORCA 通过 WSL 运行提升速度

Windows 下直接运行 ORCA 速度较慢，可通过 WSL 在 Linux 环境下运行 ORCA 以提升计算速度。在 Windows 环境中，可使用特定接口调用 WSL 下的 ORCA 程序进行计算。

---

## 2. 配置 Cmder 路径

安装 Cmder 后，需将其路径 `E:\cmder\vendor\git-for-windows\usr\bin` 添加至系统环境变量中。

---

## 3. 安装 Windows 版 gfortran

前往 MinGW-w64 官方项目页面下载并安装 Windows 环境下的 gfortran 编译器，该编译器用于编译 `extorca.f90` 文件。

---

## 4. 确保 G09 可被外部调用

需确保 Gaussian 09 (g09) 能够在系统环境中被正确调用或配置。

---

## 5. 编写外部调用脚本命令

在编写输入文件时，应将外部调用参数设置为 `external='./orca.sh'` 或 `external='sh ./orca.sh'`，以完成调用配置。
