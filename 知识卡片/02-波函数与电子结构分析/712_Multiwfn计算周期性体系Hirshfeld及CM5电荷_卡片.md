---
id: 712
title: 使用Multiwfn对周期性体系计算Hirshfeld(-I)、CM5和MBIS原子电荷
url: http://sobereva.com/712
domain: 波函数与电子结构分析
topic: Multiwfn计算周期性体系Hirshfeld及CM5电荷
cards: 19
---

# Multiwfn计算周期性体系Hirshfeld及CM5电荷 — 知识卡片

## 1. 原子电荷的定义与基于模糊空间划分的方法

原子电荷即原子所带的净电荷，是描述原子带电状态的重要描述符。Multiwfn支持多种基于模糊式原子空间划分的原子电荷计算方法，这类方法中每个原子对应一个平滑的权重函数，权重函数与体系电子密度的乘积的全空间积分即为该原子的布居数，核电荷数减去布居数即为原子电荷。Multiwfn支持的此类方法包括Hirshfeld、Hirshfeld-I、MBIS、Becke，以及对Hirshfeld电荷做后校正得到的ADCH和CM5电荷。

---

## 2. Hirshfeld电荷的特点与文献出处

Hirshfeld电荷由Theor. Chim. Acta (Berl.), 44, 129 (1977)提出，是被广为使用的原子电荷，计算方式简单，物理意义清楚。其缺点是原子电荷数值整体严重偏小，对偶极矩、静电势重现性很差。对于大多数固体体系，Hirshfeld电荷在几种方法中数值通常最小。

---

## 3. Hirshfeld-I电荷的特点与文献出处

Hirshfeld-I电荷由JCP, 126, 144111 (2007)提出，是在Hirshfeld基础上的改进，通过迭代方式不断更新原子权重函数直到收敛。其原子电荷数值显著大于Hirshfeld，对静电势的重现性也有明显改进，但需要事先提供体系中各种元素的各个氧化态的原子径向密度信息，且计算耗时较高。CP2K程序自带的Hirshfeld-I电荷实现方式明显不是基于标准定义，结果不可靠，必须用Multiwfn来算。

---

## 4. CM5电荷的特点与文献出处

CM5电荷由JCTC, 8, 527 (2012)提出，属于对Hirshfeld电荷的后校正。CM5使得原子电荷变得更大、更符合化学直觉，对静电势的重现性也明显变得更好，大小通常介于Hirshfeld与Hirshfeld-I/MBIS之间。CM5最初用于分子体系，在晶体方面已有探索，且可用于uESE溶剂模型或结合OPLS-AA力场（乘以1.2后）做动力学模拟。

---

## 5. MBIS电荷的特点与文献出处

MBIS (Minimal Basis Iterative Stockholder) 电荷由JCTC, 12, 3894 (2016)提出，通过迭代方式优化原子空间直到收敛。MBIS不需要利用各个元素各个氧化态的原子径向密度信息，实现比Hirshfeld-I简单，但经常收敛较慢，目前Multiwfn里MBIS最高支持到Rn元素。

---

## 6. 原子电荷计算方法的选择建议

对于大多数固体体系，原子电荷大小的关系通常是MBIS和Hirshfeld-I最大、CM5介中、Hirshfeld最小。如果仅关注相对大小关系，计算便宜的Hirshfeld可以使用；如果关心定量数值，建议使用CM5、Hirshfeld-I或MBIS。如果某些原子电荷算出来明显不合理（例如O的电荷超过-2），则应弃用该方法。绝对不能把原子电荷与氧化态搞混。

---

## 7. CP2K用户计算原子电荷的输入文件选择

CP2K用户可以使用两种输入文件给Multiwfn计算原子电荷：一是CP2K产生的电子密度cube文件（推荐，可考虑k点，耗时低）；二是CP2K产生的记录波函数的molden文件（无法考虑k点，需扩胞）。使用molden文件时需输入格点间距，通常用0.2 Bohr；使用cube文件时格点间距由文件决定。输入文件应基于GPW计算和赝势基组，仅记录价电子密度。

---

## 8. CP2K旧版本cube文件的Bug修正

CP2K 2026.1以前的版本有bug，产生的cube文件里的原子有效电荷都为0。为此需手动修改cube文件第一行，写入各个元素的有效核电荷，例如“N 5 B 3 Ti 12”代表N、B、Ti的有效核电荷数分别为5、3、12。有效核电荷对应当前基组描述的原子电子数（赝势基组对应价电子数）。

