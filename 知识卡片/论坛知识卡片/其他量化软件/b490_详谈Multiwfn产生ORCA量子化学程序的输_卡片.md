---
key: b490
title: 详谈Multiwfn产生ORCA量子化学程序的输入文件的功能（建议所有ORCA用户一读！）
url: http://sobereva.com/490
domain: 其他量化软件
source: blog
year: 2019
cards: 33
---

# 详谈Multiwfn产生ORCA量子化学程序的输入文件的功能（建议所有ORCA用户一读！） — 知识卡片

## 1. ORCA与Multiwfn生成输入文件功能

Multiwfn波函数分析程序支持生成ORCA量子化学程序的输入文件，该功能兼容ORCA最新版本并会随ORCA更新而调整。此功能将当前载入体系的坐标代入预设的任务关键词模板中，用户仅需修改内存和核数等参数即可运行，显著降低了ORCA的使用门槛。支持作为输入的文件格式包括fch、molden、wfn、mol、mol2、pdb、xyz、gjf等含结构信息的文件。

---

## 2. ORCA输入文件生成界面操作

进入Multiwfn主功能100的子功能2中的选项12（或直接在主菜单输入oi），输入输出文件名后即可进入ORCA输入文件生成界面。界面选项涵盖了计算任务选择、计算级别设定、计算资源设置、溶剂模型添加及弥散函数开关等功能，用户可根据需要调整参数以生成最终的输入文件。

---

## 3. ORCA计算任务类型选择

在生成ORCA输入文件的界面中，选项0允许用户选择计算任务类型。支持的任务类型包括单点计算、优化极小点、振动分析、优化极小点+振动分析、优化过渡态+振动分析、分子动力学以及考虑Counterpoise校正计算结合能。

---

## 4. ORCA振动分析与分子动力学设置

当选择振动分析任务时，生成的关键词会自动加上`tightSCF`以使用更严格的SCF收敛标准（优化任务ORCA默认即使用`tightSCF`）。分子动力学任务默认设置为在298.15 K控温下使用0.5 fs步长模拟500步。

---

## 5. ORCA输入文件中的溶剂模型

通过界面选项-1可以启用溶剂模型，支持使用SMD模型表现溶剂环境，输入溶剂名后生成的输入文件将包含相应的关键词。ORCA直接支持的SMD溶剂名详见其手册，输入`c`则可使用CPCM溶剂模型或自定义溶剂。

---

## 6. ORCA输入文件中的弥散函数

通过界面选项-2可以将基组切换为带弥散函数的版本，适用于阴离子体系单点等需要弥散函数的情况。启用后，cc-pVnZ系列基组会变为aug-cc-pVnZ，def2系列基组会变为ma-def2系列，辅助基组也会自动调整（ma-def2系列使用`autoaux`关键词构建）。B97-3c、r2SCAN-3c和CCSD(T)-F12/cc-pVDZ with RI级别无法添加弥散函数。

---

## 7. ORCA输入文件电荷与多重度设定

若载入Multiwfn的文件是fch、wfn、molden等包含波函数信息的文件，生成的ORCA输入文件中的电荷和自旋多重度将自动沿用原波函数的值。若载入的是xyz、pdb等仅含结构的文件，用户需要根据实际情况手动修改输入文件中的电荷和自旋多重度。

---

## 8. ORCA方法与任务类型的兼容性

部分ORCA计算方法与特定任务类型不兼容，例如ORCA 5.0版本中PWPB95-D3(BJ)因缺乏解析梯度无法直接用于几何优化。某些方法（如TDDFT）在启用SMD溶剂模型后也可能不再支持解析梯度，此时需手动在输入文件中添加`numgrad`（数值梯度）或`numfreq`（数值Hessian）等关键词。

---

## 9. ORCA计算资源设置

