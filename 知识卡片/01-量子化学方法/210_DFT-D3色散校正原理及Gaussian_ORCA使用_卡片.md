---
id: 210
title: DFT-D色散校正的使用
url: http://sobereva.com/210
domain: 量子化学方法
topic: DFT-D3色散校正原理及Gaussian_ORCA使用
cards: 12
---

# DFT-D3色散校正原理及Gaussian_ORCA使用 — 知识卡片

## 1. DFT-D色散校正简介

DFT-D色散校正是解决传统DFT泛函（如B3LYP、PBE）色散作用描述能力差的最有效方法。Grimme提出的DFT-D系列包括D1、D2、D3和D4版本，其中D3（JCP,132,154104(2010)）支持元素多（H到Pu）、精度好且几乎不增加计算耗时。DFT-D对色散主导的体系（如物理吸附、长链烷烃）以及氢键、卤键等静电主导体系的计算精度均有显著提升，被称为有益无害的校正。
- DFT-D3是目前最流行、支持最广泛且计算最便宜的色散校正方法。
- 引用示例：J. Mol. Model., 19, 5387 (2013) 展示了B3LYP-D3对二聚体计算与CCSD(T)定性一致。

---

## 2. DFT-D3的零阻尼形式

零阻尼DFT-D3校正能公式包含原子间距离R_AB、色散系数C_n和阻尼函数f_damp。阻尼函数f_damp随R_AB减小衰减为0，使较近距离时校正能精确为0以避免double-counting。零阻尼形式对每个泛函有4个可调参数（s6、s8、sr,6、sr,8），其中普通泛函s6=1、sr,8=1，一般只需拟合s8和sr,6。
- R0_AB = √(C8_AB / C6_AB)。
- 双杂化泛函的s6小于1，需要拟合确定。

---

## 3. DFT-D3的BJ阻尼形式

BJ阻尼DFT-D3使用Becke-Johnson阻尼函数，物理意义更明确，在中、近程距离的校正能虽小但不接近0。BJ阻尼形式对每个泛函有四个参数（a1、a2、s6、s8），普通泛函s6=1，一般需拟合三个参数。
- HF只能用BJ阻尼，M05/06/08系列只能用零阻尼。
- 多数文章中写的DFT-D3实际可能用的是DFT-D3(BJ)。

---

## 4. DFT-D3程序的基本使用

Grimme的DFT-D3程序根据原子坐标计算色散校正能及梯度，编译后在Linux下使用`./dftd3 test.xyz -func b-lyp -bj`命令运行。输入文件为xyz格式坐标，输出包含校正能（单位kcal/mol和a.u.），a.u.数值写入.EDISP文件。
- `-func`参数需按Turbomole写法（如b3-lyp、pbe0）。
- 必须通过命令行运行，不支持双击图标。

---

## 5. DFT-D3程序的高级选项

DFT-D3程序提供多种命令行选项以控制计算细节，包括三体项计算、梯度输出和原子对贡献分析。输出结果中包含每个原子对色散能贡献（kcal/mol），并可利用fragment文件定义片段分析片段间色散作用。
- `-abc`：计算三体校正项。
- `-grad`：输出梯度到dftd3_gradient文件。
- `-anal`：输出原子对贡献分析。

---

## 6. Gaussian09对DFT-D的早期支持

Gaussian03完全不支持DFT-D。Gaussian09 D.01版之前支持B97D、ωB97XD、B2PLYPD（标配DFT-D2）以及M06-2X（对弱相互作用较好）。
- 对于重原子计算出现`R6DR0: No vdW radius available`错误时，需升级到D.01版使用DFT-D3或更换泛函。
- G09早期版本可通过external关键词调用外部脚本结合DFT-D3程序进行优化，但需自行编写脚本。

---

## 7. Gaussian09 D.01及之后版本的DFT-D使用

从Gaussian09 D.01版开始直接支持DFT-D3，通过EmpiricalDispersion关键字控制。校正能被加到核互斥能中，总能量为校正后能量。
- `EmpiricalDispersion=GD2`：DFT-D2校正。
- `EmpiricalDispersion=GD3`：零阻尼DFT-D3校正。
- `EmpiricalDispersion=GD3BJ`：DFT-D3(BJ)校正（可简写为`em=GD3BJ`）。

---

## 8. Gaussian内置的含色散校正泛函

Gaussian09 D.01及之后版本支持直接调用某些含DFT-D校正的泛函，无需额外写EmpiricalDispersion。B3LYP-D3(BJ)被推荐用于弱相互作用计算，精度好且速度快。
- 内置泛函：B2PLYPD3、B97D3、mPW2PLYPD、B97D、wB97XD、B2PLYPD。
- 名称含D3的结合DFT-D3(BJ)，其余结合DFT-D2。
- G09 D.01版D3(BJ)计算频率时忽略r^-8项可能导致软振动模式虚频，建议频率计算使用零阻尼或升级至E.01版。

---

## 9. 通过IOp在Gaussian中自定义DFT-D3参数

从Gaussian16 C.01开始，需通过IOp自定义DFT-D3参数（数值=参数*1000000）。Gaussian做多步任务时IOp仅对第一个任务生效，故Opt和Freq需分别运行。
- IOp(3/174)：S6
- IOp(3/175)：S8
- IOp(3/176)：SR6
- IOp(3/177)：A1
- IOp(3/178)：A2

---

## 10. 通过环境变量在Gaussian中自定义DFT-D3参数

在Gaussian16 B.01及之前版本，可通过环境变量自定义DFT-D3参数，适用于替换内置参数或为无内置参数的泛函（如MN15、TPSSh）启用D3校正。环境变量数值需除以1000000才是实际参数值。
- 零阻尼参数：GAUSS_DFTD3_S6、GAUSS_DFTD3_S8、GAUSS_DFTD3_SR6（sr,8固定为1.0）。
- BJ阻尼参数：GAUSS_DFTD3_S6、GAUSS_DFTD3_S8、GAUSS_DFTD3_ABJ1、GAUSS_DFTD3_ABJ2。

---

## 11. ORCA程序中的DFT-D使用

ORCA通过D3ZERO（零阻尼）、D3或D3BJ（BJ阻尼）关键词启用DFT-D3校正，ABC关键词用于计算三体项。ORCA内嵌了Grimme的DFT-D3程序，输出信息与独立程序一致。
- 示例：`!B3LYP TZVP d3` 代表 B3LYP-D3(BJ)/TZVP。
- 推荐使用RI-J技术结合BLYP-D3(BJ)计算大体系弱相互作用。

---

## 12. GAMESS-US程序中的DFT-D使用

GAMESS-US在$DFT组中通过DC或IDCVER控制DFT-D校正。IDCVER=1/2/3/4分别对应D1/D2/D3(0)/D3(BJ)，默认为3。
- DCABC=.T.：计算三体校正项。
- 对于B97D和ωB97XD，直接设定DFTTYP即可，无需设置IDCVER。
- GAMESS-US内嵌Grimme程序，目前使用Bq原子可能会报错。
