---
key: b530
title: 一键把所有gjf文件转成xyz文件、把所有Gaussian输出文件转成gjf文件的脚本
url: http://sobereva.com/530
domain: 化学信息学与脚本
source: blog
year: 2020
cards: 11
---

# 一键把所有gjf文件转成xyz文件、把所有Gaussian输出文件转成gjf文件的脚本 — 知识卡片

## 1. 脚本运行前提与环境要求

这两个Linux下的Bash shell脚本利用Multiwfn程序进行格式转换，要求Multiwfn必须已恰当安装并能够通过`Multiwfn`命令直接启动。建议使用Multiwfn的最新版本以确保兼容性，该程序可从官网免费下载。这些脚本也可以在Multiwfn安装目录下的examples/scripts目录中找到。

---

## 2. gjf文件批量转xyz脚本功能

`gjf2xyz.sh`脚本用于将当前目录下的所有Gaussian输入文件（.gjf）转换为XYZ坐标文件（.xyz）。脚本运行时会显示转换进度，例如输出“Converting filename.gjf to filename.xyz ... (n of total)”。待转换的gjf文件应当使用笛卡尔坐标记录。

---

## 3. out文件批量转gjf脚本配置要求

`out2gjf.sh`脚本用于将当前目录下的所有Gaussian输出文件（.out）转换为Gaussian输入文件（.gjf）。运行此脚本前，必须将Multiwfn配置文件`settings.ini`中的`iloadGaugeom`参数设置为1，以确保Multiwfn能从输出文件中读取几何结构数据。

---

## 4. out转gjf脚本输出特征

脚本生成的gjf文件中，电荷和自旋多重度与原输出文件保持一致（使用赝势的情况除外）。坐标部分取自输出文件中最后一次输出的几何结构，如果原文件包含输入朝向坐标，则使用输入朝向，否则使用标准朝向。生成的gjf文件默认包含B3LYP/6-31G*关键词，需根据实际计算任务进行修改。

---

## 5. 生成内坐标gjf脚本及限制

若需要生成内坐标（Z矩阵）格式的Gaussian输入文件，应使用`out2gjf_zmat.sh`脚本。需注意，并非所有体系都能用内坐标描述（例如乙炔），除非引入虚原子，否则此类体系无法通过该脚本成功生成输入文件。

---

## 6. 脚本对文件后缀的适应性

如果Gaussian输出文件使用`.log`作为后缀名，需将脚本中的`out`字符串替换为`log`。同样地，通过替换脚本中的文件后缀名，可以批量将xyz、mol、mol2、pdb、gro、wfn、wfx、cub等多种Multiwfn支持的格式转换为gjf文件。

---

## 7. 波函数文件转gjf的特殊处理

当将fch、molden、mwfn等含有基函数信息的波函数文件转换为gjf文件时，需要在脚本的`${inf//out/gjf}`行下方插入一行内容`n`。此操作代表不将当前波函数信息作为初猜写入新生成的gjf文件中。

---

## 8. 模板文件template.gjf的使用方法

若当前目录下存在`template.gjf`文件，且其坐标部分用`[geometry]`或`[GEOMETRY]`标记，脚本将自动使用该文件作为模板生成新的gjf。在生成过程中，`[geometry]`或`[GEOMETRY]`占位符会被实际体系的坐标替换。

---

## 9. 模板文件中的文件名变量替换

在使用`template.gjf`生成新gjf文件时，若文件中某行包含`[name]`字符，该字符串将被替换为新生成的输入文件名（不包含后缀）。此功能允许在模板文件中动态引用文件名，用于设置chk文件路径或输出文件名等。

---

## 10. 模板文件对电荷与自旋多重度的继承

当载入Gaussian输入/输出文件、ORCA输入文件或含波函数信息的文件时，新生成的gjf文件将自动继承这些文件中的净电荷和自旋多重度。若载入的文件不包含此类信息，则沿用`template.gjf`中定义的电荷与自旋多重度。

---

## 11. 坐标朝向读取设置说明

通过修改Multiwfn的`settings.ini`文件中的`iloadGaugeom`参数，可以控制从输出文件中读取坐标的方式。将该参数设置为2时，脚本将总是载入标准朝向下的坐标；设置为1时，则根据输出文件内容决定是否使用输入朝向。
