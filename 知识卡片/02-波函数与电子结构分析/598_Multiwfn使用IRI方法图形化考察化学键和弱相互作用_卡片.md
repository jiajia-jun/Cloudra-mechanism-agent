---
id: 598
title: 使用IRI方法图形化考察化学体系中的化学键和弱相互作用
url: http://sobereva.com/598
domain: 波函数与电子结构分析
topic: Multiwfn使用IRI方法图形化考察化学键和弱相互作用
cards: 14
---
## 1. IRI方法基本概念与文献

IRI（Interaction Region Indicator，相互作用区域指示函数）通过图形化等值面能在一幅图中同时清晰展现化学键和弱相互作用，定义简单、计算快速、图像效果优于RDG和DORI等方法。该方法对应的文献为：Tian Lu, Qinxue Chen, *Chemistry—Methods*, **1**, 231-239 (2021)，引用时应记得引用该资料。
- 相关文献：Tian Lu,* Qinxue Chen, Interaction Region Indicator (IRI): A Simple Real Space Function Clearly Revealing Both Chemical Bonds and Weak Interactions, *Chemistry—Methods*, **1**, 231-239 (2021) https://chemistry-europe.onlinelibrary.wiley.com/doi/10.1002/cmtd.202100007

---



---

## 2. IRI函数定义与参数

IRI函数定义为 $|\nabla \rho| / \rho^{a}$，其中$\rho$为电子密度，参数a的标准取值为1.1，这是能同时展现化学键和弱相互作用的最佳经验数值；若a取4/3，则IRI与RDG仅相差一个常数系数。IRI计算不依赖波函数，只要有高解析度的实验电子密度数据也可计算。
- 公式：$|\nabla \rho| / \rho^{a}$
- 参数：a=1.1 (标准定义)

---

## 3. IRI等值面着色规则

IRI等值面通过sign(λ2)ρ函数着色来区分作用强弱，其中λ2是电子密度Hessian矩阵第二大本征值。绿色区域对应范德华作用（或极弱氢键），红色区域对应位阻作用（鲜红代表位阻很强），蓝色区域对应吸引作用（如氢键、卤键）或化学键（密度通常>=0.04 a.u.）。
- 阈值：>=0.04 a.u.

---

## 4. IRI与RDG及DORI的图像对比

对于展现弱相互作用，IRI与RDG图像无显著区别，但IRI能在同一等值面数值下同时清晰展现化学键和弱相互作用，解决了RDG无法兼顾或需联用ELF的麻烦。相比DORI，IRI图像更干净、计算更快、定义更简单，避免了DORI等值面杂乱、粗糙的问题。
- 经验数值：0.9~1.1 (IRI等值面推荐值)

---

## 5. IRI在AIM理论BCP缺失情况下的应用

AIM理论有时会漏掉某些明显存在的氢键（找不到键临界点BCP），而IRI等值面能清晰显示这些相互作用。例如在Ni(NH3)2(OH)2体系中，N-H...O内氢键没有对应的BCP，但在IRI图上显示出蓝色等值面，表明存在不可忽视的吸引作用。

---

## 6. IRI用于化学反应过程分析

IRI是单一且随核坐标平滑变化的函数，适用于势能面极小点、过渡态及IRC路径上的点。通过绘制IRC路径上各点的IRI图或动画，可以生动展示化学过程中相互作用的变化，如Diels-Alder反应中共价键的逐渐形成或SN2反应中新旧键的更替。
- 参考文献：http://原作者.com/200

---

## 7. 使用Multiwfn绘制分子体系IRI等值面图

使用Multiwfn绘制分子体系IRI图需载入波函数文件（如fch），依次选择主功能20（弱相互作用可视化）、4（IRI分析）、3（高质量格点）。计算完成后在后处理界面选3导出func1.cub（sign(λ2)ρ）和func2.cub（IRI），然后利用VMD加载IRIfill.vmd脚本即可绘图。
- 脚本：IRIfill.vmd
- 输出文件：func1.cub, func2.cub

---

## 8. IRI散点图与特定区域屏蔽

在Multiwfn中计算IRI后可选择-1绘制IRI vs sign(λ2)ρ散点图。若要屏蔽特定区域，可在IRI分析前通过主功能6设置原子贡献、在格点设置中限定空间范围、或利用主功能13的格点数据屏蔽功能。
- 参考手册：Multiwfn手册4.20.4节 (散点图), 3.6节 (格点设置)

---

## 9. 屏蔽IRI图中的共价键区域

若只想观察弱相互作用，可在Multiwfn做完IRI分析后选择选项9 "Screen out covalent bond regions"，将sign(λ2)ρ小于-0.1 a.u.的区域IRI值设为100，从而使成键区域在等值面图中消失。
- 功能选项：9 (需2024-Mar-29及以后版本)
- 阈值：-0.1 a.u.

---

## 10. 绘制IRI平面填色图

使用Multiwfn绘制IRI平面填色图需载入波函数文件，依次选择主功能4（绘制平面图）、24（IRI）、1（填色图），设置平面范围和坐标（如XY平面Z=0）。作图时可设置显示键、调整色彩刻度下限和上限（如-1到2）以及色彩变化方式（如Reversed rainbow）来优化显示。
- 示例设置：XY平面, Z=0, 色彩刻度 -1~2

---

## 11. 周期性体系IRI分析流程

使用CP2K产生molden文件并手动添加晶胞信息后，在Multiwfn中载入该文件。进入主功能20选择4（IRI分析），利用选项9基于晶胞平移矢量定义格点，设置合适的盒子大小（如X、Y方向自动，Z方向取16 Bohr）和格点间距（如0.15）。导出cube文件后用VMD的IRIfill.vmd脚本绘图。
- 格点间距示例：0.15
- 脚本：IRIfill.vmd

---

## 12. VMD中优化周期性体系IRI图显示

在VMD中加载周期性体系IRI图后，可输入`pbc box`显示盒子边框。若默认等值面不合适，可在Graphics - Representation中调整Isovalue（如改为0.7）。开启Display - Depth cueing并设置Cue Mode为Linear、Cue Start和End分别为1.75和2.50可增加图像层次感。
- 调整参数：Isovalue=0.7, Cue Start=1.75, Cue End=2.50

---

## 13. IRI-π函数定义与着色方式

IRI-π是专门展现π相互作用的变体，相当于计算IRI时只考虑π电子。由于与位阻无关，IRI-π等值面根据电子密度ρ着色即可，无需使用sign(λ2)ρ。乙烯（一套π）和乙炔（两套π）的IRI-π等值面形状显著不同，可据此判断π作用类型。
- 参考文献：Theor. Chem. Acc. 139, 25 (2020) https://doi.org/10.1007/s00214-019-2541-z

---

## 14. IRI-π分析π作用强弱

IRI-π等值面的颜色和形状可用于判断π作用强弱。例如在噻吩中，Cα-Cβ键的等值面颜色更蓝或延伸得更接近原子核，表明其π作用强于Cβ-Cβ键。对IRI-π进行盆分析和拓扑分析可获得极小点位置的具体数值，从而定量比较π作用强度。
- 应用实例：噻吩, 18碳环 (cyclo[18]carbon)
