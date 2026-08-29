---
id: 516
title: 关于为什么Multiwfn算的出RESP电荷与Antechamber的有所差异
url: http://sobereva.com/516
domain: 波函数与电子结构分析
topic: Multiwfn与Antechamber的RESP电荷差异原
cards: 7
---
## 1. Multiwfn与Antechamber计算RESP电荷差异的主要原因

Multiwfn算出的RESP电荷与antechamber不同主要有两点原因：拟合点的分布不同以及等价约束设置不同。Multiwfn 3.6、3.7版默认使用MK方式设置拟合点，而Antechamber从Gaussian的pop=MK IOp(6/33=2) IOp(6/42=6)输出文件中直接读取拟合点坐标和静电势。涉及的体系相关文件下载链接为http://原作者.com/attach/516/file.rar，使用的是2019-Sep-26更新的Multiwfn 3.7(dev)版。

## 2. 拟合点分布差异的具体细节

虽然MK原文定义了拟合点的分布规则，但在具体确定拟合点坐标上，不同程序的细节不同，例如在球面上的拟合点以什么算法生成排布、拟合点的密度是多少、在原子接缝的地方是否自动去除过密的拟合点等。Multiwfn和Gaussian在拟合点位置设置上的不同导致两者算出的RESP电荷会有少许差别，通常差异不大且无法判定哪个程序更准确，因为都是合理的。

---

## 3. 乙醇分子RESP电荷对比（默认拟合点）

乙醇分子使用Gaussian 09 E.01计算，关键词为#HF/6-31G* SCF=tight Test Pop=MK iop(6/33=2) iop(6/42=6)。Multiwfn载入fch文件，选择标准两步式RESP电荷计算，默认约束为Constraint 1: 2(H) 3(H) 4(H) 和 Constraint 2: 6(H) 7(H)，计算结果为C(-0.250749)、C(0.547451)、O(-0.714589)及相应的H原子电荷，与Antechamber结果存在轻微差异。

---

## 4. 通过读取Gaussian输出文件消除拟合点差异

若想让Multiwfn算出的电荷与Antechamber精确一致，需在选择开始计算RESP电荷之前先选选项8，再选1开始标准两步式拟合，并输入Gaussian输出文件路径。此时Multiwfn和Antechamber一样从Gaussian输出文件里读取拟合点的位置和静电势，计算结果与Antechamber给出的完全相同（个别原子有10的负六次方的差异是收敛限设置、舍入误差等导致的）。

---

## 5. Antechamber对苯甲醛的等价约束设置

对于苯甲醛体系，即便Multiwfn从Gaussian输出文件读取拟合点信息，结果与Antechamber仍有差异，这是因为等价性约束设置不同。Antechamber在第一步拟合时自动设置了约束：4=2、8=6、11=3、12=7，即把苯环上左右对称的原子电荷约束为相同，而Multiwfn默认情况下不做这个约束，导致结果不同。

---

## 6. 在Multiwfn中手动设置等价约束

如果想让Multiwfn实现与Antechamber相同的等价约束，可以编写约束设置文件eqs.txt，内容为4,2; 8,6; 11,3; 12,7。在Multiwfn计算RESP电荷前，选择设置等价性约束的选项，再选读取约束文件并输入路径，然后选择2开始一步式RESP电荷拟合，此时结果和Antechamber给出的精确相同。

---

## 7. 等价约束对静电势重现性的影响

对苯环上对称的原子设置等价性约束并不是RESP电荷原文里的标准做法，而是Amber开发者定义的规则。这种约束会使得静电势重现性误差增加，例如不做约束时RMSE为0.001373，做约束后RMSE增加到0.002020。Multiwfn用户可根据需要选择是否施加这种约束，也可以利用结构的对称性自动产生等价性约束设置文件。
