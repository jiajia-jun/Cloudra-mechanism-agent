---
id: 485
title: Simulating UV-Vis and ECD spectra using ORCA and Multiwfn
url: http://sobereva.com/485
domain: 激发态与光谱
topic: ORCA与Multiwfn模拟UV-Vis和ECD光谱
cards: 11
---
## 1. 教程说明与环境配置

本教程演示使用ORCA和Multiwfn模拟水环境中丙氨酸的UV-Vis和ECD光谱，ORCA版本为4.1.1，Multiwfn版本为3.7(dev)。ORCA是免费量子化学程序，Multiwfn是基于波函数分析且能绘制光谱的代码，两者均支持Windows、Linux和MacOS平台。教程中所有涉及的文件可从http://www.keinsci.com下载，普通Intel四核CPU上的计算耗时预计少于10分钟。
- Multiwfn下载地址：http://原作者.com/multiwfn
- ORCA下载地址：https://orcaforum.kofo.mpg.de/app.php/portal

---



---

## 2. 基态几何优化生成输入文件

使用Multiwfn生成ORCA基态优化输入文件，启动Multiwfn后依次输入命令：initgeom.xyz、100、2、12、S0_opt.inp、-1、[回车选择水作为默认溶剂]、0、2、1。这选择了B97-3c方法和SMD溶剂模型，生成的S0_opt.inp需根据实际情况修改"nprocs"和"maxcore"参数。
- 对应命令行序列：100 -> 2 -> 12
- 优化方法：B97-3c
- 溶剂模型：SMD (水)

---

## 3. 运行基态几何优化

将生成的S0_opt.inp移至空文件夹，在控制台输入命令如 `D:\study\orca411\orca S0_opt.inp > S0_opt.out` 进行计算。计算完成后，输出文件显示优化在11步后收敛，当前文件夹下的S0_opt.xyz为优化后的几何结构，S0_opt.trj包含优化轨迹。
- 轨迹可视化工具推荐：VMD (http://www.ks.uiuc.edu/Research/vmd/)

---

## 4. 激发态计算输入文件生成

使用Multiwfn生成ORCA TDDFT计算输入文件，依次输入：100、2、12、TDDFT.inp、-1、[回车选择水]、22。这默认设定PBE0/def2-SV(P)级别和RI加速技术及计算10个最低激发态("nroots 10")。由于体系较小，建议将输入文件中的基组"def2-SV(P)"替换为更高质量的"def2-TZVP(-f)"。
- 推荐泛函：PBE0 (对于小分子)
- 推荐基组：def2-TZVP(-f)
- 激发态数量：10

---

## 5. 运行激发态计算

执行命令如 `D:\study\orca411\orca TDDFT.inp > TDDFT.out` 进行TDDFT计算。对于原子数较多的体系，应增加"nroots"的值以确保模拟光谱能覆盖感兴趣的波长范围（如>250nm）。
- 适用场景：对于具有强电荷转移特征的大共轭体系，建议使用CAM-B3LYP或wB97XD泛函。

---

## 6. 使用Multiwfn模拟UV-Vis光谱

启动Multiwfn并加载TDDFT.out文件，依次输入：11、3、0。Multiwfn会读取输出文件中的"ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS"部分的激发能和振子强度来绘制UV-Vis光谱。
- 操作路径：主功能 11 -> 3 -> 0
- 数据来源：激发能和振子强度

---

## 7. ORCA输出文件编码问题解决

若Multiwfn在进入绘图界面前崩溃，可能是ORCA输出文件为Unicode编码，而Multiwfn仅支持ASCII编码。解决方法请参考链接：http://原作者.com/wfnbbs/viewtopic.php?id=213。
- 编码要求：ASCII

---

## 8. 使用Multiwfn模拟ECD光谱

在Multiwfn中输入：-3、11、4、0。Multiwfn将基于ORCA TDDFT输出文件中的激发能和旋转强度来绘制ECD光谱。
- 操作路径：-3 -> 11 -> 4 -> 0
- 数据来源：激发能和旋转强度

---

## 9. 溶剂模型的使用建议

对于大多数中性体系，几何优化可不使用溶剂模型以节省时间；但对于具有明显离子特征的区域（如水环境中的丙氨酸），优化阶段也应使用溶剂模型。激发态计算应始终使用溶剂模型以模拟真实环境，特别是在极性溶剂中其对电子激发影响较大。
- 优化阶段：离子体系必须使用溶剂模型
- 激发态阶段：必须使用溶剂模型

---

## 10. 构象对ECD光谱的影响及处理

ECD光谱对构象非常敏感，若分子在室温下存在多个热力学可及构象（通常指含可旋转键的柔性分子），应对每个构象进行优化和自由能计算。利用玻尔兹曼关系估算出现百分比，对概率高于阈值（如5%）的构象进行电子激发计算，最后使用Multiwfn绘制构象平均ECD光谱（参见手册Section 4.11.4）。
- 参考章节：Multiwfn手册 4.11.4
- 概率阈值：例如 5%

---

## 11. 辅助工具推荐

使用Molclus代码可获取高柔性分子的所有可能构象，其官网为http://www.keinsci.com/research/molclus.html。Multiwfn手册Section 4.A.12提供了表征和理解电子激发性质的众多功能。ORCA与Multiwfn结合使用的视频教程链接：https://youtu.be/tiTmTbtbtig。
- 构象搜索工具：Molclus
- 激发性质分析：Multiwfn手册 4.A.12
