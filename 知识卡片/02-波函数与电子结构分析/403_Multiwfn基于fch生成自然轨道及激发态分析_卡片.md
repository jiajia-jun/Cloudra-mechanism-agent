---
id: 403
title: 在Multiwfn中基于fch产生自然轨道的方法与激发态波函数、自旋自然轨道分析实例
url: http://sobereva.com/403
domain: 波函数与电子结构分析
topic: Multiwfn基于fch生成自然轨道及激发态分析
cards: 1
---

# Multiwfn基于fch生成自然轨道及激发态分析 — 知识卡片

## 1. fch文件中存储的密度矩阵类型

fch文件中至少包含SCF级别的密度矩阵，对于后HF、双杂化泛函、TDDFT等任务，在使用density或特定关键词且有解析梯度时还会包含其它类型密度矩阵。在fch文件中搜索Density字段即可确认包含哪些矩阵，常见对应关系如下：HF、DFT、CASSCF对应SCF；CIS、TDDFT对应CI、CI Rho(1)；CCSD对应CC；MP2、双杂化泛函对应MP2；MP3对应MP3；MP4SDQ对应MP4。

## 开壳层体系的密度矩阵内容
对于开壳层体系（如三重态），在fch文件中除了包含总密度矩阵外，还会包含自旋密度矩阵。例如使用# MP2/cc-pVDZ density关键词时，fch文件里会包含Total SCF Density（HF级别总密度）、Spin SCF Density（HF级别自旋密度）、Total MP2 Density（MP2级别总密度）、Spin MP2 Density（MP2级别自旋密度）。如果是闭壳层体系，则不包含Spin SCF Density和Spin MP2 Density。

## 密度矩阵的定义与关系
fch文件中的总密度矩阵定义为Alpha密度矩阵和Beta密度矩阵的加和。自旋密度矩阵定义为Alpha密度矩阵减去Beta密度矩阵。这些矩阵是Multiwfn产生各类自然轨道的数据基础。

## Multiwfn中三类自然轨道的定义
Multiwfn能产生三类自然轨道，均通过对密度矩阵对角化得到：(a)自然轨道(NO)或空间自然轨道，对总密度矩阵对角化得到，本征值是占据数，范围0.0~2.0，开壳层下也称为unrestricted natural orbital (UNO)；(b)Alpha自然轨道和Beta自然轨道，分别对Alpha和Beta密度矩阵对角化得到，占据数范围0.0~1.0，也称为自然自旋轨道(NSO)；(c)自旋自然轨道(SNO)，对自旋密度矩阵对角化得到，占据数范围-1.0至1.0，正负值分别描述Alpha和Beta单电子。

## 产生TDDFT激发态密度矩阵的Gaussian输入
要对甲醛S1态进行TDDFT分析，需在Gaussian输入文件中使用density关键词将密度矩阵存入chk文件。输入文件示例如下，其中root默认为1即对应S1态：%chk=C:\H2CO.chk\n# PBE1PBE/6-31G* TD density\n\nB3LYP/6-31G* opted\n\n0 1\nC 0.00000000 0.00000000 -0.56221066\nH 0.00000000 -0.92444767 -1.10110537\nH -0.00000000 0.92444767 -1.10110537\nO 0.00000000 0.00000000 0.69618930。

## TDDFT计算fch文件中的密度矩阵字段
将TDDFT计算的chk文件用formchk转换为fch文件后，文件内会包含Total SCF Density（基态DFT密度矩阵）、Total CI Rho(1) Density（TDDFT非弛豫S1态密度矩阵，通常可无视）、Total CI Density（TDDFT弛豫S1态密度矩阵）三个字段。

## Multiwfn基于fch产生自然轨道的操作步骤
在Multiwfn中基于fch文件里的密度矩阵产生自然轨道的步骤如下：启动Multiwfn输入fch文件名；输入200进入其他功能菜单；输入16选择基于fch里的密度矩阵产生自然轨道；根据提示输入要载入的密度矩阵级别（如SCF、CI等）。程序读取密度矩阵后会立即输出自然轨道占据数。

## 更新基函数信息以进行GTF相关分析
在Multiwfn中利用fch产生自然轨道后，内存里的基函数信息已更新为自然轨道，但GTF系数仍对应原始轨道，此时做基于GTF信息的分析无物理意义。为了进行需要GTF信息的分析（如ADCH电荷），必须在产生自然轨道后选择y，让程序将当前波函数导出为new.mwfn并自动载入，从而使内存里的GTF信息也更新为对应新轨道的情况。

## 甲醛S1态的键级与电荷分析实例
利用Multiwfn对甲醛S1态（TDDFT）进行分析，通过产生自然轨道并导出new.mwfn后，计算得到的C-O Mayer键级为1.18，O的ADCH电荷为-0.128。相比之下，基态的C-O Mayer键级为1.98，O的ADCH电荷为-0.296。这种差异是因为S1态是n->pi*激发，既削弱了C-O键，又使电子从氧转移向碳。

## 生成自旋自然轨道(SNO)的Multiwfn操作
要生成自旋自然轨道(SNO)，在载入fch文件并选择功能16产生自然轨道后，当程序询问产生哪种轨道时，应选择3（即SNO）。随后程序会显示自旋自然轨道的占据数，其值在-1.0至1.0之间。

## 丁烷双自由基SNO占据数的解读
对于丁烷双自由基体系，产生的自旋自然轨道(SNO)占据数中，只有一个正值较大（0.957908），一个负值较大（-0.957908）。这对应于理想双自由基体系中存在的一个Alpha单电子和一个Beta单电子，这两个轨道分别描述了未成对Alpha电子和Beta电子的分布特征。

## SNO轨道在Multiwfn中的存储与查看
在Multiwfn中，SNO轨道导出为new.mwfn并被视为开壳层体系，SNO轨道占用记录Alpha轨道的空间，Beta轨道部分无意义（占据数为0）。在主功能0界面查看轨道信息时，可根据占据数找出对应的SNO轨道序号（如1和96），进而绘制轨道等值面图。

## 丁烷双自由基SNO成分的定量分析
利用Multiwfn的轨道成分分析功能（主菜单8 -> Hirshfeld方式），对丁烷双自由基的主要Alpha单电子SNO（1号轨道）进行分析，结果显示Alpha单电子主要分布在C1（70.15%），在C4、C7等处也有少量分布。该定量结果与轨道图形特征相符。

## 自旋密度与SNO分析的互补性
分析自旋密度便于了解Alpha和Beta单电子分布抵消后的“净”分布情况，计算更为省事；而分析SNO可以分别考察未成对Alpha和Beta电子的原始分布，并从轨道角度研究。在丁烷双自由基案例中，两端的碳原子自旋布居与SNO贡献接近，而中间重叠区域因相互抵消导致自旋布居很小。
