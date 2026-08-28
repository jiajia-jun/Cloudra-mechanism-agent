---
id: 411
title: 使用Gaussian+PySOC在TDDFT下计算旋轨耦合矩阵元
url: http://sobereva.com/411
domain: 激发态与光谱
topic: Gaussian结合PySOC计算TDDFT旋轨耦合矩阵元
cards: 1
---

# Gaussian结合PySOC计算TDDFT旋轨耦合矩阵元 — 知识卡片

## 1. 旋轨耦合矩阵元的基本概念

旋轨耦合矩阵元定义为<i|H_SO|j>积分，体现两个电子态间的旋轨耦合作用大小，常被称为旋轨耦合常数。该矩阵元用于计算磷光发射速率、系间窜越速率（正比于矩阵元的模方）及零场分裂（ZFS）。Gaussian在TDDFT下计算此矩阵元存在短板，需结合PySOC程序实现，相关原理见J. Chem. Theory Comput., 13, 515−524 (2017)。

## 旋轨耦合算符与相对论哈密顿
旋轨耦合算符H_SO来源于相对论效应，是将Dirac方程通过FW、X2C、ZORA、DK等变换为二分量哈密顿后，由非相对论部分、标量相对论部分和旋轨耦合部分加和而成。多数程序采用Breit-Pauli (BP)哈密顿中的H_SO算符，但亦有程序使用DK或ZORA哈密顿下的算符。

## 自旋多重度与旋轨耦合的关系
不考虑旋轨耦合时，不同自旋多重度态间哈密顿矩阵元为0；引入旋轨耦合算符后，不同自旋多重度态可发生相互作用，本征态成为不同多重度态的线性组合，单重态、三重态概念不再严格存在。

## 旋轨耦合矩阵元的数值特性
旋轨耦合矩阵元为复数，包含实部和虚部，部分程序（如PySOC）仅输出其模（实部与虚部平方和开根号）。算符包含x、y、z三个分量，部分程序分别计算输出，部分程序合并计算。常用单位为cm^-1，换算关系为1 Hartree = 219474.6363 cm^-1、1 eV = 8065.5447 cm^-1。

## 旋轨耦合积分的计算方法
旋轨耦合矩阵元由基函数间旋轨耦合积分线性组合而成。H_SO包含单电子算符H_SO1和双电子算符H_SO2，后者计算耗时极高。常用的近似方法包括自旋轨道平均场（SOMF/AMFI）和有效原子电荷（Zeff）方法，前者近似计算双电子部分，后者通过修正H_SO1中的核电荷来等效包含H_SO2效果。

## 有效原子电荷（Zeff）方法
Zeff方法通过将H_SO2效果吸入H_SO1实现，仅计算单电子部分耗时，精度受有效电荷影响，误差可能达百分之十几至二三十。该方法适合结合赝势使用以同时考虑标量相对论效应，对大体系较为理想，但要求元素具有拟合好的有效电荷。

## Koseki有效电荷参数集
常用Koseki拟合的有效电荷包括：前三周期元素（6-31G*，JPC, 96, 10768 (1992)）、主族元素（SBKJC赝势，JPC, 99, 12764 (1995)）、d/ds族过渡金属（SBKJC赝势，JPCA, 102, 10430 (1998)）。SBKJC赝势中过渡金属为小核、主族为大核，与Gaussian中SDD、lanl2赝势一致，可搭配使用。

## PySOC程序原理与功能
PySOC基于Gaussian TDDFT输出文件（rwf和log）提取组态系数、轨道系数及基组信息，调用MolSOC以Zeff方式计算旋轨耦合积分，最终组合得到单重态与三重态间矩阵元。程序支持G09，对G16支持需特定方法，要求基态为闭壳层单重态，且基组角动量不超过f。

