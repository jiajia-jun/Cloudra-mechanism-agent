---
id: 623
title: revTPSS泛函结合pcSseg-1基组是计算NMR很好的选择
url: http://sobereva.com/623
domain: 量子化学方法
topic: revTPSS泛函结合pcSseg-1基组计算NMR
cards: 2
---

# revTPSS泛函结合pcSseg-1基组计算NMR — 知识卡片

## 1. JCTC期刊关于revTPSS计算氢化学位移的研究

JCTC期刊文章[https://doi.org/10.1021/acs.jctc.1c00604](https://doi.org/10.1021/acs.jctc.1c00604)测试了一批泛函计算氢化学位移的精度，参照标准是一批有机分子在氯仿中的实验化学位移。文章声称revTPSS泛函（meta-GGA档次）表现很好，不输于标度法，优于双杂化泛函和MP2。该研究直接以实验数据为参照，对于关注应用性计算的研究者具有实际意义，因为它反映了在不考虑振动校正和显式溶剂等复杂因素下的整体误差。

## 推荐的氢谱NMR计算级别
计算有机体系的氢NMR化学位移时，强烈推荐使用revTPSS/pcSseg-1级别，并在IEFPCM溶剂模型下表现氯仿环境。pcSseg-1基组大小约等于6-31G**，专门为NMR计算设计，性价比高。该级别耗时与标度法基本相同，精度互有胜负，且经验性低、不依赖于针对元素拟合的参数，具有更好的普适性。如果标度法结果与实验值误差较大，可以尝试使用该级别进行相互检验。

## 推荐的碳谱NMR计算级别
计算有机体系的碳NMR化学位移时，revTPSS/pcSseg-1级别的精度虽然不如算氢时那么准，但仍比其它普通泛函结合较贵的def2-TZVPP基组更好。不过该级别整体略逊于标度法，因此在算碳谱时优先建议使用标度法；如果必须使用标准方式计算，则推荐使用revTPSS/pcSseg-1。

## revTPSS结合不同基组的表现
revTPSS结合pcSseg-1基组计算氢谱表现最好，结合更贵的pcSseg-2基组结果反而变差，这体现了泛函与基组误差抵消的因素。revTPSS结合def2-SVP基组表现远不如pcSseg-1，因为def2-SVP太小且非专门基组；结合def2-TZVPP基组时表现虽强于def2-SVP，但比pcSseg-1无优势且昂贵得多。revTPSS本身计算NMR性能不错，不必须依赖于与基组误差的抵消。

## 几何优化级别对NMR计算结果的影响
使用revTPSS/pcSseg-1计算NMR时，几何结构只需用B3LYP/6-31G*在真空下优化即可。结合不同基组（6-31G*、def2-SVP、def2-TZVPP）优化结构对最终NMR结果影响不大且无规律，使用昂贵的def2-TZVPP优化不会带来改进。如果已在其它恰当级别下优化了结构，可直接用来算NMR，无需为NMR计算特意重新优化。

## 双杂化泛函在NMR计算中的表现
双杂化泛函DSD-PBEP86结合def2-TZVPP基组在真空下计算氢谱的表现虽比B97-2、B3LYP、MP2整体更好，但相比revTPSS/pcSseg-1并无优势。使用ORCA计算时，该泛函在CPCM表现的氯仿环境下精度不如真空下，因此不建议在计算时带溶剂模型。除非标度法和revTPSS/pcSseg-1表现均不佳，否则不值得花费更高计算代价使用双杂化泛函。

## MP2计算NMR的效率与实用性
Gaussian在MP2下做NMR计算非常昂贵，主流36核服务器在MP2/def2-TZVPP下算吡啶的NMR需花六分钟。相比之下，ORCA利用RI近似做MP2或双杂化泛函的NMR计算快得多，在i7-10870H CPU上用DSD-PBEP86/def2-TZVPP算吡啶仅需一分半钟。由于revTPSS/pcSseg-1和标度法表现出色，MP2在NMR计算上已无实用性。

## KT系列泛函的表现与局限性
KT系列泛函是专门考虑算磁属性的泛函，测试表明KT2结合def2-TZVPP算氢的精度与revTPSS/pcSseg-1基本持平，但KT1和KT2算碳的精度远不如revTPSS/pcSseg-1。由于KT泛函被程序支持较少（Gaussian不支持，ORCA需通过libxc），且revTPSS表现更全面，因此没必要使用KT系列泛函。

## 溶剂模型对NMR计算的影响
对于氯仿环境下的NMR计算，使用隐式溶剂模型不一定使结果更好，因为氯仿极性弱且存在误差抵消因素。revTPSS/pcSseg-1在真空和IEFPCM氯仿环境下互有胜负，建议仍考虑氯仿溶剂环境以符合原理。双杂化泛函DSD-PBEP86在CPCM氯仿环境下计算结果明显劣于真空，强烈建议在真空下计算。

## 振动校正对NMR计算精度结论的影响
精确计算能与实验对照的NMR化学位移不可忽略振动校正，但本文测试未考虑这一点，因为计算耗时极高。本文关于精度的结论实际上是忽略了振动校正等因素带来的误差抵消后的结果，并不直接反映计算磁屏蔽张量的内在理论精度。由于日常NMR计算一般不考虑振动校正，本文结论对于实际应用性研究具有直接指导意义。

## 使用Gaussian输入revTPSS和pcSseg基组的方法
在Gaussian中使用revTPSS泛函时需写成revTPSSrevTPSS，代表交换和相关泛函均为revTPSS定义。pcSseg基组在Gaussian 16 C.01版本中未内置，需从BSE基组数据库拷贝定义来使用，可参考《详解Gaussian中混合基组、自定义基组和赝势基组的输入》和《在线基组和赝势数据库一览》。

## 使用ORCA进行DSD-PBEP86 NMR计算的设置
在ORCA中用DSD-PBEP86/def2-TZVPP在CPCM氯仿下做NMR计算，关键词可写为：`! DSD-PBEP86 def2-TZVPP def2-TZVPP/C tightSCF NMR miniprint nopop defgrid3 CPCM(chloroform)`。双杂化算NMR强制使用RI近似，必须用库仑拟合辅助基组（如def2-TZVPP/C），且建议使用defgrid3格点。若使用pcSseg系列基组，可用cc-pwCVnZ/C系列辅助基组或autoaux关键词。

## 使用ORCA调用libxc计算KT系列泛函
ORCA自身代码不支持KT系列泛函，需通过libxc接口使用，例如使用KT2算NMR的关键词如下：
```
! def2-TZVPP tightSCF NMR miniprint nopop defgrid3
%method
 method dft
 functional gga_xc_kt2
 end
```
其中gga_xc_kt2是libxc库中的名称。对于ORCA自身支持的泛函，使用libxc接口对结果影响可忽略但耗时更高。

---

## 2. Multiwfn支持revTPSS/pcSseg-1级别的参考值

Multiwfn从2021-Oct-23更新版本开始，支持使用B3LYP/6-31G*优化、revTPSS/pcSseg-1 (IEFPCM氯仿) 级别的TMS碳和氢磁屏蔽值作为参考。在绘制NMR界面选项7中选定参考屏蔽值选项，即可将读入的磁屏蔽值转化为化学位移并直接作图，无需手动计算和输入TMS值。
