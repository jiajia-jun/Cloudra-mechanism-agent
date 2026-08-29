---
key: b499
title: 使用Multiwfn计算与超瑞利散射(HRS)实验相关的量
url: http://sobereva.com/499
domain: 波函数与电子结构分析
source: blog
year: 2019
cards: 9
---

# 使用Multiwfn计算与超瑞利散射(HRS)实验相关的量 — 知识卡片

## 1. 超瑞利散射(HRS)实验原理

超瑞利散射(HRS)是测定分子第一超极化率$\beta$的实验手段。通过入射光强度和垂直散射出的倍频光强度可得到$\beta_{HRS}$值，这是$\beta(-2\omega;\omega,\omega)$张量的各向平均属性。实验还可测得退偏比(Depolarization ratio, DR)，理论最小值为1.5。

---

## 2. HRS相关量的张量分解

HRS计算中的$<\beta^2_{ZZZ}>$和$<\beta^2_{XZZ}>$可分解为偶极(J=1)和八极(J=3)成分的加和。由此可定义各向异性参数$\rho$，以及偶极和八极对$\beta$的相对贡献$\phi(\beta_{J=1})$和$\phi(\beta_{J=3})$。

---

## 3. 散射光强度与极化角关系

入射光以X方向射入且相位延迟量$\delta=\pi/2$时，沿Y方向散射出的Z方向极化光强度与入射光极化角$\Psi$有关。散射光强度随$\Psi$的变化关系可由特定公式描述，常用于绘制极坐标图考察各向异性。

---

## 4. Gaussian计算HRS输入文件设置

计算HRS相关量需使用Gaussian的`polar=DCSHG`任务。输入文件必须包含`#P`标志，溶剂环境通过`scrf=solvent=...`（如IEFPCM）指定，频率通过文件末尾的波长值（如`1064nm`）结合`CPHF=rdfreq`定义。

---

## 5. Multiwfn解析Gaussian极化率数据

启动Multiwfn并载入Gaussian输出文件后，依次选择主功能200、子功能7解析极化率信息。需切换至含频模式(-1)，选择计算级别(1)并载入对应频率的数据(2)，最后指定考察形式为$\beta(-2\omega;\omega,\omega)$(2)。

---

## 6. Multiwfn输出HRS参数含义

Multiwfn计算结果直接给出$\beta_{HRS}$、退偏比DR、$<\beta^2_{ZZZ}>$等量。程序还会输出偶极和八极贡献的模及百分比($\phi$)、各向异性参数$\rho$以及$\beta$矢量在偶极矩上的投影等数据，默认单位为a.u.。

---

## 7. 计算结果与文献对比验证

在HF/daug-cc-pVTZ/IEFPCM(CH2Cl2)级别及1064nm波长下计算CH2Cl2，$\beta_{HRS}$和DR的计算结果分别为20.911和3.16。该结果与J. Chem. Phys. 136, 024506 (2012)文献中的数据(20.90和3.12)高度相符。

---

## 8. 导出散射光强度随角度变化数据

在Multiwfn计算界面输入`y`并输入起始角度（如-180），程序将生成`HRS_angle.txt`文件。该文件包含$\Psi$从起始值开始每增加1度对应的散射光强度值，可用于绘图分析。

---

## 9. 散射光强度数据的可视化

将`HRS_angle.txt`导入Origin，使用Plot - Polar theta(X)r(Y)可绘制极坐标图。图中径向距离代表散射强度，角度代表$\Psi$值，曲线形状反映了分子的非线性光学各向异性特征。
