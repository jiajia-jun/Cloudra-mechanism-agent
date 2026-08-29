---
key: t29399
title: Multiwfn 3.8 (dev) on macOS
url: http://bbs.keinsci.com/thread-29399-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 9
---

# Multiwfn 3.8 (dev) on macOS — 知识卡片

## 1. macOS 上的 Multiwfn 运行环境现状

Gaussian 已推出 macOS 版本，但 Multiwfn 仅支持 Windows 和 Linux 系统。macOS 用户若需使用 Multiwfn，通常需要借助虚拟机或 Docker 等工具在 Linux 环境下运行。Docker 方案可作为解决 Multiwfn 在 macOS 上兼容性问题的有效手段。

---

## 2. Docker 容器化的优势

利用 Docker 运行 Multiwfn 能够屏蔽不同操作系统间的差异，解决 macOS 版本缺失的问题。该方案便于分发和部署，用户无需进行复杂的系统配置即可获得统一的 Linux 运行环境。相关的项目代码和详细文档可在 GitHub 上获取。

---

## 3. Multiwfn Docker 镜像的使用注意事项

Docker 镜像内部未包含 Multiwfn 的可执行文件，需要用户在宿主机下载并提供。Multiwfn 的可执行文件体积较大且包含大量依赖，直接打包进镜像会导致构建缓慢和分发困难。针对 Multiwfn 的不同版本，Docker 方案提供了灵活的挂载机制以供切换使用。

---

## 4. 命令行版本 (noGUI) 的镜像拉取

在确保已安装 Docker 的前提下，使用以下命令拉取 Multiwfn 的 noGUI 版本镜像：
- $ docker pull mizubai/multiwfn:nogui

---

## 5. 命令行版本 (noGUI) 的运行命令

使用以下命令启动容器并运行 Multiwfn：
- $ docker run -it --rm -v "$(pwd)":/source -v /path/to/Multiwfn_noGUI:/opt/Multiwfn_bin mizubai/multiwfn:nogui sh -c 'ulimit -s unlimited && Multiwfn'
命令中第一个 -v 将当前目录映射为容器内的 /source，第二个 -v 将宿主机上的 Multiwfn 目录映射为容器内的 /opt/Multiwfn_bin，并将 /path/to/Multiwfn_noGUI 替换为实际路径。

---

## 6. 图形界面版本 (GUI) 的 XQuartz 依赖

若需在 macOS 上使用 Multiwfn 的图形界面功能，必须先安装 XQuartz 以提供 X11 支持。Docker 容器中的应用程序将通过 X11 协议与宿主机的 XQuartz 进行通信以显示图形界面。安装完成后，需在终端执行允许 X11 连接的命令：
- $ xhost + localhost

---

## 7. 图形界面版本 (GUI) 的镜像拉取

运行 GUI 版本前，需使用以下命令拉取对应的 Docker 镜像：
- $ docker pull mizubai/multiwfn:gui

---

## 8. 图形界面版本 (GUI) 的运行命令

执行以下命令启动支持图形界面的 Multiwfn：
- $ docker run -it --rm -v "$(pwd)":/source -v /path/to/Multiwfn:/opt/Multiwfn_bin -v /tmp/.X11-unix:/tmp/.X11-unix -e DISPLAY=host.docker.internal:0 multiwfn:gui sh -c 'ulimit -s unlimited && Multiwfn'
命令中增加了 X11 套接字映射和显示环境变量设置，需将 /path/to/Multiwfn 替换为实际的程序路径。

---

## 9. macOS 下的命令别名设置

为简化 Multiwfn 的启动操作，可在 .bash_profile 或 .zshrc 配置文件中添加 alias。macOS Catalina 默认使用 zsh，建议修改 .zshrc 文件。添加以下别名后，直接输入 Multiwfn 即可启动 GUI 版本：
- alias Multiwfn='docker run -it --rm -v "$(pwd)":/source -v /path/to/Multiwfn:/opt/Multiwfn_bin -v /tmp/.X11-unix:/tmp/.X11-unix -e DISPLAY=host.docker.internal:0 multiwfn:gui sh -c "ulimit -s unlimited && Multiwfn"'
