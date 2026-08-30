---
key: b623
title: revTPSS泛函结合pcSseg-1基组是计算NMR很好的选择
url: http://sobereva.com/623
domain: 量子化学方法
source: blog
year: 2021
cards: 22
---

# revTPSS泛函结合pcSseg-1基组是计算NMR很好的选择 — 知识卡片

## 1. JCTC期刊关于revTPSS泛函计算氢谱化学位移的研究

JCTC期刊一项研究以氯仿中有机分子的实验氢化学位移为参照，测试了多种泛函计算氢化学位移的精度。该研究声称revTPSS泛函（meta-GGA档次）表现优异，不输于依赖拟合参数的标度法，且优于双杂化泛函和MP2。此结论与以往使用CCSD(T)平衡结构数据作为参照的横测文章结论存在差异，原因在于测试集不同及参照标准不同。直接以实验数据为参照的测试结论对于不进行振动校正和显式溶剂计算的应用性研究更具实际意义。

---

## 2. 测试分子与实验数据来源

测试选取了恶丁环、异恶唑和吡啶三个有代表性的有机小分子。实验的氢1和碳13化学位移数据均为在氯仿环境下测得。

---

## 3. revTPSS/pcSseg-1计算氢谱的精度与优势

revTPSS结合专门为NMR计算的pcSseg-1基组计算氢化学位移表现出色。pcSseg-1基组大小与6-31G**相当，revTPSS/pcSseg-1计算成本低且结果准确，精度与标度法互有胜负。若不想使用经验性强的标度法，revTPSS/pcSseg-1是首选，也可与标度法结果相互检验。

---

## 4. revTPSS/pcSseg-1计算碳谱的精度

revTPSS/pcSseg-1计算碳化学位移的精度明显不如计算氢时准确，但优于其它普通泛函结合较贵的def2-TZVPP基组的结果。计算碳谱时优先建议使用标度法，若使用标准方式计算则推荐revTPSS/pcSseg-1。

---

## 5. 基组对revTPSS计算NMR的影响

使用更昂贵的pcSseg-2基组反而导致结果变差，显示出revTPSS/pcSseg-1的良好表现包含泛函与基组误差抵消的因素。revTPSS结合def2-SVP基组表现远不如结合pcSseg-1，因为def2-SVP太小且非专用NMR基组。revTPSS结合def2-TZVPP基组表现优于def2-SVP，但比pcSseg-1无优势且成本更高，因此不值得考虑。

---

## 6. 溶剂模型对NMR计算的影响

与氯仿实验NMR对照时，使用隐式溶剂模型不一定改进结果，因氯仿极性弱且存在误差抵消因素。DSD-PBEP86双杂化泛函在CPCM氯仿环境下计算的NMR明显差于真空下，建议此时在真空下计算。

---

## 7. 双杂化泛函DSD-PBEP86的计算表现

在真空下，DSD-PBEP86结合def2-TZVPP基组优于B97-2、B3LYP和MP2，但相比revTPSS/pcSseg-1无明显优势。仅在标度法和revTPSS/pcSseg-1表现均不佳时，才考虑使用计算代价更高的DSD-PBEP86/def2-TZVPP（在真空下）。

---

## 8. MP2与双杂化泛函计算NMR的效率

Gaussian在MP2下计算NMR非常昂贵，而ORCA利用RI近似进行MP2或双杂化泛函NMR计算速度极快。例如在i7-10870H上使用DSD-PBEP86/def2-TZVPP计算吡啶NMR仅需约一分半钟。

---

## 9. KT系列泛函计算NMR的表现

KT2结合def2-TZVPP计算氢谱精度与revTPSS/pcSseg-1基本持平，但KT系列泛函程序支持度较低（Gaussian不支持，ORCA需通过libxc）。考虑溶剂模型并未改进KT1的计算结果，甚至对氢谱有所劣化。KT1和KT2计算碳谱的精度远逊于revTPSS/pcSseg-1。

---

## 10. 大基组对DSD-PBEP86计算结果的影响

DSD-PBEP86结合很大的pcSseg-3基组（视为CBS级别）计算氢谱精度相比def2-TZVPP仅微弱改进，但计算碳谱精度显著下降。这表明DSD-PBEP86在NMR计算上相对revTPSS无优势是泛函自身性质所致，增大基组无法改变此结论。

