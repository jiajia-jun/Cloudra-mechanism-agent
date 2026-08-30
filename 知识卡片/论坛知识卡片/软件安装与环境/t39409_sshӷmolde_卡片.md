---
key: t39409
title: ���ssh���ӷ���������moldenʱX11ת��ʧ�ܵ�����
url: http://bbs.keinsci.com/thread-39409-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 11
---

# ���ssh���ӷ���������moldenʱX11ת��ʧ�ܵ����� — 知识卡片

## 1. Snap 应用与 Xauthority 配置问题

在基于 Red Hat 的系统（如 Almalinux 9）上通过 snap 安装的图形化应用（如 Molden）可能无法直接读取 `.Xauthority` 配置，导致 SSH 远程连接时 X11 转发失败。
- 解决方法是在 `/etc/profile` 或 `~/.bashrc` 文件中添加环境变量 `export XAUTHORITY=$HOME/.Xauthority`。

---

## 2. 安装 xorg-x11-xauth 软件包

X11 转发失败可能是因为缺少必要的认证软件包。
- 在 Almalinux 9 或 RHEL8 及以后的系统中，需使用 `sudo dnf install xorg-x11-xauth` 命令安装 `xorg-x11-xauth`（RHEL8 之前系统使用 `yum`）。

---

## 3. 启用 SSH X11 转发功能

确保 SSH 服务端配置允许 X11 转发。
- 编辑 `/etc/ssh/sshd_config` 文件，确认包含 `X11Forwarding yes` 配置项，并执行 `sudo systemctl restart sshd` 重启 sshd 服务。

---

## 4. 使用 SSH 调试模式测试连接

使用详细输出模式连接 SSH 以诊断 X11 转发问题。
- 连接命令为 `ssh -v -Y username@xxx.xxx.xxx.xxx`，通过输出的调试信息判断故障原因。

---

## 5. X11 转发常见错误提示及含义

SSH 连接日志中的特定错误提示对应不同的故障原因。
- 提示 "X11 forwarding requested but DISPLAY not set" 表示本地未安装 Xserver 或未正确设置 DISPLAY 环境变量。
- 提示 "X11 connection rejected because of wrong authentication" 表示认证错误，通常涉及 `.Xauthority` 文件或 SSH 配置问题。

---

## 6. 调整 SSH 配置解决认证错误

针对 X11 连接认证被拒绝的问题，可尝试修改 `/etc/ssh/sshd_config` 中的特定参数。
- 修改或添加配置项 `X11DisplayOffset 10` 和 `X11UseLocalhost yes`，保存后重启 sshd 服务。

---

## 7. 修复 .Xauthority 文件权限问题

若 `.Xauthority` 文件权限或所有者不正确，会导致 X11 认证失败。
- 可参考命令 `sudo cp /home/user1/.Xauthority ~/.Xauthority` 复制文件，执行 `chown user:usergroup ~/.Xauthority` 修改所有者，并执行 `chmod 600 ~/.Xauthority` 设置权限。

---

## 8. 使用 xauth 命令修复认证

部分解决方案建议通过 xauth 工具重新生成或合并认证信息。
- 切换至相关用户后，执行 `xauth list` 查看认证信息，并使用 `xauth add` 命令将列表中的信息添加到当前用户的 xauth 数据库中。

---

## 9. 安装 Molden (Snap 方式)

Molden 可通过 snap 包管理器进行安装。
- 安装命令为 `sudo snap install molden`。

---

## 10. Almalinux 9 安装 Snapd 环境准备

Almalinux 9 默认未安装 snapd，使用 snap 安装软件前需先配置环境。
- 依次执行以下命令：`sudo dnf install epel-release`、`sudo dnf install snapd`、`sudo systemctl enable --now snapd.socket` 以及 `sudo ln -s /var/lib/snapd/snap /snap`。

---

## 11. Molden 官方下载渠道

除了使用 snap 安装外，也可以直接从官方 FTP 下载 Molden。
- 可访问 https://ftp.science.ru.nl/Molden/ 获取软件安装包。
