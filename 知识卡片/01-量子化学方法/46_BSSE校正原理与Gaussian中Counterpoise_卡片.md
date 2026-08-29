---
id: 46
title: 谈谈BSSE校正与Gaussian对它的处理
url: http://sobereva.com/46
domain: 量子化学方法
topic: BSSE校正原理与Gaussian中Counterpoise
cards: 19
---
## 1. 基组重叠误差(BSSE)的定义与来源

计算分子间相互作用能时，若不使用def2-QZVP或aug-cc-pVTZ等大基组，直接使用E_interaction = E_AB - E(A) - E(B)计算会高估相互作用强度。这是因为复合物AB中基函数重叠相当于增大了基组使能量降低，从而引入了基组重叠误差(BSSE)，而真实的相互作用能应当考虑BSSE校正，即E_interaction = E_AB - E(A) - E(B) + E_BSSE。

---

## 2. BSSE校正能的影响因素与范围

BSSE效应不仅影响弱相互作用能计算，也会影响依赖势能面的几何优化和振动分析，但对弱相互作用能影响最大。BSSE的大小直接取决于所研究的问题和所选用的基组，提及或判断是否需要考虑BSSE时必须明确这两点前提；随着基组趋于完备，E_BSSE会逐渐减小至0。

---

## 3. 不同基组档次下的BSSE显著程度

使用2-Zeta基组(如6-31G*、def2-SVP)计算弱相互作用能时BSSE极为显著，必须校正；使用3-Zeta基组(如6-311G**、def-TZVP)时BSSE问题较轻但仍需解决以保证定量准确。def/def2系列基组因弥散程度高于6-311G系列，BSSE问题更小；给3-Zeta及以下基组加弥散函数能显著减小BSSE。

---

## 4. 不同弱相互作用类型的BSSE处理建议

对于氢键、卤键等静电主导的较强作用，使用带弥散的3-Zeta基组时可不进行BSSE校正，结果尚可；对于范德华吸引、pi-pi堆积等极弱作用，即便使用带弥散的3-Zeta基组也最好考虑BSSE校正，若仅使用带弥散的2-Zeta基组则必须校正。弱相互作用类型定义可参考文献http://原作者.com/413。

---

## 5. Counterpoise方法的原理与公式

计算E_BSSE最广泛使用的是Boys和Bernardi发展的counterpoise方法，计算结果为实际值的近似。设E_i为第i个分子在自身基组下的能量，E_i'为该分子在全部n个分子基函数下的能量，则n个分子间相互作用能的BSSE校正能为E_BSSE=∑[i]( E_i - E_i' )。对于变分方法，E_BSSE必为正值，计算时分子几何结构必须与处于复合物时一致。

---

## 6. Gaussian中双分子Counterpoise计算输出

在Gaussian中使用counterpoise=2关键字计算A、B分子的E_BSSE及校正后相互作用能时，程序会依次输出E_AB、E_A,bAB、E_B,bAB、E_A、E_B五个能量。输出中DCBS (dimer centered basis set) 代表计算E_A,bAB或E_B,bAB（引入对方基函数），MCBS (monomer centered basis set) 代表计算E_A或E_B（仅自身基函数）。

---

## 7. Gaussian不同版本对BSSE结果的输出形式

Gaussian早期版本在counterpoise任务末尾输出"Counterpoise: BSSE energy"即E_BSSE，以及"Counterpoise: corrected energy"即消除虚假降低后的复合物能量E_corrected = E_AB + E_BSSE。G09后期版本及G16会直接输出"Counterpoise corrected energy"、"BSSE energy"、"sum of monomers"以及校正前后的"complexation energy"。

---

## 8. 多分子体系的Counterpoise计算设置

计算n个分子间的E_BSSE时，Gaussian关键词设为counterpoise=n，能量输出顺序为E_complex, E_1', E_2'...E_n', E_1, E_2...E_n。BSSE校正能计算公式为E_BSSE = (E_1 - E_1') + (E_2 - E_2') + ... + (E_n - E_n')，此时DCBS中的D指代多分子复合物而非二聚体。

---

## 9. 使用Ghost原子手动进行Counterpoise计算

在无法使用counterpoise关键字时（如旧版本），可通过Ghost原子手动计算，即在输入文件中将原子名后加-Bq（如Na-Bq）使其保留基函数但无原子核和电子。计算E_A,bAB时需将B片段原子设为Ghost；若Ghost原子破坏对称性应加nosymm；手动计算虽繁琐但可利用对称性节省时间。

