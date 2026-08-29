---
key: t43066
title: ʹ�� Mathematica ʵ��HOMO��LUMO�����3Dͬ�����ӻ����Զ��Ű汣��
url: http://bbs.keinsci.com/thread-43066-1-1.html
domain: 可视化与制图
source: keinsci
year: 2024
cards: 15
---

# ʹ�� Mathematica ʵ��HOMO��LUMO�����3Dͬ�����ӻ����Զ��Ű汣�� — 知识卡片

## 1. 轨道可视化自动排版的优势

轨道可视化自动排版可同步调整多个轨道的视角，省去手动逐个调整的步骤。该方法可将多个轨道图形一次性排版生成图片，便于直接插入 PPT。在 PPT 数据展示时，可直接从 Mathematica 笔记本复制图片使用。

---

## 2. 测试平台与软件版本

该方法在 Ubuntu 20.04、Win11、MacOS 13.4 系统下测试通过。硬件平台包括 AMD 5950x、i7-13700 和苹果 M1 芯片。软件使用 Mathematica 13.3 或 Mathematica 14.0。

---

## 3. Gaussian 输出文件处理流程

化学应用研究通常需要处理 HOMO（最高占据分子轨道）和 LUMO（最低未占据分子轨道）数据。数据源自 Gaussian09/16 计算输出的 chk 文件。通过 `formchk` 命令将 chk 文件转换为 fchk 文件，再使用 `cubegen` 命令将 fchk 文件转换为 cube 文件以供可视化。

---

## 4. 批量轨道可视化的难点

当需要同时展示多个体系的轨道时，每个体系需要统计一个 HOMO 和 LUMO 的轨道并对比。为保证统一视角，需手动逐个调整每个轨道的观察角度，操作繁琐且易出错。此类数据的图形排版和整理工作耗时。

---

## 5. Mathematica 轨道可视化实现思路

通过 Gaussian 16 进行高精度的轨道数据计算。利用 Mathematica 强大的数据处理和图形展示功能，导入轨道数据并转换为直观的 3D 图形。设置统一的视角参数，通过代码控制实现同步旋转。将生成好的图片直接导入 PowerPoint 模板。

---

## 6. 轨道可视化文件准备步骤

在当前文件所在目录下新建一个文件夹。将 Mathematica 的 nb 文件、log 文件、homo 和 lumo 的 cube 文件放入新建的文件夹中。

---

## 7. 轨道可视化代码执行

在 Mathematica 中执行代码。代码运行后会弹出包含轨道图形的交互窗口。拖动旋转其中一个图形，所有图形视角会自动同步。点击窗口中的 "Save" 按钮即可自动保存图片文件。

---

## 8. 轨道可视化文件路径与变量定义

代码中使用 `SetDirectory[NotebookDirectory[]]` 设置工作路径。定义了 log 文件变量（如 `s0Log`）和 cube 文件变量（如 `s0HomoCube`, `s0LumoCUbe` 等）。定义了输出图片的文件名变量。

---

## 9. 轨道可视化动态视角控制

使用 `DynamicModule` 定义视角参数 `vp`（ViewPoint）和 `vv`（ViewVertical）。`logFun` 和 `cubeFun` 函数在生成 3D 图形时应用动态视角参数。`SphericalRegion -> True` 选项确保旋转时的球形区域特性。

---

## 10. 轨道网格排版与样式设置

使用 `Grid` 函数将 3D 轨道图和文本标签组合排版。`styledText1` 和 `styledText2` 定义了字体样式（Times New Roman，不同字号）。排版包含分割线 `Dividers` 和对齐方式 `Alignment -> Center`。

---

## 11. 轨道可视化自动导出功能

界面面板包含 "Save" 按钮。点击按钮后，代码执行 `Export` 命令。分别导出 s0 和 s1 的 HOMO、LUMO 单张图片，并导出排版后的组合图片 `s0s1_homolumo.png`。背景设置为透明。

---

## 12. 轨道能级图绘制扩展

除了轨道图，通过修改代码可以实现轨道能级图的绘制。HOMO 设为一种颜色，LUMO 设为另一种颜色。能级 Gap 数据可直接从对应文件读取，省去手动排版的麻烦，避免使用 Excel 等工具进行繁琐操作。

---

## 13. Mathematica 绘图应用优势

使用 Mathematica 脚本绘图具有可复用性。脚本编写成功后，每次打开只需更换数据文件即可生成标准图形。该方法支持数据分析、偶极计算、分子表面静电势等多种可视化排版需求。

---

## 14. 分子表面静电势可视化数据导入

在 Mathematica 中使用 `Import` 函数导入 esp.cube 和 Potential.cube 文件。通过指定 `"VolumetricData"` 格式读取体积数据。使用 `"Molecule"` 格式导入分子结构信息。

---

## 15. 分子表面静电势图形生成

使用 `ListContourPlot3D` 根据 esp 数据生成等值面，并使用 `DiscretizeGraphics` 转化。使用 `ListSliceDensityPlot3D` 将 Potential 数据映射到等值面上。设置 `ColorFunction` 和 `Opacity` 调整颜色和透明度。最后使用 `Show` 组合分子模型图和静电势图。
