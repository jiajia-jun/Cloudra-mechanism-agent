---
key: t54080
title: ������д��mwfn�ļ���д�⣺libmwfn
url: http://bbs.keinsci.com/thread-54080-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2025
cards: 8
---

# ������д��mwfn�ļ���д�⣺libmwfn — 知识卡片

## 1. 写入mwfn文件的便捷方案

使用C++或Python直接编写mwfn文件较为繁琐，可通过pybind11将C++编译为Python动态库以简化操作。只需编写C++代码并引入pybind11头文件，即可编译出供Python调用的动态库。推荐方式是使用libmwfn，它同时提供C++和Python接口，方便开发者调用功能。

---

## 2. libmwfn 项目

libmwfn 是一个用于写入mwfn文件的开源项目，同时提供C++和Python接口。该工具支持获取和修改mwfn输入文件的内容，包括原子核位置、基组信息、波函数数据等。对于有多种写入mwfn文件需求的场景，直接使用或基于libmwfn开发比自行编写更为便捷。

---

## 3. C++ 环境依赖

C++ 编译环境需要依赖 Eigen3 库、支持 C++20 标准的编译器以及 GNU make 工具。Eigen3 是 header-only 库，下载后直接包含即可使用。确保编译器版本符合 C++20 标准要求，否则可能导致编译失败。

---

## 4. C++ 编译安装步骤

通过 git clone 命令下载 libmwfn 源码后，需修改 Makefile 文件。在 Makefile 中指定 C++ 编译器以及 Eigen3 库的路径。配置完成后，执行 `make -j` 命令进行编译和安装。

---

## 5. Python 环境与安装

Python 环境需满足版本不低于 3.7，并已安装 setuptools 和 pip 工具。安装 libmwfn 的 Python 版本可直接使用 pip 命令执行 `pip install libmwfn`。安装完成后即可在 Python 代码中调用 libmwfn 的功能。

---

## 6. libmwfn 主要功能

libmwfn 支持获取和修改mwfn输入文件中的原子核位置、基组信息、原始波函数系数、每个原子的轨道数量信息。支持构建重叠矩阵、密度矩阵、Fock矩阵以及原子-轨道-基组对应关系列表。此外还提供 Gram-Schmidt 和 Lowdin 正交化功能。

---

## 7. 临时不支持 ROHF

当前版本的 libmwfn 临时不支持 ROHF（Restricted Open-Shell Hartree-Fock）方法。在进行相关计算或文件写入时，需注意该限制，避免使用 ROHF 类型的输入数据。

---

## 8. 波函数存储顺序差异

mwfn 原生文档对波函数数据的存储顺序为 [d0, d+1, d-1, d+2, d-2]。libmwfn 内部存储顺序则采用 [d-2, d-1, d0, d+1, d+2]。在写入mwfn文件时，libmwfn 会自动调整顺序，以确保生成的文件符合 mwfn 内部要求的顺序。
