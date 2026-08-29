---
id: 372
title: Molcas的计算双原子分子光谱常数的模块vibrot使用简介
domain: 激发态与光谱
topic: Molcas_vibrot_模块计算双原子分子光谱常数
cards: 15
---

## 1. Molcas的vibrot模块功能概述
Molcas程序的vibrot模块专门用于计算双原子分子的转动-振动光谱常数，使用时只需直接提供离散的势能面扫描数据即可，完全不依赖于Molcas的其它模块。该模块基于输入数据点做三次样条插值构建势能面，还可以计算振动波函数、转-振态间的跃迁性质以及温度平均下的可观测量（需提供不同键长对应的偶极矩等数值）。

---

## 2. 势能面扫描的数据准备要求
使用vibrot模块前需用量化程序对分子势能面进行扫描，获得极小点附近区域内的离散“坐标 能量”数据点，坐标单位必须为Bohr。数据点可均匀或不均匀分布，考察的振动能级越高所需的扫描键长范围应越大；若要输出准确的解离能，扫描距离的上限值需相当大。对于扫描上限较大的情况，建议使用UCCSD(T)、TCCSD或MRCI等方法以超越不稳定点。

---

## 3. vibrot模块的输入文件格式
vibrot的输入文件包含&VIBROT开头的关键词段，Title定义标题，Atoms定义原子种类（前导0代表最大丰度同位素质量），Potential段下列出键长和能量。可选设置包括Plot定义插值势能曲线输出范围，VIBRational定义振动量子数范围，ROTAtional定义转动量子数范围，Grid和Range定义输出振动波函数的网格密度和范围，PRWF指令直接打印振动波函数。

---

## 4. vibrot模块的运行命令与输出文件
运行命令格式为`molcas [输入文件名] > [输出文件名]`。程序运行瞬间完成，生成的文件中[文件名].VibWvs是二进制振动波函数数据，[文件名].VibPlt0包含基于插值产生的势能曲线数据，[文件名].out包含计算结果信息，.xml和.status文件可忽略。

---

## 5. vibrot输出的势能曲线极值点信息
输出文件中的extremum points部分给出了插值势能曲线的极小点位置（R，单位au）和势能值，以及外推到无穷远处的势能值。例如HF在UCCSD(T)/cc-pVQZ下的极小点位于1.731435 au，能量为-100.373181 Hartree，无穷远外推值为-100.127233 Hartree。

---

## 6. vibrot输出的振转能级能量
输出文件中的Eigenstates部分列出了各个振动量子数和转动量子数组合下的能量相对于势能曲线最小点的数值（单位Hartree）。例如v=0,J=0的值为0.009399（相当于零点能），v=1,J=0的值为0.027559。

---

## 7. 转动常数B和离心畸变常数D的计算
输出文件Rotational constants部分列出了依赖于振动量子数的转动常数B和离心畸变常数D。例如v=0时B=0.205907E+02 cm-1，D=0.210149E-02 cm-1。Observed and computed term values部分展示了基于这些常数计算的J=1,2,3转动能及差值。

---

## 8. 光谱常数De和Betae的计算与验证
输出文件中包含计算离心畸变常数D所需的De和Betae值，以及由此算出的对应v=0,1,2时的D值对比。示例输出显示Spectroscopic constants De=0.212773E-02 cm-1，Betae=-.534833E-04 cm-1，Observed and computed D values列给出了直接计算值与通过常数拟合值的对比。

---

## 9. 光谱常数Be、Alphae和Gammae的计算
输出文件中给出了计算转动常数B所需的Be、Alphae和Gammae值，以及由此算出的对应v=0,1,2时的B值对比。示例输出显示Be=0.209815E+02 cm-1，Alphae=0.786143E+00 cm-1，Gammae=0.916029E-02，Observed and computed B values列显示了拟合精度。

---

## 10. 振动常数we、wexe、weye的计算
输出文件给出了计算振动能级所需的振动常数we、wexe、weye，以及由此算出的对应v=0,1,2时的振动能级。示例输出显示we=0.417438E+04 cm-1，wexe=-.990961E+02 cm-1（注意此处数值含负号，与习俗不同），weye=0.290290E+01 cm-1。Observed and computed band origins列出了能级计算值与拟合值的对比。

---

## 11. 双原子分子光谱常数汇总及解离能说明
输出文件最后汇总了最重要的双原子分子光谱常数，包括Re(埃)、De(ev)、D0(ev)、we、wexe、weye、Be、Alphae、Gammae、Dele和Betae。由于势能面扫描范围有限（示例仅到4 Bohr），若未达到水平区域，De和D0的数值仅为外推值，仅供参考。

---

## 12. vibrot的Term values矩阵与振动波函数
输出文件Term values部分以cm-1为单位重新输出了各组合相对于极小点的能量。随后是不同转动量子数J下各振动能级的振动波函数随径向距离（Bohr）变化的数据，vibrot通过Numerov方法求解二阶微分方程得到这些波函数，且给出的波函数并未归一化。

---

## 13. vibrot计算振动平均量与跃迁属性
vibrot可通过在输入文件添加observable段提供依赖r的量p，计算积分$\int \phi(v1) p \phi(v2) dr$。例如提供坐标值本身可计算振动平均结构$\int |\phi|^2 r dr$，输出文件中Matrix elements of observable给出了J=0时各振动态间的跃迁矩阵元，非谐振势下可出现$\Delta v \neq \pm 1$的跃迁值。

---

## 14. vibrot计算温度平均可观测量
vibrot能根据玻尔兹曼分布计算各转-振态的分布比例，加权平均得到特定温度下observable段所提供量的平均值。输出文件中的Temperature averaged observable给出了结果（如300K下的温度平均键长），具体温度可通过输入文件TEMPERATURE关键词设定。

---

## 15. vibrot在计算零点能方面的优势
对于高精度计算双原子分子的热力学数据（如解离能ZPE），vibrot结合高级别势能面扫描数据的方法非常精确。该方法只需在平衡位置及附近分布点（至少7个）即可计算ZPE，优于Gaussian的freq=anharmonic（需四阶导数且不支持CCSD(T)）及基于谐振近似+校正因子的粗糙做法。
