---
key: b479
title: 使用Multiwfn一键批量产生各类光谱图（含演示视频）
url: http://sobereva.com/479
domain: 波函数与电子结构分析
source: blog
year: 2019
cards: 7
---

# 使用Multiwfn一键批量产生各类光谱图（含演示视频） — 知识卡片

## 1. Multiwfn 光谱批量绘制原理

Multiwfn 程序支持通过批处理脚本对当前目录下所有支持的输入文件（如 Gaussian、ORCA 等程序的输出文件）进行自动批量处理，从而一键生成各类光谱图。该方法利用外部文资料件记录 Multiwfn 的交互指令，通过循环调用程序并将输出重定向，自动完成光谱参数设置与图像文件生成。进行此操作需要使用 2019-Apr-28 及之后更新的 Multiwfn 程序包，且需将 settings.ini 中的 isilent 参数设为 1 以进入安静模式。

---

## 2. Windows 批处理脚本运行方法

在 Windows 系统下，将待处理的输出文件、examples\spectra 目录下的 UV-Vis.txt 以及 batchspec.bat 文件复制到 Multiwfn 安装目录。双击运行 batchspec.bat 即可自动处理当前目录下所有 .out 文件并生成对应的 PNG 格式光谱图像文件。若需批量绘制红外光谱，需将 IR.txt 替换 UV-Vis.txt 并相应修改批处理脚本中的文件引用。

---

## 3. Windows 批处理脚本内容解析

Windows 批处理文件 batchspec.bat 利用 `for /f` 循环遍历当前目录下的所有 .out 文件，并对每个文件执行 Multiwfn 程序，指令输入来源于 UV-Vis.txt。屏幕输出信息被重定向到 NUL 以避免干扰，生成的默认图像文件 DISLIN.png 通过 `rename` 命令重命名为与输入文件同名的 PNG 文件。代码中 `%%~ni` 写法代表去除文件名变量的后缀。

---

## 4. 光谱绘制指令文件格式

记录 Multiwfn 交互指令的文资料件（如 UV-Vis.txt）每一行对应一次键盘输入，可用于定义光谱类型、坐标轴范围及缩放设置。例如，输入 11 进入光谱绘制功能，输入 3 选择绘制 UV-Vis 光谱，后续通过子选项代码设定横坐标范围（如 150,850,100）及纵坐标范围。通过修改资料资料件中的数值参数，可以调整输出光谱的坐标范围和显示方式。

---

## 5. settings.ini 安静模式设置

在批量处理光谱时，必须在 Multiwfn 目录下的 settings.ini 文件中将 isilent 设为 1。此设置使程序处于安静模式，禁止在屏幕上弹出绘图窗口，从而避免因等待用户关闭窗口而中断批处理进程。

---

## 6. Linux 环境批量运行脚本

在 Linux 系统下，需将 batchspec.sh 脚本、指令文件（如 UV-Vis.txt）及待处理文件拷贝至同一目录，并赋予脚本可执行权限（chmod +x）。运行 ./batchspec.sh 脚本将自动调用 Multiwfn 处理所有 .out 文件，并将生成的 dislin.png 重命名为对应的 .png 文件。脚本中使用 ${inf//out/png} 语法将输入文件的后缀替换以生成新的输出文件名。

---

## 7. Linux 批量绘图的命令别名配置

为方便在 Linux 下使用，可将 batchspec.sh 和 UV-Vis.txt 放置在固定目录（如 /sob），并在 ~/.bashrc 中设置别名（如 alias UV）指向脚本路径。设置完成后，在任意包含输出文件的目录下输入定义的别名命令，即可立即将当前目录下的文件转化为光谱图。配合编辑指令文件的别名（如 gUV），可快速修改绘图参数而无需移动文件。
