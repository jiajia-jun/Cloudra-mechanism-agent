---
id: 472
title: 将多帧xyz文件转化成量子化学输入文件的工具：xyz2QC
url: http://sobereva.com/472
domain: 化学信息学与脚本
topic: xyz2QC多帧转Gaussian与ORCA输入
cards: 1
---

# xyz2QC多帧转Gaussian与ORCA输入 — 知识卡片

## 1. xyz2QC程序功能与定位

xyz2QC是Molclus程序（1.7版及之后）的一个子程序，旨在解决在超算上不方便使用Molclus自动调用其他程序的问题，它可以将含有多帧的.xyz文件转化成Gaussian和ORCA输入文件。
- xyz2QC基于Gaussian和ORCA的模板文件进行转换。
- 模板文件Gaussian必须叫template.gjf，ORCA必须叫template.inp，运行前必须放在当前目录下。
- 输入的.xyz文件可以是genmer、gentor产生的，也可以是molclus产生的isomers.xyz，或isostat筛选后的cluster.xyz。
- 转换出的输入文件既可以是包含所有被选结构的单一多步任务文件，也可以拆分成一个个独立文件。

## xyz2QC操作步骤示例
操作xyz2QC时，需将cluster.xyz和template.gjf放在xyz2QC目录下，启动程序后依次输入选项、文件路径和帧号范围。
- 示例输入依次为：`1`（产生含多步的单一Gaussian输入文件）、`cluster.xyz`、`1-3`（选择xyz文件里的第1~3帧）。
- 程序执行后会生成Gaussian.gjf文件，按回车即可退出。
- 也可以选择拆分成独立的.gjf文件，如000001.gjf、000002.gjf...，文件名数字前头可以自行定义前缀。

## Gaussian多步任务输出格式
xyz2QC生成的Gaussian多步任务输入文件使用`--link1--`分隔不同结构，可以直接提交Gaussian计算挨个算出能量。
- 输出文件中每个结构的计算部分由模板内容与具体坐标构成，中间用`--link1--`隔开。
- 计算完成后可使用Ultraedit或Linux下的grep命令提取带有SCF Done字样的行来获取能量。
- `--link1--`前面的空行数目必须正确，这取决于template.gjf末尾的空行数。

## 拆分独立文件的优势与Gaussian模板占位符
将.xyz里的指定帧拆分成单独的.gjf文件可以防止单个任务失败导致整个多步任务停止，同时Gaussian模板支持`[FILENAME]`占位符以管理chk文件。
- 如果多步任务中有一个失败（如SCF不收敛），整个任务会停止，拆分成独立文件可避免此问题。
- 模板中的`[FILENAME]`占位符会被替换为“前缀 帧号”。
- 可在模板中写`%chk=/sob/[FILENAME].chk`，使计算后的chk文件以恰当名字保存在/sob目录，便于配合Multiwfn批量做波函数分析。

## ORCA多步任务注意事项
使用xyz2QC产生ORCA的多步任务单一输入文件时，强烈建议在模板文件template.inp里加入`noautostart`关键词。
- 如果不加`noautostart`，下一个任务的初猜会自动用前一个任务收敛的波函数，由于选定结构的几何差异可能不小，这样得到的初猜可能会很糟糕。
- `noautostart`代表不自动从与当前文件同名的.gbw文件中读取初猜波函数，可确保计算准确。
