---
key: b542
title: 在ORCA中做counterpoise校正并计算分子间结合能的例子
url: http://sobereva.com/542
domain: 其他量化软件
source: blog
year: 2020
cards: 9
---

# 在ORCA中做counterpoise校正并计算分子间结合能的例子 — 知识卡片

## 1. ORCA程序中的Counterpoise校正实现方式

ORCA程序（以4.2.1版为例）未提供像Gaussian那样现成的counterpoise关键词，只能通过定义鬼原子的方式手工实现。使用Multiwfn程序生成ORCA输入文件可以简化此过程，其中包含对鬼原子的定义和不同计算任务的设置。

---

## 2. 分子间结合能与相互作用能的区别

按照特定例子计算得出的是复合物结构中单体间的相互作用能。一般意义的结合能计算需考虑单体形成复合物过程中的变形能，在单体为刚性时变形能可忽略，此时相互作用能可视作结合能。

---

## 3. 使用Multiwfn生成ORCA的Counterpoise输入文件步骤

启动Multiwfn并载入复合物结构文件，在主功能0中查询并确认两个单体的原子序号范围。依次输入相关指令选择生成ORCA输入文件、任务类型为考虑counterpoise校正的结合能、输入两个片段的序号范围、添加弥散函数及设定计算方法（如DLPNO-CCSD(T)）。

---

## 4. ORCA Counterpoise输入文件的内容结构

生成的输入文件包含三个单点任务：第一个任务计算二聚体能(E_AB)，第二个任务计算第1个片段在二聚体基组下的能量(E_A(AB))，第三个任务计算第2个片段在二聚体基组下的能量(E_B(AB))。原子名后带冒号表示该原子为鬼原子，nproc只需在开头定义一次。

---

## 5. Counterpoise校正结合能的计算公式

在输出文件中搜索"FINAL SINGLE POINT ENERGY"获取三个能量值E_AB、E_A(AB)和E_B(AB)。Counterpoise校正后的结合能计算公式为：E_bind = E_AB - E_A(AB) - E_B(AB)。

---

## 6. 实例计算结果与精度验证

对于示例体系（S66弱相互作用测试集中的体系），在DLPNO-CCSD(T)/aug-cc-pVTZ with normalPNO级别下计算得到的Counterpoise校正结合能为-2.13 kcal/mol。此结果与S66文献中CCSD(T)/CBS金标准结果-2.40 kcal/mol符合良好。

---

## 7. 自动提取结合能的脚本使用

文件包中的getEbind.sh脚本可自动处理当前目录下的所有out文件，提取整体和两个片段的能量并计算差值。脚本输出包含Hartree、kcal/mol和kJ/mol单位的结合能，方便批量处理数据。

---

## 8. Multiwfn扩展的完整Counterpoise计算功能

从2022-Jan-9更新的Multiwfn版本开始，生成ORCA输入文件时可选择任务类型-7。此时产生的输入文件会计算5个能量：整体能量、整体基组下片段1能量、整体基组下片段2能量、片段1自身能量、片段2自身能量。

---

## 9. 使用ORCA_CP.sh脚本处理完整Counterpoise输出

ORCA_CP.sh脚本可处理任务类型-7生成的输出文件，输出内容包括：5个能量的具体数值、原始相互作用能、BSSE校正后的相互作用能、BSSE校正能以及BSSE校正后的整体能量。该计算过程和脚本输出信息与Gaussian程序的counterpoise关键词完全一致。
