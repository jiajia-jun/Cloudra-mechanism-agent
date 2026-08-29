---
id: 614
title: Multiwfn使用的高效的静电势算法的介绍文章已于PCCP期刊发表！
domain: 波函数与电子结构分析
topic: Multiwfn高效静电势算法发表与性能测试
cards: 10
---

## 1. Multiwfn高效静电势算法的PCCP发表文献
研究人员在《Phys. Chem. Chem. Phys.》期刊 23, 20323 (2021) 发表了题为 Efficient Evaluation of Electrostatic Potential with Computerized Optimized Code 的文章，DOI为 10.1039/d1cp02805g。该文章介绍了一种非常高效的静电势计算算法，已实现在波函数分析程序中，并作为当前版本计算静电势时的默认代码。

---

## 2. 静电势在量子化学中的应用
静电势是量子化学中的一种极为重要的实空间函数，可用于解释和预测分子间静电相互作用、计算拟合静电势电荷用于分子模拟、预测亲核和亲电反应位点、计算基于静电势定义的描述符预测体系凝聚相性质。Multiwfn程序支持非常丰富的静电势相关的分析，相关资料汇总在《静电势与平均局部离子化能相关资料合集》帖子里。

---

## 3. Multiwfn静电势计算代码的演变
Multiwfn最早的静电势计算代码写于2011年，速度较慢；后来程序支持调用Gaussian的cubegen程序使耗时大幅下降。最终在Multiwfn 3.7版中，研究人员合作实现了一种非常高效的静电势计算算法，该算法如今是当前版本计算静电势时默认使用的，并正式发表于 *Phys. Chem. Chem. Phys.* 期刊。

---

## 4. Multiwfn新静电势代码的速度测试结果
测试显示Multiwfn的新静电势代码比最早的代码快了几十倍，也显著胜于ORCA程序自带的orca_vpot工具，在多数情况下比知名的商业量子化学程序自带的快速静电势计算工具速度还要快。测试数据涉及多巴胺和瑞德西韦体系在不同基组下的RESP电荷计算耗时。

---

## 5. Multiwfn新代码处理大体系的能力
从MOF-5晶体截取的重复单元（化学组成H120C144O104Zn32，共400个原子）被用于测试大体系计算能力。该体系Gaussian函数数目多达4840个，被计算静电势的表面顶点数多达259262个，在36核服务器下仅需半小时即可完成计算，说明Multiwfn的静电势分析结合VMD绘图已可用于相当大的体系。

---

## 6. Multiwfn静电势计算的并行效率
对ATP分子在B3LYP/6-311+G(2d,p)下产生的波函数计算RESP电荷的测试表明，Multiwfn静电势计算的并行效率很理想。随着调用的CPU核数增多，相对于单线程运行的速度提升也很理想，因此可以充分利用多核CPU的运算能力。

---

## 7. Multiwfn内部代码优于cubegen的方面
Multiwfn内部的静电势代码相比调用Gaussian的cubegen具有以下优势：(1)无需购买付费程序；(2)输入格式普适，支持fch、molden、mwfn、wfn、wfx、gms等任意Multiwfn支持的格式；(3)支持更多涉及静电势的功能，如对静电势做拓扑分析，以及结合特定巨幅降低绘图耗时的技巧。

---

## 8. cubegen计算格点数据的特殊优势
目前只有一种情况使得调用cubegen算静电势的耗时比Multiwfn自己的代码明显更低，即利用主功能5计算均匀分布的静电势格点数据时。cubegen对此做了特殊考虑，通过批量计算和共享中间数据避免重复计算，从而大幅节约时间，因此算中、大体系静电势格点数据时若有条件仍建议调用cubegen。

---

## 9. Multiwfn静电势算法的未来改进方向
当前的静电势算法及代码仍有进一步改进的余地，未来可能提升速度的方向包括：(1)更充分地利用CPU的SIMD指令集；(2)充分利用积分屏蔽来降低巨大体系的耗时；(3)针对收缩型基函数优化代码，当前代码基于primitive函数计算的好处是支持wfn、wfx等不含基函数信息的输入文件。

---

## 10. Multiwfn静电势分析的文献引用要求
如果使用Multiwfn程序内部代码（即默认情况）进行静电势相关分析，请在发表的文章中对 *Phys. Chem. Chem. Phys.*, 23, 20323 (2021) 文章进行提及和引用。建议在Computational Details段落写明：The electrostatic potential involved in the analyses was evaluated by Multiwfn based on the highly effective algorithm proposed in Ref.[PCCP文章]。