## PySOC修改版功能改进
修改版PySOC主要改进包括：修正态序号输出格式为两位；删除TD计算下不准确的激发态跃迁偶极矩计算功能（降低耗时约40%）；在MolSOC中补充Koseki拟合的有效电荷参数，支持赝势计算。下载地址：http://sobereva.com/soft/sob_PySOC_MolSOC.zip

## PySOC安装与配置要求
PySOC要求Python版本>=2.7，建议系统为CentOS/RHEL >7.0。安装需解压PySOC和MolSOC修改版，赋予可执行权限，修改pysoc/bin/pysoc.py中的路径和init.py中的g09root及molsoc_path，并将PySOC bin目录添加至PATH环境变量。

## MolSOC可执行文件选择
MolSOC提供三个可执行文件对应不同有效电荷组合：molsoc0.1_1.exe（作者前五周期+Koseki金属小核）、molsoc0.1_2.exe（作者前三周期+Koseki主族大核+金属小核）、molsoc0.1_3.exe（Koseki前三周期+主族大核+金属小核）。通常推荐使用molsoc0.1_3.exe，适合前三周期全电子、后续元素用SDD/lanl2赝势的情况。

## Gaussian计算输入文件要求
使用PySOC前需运行Gaussian TD(50-50,nstates=x)任务，计算x个单重态和x个三重态。输入文件必须包含`%rwf=gaussian.rwf`、`6D 10F`（笛卡尔基函数）、`nosymm`和`GFInput`关键词。输出文件须命名为gaussian.log，并保留gaussian.rwf文件。

## PySOC计算步骤与init.py设置
将init.py拷至计算目录，根据nstates设置n_s和n_t列表（如[1,2,3,4,5]）。运行命令`pysoc.py`，程序调用rwfdump和MolSOC进行计算。耗时随体系大小和态数增加，建议重定向输出（如`pysoc.py > pysoc.out`）。

## PySOC输出结果解读
主要输出文件为soc_out.dat（旋轨耦合矩阵元）和ene_out.dat（激发能）。soc_out.dat中格式如`sum_soc, <S0|Hso|T1,1,0,-1> (cm-1): 115.94270 81.98387 0.01644 81.98387`，第一个值为总SOC（各子态矩阵元平方和开根号），后续值为Ms=1,0,-1子态的分量。

## 实例1：甲醛(H2CO)计算结果
使用B3LYP/TZVP级别计算H2CO，设置nstates=5。PySOC（Koseki有效电荷）算得<S1|H_SO|T2>为49.81285 cm-1，与PySOC原文结果（45 cm-1）偏差源于有效电荷参数不同；若使用MolSOC作者原版有效电荷（molsoc0.1_1.exe），结果为44.73483 cm-1，与原文精确一致。

## 实例2：Os配合物计算设置
重现Phys. Chem. Chem. Phys., 16, 26184 (2014)中Os-4配合物数据。优化使用B3LYP/genecp（Os用lanl2DZ），激发态计算使用B3LYP/def2TZVP（Os为小核赝势）+ PCM(CH2Cl2)，设置nstates=10。def2-TZVP对Os为小核赝势，适用于修改版MolSOC中的Koseki参数。

## 实例2：Os配合物计算结果与验证
计算得到S1-T2能级差为0.09 eV（文献0.11 eV），旋轨耦合矩阵元<S1|H_SO|T2>为593.44 cm-1（文献620 cm-1），相对误差不到5%，说明赝势+Zeff方法对配合物可靠。使用更廉价基组（6-311G*/SDD）得到矩阵元539.9 cm-1，能级差0.093 eV，结果定性合理。

## 方法总结与替代方案建议
Gaussian+PySOC组合可容易获取TDDFT级别单-三重态旋轨耦合矩阵元，耗时比TDDFT低一个数量级，基于Zeff方法的精度对过渡金属配合物等大体系足够。若非必须使用Gaussian，推荐使用ORCA（更快、更准确、更方便），见http://sobereva.com/462；免费Dalton亦可计算但耗时较高。

---
