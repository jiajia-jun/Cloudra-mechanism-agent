---
key: t18150
title: ʹ��vmd������Ⱦcube�ļ���tcl�ű�vcube ����2.0��
url: http://bbs.keinsci.com/thread-18150-1-1.html
domain: 可视化与制图
source: keinsci
year: 2020
cards: 27
---

# ʹ��vmd������Ⱦcube�ļ���tcl�ű�vcube ����2.0�� — 知识卡片

## 1. vcube 脚本功能概述

vcube 是基于 VMD 的 TCl 脚本，旨在简化 VMD 操作、批量处理文件及美化图形。目前包含四个模块：生成 cube (MCubeGen)、渲染 cube (vcube)、图片合成 (MFigComp) 以及文本处理 (tmwfn)。这四个模块彼此独立可单独使用，亦可协同工作。

---

## 2. vcube 渲染 cube 文件

vcube 是通过 Tcl 脚本编写的 VMD 插件，用户无需在 VMD 中手动操作 Multiwfn 即可渲染所需的 cube 文件。

---

## 3. 命令 vmol 提取原子结构

使用 vmol 命令可以从现有的 cube 文件中提取原子结构信息，以便生成 VMD 支持的结构文件。使用方法为在 VMD 控制台输入 `vmol *.cub *.pdb`，该命令会读取目录中的 cub 文件和 PDB 文件。

---

## 4. 命令 vrename 修改分子名称

VMD 加载 cube 文件时默认以文件名作为分子名称，这会影响到后续图片的生成。使用 `vrename _oH _HOMO` 命令可以将当前载入分子的文件名中的 `_oH` 替换为 `_HOMO`。该命令支持正则表达式，例如 `vrename {^} confer1_ 0 1 2` 会将编号为 0、1、2 的分子的文件名前加上 `confer1_` 前缀。

---

## 5. 命令 vrenders 渲染当前帧

使用 `vrenders` 命令可以对当前视图进行渲染。如果不带参数，默认将视图放大 3 倍并渲染为 `current.bmp` 文件，使用该命令会覆盖之前生成的 `current.bmp`。如果输入 `vrenders orbital01 4`，则将当前视图放大 4 倍并渲染为 `orbital01.bmp`。

---

## 6. 命令 vrender 添加文件名后缀

为了在渲染不同角度的图片时避免文件名被覆盖，vrender 命令支持添加后缀选项。例如 `vrender _topview` 会在渲染的文件名后添加 `_topview` 后缀。`vrender _sideview 4 0 1 2` 表示对 0、1、2 号分子使用 4 号分子的视角进行渲染，并在文件名后添加 `_sideview` 后缀。

---

## 7. OSPRAY 渲染模式支持

Windows 系统下的 OSPRAY 插件存在较多 bug。TachyonLOpix 是 VMD 支持的另一种渲染器，速度极快，但对默认的波函数没有做特别优化。如果在启动 VMD 时检测到支持 OSPRAY，会提示 `TachyonLOSPRAYInternal is available`。输入 `set ospray 1` 可开启 OSPRAY 渲染，输入 `set ospray 0` 则关闭。

---

## 8. 命令 vgroup 按文件名分组

`vgroup` 命令可以根据文件名中的分隔符对分子进行分组。例如对于 `mol1_S1_oH`, `mol2_S1_oH`, `mol1_S2_oH`, `mol2_S2_oH` 四个文件，使用 `vgroup _` 命令会以下划线为分隔符将前两段作为分组依据，将文件分为两组。若使用 `vgroup {_ 0}`，则指定分割符为下划线，取第 0 段作为组名。若使用 `vgroup {_ -1}`，则取除去最后一段之外的部分作为组名。

---

## 9. 跨平台渲染支持 (Windows 到 Linux)

在 Windows 下生成渲染数据文件并传输到 Linux 下进行渲染可以提高效率。在 Windows 下执行 vrender 命令并输入 `n` 后，会在 VCUBE 文件夹下生成 dat 文件、Tachyon 渲染文件、bat 文件（Windows 用）和 sh 文件（Linux 用）。将 VCUBE 文件夹复制到 Linux 环境中，确保 VMD 已安装并添加到 PATH，执行 `sh renderall.sh` 即可使用默认线程渲染，执行 `sh renderall.sh 24` 可指定 24 线程渲染。

---

## 10. 命令 vtachyopt 修改 Tachyon 参数

Tachyon 渲染参数如 `-trans_raster3d`（使用透明度渲染）和 `-shadow_filter_off`（关闭阴影）对渲染效果影响大。使用 `vtachyopt "-shadow_filter_off"` 可以添加对应参数。若要同时关闭阴影和开启透明度，可输入 `vtachyopt "-shadow_filter_off -trans_raster3d"`。输入 `vtachyopt " "`（空格）则重置为默认值。

---

## 11. Linux 系统下的支持与优化

在 Linux 64 位系统下可以生成大于 3G 的 cube 文件。推荐使用 xmanager 连接 Linux 以支持图形界面，若无法显示图形界面，可使用 `vmd -dispdev text` 命令以文本模式启动 VMD。若安装了支持 CUDA 的 OptiX 版本 VMD，可使用 `set optix 1` 开启 TachyonLOptiXInternal 进行极速渲染。图片预览默认使用 eog 或 gwenview，可通过 `set image_viewer xxx` 指定其他查看器。

