---
key: t56646
title: ģ�廯Multiwfn���е�һ��;��
url: http://bbs.keinsci.com/thread-56646-1-1.html
domain: 其他量化软件
source: keinsci
year: 2025
cards: 18
---

# ģ�廯Multiwfn���е�һ��;�� — 知识卡片

## 1. BaneWfn 软件简介

BaneWfn 是一个针对 Multiwfn 设计的批处理映射程序。该软件能够自动化 Multiwfn 的输入输出流程，支持通过配置文件和脚本实现批量处理，从而降低手动输入的繁琐程度并提高计算精度。BaneWfn 提供了 Windows 安装程序，也可直接在 Linux 环境下使用，相关源码和手册可在 GitHub 或 Gitee 获取。

---

## 2. BaneWfn 基础配置与配置文件搜索

BaneWfn 在启动时会自动搜索配置文件 banewfn.rc。搜索路径依次为当前目录和用户目录下的 ~/.bane/wfn。配置文件中需指定 Multiwfn 的可执行文件路径、配置文件路径以及并发核心数，例如设置 Multiwfn_exec 和 confpath 等参数。

---

## 3. BaneWfn 配置文件基本语法与变量

BaneWfn 配置文件使用 INI 风格的结构，支持 Shell 风格的变量占位符。变量格式如 ${logfile:-}，其中 :- 后跟默认值，表示若未指定参数则使用默认值。此外，支持 ${input} 变量，该变量会被替换为输入 Multiwfn 的主文件名（不含后缀），也可使用 ${name} 引用目录名或文件头定义的值。

---

## 4. 配置文件中的主要功能块

配置文件主要由多个功能块（Module）组成，例如 [main] 块用于定义主流程输入，[quit] 块用于定义退出流程。功能块下方列出对应的 Multiwfn 菜单序号和参数，如 [main] 下包含输入日志文件、状态选择、网格设置等步骤。每个功能块对应不同的计算功能，如 hole-electron 分析、overlap 计算等。

---

## 5. [main] 与 [quit] 功能块示例

[main] 功能块记录了 Multiwfn 启动后的初始操作逻辑，包括载入日志文件、选择电子态和网格密度等。[quit] 功能块则记录了退出 Multiwfn 所需的指令序列，通常输入 0、0、0 和 q 以安全结束程序。这些块确保了批处理流程的完整闭环。

---

## 6. 子功能块定义与参数传递

在主配置文件中可以引用其他子功能块，例如 [cub]、[overlap] 等，这些块定义了特定的 Multiwfn 功能参数。在调用时，可以通过变量或直接在主块中指定参数值。例如，[cub] 块中定义了功能号 10 及其相关选项（1=total, 2=local, 3=cross），并使用 ${choice:-1} 来设置默认值。

---

## 7. %process 块的作用

%process 块用于向 Multiwfn 发送交互式指令，其下方的每一行都会作为单独的指令发送。在发送指令时，如果有多个参数（如功能号和选项），需要用空格分隔。若某行指令需要修改参数数值（如修改 grid 的值），直接在对应行书写新数值即可，脚本执行时会按顺序读取。

---

## 8. %command 块的作用与系统兼容性

%command 块用于执行系统级的 Shell 或批处理命令。在 Linux 环境下，这些命令会被写入 .sh 脚本执行；在 Windows 环境下，则被写入 .bat 脚本执行。对于 Windows 用户，若配置文件 banewfn.rc 中设置了 gitbash_exec，还可以通过在开头写 #!/bin/bash 来强制使用 Git Bash 执行脚本。

---

## 9. 文件头定义与自动匹配

BaneWfn 支持在功能块开头通过文件头定义输入文件，格式如 wfn=*.fchk。程序会自动匹配当前目录下符合通配符的文件，并依次处理。使用 ${input} 变量可以引用当前正在处理的文件名，从而避免输出文件被覆盖，同时也支持 core=xx 格式指定特定原子。

---

## 10. 脚本编写中的细节与注意事项

编写配置脚本时需注意：每个 [module] 块必须以 end 结尾，除非使用 wait 暂停等待用户操作；%command 可以独立写在一个块中，但也需要 end 结尾；# 号开头的行为注释，若在 %command 中使用 # 需要转义；空行会被自动移除；在 Multiwfn 11.4 版本后，command 的输出可能会影响 bash 脚本的行为。

---

## 11. Hole-Electron 分析配置示例

针对 Hole-Electron 分析，配置文件可定义 [hole-ele] 功能块。在该块中指定电子态（如 state 1），并在 %process 中调用 cub 生成孔和电子分布。通过 %command 中的系统命令（如 mkdir 和 mv），将生成的 hole.cub 和 electron.cub 移动并重命名到指定目录，例如 ${input}_s1_hole.cub。

---

## 12. Windows 下双击运行 .bw 文件

在 Windows 系统中，用户可以将 BaneWfn 的脚本配置文件后缀改为 .bw。双击 .bw 文件即可自动调用 BaneWfn 并执行脚本。这种方式简化了操作流程，特别适用于固定流程的批量处理任务。

---

## 13. Windows 下批量处理 Hole-Electron 的实例

在 Windows 下进行批量 Hole-Electron 分析时，可创建一个 .bw 文件，并在其中写入 wfn=*.fchk 以匹配所有输入文件。配置 [hole-ele] 块对不同状态（state 1, state 2）进行处理，并使用 move 命令将结果重命名。双击该文件即可对当前目录下所有匹配的 fchk/log 文件进行计算。

---

## 14. Linux 下使用 Shebang 运行 BaneWfn

在 Linux 环境下，可以通过在脚资料件第一行添加 Shebang #!/usr/bin/env banewfn 将其转化为可执行脚本。将脚本赋予执行权限并放入 PATH 环境变量后，即可直接在命令行运行。配合 wfn=*.fchk 设置，脚本会自动处理当前目录下的所有相关文件。

---

## 15. NICS-2D 计算流程与自动生成输入

NICS-2D 计算通常涉及两个步骤：首先生成 2D 扫描输入文件，然后进行计算。通过配置脚本，可以定义 ring 参数（如 ring=1,3,5）并使用 %command 块编写脚本（如批处理或 Shell 脚本）来自动生成 Gaussian 的 .gjf 输入文件，模板中包含计算方法和几何结构占位符。

---

## 16. NICS-2D 脚本中的向量提取与动态配置

在 NICS-2D 计算脚本中，可以通过 %command 读取 Gaussian 输出文件中的单位法向量和坐标信息。脚本利用 findstr 等命令提取特定数值（如 X, Y, Z 分量），并将其存入变量。随后，脚本动态生成一个新的 .bw 配置文件，将提取的向量值传递给 nics2d 功能块，实现后续的自动化计算。

---

## 17. NICS-2D 中的 wait 指令使用

在复杂的 NICS-2D 批处理流程中，当需要在上一步 Gaussian 计算完成后才能进行下一步操作时，可以在配置中使用 wait 指令。wait 指令会暂停 BaneWfn 的执行，直到用户确认，或者在连续的自动化流程中作为逻辑分隔点，确保数据准备完毕后再进行后续分析。

---

## 18. NICS-2D 流程的封装与简化

虽然 NICS-2D 计算涉及生成输入、运行 Gaussian 和分析结果等多个步骤，但可以通过 BaneWfn 将所有逻辑封装在一个配置文件中。这种封装省去了手动重复繁琐的步骤，用户只需双击或运行脚本，即可完成从结构文件到最终 NICS-2D 图绘制的全过程。
