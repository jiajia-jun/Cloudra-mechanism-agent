---
key: b593
title: 比SMD算溶解自由能更好的溶剂模型uESE的使用
url: http://sobereva.com/593
domain: 量子化学方法
source: blog
year: 2021
cards: 14
---

# 比SMD算溶解自由能更好的溶剂模型uESE的使用 — 知识卡片

## 1. uESE溶剂模型简介

uESE (universal Easy Solvation Energy Evaluation) 是一种计算溶解自由能的隐式溶剂模型，由Vyboishchikov等人提出，发表于J. Comput. Chem. (2021)。该模型考虑了溶质-溶剂相互作用的极性和非极性部分，旨在提供比SMD模型更高的计算精度，特别是对于离子体系。uESE支持约100种溶剂，而其前身xESE仅支持水溶剂。

---

## 2. uESE模型与SMD模型的主要区别

uESE/xESE模型的极性部分利用COSMO模型，且基于CM5原子电荷计算溶质孔洞表面的静电势，这与SMD基于IEFPCM且通常直接基于电子密度计算不同。uESE/xESE不纳入SCF迭代过程，不影响电子结构，属于“后”溶剂模型，仅适用于基于CM5电荷计算溶解自由能。此外，uESE/xESE包含对溶剂-溶质极性作用部分的经验校正项，且根据溶剂类型（水、非水极性质子溶剂、极性非质子溶剂、非极性溶剂）使用不同的校正项和非极性部分形式。

---

## 3. uESE模型的参数依赖性

uESE/xESE的拟合经验参数依赖于元素、溶剂类型和溶剂本身。极性部分校正项和非极性部分目前仅包含H, C, N, O, F, P, S, Cl, Br, I元素的参数，对于其它元素只能给出COSMO极性部分的结果。相比之下，SMD模型不包含依赖原子半径以外元素的参数。

---

## 4. uESE模型的计算精度优势

根据原文测试，uESE计算溶解自由能的平均绝对误差（MAE）表现为：中性体系中xESE≈SM12>=uESE>=SMD；阳离子体系中uESE>xESE>SMD>=SM12；阴离子体系中uESE>xESE≈SMD12>>SMD。uESE计算中性体系的MAE小于1 kcal/mol，计算阴、阳离子的MAE均小于3 kcal/mol，而SMD计算阴离子的MAE约为8 kcal/mol。

---

## 5. uESE模型的计算级别要求

uESE/xESE模型的经验参数是基于气相下B3LYP/def2-TZVP级别的结构和波函数计算的CM5原子电荷拟合得到的。因此，使用uESE/xESE进行计算时，必须也在此理论级别下计算CM5电荷。

---

## 6. uESE与xESE程序的获取

uESE和xESE方法的同名计算程序可在原链接下载，包含Windows和Linux版可执行文件（不开源）。若原链接失效，程序存档可在备用链接下载。uESE程序可以指定溶剂，而xESE程序只支持水溶剂。

---

## 7. uESE程序的命令行使用格式

uESE程序需通过命令行使用，在Windows下的使用格式为：uESE.exe [输入文件路径] -solvent [溶剂名]。可用的溶剂名称列表可在GitHub的solvent-list.md文件中查阅。

---

## 8. uESE输入文件的生成

uESE/xESE的输入文件需包含各原子的原子序号、坐标以及CM5电荷。使用Multiwfn波函数分析程序时，若将settings.ini中的uESEinp参数设为1，在计算完CM5电荷后程序会询问是否生成uESE/xESE的输入文件。

---

## 9. 使用Multiwfn生成uESE输入文件的操作步骤

启动Multiwfn并载入含有波函数信息的文件（如.fch），依次输入：7（布居分析与原子电荷计算）-> 16（计算CM5电荷）-> 1（使用内置的球对称化的自由原子密度）。随后按回车键确认，即可在当前目录下生成uESE输入文件。

---

## 10. PhO-在乙腈中溶解自由能计算实例（结构优化）

使用Gaussian程序在真空下对PhO-进行结构优化，推荐使用B3LYP/def2TZVP级别。输入文件中需包含电荷和自旋多重度（-1 1），并设置opt和freq关键词以进行优化和频率分析。

---

## 11. PhO-在乙腈中溶解自由能计算实例（uESE运行）

将生成的输入文件（如PhO-_optfreq.inp）与uESE.exe放在同一目录下。在命令行中进入该目录，运行命令：uESE PhO-_optfreq.inp -solvent acetonitrile。程序输出中将包含COSMO静电能、校正项和总溶解自由能。

---

## 12. PhO-在乙腈中溶解自由能计算实例（SMD对比）

为了对比，可使用M05-2X/6-31G*级别计算气相单点能和SMD模型下的乙腈溶剂单点能。溶解自由能通过两者能量差乘以转换因子627.51得到。对比结果显示，uESE计算结果（-54.554 kcal/mol）比SMD结果（-58.98 kcal/mol）更接近实验值（-55.1 kcal/mol）。

---

## 13. uESE模型对高价离子的局限性

uESE模型在测试和拟合参数时仅考虑了带+1、-1电荷的离子。由于高价离子与溶剂的相互作用显著强于一价离子，使用uESE计算高价离子体系预计无法得到较好结果，此时必须使用显式+隐式的杂化溶剂模型。

---

## 14. uESE模型输出的溶解自由能定义

uESE/xESE程序给出的溶解自由能对应于溶解前后均为1M浓度的情况。这一标准定义使得计算结果可直接与同标准下的实验值（如SMD原文补充材料中的数据）进行对比。
