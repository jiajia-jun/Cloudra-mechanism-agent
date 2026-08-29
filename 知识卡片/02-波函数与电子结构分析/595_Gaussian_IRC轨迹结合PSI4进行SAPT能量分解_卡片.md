---
id: 595
title: 对Gaussian计算的IRC轨迹上每个点用PSI4做SAPT分析的辅助工具
domain: 波函数与电子结构分析
topic: Gaussian_IRC轨迹结合PSI4进行SAPT能量分解
cards: 8
---

## 1. IRC_SAPT工具的功能与下载
IRC_SAPT工具用于将Gaussian计算产生的IRC轨迹输出文件便捷地转换为对应于每个IRC点的PSI4 SAPT输入文件。可从 获取，压缩包内无后缀文件为Linux平台可执行程序，有后缀文件为Windows平台可执行程序。SAPT原则上适用于弱相互作用分解，不适合存在化学键作用的片段间相互作用分解。

---

## 2. SAPT模板文件SAPT_template.inp的格式要求
在使用IRC_SAPT前，需在当前文件夹准备名为SAPT_template.inp的PSI4 SAPT标准输入文件模板。该模板文件中两个片段的电荷、自旋多重度及坐标部分需分别用[monomer1]和[monomer2]代替。模板中应包含[ RxCoord]占位符，该行将被IRC_SAPT自动替换为具体的反应坐标值。

---

## 3. IRC_SAPT的运行输入参数
启动IRC_SAPT后，需按提示输入Gaussian IRC输出文件的路径、需要考虑的正向和反向IRC点数量、片段1和片段2的净电荷与自旋多重度以及原子序号。程序根据这些输入在当前文件夹生成一批对应于每个IRC点的SAPT输入文件，文件名从0001.inp开始按顺序编号，其中对应过渡态几何的输入文件序号居中。

---

## 4. 水二聚体构型转换的IRC计算设置
水二聚体构型转换示例中，首先使用Gaussian 16 A.03通过关键词"# B3LYP/6-311+G** em=GD3BJ opt(calcfc,TS,noeigen) freq"优化过渡态并进行频率分析。随后基于优化后的结构，使用关键词"# B3LYP/6-311+G** em=GD3BJ IRC(calcfc,recalc=3,LQA,maxpoints=50)"生成IRC轨迹，计算包含30个正向点和30个反向点。

---

## 5. PSI4输入文件模板的计算级别与输出设置
示例中的SAPT_template.inp设定计算级别为SAPT2+(3)δMP2/aug-cc-pVTZ，该级别在J. Comput. Chem., 40, 2868 (2019) DOI: 10.1002/jcc.26068 中被证明能准确表示氢键相互作用。模板通过psi4.print_out指令要求PSI4在任务结束时打印反应坐标、总相互作用能及各分量能量，并将能量单位转换为kcal/mol。

---

## 6. PSI4批量计算脚本psi4all.sh的使用
将生成的SAPT输入文件及IRC_SAPT文件夹中的psi4all.sh脚本移至新文件夹后执行psi4all.sh，该脚本将调用本机的PSI4运行所有SAPT输入文件。psi4all.sh默认使用36线程进行PSI4计算，用户应根据实际情况修改线程数设置。计算产生的输出文件名与输入文件相同，后缀为.out。

---

## 7. 数据提取脚本extract.sh的输出格式
所有PSI4计算完成后，运行extract.sh脚本可从当前文件夹的所有.out文件中提取数据并汇总生成energy.txt文件。输出文件各列含义依次为：反应坐标(单位sqrt(amu)*Bohr)、总相互作用能(E_tot)、静电能(E_elst)、交换能(E_exch)、色散能(E_disp)、诱导能(E_ind)，所有能量单位均为kcal/mol。

---

## 8. 水二聚体IRC轨迹SAPT分析结论
对水二聚体IRC轨迹上各点的SAPT分析结果显示，静电吸引作用在稳定最小构型相对于过渡态构型方面起主导作用，诱导效应也有一定贡献。色散相互作用对二聚体构型的敏感性不如静电和诱导效应，交换排斥效应在很大程度上抵消了静电和诱导效应的稳定作用。
