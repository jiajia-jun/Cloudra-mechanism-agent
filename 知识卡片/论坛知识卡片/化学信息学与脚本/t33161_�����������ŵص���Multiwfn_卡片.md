---
key: t33161
title: �����������ŵص���Multiwfn�ķ�����Linux��
url: http://bbs.keinsci.com/thread-33161-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2022
cards: 5
---

# �����������ŵص���Multiwfn�ķ�����Linux�� — 知识卡片

## 1. Multiwfn 环境变量配置

Multiwfn 官方推荐在 .bashrc 文件中添加环境变量 export OMP_STACKSIZE=200M 和 ulimit -s unlimited 以设置栈大小。同时需要将 Multiwfn 的安装目录路径赋值给环境变量 Multiwfnpath，并将该目录添加到 PATH 环境变量中。每次打开 bash 终端时，.bashrc 中的这些命令会被自动执行。
- export OMP_STACKSIZE=200M
- ulimit -s unlimited
- export Multiwfnpath=/home/你的用户名/你的Multiwfn目录
- export PATH=$PATH:/home/你的用户名/你的Multiwfn目录

---

## 2. Wine 配置冲突风险

在 .bashrc 中直接使用 ulimit -s unlimited 命令可能会导致某些程序出现问题。在已设置该参数的条件下，运行 winecfg 可能会报错并崩溃。
- ulimit -s unlimited

---

## 3. 环境初始化函数封装方案

为了避免对全局 shell 环境造成影响，可以将 Multiwfn 的环境变量设置命令封装在一个 bash 函数中。用户可以将这些命令写入 .bashrc，并包裹在 mtf(){ ... } 结构内，函数名可以自定义。每次需要使用 Multiwfn 前，在终端手动输入该函数名即可初始化环境，随后直接输入 Multiwfn 即可启动。
- mtf(){
- export OMP_STACKSIZE=200M
- ulimit -s unlimited
- export Multiwfnpath=/home/你的用户名/你的Multiwfn目录
- export PATH=$PATH:/home/你的用户名/你的Multiwfn目录
- }

---

## 4. 启动脚本自动化方案

为了避免每次调用 Multiwfn 都需要先运行初始化函数，可以编写一个独立的 bash 脚本来自动加载环境并启动程序。脚本内容应包含环境变量设置和绝对路径下的 Multiwfn 执行命令，并使用 "$@" 传递后续参数。将此脚本命名为 Multiwfn 并放入 PATH 包含的目录（如用户目录下的 bin 文件夹）中，即可直接通过 Multiwfn 命令调用该脚本。
- export OMP_STACKSIZE=200M
- ulimit -s unlimited
- export Multiwfnpath=/home/你的用户名/你的Multiwfn目录
- /home/你的用户名/你的Multiwfn目录/Multiwfn "$@"

---

## 5. 个人 bin 目录配置

Linux 系统允许用户在个人目录下创建 bin 文件夹，并通过修改 PATH 环境变量将其纳入系统路径。将自定义脚本或可执行文件放入该 bin 目录后，可以在终端直接调用，无需每次输入完整路径。此方法适用于管理多个自编脚本或程序，且不影响 .bashrc 中的全局配置。
- export PATH=$PATH:/home/你的用户名/bin
