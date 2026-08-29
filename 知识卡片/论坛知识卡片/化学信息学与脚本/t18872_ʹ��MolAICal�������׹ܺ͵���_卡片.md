---
key: t18872
title: ʹ��MolAICal�������׹ܺ͵����ʿ׵��뾶�Ľ̳�
url: http://bbs.keinsci.com/thread-18872-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 13
---

# ʹ��MolAICal�������׹ܺ͵����ʿ׵��뾶�Ľ̳� — 知识卡片

## 1. MolAICal 简介

MolAICal 是一款用于计算通道和孔洞半径的方法工具，基于发表在《Briefings in Bioinformatics》上的研究开发。该工具的功能包括纳米管半径计算、孔洞入口半径计算以及沿通道方向的连续半径计算。计算通道半径需要熟悉 VMD、NAMD 软件的使用，并涉及 CHARMM 力场及 PDB、PSF 文件的处理。如果仅处理非极性结构的 PDB 文件，也可以不使用 CHARMM 力场参数进行半径计算。

---

## 2. MolAICal 教程资源获取

MolAICal 的官方网站地址为 https://molaical.github.io。中文教程可访问 https://molaical.github.io/cntutorial.html。博客信息可在 https://qblab.blogspot.com 查阅。本教程所需的示例文件可通过 GitHub 链接 https://github.com/MolAICal/tutorials/tree/master/005-radiiCal 下载。VMD 软件可从 https://www.ks.uiuc.edu/Research/vmd 获取。

---

## 3. 使用 VMD 构建纳米管模型

在 VMD 中构建碳纳米管需通过 Extensions 菜单依次选择 Modeling 和 Nanotube Builder。模型构建完成后，打开 Tk Console 并使用 `cd` 命令切换至包含 `parameter.dat` 文件的工作目录。在 Tk Console 中输入 `set all [atomselect top all]` 和 `$all writepdb nanotube.pdb` 命令，可将生成的纳米导出为 PDB 文件。

---

## 4. 纳米管半径计算参数配置

计算纳米管半径时需配置 `parameter.dat` 文件，其中包含 `cpoint` 和 `vector` 两个关键参数。`cpoint` 用于指定通道入口处的某一点坐标，例如 `-0.2015 0.4185 30.147`。`vector` 用于指定计算半径的方向，`0.00 0.00 1.00` 表示沿 Z 轴方向，`0.00 1.00 0.00` 表示沿 Y 轴方向，`1.00 0.00 0.00` 表示沿 X 轴方向。`vector` 的方向设置必须与通道的物理走向保持一致。

---

## 5. 纳米管半径计算执行与可视化

在 Windows DOS 或 Linux 终端中执行命令 `molaical.exe -channel radii -cpp parameter.dat` 即可开始半径计算。计算过程会生成 `channel_radii.dat`、`dot.vmd_plot` 和 `surf.vmd_plot` 三个输出文件。使用 VMD 的 Tk Console 加载 `source dot.vmd_plot` 命令，可以可视化展示纳米管的通道和半径。可视化结果可以根据个人喜好调整颜色和显示方式。

---

## 6. 纳米管半径数据输出与分析

文件 `channel_radii.dat` 存储了计算得到的坐标与对应的半径值。该文件第一列为对应的坐标值，第二列为计算出的半径值。用户可以使用 OriginLab 或 Microsoft Excel 等工具读取该文件并绘制半径沿通道坐标变化的曲线图。该曲线图能够直观展示纳米管通道半径的分布情况。

---

## 7. 孔洞入口半径计算参数配置

计算孔洞（如钾离子通道 KcsA）入口半径时，需切换至相应案例目录如 `005-radiiCal/KcsA`。在 `parameter.dat` 文件中设置 `cpoint` 为选定的孔洞中心坐标。`vector` 参数设置规则与纳米管计算相同，`0.00 0.00 1.00` 代表 Z 轴方向，`0.00 1.00 0.00` 代表 Y 轴方向，`1.00 0.00 0.00` 代表 X 轴方向。计算方向必须与通道的几何方向一致。

---

## 8. 孔洞入口半径计算执行与可视化

在 Windows DOS 或 Linux 终端中执行命令 `molaical.exe -channel radii -cpp parameter.dat` 以计算孔洞半径。计算完成后，在 VMD 的 Tk Console 中依次执行 `mol load pdb KcsA.pdb` 和 `source dot.vmd_plot` 命令进行可视化。可视化图形展示了孔洞入口处的通道结构，用户可根据需要调整显示参数。

---

## 9. 孔洞半径数据输出与分析

孔洞半径计算结果同样保存在 `channel_radii.dat` 文件中，包含坐标列和半径列。用户可以利用 OriginLab 或 Microsoft Excel 等工具导入数据并绘制半径-坐标曲线图。通过分析该曲线图，可以了解孔洞通道内半径的变化趋势。

---

## 10. 计算参数 conpar 的作用与调整

`parameter.dat` 文件中的参数 `conpar` 是一个控制参数，默认值为 0.15。该值决定了计算曲线时的平滑程度，值越大，曲线越平滑，但可能会忽略一些细微的结构变化。对于较窄的孔洞通道或沿 X、Y、Z 某一轴变化较快的情况，建议减小 `conpar` 的值，例如设置为 0.04。若将 `conpar` 设置为 0，则可获得原始的、未经平滑的通道轮廓。

---

## 11. CHARMM 力场文件支持的高级计算

MolAICal 支持使用 CHARMM 力场格式文件（PDB 和 PSF）进行复杂的通道半径计算。进行此类计算时，需切换至包含力场文件的目录，如 `005-radiiCal/GramicidinA`。在 `parameter.dat` 文件中需配置 `pdbpath`、`psfpath` 指定文件路径，并设置 `cpoint` 和 `vector` 参数。`vector` 的方向设置必须与通道轴向一致，如 `0.00 0.00 1.00` 表示沿 Z 轴。

---

## 12. CHARMM 力场模式下的计算命令与可视化

在使用 CHARMM 力场文件时，需在命令行中加入 `-fc charmm` 参数，完整命令为 `molaical.exe -channel radii -cpp parameter.dat -fc charmm`。计算完成后，使用 VMD 加载 PDB 文件并执行绘图脚本，命令为 `mol load pdb 1JNO.pdb` 和 `source surf.vmd_plot`。此过程可生成并展示通道的三维表面结构图。

---

## 13. 高级计算结果的绘图与分析

高级模式计算输出的 `channel_radii.dat` 文件格式与基础模式一致，包含坐标和半径两列数据。用户可使用 OriginLab 或 Microsoft Excel 等工具对该文件中的数据进行绘图分析。生成的半径-坐标曲线图可用于分析复杂通道结构（如 Gramicidin A）内部的几何特性。
