---
key: t27112
title: WSL2��ͼʹ��wslg������ʱ��ʾ���� Can't open display: :0�Ľ����������VMDΪ��
url: http://bbs.keinsci.com/thread-27112-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2021
cards: 9
---

# WSL2��ͼʹ��wslg������ʱ��ʾ���� Can't open display: :0�Ľ����������VMDΪ�� — 知识卡片

## 1. WSL2 图形化显示方案

Windows 上显示 WSL 图形化界面的一种方案是使用 VcXsrv 搭配 xfce4，另一种方案是使用官方的 WSLg。

---

## 2. WSLg 报错：Can't open display: :0

在 WSLg 环境下在终端输入 `vmd` 命令时，如果提示 "Can't open display: :0"，可参考 Microsoft WSLg 官方 Wiki 进行诊断。

---

## 3. 排查步骤一：检查版本

解决 "Can't open display" 类型问题的第一步是确认 Windows 版本以及 WSL 是否已经更新。

---

## 4. 排查步骤二：设置环境变量

部分旧版配置或自定义操作可能导致 WSLg 环境变量失效，可在 `.bashrc` 文件中添加以下内容：
```
# display
export DISPLAY=:0
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
export PULSE_SERVER=/mnt/wslg/PulseServer
```

---

## 5. 排查步骤三：修复 .X11-Unix 链接

使用 `ls -la /tmp/.X11-unix` 命令检查目录，若显示指向 `/mnt/wslg/.X11-unix` 的软链接，则无需额外设定；若不是，则需执行以下命令修复：
```bash
sudo rm -r /tmp/.X11-unix
sudo ln -s /mnt/wslg/.X11-unix /tmp/.X11-unix
```

---

## 6. 验证 .X11-Unix 修复结果

执行修复命令后，输入 `ls /tmp/.X11-unix` 应显示 "X0"；输入 `ls -la /tmp/.X11-unix` 应显示 "/tmp/.X11-unix -> /mnt/wslg/.X11-unix"。

---

## 7. 配置快捷修复命令

为避免每次手动输入修复命令，可在 `~/.bashrc` 中添加别名设置：
```bash
# wslg
alias x11="sudo rm -r /tmp/.X11-unix && sudo ln -s /mnt/wslg/.X11-unix /tmp/.X11-unix"
```

---

## 8. 使用快捷修复命令

配置别名后重新加载终端，此后每次只需输入 `x11` 即可执行修复操作。"x11" 为命令别名，可根据偏好修改为其他名称。

---

## 9. 问题反馈渠道

如果尝试上述方法后问题仍未解决，且涉及硬件加速或特定操作异常，可向官方提交 issue 反馈。