输入文件中的`%maxcore`参数控制ORCA并行计算时每个进程使用的内存上限（MB）。建议设置值计算公式为：（总物理内存 - 系统占用）/ 核数，并适当下调以留出余量。CPU核数和`maxcore`既可直接编辑生成的输入文件，也可在生成界面中通过选项-10进行修改，默认核数与Multiwfn配置文件中的`nthreads`参数一致。

---

## 10. ORCA输入文件默认关键词

Multiwfn生成的ORCA输入文件默认包含`noautostart`和`miniprint`关键词。`noautostart`禁止ORCA自动读取当前目录下的gbw文件作为初猜，`miniprint`用于减少无意义的中间信息输出并关闭默认的布居分析，以减小输出文件体积。

---

## 11. 使用用户模板生成ORCA输入文件

通过界面选项-100，用户可以提供自定义的ORCA模板文件，其中将坐标部分标记为`[geometry]`，Multiwfn会将其替换为当前体系的坐标。此功能允许完全自定义ORCA输入文件内容，结合脚本可实现批量将xyz文件等转化为带有特殊关键词的ORCA输入文件。

---

## 12. 计算级别B97-3c

B97-3c是Grimme提出的低成本组合方法，使用纯泛函和内定基组，包含DFT-D3和gCP校正，适用于主族和过渡金属体系。其计算耗时略高于RI-BLYP/def2-SVP，但精度更好，适合大体系优化、能量计算或小体系初步筛选。

---

## 13. 计算级别r2SCAN-3c

r2SCAN-3c是基于r2SCAN泛函的-3c方法，是B97-3c的后继者。其耗时比B97-3c高百分之几十，但精度全面提升，在条件允许时建议总是使用r2SCAN-3c代替B97-3c。

---

## 14. 计算级别RI-BLYP-D3(BJ)/def2-TZVP

该级别使用RIJ加速的BLYP纯泛函，结合D3(BJ)色散校正和def2-TZVP基组，在弱相互作用计算中表现优异。利用RIJ加速后，计算速度比Gaussian快一个数量级以上（振动分析除外），但精度未必优于B97-3c，在ORCA 5.0支持r2SCAN-3c后使用价值降低。

---

## 15. 计算级别RI-B3LYP-D3(BJ)/def2-TZVP(-f)

该级别结合了B3LYP泛函、D3(BJ)色散校正和去除了f极化函数的def2-TZVP(-f)基组。使用RIJCOSX加速杂化泛函计算，`def2/J`指定辅助基组，计算速度远胜Gaussian但显著高于纯泛函，适合主族体系计算。

---

## 16. 计算级别RI-B3LYP-D3(BJ)/def2-TZVP

该级别与RI-B3LYP-D3(BJ)/def2-TZVP(-f)类似，但使用完整的def2-TZVP基组。关键词为`B3LYP D3 def2-TZVP def2/J RIJCOSX`。

---

## 17. 计算级别RI-wB97M-V/def2-TZVP

该级别使用wB97M-V泛函、def2-TZVP基组和RIJCOSX加速，并添加`strongSCF`以提高SCF收敛精度。ωB97M-V在主族和过渡金属体系的反应能、势垒及弱相互作用计算中性能顶级，但缺乏解析Hessian，不建议用于优化，推荐配合低级别优化结构后进行单点计算。

---

## 18. 计算级别RI-PWPB95-D4/def2-TZVPP

该级别使用双杂化泛函PWPB95-D4和def2-TZVPP基组，通过RIJCOSX加速SCF部分，RI加速相关部分（使用def2-TZVPP/C辅助基组），并使用`tightSCF`确保精度。其精度介于ωB97M-V和CCSD(T)之间，适用于较大体系的高精度单点计算。

---

## 19. 计算级别RI-PWPB95-D4/def2-QZVPP

该级别使用PWPB95-D4泛函和def2-QZVPP基组，其余设置同RI-PWPB95-D4/def2-TZVPP。为了充分发挥双杂化泛函的潜力，在计算量可接受的情况下推荐使用此更大基组。

---

