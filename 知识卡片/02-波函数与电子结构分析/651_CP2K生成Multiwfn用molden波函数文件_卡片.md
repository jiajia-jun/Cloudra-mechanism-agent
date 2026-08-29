---
id: 651
title: 详谈使用CP2K产生给Multiwfn用的molden格式的波函数文件
domain: 波函数与电子结构分析
topic: CP2K生成Multiwfn用molden波函数文件
cards: 16
---

## 1. 在CP2K中开启Molden文件输出
在CP2K输入文件的&DFT字段中加入PRINT和MO_MOLDEN模块，并设置NDIGITS参数，可以在SCF收敛后在当前目录下产生.molden为后缀的文件。代码示例为 &PRINT &MO_MOLDEN NDIGITS 9 &END MO_MOLDEN &END PRINT。其中NDIGITS控制输出的轨道展开系数，上例要求绝对值大于1E-9的展开系数才会被输出，NDIGITS 9对于波函数分析的目的足够精确了。

---

## 2. CP2K输出Molden文件的限制
对任何CP2K支持的半经验级别的方法，如GFN1-xTB、PM6、DFTB，CP2K都无法产生molden文件。考虑k点时也无法产生molden文件，因此晶胞必须足够大，不够大就需要扩成超胞来算。

---

## 3. 控制Molden文件输出频率
对于MD等涉及结构变化的任务，加入输出molden文件的设置后，默认每一步都输出一个molden文件，可以通过&MO_MOLDEN中的&EACH子字段控制对各种任务输出molden文件的频率。利用这个特征，可以令分子动力学模拟过程中不断产生molden文件，然后写脚本批量调用Multiwfn做波函数分析。

---

## 4. 向Molden文件添加盒子信息方法一
从CP2K 2026.2版本开始，在&MO_MOLDEN里加入WRITE_CELL T，这样CP2K就会在molden文件里写入[Cell]字段，默认以Bohr为单位。这是Multiwfn载入molden文件时获得盒子信息的推荐方法。

---

## 5. 向Molden文件添加盒子信息方法二
用文本编辑器打开molden文件，在开头部分插入[Cell]字段，里面通过三行来分别定义盒子的三个平移矢量的X、Y、Z分量（以埃为单位），或者通过一行定义盒子的三个边长(a,b,c)和夹角(α,β,γ)。如果不想修改molden文件，可以在当前目录下创建一个叫[Cell].txt的文件，Multiwfn载入时会询问是否从该资料件读取。

---

## 6. 向Molden文件添加有效核电荷数方法一
从2026.2版本开始，在&MO_MOLDEN里加入WRITE_PSEUDO T，这样CP2K就会在molden文件里写入[Pseudo]字段，记录各个原子的实际价电子数。这是让Multiwfn在载入molden文件时得知实际价电子数的推荐方法。

---

## 7. 向Molden文件添加有效核电荷数方法二
用文本编辑器打开molden文件并手动修改，可以将[Atoms]字段里每个原子的第三列改为其有效核电荷数，或者在头部插入[Nval]字段记录各种元素的有效核电荷数。在当前用的赝势下，各种元素的有效核电荷数可以去看基组定义，例如在BASIS_MOLOPT文件中q后面的数字。

---

## 8. 合并添加盒子信息和核电荷数
在计算是在远程服务器上进行且编辑molden文件不方便时，可以在本机写一个包含[Cell]和[Nval]字段的文该资料件。上传后运行cat add.txt org.molden > final.molden，就把[Cell]和[Nval]字段加入到原先的org.molden文件开头，得到了可以用于Multiwfn做分析的final.molden。

---

## 9. CP2K输出空轨道的设置
对于使用对角化做SCF的情况，在&SCF里写ADDED_MOS N就会把最低N个空轨道也计算并输出到molden文件里。而OT则不兼容ADDED_MOS关键词。注意Multiwfn内部要求基函数数目与轨道数目是相等的，如果molden文件只记录了部分轨道信息，载入Multiwfn后其余轨道系数、占据数、能量都为0。

---

## 10. OT计算获取轨道能量的方法一
基于OT收敛的波函数做对角化：先做一次OT计算得到记录收敛波函数的wfn文件，再用相同设定做一次对角化的单点计算，从wfn中读取之前收敛的波函数做初猜。此时往往只需要一轮或很少几轮SCF迭代就可以完成，得到的molden文件里就有轨道能量信息了。

---

## 11. OT计算获取轨道能量的方法二
让Multiwfn读取输出文件里的轨道能量：用OT时要求CP2K把轨道能量计算出来并输出到输出文件里，然后用Multiwfn载入molden文件后，在主菜单里输入cp、7，并输入CP2K输出文件的路径。CP2K可通过&MO或&MO_CUBES模块将轨道能量输出到输出文件。

---

## 12. CP2K输出全部轨道能量的设置
在&DFT/&PRINT字段中加入&MO ENERGIES T OCCUPATION_NUMBERS T &END MO，SCF收敛后会输出全部求解出的轨道能量，用对角化时如果用了ADDED_MOS还会输出空轨道能量。

---

## 13. CP2K输出部分空轨道能量的设置
在&DFT/&PRINT字段中加入&MO_CUBES NHOMO 1 NLUMO 3 WRITE_CUBE F &END MO_CUBES，SCF收敛后会显示所有占据轨道能量和最低指定个数的空轨道能量。即便对于SCF过程中无法求解空轨道的OT也可以用这种方法得到空轨道能量，但无法用Multiwfn对空轨道部分绘制PDOS。

---

## 14. 检查Molden文件是否包含轨道能量
把molden文件载入Multiwfn后，进入主功能0，左上角选择Orbital info. - Show occupied orbitals，从文本窗口里显示的能量上就能判断；如果当前不方便进入图形界面，也可以进入主功能6的子功能3查看。

---

## 15. Multiwfn分析时的基组选择
CP2K用户通常使用MOLOPT系列赝势基组，但对于实空间函数的分析（如AIM、IGMH等），如果体系很大且CPU不给力，用MOLOPT系列耗时很高，建议使用TZVP-GTH或TZV2P-GTH赝势基组。如果想用全电子基组，pob-TZVP是很好的选择。

---

## 16. 对弥散函数敏感的分析的基组选择
Multiwfn支持的分析中有一部分在原理上不兼容弥散函数，如Mulliken分析、SCPA分析、Pipek-Mezey轨道定域化。这些分析不适合用DZVP-GTH、TZVP-GTH这样的基组，建议用pob-TZVP或者MOLOPT-SR-GTH系列基组。
