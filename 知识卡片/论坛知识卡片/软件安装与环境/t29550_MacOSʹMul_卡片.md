---
key: t29550
title: ��MacOS��ʹ�����������Multiwfn���°�
url: http://bbs.keinsci.com/thread-29550-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 7
---

# ��MacOS��ʹ�����������Multiwfn���°� — 知识卡片

## 1. Multiwfn 软件简介

Multiwfn 是一款实现波函数分析与化学可视化计算的关键多任务波函数分析程序。该软件具有免费、开源、高效、用户友好和功能丰富等特点，支持绝大多数波函数分析的重要功能。Multiwfn 目前在全球范围内已有广泛应用，并被超过 9000 篇学术论文引用，涵盖 80 多个国家。

---

## 2. MacOS 系统兼容性说明

在 3.7 版本之前，Multiwfn 曾直接提供 MacOS 系统支持的二进制文件以及该系统下的源代码。Multiwfn 新版本已不再对 MacOS 系统提供直接支持，在 MacOS 系统下顺利使用 Multiwfn 需要采用额外的配置方式。

---

## 3. 安装 Docker 环境步骤

在终端通过 brew 命令安装 Docker：`# brew install docker`。也可以访问 Docker 官网下载并安装对应版本的 Docker Desktop，安装时应根据芯片类型（Intel 芯片选择第一个，苹果芯片选择第二个）进行选择。

---

## 4. 拉取 Ubuntu 镜像

打开 Docker，进入 Images 界面可查看当前系统已安装的镜像。在终端执行命令 `# docker pull ubuntu` 即可拉取 Ubuntu 镜像，拉取成功后在 REPOSITORY 列表中会出现 ubuntu 相关项。

---

## 5. 运行容器并挂载目录

执行命令 `# docker run -t -i -v /Users/dai_jh/OneDrive/MULTIWFN:/Multiwfn ubuntu /bin/bash` 来运行 ubuntu 容器。命令中的 `/Users/dai_jh/OneDrive/MULTIWFN` 应替换为宿主机上存放 Multiwfn 相关文件的实际路径，`/Multiwfn` 为容器内的挂载路径。如果上述路径下的目录不存在，执行该命令后会自动创建。

---

## 6. 下载与解压 Multiwfn

从 Multiwfn 官网下载最新版 Linux 64 位二进制文件（可选 GUI 或 no_GUI 版本）或 Linux 下的源代码包。将下载的文件放入宿主机挂载目录，在容器终端的 `/Multiwfn` 目录下执行 `# ls` 确认文件存在，随后依次执行 `# apt-get update`、`# apt-get install unzip` 和 `# unzip Multiwfn_3.8_dev_bin_Linux.zip` 进行解压。

---

## 7. 编译与运行 Multiwfn

对于下载的源代码包，解压后进入解压目录执行 `# make` 命令开始编译。如果编译过程中提示缺少库文件，可通过 `# apt-get install [对应版本]lib` 安装依赖库。编译或解压二进制文件后，在当前目录执行 `# ./Multiwfn [输入文件名]` 即可开始计算。
