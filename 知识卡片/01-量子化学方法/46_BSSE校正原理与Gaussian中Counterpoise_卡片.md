---
id: 46
title: 谈谈BSSE校正与Gaussian对它的处理
url: http://sobereva.com/46
domain: 量子化学方法
topic: BSSE校正原理与Gaussian中Counterpoise
cards: 1
---

# BSSE校正原理与Gaussian中Counterpoise — 知识卡片

## 1. 基组重叠误差(BSSE)的定义与来源

计算两个分子A、B间的相互作用能时，除非基组很大如def2-QZVP这样的4-zeta档次，或者aug-cc-pVTZ这样带非常充分弥散函数的3-zeta档次基组，否则不宜简单地通过E_interaction = E_AB - E(A) - E(B)来计算。E_AB能量相对于E(A) + E(B)的降低一方面来自真实的A、B分子间的相互作用能，另一方面来自于A、B分子的基函数在复合物体系中重叠，相当于增大了复合物的基组而使E(AB)能量降低，这部分贡献会高估相互作用强度，称为基组重叠误差(BSSE)。BSSE问题的大小直接取决于计算的问题和用的基组。

## BSSE校正公式与必要性
为了解决BSSE问题，严格的双分子的相互作用能应该表述为E_interaction = E_AB - E(A) - E(B) + E_BSSE，这里E_BSSE称为BSSE校正能。当基组不很大而相互作用本身又较弱时，E_BSSE所占E_interaction的比例往往不小，不考虑BSSE校正的话甚至可能结果定性不合理。由于BSSE问题会影响势能面，因此BSSE效应不仅影响弱相互作用能，也会影响几何优化、振动分析等任务的结果，只不过一般只是对计算弱相互作用能进行校正。

## 不同基组下的BSSE显著性
用2-Zeta基组如6-31G*、def2-SVP算弱相互作用能时BSSE问题是极为显著的，必须解决。3-zeta基组如6-311G**、def-TZVP算弱相互作用的BSSE问题比2-Zeta基组轻，但依然必须解决，否则结果定量不准。def/def2系列基组比6-311G系列的BSSE问题更小。对于4-Zeta基组，BSSE问题通常很不显著，故一般可以不考虑。给3-zeta及以下档次的基组加上弥散函数能显著减小BSSE问题。

## 不同类型弱相互作用的BSSE处理策略
对于氢键、卤键等静电主导的强度不很弱的作用，用了带弥散的3-Zeta级别的基组后，不做BSSE校正算出来的相互作用能也还行。而范德华吸引、pi-pi堆积作用能一般强度很弱，即便用了带弥散函数的3-Zeta基组计算它们，BSSE问题往往仍然不可充分忽略，故最好考虑BSSE校正，而若是仅仅用带弥散的2-Zeta基组的话则更必须考虑BSSE校正。

## Counterpoise方法计算BSSE的原理
目前计算E_BSSE最广泛的方法是Boys和Bernardi发展的counterpoise方法。设E_i为第i个分子在自身基组下的能量，E_i'为第i个分子在全部n个分子的基函数都出现下的能量，则n个分子间的相互作用能的E_BSSE=∑[i]( E_i - E_i' )。对于变分的方法，E_i'比E_i更负，故E_BSSE必为正值。注意计算E_i与E_i'时的分子几何结构必须与i处在复合物时的一致。

## Gaussian中双分子Counterpoise计算的输出
若要计算A、B两个分子的E_BSSE，在Gaussian中使用counterpoise=2关键字，会自动依次计算5个体系，依次输出以下能量：E_AB（A、B基函数下AB复合物的能量）、E_A,bAB（A、B基函数下A的能量）、E_B,bAB（A、B基函数下B的能量）、E_A（A基组下A的能量）、E_B（B基组下B的能量）。计算过程中输出"doing DCBS calculation"代表计算E_i'，输出"doing MCBS calculation"代表计算E_i。

## 不同Gaussian版本的BSSE输出结果
G09早期版本或更早版本任务最后会输出"Counterpoise: BSSE energy"即E_BSSE，即(E_A - E_A,bAB) + (E_B - E_B,bAB)，还会输出"Counterpoise: corrected energy"，这是消除了虚假能量降低后的AB复合物能量。Gaussian09后期版本或G16的输出更直接：Counterpoise corrected energy（校正后的整体能量）、BSSE energy（BSSE校正能）、complexation energy (raw)（校正前的相互作用能）、complexation energy (corrected)（校正后的相互作用能）。

## 多分子体系的Counterpoise计算
若计算n个分子间的E_BSSE，则关键词为counterpoise=n，能量按如下顺序输出：E_complex, E_1', E_2'...E_n', E_1, E_2...E_n。E_BSSE = (E_1 - E_1') + (E_2 - E_2') + ... + (E_n - E_n')。计算过程中DCBS中的D的含义指多分子复合物而非具体指Dimer。

