---
id: 90
title: Mayer能量分解及APEX4程序使用简介
url: http://sobereva.com/90
domain: 波函数与电子结构分析
topic: Mayer能量分解及APEX4程序使用
cards: 1
---

# Mayer能量分解及APEX4程序使用 — 知识卡片

## 1. CECA能量分解方法特点

CECA (Chemical Energy Component Analysis) 方法不需要人为定义片段，也不需要设定参考态，而是直接利用量子化学计算的整个体系的单粒子密度矩阵信息。CECA可以直接获得体系中每个原子的能量以及每一对儿原子间的能量，每一对儿原子间的能量可以被分解为"动能"+"静电"+"交换"+"重叠"项。

## 体系密度函数与密度的原子划分
体系的密度函数写为原子成分的加和 $\rho(r) =\sum[a]\rho_a(r)$，其中 $\rho_a(r) =\sum[i\in a]\sum[j]P_{i,j}*\chi_j(r)*\chi_i(r)$，$\chi$代表基函数，$P$是密度矩阵。体系的密度矩阵函数也可以拆解为原子的加和 $\rho(r|r')=\sum[a]\rho_a(r|r')$，其中 $\rho_a(r|r')=\sum[i\in a]\sum[j]P_{i,j}*\chi_j(r)*\chi_i(r')$。

## Hartree-Fock总能量的原子对分解形式
Hartree-Fock总能量可以写为原子对儿加和形式 $E=\sum[a]\sum[b>a]E_{a,b}+\sum[a]E_{a,a}$，其中 $E_{a,b}$ 代表 $a,b$ 原子间的作用能，$E_{a,a}$ 是原子 $a$ 在实际体系中自身的能量。

## 原子间作用能E_{a,b}的表达式
$E_{a,b}=2\sum[i\in a]\sum[j\in b]P_{i,j}*<i|T|j> + Z_a*Z_b/R_{a,b} - \int Z_a*\rho_b(r)/|R_a-r|dr - \int Z_b*\rho_a(r)/|R_b-r|dr + \int\int\rho_a(r)*\rho_b(r')/|r-r'|drdr' - \int\int\rho_a(r|r')*\rho_b(r'|r)/|r-r'|drdr'$。第一项是原子间相互作用的动能贡献，第2~5项是静电贡献，最后一项是交换贡献。

## CECA在KS-DFT中的应用
CECA的形式可以直接用在KS-DFT波函数上，前提是将KS-DFT认为是用于提供比较好的密度（矩阵）函数。此时各项加和的结果不等于量子化学计算输出的总能量，因为忽略了相关能，且计算交换能的方式不同。

## Preparation能量定义与性质
原子 $a$ 在实际体系中的能量 $E_{a,a}$ 相对于它在自由状态的能量的变化可正可负，称为 preparation 能量。Preparation 能量一方面来自于电子密度的极化，另一方面来自于电子在原子间的净转移；前者总是使原子能量升高，后者对于失电子的原子会使其能量升高，得电子的原子会使其能量降低。

## CECA结果的基组依赖性
CECA的结果有一定基组依赖性，且不随基组质量提高而收敛，因为CECA对密度矩阵的划分实际上用的是Mulliken布居分析用的平均划分形式。建议至少含弥散函数的基组切不可用，因为弥散函数会明显破坏基组的平衡性。

## APEX4程序简介与支持范围
APEX4 是实现 CECA 的程序，使用简单，运行速度快，仅需要 Gaussian (G92~G09) 的 fch 文件即可，执行中不需要调用量子化学程序。APEX4 支持 RHF、UHF 波函数和 KS-DFT 波函数，缺点是不支持 f 及以上角动量函数。

## APEX4程序编译方法
对于 Linux 下的编译，下载并解压后，将 Makefile 里的 f77 改成编译器，然后在此目录下执行 make 命令。对于 Windows 下的编译，如用 CVF6.5，将所有文件加入工程里然后 build 即可。

## APEX4程序执行方法
将体系的 fch 文件改名为 Test.FChk 后，放到与 APEX4 可执行文件相同路径下，在命令行启动 APEX4 即可。程序最先输出的是 Mayer 键级矩阵和原子价，随后输出各种各样的能量矩阵。

## APEX4输出矩阵的四种总能量关系
"CECA" = ELECTROSTATIC + EXCHANGE + OVERLAP + FINITE-BASIS CORRECTIONS；"CECA + 3- and 4-center contributions" = CECA + Remaining 3- and 4-center；"CECA/T" = ELECTROSTATIC + EXCHANGE + OVERLAP + KINETIC ENERGY；"Exact" = "CECA/T" + Remaining 3- and 4-center。四种矩阵的对角元是 $E_{a,a}$，非对角元是 $E_{a,b}$。

## "Exact"与"CECA/T"矩阵的区别
从精确与近似分解的角度看，"CECA/T" 对三、四中心积分通过近似方式处理，导致加和不精确等于 SCF 能量，而 "Exact" 没有对三、四中心积分进行近似处理，其上三角矩阵元加和直接就是 SCF 能量。从动能考虑的角度看，"CECA/T" 将电子动能同时分解到单中心项和双中心项，不需要 "FINITE-BASIS CORRECTIONS" 这一项。

## APEX4矩阵选取建议
不要使用 "CECA" 和 "CECA + 3- and 4-center contributions" 矩阵，因为原子间作用项过大，化学意义差。如果想精确地将总能量分解为单中心和双中心项，就用 "Exact"。如果将单、双中心项再分解为各种类型能量成分，就用 "CECA/T" 及构成它的各个矩阵。

## APEX4点电荷近似矩阵
程序输出的 "ELECTROSTATICS: POINT-CHARGE APPROXIMATION" 矩阵代表将体系电荷的连续分布用原子电荷模型代替后计算出的静电作用矩阵。"ELECTROSTATICS: DEVIATION FROM P.-CH. APPROIMATION" 矩阵是 "ELECTROSTATIC CONTRIBUTIONS" 矩阵与点电荷近似矩阵的差值，原子间距离越远，这个偏差矩阵数值越小。

## 交错式乙烷的能量分解分析
HF/6-31G** 优化下的交错式乙烷 C-C 键作用能是 -0.1895 a.u.，同一个甲基的氢呈现互斥作用，而一个甲基氢与另一个甲基的位置相反的氢呈现稳定化作用。H2-H6 相互作用能为负值，其中静电项为正值，主要降低能量的因素来自于动能项。

## 改进的化学能量成份分析程序使用
Mayer 提出的改进分解方法目前只支持闭壳层 HF/DFT 波函数。下载 NEWENPART 程序并解压，进入 executables 文件夹，修改 futs 文件里的路径配置，将 fch 文件改名为 Test.FChk 后放到此文件夹里，运行 ./futs ltwd 即可。

## 改进方法的输出结果解读
改进方法输出的 Two-center components 数值越负，代表相应两个原子间键的强度越大，这对于讨论分子在质谱过程的裂解顺序有帮助，比 Mayer 键级更可靠。此方法能正确反映出甲酰胺中 C=O 键的能量明显大于 C-N 键。

## 原子相对于自由原子的能量差
改进的程序还会输出体系中各个原子相对于 ROHF 下计算的自由原子能量的差值。这反映了原子在形成分子过程中的能量变化，但自由原子能量具体基组未明确。
