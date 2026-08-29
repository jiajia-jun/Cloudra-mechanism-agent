---
key: t55597
title: ��Rocky Linux 9.6�°�װmaui3.3.1�ĵ÷���
url: http://bbs.keinsci.com/thread-55597-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2025
cards: 9
---

# ��Rocky Linux 9.6�°�װmaui3.3.1�ĵ÷��� — 知识卡片

## 1. Rocky Linux 9.6 环境下 Maui 编译的 sed 版本兼容性

Rocky Linux 9.6 自带的 sed 版本（4.8）会导致 Maui 的 configure 过程报错，需要降级使用 sed 4.2.2（即 CentOS 7 的版本）。在编译前需保留系统原版 sed，指定旧版本 sed 路径进行 configure。

- PATH=/.../sed4.2.2/bin:$PATH ./configure --prefix=/usr/local/torque --with-pbs=/usr/local/torque

---

## 2. Maui 源码编译时的全局变量重复定义错误

在 Maui 的 make 编译过程中，可能会出现 `multiple definition of 'MSim'` 错误，原因在于源文件（如 mprof.c）中缺少 `extern` 声明导致全局变量重复定义。需使用 vi 编辑器修改相关源文件，在变量定义处添加 `extern` 关键字。

- extern int MSim

---

## 3. Maui 3.3.1 需修改 `extern` 的具体文件与位置

Maui 3.3.1 源码中存在约 5-6 处缺少 `extern` 声明的地方，主要位于 `mprof.c` 文件（例如第 178 行）。需要逐一检查并修正这些重复定义错误，修改完成后即可成功执行 make 和 make install。

---

## 4. Systemd 服务文件中的 PIDFile 路径权限设置

在创建 Maui 的 systemd 服务文件时，PIDFile 路径不能设置为 `/run/` 下的默认位置，否则会报错 "Operation not permitted"。应将 PIDFile 路径指定为 `/var/spool/maui/maui.pid`，该目录通常具有可写权限（755）。

- PIDFile=/var/spool/maui/maui.pid

---

## 5. Rocky Linux 9.6 下 Maui 的 Systemd 服务配置内容

由于 Rocky Linux 9.6 不再支持 chkconfig，需在 `/etc/systemd/system/` 下手动创建 `maui.d.service` 文件来管理服务。服务文件应包含 `[Unit]`、`[Service]`（Type 设为 forking）和 `[Install]` 段落，并通过 ExecStart/Stop 调用 init.d 脚本。

- ExecStart=/etc/init.d/maui.d start
- ExecStop=/etc/init.d/maui.d stop

---

## 6. Maui 与 Torque 的动态库路径配置

为了确保系统能正确加载 Maui 和 Torque 的动态库，需要将它们的库路径写入配置文件。将 `/usr/local/torque/lib` 和 `/usr/local/maui/lib` 分别写入 `/etc/ld.so.conf.d/` 下的对应配置文件中，并执行 ldconfig 刷新。

- echo "/usr/local/torque/lib" > /etc/ld.so.conf.d/torque.conf
- echo "/usr/local/maui/lib" > /etc/ld.so.conf.d/maui.conf
- ldconfig

---

## 7. Maui 服务的启用、启动与状态检查

完成服务文件配置后，需执行 `systemctl daemon-reload` 重新加载配置，随后启用并启动 Maui 服务。使用 `systemctl status maui.service` 检查服务运行状态。

- systemctl daemon-reload
- systemctl enable maui.service
- systemctl start maui.service
- systemctl status maui.service

---

## 8. PBS 调度器与 Maui 的切换及环境变量配置

在启动 Maui 前，需要停止系统原有的 PBS 调度器 `pbs_sched`，避免冲突。同时，建议将 Maui 的环境变量脚本 `maui.sh` 复制到 `/etc/profile.d/` 目录下以便加载。

- systemctl stop pbs_sched
- cp etc/maui.sh /etc/profile.d/

---

## 9. Maui 编译前对系统工具的版本检查

在 Rocky Linux 9.6 上安装 Maui 前，必须检查 GCC 和 sed 等基础工具的版本。高版本的 GCC（如 11.2.1）和 sed（如 4.8）可能导致编译或配置失败，建议先安装 PBS Torque，并针对 sed 版本问题进行预处理。
