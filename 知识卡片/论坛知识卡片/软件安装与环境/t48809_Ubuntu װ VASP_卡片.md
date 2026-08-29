---
key: t48809
title: Ubuntu ��װ VASP
url: http://bbs.keinsci.com/thread-48809-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 2
---

# Ubuntu ��װ VASP — 知识卡片

## 1. 系统环境与软件版本

资料涉及的测试基于 Ubuntu 22.04 操作系统、AMD EPYC 7k62 处理器，使用 VASP 6.4.3 版本及 OpenMPI 4.1.1。测试对比了 ChatGPT 和 Notion AI 在辅助安装 VASP 时的表现。
- 记录了具体的硬件配置、操作系统及并行环境软件版本号。

---

## 2. 安装依赖工具 tmux

在编译安装 VASP 之前，建议先安装终端复用工具 tmux。
- tmux 可用于保持编译会话不中断，防止网络波动或断连导致编译失败。
