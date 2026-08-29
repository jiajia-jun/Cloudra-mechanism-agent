---
key: t29567
title: ���װ�װstandalone��XMVB
url: http://bbs.keinsci.com/thread-29567-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 10
---

# ���װ�װstandalone��XMVB — 知识卡片

## 1. 价键理论发展历程

价键理论 (VBT) 和分子轨道理论 (MOT) 几乎同时起源于20世纪，但在随后几十年的发展中VBT处于下风。VBT基于Heitler和London的双原子氢分子处理，能直观展示化学键的静态和动态性质，但在数学形式和计算上极为复杂。随着计算化学的发展，现代价键理论 (Modern Valence Bond Theory) 在近年来得到了应用和扩展。

---

## 2. XMVB 程序简介

XMVB 是由厦门大学团队开发的现代价键理论计算程序，擅长处理$\pi$共轭体系的离域问题。目前主流的 ab initio VB 程序还包括 TURTLE、VB2000 和 CRUNCH。XMVB 提供独立版 (Standalone) 和集成在 GAMESS 中的版本 (GAMESS-XMVB)。

---

## 3. 系统兼容性与 GLIBC 依赖

Standalone 版 XMVB 对系统环境有特定要求，通常需要 GLIBC 2.2.7 和 GFORTRAN 1.0/1.4。在 CentOS 7 上安装常因 GLIBC 版本不匹配 (CentOS 7 默认为 2.17) 而失败。直接升级系统的 glibc 和 gcc 风险较高且容易破坏系统稳定性。

---

## 4. 推荐的安装环境方案

为了避免系统依赖冲突，推荐使用 Docker 或 WSL2 (Windows Subsystem for Linux) 搭建 Ubuntu 18.04 环境来安装 XMVB。该方案兼容 Windows 10+ 和 Linux，通过容器或虚拟机技术隔离环境，降低了依赖库版本的配置难度。

---

## 5. Ubuntu 环境编译工具配置

在 Ubuntu 18.04 环境下，需要安装 gcc-5 和 gfortran-5 并将其设为默认版本。使用 `update-alternatives` 命令将 gcc、cpp 和 gfortran 链接到版本 5，并创建符号链接 `ln -s /usr/bin/gcc /usr/bin/cc` 以确保编译兼容性。

---

## 6. XMVB 安装步骤

从 XMVB 官方网站获取安装包 (如 xmvb3.0-linux-x86_64-gnu.tar.bz2) 后，解压并运行 `./post-install` 脚本。部分安装包可能缺少 data 文件夹，需从旧版本复制或联系开发团队补全。

---

## 7. 环境变量配置

安装完成后需将 XMVB 的 bin 目录路径添加到系统的 PATH 环境变量中。编辑 `~/.bashrc` 文件，添加 bin 路径，以使 `xmvb` 命令可在任意目录下执行。

---

## 8. XMVB 输入文件示例 (F2.xmi)

XMVB 的输入文件包含控制组 (`$ctrl`)、结构组 (`$str`)、轨道组 (`$orb`) 和基组重叠组 (`$gus`)。对于 F2 分子计算，需设置电子数 `nae=2`、轨道数 `nao=2`，并定义具体的轨道占据和结构列表。

---

## 9. XMVB 计算执行流程

XMVB 计算分为积分准备和主程序运行两步。首先执行 `preint tmp.input` 生成积分文件，然后运行 `xmvb F2.xmi` 执行能量计算。

---

## 10. 配合 GAMESS 使用建议

在使用 XMVB 进行计算前，推荐先运行 GAMESS 进行 HF 计算以获取分子轨道，这有助于可视化分析并生成后续 `.xmi` 文件所需的轨道信息。对于复杂体系的共轭连接，GAMESS-XMVB 版本提供了快速构建的便利。