---

## 12. 命令 vgroup 按编号分组

vgroup 支持按照分子编号进行分组。例如 `vgroup by 0,2,5 1,3,4` 会将编号为 0、2、5 的分子分为一组，编号为 1、3、4 的分子分为另一组。

---

## 13. 支持自定义脚本应用

用户可以将自定义的 VMD 脚本（.tcl 或 .vmd）放在当前目录、styles 目录或 scripts 目录下。使用 `vapply` 命令可以查看可用的脚资料件，使用 `vapply xxx.vmd` 可以将自定义脚本应用到当前每一个分子上。

---

## 14. 多线程渲染设置

默认使用 `set nproc -2` 进行渲染。用户可以通过 `set nproc 8` 指定使用 8 个线程进行渲染。在确认渲染时会显示当前使用的线程数和分辨率。

---

## 15. vcube 脚本功能特性

vcube 脚本支持单值 cube（如电子密度、LOL、ELF）、双值 cube（空穴-电子图）、mapped cube（如 RDG）以及多 cube 同时绘图（如孔洞图）。每组分子的数据支持独立预览、切换 style、调整 iso、color range 和 alpha。同组内的轨道可以联动移动、旋转和显示。

---

## 16. vcube 安装步骤

安装 vcube 需要在 Windows 系统上安装 VMD。下载 vcube.rar 并解压（如 D:/vmwfn）。在 VMD 安装目录下的 vmd.rc 文件中添加 `source {D:\vmwfn\vcube.tcl}` 和 `set style_dir {D:\vmwfn\styles}`。重启 VMD 并在控制台查看输出信息确认加载成功。建议将 vmd.exe 加入系统环境变量。

---

## 17. vcube 基本使用流程

准备好待渲染的 cub 文件，建议按“轨道名_后缀.cub”格式命名。在文件所在目录打开 PowerShell 或 WSL Shell，输入 `vmd.exe` 启动 VMD，加载完成后输入 `vcube *.cub`。在 VMD 图形窗口中使用键盘快捷键调整视图：`a`/`d` 切换分子，`q`/`e` 调整 iso 值，`PgUp`/`PgDn` 切换 style。调整完毕后输入 `vrender` 进行渲染。

---

## 18. 分子联动调整技巧

使用 `a`/`d` 选择分子时，若同一分子的不同轨道（如 HOMO 和 LUMO）被分在同一组，它们会保持相同的视角。若要单独调整某个轨道的角度，可先使用 `w`/`s` 选中该轨道，再进行调整。

---

## 19. 多 cube 显示切换

在同时显示多个 cube 的状态下，按 `g` 可循环切换显示模式：a. 仅显示当前分子；b. 显示当前分子所在组的所有分子；c. 显示所有分子。

---

## 20. VMD 窗口焦点问题

如果在 VMD 图形窗口操作时无响应，可能是因为焦点不在图形窗口上。只需在 VMD 控制台窗口按一下回车键，焦点切回图形窗口即可恢复正常操作。

---

## 21. 调整等值面透明度

使用 `Home`/`End` 键可以快速调整 isosurface 的透明度。修改透明度对预览效果影响不大，但会对最终渲染效果产生显著影响，建议在渲染前使用 `v` 预览实际效果。

---

## 22. 渲染分辨率说明

当前默认渲染分辨率为窗口大小的 3 倍。窗口大小通常决定了轨道显示的大小，因此在脚本中设定的图片打印尺寸仅供参考。若轨道显示窗口太小，会导致预览卡顿且无必要生成过高分辨率的图片。

---

## 23. 绘制 mapped cube 图（如静电势）

绘制 mapped cube 图（如静电势映射到电子密度）时，需准备好两个文件：密度文件（如 xxx_den.cub）和属性文件（如 xxx_esp.cub）。使用命令 `vcube *_den.cub map *_esp.cub` 进行加载，通过 map 关键字建立对应关系。

---

## 24. 显示 Color scale bar

要显示 Color scale bar，需先选中 mapped cube 分子。在 Graphics -> Representations 菜单中新建一个 Color scale bar。在 VMD 控制台输入 `vshowalways 8`（8 为 color scale bar 对应的 molid 编号）使其始终显示。调整好位置后使用 `vrender` 渲染。

---

## 25. 帮助命令使用

在 VMD 控制台输入 `vhelp` 可以查看所有可用命令和快捷键的帮助信息。输入 `vhelp viso` 可以查看特定命令（如 viso）的详细用法。vcube 源自的命令均以 `v` 开头，在 VMD 中输入 `v` 后按 Tab 键可列出所有相关命令。

---

## 26. 内置风格示例

vcube 内置了多种风格，包括 sob 风格（默认）、AO 风格（白底黑线或灰线，适合打印）、白色风格（白底纯色，强调轮廓感）以及莫兰迪风格（低饱和度色调，视觉柔和，适合展示密度图或需降低视觉干扰的场景）。

---

## 27. 创建自定义风格

用户可以通过修改 styles 文件夹中的 stl 文件（针对普通 cube）和 mtl 文件（针对 map cube）来创建自定义风格。在 VMD 中打开一个 cube 文件，调整至满意的显示效果，记录相关参数。将参数复制到对应的 stl 或 mtl 文件中，保存即可完成自定义风格的创建。
