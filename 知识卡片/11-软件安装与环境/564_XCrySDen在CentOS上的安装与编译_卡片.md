---
id: 564
title: XCrySDen在CentOS上的傻瓜式安装方法
url: http://sobereva.com/564
domain: 软件安装与环境
topic: XCrySDen在CentOS上的安装与编译
cards: 7
---

# XCrySDen在CentOS上的安装与编译 — 知识卡片

## 1. XCrySDen在CentOS上的预编译版安装与配置

下载地址为 http://sobereva.com/attach/564/xcrysden-1.6.2_sobereva.tar.gz。解压后进入目录运行 ./xcrysden 即可启动；若在 ~/.bashrc 中添加 export PATH=$PATH:[XCrySDen的目录名]，重新进入终端后可在任意目录直接启动。

---

## 2. 预编译版XCrySDen在CentOS 7上的运行环境

此预编译版在 CentOS 7 系列各版本上均可运行。若系统安装方式参照 http://sobereva.com/454 演示过程，无需额外安装库即可运行；若提示缺库，需 Google 报错提示并用 yum 安装相应包。

---

## 3. 预编译版XCrySDen在CentOS 8.0上的运行设置

CentOS 8.0 需将解压目录下 tcl/xcInit.tcl 文件里的两处 0m 改为 0 才能运行。关闭程序时必须点击右上角强行关闭。

---

## 4. XCrySDen编译所需基础环境与库安装

运行 yum install libGL-devel libGLU-devel libXmu-devel 安装所需库。系统应已安装 gcc 和 gfortran，若未安装则运行 yum install gcc-gfortran。

---

## 5. XCrySDen修改版源代码包的编译步骤

下载地址为 http://sobereva.com/attach/564/xcrysden-1.6.2_src_sobereva.tar.gz。解压后进入目录，运行 make all，约 5 分钟编译完毕，之后直接运行 ./xcrysden 即可启动。

---

## 6. 部分CentOS版本编译失败的解决方案

对于 CentOS 7.4 等特定版本，编译中途可能失败，需在解压目录下的 Makefile 中 X_LIB= 后面加入 -lXss 选项，然后重新运行 make all。

---

## 7. 修改版源代码包的Makefile与Make.sys修改细节

Make.sys 基于文件 system/Make.sys-shared 修改；Makefile 中将 all: 后面的 mesa 去掉。external/src 目录下已放置 tcl、tk、Togl、fftw、bwidget 压缩包，避免编译过程中自动下载失败。
