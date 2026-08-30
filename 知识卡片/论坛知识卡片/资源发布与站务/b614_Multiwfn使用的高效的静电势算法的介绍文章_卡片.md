---
key: b614
title: Multiwfn使用的高效的静电势算法的介绍文章已于PCCP期刊发表！
url: http://sobereva.com/614
domain: 资源发布与站务
source: blog
year: 2021
cards: 10
---

# Multiwfn使用的高效的静电势算法的介绍文章已于PCCP期刊发表！ — 知识卡片

## 1. 静电势算法发表信息

深圳湾实验室张鋆与北京科音自然科学研究中心原作者共同撰写的文章《Efficient Evaluation of Electrostatic Potential with Computerized Optimized Code》发表于 *Phys. Chem. Chem. Phys.* 期刊 2021 年第 23 卷第 20323 页。文中介绍了一种高效的静电势计算算法，该算法已实现在波函数分析程序 Multiwfn 中，并作为当前版本计算静电势的默认代码。

---

## 2. 静电势的定义与应用

静电势是量子化学中一种重要的实空间函数，可用于解释和预测分子间静电相互作用、计算拟合静电势电荷用于分子模拟、预测亲核和亲电反应位点以及计算基于静电势定义的描述符以预测体系凝聚相性质。Multiwfn 程序支持丰富的静电势相关分析，相关资料与文献汇总在《静电势与平均局部离子化能相关资料合集》中。

---

## 3. Multiwfn 静电势算法演进

Multiwfn 早期的静电势计算代码实现简单但速度较慢，随后增加了调用 Gaussian 的 cubegen 程序进行计算的功能以降低耗时。自 Multiwfn 3.7 版起，程序实现了一种非常高效的静电势计算算法，该算法目前为默认使用，速度比最早的代码快几十倍，且在多数情况下优于知名商业量子化学程序自带的静电势计算工具。

---

## 4. 静电势计算速度测试对比

在计算多巴胺（Dopamine）和瑞德西韦（Remdesivir）体系的 RESP 原子电荷测试中，Multiwfn 的新静电势代码显著优于 ORCA 程序自带的 orca_vpot 工具及最早的旧版代码。测试数据表明，新代码在多数情况下的计算速度快于某知名商业量子化学程序自带的静电势计算工具。

---

## 5. 大体系静电势计算实例

针对从 MOF-5 晶体中截取的含 400 个原子（化学组成为 H120C144O104Zn32）的重复单元，使用 xtb 程序在 GFN2-xTB 理论下计算波函数并生成 molden 文件。利用 Multiwfn 计算表面静电势，体系包含 4840 个 Gaussian 函数和 259262 个表面顶点，在 36 核服务器上耗时约半小时完成，表明该算法可用于处理较大体系。

---

## 6. 静电势计算的并行效率

对 ATP 分子在 B3LYP/6-311+G(2d,p) 理论下产生的波函数进行 RESP 电荷计算测试显示，Multiwfn 的静电势计算具备理想的并行效率。随着调用的 CPU 核数增加，相对于单线程运行的速度提升显著，能够充分利用多核 CPU 的运算能力。

---

## 7. 内部代码相对于调用 cubegen 的优势

使用 Multiwfn 内部静电势计算代码相较于调用 Gaussian 的 cubegen 程序具有以下优势：无需购买 Gaussian 程序；支持 fch、molden、mwfn、wfn、wfx、gms 等多种输入格式；支持调用 cubegen 不具备的功能（如主功能 2 的静电势拓扑分析）以及特定的快速绘图技巧。

---

## 8. 调用 cubegen 的适用场景

在使用主功能 5 计算均匀分布的静电势格点数据时，调用 cubegen 的耗时通常明显低于使用 Multiwfn 内部代码。这是因为 cubegen 针对批量计算格点数据进行了特殊优化，通过共享中间数据避免重复计算从而节约时间，因此在中大体系格点数据计算中若有条件仍建议调用 cubegen。

---

## 9. 算法未来的改进方向

现有的静电势算法及代码仍有进一步改进空间，未来可能通过以下方式提升速度：更充分地利用 CPU 的 SIMD 指令集；利用积分屏蔽降低巨大体系的计算耗时；针对收缩型基函数优化代码（当前代码基于 primitive 函数计算，这使得不含基函数信息的 wfn、wfx 文件也可用于计算）。

---

## 10. 文章引用建议

若使用 Multiwfn 内部代码（即默认情况）进行静电势相关分析并发表文章，应在 Computational Details 段落中对文章 *Phys. Chem. Chem. Phys.*, **23**, 20323 (2021) 进行提及和引用。引用示例可写为：The electrostatic potential involved in the analyses was evaluated by Multiwfn based on the highly effective algorithm proposed in Ref.[PCCP文章]。