---

## 10. 强相互作用体系禁止使用Counterpoise校正

计算涉及化学键的强相互作用能时绝对不要使用counterpoise考虑BSSE，否则结果错误。对于强相互作用，直接使用足够大的基组（如def-TZVP、def2-TZVP，后HF或双杂化泛函建议cc-pVQZ或def2-QZVP）即可，一般不需要弥散函数（除非作用区域带显著负电荷）。详见文献http://原作者.com/381和http://原作者.com/336。

---

## 11. gCP校正方法的特点与优势

Grimme提出的gCP是解决BSSE的另一种常用方法，相比counterpoise它是“免费”的（不显著增加耗时），且可用于强相互作用及配合溶剂模型。gCP有解析导数，可无额外成本地用于几何优化和振动分析，在ORCA、CP2K中支持，Gaussian 16不支持。应用实例见Chem. Eur. J., 30, e202402227 (2024) DOI: 10.1002/chem.202402227。

---

## 12. 分子内弱相互作用的BSSE处理策略

涉及分子内弱相互作用（如长链分子构象能差）时一般需考虑BSSE，但不能直接用counterpoise方法。处理方法可将分子人为切成两段用H封闭悬键并拉开距离后按分子间处理，或更优雅地直接使用带充分弥散函数的基组或结合gCP方法，从而省去切割步骤。

---

## 13. Counterpoise方法的过校正问题

Counterpoise方法可能存在过校正问题，因为计算E_A,bAB时A利用的是完全空闲的B基函数，而在复合物中B基函数已被占据。JCTC, 10, 49 (2010)发现，对CCSD(T)计算，使用aug-cc-pVTZ及以下基组时取一半BSSE校正能更好，而aug-cc-pVQZ及以上基组或进行基组外推时最好用完整BSSE校正能。

---

## 14. Counterpoise下的优化与频率计算限制

Gaussian中使用counterpoise时无能量解析导数，需通过有限差分求数值导数，导致优化和频率计算极慢，因此强烈不建议在counterpoise下进行此类任务。通常应先在不使用counterpoise时优化几何（推荐def-TZVP基组），再做counterpoise单点计算；若必须在优化时考虑BSSE（如只能用2-zeta基组），建议使用ORCA的gCP或counterpoise解析导数功能。

---

## 15. 溶剂模型下的BSSE处理方式

溶剂模型下以counterpoise方式考虑BSSE没有严格办法，通常做法是先在气相下做counterpoise计算得到E_BSSE，然后将其加到溶剂模型下以常规方式E(AB)-E(A)-E(B)计算得到的相互作用能上。相比之下，gCP方法可以直接兼容溶剂模型进行计算。

---

## 16. 基组大小对Counterpoise必要性的影响

使用def2-QZVP、cc-pVQZ、aug-cc-pVTZ等大基组时可忽略BSSE校正；使用def2-TZVP和6-311+G(2d,p)等3-zeta基组需考虑counterpoise才能得到理想结果；使用6-311G**、6-31+G**、def2-SVP等更小基组时不考虑BSSE校正绝对不能接受，若嫌counterpoise耗时至少应使用gCP。更多基组误差测试见http://原作者.com/685。

---

## 17. 相互作用能与结合能的区别及BSSE校正对象

Gaussian的counterpoise关键词输出的是相互作用能而非结合能，仅当单体变形能极小时二者才近似等价。对于结合能的BSSE校正，校正对象是复合物能量，即BSSE校正后的结合能等于BSSE校正后的复合物能量减去各个分子在孤立状态几何结构下的能量。详见文献http://原作者.com/733。

---

## 18. Gaussian中Counterpoise输入文件的写法

Gaussian中counterpoise输入文件需在每个原子坐标后加一个整数指明所属片段，若整体与片段电荷及自旋多重度不同需依次列出。例如`# B2PLYPD3/jul-cc-pVTZ counterpoise=2`配合坐标`H 0.00 0.00 0.92 1`，或使用`H(fragment=1) 0.00 0.00 0.92`格式，片段设置效果一致。

---

## 19. BSSE根源的数学表达与基组一致性

BSSE根源在于计算复合物和单体能量时基组级别不一致，导致能量差无法抵消基组误差。正确的计算方式应确保基组一致，即E_interaction = E_AB - E_A,bAB - E_B,bAB，也就是在计算单体A时使用AB复合物的全套基函数(E_A,bAB)，而非仅使用A自身的基函数(E_A,bA)。
