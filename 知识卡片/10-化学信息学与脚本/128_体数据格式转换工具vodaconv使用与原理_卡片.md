---
id: 128
title: 谈谈体数据2：体数据格式转换工具vodaconv的使用及原理
url: http://sobereva.com/128
domain: 化学信息学与脚本
topic: 体数据格式转换工具vodaconv使用与原理
cards: 14
---

# 体数据格式转换工具vodaconv使用与原理 — 知识卡片

## 1. vodaconv程序功能概述

vodaconv是用于体数据格式转换的工具，支持的输入格式包括raw、Gaussian型cube文件(.cub)、OpenDX的格点数据格式(.dx)、Dmol3的.grd格式，输出格式支持raw和cube。该程序只支持平移向量平行于笛卡尔坐标轴的立方格子的格点文件，旨在解决计算化学领域通用渲染程序与Gaussian型cube文件不兼容的问题。
- 程序下载地址：/usr/uploads/file/20150611/20150611014131_45262.rar

---

## 2. Raw文件输入参数设置

当输入文件为.raw格式时，用户必须自行输入各个方向的格点数、格点间隔、起始位置以及数据类型，否则程序无法正确读取。若输入参数与文件实际内容不符（如格点数和数据类型），程序将自动退出；用户可通过计算文件大小来验证参数，例如256*256*128个格点的16bit文件大小应为16777216字节。
- 验证公式：文件大小 = nx * ny * nz * 每数据位数 / 8

---

## 3. Raw文件数据类型与字节序

vodaconv支持8bit整数、16bit整数和单精度浮点数三种raw数据类型，读写整数时一律按无符号整数处理（8bit范围0~255，16bit范围0~65535）。vodaconv.exe读写raw文件采用Big Endian顺序，而vodaconv_LE.exe采用Little Endian顺序。
- 8bit无符号整数范围：0~255
- 16bit无符号整数范围：0~65535

---

## 4. 数据映射与范围变换功能

读取格点数据后，程序提供数据映射功能，用户需输入原数据范围的上下限和新数据范围的上下限，程序按比例将原数据映射到新数值范围。该功能主要用于防止以8/16bit整数输出raw时数据越界，也可用于降采样（如16bit转8bit），或将ELF函数值域[0,1]映射到0~65535以充分利用16bit整数范围。
- 映射示例：ELF值域[0,1]可映射为16bit整数范围[0,65535]

---

## 5. 输出Cube文件的原子处理

当载入.raw/.dx/.grd格式文件并输出为cube文件时，由于输入格式中不包含原子信息，程序会自动在cube文件内添加一个位于原点的氢原子。此操作是为了避免某些程序在读取cube文件时因要求至少有一个原子而产生不兼容问题。

---

## 6. Linux下编译vodaconv的方法

在Linux环境下，使用Intel Fortran编译器执行命令`ifort vodaconv.f90 -o vodaconv`即可编译源代码。切勿使用gfortran编译，因为程序使用了integer*1数据类型，而gfortran不支持该类型。
- 编译命令：ifort vodaconv.f90 -o vodaconv

---

## 7. Windows下编译vodaconv的设置

在Windows下使用Compaq Visual Fortran (CVF) 或 Intel Visual Fortran (IVF) 编译时，需将stack size设置为较大值（如256MB）以防止载入大格点文件时栈内存溢出。在CVF中需在"Project"-"Settings..."-"Link"-"Output"的"Reserve"输入"0x10000000"；在IVF中需在项目属性的"Linker"-"System"里将"Stack Reserve Size"设为"268435456"。
- CVF Stack Reserve: 0x10000000 (256MB)
- IVF Stack Reserve: 268435456 (256MB)

---

## 8. 编译时设置字节序

编译器默认使用Little Endian顺序，若需使用Big Endian顺序，需在编译时进行特定设置。Linux下编译需加上`-convert big_endian`选项；IVF中需在项目属性的Fortran-Compatibility中将"Unformatted file conversion"设为"Big Endian"；CVF中需在"Project"-"Settings"-"Fortran"-"Compatibility"中将"Unformatted file conversion"设为"Big Endian"。
- Linux编译选项：-convert big_endian

---

## 9. 无符号与含符号整数的数值关系

无符号8bit整数范围为0~255，16bit为0~65535；含符号8bit整数范围为-128~127，16bit为-32768~32767。在0~32767范围内两者记录方式相同；当无符号整数值大于32767时，对应的含符号整数值为负值，两者换算关系为：含符号整数值 + 65536 = 无符号整数值。
- 16bit转换关系：Signed = Unsigned - 65536 (当Unsigned > 32767)

---

## 10. Raw文件读写中的整数转换

Fortran标准仅定义含符号整型，而raw格式使用无符号整型，因此读入raw文件的无符号8bit/16bit数据后，必须将负值部分分别加上256或65536以还原正确数值。输出raw文件前，需利用int1()或int2()函数将数据转换为含符号整型，大于127或32767的数据会自动减去256或65536变为负数。
- 读入后修正：负值 + 256 (8bit) 或 65536 (16bit)
- 输出前转换：使用int1()或int2()函数

---

## 11. 二进制文件的字节记录顺序

多字节数据在二进制文件中的记录顺序分为Little Endian（低字节在前）和Big Endian（高字节在前）。例如整数32444（0x7EBC），Little Endian记录为BC 7E，Big Endian记录为7E BC；Windows和Linux程序通常使用Little Endian。
- 32444的十六进制表示：0x7EBC
- Little Endian示例：BC 7E

---

## 12. vodaconv程序的数据存储结构

vodaconv程序内部使用名为defvar的module保存格点设定，包括原点分量orgx/orgy/orgz、格点平移距离dx/dy/dz、点数nx/ny/nz。原子信息保存在数组a中，格点数据根据类型分别存放在8bit含符号整型数组cubmati1、16bit含符号整型数组cubmati2或单精度浮点型数组cubmatr4中。
- 内部统一存储：单精度浮点数组cubmatr4

---

## 13. vodaconv程序的数据载入流程

程序首先根据扩展名判定输入格式，raw格式需用户输入格点设定和数据类型；.dx、.grd和.cub格式文件读取方式相似，数据以单精度浮点数存入cubmatr4。若是raw整型数据，先载入对应整型数组，转换数值后移入cubmatr4，程序内部统一以单精度浮点方式保存数据。
- 数据精度：单精度浮点数

---

## 14. vodaconv程序的数据输出流程

输出时根据目标文件后缀名判断格式，将cubmatr4中的数据以相应方式写入文件。输出cube文件时，若输入格式不含原子信息，程序会自动在原点添加一个氢原子以保证兼容性。
- 自动添加原子：位于原点的氢原子
