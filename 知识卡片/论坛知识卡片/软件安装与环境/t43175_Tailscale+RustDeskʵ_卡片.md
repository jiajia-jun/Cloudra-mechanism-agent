---
key: t43175
title: ����Tailscale+RustDeskʵ��������͸�Լ�Զ�̷���
url: http://bbs.keinsci.com/thread-43175-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 11
---

# ����Tailscale+RustDeskʵ��������͸�Լ�Զ�̷��� — 知识卡片

## 1. Tailscale 定义与功能

Tailscale 是一款开源软件，能够基于 WireGuard 协议构建虚拟局域网。该软件可实现设备间的透明穿透，使得处于不同网络环境的设备可以直接通过内网 IP 地址互相访问。

---

## 2. Windows 系统安装 Tailscale

在 Windows 系统中，用户可直接下载 Tailscale 安装包进行安装。安装完成后会自动跳转至登录页面，需选择相应的账号（如 Google 账号）完成登录。

---

## 3. Tailscale 管理控制台访问

用户可以点击 "visit the console" 按钮或直接访问 https://login.tailscale.com/admin/machines 进入管理控制台。在控制台中可以查看并记录设备的 IP 地址。

---

## 4. Linux 系统 Tailscale 安装命令

在 Linux 系统中，可以使用脚本命令进行一键安装：`curl -fsSL https://tailscale.com/install.sh | sh`。安装完成后，需执行 `tailscale up` 命令启动连接，随后点击链接即可完成登录认证。

---

## 5. Android 系统 Tailscale 安装与状态

Android 系统可直接安装 Tailscale App 并登录。连接成功后，状态栏显示应为 "Active"，若显示 "Stopped" 则表示未成功连接。

---

## 6. 连通性测试方法

Tailscale 组网完成后，可以使用 Ping 命令测试设备间的连通性。测试示例包括从家用笔记本 Ping 学校内网的服务器，若能 Ping 通则组网成功，且速度通常较快。

---

## 7. RustDesk 定义与 Tailscale 结合用途

RustDesk 是一款开源远程控制工具。结合 Tailscale 分配的 IP 地址，可以直接实现设备间的点对点直连，无需依赖中转服务器。

---

## 8. RustDesk 下载地址与安装

RustDesk 的下载地址为 https://github.com/rustdesk/rustdesk/releases。用户需根据自身操作系统选择对应的安装包进行下载和安装。

---

## 9. RustDesk 在 Linux 系统的使用注意事项

RustDesk 目前对 Linux 系统 Wayland 显示协议的支持尚不完善。建议在使用 Linux 系统时配合 X11 协议使用以获得更好的体验。

---

## 10. RustDesk ID 连接与 IP 直连

RustDesk 支持通过输入被控端的 ID 进行连接。在已安装 Tailscale 的环境下，也可以直接输入 Tailscale 分配的 IP 地址进行连接或传输文件。

---

## 11. Windows 远程桌面 RDP 性能对比

Windows 系统自带的远程桌面 (RDP) 协议是基于底层的屏幕图像指令实现的。相比其他方案，RDP 在远程操作时的传输速度更快，且画面体验更流畅。
