---
key: t18745
title: ����Multiwfn��������cube�Ľű�MCubeGen 1.0
url: http://bbs.keinsci.com/thread-18745-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 13
---

# ����Multiwfn��������cube�Ľű�MCubeGen 1.0 — 知识卡片

## 1. MCubeGen 脚本功能

MCubeGen 是一个基于 Python 编写的脚本，旨在调用 Multiwfn 批量生成 cube 文件，便于后续使用 vmd 等程序进行渲染。该脚本生成的 cube 文件命名格式兼容 vmd 的 vcube 脚本识别规范，适用于 Linux 和 Windows 系统。

---

## 2. 脚本环境依赖

使用 MCubeGen 脚本需要系统安装 Python3（推荐使用 Anaconda 配置），并将 Multiwfn、MCubeGen.py 以及 Gaussian（g09 或 g16）的可执行文件路径添加到系统的 PATH 环境变量中。

---

## 3. 脚本内存与核心设置

脚本默认使用的内存大小为系统总内存的 80%，默认调用 Multiwfn 的全部核心数进行计算。用户可以通过 -m 参数指定内存大小（如 10GB），或通过 -n 参数指定使用的核心数。

---

## 4. 轨道 Cube 文件批量生成

使用命令 `MCubeGen.py -o H1-L1,10 *.fchk` 可以批量生成指定轨道的 cube 文件。该命令会针对当前目录下所有的 fchk 文件，生成 HOMO-1、HOMO、LUMO、LUMO+1 以及第 10 号轨道的 cube 文件；对于开壳层体系，脚本会自动区分 alpha 和 beta 轨道。

---

## 5. 实空间函数 Cube 文件批量生成

使用命令 `MCubeGen.py -c den,esp,esd,elf,lol,rdg,lmd -g 2 *.fchk` 可批量生成多种实空间函数的 cube 文件。参数 -c 指定生成电子密度、静电势、变形密度、ELF、LOL、约化密度梯度以及 lambda2 等类型的 cube 文件，-g 2 则将网格间距设置为 2。

---

## 6. 激发态相关 Cube 文件生成

生成激发态下的空穴、电子、跃迁密度或电荷差分密度 cube 文件，需要确保 Gaussian 输出的 log 文件与 fchk 文件在同一目录下。命令格式为 `-e s1,t1-3:ele,hole,td,cdd`，其中冒号前定义激发态（如 s1, t1-3），冒号后定义待生成的 cube 类型（如电子、空穴、跃迁密度、电荷差分）。

---

## 7. 激发态参数细节与网格设置

指定激发态范围时，`t1-3` 表示第一至第三三重态，`s1` 表示第一单重态。若仅需针对 log 文件中列出的激发态，可直接使用数字索引（如 `-e 1,2:hole,ele`）。参数 -g "4;0.2" 用于将等值面数值设定为 0.2。

---

## 8. CI 态密度与静电势计算

使用命令 `MCubeGen.py -d CI -c den,esp *.fchk` 可以计算 CI 态下的电子密度和静电势 cube 文件。该命令通过 -d 选项指定 Multiwfn 使用 CI 态密度替代默认的 SCF 密度进行计算。

---

## 9. 自然跃迁轨道 (NTO) 生成流程

生成 NTO cube 文件需要分两步执行：首先运行 `MCubeGen.py -e 1-3:nto *.fchk` 以生成包含 NTO 信息的 fchk 文件；然后进入生成的 MCUBEG 目录，运行 `MCubeGen.py -o h,l *.fchk` 来生成 NTO 的空穴和电子 cube 文件。

---

## 10. Windows 系统操作方式

在 Windows 系统下，需将 MCubeGen.py 脚本与 fchk 文件置于同一目录。操作方法为在该目录下按住 Shift 键并点击鼠标右键，选择“在此处打开 PowerShell 窗口”，然后输入命令 `python MCubeGen.py -选项 内容 *.fchk` 执行。

---

## 11. Linux 系统操作方式

在 Linux 系统下，若脚本已添加至 PATH 环境变量，可直接在包含 fchk 文件的目录中运行命令 `MCubeGen.py -选项 内容 *.fchk` 进行批量处理。

---

## 12. 输出文件与命名规则

程序执行完毕后，会在当前目录下生成一个名为 MCUBEG 的文件夹，所有计算生成的 cube 文件均存储于此。生成的 cube 文件命名格式为“原文件名_cube.类型.cub”，例如用于表示电子密度或轨道等不同物理量。

---

## 13. 调试与日志文件检查

脚本运行结束后，当前目录下会生成 Multiwfn_com、Multiwfn_out 和 Multiwfn_err 三个文件。若计算过程中出现问题，可通过打开 Multiwfn_err 查看错误信息，或查看 Multiwfn_com 了解具体调用的 Multiwfn 命令，也可手动运行该命令进行进一步调试。
