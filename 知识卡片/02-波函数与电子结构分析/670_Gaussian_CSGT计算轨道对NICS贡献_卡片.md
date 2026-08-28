---
id: 670
title: 基于Gaussian的NMR=CSGT任务得到各个轨道对NICS贡献的方法
url: http://sobereva.com/670
domain: 波函数与电子结构分析
topic: Gaussian_CSGT计算轨道对NICS贡献
cards: 6
---

# Gaussian_CSGT计算轨道对NICS贡献 — 知识卡片

## 1. 轨道对NICS贡献方法的理论基础

利用Gaussian的AICD程序界面结合NMR=CSGT任务可以将NICS分解为不同类型分子轨道的贡献，该方法基于CSGT而非NCS。计算所有电子贡献的总NICS时，NCS(GIAO)与CSGT结果差异很小可忽略，但单个轨道的贡献可能相差很大，而同类轨道的总和差异通常很小。此方法适用于Gaussian G09 D.01及之后版本。
- 原文引用：http://sobereva.com/176, http://sobereva.com/carbon_ring.html, http://sobereva.com/294

---

## 2. 计算特定轨道对NICS贡献的输入文件设置

计算特定轨道（如苯的pi轨道）对NICS(1)ZZ的贡献，需要在Gaussian输入文件中使用`IOp(10/93=2)`关键词调用AICD界面，使用`guess=read`从chk文件读取波函数以节省时间。在分子坐标后的空行后依次写入AICD输出文件名（如nouse.txt）和指定的轨道序号（如17 20 21），并在体系坐标中加入`Bq 0. 0. 1.0`定义NICS探测点。
- 输入文件示例：benzene_NICS-pi.gjf

---

## 3. 苯pi电子与其它电子对NICS_ZZ的贡献数值

在B3LYP/6-31G(d)水平下计算得到苯的总NICS(1)ZZ为-27.3147，其中pi轨道（17、20、21号）的贡献为-29.7306，其它电子（sigma等）的贡献为2.4158。其它电子的贡献值既可以通过总NICS减去pi轨道贡献得到，也可以通过在输入文件中指定剩余占据轨道序号（1-16 18 19）直接计算验证。
- 结果验证：-27.3147 - (-29.7306) = 2.4159

---

## 4. 计算所有轨道对NICS贡献的脚本准备步骤

使用orbNICS.sh脚本自动计算各轨道贡献需要三个准备步骤：首先进行单点计算生成NICS.chk文件；其次创建NICS.gjf模板文件，必须包含`Bq`原子、`IOp(10/93=2)`、`guess=read`，且轨道序号行写为`orbidx`；最后修改脚本中循环的起始和终止轨道序号，并设置正确的Gaussian运行命令（默认为g16）。
- 脚本文件：orbNICS.sh

---

## 5. orbNICS.sh脚本的执行与输出结果

运行orbNICS.sh脚本后，会依次计算指定范围内各轨道的NICS贡献，结果保存在iso.txt和ZZ.txt中。iso.txt包含各轨道对Bq位置各向同性磁屏蔽值的贡献，ZZ.txt包含ZZ分量的贡献，文件末尾的Total值与直接使用NMR=CSGT计算的总磁屏蔽值完全一致。脚本每次运行时会自动清理旧的.out文件、iso.txt和ZZ.txt。
- 输出示例：Total: 13.6602 (Isotropic), Total: 27.3147 (ZZ)

---

## 6. 开壳层体系轨道序号的特殊规则

对于非限制性开壳层体系，在使用Gaussian的AICD界面或orbNICS.sh脚本指定轨道序号时，beta占据轨道的序号规则与fch文件中的显示不同，必须特别注意。若直接使用fch文件中的轨道序号进行指定会导致错误，具体规则需参考相关文献说明。
- 参考资料：http://sobereva.com/294