---

## 9. VASP用户计算原子电荷的文件格式

VASP用户可以使用记录晶胞中价电子密度的CHGCAR文件作为Multiwfn的输入文件。为了让Multiwfn得知各类原子的有效核电荷数，CHGCAR文件的第一行需要以Nval为开头，后面依次写上各类元素的名字和有效核电荷，并以空格分隔，例如“Nval Na 1 Cl 7”。

---

## 10. VASP PAW计算的注意事项

VASP的PAW计算可能在原子核附近区域产生负值的电子密度。从2024-Dec-27更新的Multiwfn开始可以对这种情况给出正确的Hirshfeld、Hirshfeld-I、CM5电荷，但这种情况的电子密度原理上不兼容MBIS计算，因此算MBIS电荷时应当不用PAW。

---

## 11. 计算TiO2晶体电荷的CP2K输入生成示例

以TiO2金红石晶型为例，用Multiwfn载入cif文件后，依次输入命令生成CP2K输入文件：`cp2k`，回车使用默认文件名，`-3`（产生cube文件），`1`（电子密度），`8`（设置k点），`4,4,6`（k点设置），`0`（产生输入文件）。

---

## 12. CP2K cube文件有效核电荷修改示例

对于TiO2晶体使用PBE/DZVP-MOLOPT-SR-GTH基组，CP2K计算后得到的cube文件第一行需改为“Ti 12 O 6”。这代表Ti和O的有效核电荷分别为12和6，对应基组名DZVP-MOLOPT-SR-GTH-q12和DZVP-MOLOPT-SR-GTH-q6中q后面的值。

---

## 13. 计算Hirshfeld-I电荷的文件准备

计算Hirshfeld-I电荷需要用到各种元素各个价态的径向电子密度文件。应将Multiwfn自带的examples目录下的atmrad目录挪到当前目录下，以便Multiwfn计算时自动调用。

---

## 14. AlN晶体基于molden文件的计算流程

对于AlN晶体，可构造超胞并基于molden文件计算。在CP2K输入文件生成时选择`-11`进入几何操作界面，选19构造超胞（如4,4,3），然后选`-2`要求产生molden文件。计算得到的molden文件需在开头插入[Cell]定义晶胞和[Nval]定义价电子数（如Al 3, N 5）。

---

## 15. NaCl板吸附CO体系的片段电荷计算

计算NaCl板吸附CO的片段电荷时，在Multiwfn主功能7中先输入`-1`定义片段（如输入CO的原子序号109,110），然后选择相应的电荷计算方法（如Hirshfeld、CM5等）。结果中会显示Fragment charge（片段电荷）和Fragment population（片段布居数）。

---

## 16. 不同电荷计算方法对NaCl板吸附CO的结果对比

对于NaCl板吸附CO体系，Hirshfeld、CM5、Hirshfeld-I、MBIS和Mulliken方法计算的原子电荷在定量上有差异，但共性一致：CO整体带少量正电，电子从CO往NaCl板转移；C带正电，O带负电，且C的电荷绝对值大于O。

---

## 17. 不同电荷计算方法对典型离子晶体的数值表现

对于强离子性化合物如NaCl和MgF2，Hirshfeld-I和MBIS电荷数值通常在氧化态附近，甚至可能因方法定义缺陷轻微大于氧化态（除非使用大核赝势只描述最外层价电子）。其它原子电荷的大小关系通常为Mulliken > CM5 > Hirshfeld。

---

## 18. MBIS电荷的特殊情况示例

MBIS电荷并非总是较大。对于单层MoS2体系，在PBE/DZVP-MOLOPT-SR-GTH级别下，Mo的Hirshfeld-I电荷为1.987，而MBIS电荷为-0.059。对于此体系，MBIS电荷接近0，显得不符合常识，应谨慎使用。

---

## 19. 固体表面电荷计算方法推荐

对于计算固体表面或者多孔物质的原子电荷以用于基于力场的动力学模拟，最推荐CP2K计算REPEAT电荷。但REPEAT电荷需要在真空区定义拟合点，无法用于AlN、TiO2等致密固体，也不是普适性的原子电荷计算方法。
