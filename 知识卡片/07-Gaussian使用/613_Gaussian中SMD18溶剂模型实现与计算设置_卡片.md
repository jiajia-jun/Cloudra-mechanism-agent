---
id: 613
title: 显著改进SMD溶剂模型描述Br和I元素精度的溶剂模型SMD18的介绍
url: http://sobereva.com/613
domain: Gaussian使用
topic: Gaussian中SMD18溶剂模型实现与计算设置
cards: 13
---
## 1. SMD模型原子半径定义规则

SMD溶剂模型通过原子球叠加构建溶质孔洞以计算溶剂-溶质相互作用的静电部分。SMD原文仅对H、C、N、O、F、Si、P、S、Cl、Br专门优化了原子半径，对其它元素使用Bondi范德华半径，若Bondi半径缺失则使用2.0埃。
- 参考链接：[http://原作者.com/327](http://原作者.com/327)

---



---

## 2. SMD18模型对Br和I原子半径的修正

SMD18模型源自Chem. Eur. J., 24, 15983 (2018)，该研究发现SMD模型对碘使用Bondi范德华半径1.98埃过小，故改用SM1模型中优化的半径2.74埃，极大提升了结果准确性。同时研究对Br半径进行优化，发现2.60埃比SMD原文的3.06埃更接近实验数据。SMD18即指将SMD中Br和I半径分别改为2.60埃和2.74埃后的模型。

---

## 3. SMD18模型的适用场景

对于溶液中涉及卤键形成或断裂的过程、与Br和I密切相关的化学过程（如成键断键），以及计算含有Br和I体系的溶解自由能，强烈建议使用SMD18代替SMD模型。

---

## 4. SMD18推荐的理论方法与计算流程

SMD18模型非常适合结合M06-2X泛函使用。为最大程度实现误差抵消，计算溶液中自由能（1M标准态）的流程应与SMD18原文一致：在M06-2X下进行优化和振动分析并直接携带SMD18溶剂模型，取程序输出的自由能后加上1.89 kcal/mol的1atm->1M标准态转变自由能变。

---

## 5. SMD18推荐的基组设置

按照SMD18原文，对Cl、Br、I应当使用def2-TZVPD基组（对I需结合相应赝势），对其它元素使用def2-TZVP。Gaussian中相关设置可参考《给ahlrichs的def2系列基组加弥散的方法》和《详解Gaussian中混合基组、自定义基组和赝势基组的输入》。
- 参考链接：[http://原作者.com/340](http://原作者.com/340), [http://原作者.com/60](http://原作者.com/60)

---



---

## 6. 低频振动时的热力学校正方法

根据SMD18原文，若存在100 cm^-1以下的低频振动频率，应使用Grimme的准RRHO模型计算热力学量，而非Gaussian默认的RRHO模型。这可以通过Shermo程序实现，详见《使用Shermo结合量子化学程序方便地计算分子的各种热力学数据》。
- 参考链接：[http://原作者.com/552](http://原作者.com/552)

---



---

## 7. SMD18计算的经济性替代方案

def2-TZVP和def2-TZVPD基组用于opt freq计算昂贵，为与SMD18优化半径实现误差抵消需忍受该成本。若计算过于吃力，可在opt freq时使用def2-TZVP(-f)等便宜基组（对热校正和结构影响小），再用SMD18原文基组做单点计算，最后相加电子能量和自由能热校正量。此外，为保持与原文一致，不考虑ZPE校正因子。

---

## 8. Gaussian中实现SMD18的输入设置

目前Gaussian不支持直接调用SMD18，但可通过修改SMD模型中Br和I半径实现。需使用scrf(SMD,solvent=溶剂名,read)关键词，并在输入文件末尾空一行写modifysph，下面再空一行写入：I 2.74和Br 2.60。

---

## 9. Gaussian中SMD18计算的完整输入示例

以下为使用M062X/def2-TZVP(D)级别在乙腈中做opt freq的Gaussian 16输入示例，包含引入外部基组文件、赝势文件及修改Br、I半径的设定。输入文件和输出文件可在[http://原作者.com/attach/613/file.zip](http://原作者.com/attach/613/file.zip)下载。
```
#P M062X/genecp SCRF(SMD,solvent=acetonitrile,read) opt freq

Title

0 1
[坐标略]

@/sob/SMD18.gbs/N

@/sob/def2-ECP.txt/N

modifysph

I 2.74
Br 2.60

```

---



---

## 10. SMD18计算所需的外部基组与赝势文件

SMD18.gbs是基于BSE数据库def2-TZVP基组文件并将Cl、Br、I替换为def2-TZVPD后的基组文件。def2-ECP.txt是def2系列标配的Stuttgart赝势基组定义。即使体系不含I，也可使用通用输入文件（此时I的赝势及半径修改不生效）。文件可在[http://原作者.com/attach/613/SMD18.gbs](http://原作者.com/attach/613/SMD18.gbs)和[http://原作者.com/attach/613/def2-ECP.txt](http://原作者.com/attach/613/def2-ECP.txt)下载。

---

## 11. Gaussian 09修改半径的Bug及注意事项

在Gaussian 09中，元素半径的修改无法在opt freq任务中传递给freq部分，这是一个Bug，因此必须将opt和freq分别进行计算。该问题在Gaussian 16中已得到修正。

---

## 12. 使用Shermo处理低频振动并计算自由能

对于低频仅44.24 cm^-1的体系，不应直接读取输出文件中基于RRHO模型的结果，而应使用Shermo程序基于准RRHO模型计算。将Shermo的settings.ini中ilowfreq设为2，读取输出文件得到"Sum of electronic energy and thermal correction to G"（例如-3176.6090365 a.u.），加上1.89/627.51=0.00301 a.u.的标准态转换项，即得1M浓度下的乙腈自由能-3176.60602 a.u.。

---

## 13. 隐式溶剂模型准确度对原子半径的敏感性

SMD18模型体现了隐式溶剂模型计算能量的准确度对原子半径的高度敏感性。J. Phys. Chem. A, 123, 9498 (2019)提出的SMD-B模型将SMD原子半径全部改为Bondi范德华半径，改进了离子体系（特别是含硫）的溶解自由能计算。在scrf里使用read关键词并在输入文件末尾加Radii=Bondi可简便实现SMD-B。
