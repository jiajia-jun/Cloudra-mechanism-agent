---
id: 490
title: 详谈Multiwfn产生ORCA量子化学程序的输入文件的功能
url: http://sobereva.com/490
domain: 其他量化软件
topic: Multiwfn生成ORCA输入文件功能详解
cards: 26
---

# Multiwfn生成ORCA输入文件功能详解 — 知识卡片

## 1. Multiwfn生成ORCA输入文件的功能定位

Multiwfn产生ORCA输入文件的功能是将当前载入的体系坐标套入特定类型任务的关键词模板里，用户只需修改内存、核数等参数即可运行，这显著降低了ORCA的使用门槛。产生的关键词对ORCA最新版都是合适的，且随着ORCA的更新和用法变动，Multiwfn也会相应地更新。如果研究中使用了此功能，建议在文章中提及"The input files of ORCA program were prepared with the help of Multiwfn code"并引用Multiwfn。

---

## 2. 生成ORCA输入文件的文件输入与界面进入

支持含有结构信息的任意Multiwfn支持的文件作为输入，如fch、molden、wfn、mol、mol2、pdb、xyz、gjf等。进入主功能100的子功能2中的选项12（或在主菜单直接输入oi），输入要产生的ORCA输入文件名即可看到设置界面。

---

## 3. 输入文件中的默认关键词与设置

Multiwfn产生的ORCA输入文件里都带着noautostart miniprint关键词。noautostart代表要求ORCA不自动从当前目录下与任务同名的gbw文件读取结构和波函数作为初猜。miniprint代表避免输出对普通用户无意义的中间信息，也不自动做布居分析，以避免输出文件信息量过大。

---

## 4. 计算资源设置选项

界面选项-10用于设置计算资源，默认核数与Multiwfn的settings.ini里的nthreads参数等同，默认内存为每个核心1000 MB。输入文件里的%maxcore控制ORCA并行计算时每个进程用的内存量（MB）的上限，设置时需考虑物理内存总量及并行核数，并留有余量。

---

## 5. 溶剂模型设置选项

界面选项-1用于启用隐式溶剂模型，默认为No。选择后可输入SMD溶剂名（ORCA直接支持的溶剂名详见手册），输入c则可使用CPCM溶剂模型或自定义溶剂。启用后导出的输入文件里会携带相应的溶剂模型关键词。

---

## 6. 弥散函数添加选项

界面选项-2用于切换是否添加弥散函数，默认为No。切换为Yes后，cc-pVnZ系列基组会改为aug-cc-pVnZ，def2系列基组会改为ma-def2系列，辅助基组也会相应改成恰当的。对于ma-def2系列，由于没有标配的辅助基组，会自动使用autoaux关键词自动构建。

---

## 7. 自定义模板文件生成输入

界面选项-100允许用户提供一个ORCA模板文件，其中包含实际计算要用的所有设置，但坐标部分写成[geometry]。Multiwfn会将[geometry]替换为当前体系的坐标来产生ORCA输入文件，以此实现完全自定义的输入文件创建或批量处理。

---

## 8. ORCA版本兼容性设置

界面选项-11用于选择ORCA版本兼容性，默认对应>ORCA 5.0。由于ORCA不同大版本的某些关键词写法相差甚大，此选项确保了产生的输入文件能与指定版本的ORCA兼容。

---

## 9. 电荷与自旋多重度的来源

如果载入Multiwfn的文件是fch、wfn、molden等带有波函数信息的，产生的ORCA输入文件里的电荷和自旋多重度与原波函数一致。如果载入的是xyz、pdb等只含结构信息的文件，用户需根据实际情况手动修改电荷和自旋多重度。

---

## 10. 甲醇结构优化与单点计算示例流程

首先在GaussView中画甲醇并保存，载入Multiwfn，依次输入100、2、12、opt.inp、0（选任务）、2（选优化）、1（选B97-3c）生成opt.inp并运行。算完后载入生成的opt.xyz，依次输入100、2、12、SP.inp、-1（启用溶剂）、ethanol（输入溶剂名）、5（选RI-wB97M-V/def2-TZVP）生成SP.inp并运行。

---

## 11. B97-3c计算级别特点

关键词：B97-3c。这是Grimme提出的便宜且快的组合式方法，使用纯泛函、内定基组及DFT-D3、SRB校正，适用于主族和过渡金属体系。使用时不需要写与RI相关的关键词和指定辅助基组，因为默认会使用RIJ和恰当的辅助基组。

---

## 12. r2SCAN-3c计算级别特点

关键词：r2SCAN-3c。这是B97-3c的后继者，基于2020年末提出的r2SCAN泛函，耗时比B97-3c高百分之几十，但精度全面提升。如果不是特别追求速度，建议总是用r2SCAN-3c代替B97-3c。

---

## 13. RI-BLYP-D3(BJ)/def2-TZVP计算级别特点

关键词：BLYP D3 def2-TZVP def2/J。这是纯泛函结合RIJ加速库仑部分计算，对于稍大体系速度可比Gaussian快一个数量级以上。关键词中D3代表加上DFT-D3(BJ)色散校正，def2/J代表使用def2系列通用的RIJ辅助基组。

---

## 14. RI-B3LYP-D3(BJ)/def2-TZVP(-f)计算级别特点

关键词：B3LYP D3 def2-TZVP(-f) def2/J RIJCOSX。def2-TZVP(-f)是去掉了f极化函数的def2-TZVP，能显著节约时间。RIJCOSX关键词用于加速杂化泛函计算，对于二、三十个原子以上的体系通常比RIJK更快。

---

