---
id: 685
title: 使用sobEDA和sobEDAw方法做非常准确、快速、方便、普适的能量分解分析
domain: 波函数与电子结构分析
topic: sobEDA与sobEDAw能量分解分析原理及脚本使用
cards: 14
---

## 1. sobEDA和sobEDAw方法的出处与核心优势
sobEDA和sobEDAw是基于色散校正DFT理论的能量分解分析方法，发表在 *J. Phys. Chem. A*, 127, 7023 (2023)。sobEDA.sh脚本结合Gaussian和Multiwfn程序实现，具有门槛低、速度快（耗时仅约为DFT单点能计算的两倍）、普适性强（适用于闭壳层/开壳层、主族/过渡金属、弱相互作用/化学键）、物理意义清晰且准确的特点。对于Gaussian用户，sobEDA提供了无需额外代价即可进行EDA的方法。

---

## 2. sobEDA方法的能量组成定义与物理含义
sobEDA将色散校正DFT计算的相互作用能 $\Delta E_{int}$ 分解为 $\Delta E_{int} = \Delta E_{els} + \Delta E_{x} + \Delta E_{DFTc} + \Delta E_{dc} + \Delta E_{rep} + \Delta E_{orb}$。各分量含义为：$\Delta E_{els}$ 为经典静电作用能；$\Delta E_{x}$ 为交换作用能（数值为负）；$\Delta E_{DFTc}$ 为DFT相关能（数值为负）；$\Delta E_{rep}$ 为Pauli互斥能（数值为正）；$\Delta E_{orb}$ 为轨道相互作用能（数值为负，体现极化和电荷转移）；$\Delta E_{dc}$ 为色散校正能。$\Delta E_{x}$ 与 $\Delta E_{rep}$ 可合并为交换-互斥项 $\Delta E_{xrep}$，$\Delta E_{DFTc}$ 与 $\Delta E_{dc}$ 可合并为库仑相关项 $\Delta E_c$。

---

## 3. sobEDA中色散校正项 $\Delta E_{dc}$ 的物理意义限制
在sobEDA中，$\Delta E_{dc}$ 的物理意义取决于泛函描述色散的能力。仅当使用的泛函完全无法描述色散作用时（如BLYP、B3LYP、BHandHLYP），结合D3(BJ)校正后的 $\Delta E_{dc}$ 才能被明确解释为色散作用能。对于本身能描述部分色散作用的泛函（如PBE、PBE0、M06-2X），$\Delta E_{dc}$ 仅是对DFT未涵盖部分的补充。

---

## 4. sobEDAw方法的设计目的与计算公式
sobEDAw是sobEDA的变体，专门用于弱相互作用分析，旨在使色散/静电比例与SAPT方法可比。其能量分解公式为 $\Delta E_{int} = \Delta E_{els} + \Delta E_{xrep} + \Delta E_{orb} + \Delta E_{disp}$。sobEDAw引入系数 $w$ 将sobEDA的 $\Delta E_{dc}$ 和部分 $\Delta E_{DFTc}$ 组合成 $\Delta E_{disp}$，剩余部分归入 $\Delta E_{xrep}$。系数 $w$ 和参数 $c, a, r$ 通过拟合S66测试集与DFT-SAPT数据确定，使得 $\Delta E_{disp}/\Delta E_{els}$ 比例与SAPT高度一致。

---

## 5. sobEDAw推荐的基组与泛函组合及精度
对于B3LYP-D3(BJ)泛函，推荐的基组及性能（相对于CCSD(T)/CBS的MAE）如下：6-31+G** w.CB (MAE=0.26 kcal/mol)、6-311+G(2d,p) w.CB (更优精度)、def2-TZVP w.CB (元素覆盖广)、def2-TZVP(-f) w.CB (性价比高)。这些组合与DFT-SAPT的色散/静电比例平均绝对百分比误差（MAPE）约为6%。在96核服务器上，对18+224原子的体系做sobEDAw仅需71分钟。

---

## 6. sobEDAw适用的泛函范围及不适用情况
sobEDAw计算需要现成的 $c, a, r$ 参数，目前支持B3LYP-D3(BJ)、TPSS-D3(BJ)、TPSSh-D3(BJ)、BLYP-D3(BJ)、BHandHLYP-D3(BJ)结合特定基组。PBE、PBE0、M06-2X等泛函因本身能较好描述色散，无法拟合出合理的sobEDAw参数，故不支持。如需使用其它级别，需自行拟合参数。

