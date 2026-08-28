---
id: 521
title: Grimme的xtb程序的编译方法
url: http://sobereva.com/521
domain: 软件安装与环境
topic: CentOS下使用Intel编译器编译xtb程序
cards: 4
---

# CentOS下使用Intel编译器编译xtb程序 — 知识卡片

## 1. CentOS 7.4下xtb编译环境准备

编译Grimme的xtb程序6.2.1版前，需确保已安装ifort+icc 19.0.1.144编译器。先通过`yum install python3`安装Python 3及pip3。之后运行`pip3 install meson`和`yum install ninja-build`安装meson和ninja构建工具，因为yum源中的meson版本过旧，而xtb 6.2.1要求meson版本必须>=0.49。

---

## 2. xtb源代码meson.build文件修改

解压xtb源代码包后，需打开目录下的meson.build文件进行修改。在“## LIBRARIES”部分的前头一行加上`add_project_link_arguments('-L/usr/lib/x86_64-redhat-linux6E/lib64/', language: 'c')`。此步骤用于避免在链接可执行文件时提示找不到库文件的错误。

---

## 3. xtb编译的具体命令操作

在xtb目录下依次执行以下命令进行编译：首先设置编译器环境变量`export FC=ifort CC=icc CXX=icpc`。接着运行`meson setup build_intel --optimization=2`进行构建配置。最后执行`ninja -C build_intel`进行编译，编译过程不到10分钟。

---

## 4. xtb编译过程中的注意事项

编译过程中若屏幕提示“dep hack”并卡住不动，无需着急，应耐心等待。编译完成后，在build_intel目录下会生成xtb可执行文件。将该文件移动到xtb可执行文件包中，覆盖原有的可执行文件即可完成安装。
