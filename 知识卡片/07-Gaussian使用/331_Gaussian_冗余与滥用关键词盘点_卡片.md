---
id: 331
title: 常见的多余的和被滥用的Gaussian关键词
domain: Gaussian使用
topic: Gaussian_冗余与滥用关键词盘点
cards: 29
---

## 1.
达到同一个计算目的，用的关键词越少，通常体现经验越丰富；计算化学输入文件应遵循“如无必要，勿增关键词”的原则。

---

## 2. 冗余关键词scf=maxcyc与opt=maxcyc
使用scf=maxcyc=几百或opt=maxcyc=几百通常是无用且有害的，解决SCF不收敛或几何优化收敛问题应当采用科学的方法而非盲目增加循环次数。

---

## 3. 冗余关键词freq=noraman
Gaussian仅对于HF方法做振动分析时才默认计算Raman活性，对于其他理论方法默认根本不计算Raman，此时写freq=noraman纯属多余。

---

## 4. 滥用IOp(5/13=1)
IOp(5/13=1)是一种饮鸩止渴、掩耳盗铃的逃避（而不是解决）SCF不收敛的方法，官方也明确表态使用该选项是愚蠢的。

---

## 5. scrf关键词下的模型选择冗余
Gaussian里scrf默认就用PCM（等价于IEFPCM），写PCM或IEFPCM纯属多余；除非有特殊理由，否则应优先使用SMD模型计算溶解自由能和体系自由能，而非盲目使用CPCM。

---

## 6. 滥用nosymm关键词
不应在不需要的时候使用nosymm关键词，只有在特定情况下才需要使用该选项，具体使用场景需参考关于对称性与nosymm使用的专门文章。

---

## 7. 冗余关键词scf=tight
从Gaussian 09开始，SCF收敛限默认就是tight，再写scf=tight毫无意义。

---

## 8. 积分格点设定的冗余与误区
HF、半经验、后HF等方法根本不涉及积分格点，设int=fine或ultrafine纯属多余；G09对DFT默认是int=fine，G16默认是int=ultrafine，无需重复书写；仅明尼苏达系列泛函（如M06HF、M06-2X）对积分格点敏感，其它泛函（如B3LYP）用fine格点已足够。

---

## 9. 无用关键词test与sp
test关键词根本毫无意义；sp代表做单点计算，这是默认行为，写sp纯属多余。

---

## 10. 方法名前缀U与R的冗余
自旋多重度为1时默认是R（限制性闭壳层），自旋多重度大于1时默认是U（非限制性开壳层），平时无需专门写；仅计算自旋极化单重态时才有必要明确写U。

---

## 11. 激发态计算关键词root与自旋态关键词
CIS、TD计算默认就是root=1，关注第一激发态时无需写root=1；singlet、triplet、50-50关键词仅对闭壳层参考态有意义，对非限制性开壳层参考态不起作用，此时需根据输出的<S**2>确定自旋多重度。

---

## 12. 冗余关键词freq=numer
freq=numer基于一阶解析导数做有限差分得到二阶导数，对于有二阶解析导数的方法（如MP2、DFT）使用该选项相比直接写freq不仅白浪费几十乃至几百倍耗时，精度还降低。

---

## 14. 冗余组合opt=calcall与freq
使用opt=calcall时程序会自动做振动分析，此时再写freq是多余的。

---

## 15. density关键词的使用规范
density含义是产生/导出/分析当前级别下的波函数，SCF类型计算（半经验/HF/DFT/MCSCF）写density纯属多余；density默认就是density=current；从G09 C.01开始，后HF计算用out=wfn/wfx时默认已用了density关键词。

---

## 16. 滥用scrf=externaliteration
外迭代在隐式溶剂模型下仅在做后HF或TD/CIS算激发态时才用得着，SCF类型的理论方法计算时写externaliteration是乱用。

---

## 17. 滥用polar=enonly
常用DFT方法在Gaussian中有三阶解析导数，计算第一超极化率时写polar=enonly（基于解析一阶导数做两阶有限差分）会白白糟蹋大量计算资源且精度更低。

---

## 18. 冗余写法gen pseudo=read
自定义基组+赝势应使用更方便的关键词genecp，使用老式写法gen pseudo=read是多余的。

---

## 19. 误用scf=conver=6
单点计算可以将SCF收敛限从默认的8降到6以降低不收敛几率和耗时，但在几何优化、频率计算、超极化率计算等涉及能量导数计算时用scf=conver=6可能导致极小点/过渡态定位精度不够、几何优化时震荡、频率计算不准等问题。

---

## 20. 冗余IOp(1/8=x)与IOp(6/7=3)
IOp(6/7=3)相当于pop=full，IOp(1/8=x)相当于在opt里定义maxstep，有对应关键词时不建议写IOp；优化极小点时用maxstep必须带notrust（即opt(maxstep=x,notrust)），否则步长上限会随优化进行自发变化，而opt=TS任务默认已用notrust，再写是多余的。

---

## 21. 滥用scf=xqc与scf=qc
scf=qc（二次收敛）每步迭代比一般方式多花好几倍时间，不应作为默认关键词或首选解决不收敛的方法；如果迫不得已只能用qc方式收敛，极有可能最后得到的波函数并不稳定，暗示当前体系结构、方法、自旋多重度、基组等可能不合适。

---

## 22. 积分精度int=Acc2E的设定
int=Acc2E=12仅在G16之前版本非默认，对中、大体系用弥散函数奇多的基组（如LPol系列）可能有轻微帮助，一般情况下用处不大；从G16开始int=Acc2E=12已成为默认，没必要手动写。

---

## 23. 冗余关键词NMR=GIAO
Gaussian计算NMR时GIAO是默认的也是最好的方法，只需写NMR即可，写NMR=GIAO多余，写NMR=CSGT通常没有特殊理由。

---

## 24. 滥用guess=huckel
Gaussian默认的SCF初猜方式通常是最佳选择，除非碰见不收敛，否则没必要自行指定其它初猜方式（如guess=huckel），这通常会导致需要更多步才收敛甚至难收敛。

---

## 25. 无用关键词gfinput与gfprint
gfinput和gfprint用来输出基组详细定义，初学者通常读不懂也用不到这些信息，写这些关键词只会导致输出文件臃肿，完全毫无意义。

---

## 26. 无意义分割rwf文件
只有当单一读写rwf文件的分区空间不足时才有必要分割rwf文件；若无空间限制问题，对rwf做无意义分割（如分多个段写在一个分区）完全是多此一举。

---

## 27. 冗余关键词pop=full
pop=full会输出所有轨道展开系数，导致输出文件巨大且难以查找数据；如需考察轨道系数，应保留fch文件并使用Multiwfn程序主功能6的选项4进行输出，比在文本输出文件中查找方便得多。

---

## 28. QST任务中误用noeigen
在opt=TS任务中一般需要写noeigen，但QST2、QST3任务在计算时根本不会自动对每一步做Hessian矩阵本征值检测，因此对QST任务写noeigen毫无意义。

---

## 29. 冗余关键词SCF=direct与TD=direct
对于SCF计算，默认算法就是direct；对于TD计算，默认算法也叫direct且是最理想的，因此写SCF=direct或在TD中写direct毫无意义。

---

## 30. scrf里乱写read
scrf里写read代表从输入文件末尾读取自定义溶剂信息；如果在scrf里写了read但输入文件末尾没有任何自定义溶剂信息，这毫无意义且可能导致程序误读其它信息并报错。