## 20. 计算级别RI-wB97X-2-D3(BJ)/def2-TZVPP

该级别使用wB97X-2泛函和def2-TZVPP基组。由于ORCA未内置其DFT-D3(BJ)色散校正参数，生成的输入文件会通过`%method ... end`字段自动补充参数。关键词包含`tightSCF`、RIJCOSX及相应的辅助基组。

---

## 21. 计算级别RI-revDSD-PBEP86-D4/def2-TZVPP

该级别使用revDSD-PBEP86-D4泛函和def2-TZVPP基组，是计算有机反应能及弱相互作用能方面表现顶级的方法之一。关键词为`revDSD-PBEP86-D4/2021 def2-TZVPP def2/J def2-TZVPP/C RIJCOSX tightSCF`。

---

## 22. 计算级别DLPNO-CCSD(T)/def2-TZVPP with normalPNO

该级别使用DLPNO-CCSD(T)方法和NormalPNO阈值，结合RIJCOSX加速HF部分，使用def2-TZVPP基组及对应辅助基组。NormalPNO精度显著优于双杂化泛函，相对于CCSD(T)误差通常在1 kcal/mol以内，适合计算较大体系。

---

## 23. 计算级别DLPNO-CCSD(T)/def2-TZVPP with tightPNO

该级别使用DLPNO-CCSD(T)方法和TightPNO阈值，相对于CCSD(T)误差在1 kJ/mol左右。TightPNO耗时通常比NormalPNO高几倍，若追求更高精度可将基组提升至def2-QZVPP。

---

## 24. 计算级别CCSD(T)/cc-pVTZ

该级别为标准的CCSD(T)方法结合cc-pVTZ基组，使用`tightSCF`。若遇到不支持的元素，需将cc-pVTZ替换为def2-TZVPP；若缺乏辅助基组，需相应替换辅助基组。

---

## 25. 计算级别CCSD(T)-F12/cc-pVDZ-F12 with RI

该级别结合了显式相关方法F12与cc-pVDZ-F12基组，利用RI加速。其耗时显著低于CCSD(T)/cc-pVQZ，但精度与之接近，适合需要接近cc-pVQZ档次数据但计算资源受限的情况。

---

## 26. 计算级别Approximated CCSD(T)/CBS with help of MP2

该级别利用ORCA的`ExtrapolateEP2(3/4,cc,MP2)`关键词实现基于MP2的近似CBS外推。通过MP2/cc-pVTZ和cc-pVQZ外推MP2/CBS相关能，再结合CCSD(T)/cc-pVTZ能量，近似得到CCSD(T)/CBS结果，避免了昂贵的CCSD(T)/cc-pVQZ计算，误差通常在0.1 kcal/mol左右。

---

## 27. ORCA中DLPNO-CCSD(T)与CCSD(T)的CBS外推设置

DLPNO-CCSD(T)结合tightPNO设置能够以接近CCSD(T)的精度处理明显更大的体系，但目前ORCA无法通过一套关键词直接实现tightPNO下的DLPNO-CCSD(T) CBS外推。ORCA支持使用Extrapolate关键词对任意后HF方法进行基组外推，RIJCOSX积分加速可用于节约SCF时间。
- DLPNO-CCSD(T)/CBS (def2-TZVPP->QZVPP extrapolation) 关键字：`DLPNO-CCSD(T) tightPNO Extrapolate(3/4,def2) def2-QZVPP/C RIJCOSX tightSCF`
- CCSD(T)/CBS (cc-pVTZ->QZ extrapolation) 关键字：`CCSD(T) Extrapolate(3/4,cc) tightSCF`
- 使用def2基组而非cc-pVXZ基组进行DLPNO计算是基于辅助基组层面的考量。

---

## 28. 大体系电子光谱计算：sTD-DFT方法

