---
id: 115
title: AMBER程序支持的力场一览
url: http://sobereva.com/115
domain: 分子动力学与力场
topic: AMBER程序支持的力场版本及特点
cards: 25
---
## 1. AMBER力场概述

AMBER全称为Assisted Model Building with Energy Refinement，主要适合蛋白和核酸的凝聚相模拟，对有机小分子支持较少。该力场函数形式简单，后期版本均采用RESP电荷，计算RESP电荷的最佳工具是Multiwfn。计算RESP电荷的方法可参考《RESP拟合静电势电荷的原理以及在Multiwfn中的计算》（http://原作者.com/441）。

---

## 2. ff10力场

ff10力场对应文件parm10.dat，是对ff99各种参数补丁的集合，内容相当于parm99.dat+frcmod.ff03+bsc0+chi.OL3+新的离子参数+原子和残基名的修改。该版本修改原子和残基名以顺应PDB format version 3，被认为是目前最好的amber力场。

---

## 3. ff03.r1力场

ff03.r1力场由文件parm99.dat+frcmod.ff03定义，是ff99力场的修改版。获取电荷时通过连续介电模型表现溶剂可极化效应，并修改了蛋白phi、psi骨架参数，减少了对螺旋构象的偏爱，其核酸参数相对于ff99没变。

---

## 4. ff03与ff03.r1的区别

ff03.r1与amber9中的ff03略有不同，amber9时代的ff03仍使用ff94的方法得来的碳、氮端基原子电荷。如果用户仍想使用那个时代的ff03，需要调用oldff/leaprc.ff03。

---

## 5. ff03ua力场

ff03ua力场由文件parm99.dat+frcmod.ff03+frcmod.ff03ua定义，是ff03力场的united-atom版本。该版本将侧链的氢原子进行了合并，但骨架上的氢原子和芳香环上的氢原子仍被保留；骨架势参数不变，侧链参数因使用united原子而重新拟合，核酸参数完全没变且仍为全原子。

---

## 6. ff02力场

ff02力场由文件parm99.dat+frcmod.ff02pol.r1定义，是ff99力场的可极化版。该版本给原子上增加了可极化的偶极子，其中frcmod.ff02pol.r1是对原ff02的扭转参数的修正。

---

## 7. ff02EP力场

ff02EP力场由文件parm99EP.dat+frcmod.ff02pol.r1定义，是在ff02力场基础上给诸如氧、氮、硫原子增加了偏离原子中心的点电荷。这种修改旨在表现孤对电子效应，据称比ff02稍好一点。

---

## 8. ff99力场

ff99力场对应文件parm99.dat，大部分参数来自ff94力场，修改了许多扭转角的参数。该力场存在甘氨酸骨架参数问题，螺旋和延展构象的平衡性不对；对于DNA，长时间模拟中亚稳态占统治地位，即alpha和gamma二面角倾向于分别为gauche+和trans状态，这些问题在ff94里也存在。

---

## 9. ff99SB力场

ff99SB力场由文件parm99.dat+frcmod.ff99SB定义，是对ff99的蛋白二面角参数进行修正的版本。该修正改善了二级结构间分布的比例，同时也解决了甘氨酸骨架参数问题。

---

## 10. bsc0补丁

bsc0补丁对应文件frcmod.parmbsc0，用于解决ff99在核酸模拟中的问题，同时还改进了RNA的糖苷的gamma二面角扭转势。具体内容可参考http://mmb.pcb.ub.es/PARMBSC0。

---

## 11. ff99SB+bsc0组合力场

ff99SB+bsc0组合力场是将bsc0补丁用到ff99SB上，相对于ff99同时增进对蛋白和核酸的效果。这个组合会导致gamma二面角过分偏离trans型，因此如果初始结构有很多gamma角为trans的情况，建议使用ff99。

---

## 12. ff99SBildn补丁

ff99SBildn补丁对应文件frcmod.ff99SBildn，是在ff99SB基础上修改氨基酸侧链参数的补丁。

---

## 13. ff99SBnmr补丁

ff99SBnmr补丁对应文件frcmod.ff99SBnmr，是在ff99SB基础上修改骨架扭转项参数的补丁，旨在使其更符合NMR数据。

---

## 14. ff98力场

ff98力场对应文件parm98.dat，是对ff94改进了糖苷的扭转角参数的版本。

---

## 15. ff96力场

ff96力场对应文件parm96.dat，来自Beachy et al，其扭转角与ff94不同，计算出来的能量更接近量化结果。由于构象有明显偏向beta等问题，该力场使用不广泛。

---

## 16. ff94力场

ff94力场对应文件parm94.dat，来自Cornell, Kollman et al，适合溶剂环境。其电荷由RESP HF/6-31G*获得。

---

## 17. ff86力场

ff86力场对应文件parm91X.dat，是将ff84扩展为全原子力场的版本。它和ff84一样对氢键使用Lennard-Jones 10-12势，因此如果想在sander里用ff84/86，必须重新带着-DHAS_10_12选项编译。文件名parm91X是因为对原始ff86做了一些修正。

---

## 18. parm91X.dat文件说明

parm91X.dat是parm91.dat的补完版，加入了一些非键项。但其中的非键项参数（如Mg、I等）都没调好，只是近似值。

---

## 19. ff84力场

ff84力场对应文件parm91X.ua.dat，是最早的AMBER力场，属于用于模拟核酸和蛋白质的联合原子力场。该力场不推荐使用，但在真空或者距离依赖的介电常数下模拟还有用。

---

## 20. parmAM1和parmPM3力场

parmAM1和parmPM3力场对应文件parmAM1.dat/parmPM3.dat，使用这些参数对蛋白质优化可以得出与AM1/PM3相同的优化结果，目前已没什么价值。

---

## 21. GAFF力场

GAFF力场全称为Generation Amber Force Field，对应文件gaff.dat，是普适型有机小分子力场。其函数形式和AMBER力场相同，与AMBER力场完全兼容。

---

## 22. GLYCAM-06力场

GLYCAM-06力场对应文件GLYCAM_06g.dat，是对以前GLYCAM力场做了改进的版本，并且纳入了一小部分脂类的参数。

---

## 23. GLYCAM-04EP力场

GLYCAM-04EP力场对应文件GLYCAM04EP.dat，是将GLYCAM04扩展到可用于TIP5P模型下的模拟。该版本给氧加上非原子中心点电荷以表现孤对电子效应。

---

## 24. GLYCAM-04力场

GLYCAM-04力场对应文件GLYCAM04.dat，全称为glycans and glycoconjugates in AMBER，专用于糖的模拟。它和AMBER完全兼容，可一起用于糖蛋白的模拟，官网为http://glycam.ccrc.uga.edu/ccrc/index.jsp。

---

## 25. 其他支持的力场

Amber程序还支持AMOEBA力场，也可以通过自带的CHAMBER工具来支持CHARMM力场。
