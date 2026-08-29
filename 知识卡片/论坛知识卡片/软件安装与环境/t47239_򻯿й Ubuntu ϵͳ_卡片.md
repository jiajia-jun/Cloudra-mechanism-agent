---
key: t47239
title: �򻯿��й��������� Ubuntu ϵͳ��ΪGView6 ���������ݷ�ʽ
url: http://bbs.keinsci.com/thread-47239-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 7
---

# �򻯿��й��������� Ubuntu ϵͳ��ΪGView6 ���������ݷ�ʽ — 知识卡片

## 1. Linux 系统 Gaussian 与 GView 启动方式

在 Linux 系统中运行 Gaussian 及 GView 通常需要通过终端用户界面执行命令，缺乏直观的图形化入口。将 GView 6 集成到桌面环境可以解决直接运行命令的不便，提升使用体验。

---

## 2. 准备 GView 6 图标资源

为 GView 6 创建桌面快捷方式需要预先准备相应的图标图片文件（.png）。图标文件需下载并传输至 Linux 系统中的指定目录备用。

---

## 3. GView 6 启动环境配置脚本

GView 6 依赖特定的环境变量才能正常运行，需编写 Shell 脚本（如 `start_gv.sh`）进行环境初始化。脚本内容需包含 Gaussian 16 的环境变量（如 `g16root`, `GAUSS_SCRDIR`）以及 GView 6 的库路径和可执行文件路径。

---

## 4. start_gv.sh 脚本内容示例

以下脚本示例展示了如何配置 Gaussian 16 和 GView 6 的运行环境：
```bash
#!/bin/bash

# gaussian16 环境配置
export g16root=$HOME/Software
export GAUSS_SCRDIR=$HOME/Software/g16/scratch
source $HOME/Software/g16/bsd/g16.profile
export PGI_FASTMATH_CPU=sandybridge

# gv6 环境配置
export GV_DIR=$HOME/Software/gv
export LIBPATH=$HOME/Software/gv
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$HOME/Software/gv/lib
export PATH=$PATH:$HOME/Software/gv

$HOME/Software/gv/gview.exe
```
脚本中的路径（如 `/Software`）需根据实际安装位置进行替换。

---

## 5. 创建 .desktop 桌面配置文件

在 Linux 中创建应用图标需要编写 `.desktop` 文件，该文件定义了应用的名称、图标位置、执行命令及类型。文件通常存放在用户目录下的 `~/.local/share/applications/` 路径中。

---

## 6. gview.desktop 文件编写示例

`gview.desktop` 文件的具体内容示例如下：
```text
[Desktop Entry]
Name=GView
Icon=/home/wxyhgk/Software/gv/gview.png
Exec=bash -c '/home/wxyhgk/Documents/Scripts/start_gv.sh'
Type=Application
Terminal=false
```
`Icon` 路径需指向实际的 GView 图标文件位置，`Exec` 路径需指向实际的 `start_gv.sh` 启动脚本位置。

---

## 7. 完成桌面图标集成

完成 `.desktop` 文件的编辑与保存后，GView 图标将出现在 Ubuntu 应用程序菜单中。用户即可通过点击图标直接启动 GView 6，实现了从命令行操作到图形化界面操作的转换。
