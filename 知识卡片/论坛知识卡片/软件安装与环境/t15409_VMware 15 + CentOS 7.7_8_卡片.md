---
key: t15409
title: VMware 15 + CentOS 7.7/8.0�������Ϳͻ���֮�俽���ļ�ʧ�ܵĽ���취
url: http://bbs.keinsci.com/thread-15409-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2019
cards: 5
---

# VMware 15 + CentOS 7.7/8.0�������Ϳͻ���֮�俽���ļ�ʧ�ܵĽ���취 — 知识卡片

## 1. CentOS 7.x 版本兼容性

CentOS 7.7 是 CentOS 7.x 系列中的一个版本，该系列的最终维护版本为 7.9。旧版本如 7.6 压缩包的某些操作按钮在当前目录下可能存在显示 Bug，导致按钮不显示或用户无法操作。

---

## 2. VMware Tools 安装界面异常

在 VMware 15（特别是 15.5.1 版本）上安装 CentOS 7.7 时，直接从宿主机拖拽文件到虚拟机可能失败，无法直观地看到拖拽的文件图标、名称或目标目录。

---

## 3. 自动安装 open-vm-tools 的故障排除

通过执行命令 `yum remove open-vm-tools` 可以卸载系统自动安装的 open-vm-tools。卸载后，需选择虚拟机菜单中的“重新安装 VMware Tools”选项来尝试修复共享文件夹功能异常的问题。

---

## 4. VMware Tools 手动安装步骤

解压 VMware Tools 压缩包后，进入解压目录并运行 `.pl` 后缀的脚资料件。安装过程中遇到询问时输入 `yes`，其余询问直接按回车键确认，完成手动安装后即可实现宿主机与客户机之间的文件拖拽功能。

---

## 5. VMware 15.x 与 CentOS 8 的兼容性

VMware 15.x 配合 CentOS 8 系统可以直接支持文件拖拽功能，无需额外配置。若在此环境下拖拽文件不生效，手动安装 VMware Tools 即可解决该问题。
