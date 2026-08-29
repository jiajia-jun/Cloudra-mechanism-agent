---
id: 542
title: 在ORCA中做counterpoise校正并计算分子间结合能的例子
url: http://sobereva.com/542
domain: 其他量化软件
topic: ORCA中利用Multiwfn做BSSE校正
cards: 11
---
## 1. ORCA程序实现counterpoise校正的方式

ORCA程序（截至4.2.1版）没有提供现成的counterpoise关键词，只能通过定义鬼原子的方式手工实现，因此实现起来比Gaussian麻烦。在ORCA输入文件中，原子名后面带冒号说明这个原子是鬼原子。
- 来源：http://原作者.com/46
- 相关链接：http://原作者.com

---



---

## 2. Multiwfn生成ORCA的counterpoise校正输入文件

Multiwfn程序支持生成包含counterpoise校正任务的ORCA输入文件。用户载入结构文件并确定两个片段的原子序号范围后，在主功能菜单中选择生成ORCA输入文件功能，随后选择任务类型为考虑counterpoise校正的结合能，并输入片段序号、加弥散函数选项及计算方法即可自动生成。
- 相关链接：http://原作者.com/490, http://原作者.com/multiwfn, http://原作者.com/452

---



---

## 3. 示例体系的计算级别与结构获取

该示例体系是S66弱相互作用测试集中的一个结构，使用DLPNO-CCSD(T)/aug-cc-pVTZ with normalPNO级别计算其结合能并考虑counterpoise校正。相关的xyz格式结构文件、输入输出文件及处理脚本均可从指定链接下载。
- 相关链接：http://原作者.com/attach/542/file.rar

---



---

## 4. 使用Multiwfn确定单体片段原子序号

启动Multiwfn载入二聚体结构文件后，若不清楚两个单体的原子序号范围，可进入主功能0，选择Tools - Select fragment，输入其中一个片段中的任意一个原子序号，整个片段会被高亮并显示序号范围。
- 支持的输入文件格式见：http://原作者.com/379

---



---

## 5. 使用Multiwfn生成counterpoise输入文件的交互步骤

在Multiwfn中生成ORCA输入文件的具体交互命令序列为：输入`oi`并回车确认输出文件名，选择任务类型`0`，接着选择`7`（考虑counterpoise校正的结合能），依次输入两个片段的序号范围（如1-15和16-32），输入`-2`加弥散函数，最后输入`8`选择DLPNO-CCSD(T) with NormalPNO方法。

---

## 6. 生成的ORCA输入文件包含的任务内容

生成的输入文件包含DLPNO-CCSD(T)/aug-cc-pVTZ with normalPNO级别下的三个单点任务。第一个子任务计算二聚体能量E_AB；第二个子任务计算第1个片段在二聚体基组下的能量E_A(AB)，其中片段2的原子标记为鬼原子；第三个子任务计算第2个片段在二聚体基组下的能量E_B(AB)，其中片段1的原子标记为鬼原子。
- 输入文件中需将maxcore和nproc设为恰当值，nproc只需在开头定义一次

---

## 7. Counterpoise校正结合能的计算公式

在输出文件中搜索"FINAL SINGLE POINT ENERGY"获取E_AB、E_A(AB)和E_B(AB)三个能量值。考虑counterpoise校正的结合能计算公式为E_int(CP) = E_AB - E_A(AB) - E_B(AB)。
- 相关培训课件：http://www.keinsci.com/workshop/KBQC_content.html

---

## 8. 示例体系的计算结果与精度对比

在36核并行、每核6000MB内存的硬件环境下，示例任务耗时41分钟。计算得到的E_AB为-393.613585294163 Hartree，E_A(AB)为-196.197449643018 Hartree，E_B(AB)为-197.412738820804 Hartree。据此计算出的counterpoise校正结合能为-2.13 kcal/mol，与S66文中CCSD(T)/CBS金标准结果-2.40 kcal/mol符合得非常好。

---

## 9. 使用getEbind.sh脚本自动提取结合能

getEbind.sh脚本可处理当前目录下的所有out文件，自动提取整体和两个片段的能量，并计算差值给出不同单位的结合能。脚本输出信息包括Hartree、kcal/mol和kJ/mol单位的能量值。
- 脚本示例输出显示格式包含Etot, E1, E2及各单位的结合能

---

## 10. Multiwfn新增的完整counterpoise计算选项

从2022-Jan-9更新的Multiwfn开始，生成ORCA输入文件时可选择任务类型-7。此时生成的输入文件会计算5个能量：整体能量E(AB)、整体基函数下片段1能量E(A)_AB、整体基函数下片段2能量E(B)_AB、片段1自身能量E(A)、片段2自身能量E(B)。
- 该功能与Gaussian程序的counterpoise关键词完全相同

---

## 11. 使用ORCA_CP.sh脚本处理完整counterpoise输出

ORCA_CP.sh脚本用于处理包含5个能量计算的ORCA输出文件。该脚本会输出：(1)5个能量的具体数值；(2)原始的相互作用能；(3)BSSE校正后的相互作用能；(4)BSSE校正能；(5)BSSE校正后的整体的能量。
- 相关链接：http://原作者.com/46
