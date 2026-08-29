---
id: 517
title: 将Gaussian等程序收敛的波函数作为ORCA的初猜波函数的方法
domain: 其他量化软件
topic: Gaussian波函数转ORCA初猜
cards: 12
---

## 1. ORCA与其他程序的SCF收敛性对比
ORCA在SCF收敛方面不如Gaussian成熟，Gaussian能收敛的情况ORCA往往难以收敛。Gaussian在产生初猜波函数方面更灵活，支持片段组合波函数和stable=opt自动优化稳定波函数。虽然ORCA也能通过%SCF FlipSpin计算自旋极化单重态，但不如Gaussian方便。若能将Gaussian等程序收敛的波函数作为ORCA的初猜，可以弥补ORCA的SCF收敛短板。

---

## 2. 利用Multiwfn转换波函数为ORCA初猜的原理
Multiwfn支持载入.fch、.molden、GAMESS-US/Firefly输出文件，并从2019-Oct-10版本起支持导出.mkl文件。.mkl文件是老版本Molekel的输入文件格式，可被ORCA自带的orca_2mkl工具转换为.gbw文件。ORCA计算时可以从.gbw文件中读取轨道作为初猜波函数，从而利用其他程序收敛的波函数。

---

## 3. 基函数类型的一致性要求
ORCA是基于球谐型高斯函数进行计算的，因此为了让转换后的波函数能被ORCA正确使用，其它程序（如Gaussian）计算时也应当使用球谐型高斯函数。例如Gaussian使用def2-SVP基组时默认即为球谐型，但使用Pople基组如6-31G(d)时默认是笛卡尔型，需注意相关设置。

---

## 4. 使用Multiwfn将Gaussian波函数转换为ORCA初猜的步骤
首先使用Gaussian进行计算生成.chk文件，用formchk将其转换为.fch文件。载入.fch文件进入Multiwfn，依次输入100（其它功能）、2（导出文件）、9（导出mkl文件），输入文件名并确认是给ORCA使用。然后在命令行运行`orca_2mkl C4H8 -gbw`（假设文件名为C4H8.mkl）即可生成ORCA可读取的.gbw文件。

---

## 5. ORCA读取外部.gbw文件作为初猜的方法
将生成的.gbw文件与ORCA输入文件放在同一目录下，且文件名需与ORCA输入文件主文件名一致，ORCA即会自动读取。如果文件名不一致，需在ORCA输入文件中使用moread关键词，并添加`%moinp "文件路径/文件名.gbw"`来指明.gbw文件的位置。

---

## 6. Gaussian与ORCA计算中基组的一致性
确保Gaussian中使用的基组与ORCA中精确一致，特别要注意基函数类型的差异。Gaussian使用6-31G系列基组时默认使用笛卡尔型d基函数（5d/6d问题），而ORCA总是使用球谐型基函数。若使用Pople系列基组，Gaussian计算时需加上5d关键词以匹配ORCA的球谐型定义，尽管ORCA用户很少使用此类基组。

---

## 7. Gaussian与ORCA计算中分子坐标的一致性
Gaussian计算时会自动将分子朝向调整为标准朝向，导致.chk文件中的坐标与输入文件坐标可能不同。为了保证ORCA能正确读取波函数，应使ORCA输入文件中的坐标与Gaussian输出文件中的标准朝向坐标一致，或在Gaussian计算时加上nosymm关键词禁止重新定向。

---

## 8. 避免Gaussian自动删除基组原始函数的设置
Gaussian为节约时间，会自动去掉部分广义收缩基组（如Dunning基组、ANO基组、部分元素的6-311G基组）中重复指数的原始高斯函数及收缩系数极小的函数。由于ORCA不做此处理，这可能导致波函数转换后无法收敛，应在Gaussian计算时加入int=NoBasisTransform关键词以保留所有原始基组定义。

---

## 9. 避免Gaussian自动处理线性依赖基函数的设置
建议在Gaussian计算时带上IOp(3/32=2)关键词，尤其是在使用弥散函数时。该设置可以避免Gaussian自动去除线性依赖的基函数，从而确保Gaussian和ORCA计算所使用的基函数严格一致，提高波函数转换后的收敛成功率。

---

## 10. DFT计算积分格点对收敛的影响
对于DFT计算，如果基组、坐标和基函数定义都已一致但ORCA仍不收敛，可以尝试提高Gaussian和ORCA计算时的DFT积分格点精度。同时在ORCA计算中关闭RI（Resolution of Identity）近似，这有助于改善收敛性。

---

## 11. 批量转换chk为gbw的脚本功能
chk2gbw.sh是一个bash脚本，可批量将当前目录下的.chk文件转换为.gbw文件。脚本会自动调用formchk、Multiwfn和orca_2mkl工具，转换后的.gbw文件后缀会加上_Gau（如popipa.chk变为popipa_Gau.gbw）。同时脚本会生成对应的ORCA输入文件（.inp），其中已包含moread关键词和%moinp设置，坐标直接对应于chk文件。

---

## 12. 批量转换gbw为chk的脚本功能
从2020年8月21日更新的Multiwfn开始，在examples\scripts目录下提供了gbw2chk.sh脚本。运行该脚本可以将当前目录下的所有.gbw文件转换为同名的.chk文件，以便在Gaussian中使用guess=read关键词读取波函数作为初猜。对于UHF/UKS计算得到的波函数，必须使用2021年10月1日及以后更新的Multiwfn版本。
