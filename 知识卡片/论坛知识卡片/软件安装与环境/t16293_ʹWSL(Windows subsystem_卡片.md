---
key: t16293
title: ʹ��WSL(Windows subsystem for linux)��win10ϵͳ����Linux�桰������������
url: http://bbs.keinsci.com/thread-16293-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2020
cards: 16
---

# ʹ��WSL(Windows subsystem for linux)��win10ϵͳ����Linux�桰������������ — 知识卡片

## 1. WSL2 默认挂载权限

WSL2 默认挂载 Windows 磁盘目录（如 /mnt/c）的权限为 777。
- 在此类挂载目录下运行 Gaussian 计算可能存在风险。

---

## 2. Gaussian 软件放置建议

不建议将 Gaussian 程序文件（如 g09 文件夹）放置在 /mnt 等挂载目录下。
- 建议将软件安装在 Linux 文件系统的内部目录中，例如 /home/用户名/apps。

---

## 3. WSL 安装前提

WSL 功能不支持 Windows 10 S 系统。
- 安装前需确认当前系统版本为标准的 Windows 10。

---

## 4. 启用 WSL 功能步骤

在 Windows 中进入“控制面板\程序\程序和功能”，点击右侧“启用或关闭 Windows 功能”。
- 在弹出的对话框中勾选“Windows Subsystem for Linux”复选框，点击确定并等待系统安装完成。

---

## 5. Ubuntu 发行版获取

在 Microsoft Store 中搜索并安装 Ubuntu。
- 下载前建议将 Store 账户区域切换至中国或其他非限制区域，以便获取 Linux 应用。

---

## 6. Ubuntu 初始设置

Ubuntu 安装完成后点击打开，首次启动需要设置 UNIX 用户名和密码。
- 例如设置用户名为 iceeyes。

---

## 7. 创建软件安装目录

使用 mkdir 命令在用户目录下创建 apps 文件夹，用于存放安装软件。
- 命令示例：`mkdir /home/iceeyes/apps`。

---

## 8. Windows 交换目录创建

在 Windows 系统的 C 盘根目录下新建一个文件夹，命名为 mywslfiles。
- 该目录用于在 Windows 和 WSL 之间交换文件，避免直接在 Linux 系统盘下操作。

---

## 9. 访问 Windows 目录

在 Linux 终端中使用 `cd /mnt/c/mywslfiles` 命令。
- 可以进入刚才在 C 盘创建的 mywslfiles 目录，以便后续文件传输。

---

## 10. 拷贝 Gaussian 至 Linux 内部

将准备好的 Gaussian 安装文件从 Windows 目录拷贝至 Linux 内部 apps 目录。
- 命令示例：`cp -r /mnt/c/mywslfiles/g09 /home/iceeyes/apps/`。

---

## 11. 进入程序目录与创建临时目录

切换至 g09 目录并创建名为 scratch 的临时文件夹。
- 命令依次为：`cd /home/iceeyes/apps/g09` 和 `mkdir scratch`。

---

## 12. 修改文件权限

使用 chmod 命令递归修改当前目录下所有文件的权限。
- 命令示例：`chmod 750 -R *`。

---

## 13. 配置环境变量

使用 vim 编辑 ~/.bashrc 文件，添加 Gaussian 所需的环境变量配置。
- 需添加的内容如下：
```
export g09root=/home/iceeyes/apps
export GAUSS_SCRDIR=/home/iceeyes/apps/g09/scratch
source /home/iceeyes/apps/g09/bsd/g09.profile
```

---

## 14. 使配置生效

编辑完 ~/.bashrc 后，需要退出 Ubuntu 终端并重新打开。
- 这样才能使新添加的环境变量生效。

---

## 15. 计算文件放置位置

用于计算的输入文件（.gjf）建议放置在 /mnt/c/mywslfiles 目录下。
- 这样方便在 Windows 和 WSL 环境中共同访问和管理文件。

---

## 16. 计算性能对比数据

针对 opt b3lyp/6-31g(d) em=gd3 双核 150MW 内存任务的测试耗时数据如下。
- g16w a03 64bit 耗时 14分59秒。
- g16 a03 vmware /centos7.8 耗时 4分25秒。
- g16 a03 wsl /ubuntu 耗时 3分51秒。
