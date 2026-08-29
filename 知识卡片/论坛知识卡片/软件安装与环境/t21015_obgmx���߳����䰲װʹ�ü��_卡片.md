---
key: t21015
title: obgmx���߳����䰲װʹ�ü��
url: http://bbs.keinsci.com/thread-21015-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2020
cards: 7
---

# obgmx���߳����䰲װʹ�ü�� — 知识卡片

## 1. OBGMX 工具简介

OBGMX 是一个基于 Web 的生成器，用于为分子和周期性系统生成 GROMACS 拓扑文件，使用通用力场 (UFF)。该工具由 G. Garberoglio 开发，相关文献发表于 J. Comput. Chem. 33 (2012), 2204-2208，DOI 为 10.1002/jcc.23049。

---

## 2. OBGMX 依赖环境

OBGMX 依赖于 OpenBabel，详细安装步骤可参考相关文档。示例中使用的是 OpenBabel 2.3.2 版本，该版本在 Ubuntu 下编译后也可在 CentOS 7.6 环境下使用。

---

## 3. OBGMX 安装步骤

通过 yum 安装依赖并解压源码包后，需创建 `/usr/local/ob-gg-232` 目录。将解压出的 `share` 文件夹移动至该路径下，随后即可在当前目录通过 `./obgmx` 运行程序。

---

## 4. OBGMX 安装命令列表

安装过程涉及的具体命令如下：`yum -y install openbabel 2.3.2`、`tar -xjf obgmx.tar.bz2`、`mkdir /usr/local/ob-gg-232` 以及 `mv ./share /usr/local/ob-gg-232`。

---

## 5. OBGMX 基本用法

OBGMX 的基本调用格式为 `./obgmx [options] <filename>`。支持的输入文件格式包括 xyz 和 mol2 等常见分子结构文件。

---

## 6. OBGMX 参数选项详情

OBGMX 提供多个功能选项：`-h` 表示在计算能量前加氢；`-d` 用于包含调试语句；`-LB` 指定使用 Lorentz-Berthelot 混合规则（默认为几何规则）；`-14 mult` 设置 1-4 相互作用乘法因子（默认为 1.0）；`-H` 指定角度势能使用谐波形式（默认为余弦形式）。

---

## 7. OBGMX 几何数据参数

`-G idx` 选项用于指定几何数据类型，参数 idx 为选项的按位或 (OR) 组合：1 代表键长，2 代表键角，4 代表二面角。