---

## 7. 泛函和基组的选择建议
做sobEDAw分析时，默认推荐B3LYP-D3(BJ)；对于大共轭体系建议用BHandHLYP-D3(BJ)；对于过渡金属配合物建议用TPSSh-D3(BJ)。基组方面，准定量准确用6-31+G(d,p) w.CB，高精度用6-311+G(2d,p) w.CB，未定义元素用def2-TZVP w.CB或def2-TZVP(-f) w.CB。做sobEDA分析时，泛函和基组选择更自由，一般用B3LYP-D3(BJ)或TPSSh-D3(BJ)/PBE0-D3(BJ)，基组可用6-311G(d,p)或def2-TZVP。两种方法均不支持范围分离泛函（如ωB97XD、CAM-B3LYP），因Gaussian Link 608模块无法提取其能量成分。

---

## 8. sobEDA.sh脚本的使用环境要求
运行sobEDA.sh脚本需要满足：(1)Linux环境（包括WSL或虚拟机）；(2)已安装Gaussian (G16 A.03及以后)；(3)已安装Multiwfn (2023-Jun-25及以后的版本)；(4)系统可用dos2unix命令。脚本通过结合Gaussian和Multiwfn自动进行计算、提取和处理数据。

---

## 9. sobEDA.sh脚本的运行流程与输入文件
运行sobEDA.sh需：(1)赋予脚本可执行权限；(2)修改脚本内的设置（如Gaussian和Multiwfn路径、sobEDAw参数）；(3)在当前目录放置system.xyz（体系坐标）、fragment.txt（片段定义）、template.gjf（Gaussian输入模板）。启动脚本后，将自动生成并计算fragment、promol、frozen、final等状态的Gaussian任务，最终输出能量分解结果。中间产生的gjf、out、chk/fch文件会保留。

---

## 10. fragment.txt文件的格式与自旋多重度定义
fragment.txt定义片段数量、原子归属、电荷和自旋多重度。第一行为片段数，随后每两行定义一个片段：第一行为电荷和自旋多重度，第二行为原子序号。自旋多重度写为负值时表示片段带beta单电子。所有片段的原子并集必须覆盖整个体系。

---

## 11. template.gjf文件的编写要求
template.gjf是Gaussian输入文件的模板，必须包含#P、nosymm和ExtraLinks=L608关键词。文件末尾需有两个数字，第一个对应泛函的IOp(3/74)值（如B3LYP为-5，PBE0为-13，TPSSh为-35），第二个数字通常为5（代表ultrafine积分格点）。坐标部分用[geometry]占位符。若泛函的D3(BJ)参数未内置，需手动定义。

---

## 12. SCF不收敛问题的解决策略
若计算中遇到SCF不收敛，可在template.gjf中加入scf(novaracc,noincfock,conver=6)等辅助收敛关键词，但禁止使用scf=QC、scf=XQC和guess=AM1等不兼容关键词。若片段计算不收敛，可按官方教程第6节方法读取外部收敛波函数作为初猜；若准分子或最终态不收敛，则无法读取外部初猜。

---

## 13. 能量结果不一致的排查方法
若sobEDA.sh给出的总相互作用能与手动计算不符，原因可能包括：几何结构/基组/泛函/溶剂模型/积分格点不一致、Counterpoise校正差异、波函数收敛状态不同。排查方法包括对比sobEDA.sh生成的fragment.out和final.out与手动计算的能量，确保对应相同的波函数。若整体计算波函数不同，可将手动算的整体能量与final.out中第一次SCF能量（冻结态）之差作为 $\Delta E_{orb}$，其余项保持不变。

---

## 14. 实例：H2O...NH3的sobEDAw分析结果
对H2O...NH3体系在B3LYP-D3(BJ)/6-311+G(2d,p) w.CB级别进行sobEDAw分析，得到总相互作用能为-7.18 kcal/mol。sobEDA分量为：$\Delta E_{els}$=-12.15, $\Delta E_{xrep}$=13.88, $\Delta E_{orb}$=-5.38, $\Delta E_{disp}$=-3.43。分析表明该氢键由静电主导（占吸引作用的58%），其次是轨道相互作用（26%），色散贡献最小。该结果与高阶SAPT2+(3)δMP2计算结果吻合极好，色散/静电比例分别为0.282和0.276。
