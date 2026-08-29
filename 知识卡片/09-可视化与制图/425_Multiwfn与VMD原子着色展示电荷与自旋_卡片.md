---
id: 425
title: 使用Multiwfn+VMD以原子着色方式表现原子电荷、自旋布居、电荷转移、简缩福井函数
url: http://sobereva.com/425
domain: 可视化与制图
topic: Multiwfn与VMD原子着色展示电荷与自旋
cards: 11
---
## 1. 使用Multiwfn将原子电荷导出为VMD可用格式

Multiwfn程序主功能7在计算完原子电荷后可以导出.chg格式的文件，它和常见的.xyz格式的唯一区别是每个原子后面增加了一列用于记录原子电荷。对于2018年6月3日及以后更新的Multiwfn程序，如果以.chg文件作为输入文件，那么在主功能100的子功能2当中可以导出.pqr格式。.pqr格式和pdb格式关键差异在于多增加了两列，一列记录原子电荷，另一列记录原子半径，该文件可以直接载入到VMD程序中并根据原子电荷值着色。
- 文献出处：http://原作者.com/425

---



---

## 2. VMD中原子着色的基础设置步骤

启动VMD载入.pqr文件后，进入Graphics - Representation，将Coloring Method设为Charge（按照原子电荷那一列着色），Drawing Method设为VDW。为了改进图像效果，建议关闭坐标轴（Display-Axes-Off），将背景设为白色（在命令行输入color Display Background white），将Coloring Method改为BWR（蓝-白-红），将Sphere Scale设为0.5，Material设为Glossy，并在Trajectory标签页设定对称的色彩刻度范围（如-0.15和0.15）。
- 文献出处：http://原作者.com/425

---



---

## 3. VMD中添加键连显示和渲染设置

在VMD的Representation界面里点击Create Rep，将新Rep的Coloring Method设Color ID（选32 orange），Material设AOEdgy，Drawing Method设DynamicBonds，Distance Cutoff设3.6，Bond Radius设0.2。确保开启GLSL（Display-Rendermode-GLSL）以充分展现效果，若需更好效果可使用内置的Tachyon渲染器进行渲染。
- 文献出处：http://原作者.com/425

---



---

## 4. 展现Au20团簇ADCH电荷的操作流程

使用Multiwfn载入Au20.fch，依次选择主功能7（布居分析）、子功能11（ADCH电荷）、选项1（使用内置的球对称化密度计算ADCH电荷）。计算完成后在当前目录导出Au20.chg文件，重启Multiwfn载入此.chg文件，进入主功能100的子功能2，选择选项1输出Au20.pqr文件。该文件倒数第一列是原子的Bondi范德华半径，倒数第二列是ADCH原子电荷。
- 文献出处：http://原作者.com/425

---



---

## 5. 手动构建原子自旋布居的.chg文件

启动Multiwfn载入C4H8.fch，依次选择主功能15（模糊空间分析）、子功能1（对原子空间积分）、子功能5（积分自旋密度），计算后将屏幕输出的自旋布居数值拷出。进入主功能100的子功能2导出.xyz文件，去掉开头两行，利用文本编辑器的列模式将自旋布居值粘贴到最后一列，将后缀改为.chg。由于xyz和chg是自由格式而pqr是固定格式，手动编辑得到chg文件再转换成pqr更为方便。
- 文献出处：http://原作者.com/425

---



---

## 6. 同时展示元素类型和原子属性值的VMD设置

在VMD中建立两个Rep以同时展示元素和原子属性值：第一个Rep用Charge着色，VDW风格显示，材质设Transparent，Sphere Scale设0.3；第二个Rep用Name着色，Licorice风格显示，材质用Opaque。进入Graphics-Material，把Transparent的Opacity设为0.7以降低透明度，这样元素和原子的自旋布居大小可同时展现且互不干扰。
- 文献出处：http://原作者.com/425

---



---

## 7. 单体原子电荷计算中nosymm关键词的使用

在分析二聚体（如鸟嘌呤-胞嘧啶碱基对）的静电相互作用时，应使用单体原本的电荷分布，因此需将G、C坐标从xyz文件中提取并分别计算。在编写Gaussian输入文件.gjf时，关键词必须使用# M062X/6-311G** nosymm。若不加nosymm，Gaussian会自动平移和旋转体系坐标到标准朝向，导致单体fch文件里的坐标与复合物不同，影响后续绘图。
- 文献出处：http://原作者.com/425

---



---

## 8. 计算二聚体形成时原子电荷变化的方法

为了考察形成二聚体时各个原子电荷的变化，需要计算二聚体状态的原子电荷与单体的原子电荷的差值。由于ADCH电荷的Hirshfeld权重函数过于平滑、随径向距离收敛太慢，计算电荷变化不太理想，建议改用权重函数收敛更快的原子偶极矩校正的Becke电荷（Multiwfn主功能7子功能10）。将GC、G、C的原子电荷拷入Excel，计算GC电荷减去G和C电荷的变化量，替换进.chg文件并转换为.pqr文件进行作图。
- 文献出处：http://原作者.com/425

---



---

## 9. 计算简缩福井函数f-的数据准备

计算简缩福井函数f-时，需要对N电子和N-1电子状态的fch文件都计算Hirshfeld原子电荷（因Hirshfeld电荷相对较适合讨论反应位点问题）。将N和N-1态的原子电荷放入Excel，令N-1态的原子电荷减去N态的原子电荷，即得到简缩福井函数f-。将此数值写入对应体系的.chg文件最后一列，再转换为.pqr文件供VMD使用。
- 文献出处：http://原作者.com/425；http://www.whxb.pku.edu.cn/CN/abstract/abstract28694.shtml

---



---

## 10. 简缩福井函数f-的图像解读

使用VMD对 coronene.pqr 作图，以CPK显示，色彩刻度设为-0.07~0.07，色彩变化用BWR。图中越红的原子，拥有越大的简缩福井函数f-，因此越容易发生亲电反应。该图与f-等值面图及把f-投影到分子表面上的图传达的信息相同。
- 文献出处：http://原作者.com/425

---



---

## 11. 原子着色方法的适用范围扩展

该原子着色表现原子属性的做法具有普适性，不仅限于原子电荷、自旋布居和简缩福井函数。还可用于表现原子跃迁电荷、原子对分子轨道（或NTO）的贡献、原子对空穴/电子分布的贡献、原子偶极矩的大小、原子的电子动能、原子的源函数值、原子的简缩双描述符、电子激发前后电荷的变化、外加电场前后电荷的变化，以及其他程序计算的原子极化率、原子受力大小等。
- 文献出处：http://原作者.com/425