对于好几百个原子的大体系，使用常规TDDFT计算覆盖感兴趣波长范围所需的大量激发态往往过于困难，此时可采用Grimme提出的sTD-DFT方法。sTD-DFT基于DFT轨道，通过对TDDFT矩阵元进行高度近似，仅需少量计算量即可算出大量激发态，虽然精度有所降低但满足大体系粗放式研究需求。
- 参考文献Phys.Chem.Chem.Phys.,16,14408(2014)测试表明，将wB97X-D3泛函结合sTD-DFT用于大体系（通常有显著电子共轭）结果较理想。
- sTD-DFT目前仅支持对单个结构做电子激发计算，不可用于激发态优化或振动分析。

---

## 29. ORCA中sTD-DFT计算的关键字与参数

进行sTD-DFT计算时，需先进行DFT单点计算，随后基于其轨道进行sTD-DFT计算。参数PThresh和PTLimit用于控制纳入考虑的组态函数范围，在大体系计算中设置合理的阈值可避免耗时过高且对精度影响可忽略不计。
- 关键字示例：`wB97X-D3 def2-SV(P) def2/J RIJCOSX`
- 模块设置：
  ```
  %tddft
   Mode sTDDFT
   Ethresh 7.0
   PThresh 1e-4
   PTLimit 30
   maxcore 6000
  end
  ```

---

## 30. ORCA中常规TDDFT计算设置（PBE0）

PBE0是TDDFT计算激发态的常用泛函，def2-SV(P)基组大小与6-31G*相近，适合计算中、大体系的电子光谱，在计算成本和精度之间取得平衡。使用tightSCF关键字有助于降低数值层面的误差，nroots参数用于指定计算的激发态数目。
- 关键字示例：`PBE0 def2-SV(P) def2/J RIJCOSX tightSCF`
- 模块设置：
  ```
  %tddft
   nroots 10
   TDA false
  end
  ```
- 对于大共轭体系，建议将泛函改为CAM-B3LYP等长程校正泛函；若追求更高精度，可将基组升级为def2-TZVP(-f)或def2-TZVP。

---

## 31. ORCA中双杂化泛函TDDFT计算设置

ORCA支持双杂化泛函下的TDDFT计算，该级别精度高于普通泛函TDDFT但耗时也明显更高。根据JCTC文献测试，DSD-PBEP86在计算局域激发和分子内电荷转移激发时表现最佳，而RSX-QIDH是计算分子间CT激发的首选。
- 关键字示例 (DSD-PBEP86)：`DSD-PBEP86 def2-TZVP def2/J def2-TZVP/C RIJCOSX tightSCF`
- 若使用RI-RSX-QIDH，将上述关键字中的泛函名改为RSX-QIDH。
- 模块设置：
  ```
  %tddft
   nroots 10
   TDA false
  end
  ```

---

## 32. ORCA中EOM-CCSD激发态计算

EOM-CCSD方法计算激发态具有不错的精度，比TD-双杂化泛函方法更高、更稳健且普适，但计算成本颇高，且随计算态数增加总耗时迅速增加。该方法主要适用于小体系的低阶激发态高精度研究，RI加速技术在EOM-CCSD计算中不适用。
- 关键字示例：`EOM-CCSD cc-pVTZ tightSCF`
- 模块设置：
  ```
  %mdci
   nroots 3
  end
  ```

---

## 33. ORCA中STEOM-DLPNO-CCSD激发态计算

STEOM-CCSD与EOM-CCSD精度相当，但在电荷转移激发（CT）方面往往表现更好，二者不应视为近似关系而是不同方法。引入DLPNO技术后的STEOM-DLPNO-CCSD可用于处理大得多的体系，在def2-TZVP(-f)基组下可计算超过60个原子的体系，但该方法极度消耗硬盘空间（需数TB剩余空间）。
- 关键字示例：`STEOM-DLPNO-CCSD RIJCOSX def2-TZVP(-f) def2/J def2-TZVP/C tightSCF`
- 模块设置：
  ```
  %mdci
   nroots 3
  end
  ```