---

## 11. 几何优化级别对revTPSS计算NMR的影响

使用B3LYP结合不同基组（6-31G*、def2-SVP、def2-TZVPP）优化的结构，对revTPSS/pcSseg-1计算NMR的结果影响不大且无规律。优化仅需使用便宜的B3LYP/6-31G*即可，使用昂贵的def2-TZVPP不会带来改进。

---

## 12. revTPSS/pcSseg-1计算氢谱的综合结论

revTPSS特别适合计算氯仿环境中有机体系的氢化学位移。revTPSS/pcSseg-1在IEFPCM氯仿环境下计算氢谱，在耗时和精度上与标度法相当。revTPSS/pcSseg-1经验性低、不依赖拟合参数，是比标度法更普适的方法。

---

## 13. revTPSS/pcSseg-1计算碳谱与双杂化泛函的结论

revTPSS/pcSseg-1计算氯仿中有机体系碳谱精度不明显输于标度法，优于普通泛函及MP2结合大基组，昂贵双杂化泛函相对无优势。对于算氢和碳的NMR，双杂化泛函相比revTPSS/pcSseg-1和标度法无优点，不值得花费高计算代价，但不排除在其它体系或元素上有更好表现。

---

## 14. 振动校正对结论的说明

精确计算与实验对照的NMR化学位移不可忽略振动校正，但资料未考虑此因素。资料的结论基于忽略振动校正等因素后的误差抵消，反映了实际应用研究（通常不考虑振动校正）中的直接指导意义。

---

## 15. Multiwfn对revTPSS/pcSseg-1计算的支持

Multiwfn从2021-Oct-23更新版本开始，内置了B3LYP/6-31G*优化和revTPSS/pcSseg-1 (IEFPCM氯仿)级别的TMS参考磁屏蔽值。用户可直接使用该功能将计算值转化为化学位移作图，无需手动计算和输入TMS值。

---

## 16. revTPSS泛函在Gaussian中的写法

在Gaussian输入文件中，revTPSS泛函需要写成`revTPSSrevTPSS`，代表交换泛函和相关泛函均采用revTPSS定义。

---

## 17. pcSseg基组在Gaussian与ORCA中的使用

Gaussian 16（C.01及之前）未内置pcSseg基组，需从BSE数据库拷贝定义使用。ORCA内置pcSseg基组，可直接在关键词中使用，如`pcSseg-1`。

---

## 18. B97-2泛函在Gaussian中的写法

在Gaussian程序中，B97-2泛函应写作`B972`。

---

## 19. ORCA中DSD-PBEP86计算NMR的关键词

ORCA中在CPCM氯仿环境下使用DSD-PBEP86/def2-TZVPP计算NMR的关键词示例如下：
```
! DSD-PBEP86 def2-TZVPP def2-TZVPP/C tightSCF NMR miniprint nopop defgrid3 CPCM(chloroform)
```
双杂化计算强制使用RI近似，必须指定库仑拟合辅助基组（如def2-TZVPP/C）。`defgrid3`提供比默认更好的积分格点。

---

## 20. ORCA中使用pcSseg基组进行双杂化计算的辅助基组选择

若使用pcSseg系列基组进行双杂化泛函NMR计算，无标配辅助基组，可使用cc-pwCVnZ/C系列。例如pcSseg-3应搭配cc-pwCVQZ/C，也可使用`autoaux`让ORCA自动构建。

---

## 21. ORCA中通过libxc使用KT系列泛函

ORCA自身不支持KT系列泛函，需通过libxc接口调用。例如使用KT2计算NMR的关键词如下：
```
! def2-TZVPP tightSCF NMR miniprint nopop defgrid3
%method
 method dft
 functional gga_xc_kt2
 end
```
`gga_xc_kt2`是libxc库中的名称，可用`orca -libxcfunctionals`查看支持的写法。

---

## 22. libxc界面对计算结果的影响

对于ORCA自身支持的泛函，使用libxc界面实现与否对NMR计算结果影响可忽略，但libxc界面的计算耗时通常更高。
