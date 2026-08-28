---
id: 585
title: 计算适用于OPLS-AA力场做模拟的1.2*CM5原子电荷的懒人脚本
url: http://sobereva.com/585
domain: 分子动力学与力场
topic: OPLS-AA力场1.2倍CM5电荷计算脚本
cards: 14
---

# OPLS-AA力场1.2倍CM5电荷计算脚本 — 知识卡片

## 1. OPLS-AA力场推荐使用1.2*CM5原子电荷

根据J. Phys. Chem. B., 121, 3864 (2017)中的测试，基于OPLS-AA力场的模拟很适合结合1.2*CM5原子电荷。1.2*CM5电荷在水合自由能计算精度上稍逊于1.14*CM1A-LBCC，但在计算蒸发焓、密度等其他属性时误差更小，且经验性更低、更有普适性。1.2*CM5电荷是在Truhlar等人提出的原始CM5电荷基础上乘上1.2，等效体现出了溶剂环境对溶质的极化作用。

---

## 2. 1.2*CM5电荷懒人脚本的位置与版本要求

计算1.2*CM5原子电荷的懒人Linux脚本是Multiwfn文件包里的examples\scripts\1.2CM5.sh，该脚本在2021-Jan-28及之后更新的Multiwfn版本中才有。Multiwfn程序可以在其主页http://sobereva.com/multiwfn免费下载。

---

## 3. 脚本运行的前提条件与基本命令

运行此脚本前需确保已安装Gaussian和Multiwfn，Multiwfn需按照手册2.1.2节说明安装。假设1.2CM5.sh和结构文件phenol.xyz都在当前目录，运行命令为./1.2CM5.sh phenol.xyz。

---

## 4. 脚本运行输出结果内容

脚本运行结束后，屏幕会提示Finished! The optimized atomic coordinates with 1.2*CM5 charges (the last column) have been exported to phenol.chg in current folder。最终生成的phenol.chg文件中，第2、3、4列是优化后的XYZ坐标（埃），最后一列即为1.2*CM5电荷。

---

## 5. 脚本的计算原理与理论级别

脚本将输入文件的结构作为初猜，使用Gaussian在B3LYP-D3(BJ)/def2-SVP理论水平下进行几何优化。之后调用formchk将chk文件转化为fchk文件，再调用Multiwfn计算CM5电荷，最后输出乘以1.2后的结果。

---

## 6. 支持的输入文件格式

脚本使用的输入文件可以是任意含有结构信息且Multiwfn支持的文件格式，例如pdb、mol、mol2、xyz、fch、gjf、wfn等。

---

## 7. 设置电荷与自旋多重度参数

脚本默认将电荷设为0，自旋多重度设为1。对于不带电的二重态体系，运行命令需修改为./1.2CM5.sh phenol.xyz 0 2。

---

## 8. 脚本的可执行权限与Gaussian版本设置

若运行脚本提示没有可执行权限，需先运行chmod +x ./1.2CM5.sh。脚本默认调用Gaussian 16，如果机子安装的是Gaussian 09，需将文件第22行改为Gaussian=g09。

---

## 9. 脚本的计算环境与关键词注意事项

脚本中的计算是在真空下进行的，这是刻意设定，不要自行改成在溶剂模型下进行。

---

## 10. 脚本运行失败的排查方法

脚本运行失败可能的原因包括：Gaussian未恰当安装；Multiwfn未按手册安装（可用noGUI版避免图形库依赖）；Gaussian计算失败（版本太老不支持em=GD3BJ关键词可去掉，或优化/SCF不收敛需查看gau.out文件）。

---

## 11. 直接使用波函数文件计算CM5电荷的方法

如果已有Gaussian或其它程序产生的Multiwfn支持的波函数文件（fch/wfn/wfx/molden/mwfn等），无需使用脚本。直接载入Multiwfn，依次输入7、16、1即可得到CM5电荷，再手动乘上1.2。

---

## 12. 带电体系的电荷选择建议

J. Phys. Chem. B.文章仅考虑了中性体系，带电体系一般情况下不能用1.2*CM5电荷，因为此时总电荷不为整数。对于带电体系，建议使用Multiwfn计算RESP2电荷。

---

## 13. 脚本的引用要求

如果使用此脚本计算1.2*CM5电荷，必须按照Multiwfn程序包里How to cite Multiwfn.pdf文档的说明恰当引用Multiwfn。

---

## 14. 免费程序ORCA替代方案

如果没有购买Gaussian，可以使用免费的ORCA量子化学程序结合Multiwfn计算1.2*CM5原子电荷，相应的傻瓜式脚本见《ORCA结合Multiwfn计算RESP、RESP2和1.2*CM5原子电荷的懒人脚本》（http://sobereva.com/637）。
