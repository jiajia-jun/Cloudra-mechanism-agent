---
key: t29302
title: ���� docker Ϊ wsl ��װ centos7
url: http://bbs.keinsci.com/thread-29302-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 8
---

# ���� docker Ϊ wsl ��װ centos7 — 知识卡片

## 1. Windows 下安装 CentOS7 版本 WSL 的背景与需求

在 Windows 上运行 WSL 时，Microsoft Store 提供的 Ubuntu-20.04、openEuler 或 CentOS8 等发行版可能因 glibc 版本不匹配导致某些遗留软件无法运行。为解决兼容性问题，需要通过 Docker 导入镜像的方式在 WSL 中部署 CentOS7。

---

## 2. 安装前的准备工作与文档参考

实现 WSL 自定义发行版可参照微软官方文档进行操作。安装前需确保已安装 WSL2，详细步骤可参考 Microsoft 官方的手动安装指南。

---

## 3. Docker 获取并运行 CentOS7 容器的命令

在安装 Ubuntu-20.04 和 Docker Desktop 后，需将 Linux Shell 切换至 ubuntu-20.04 环境执行相关命令。操作步骤包括拉取镜像、运行实例以及查看容器 ID，具体命令如下：
- docker pull centos:centos7
- docker run -t centos:centos7 bash ls /
- docker container ls -a

---

## 4. 导出 CentOS7 容器为 Tar 文件

导出容器时需注意 Windows 的磁盘自动挂载于 /mnt 目录下。使用 export 命令将容器导出为 tar 文件，命令格式如下：
- export {容器ID} > {tar保存位置}/centos.tar

---

## 5. 在 WSL 中导入 CentOS7 镜像

切换至 PowerShell 执行导入命令，需注意路径格式应使用反斜杠 `\` 而非正斜杠 `/`。具体命令如下：
- wsl --import CentOS7 {安装预设的目标目录} {tar保存位置}\centos7.tar

---

## 6. 设置 WSL 默认发行版与资源配置

CentOS7 导入完成后，可在其内部安装常用软件。若需将其设为默认 Linux Shell，可在 PowerShell 执行 `wslconfig /set-default CentOS7`。若需修改 WSL 使用的核心数或内存，可在用户目录下创建或修改 `.wslconfig` 文件。

---

## 7. WSL2 资源限制配置文件内容

通过编辑 `.wslconfig` 文件可以对 WSL2 的处理器数量、内存大小和交换空间进行限制。配置文件内容示例如下：
- [wsl2]
- processors=8
- memory=8GB
- swap=8GB
- localhostForwarding=true

---

## 8. 软件兼容性与 AVX512 指令集注意事项

在使用编译软件或特定指令集时，需注意第 12 代 i 系处理器对 AVX512 的杀毒或兼容性问题。
