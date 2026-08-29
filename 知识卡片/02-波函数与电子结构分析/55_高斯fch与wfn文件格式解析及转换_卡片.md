---
id: 55
title: 高斯fch文件与wfn波函数文件的介绍及转换方法
domain: 波函数与电子结构分析
topic: 高斯fch与wfn文件格式解析及转换
cards: 28
---

## 1. wfn文件第一行格式
wfn文件的第一行没有任何物理意义，仅作为文件注释使用，例如可以是"Title Card Required"。

---

## 2. wfn文件第二行格式
wfn文件第二行包含基本信息，格式如"GAUSSIAN 5 MOL ORBITALS 27 PRIMITIVES 5 NUCLEI"。其中"GAUSSIAN"说明函数类型为高斯型，"MOL ORBITALS"后数字为分子轨道数，"PRIMITIVES"后数字为原始高斯函数总数，"NUCLEI"后数字为原子数。

---

## 3. wfn文件原子信息行格式
wfn文件原子信息行格式为"元素符号 原子序号 (CENTRE 原子序号) X坐标 Y坐标 Z坐标 CHARGE = 核电荷数"。坐标单位为波尔，使用赝势时核电荷数等于被明确表达的价层电子数而非原子序数。

---

## 4. wfn文件高斯函数中心指配
wfn文件中的"CENTRE ASSIGNMENTS"行列出了每个高斯函数所在的原子序号，项数与"PRIMITIVES"数目一致。

---

## 5. wfn文件高斯函数类型编号
wfn文件"TYPE ASSIGNMENTS"行使用数字定义高斯函数类型，对应关系为：1=S, 2=X, 3=Y, 4=Z, 5=XX, 6=YY, 7=ZZ, 8=XY, 9=XZ, 10=YZ, 11=XXX, 12=YYY, 13=ZZZ, 14=XXY, 15=XXZ, 16=YYZ, 17=XYY, 18=XZZ, 19=YZZ, 20=XYZ。生成wfn文件时应使用6d/10f型高斯函数。

---

## 6. wfn文件高斯函数指数
wfn文件"EXPONENTS"行列出了每个高斯函数的指数，对应表达式 $N \cdot x^{ix} y^{iy} z^{iz} \exp(-\alpha r^2)$ 中的 $\alpha$，项数与原始高斯函数总数一致。

---

## 7. wfn文件分子轨道信息格式
wfn文件分子轨道信息行格式为"MO 序号 MO 0.0 OCC NO = 占据数 ORB. ENERGY = 轨道能"。占据数对于闭壳层为2，非限制性波函数为1，限制性开壳层计算可能需要手动修改。轨道能单位为Hartree。

---

## 8. wfn文件轨道展开系数
wfn文件中每个分子轨道下列出了其向所有高斯函数的展开系数。这些展开系数已经包含了高斯函数的归一化系数，即对应向未归一化高斯函数 $x^{ix} y^{iy} z^{iz} \exp(-\alpha r^2)$ 展开的系数。

---

## 9. wfn文件中后HF方法的轨道记录
使用后HF方法并加density=current时，wfn文件输出的是自然轨道。此时轨道数目与可独立变分基函数一致，所有自然轨道都会被列出，占据数一般不为整数。

---

## 10. wfn文件中自旋轨道的记录顺序
wfn文件对于自旋轨道，先按能量由低到高记录所有alpha轨道，再记录beta轨道。可通过检验轨道能量或占据数与前一个轨道的关系来判断alpha与beta轨道的分界。

---

## 11. wfn文件结束行及附加信息
wfn文件标准信息以"END DATA"行结束。之后允许附加信息，如"THE HF ENERGY = 数值 THE VIRIAL(-V/T)= 数值"，分别代表HF或DFT总能量（后HF方法时仍为HF能量）和维里值。

---

## 12. 读取wfn文件的Fortran数据结构定义
读取wfn文件需定义原子类型atomtype（含名称、坐标、电荷）、基函数类型basistype（含中心、类型、指数）、轨道数nmo、原始高斯函数数nprims、原子数ncenter、总能量totenergy、维里值virialratio、轨道占据数MOocc、轨道能量MOene、系数矩阵CO等变量。

---

## 13. wfn文件读取逻辑：判断波函数类型
在读取wfn文件后，通过总电子数与轨道数的关系判断波函数类型：若总电子数为轨道数2倍则为RHF；若相等则为UHF；若最后轨道占据数非整数则为后HF波函数；否则为ROHF。对于UHF和开壳层后HF，需通过能量或占据数变化确定alpha/beta轨道分界。

---

