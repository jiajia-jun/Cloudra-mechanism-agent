---
key: t23036
title: ��CentOS 8�°�װQtGrace�ķ���
url: http://bbs.keinsci.com/thread-23036-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 7
---

# ��CentOS 8�°�װQtGrace�ķ��� — 知识卡片

## 1. CentOS 7 安装 xmgrace

在 CentOS 7 系统中，可通过 yum 安装 EPEL 源，随后使用 yum install grace 命令直接安装 xmgrace 绘图软件。
- 该方法适用于 CentOS 7 环境。
- 命令为 yum install epel-release 和 yum install grace。

---

## 2. CentOS 8 xmgrace 安装限制

在 CentOS 8 及对应版本的 EPEL 源中，停止维护时默认不包含 grace 软件包，无法直接通过 yum 或 dnf 命令安装 xmgrace。
- 适用于 CentOS 8 系统。
- 需寻求替代方案如 QtGrace。

---

## 3. QtGrace 功能特点

QtGrace 是基于 Qt 开发的 Grace 版本，其用法与 xmgrace 区别不大，但界面更美观且支持更多功能扩展。
- 适用于 xmgrace 停止维护的系统环境。
- 具备更好的图形界面和扩展性。

---

## 4. CentOS 8 Stream 安装 Qt 依赖

在 CentOS 8 Stream 系统中编译安装 QtGrace，需使用 dnf 安装 qt5-qtbase-devel 和 qt5-qtsvg-devel 依赖包，并创建 qmake-qt5 到 qmake 的软链接。
- 必须执行 dnf install qt5-qtbase-devel。
- 必须执行 dnf install qt5-qtsvg-devel。
- 必须执行 ln -s /usr/bin/qmake-qt5 /usr/bin/qmake。

---

## 5. QtGrace 源码编译

下载并解压 QtGrace 源码包（如 qtgrace_v026_src.zip）后，在解压目录下直接执行 make 命令即可开始编译。
- 源码文件名为 qtgrace_v026_src.zip。
- 编译命令为 make。

---

## 6. QtGrace 环境变量配置

编译完成后，需将 QtGrace 的 bin 目录路径（如 /sob/qtgrace_v026_src/bin）添加到 PATH 环境变量中，可通过修改 ~/.bashrc 文件实现。
- 配置语句为 export PATH=$PATH:/sob/qtgrace_v026_src/bin。
- 重新登录终端后生效，可直接使用 qtgrace 命令。

---

## 7. CentOS 7.x 安装 QtGrace 依赖

在 CentOS 7.x 系统中安装 QtGrace，相应的依赖安装步骤为使用 yum 安装 qt-devel，并将 qmake-qt4 链接到 qmake。
- 命令为 yum install qt-devel。
- 命令为 ln -s /usr/bin/qmake-qt4 /usr/bin/qmake。
