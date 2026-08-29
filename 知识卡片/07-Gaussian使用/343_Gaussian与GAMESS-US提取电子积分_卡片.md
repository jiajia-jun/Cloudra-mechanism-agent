---
id: 343
title: 从Gaussian和GAMESS-US中提取电子积分
url: http://sobereva.com/343
domain: Gaussian使用
topic: Gaussian与GAMESS-US提取电子积分
cards: 10
---
## 1. 电子积分定义与对称性

无论输出的是单电子积分还是双电子积分，都是基函数已归一化后的值。双电子积分形式是(IJ|KL)，I,J基函数是r1坐标，K,L基函数是r2坐标。由于积分有对称性，即IJKL=IJLK=JIKL=JILK=KLIJ=LKIJ=KLJI=LKJI，所以程序输出双电子积分的时候都只输出对称唯一的部分。

---

## 2. Gaussian提取单电子积分

在Gaussian中计算时加上IOp(3/33=1)即可输出单电子积分，输出的包括：*** Overlap ***（重叠积分）、*** Kinetic Energy ***（动能积分）、****** Core Hamiltonian ******（核哈密顿矩阵，其数值就是动能积分矩阵元减去核吸引势积分矩阵元）、Multipole matrices（输出三次，IX= 1、IX= 2、IX= 3分别对应X,Y,Z方向的偶极矩积分矩阵）。

---

## 3. Gaussian提取双电子积分

Gaussian可以通过L316模块双电子积分，使用关键词IOp(3/33=3) extralinks(L316) scf=conventional noraff，同时单电子积分也会输出。输出信息中IntCnt是实际输出的积分总数，并行计算时每次输出的积分顺序可能不同。

---

## 4. Gaussian双电子积分阈值与限制

Gaussian计算并输出双电子积分的值阈值可以用IOp(3/27=N)调节，小于10^-N的积分不会被计算和输出，默认N=10。用32bit版本时这种方式输出积分时基函数最多127个，虽然64bit版没这个限制，但基函数多于这个时输出文件会巨大。

---

## 5. GAMESS-US积分提取注意事项

从GAMESS-US提取积分的方法对2014-Dec版亲测有效，相同基组下（Dunning基组不算，因Gaussian会自动会去掉其中冗余的GTF）输出的结果和Gaussian中的一致。输出积分时绝对不要用并行运算，否则输出内容会癫狂。

---

## 6. GAMESS-US单电子积分提取方法1

在$CONTRL里写上NPRINT=3即可在计算时输出基函数间的各种积分矩阵，输出的包括OVERLAP MATRIX（重叠矩阵）、BARE NUCLEUS HAMILTONIAN INTEGRALS (H=T+V)（核哈密顿矩阵）、KINETIC ENERGY INTEGRALS（动能积分矩阵）。程序没直接给出核吸引势积分，这只需自行把核哈密顿矩阵减去动能积分矩阵即可。

---

## 7. GAMESS-US单电子积分提取方法2

在gamess/source/int1.src中----- OPTIONAL DEBUG PRINTOUT -----第一处的下面加上特定代码，重新编译该资料件并链接成新的可执行文件（在GAMESS-US目录下执行./comp int1;./lked gamess 00），即可直接输出重叠积分、动能积分、核哈密顿矩阵以及考虑电子带负电荷的核吸引势积分。

## 8. GAMESS-US双电子积分提取设置

一定要用$SCF DIRSCF=.F. $END使用conventional的SCF方式，否则不会输出这些积分。在$CONTRL里写上NPRINT=4即可在计算时输出双电子积分，默认是小于10^-9的积分不被输出，可以在$CONTRL里用ICUT=N来把输出阈值调为10^-N。

---

## 9. GAMESS-US双电子积分输出格式

在输出双电子积分时，TOTAL NUMBER OF NONZERO TWO-ELECTRON INTEGRALS后面的数值是实际输出的双电子积分数。对(IJ|KL)积分，有8种等价形式，程序自动把指标调换成I>=J、K>=L、I>=K的形式。

---

## 10. GAMESS-US双电子积分提取方法2

在gamess/source/int2a.src的I4 = LOCL+L下面加上write(*,"(4i6,D25.16)") I1,I2,I3,I4,VAL，重新编译并链接（执行./comp int2a;./lked gamess 00）即可输出双电子积分。如果想输出所有积分，直接把int2a.src中IF(ABS(VAL).LT.CUTOFF) GO TO 200这一行注释掉即可。
