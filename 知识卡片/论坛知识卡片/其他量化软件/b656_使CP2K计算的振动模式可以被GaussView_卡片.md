---
key: b656
title: 使CP2K计算的振动模式可以被GaussView观看的程序：MfakeG
url: http://sobereva.com/656
domain: 其他量化软件
source: blog
year: 2023
cards: 8
---

# 使CP2K计算的振动模式可以被GaussView观看的程序：MfakeG — 知识卡片

## 1. MfakeG程序简介

MfakeG是一款将CP2K程序计算出的振动模式转化为GaussView可识别格式的工具，旨在解决GaussView仅支持Gaussian程序振动分析输出文件的限制。通过该程序，用户可以在GaussView中方便地显示振动矢量、播放和保存振动动画，以及沿特定振动模式对结构进行位移。MfakeG可在Windows和Linux系统上运行，并免费提供下载。

---

## 2. CP2K输出Molden振动文件的设置

在CP2K的振动分析任务输入文件中，需在`&VIBRATIONAL_ANALYSIS`字段内添加特定参数以输出后缀为.mol的Molden文件。默认生成的文件名为`[项目名]-VIBRATIONS-1.mol`。若使用Multiwfn创建CP2K输入文件，默认也会包含生成该.mol文件的设置。

---

## 3. CP2K输出Molden文件的输入参数

为了在振动分析结束时输出Molden文件，CP2K输入文件中应包含以下代码块：
```
  &PRINT
  &MOLDEN_VIB
  &END MOLDEN_VIB
  &END PRINT
```
此配置确保计算结束后生成记录振动信息的.mol文件。

---

## 4. Molden振动文件的数据内容

CP2K生成的.mol文件包含了丰富的振动分析数据，具体包括元素类型、原子坐标、振动频率、描述振动矢量的正则坐标以及红外强度。该文件格式与常见的仅记录分子结构和键连关系的.mol文件完全不同。

---

## 5. MfakeG程序的基本使用方法

启动MfakeG程序后，输入CP2K生成的.mol文件的路径。程序会在相同目录下生成一个文件名相同但带有`-fake`后缀的.out文件。该.out文件为伪Gaussian输出格式，可直接载入GaussView，通过Results - Vibrations界面查看振动信息。

---

## 6. 周期性体系晶胞边框的显示方法

为了让GaussView在显示周期性体系时能够呈现晶胞边框，需要自行编辑.mol文件。在文件的第二行插入`[Cell]`字段，随后填入三行晶胞矢量数据。晶胞矢量单位为埃。

---

## 7. 晶胞矢量数据格式示例

在.mol文件中插入的晶胞矢量数据格式如下所示：
```
  [Cell]
  19.25142628 0.00000000 0.00000000
  -9.62562669 16.67336579 0.00000000
  0.00000000 0.00000000 15.00000000
```
这三行数据分别代表晶胞的三个基矢量。经过MfakeG转换后，伪Gaussian输出文件的原子坐标部分末尾会自动增加三个对应晶胞矢量的原子信息。

---

## 8. 基于Molden格式的通用性设计

MfakeG选择转换.mol格式而非直接转换CP2K输出文件，是因为.mol格式更为简单且具有更好的通用性。用户可以将其他计算化学程序的振动分析结果写成.mol格式，再利用MfakeG转换为GaussView可读文件，从而在GaussView中查看振动模式。