## 手动进行Counterpoise计算的方法
如果有特殊原因需要手动进行counterpoise计算，可以通过设定Ghost原子来实现：把某个原子名后面加上-Bq就说明它是Ghost原子，即这个原子照常有它原本的基函数，但是没有原子核和电子。要计算E_A,bAB，只需要在复合物的输入文件中把B片段的所有原子后面都加上-Bq即可。注意Bq原子若破坏了原有对称性，最好加上nosymm。手动做counterpoise的每个步骤比直接用counterpoise关键词可能更省时，因为可以利用对称性。

## 强相互作用能计算中禁止使用Counterpoise
计算强相互作用能，即牵扯到化学键作用时，绝对不要用counterpoise考虑BSSE问题，否则自取其辱。计算强相互作用能的时候直接用一个足够大的基组就完了，通常至少def-TZVP，用def2-TZVP更好，如果是后HF方法或双杂化泛函并想得到尽可能好的结果则建议cc-pVQZ或def2-QZVP。两个片段间如果既有显著的弱相互作用也有化学键作用，也属于这种情况。

## gCP校正方法的特点与应用
Grimme提出的gCP是如今挺常用的解决BSSE的方法。counterpoise任务的耗时是复合物单点耗时的三倍多，而gCP校正是“免费”的，而且涉及到强相互作用时也能用。此外，gCP校正有解析导数，因此带着gCP做几何优化、振动分析也不会带来额外的成本。gCP可以结合不带弥散的一些极小基、2-zeta和3-zeta基组使用，在ORCA、CP2K里支持，Gaussian 16不支持。

## 分子内弱相互作用的BSSE处理
涉及分子内弱相互作用时一般也要考虑BSSE。由于两个片段属于同一个分子，不能直接用counterpoise方法处理。非要用counterpoise的话，可以将分子人为地切成两段，悬键用比如H来封闭，然后适当调整两个片段。而更优雅的做法是直接在计算时令基组带充分的弥散函数，或者不带弥散函数但是用gCP，这就省得切割片段了。

## Counterpoise方法可能存在的过校正问题
Counterpoise有时有过校正问题，因为计算E_A,bAB时A感受到的是完全“空闲”的B的基函数，能被A充分利用；而在复合物中A感受到的B的基函数已经有一定占据，不能被A充分利用。JCTC, 10, 49 (2010)发现，对于CCSD(T)计算相互作用能，使用aug-cc-pVTZ及以下基组时，BSSE校正能取一半比取完整的BSSE校正能更好；而对于aug-cc-pVQZ及以上级别的基组，或者进行基组外推，最好用完整的BSSE校正能。

## Gaussian中Counterpoise计算优化的局限性
Gaussian中使用counterpoise时没有能量的解析导数，只能通过有限差分以数值方式获得导数，因此优化和频率计算极慢，强烈不建议在counterpoise下进行优化和计算频率。BSSE问题对于优化出的几何结构的影响一般很小，因此通常的弱相互作用计算，都应当在不使用counterpoise的情况下先做优化，然后再带着counterpoise计算相互作用能。若想在优化时明确考虑BSSE校正，应该用gCP方法。

## 溶剂模型下的BSSE校正策略
溶剂模型下以counterpoise方式考虑BSSE问题没有严格的办法，一般做法是在气相下做counterpoise计算得到E_BSSE，然后加到溶剂模型下以常规方式E(AB)-E(A)-E(B)计算的相互作用能上。gCP可以直接兼容溶剂模型。

## 不同基组下是否考虑BSSE的建议
用def2-QZVP、cc-pVQZ、aug-cc-pVTZ及其月份基组变体时可以不考虑BSSE校正。对于3-zeta档次基组，def2-TZVP和6-311+G(2d,p)算弱相互作用能能及格，但考虑counterpoise后才能足够理想。对于明显更小的基组，如6-311G**、6-31+G**、def2-SVP等，算相互作用能如今不考虑BSSE校正能绝对不能接受，若嫌counterpoise明显增加耗时至少也应当用免费的gCP。

## 相互作用能与结合能的区别及BSSE校正对象
counterpoise关键词给出的complexation energy是相互作用能而不是结合能，仅当单体的变形能非常小的时候二者才近似等价。对于计算结合能的BSSE校正来说，counterpoise校正的对象是复合物能量，也就是说BSSE校正后的结合能等于BSSE校正后的复合物能量减去各个分子在孤立状态几何结构下的能量。

## Gaussian中Counterpoise输入文件的写法
Gaussian中做counterpoise计算时，每个原子最后需要有一个整数说明这个原子属于第几个片段。若整体与片段的电荷和自旋多重度不一样，应该按顺序写：整体电荷，整体自旋多重度，片段1电荷，片段1自旋多重度，片段2电荷，片段2自旋多重度。坐标部分也可以用"fragment="关键字来设置片段。

## BSSE产生的根源分析
BSSE的根源在于计算复合物和计算单体时不在相同的基组级别下。A单体中靠近B单体的原子的基组完备性在复合物状态下高（因为B的基函数侵入此原子空间），而在A单体单独计算时低，这就导致能量在求差值时基组误差无法被抵消。正确的写法是E_interaction = E_AB - E_A,bAB - E_B,bAB，即计算复合物和单体的能量时都在AB基组下（文中E_AB和E_AB,bAB在符号上是等价的）。