## 15. RI-wB97M-V/def2-TZVP计算级别特点

关键词：wB97M-V def2-TZVP def2/J RIJCOSX strongSCF。ωB97M-V在非双杂化泛函中性能顶级，但由于没有解析Hessian不建议做优化，推荐用B97-3c或RI-B3LYP-D3(BJ)/def2-TZVP(-f)优化后用此级别算单点。strongSCF用于提高能量收敛精度。

---

## 16. RI-PWPB95-D4/def2-TZVPP计算级别特点

关键词：PWPB95 D4 def2-TZVPP def2/J def2-TZVPP/C RIJCOSX tightSCF。这是稳健且精度很好的双杂化泛函，SCF部分用RIJCOSX加速，MP2部分用RI加速并使用def2-TZVPP/C辅助基组。tightSCF保证SCF部分尽量准确。手动加上float关键词可用单精度变量储存中间数据以节约时间和硬盘。

---

## 17. RI-wB97X-2-D3(BJ)/def2-TZVPP计算级别特点

关键词：wB97X-2 D3 def2-TZVPP def2/J def2-TZVPP/C RIJCOSX tightSCF，并包含%method块设定D3参数。这是因为ORCA内置的原版wB97X-2搭配的DFT-D3(BJ)参数未在程序内置，需根据PCCP, 20, 23175 (2018)的补充材料在输入文件中手动补充。

---

## 18. DLPNO-CCSD(T)/def2-TZVPP with normalPNO计算级别特点

关键词：DLPNO-CCSD(T) normalPNO RIJCOSX def2-TZVPP def2/J def2-TZVPP/C tightSCF。这是CCSD(T)的近似方法，NormalPNO标准下精度显著超过revDSD-PBEP86-D4，相对于CCSD(T)的误差通常在1 kcal/mol以内。HF部分用RIJCOSX加速，相关部分用def2-TZVPP/C辅助基组。

---

## 19. DLPNO-CCSD(T)/def2-TZVPP with tightPNO计算级别特点

关键词：DLPNO-CCSD(T) tightPNO RIJCOSX def2-TZVPP def2/J def2-TZVPP/C tightSCF。结合tightPNO时，与CCSD(T)的误差在1 kJ/mol程度，但耗时比NormalPNO高几倍。若追求更高精度，建议将基组提升至def2-QZVPP。

---

## 20. CCSD(T)-F12/cc-pVDZ-F12 with RI计算级别特点

关键词：CCSD(T)-F12/RI cc-pVDZ-F12 cc-pVDZ-F12-CABS cc-pVTZ/C tightSCF。这是显式相关方法，CCSD(T)-F12结合cc-pVDZ-F12基组时，耗时显著低于CCSD(T)/cc-pVQZ，但精度接近。关键词中/RI代表利用RI进一步节约时间。

---

## 21. 近似CCSD(T)/CBS外推计算级别特点

关键词：ExtrapolateEP2(3/4,cc,MP2) tightSCF。这是利用MP2进行近似CBS外推的方法，通过MP2/cc-pVTZ和QZ外推MP2/CBS相关能，再结合CCSD(T)/cc-pVTZ估算CCSD(T)/CBS，避免了昂贵的CCSD(T)/cc-pVQZ计算，误差通常约0.1 kcal/mol。

---

## 22. DLPNO-CCSD(T)/CBS外推计算级别特点

关键词：DLPNO-CCSD(T) tightPNO Extrapolate(3/4,def2) def2-QZVPP/C RIJCOSX tightSCF。使用tightPNO标准的DLPNO-CCSD(T)结合def2系列基组进行(3/4)外推，比直接使用CCSD(T)外推便宜得多，用于计算较大体系的高精度能量。

---

## 23. sTD-DFT基于RI-wB97X-D3轨道的计算级别特点

关键词：wB97X-D3 def2-SV(P) def2/J RIJCOSX及%tddft块（含Mode sTDDFT, Ethresh 7.0, PThresh 1e-4, PTLimit 30）。此方法先做RI-wB97X-D3/def2-SV(P)单点，再基于轨道做sTD-DFT，适用于大体系计算大量激发态（如几百个原子算几百个态）。PThresh和PTLimit用于控制组态函数范围以避免耗时过高。

---

## 24. TDDFT RI-PBE0/def2-SV(P)计算级别特点

关键词：PBE0 def2-SV(P) def2/J RIJCOSX tightSCF及%tddft块（nroots 10, TDA false）。使用PBE0泛函和def2-SV(P)基组进行TDDFT计算，nroots 10代表计算10个激发态，需根据实际情况调节。tightSCF用于降低数值误差。

---

## 25. TDDFT RI-DSD-PBEP86/def2-TZVP计算级别特点

关键词：DSD-PBEP86 def2-TZVP def2/J def2-TZVPP/C RIJCOSX tightSCF及%tddft块（nroots 10, TDA false）。这是双杂化泛函下的TDDFT计算，精度比普通泛函TDDFT更高，但耗时也明显更高，计算时需指定/C辅助基组。ORCA中还提供了RI-RSX-QIDH/def2-TZVP选项用于分子间CT激发。

---

## 26. STEOM-DLPNO-CCSD/def2-TZVP(-f)计算级别特点

关键词：STEOM-DLPNO-CCSD RIJCOSX def2-TZVP(-f) def2/J def2-TZVP/C tightSCF及%mdci块（nroots 3）。这是STEOM-CCSD与DLPNO技术的结合，可处理比EOM-CCSD大得多的体系（如超过60原子），但计算非常消耗硬盘。STEOM-CCSD对CT激发的结果往往比EOM-CCSD更好。
