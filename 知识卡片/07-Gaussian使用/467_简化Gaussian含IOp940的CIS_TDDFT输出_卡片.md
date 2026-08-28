---
id: 467
title: 简化用了IOp(9/40=x)的Gaussian的CIS/TDDFT任务的输出文件的程序：simpIOp940
url: http://sobereva.com/467
domain: Gaussian使用
topic: 简化Gaussian含IOp940的CIS_TDDFT输出
cards: 6
---

# 简化Gaussian含IOp940的CIS_TDDFT输出 — 知识卡片

## 1. simpIOp940程序的功能与用途

simpIOp940程序用于简化使用了IOp(9/40=x)关键词的Gaussian CIS/TDDFT计算输出文件。该程序允许用户输入组态系数绝对值的阈值，仅输出大于该阈值的组态系数，以便于人工查看激发态主要信息。

---

## 2. 使用IOp(9/40=x)的原因

Gaussian默认只输出绝对值大于0.1的组态系数，这对激发态描述的精度不够。为了使用Multiwfn进行依赖于组态系数的电子激发分析，用户一般需要使用IOp(9/40=x)输出所有绝对值大于10^-x的组态系数，一般x设为4。

---

## 3. simpIOp940程序的主要输出结果

simpIOp940程序处理输入文件后，会生成包含激发态信息及大于阈值组态系数的结果文件（默认为new.out）。程序还会输出名为largest_pair.txt的文件，列出各激发态中系数绝对值最大的轨道跃迁，包含激发态序号、MO对和系数值。

---

## 4. simpIOp940程序的下载与版本

simpIOp940程序可在此下载：http://sobereva.com/soft/simpIOp940.rar。程序包中包含Windows版（带.exe后缀）和Linux版（不带后缀）的可执行文件，以及Fortran源文件。

---

## 5. simpIOp940程序的使用示例

程序包中的示例文件uracil.out使用了IOp(9/40=4)进行TDDFT计算。运行simpIOp940，输入uracil.out路径并设置阈值为0.1后，生成的new.out文件仅保留了绝对值大于0.1的组态系数，largest_pair.txt文件显示了各激发态贡献最大的MO对。

---

## 6. simpIOp940程序的兼容性说明

由于电子激发任务类型很多，simpIOp940程序不一定兼容所有情况。若碰到不兼容的情况，用户需自行修改程序。
---
