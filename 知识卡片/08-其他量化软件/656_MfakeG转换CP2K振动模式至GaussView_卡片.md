---
id: 656
title: 使CP2K计算的振动模式可以被GaussView观看的程序：MfakeG
url: http://sobereva.com/656
domain: 其他量化软件
topic: MfakeG转换CP2K振动模式至GaussView
cards: 5
---
## 1. MfakeG程序的功能与用途

MfakeG是一个工具，能够将CP2K程序计算得到的振动模式转换为GaussView可识别的格式，从而利用GaussView查看振动矢量、播放和保存振动动画以及沿特定振动模式对结构进行位移。该程序是原作者继OfakeG（将ORCA输出文件转化为Gaussian格式）之后编写的，旨在解决GaussView仅支持Gaussian程序振动分析输出文件的限制，同时利用了Molden格式简单通用的特点。MfakeG免费下载地址为 http://原作者.com/soft/MfakeG，提供Windows和Linux版。

---



---

## 2. CP2K输出Molden振动文件的设置方法

在CP2K的振动分析任务输入文件中，需在&VIBRATIONAL_ANALYSIS字段内加入特定内容以输出后缀为.mol的Molden文件，默认文件名为[项目名]-VIBRATIONS-1.mol。具体的输入设置如下：
&PRINT
&MOLDEN_VIB
&END MOLDEN_VIB
&END PRINT
如果使用Multiwfn生成CP2K输入文件（参考《使用Multiwfn非常便利地创建CP2K程序的输入文件》 http://原作者.com/587），默认也会产生此.mol文件。

---

## 3. MfakeG程序的基本使用方法

启动MfakeG程序后，输入CP2K生成的.mol文件的路径，程序会在相同目录下生成一个同名但带有-fake后缀的.out文件。将此生成的.out文件载入GaussView中，即可通过Results - Vibrations界面像查看Gaussian输出文件一样观看振动信息。MfakeG的工作原理是解析.mol文件中记录的元素、坐标、振动频率、描述振动矢量的正则坐标以及红外强度等字段，并将其转换为GaussView能够识别的伪Gaussian振动分析输出文件格式。

---

## 4. 在MfakeG中显示周期性体系晶胞边框的方法

对于CP2K通常计算的周期性体系，若要使GaussView显示出晶胞边框，需要自行编辑.mol文件并在文件第二行插入[Cell]字段。[Cell]字段下方应列出晶胞的三个矢量，单位为埃，格式示例如下：
[Cell]
19.25142628 0.00000000 0.00000000
-9.62562669 16.67336579 0.00000000
0.00000000 0.00000000 15.00000000
经过MfakeG转换后，伪Gaussian输出文件的原子坐标部分最后会多出三个原子信息，这三个原子对应于上述晶胞矢量。

---

## 5. MfakeG选择转换Molden格式的原因

作者原本计划直接转换CP2K的输出文件，但最终决定转换.mol格式是因为Molden格式比CP2K输出文件更简单且具有通用性。这种设计允许用户自行编写小程序，将任意其他计算化学程序进行振动分析得到的结果写成.mol格式，随后都可以借助MfakeG工具在GaussView中观看。MfakeG自带示例目录，其中的freq.inp是CP2K对GaN超胞做振动分析的输入文件，计算产生的freq-VIBRATIONS-1.mol经转换后生成的freq-VIBRATIONS-1_fake.out可在GaussView中呈现良好的可视化效果。
