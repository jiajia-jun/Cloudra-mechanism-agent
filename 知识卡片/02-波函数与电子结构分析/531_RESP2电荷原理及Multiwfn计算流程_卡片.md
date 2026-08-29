---
id: 531
title: RESP2原子电荷的思想以及在Multiwfn中的计算
domain: 波函数与电子结构分析
topic: RESP2电荷原理及Multiwfn计算流程
cards: 12
---

## 1. RESP电荷及其对计算级别的依赖性
RESP是几乎最适合用于分子动力学模拟的原子电荷计算方法，其具体数值明显依赖于计算电子波函数用的量子化学方法和基组，以及对溶剂效应的考虑。相关详细介绍可参考《RESP拟合静电势电荷的原理以及在Multiwfn中的计算》。目前已有使用Multiwfn计算RESP2电荷的文章发表，如Nature Energy (2023) DOI: 10.1038/s41560-023-01275-y、Chem. Phys. Lett., 754, 137707 (2020)。使用该方法需要在文章中恰当引用Multiwfn，引用方式可参考《Multiwfn FAQ》。

---

## 2. 溶剂介电常数对溶质极化的影响
在溶剂环境下，溶质的电荷分布会被溶剂环境所极化，极化程度随溶剂介电常数的增大而增大（非线性关系）。以甲醛在B3LYP/aug-cc-pVTZ/IEFPCM下的计算为例，水（常温介电常数78.3）中的极化程度显著高于真空。对于固定电荷力场，原子电荷分布应当能等效地体现出实际环境产生的极化效果，例如SPC/E水模型偶极矩2.35 Debye明显高于气相实验值1.85 Debye。

---

## 3. HF/6-31G*计算RESP电荷的缺陷与历史原因
HF/6-31G*无法考虑电子库仑相关，高估了体系极性，这误差恰巧能一定程度表现凝聚相中溶剂对溶质的极化作用，因此被AMBER力场沿用至今。但由于数据点分散、高估程度不一，且无法体现不同溶剂的极化差异，这种“以错误的方式得到凑合能用的结果”的做法应当被摒弃。AMBER力场开发者因参数与电荷间的耦合，不敢轻易更换计算级别。

---

## 4. DFT结合隐式溶剂模型计算偶极矩的优势
J. Chem. Inf. Model., 60, 249 (2020) 对比显示，HF/6-31G*高估体系极性且数据分散，而B3LYP结合大基组及隐式溶剂模型（即使低介电常数如苯）计算出的极性也比HF真空下更高，且数据分布集中。使用DFT结合隐式溶剂模型在理论上非常理想，但需注意避免过度极化，AMBER03力场特意设置了介电常数为4。

---

## 5. IPolQ与IPolQ-mod电荷的定义
J. Phys. Chem. B, 117, 2328 (2013) 提出的IPolQ电荷是将气相和显式水下算的RESP电荷取平均。J Comput Aided Mol Des, 28, 277 (2014) 提出的IPolQ-mod将其简化为气相和隐式水下RESP电荷的平均值，使用MP2/aug-cc-pVDZ级别。IPolQ-mod电荷计算水合自由能的结果与HF/6-31G* RESP电荷差不多，但做法严格合理得多。

---

## 6. RESP2电荷的定义与公式
RESP2电荷由2019年的ChemRxiv文章（后发表于Communications Chemistry, 3, 44 (2020)）提出，定义公式为 q_RESP2 = (1-δ)*q_gas + δ*q_aqu，其中q_gas和q_aqu分别是气相和水模型下计算的RESP电荷，δ是可调参数。例如δ=0.5时称为RESP2(0.5)，实际上相当于IPolQ-mod电荷。RESP2文章使用的PW6B95/aug-cc-pV(D+d)Z级别并非必须，推荐使用B3LYP/def2-TZVP。

---

## 7. RESP2电荷参数δ的选择
RESP2文章基于SMIRNOFF力场测试发现，不重新优化LJ参数时，RESP2(0.6)改善介电常数，加大δ改善介电常数和水合自由能，减小δ改善密度。重新优化LJ参数时，δ在0.5~0.7时整体误差最低，RESP2(0.6)比RESP更优。文中整体误差最小δ为0.6，与IPolQ的0.5接近，因此δ=0.5可视为普适参数。

---

## 8. 针对AMBER/GAFF力场推荐的RESP2(0.5)计算流程
推荐使用RESP2(0.5)电荷，公式为 q_RESP2(0.5) = 0.5*q_gas + 0.5*q_solv。几何优化使用B3LYP-D3(BJ)/def-TZVP（或6-311G**）在真空下进行（带电体系需在溶剂下优化）。单点计算使用B3LYP-D3(BJ)/def2-TZVP（阴离子用ma-TZVP）分别计算气相和PCM模型（实际溶剂）下的波函数以生成q_gas和q_solv。对于GAFF力场，RESP2(0.5)电荷兼容性良好且表现优于HF/6-31G*。

---

## 9. 使用Gaussian和Multiwfn手动计算RESP2电荷的步骤
首先用Gaussian进行结构优化（B3LYP-D3(BJ)/def-TZVP），然后基于优化结构分别进行气相和溶剂（如IEFPCM乙醇）下的单点计算，得到SP_gas.chk和SP_solv.chk并转为fch文件。启动Multiwfn分别加载这两个文件，依次选择 7 -> 18 -> 1 计算RESP电荷。最后将两组电荷数据取平均（如使用Excel）即得到RESP2(0.5)电荷。

---

## 10. 使用Multiwfn脚本calcRESP.sh批量计算RESP2电荷
Linux脚本calcRESP.sh位于Multiwfn文件包的examples\RESP2目录下，使用示例包括：./calcRESP.sh SP_gas.fch（计算RESP）、./calcRESP.sh SP_gas.fch SP_solv.fch（计算RESP2(0.5)）、./calcRESP.sh SP_gas.fch SP_solv.fch 0.7（计算RESP2(0.7)）。运行后RESP电荷输出为同名.chg文件，RESP2电荷输出为RESP2.chg文件。输入文件支持fch、molden或直接使用chk（需配置settings.ini）。

---

## 11. 使用RESP2.sh脚本一键调用Gaussian和Multiwfn计算
脚本RESP2.sh位于examples\RESP\目录下，只需提供结构文件即可自动调用Gaussian和Multiwfn完成RESP2(0.5)计算。用法示例：./RESP2.sh H2O.pdb（中性单重态水分子）、./RESP2.sh foo.xyz 0 3（中性三重态）、./RESP2.sh nozomi.mol -1 1 ethanol（阴离子单重态，乙醇溶剂）。默认计算级别为B3LYP-D3(BJ)/def2-SVP优化和B3LYP-D3(BJ)/def2-TZVP单点，调用Gaussian 09。

---

## 12. 基于已有结构或使用ORCA计算RESP2电荷的脚本选项
若输入结构文件已足够好，可使用examples\RESP\目录下的RESP2_noopt.sh跳过优化步骤，用法与RESP2.sh完全相同。如果没有购买Gaussian，可以使用免费的ORCA量子化学程序结合Multiwfn计算RESP2电荷，详见《ORCA结合Multiwfn计算RESP、RESP2和1.2*CM5原子电荷的懒人脚本》。
