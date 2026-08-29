---
key: b564
title: XCrySDen在CentOS上的傻瓜式安装方法
url: http://sobereva.com/564
domain: 软件安装与环境
source: blog
year: 2020
cards: 9
---

# XCrySDen在CentOS上的傻瓜式安装方法 — 知识卡片

## 1. XCrySDen简介与用途

XCrySDen 是第一性原理程序 Quantum ESPRESSO 用户常用的工具软件，支持查看输入输出文件、显示轨迹及设置 k 点，且作图效果良好。该软件在 Ubuntu 系统上较易运行，但在 CentOS 系统上安装运行存在一定难度。官方较新版本（如 1.6.2）仅提供 shared 版，其依赖的动态库在 CentOS 中可能缺乏对应源。为解决 CentOS 环境下的兼容性问题，已提供经过编译的版本及修改过的源代码包。

---

## 2. 预编译版XCrySDen的下载与运行

下载地址为 http://原作者.com/attach/564/xcrysden-1.6.2_原作者.tar.gz。文件解压后进入目录，直接运行命令 ./xcrysden 即可启动程序。若需在任意目录下启动，需在 ~/.bashrc 文件中添加 export PATH=$PATH:[XCrySDen的目录名]，并重新进入终端生效。

---

## 3. 预编译版在CentOS 7上的兼容性

该预编译版 XCrySDen 1.6.2 可在 CentOS 7 系列各个版本上运行。若系统安装方式符合特定演示（如 VMware 15 中安装 CentOS 7.6），通常无需安装额外库即可直接运行。若运行时提示缺库，应根据报错提示使用 yum 命令安装相应的包。

---

## 4. 预编译版在CentOS 8上的修改与注意事项

在 CentOS 8.0 系统上，需将解压后目录下 tcl/xcInit.tcl 文件里的两处 "0m" 改为 "0" 才能运行。在此版本下关闭程序时，必须点击右上角强行关闭。

---

## 5. 编译XCrySDen前的依赖库安装

在 CentOS 7.x 和 8.0 下编译前，需运行 `yum install libGL-devel libGLU-devel libXmu-devel` 安装必要的库。系统环境应已安装 gcc 和 gfortran，若未安装需运行 `yum install gcc-gfortran` 进行安装。

---

## 6. XCrySDen源代码编译过程

下载修改后的源代码包 http://原作者.com/attach/564/xcrysden-1.6.2_src_原作者.tar.gz。解压并进入目录后，运行 `make all` 即可开始编译，过程大约耗时 5 分钟。编译完成后，运行 `./xcrysden` 即可启动程序。

---

## 7. 针对特定CentOS版本的编译修复

在部分 CentOS 版本（如 CentOS 7.4）上编译可能失败，需在解压目录下的 Makefile 文件中 X_LIB= 后面加入 -lXss 选项，随后重新运行 `make all`。经测试，CentOS 7.7 版本无需进行此修改。

---

## 8. 修改版源代码包的细节调整

Make.sys 文件基于 system/Make.sys-shared 修改，解决了原文件无法使用的问题。Makefile 文件中去除了 all: 后的 mesa，因 CentOS 源已包含该库并通过 yum 安装。

---

## 9. 源代码包中外部依赖的处理方式

对于 CentOS 8，可利用源中已升级的 tcl/tk 8.6 版本而不必编译。原编译过程会自动下载 tcl、tk、Togl、fftw、bwidget 包，为避免网络问题导致下载失败，这些压缩包已被直接放置于 external/src 目录下供编译使用。
