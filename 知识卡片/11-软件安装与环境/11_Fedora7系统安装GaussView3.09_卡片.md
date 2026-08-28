---
id: 11
title: Fedora7下使用GaussView3.09的方法
url: http://sobereva.com/11
domain: 软件安装与环境
topic: Fedora7系统安装GaussView3.09
cards: 4
---

# Fedora7系统安装GaussView3.09 — 知识卡片

## 1. GaussView Linux版在Fedora7下的依赖包安装

GaussView Linux版主要面向RH9时代的系统开发，在Fedora7-64bit下使用必须安装特定兼容包。操作步骤是下载指定压缩包，解压后安装其中的compat-libstdc++-296-2.96-138.i386.rpm。
下载链接：[http://pan.baidu.com/s/1c0HDUUW](http://pan.baidu.com/s/1c0HDUUW) 密码：1o5b

---

## 2. 替换Fedora7的libXft.so.1库文件

Fedora7系统自带的是libXft.so.2，而GaussView不支持该版本，需要使用压缩包内提供的旧版本库文件。操作步骤是将包内的libXft.so.1文件复制到/usr/lib目录下。

---

## 3. GaussView目录的移动与路径设置

安装过程中需要将压缩包内的gview目录移动到/sob/GV307_linux/下面。随后需要在/root/.bashrc文件中添加目录及路径配置，添加内容如下：
export GV_DIR=/sob/GV307_linux/gview
export LIBPATH=/sob/GV307_linux/gview/lib
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/sob/GV307_linux/gview/lib
PATH=$PATH:/sob/GV307_linux/gview

---

## 4. GaussView在Fedora7下的启动命令

完成环境变量配置后，需要重新加载环境或执行特定命令来启动程序。具体操作是输入bash命令，然后输入gview即可启动GaussView。
