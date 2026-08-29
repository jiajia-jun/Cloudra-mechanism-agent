---
id: 623
title: revTPSS泛函结合pcSseg-1基组是计算NMR很好的选择
url: http://sobereva.com/623
domain: 量子化学方法
topic: revTPSS泛函结合pcSseg-1基组计算NMR
cards: 15
---
## 1. revTPSS泛函计算NMR的优势

revTPSS泛函（meta-GGA档次）计算氢的化学位移表现很好，不输于依赖拟合参数的标度法，且优于双杂化泛函、MP2以及B3LYP等普通泛函。虽然双杂化泛函和MP2在以往文献的高精度理论测试中表现较好，但在以实验数据为参照的实用测试中，revTPSS因整体误差小、计算省事且普适，更具有实际意义。
- 出处: JCTC, https://doi.org/10.1021/acs.jctc.1c00604

---

## 2. 推荐的氢谱计算级别

revTPSS结合pcSseg-1基组计算氢的化学位移精度出色且计算便宜，强烈推荐使用。pcSseg-1大小约等于6-31G**，该级别耗时与标度法基本一致且精度互有胜负，若不想使用经验性强的标度法，revTPSS/pcSseg-1是首选。
- 推荐操作: revTPSS/pcSseg-1结合IEFPCM溶剂模型（氯仿）

---

## 3. 碳谱计算方法选择

revTPSS/pcSseg-1计算碳的化学位移精度不如氢谱，但整体优于其他普通泛函结合def2-TZVPP的结果，略逊于标度法。算碳的NMR优先建议使用标度法，若必须使用标准方式计算，则推荐使用revTPSS/pcSseg-1。

---

## 4. 基组对revTPSS计算的影响

revTPSS/pcSseg-1表现好的部分原因是泛函与基组误差抵消得当，且这一现象具有普遍性。revTPSS结合def2-SVP结果较差，结合def2-TZVPP虽强于def2-SVP但比pcSseg-1无优势且昂贵，不值得考虑；revTPSS本身算NMR表现不错，并非单纯依赖误差抵消。
- 出处: JCTC, https://doi.org/10.1021/acs.jctc.1c00604 图3

---

## 5. 双杂化泛函的计算建议

双杂化泛函DSD-PBEP86在真空下计算NMR精度优于在CPCM氯仿环境下，结合def2-TZVPP时虽优于B97-2、B3LYP、MP2，但相比revTPSS/pcSseg-1无明显优势。仅当标度法和revTPSS/pcSseg-1表现不佳时，才值得考虑在真空下使用DSD-PBEP86/def2-TZVPP。

---

## 6. MP2计算NMR的效率与替代方案

Gaussian在MP2下做NMR计算非常昂贵，而ORCA利用RI近似做MP2或双杂化泛函的NMR计算则快得多。由于revTPSS/pcSseg-1和标度法表现出色，且ORCA支持双杂化泛函算NMR，导致MP2在NMR计算上已无实用性。

---

## 7. KT系列泛函的表现

KT2结合def2-TZVPP算氢的精度和revTPSS/pcSseg-1基本持平，但算碳的精度远不如revTPSS/pcSseg-1。考虑到KT系列泛函（如KT1、KT2）在Gaussian中不支持，ORCA也需通过libxc界面使用，有了revTPSS/pcSseg-1就没必要考虑KT系列泛函了。

---

## 8. 几何结构优化的级别

为了计算NMR而优化几何结构时，使用B3LYP/6-31G*在真空下优化就完全足够了。用更贵的def2-TZVPP优化不会带来明显改进，不同基组优化对最终NMR结果影响不大且无规律，直接用已有结构计算NMR即可。
- 参考文章: 《谈谈量子化学研究中什么时候用B3LYP泛函优化几何结构是适当的》

---

## 9. 振动校正与误差抵消

精确计算与实验对照的NMR化学位移时振动校正不可忽略，但该资料未考虑该因素。该资料关于精度的结论是忽略了振动校正等误差后的结果，实际反映了各种误差相互抵消后的表现，这对于通常不考虑振动校正的实际应用研究具有直接指导意义。

## 10. revTPSS/pcSseg-1在Multiwfn中的应用

B3LYP/6-31G*真空优化结构、revTPSS/pcSseg-1在IEFPCM氯仿下计算NMR这一组合非常有价值，Multiwfn（从2021-Oct-23更新版本起）已内置该级别的TMS磁屏蔽值。使用时在选项7中选择Set reference shielding value to determine chemical shift，可直接将磁屏蔽值转化为化学位移作图。
- 参考文章: 《使用Multiwfn绘制NMR谱》

---

## 11. Gaussian中revTPSS与pcSseg基组的使用

revTPSS在Gaussian中要写成revTPSSrevTPSS。pcSseg基组在Gaussian 16中未内置，需从BSE基组数据库拷贝定义使用；在ORCA中pcSseg基组是内置的，可直接使用。
- 参考文章: 《详解Gaussian中混合基组、自定义基组和赝势基组的输入》、《在线基组和赝势数据库一览》

---

## 12. ORCA中双杂化泛函的计算设置

ORCA中用DSD-PBEP86在CPCM氯仿下做NMR计算的关键词为：! DSD-PBEP86 def2-TZVPP def2-TZVPP/C tightSCF NMR miniprint nopop defgrid3 CPCM(chloroform)。双杂化算NMR必须使用库仑拟合辅助基组（如def2-TZVPP/C），且建议使用defgrid3提高积分格点质量。

---

## 13. ORCA中pcSseg基组与辅助基组的搭配

若使用pcSseg系列基组做双杂化泛函NMR计算，没有标配辅助基组可用，可用cc-pwCVnZ/C系列，如pcSseg-3搭配cc-pwCVQZ/C。也可以使用autoaux让ORCA自动构建，但在质量相同时比cc-pwCVQZ/C大很多。
- 出处: JCTC, 14, 4756 (2018) 图1

---

## 14. ORCA中KT系列泛函的调用方式

ORCA自身不支持KT系列泛函，需通过libxc接口使用。例如使用KT2算NMR的关键词为：! def2-TZVPP tightSCF NMR miniprint nopop defgrid3，配合 %method method dft functional gga_xc_kt2 end。泛函名可通过orca -libxcfunctionals命令查询。

---

## 15. ORCA中libxc接口的性能影响

对于ORCA自身支持的泛函，使用libxc接口与否对NMR计算结果影响可忽略不计，但使用libxc接口计算耗时会更高。
