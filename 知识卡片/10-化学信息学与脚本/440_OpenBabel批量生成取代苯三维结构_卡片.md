---
id: 440
title: 基于OpenBabel批量产生特定基团以任意方式接到苯上的结构的方法
domain: 化学信息学与脚本
topic: OpenBabel批量生成取代苯三维结构
cards: 10
---

## 1. OpenBabel批量生成特定基团取代苯结构的方法
实现自动产生大批量带有指定基团（如CH3、H、CN、F、Cl、Br、I、OH）并以随机方式组合接到苯环上的取代苯结构，最简单的方式是编写程序生成SMILES字符串，再利用OpenBabel生成三维结构。

---

## 2. SMILES字符串定义与适用范围
SMILES是一种格式简单、仅记录原子间连接关系的分子结构描述字符串，适用于大部分分子（复杂笼状体系除外），通常使用.smi后缀。
- 介绍

---

## 3. OpenBabel的功能与获取方式
OpenBabel是一款免费的化学文件格式转换程序，具备基于力场的几何优化、加氢/去氢、合并/拆分文件、相似性对比、结构排序/对齐等功能。
- CentOS安装命令：yum install epel-release 后执行 yum install openbabel

---

## 4. OpenBabel生成三维结构的原理与局限
OpenBabel可以基于SMILES字符串通过CORINA算法快速、近似产生分子三维结构，所得结构较为粗糙但足以作为几何优化的初猜结构。

---

## 5. 取代苯SMILES字符串生成代码参数
Fortran代码中定义了8种取代基、生成分子数量为20，并将结果输出至subben.smi文件。
- 取代基数组：`sub(nsub)=(/ "(C)","","(C#N)","(F)","(Cl)","(Br)","(I)","(O)" /)`
- 分子数量：`nmol=20`

---

## 6. 取代苯SMILES字符串生成逻辑
程序通过循环遍历苯环的6个位置，利用随机数函数从8种取代基中选取一种拼接至SMILES字符串中，从而构建出随机取代苯的SMILES。

---

## 7. SMILES字符串生成代码示例
程序运行后会生成包含随机取代苯SMILES字符串的文件subben.smi，每次运行结果不同。
- 示例字符串：`c1(Cl)c(I)c(F)c(C#N)cc1(O)`, `c1(I)cc(F)cc(C)c1`, `c1(F)cc(O)c(I)c(Br)c1(O)`, `c1(O)c(Cl)c(Br)c(I)c(F)c1(Br)`, `c1c(C#N)c(O)cc(F)c1(I)`, `c1(C#N)c(F)c(Br)c(Br)c(F)c1(O)`

---

## 8. OpenBabel批量转换SMILES为三维结构的命令
将生成的subben.smi文件放在当前目录，使用命令行批量转化为PDB格式的三维结构文件。
- 命令：`obabel subben.smi -O out.pdb --gen3d -m`
- 参数说明：--gen3d 代表自动产生三维结构，-m 代表拆分文件

---

## 9. 可视化查看批量生成结构的方法
将生成的out1.pdb、out2.pdb... out20.pdb等文件拖入VMD软件，通过Extensions - Visualization - Multiple Molecule animation功能轮回显示结构。

---

## 10. OpenBabel生成优化三维结构的命令
若想在生成三维结构时同步使用MMFF94高精度有机小分子力场进行优化，可使用特定命令。
- 命令：`obabel subben.smi -O out.pdb --gen3d -m --minimize --ff MMFF94`