## 14. wfn文件输出格式规范
输出wfn文件时，首行可为任意注释，次行为"GAUSSIAN"及轨道数、高斯函数数、原子数。随后依次输出原子信息、中心指配、类型指配、指数、各轨道的占据数与能量及系数，最后以"END DATA"和能量、维里值行结束。系数输出格式为5D16.8。

---

## 15. fch文件基本信息与格式
fch文件是ASCII格式的检查点文件，可用于跨平台交换数据。首行为标题，次行包含任务类型、方法、基组。数组型数据前有标签，读取格式为A40,3X,A1,5X,I12，其中数据类型R/I/C/L分别代表实型、整型、字符型、逻辑型。

---

## 16. fch文件中基函数的壳层类型定义
fch文件中Shell types定义壳层类型：0=s, 1=p, -1=sp, 2=6d, -2=5d, 3=10f, -3=7f, 4=15g, -4=9g。这与wfn文件按高斯函数顺序储存不同，fch是按壳层分层储存。

---

## 17. fch文件中基函数的排列顺序
fch文件中每个壳层内笛卡尔型基函数按顺序排列：S, X, Y, Z, XX, YY, ZZ, XY, XZ, YZ, XXX, YYY, ZZZ, XYY, XXY, XXZ, XZZ, YZZ, YYZ, XYZ。注意f轨道顺序与wfn不同。

---

## 19. fch文件中的密度矩阵记录
fch文件中的Total SCF Density或Total MP2 Density等记录的是密度矩阵的下三角部分（含对角元），顺序为(1,1)(2,1)(2,2)(3,1)(3,2)(3,3)(4,1)...。

---

## 20. fch文件中的轨道系数与自然轨道处理
fch文件默认记录SCF轨道系数。若要记录自然轨道系数，需在后HF计算中使用density=current，随后运行Guess=(Save,Only,NaturalOrbitals) ChkBasis，此时轨道能量部分存储的是占据数。

---

## 21. fch文件处理NBO轨道的特殊标记
若fch文件含有NBO轨道信息，需根据使用的密度类型修改第一行标记：使用后HF密度改为"saveNBOocc"（轨道能量部分存占据数），使用SCF密度改为"saveNBOene"（轨道能量部分存能量，占据数需手动补充）。

---

## 22. fch文件中SP壳层的收缩系数
fch文件中"Contraction coefficients"包含S型和部分P型系数，而"P(S=P) Contraction coefficients"专门用于SP壳层中P部分的收缩系数。对于S壳层，后者对应项为0。

---

## 23. fch文件读取中的标签定位子程序
读取fch文件时，使用loclabel子程序定位标签（如'Alpha MO coefficients'），该子程序从文件头开始搜索，找到后回退一行，若未找到则设置noentryinfch标志为1。

---

## 24. fch文件读取中对特殊轨道的识别逻辑
读取fch文件时，检查第一行标题：含'saveNBOocc'、'saveNBOene'或'saveNO'时，说明文件分别包含NBO占据数、NBO能量或自然轨道信息，此时应读入所有轨道而非仅占据轨道。

---

## 25. fch文件读取中系数矩阵的读取策略
对于RHF或ROHF，只读取Alpha轨道系数；对于UHF，分别读取Alpha和Beta轨道系数。若文件包含自然轨道或NBO信息，需根据情况调整读取的轨道数目并将MOocc与MOene数组内容互换或置零。

---

## 26. 高斯函数归一化系数计算公式
计算高斯函数归一化系数的公式为 $(2\alpha/\pi)^{0.75} \sqrt{ (8\alpha)^{ix+iy+iz} \cdot ix! \cdot iy! \cdot iz! / [(2ix)! \cdot (2iy)! \cdot (2iz)!] }$，其中ix, iy, iz由高斯函数类型决定。

---

## 27. fch到wfn系数矩阵转换的循环逻辑
转换fch系数矩阵到wfn系数矩阵采用三层循环：最外层循环壳层，中层循环基函数，内层循环高斯函数。对于每个高斯函数，需乘以收缩系数和归一化系数，并根据波函数类型（RHF/UHF）从amocoeff或bmocoeff中提取对应轨道的基函数系数。

---

## 28. SP壳层在fch到wfn转换中的处理
在fch到wfn转换过程中，对于SP壳层（shelltype=-1），其第一个基函数使用"Contraction coefficients"，后续基函数（即P型）必须使用"P(S=P) Contraction coefficients"作为收缩系数。

---

## 29. fch2wfn程序的执行方式
fch2wfn程序可通过交互模式输入文件名运行，也可通过命令行模式运行，例如"fch2wfn c:\sob.fch..\saint.wfn"。含自然轨道的fch文件首行需改为saveNO，含NBO的需改为saveNBOocc或saveNBOene。
