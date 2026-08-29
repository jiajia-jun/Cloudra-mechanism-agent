---
key: t26976
title: ͨ��VcXsrv+xfce4ʵ����Windows�����²���Ubuntu-WSL2�е�VMD
url: http://bbs.keinsci.com/thread-26976-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 6
---

# ͨ��VcXsrv+xfce4ʵ����Windows�����²���Ubuntu-WSL2�е�VMD — 知识卡片

## 1. VMD 在不同操作系统环境下的兼容性与内存限制

VMD 在 Windows 32 位版本下的运行受限于 2GB 内存寻址空间，Windows 64 位版本可正常使用，Linux 64 位版本可通过 VMware 等虚拟机或直接在实体 Linux 系统下运行。Windows 32 位系统结合 Linux 环境可通过配置 PATH 变量安装 VMD。
- Windows 32 位版本内存限制为 2GB。

---

## 2. WSL2 运行图形化界面程序的环境要求

在 Windows 10 21H2 及以上版本或 Windows 11 中，配合最新版本的 WSL2，可以使用官方推出的 WSLg 功能实现 Linux 图形化程序的运行。若不使用 WSLg，需通过 VcXsrv 配合 xfce4 桌面环境实现图形转发。
- WSLg 功能官方介绍链接：http://bbs.keinsci.com/thread-27112-1-1.html

---

## 3. VMD 在 WSL2 环境下的依赖组件与安装顺序

在 WSL2 环境下安装 VMD 前，需先行安装 CUDA（若有 GPU 加速需求）和 xfce4 桌面环境。安装 xfce4 的命令为 `sudo apt install -y xfce4`。若已安装 CUDA，VMD 安装过程可自动检测到相关环境。
- 安装 xfce4 命令：`sudo apt install -y xfce4`

---

## 4. WSL2 配置 DISPLAY 环境变量的方法

通过读取 `/etc/resolv.conf` 文件中的 nameserver 地址，可以自动获取 Windows 主机的 IP 地址并设置为 DISPLAY 环境变量。需编辑 `~/.bashrc` 文件，添加 `export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0` 并在 WSL2 终端下生效。
- 添加命令：`export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0`

---

## 5. Windows 端 VcXsrv 的下载与配置

VcXsrv 是 Windows 端用于 X Window 系统的图形界面服务器，下载地址为 SourceForge 项目页。安装后需运行 XLaunch，选择 "Multiple windows" 模式、"Start no client"，并取消勾选 "Disable access control"。配置完成后若弹出防火墙提示，需允许访问。
- 下载地址：https://sourceforge.net/projects/vcxsrv/

---

## 6. VMD 在 WSL2 下的启动验证

在 WSL2 环境下输入 `vmd` 命令启动程序，若成功显示 VMD 图形界面或终端显示版本信息（如 "VMD for LINUXAMD64, version 1.9.3"），则表明图形转发配置成功。启动后即可在 Linux 图形界面下使用 VMD。
- 启动命令：`vmd`
