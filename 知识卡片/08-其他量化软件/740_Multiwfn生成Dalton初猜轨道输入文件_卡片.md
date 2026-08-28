---
id: 740
title: 利用Multiwfn令Dalton计算时使用其它程序产生的轨道作为初猜
url: http://sobereva.com/740
domain: 其他量化软件
topic: Multiwfn生成Dalton初猜轨道输入文件
cards: 8
---

# Multiwfn生成Dalton初猜轨道输入文件 — 知识卡片

## 1. Dalton程序使用外部轨道作为初猜的背景与功能

自2025-Apr-5更新的Multiwfn版本开始，支持将当前载入的轨道波函数写入Dalton的输入文件.dal中作为初猜波函数，解决了Dalton在SCF收敛方面表现不佳且无法产生UHF计算产生的UNO轨道等特定轨道的问题。借助此功能，Dalton用户可以使用Gaussian、ORCA、GAMESS-US等程序产生的波函数作为初猜，也可以直接使用Multiwfn产生的UNO、定域化分子轨道（LMO）等作为CASSCF初猜。若此功能对研究有帮助，请在论文中引用Multiwfn启动时提示的原文文献。

---

## 2. 使用Gaussian HF波函数作为Dalton CCSD(T)计算初猜的步骤

首先用Gaussian进行HF/cc-pVTZ单点计算（需使用`int=NoBasisTransform`关键词），将得到的.chk文件用formchk转为.fch文件。启动Multiwfn载入.fch文件，依次输入`100`（其它功能）、`2`（产生输入文件）、`19`（产生Dalton输入文件），输入输出文件名后选择`y`将轨道展开系数写入.dal文件，并选择格式`1`（Dalton标准格式4F18.14）。将生成的.mol文件中的基组名修改为`cc-pVTZ_emsl`，并修改.dal文件中的设置为CCSD(T)计算，加入`.MOSTART`和`FORM18`关键词及`**MOLORB`部分的轨道系数。

---

## 3. 传输波函数至Dalton时的基组与泛函注意事项

将Gaussian的cc-pVDZ、cc-pVTZ波函数作为Dalton初猜时，Dalton必须使用`cc-pVDZ_emsl`、`cc-pVTZ_emsl`基组以避免收敛困难（结果与不带后缀版本一致）。对于def、def2系列基组（如def2-TZVP），在Dalton中应写作对应基组库文件名（如Turbomole-TZVP、def2_tzvp）。Dalton默认基于球谐型基函数计算，若Gaussian使用6-31G*等默认笛卡尔型基函数，必须使用`5d`关键词强制使用球谐型，否则Multiwfn写入初猜轨道系数的功能不支持此情况。

---

## 4. 使用Gaussian DFT波函数作为Dalton DFT计算初猜的示例

以顺铂体系为例，使用Gaussian的PBE0/genecp（含`int=NoBasisTransform`）计算得到波函数，通过Multiwfn生成Dalton输入文件。在Dalton的.mol文件中需正确设置基组和赝势，例如Pt使用`stuttgart_rsc_1997_ecp`基组和赝势。计算结果显示，使用外部初猜后Dalton经过4轮SCF收敛，能量为-1152.597056，与Gaussian结果-1152.596983非常接近。

---

## 5. 使用UNO轨道作为Dalton CASSCF计算初猜的步骤

首先用Gaussian进行UHF/6-31G*计算（使用`guess=mix`和`5d`），将.chk转为.fch并载入Multiwfn。依次输入`200`、`16`，选择`SCF`密度矩阵并产生空间自然轨道（输入`1`），确认HONO和LUNO占据数显著偏离整数后，输入`n`不导出文件。返回主菜单后通过`100` -> `2` -> `19`生成Dalton输入文件，选择写入当前轨道（即UNO）。修改.dal文件，将DFT设置替换为CASSCF配置，如设置`.CAS SPACE`为2，`.ELECTRONS`为2，`.INACTIVE`为15。

---

## 6. 解决线性依赖基函数导致轨道数不匹配的方法

若存在线性依赖导致Gaussian的`NBsUse`小于`NBasis`，可采取两种方法：(1) 不去除线性依赖：Gaussian使用`IOp(3/32=2)`，Dalton在`**WAVE FUNCTIONS`中加入`*ORBITAL`和`.AO DELETE 1E-100`，但这可能导致数值不稳定；(2) 允许去除线性依赖并让Dalton少读轨道：若Gaussian去除了4个基函数，Multiwfn导出的.dal文件中最后4个轨道系数为0，此时需在Dalton的`*ORBITAL`中加入`.DELETE 4`，使Dalton忽略最后4个轨道以避免报错。

---

## 7. 解决Dalton无法读取.dal中星号格式轨道系数的问题

若.dal文件中轨道展开系数因数值过大超出F18.14格式上限而显示为星号导致Dalton报错，需在Multiwfn导出时选择格式`2`（4E20.12科学计数法）。同时必须修改Dalton源代码：对于Dalton 2022版，修改`DALTON/sirius/sirgp.F`文件，将`PFMT = '(4F18.14)'`替换为`PFMT = '(4E20.12)'`，然后重新编译程序。

---

## 8. Multiwfn与MOKIT程序在传轨道功能上的对比

Multiwfn不需要Python环境（解压即用），专门解决了.dal记录轨道系数的格式问题，且自身能产生定域化分子轨道、自然轨道、NTO等多种轨道作为Dalton初猜。MOKIT的fch2dal子程序则能将fch里的基组、赝势定义直接写入.mol文件，支持Gaussian使用的但在Dalton中未自带的基组，并且支持笛卡尔型基函数的情况。
