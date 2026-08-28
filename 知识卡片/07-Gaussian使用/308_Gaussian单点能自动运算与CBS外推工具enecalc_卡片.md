---
id: 308
title: Gaussian单点能自动相互运算工具enecalc
url: http://sobereva.com/308
domain: Gaussian使用
topic: Gaussian单点能自动运算与CBS外推工具enecalc
cards: 8
---

# Gaussian单点能自动运算与CBS外推工具enecalc — 知识卡片

## 1. enecalc工具简介与用途

enecalc是一个用于对Gaussian计算的单点能进行数学运算的工具，程序会对指定结构在不同级别下调用Gaussian计算单点能，然后根据预设系数进行相互运算得到最终能量。该工具非常适合用于进行基组外推计算。程序首次发布于2015年11月3日，最后更新于2020年8月21日。

---

## 2. 压缩包文件组成

enecalc工具的压缩包内包含：编译好的Windows版可执行文件enecalc.exe、编译好的Linux 64bit版可执行文件enecalc、用于设定运行参数的settings.ini文件、以及包含体系结构和内存内核数设定且关键词部分留空的模板文件template.gjf。

---

## 3. 基组外推公式实例

在一般的外推计算中，例如计算E[QCISD(T)/CBS]，可以使用如下公式：E[QCISD(T)/CBS]=1.4629*E[QCISD(T)/TZ]-0.4629*E[QCISD(T)/DZ]+1.6938*E[MP2/QZ]-2.1567*E[MP2/TZ]+0.4629*E[MP2/DZ]。

---

## 4. 一般情况下的settings.ini配置参数

在一般非ONIOM计算中，settings.ini文件应包含Gaussian路径（用双引号扩住）、当前系统设定（1为Windows，2为Linux或MacOS）、ONIOM任务标志（0为非ONIOM）、计算级别数、每个级别的能量系数、计算时用的关键词以及用于定位能量的字符串（如QCISD(T)=）。

---

## 5. 模板文件template.gjf格式

模板文件template.gjf用于定义计算结构，包含内存（%mem）、内核数（%nproc）等设定，关键词行留空由程序自动填入，随后是电荷、自旋多重度及分子结构坐标。

---

## 6. enecalc程序运行流程

启动enecalc后，程序读取当前目录下的settings.ini，将第一个计算级别的关键词套入template.gjf生成001.gjf，调用Gaussian产生001.out并读取能量显示。此过程重复直至所有级别处理完毕，最后输出根据定义规则运算出的最终总能量。

---

## 7. ONIOM计算下的settings.ini配置

当基于ONIOM计算进行能量外推时，settings.ini文件中的ONIOM任务标志应设为1，设定计算级别数和系数，写入ONIOM关键词（如oniom(CCSD(t)/cc-pVTZ:M062X/TZVP)），此时不需要写用于定位能量的字符串，因为程序直接读取输出文件中ONIOM: extrapolated energy =后面的值。

---

## 8. ONIOM模板文件结构

ONIOM计算的模板文件template.gjf需设置内存和内核数，包含标题行、电荷自旋多重度，以及带有原子层定义标记（如L, H）的分子坐标结构。
