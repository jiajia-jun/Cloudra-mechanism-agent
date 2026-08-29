---
key: t21352
title: ORCA��������def2ϵ��Gaussian��ʽ�Ļ����ļ�(H-Kr)
url: http://bbs.keinsci.com/thread-21352-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2021
cards: 10
---

# ORCA��������def2ϵ��Gaussian��ʽ�Ļ����ļ�(H-Kr) — 知识卡片

## 1. ORCA 基组重缩写基组列表与元素范围

提供了一套基于 DKH 和 ZORA 相对论方法的 def2 系列基组重缩写版本，覆盖从 SVP 到 QZVPP 的不同精度。支持的基组包含常规版本以及 ma-（模型原子）前缀版本，元素适用范围为 H-Kr。这些基组文件适用于全电子相对论计算，并可用于转换为 Gaussian 输入文件。

---

## 2. Gaussian DKH 计算输入设置

在 Gaussian 中使用 DKH2 相对论方法和重缩写基组时，需要在路由行中指定 `int(nobasistransform,DKH2)` 和 `iop(3/93=1)`。`iop(3/93=1)` 用于将核模型从默认的高斯分布更改为点电荷分布，以便与 ORCA 的默认设置保持一致。

---

## 3. ORCA DKH 计算输入设置

在 ORCA 中进行 DKH 相对论计算时，需在输入文件中设定 `%rel` 模块，指定方法为 `DKH` 且阶数为 2。为了与 Gaussian 进行细致对比，应设置极高的收敛精度，即使用 `VeryTightSCF` 关键字，并将 `%scf` 模块下的 `Thresh` 设为 `1e-12`，`Tcut` 设为 `1e-14`。

---

## 4. 使用 mkl2gjf 转换基组的通用步骤

转换过程首先需要编写一个包含 H-Kr 所有元素的 ORCA 输入文件，并开启 `DryRun True` 模式。运行 ORCA 生成 `.mkl` 文件后，使用 `orca_2mkl` 命令提取基组信息，最后通过 `mkl2gjf` 程序将基组数据转换为 Gaussian 的 `.gjf` 格式。

---

## 5. ORCA 基组提取输入文件示例

用于提取基组的 ORCA 输入文件应包含所有目标元素，并关闭迭代计算。具体示例如下：使用 `! RHF DKH-def2-SVP noiter` 关键字，设置 `%maxcore 2000`，在 `%scf` 模块中设置 `DryRun True`，并在坐标部分按顺序列出 H 到 Kr 的原子坐标。

---

## 6. 基组提取与转换命令

获取 `.mkl` 文件后，需执行命令 `orca_2mkl DKH-def2-SVP -mkl` 进行处理。随后运行 `mkl2gjf DKH-def2-SVP.mkl` 将基组转换为 Gaussian 格式，如果合并了分子轨道文件，可添加 `-mo` 参数。

---

## 7. mkl2gjf 工具的来源与使用

mkl2gjf 是 MOKIT 程序包中的一个小工具，可从 GitLab 下载源码。通过执行 `make mkl2gjf` 编译后，即可使用该工具将 ORCA 的基组数据转换为 Gaussian 可用的格式。

---

## 8. 基组文件中的元素符号替换

转换得到的 `.gjf` 文件初始包含整数标签，需使用 Fortran 程序 `replace_int_with_elem.f90` 进行处理。运行 `gfortran replace_int_with_elem.f90 -o replace_int_with_elem` 编译程序，然后执行 `./replace_int_with_elem DKH-def2-SVP.gjf`，将整数替换为对应的元素符号，并确保基组标题与文件名一致。

---

## 9. ORCA 拟合基组的局限性注意事项

ORCA 生成的 `.mkl` 文件中的基组数据可能存在缺陷，缺乏某些描述信息，直接使用 mkl2gjf 转换可能导致全电子计算出现严重问题。由于 ORCA 未提供官方基组文件，这种转换格式的正确性无法得到绝对保证，由此产生的问题需由使用者自行承担。

---

## 10. 基组转换的替代方案

对于有经验的用户，可以尝试替代方案，即在 ORCA 输入文件中添加 `PrintBasis` 关键字。直接从 ORCA 输出文件中读取基组信息并手动转换为 Gaussian 格式，这种方式虽然可能涉及 un-normalized 形式，但在数据获取上可能比从 `.mkl` 文件提取更为简单直接。
