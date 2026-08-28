---
id: 593
title: 比SMD算溶解自由能更好的溶剂模型uESE的使用
url: http://sobereva.com/593
domain: 量子化学方法
topic: uESE溶剂模型原理及溶解自由能计算
cards: 1
---

# uESE溶剂模型原理及溶解自由能计算 — 知识卡片

## 1. uESE溶剂模型的基本定义

uESE (universal Easy Solvation Energy Evaluation) 是一种用于计算溶解自由能的隐式溶剂模型，由Vyboishchikov等人提出，原文见 J. Comput. Chem. (2021) DOI: 10.1002/jcc.26531。uESE模型考虑了溶质-溶剂相互作用的极性和非极性部分，支持约100种溶剂，特别在计算离子体系溶解自由能方面表现出优于SMD模型的精度。
- uESE模型不纳入SCF迭代过程，属于“后”溶剂模型，仅基于CM5电荷计算溶解自由能。
- 模型对溶剂分为四类：水、非水极性质子溶剂、极性非质子溶剂、非极性溶剂。

## uESE模型的极性部分计算原理
uESE模型的极性部分利用COSMO模型，但不基于电子密度计算，而是基于CM5原子电荷计算。具体来说，在求解表面显著电荷时，使用CM5电荷计算溶质孔洞表面的静电势。
- uESE模型包含对溶剂-溶质极性作用部分的经验校正项。
- 模型拟合参数依赖于元素、溶剂类型和溶剂本身，极性部分校正项和非极性部分目前只支持H,C,N,O,F,P,S,Cl,Br,I元素。

## uESE与xESE及SMD的精度对比
根据uESE原文测试，不同体系的溶解自由能计算精度（平均绝对误差，MAE）关系如下：中性体系为xESE≈SM12>=uESE>=SMD；阳离子体系为uESE>xESE>SMD>=SM12；阴离子体系为uESE>xESE≈SMD12>>SMD。uESE计算中性体系的MAE小于1 kcal/mol，计算阴、阳离子体系的MAE都小于3 kcal/mol，而SMD计算阴离子的MAE达到8 kcal/mol左右。
- 计算离子体系溶解自由能时，若不想用杂化溶剂模型，应使用uESE而非SMD。

## uESE模型的计算级别限制
uESE和xESE模型中的经验参数是基于气相下B3LYP/def2-TZVP级别的结构和波函数计算的CM5原子电荷拟合的。因此，用户在使用uESE/xESE时，CM5电荷必须在该理论级别下计算以确保准确性。
- 如果使用其它理论级别计算CM5电荷，可能会导致结果不准确。

## uESE程序在Windows下的使用格式
uESE程序是同名计算软件，不开源，需要在命令行下运行。Windows下的使用格式为：uESE.exe [输入文件路径] -solvent [溶剂名]。
- 可用的溶剂名称列表见 https://github.com/vyboishchikov/ESE/blob/main/solvent-list.md。
- 若原链接失效，程序可在 http://sobereva.com/attach/593/uESE,xESE.zip 下载。

## uESE输入文件的生成方法
uESE程序的输入文件需要包含各原子的原子序号、坐标以及CM5电荷。使用Multiwfn程序计算CM5电荷时，通过将settings.ini里的uESEinp参数设为1，可在计算完CM5电荷后选择生成uESE/xESE的输入文件。
- Multiwfn计算CM5电荷需要提供.wfn/.wfx/.fch/.molden/.mwfn等包含波函数信息的文件。
- 若使用Multiwfn生成的输入文件发表文章，需提及并按照提示恰当引用Multiwfn。

## uESE计算PhO-在乙腈中的溶解自由能示例步骤
计算PhO-在乙腈中的溶解自由能，首先需在气相下使用B3LYP/def2TZVP对PhO-进行优化和频率计算，确认无虚频后，使用formchk将.chk文件转换为.fch文件。接着使用Multiwfn载入.fch文件，选择布居分析与原子电荷计算功能中的CM5电荷计算，并生成uESE输入文件。
- Gaussian输入文件关键字为 `#p B3LYP/def2TZVP opt freq`，电荷与多重度设为 `-1 1`。

## uESE计算PhO-溶解自由能的具体操作命令
在Multiwfn中依次输入 `7` (布居分析与原子电荷计算)、`16` (计算CM5电荷)、`1` (使用内置的球对称化的自由原子密度)，确认生成输入文件。在命令行中进入uESE.exe所在目录，运行 `uESE PhO-_optfreq.inp -solvent acetonitrile`。
- 程序输出COSMO静电能、校正项和总溶解自由能，本例中总溶解自由能为 -54.554 kcal/mol。

## uESE与SMD计算PhO-溶解自由能的误差对比
对于PhO-在乙腈中的溶解自由能，uESE计算值为 -54.554 kcal/mol，实验值为 -55.1 kcal/mol，误差为 0.55 kcal/mol。使用SMD模型（基于M05-2X/6-31G*级别计算单点能）得到的溶解自由能为 -58.98 kcal/mol，相对于实验值的误差为 -3.9 kcal/mol。
- 该对比体现了uESE在计算阴离子溶解自由能时相对于SMD的显著优势。

## uESE模型对高价离子的适用性限制
uESE模型在测试和拟合参数时，仅考虑了带有+1和-1电荷的离子。由于高价离子与溶剂的相互作用显著强于一价离子，使用uESE计算高价离子无法得到较好结果，必须使用杂化溶剂模型。
- 对于非一价离子体系，不应直接使用uESE模型。
