---
id: 593
title: 比SMD算溶解自由能更好的溶剂模型uESE的使用
url: http://sobereva.com/593
domain: 量子化学方法
topic: uESE溶剂模型原理及溶解自由能计算
cards: 8
---
## 1. uESE与SMD溶剂模型的特点对比

SMD模型在Gaussian程序中极性部分等同于IEFPCM，非极性部分考虑周到，但计算离子体系溶解自由能误差远大于中性体系。uESE (universal Easy Solvation Energy Evaluation) 模型考虑了溶质-溶剂相互作用的极性和非极性部分，与SMD的区别在于极性部分利用基于CM5原子电荷的COSMO模型，且不纳入SCF迭代过程，不影响电子结构。uESE原文见于J. Comput. Chem. (2021) DOI: 10.1002/jcc.26531，类似的xESE模型见于Phys. Chem. Chem. Phys., 22, 14591 (2020)。

---

## 2. uESE/xESE模型的工作机制与限制

uESE/xESE属于“后”溶剂模型，仅基于气相下B3LYP/def2-TZVP级别的结构和波函数计算CM5原子电荷，并包含对溶剂-溶质极性作用的经验校正项。模型将溶剂分为四类：水、非水极性质子溶剂、极性非质子溶剂、非极性溶剂，极性部分校正项和非极性部分目前仅支持H,C,N,O,F,P,S,Cl,Br,I元素参数。uESE支持约100种溶剂，xESE仅支持水溶剂。

---

## 3. uESE与SMD及SM12的计算精度统计

根据uESE原文测试，溶解自由能计算的平均绝对误差（MAE）关系为：中性体系xESE≈SM12>=uESE>=SMD；阳离子体系uESE>xESE>SMD>=SM12；阴离子体系uESE>xESE≈SMD12>>SMD。uESE计算中性体系MAE小于1 kcal/mol，阴、阳离子体系MAE都小于3 kcal/mol，而SMD计算阴离子MAE达到8 kcal/mol左右。

---

## 4. uESE程序下载与命令行使用格式

uESE和xESE程序需基于命令行使用，Windows下的使用格式是：uESE.exe [输入文件路径] -solvent [溶剂名]。可用的溶剂名称列表见https://github.com/vyboishchikov/ESE/blob/main/solvent-list.md。若原文链接无法访问，可在http://原作者.com/attach/593/uESE,xESE.zip下载程序。

## 5. 使用Multiwfn生成uESE输入文件

Multiwfn波函数分析程序可直接计算CM5电荷，通过将settings.ini里的uESEinp参数设为1，计算完CM5电荷后会询问是否产生uESE/xESE的输入文件。uESE/xESE的输入文件需要包含各原子的原子序号、坐标以及CM5电荷，若使用Multiwfn产生的输入文件发表文章，需提及并恰当引用Multiwfn。

---

## 6. uESE计算溶解自由能的步骤与参数设置

使用uESE计算溶解自由能需先用B3LYP/def2-TZVP在真空下优化结构，然后用formchk将chk文件转换为fch文件。接着使用Multiwfn载入fch文件，选择布居分析与原子电荷计算功能计算CM5电荷，并生成uESE输入文件。最后在命令行运行uESE程序，指定输入文件和溶剂名称即可得到溶解自由能。

---

## 7. uESE计算PhO-在乙腈中的溶解自由能实例结果

对PhO-在乙腈中的计算实例显示，运行uESE PhO-_optfreq.inp -solvent acetonitrile后输出COSMO electrostatic energy = -66.946 kcal/mol，Correction term = 12.393 kcal/mol，Total solvation free energy = -54.554 kcal/mol。该结果与实验值-55.1 kcal/mol相比误差仅为0.55 kcal/mol，而同一体系下SMD模型计算误差为-3.9 kcal/mol。

---

## 8. uESE模型对离子电荷的限制

uESE模型在测试和拟合参数时仅考虑了带+1、-1电荷的离子。由于高价离子与溶剂相互作用显著强于一价离子，使用uESE计算高价离子体系预计无法得到较好结果，必须使用显式+隐式的杂化溶剂模型。
