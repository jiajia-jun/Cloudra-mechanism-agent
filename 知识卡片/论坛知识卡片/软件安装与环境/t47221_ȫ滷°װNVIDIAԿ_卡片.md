---
key: t47221
title: ȫ�������滷���°�װNVIDIA�Կ�����������Ҫ����ճ�������
url: http://bbs.keinsci.com/thread-47221-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 8
---

# ȫ�������滷���°�װNVIDIA�Կ�����������Ҫ����ճ������� — 知识卡片

## 1. Rocky Linux 禁用 nouveau 驱动

在安装 NVIDIA 显卡驱动前需手动禁用系统自带的 nouveau 驱动。该操作是顺畅安装的必要前提。通过禁用该驱动可以避免与 NVIDIA 官方驱动产生冲突。后续只需按照特定命令顺序执行即可完成自动安装。

---

## 2. 软件源缓存与 CRB 仓库启用

执行 `sudo dnf makecache` 命令更新软件源缓存。运行 `sudo dnf config-manager --set-enabled crb` 启用 CRB 仓库。这些步骤是安装依赖包前的准备工作。适用于 Rocky Linux 系统。已测试环境包括 Rocky Linux 9.4 全新安装以及 Rocky Linux 8.10 最小化安装。

---

## 3. EPEL 仓库安装

使用 `sudo dnf install -y epel-release -y` 安装 EPEL 仓库。使用 `sudo dnf install -y epel-next-release -y` 安装 EPEL Next 仓库。安装完成后需再次运行 `sudo dnf makecache` 更新缓存。这些仓库提供了额外的软件包支持。

---

## 4. 内核与开发工具依赖安装

执行长命令安装内核头文件、开发包及编译工具。命令包含 `kernel-headers-$(uname -r)`、`kernel-devel-$(uname -r)`、`gcc`、`gcc-c++`、`dkms` 等组件。同时还安装了 `pciutils`、`elfutils-libelf-devel`、`libglvnd-opengl`、`libglvnd-glx` 等图形与硬件相关库。该步骤确保了驱动编译和运行所需的环境。

---

## 5. NVIDIA CUDA 仓库配置

使用 `sudo dnf config-manager --add-repo` 命令添加 NVIDIA CUDA 仓库。仓库地址为 `http://developer.download.nvidia.com/compute/cuda/repos/rhel9/$(uname -i)/cuda-rhel9.repo`。该地址会根据系统架构变量 `$(uname -i)` 自动调整。添加后需再次执行 `sudo dnf makecache`。

---

## 6. NVIDIA 驱动模块安装

使用 `sudo dnf module install -y nvidia-driver:latest-dkms` 安装 NVIDIA 驱动模块。该命令利用 DKMS 方式安装最新版本的驱动。安装过程顺利且无卡顿。驱动占用空间极小，约为 0.5G。

---

## 7. 驱动安装验证

安装完成后运行 `nvidia-smi` 命令验证驱动是否正常工作。该命令用于查看显卡状态和驱动信息。若驱动安装成功，屏幕将显示 GPU 详细信息表格。

---

## 8. 原文故障现象

显卡驱动虽然安装成功，但在 `nvidia-smi` 验证时出现了莫名的错误。该错误的具体原因尚未查明。尽管安装过程看似顺畅，但驱动无法正常查询或调用。
