---
key: t28196
title: ����� M1 chip �� macOS �����ŵ�ʹ�� Gaussian 09 �� GaussView 6
url: http://bbs.keinsci.com/thread-28196-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 8
---

# ����� M1 chip �� macOS �����ŵ�ʹ�� Gaussian 09 �� GaussView 6 — 知识卡片

## 1. 在 macOS 上运行 Gaussian 09 的版本兼容性

Gaussian 09 官方仅提供 32 位版本，而 macOS Catalina 及后续版本不再支持 32 位应用，导致无法在较新的 macOS 系统上直接运行 Gaussian 09。为了在 macOS 上使用 Gaussian 09 进行几何优化等计算，需要通过特定的环境配置或安装辅助工具来解决兼容性问题。

---

## 2. 在 macOS 上安装 GaussView 6 的推荐方案

由于无法在 macOS 上直接使用 Mac 版 GaussView 5，推荐安装 Windows 版的 GaussView 6 并通过 CrossOver 运行。CrossOver 能够在 macOS 上提供良好的兼容环境，使得 Windows 版本的 GaussView 6 能够顺利启动并进行图形界面操作，用于构建输入文件。

---

## 3. Gaussian 09 与 GaussView 6 的跨平台协同工作流程

跨平台协同工作的流程是：在 CrossOver 运行的 Windows 版 GaussView 6 中构建分子模型并保存输入文件，随后在 macOS 原生终端调用本机安装的 Gaussian 09 进行计算。这种组合利用了 GaussView 优秀的图形界面和 Gaussian 09 的计算能力，实现了在 macOS 环境下的完整工作流。

---

## 4. Gaussian 09 在 macOS 上的运行环境需求

Gaussian 09 需要安装在“应用程序”文件夹下，并且必须配置正确的环境变量才能运行。系统环境变量需设置 g09root 指向安装目录，GAUSS_SCRDIR 指向临时文件目录，并加载 g09.profile 配置文件。

---

## 5. Gaussian 09 环境变量配置步骤

在终端中使用 vim 编辑 ~/.zshrc 文件，需添加 `export g09root=/Applications/gaussian09/`、`export GAUSS_SCRDIR=/Applications/gaussian09/Scratch` 以及 `source $g09root/g09/bsd/g09.profile`。保存并退出编辑器后，重启终端以确保环境变量生效，Gaussian 09 即可正常使用。

---

## 6. 使用 CrossOver 安装 GaussView 6 的操作

在 CrossOver 中选择“安装 Windows 应用程序”，并在“应用程序”列表中依次选择“科学计算 -> 计算化学 -> Palynodata”。选择下载好的 GV6.0.16_win64.exe 安装包进行安装，安装类型建议选择“Windows 10 64-bit”，并在安装过程中输入提供的序列号以完成激活。

---

## 7. GaussView 6 生成的输入文件路径修正方法

GaussView 6 生成的输入文件默认使用 Windows 风格的路径（如 C:\），这会导致在 macOS 终端运行 Gaussian 时报错。需使用文本编辑器打开 .gjf 文件，将 `%chk=C:\文件名.chk` 修改为 `%chk=文件名.chk`，即去掉盘符和反斜杠，使 Gaussian 能在当前目录下正确读写检查点文件。

---

## 8. 在 macOS 终端运行 Gaussian 09 的命令格式

在终端中使用 `cd` 命令进入输入文件所在目录后，可使用 `g09 < test.gjf > test.out` 将计算结果输出到 test.out 文件中。若希望在屏幕实时显示输出信息同时保存到文件，可使用 `g09 < test.gjf |tee test.out`；若直接运行 `g09 test.gjf`，则输出文件默认为当前目录下的 test.log。
