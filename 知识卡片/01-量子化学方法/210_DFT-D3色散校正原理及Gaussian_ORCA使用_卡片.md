---
id: 210
title: DFT-D色散校正的使用
url: http://sobereva.com/210
domain: 量子化学方法
topic: DFT-D3色散校正原理及Gaussian_ORCA使用
cards: 1
---

# DFT-D3色散校正原理及Gaussian_ORCA使用 — 知识卡片

## 1. DFT-D色散校正的原理与必要性

传统交换-相关泛函（如B3LYP、PBE、PW91）由于相关势的长程行为不对，完全不能描述色散作用，而用于研究物理吸附、长链烷烃构象等色散主导的问题时结果差；引入经验的色散校正项可立竿见影地改进色散作用描述，且有助于改进热力学性质计算。DFT-D3支持从H到Pu的元素，几乎不增加计算耗时，如今几乎所有主流量子化学程序都支持。
参考文献：JCP,132,154104(2010)

## DFT-D系列的发展
DFT-D系列包括DFT-D1（2004）、DFT-D2（2006）和DFT-D3（2010）。DFT-D3比DFT-D2更严谨，精度更好，支持元素更多；DFT-D4（2017）则考虑了实际电子结构对色散校正能的影响，但计算复杂，支持程序较少。B3LYP-D3校正能使二聚体相互作用能计算结果与金标准CCSD(T)定性一致，而未校正的B3LYP无法得到稳定构型。

## DFT-D3的零阻尼形式
基于零阻尼的DFT-D3校正能公式为：
$$E_{\text{disp}} = -\sum_{A<B} \frac{C_{6,AB}}{R_{AB}^6} f_{damp}(R_{AB}) s_6 + \sum_{A<B} \frac{C_{8,AB}}{R_{AB}^8} f_{damp}(R_{AB}) s_8$$
其中阻尼函数为：
$$f_{damp}(R_{AB}) = \frac{1}{1 + e^{-\gamma (R_{AB} - R_0,AB)/s_{r,n}}}$$
对普通泛函，s8和sr,6为拟合参数，s6和sr,8固定为1。

## DFT-D3的BJ阻尼形式
基于BJ阻尼的DFT-D3校正能公式为：
$$E_{\text{disp}} = -\sum_{A<B} \frac{C_{6,AB}}{R_{AB}^6} \frac{1}{1 + e^{-\gamma (R_{AB} - R_0,AB)/s_{r,n}}} + \sum_{A<B} \frac{C_{8,AB}}{R_{AB}^8} \frac{1}{1 + e^{-\gamma (R_{AB} - R_0,AB)/s_{r,n}}} s_8$$
BJ阻尼使得中近程校正能虽小却不为0，适用于HF；零阻尼适用于M06-2X等已表现中程相关的泛函。三体项一般不考虑，除非是大体系。

## 使用Grimme的dftd3独立程序
Grimme的DFT-D3程序可计算校正能及导数。Linux下使用命令：
`./dftd3 test.xyz -func b-lyp -bj`
输出校正能：
`Edisp /kcal,au: -3.3486 -0.00533628`
定义片段需创建`fragment`文件：
```
2-4
1,6
```
输出结果示例：
`group 1 -- 1 -0.74`

## Gaussian中的DFT-D3支持与使用
Gaussian03不支持DFT-D；Gaussian09支持自带DFT-D2的泛函（B97D、wB97XD等）；Gaussian09 D.01及之后直接支持DFT-D3（GD3或GD3BJ）。
使用方法：
`# B3LYP/aug-cc-pVDZ EmpiricalDispersion=GD3BJ opt`
简写为`em=GD3BJ`。
G09支持B2PLYPD3、B97D3、mPW2PLYPD3等自带D3的泛函。
**注意事项**：G09 D.01版频率计算色散校正不完全准确，建议零阻尼优化，或使用E.01版；G16需通过IOp(3/174-178)自定义参数，如用MN15-D3(BJ)：
`MN15 em=GD3BJ IOp(3/174=1000000,3/175=786200,3/177=2097100,3/178=7592300)`

## ORCA中的DFT-D3使用
ORCA 4.1及以后支持DFT-D4。
启用DFT-D3：
`! B3LYP TZVP d3`
使用RI技术加速（推荐用于大体系）：
`! BLYP-TZVP def2-SVP/J RIJK d3`
三体项需添加`ABC`。
ORCA中的B2PLYP-D3、mPW2PLYP-D3可直接调用。

## GAMESS-US中的DFT-D3使用
在`$DFT`部分写入：
`DC=.T.`
`IDCVER=1/2/3/4`分别对应D1/D2/D3(0)/D3(BJ)。
默认不计算三体项，需写`DCABC=.T.`。
`DFTTYP=B97-D`或`wB97X-D`可直接调用。
