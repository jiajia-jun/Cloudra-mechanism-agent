---
key: b685
title: 使用sobEDA和sobEDAw方法做非常准确、快速、方便、普适的能量分解分析
url: http://sobereva.com/685
domain: 波函数与电子结构分析
source: blog
year: 2023
cards: 30
---

# 使用sobEDA和sobEDAw方法做非常准确、快速、方便、普适的能量分解分析 — 知识卡片

## 1. sobEDA与sobEDAw方法概述

sobEDA和sobEDAw是基于色散校正DFT理论的能量分解分析方法，旨在将体系中片段间的相互作用能分解为不同物理成分。这两种方法结合Gaussian和Multiwfn程序实现，具有耗时低、使用简单、普适性强、精度好和物理意义清晰的特点。sobEDAw是sobEDA的变体，专门用于考察弱相互作用，其色散项定义与SAPT方法具有可比性。相关方法已发表在J. Phys. Chem. A, 127, 7023 (2023)。

---

## 2. sobEDA方法的能量项定义

sobEDA方法将相互作用能$\Delta E_{int}$分解为六个物理成分：$\Delta E_{els}$（经典静电作用能）、$\Delta E_{x}$（交换作用能）、$\Delta E_{DFTc}$（DFT相关能）、$\Delta E_{dc}$（色散校正能）、$\Delta E_{rep}$（Pauli互斥能）和$\Delta E_{orb}$（轨道相互作用能）。其中$\Delta E_{x}$与$\Delta E_{rep}$常合并为交换-互斥项$\Delta E_{xrep}$，$\Delta E_{DFTc}$和$\Delta E_{dc}$可合并为库仑相关项$\Delta E_{c}$。各项加和精确等于色散校正DFT方法计算的超分子相互作用能。

---

## 3. 色散校正项$\Delta E_{dc}$的物理意义

在sobEDA实现中，色散校正项$\Delta E_{dc}$由DFT-D3(BJ)方法计算。仅当使用完全无法描述色散作用的泛函（如BLYP、B3LYP、BHandHLYP）时，$\Delta E_{dc}$才能明确解释为纯色散作用能。对于本身能描述部分色散作用的泛函（如PBE、PBE0、M06-2X），$\Delta E_{dc}$仅补充描述了泛函未能涵盖的长程库仑相关部分。

---

## 4. sobEDAw方法的定义与参数

sobEDAw是为了与SAPT方法结果对比而提出的变体，其能量分解公式为$\Delta E_{int} = \Delta E_{els} + \Delta E_{xrep} + \Delta E_{orb} + \Delta E_{disp}$。sobEDAw通过引入系数$w$组合sobEDA的$\Delta E_{dc}$和部分$\Delta E_{DFTc}$来定义$\Delta E_{disp}$，参数$c$、$a$、$r$针对特定泛函/基组组合拟合，目标是使$\Delta E_{disp}/\Delta E_{els}$比例与DFT-SAPT在S66测试集上的结果一致。

---

## 5. sobEDAw推荐基组与精度

使用B3LYP-D3(BJ)进行sobEDAw分析时，推荐基组的选择取决于精度需求和耗时考虑。6-31+G(d,p) w.CB是经济首选，平均绝对误差（MAE）为0.26 kcal/mol；追求更高精度推荐使用6-311+G(2d,p) w.CB；对于元素覆盖广的情况推荐def2-TZVP w.CB或其简化版def2-TZVP(-f) w.CB。上述基组与DFT-SAPT的平均绝对百分比误差（MAPE）约为6%。

---

## 6. sobEDAw适用的泛函限制

sobEDAw计算使用的泛函和基组组合必须具有现成的$c$、$a$、$r$拟合参数。已支持参数的泛函包括B3LYP-D3(BJ)、TPSS-D3(BJ)、TPSSh-D3(BJ)、BLYP-D3(BJ)和BHandHLYP-D3(BJ)。PBE、PBE0和M06-2X等对色散作用描述较充分的泛函不适用于sobEDAw，因为无法拟合出合理参数。

---

## 7. sobEDA适用的泛函与基组

sobEDA原则上可结合任意非双杂化泛函和任意基组使用，不依赖经验参数。泛函选择上，一般体系可用B3LYP-D3(BJ)，过渡金属配合物推荐TPSSh-D3(BJ)或PBE0-D3(BJ)。基组方面，主族元素可用6-311G(d,p)，过渡金属可用SDD赝势及其标配基组，高精度需求可选用def2-TZVP。sobEDA允许使用混合基组。

---

## 8. 范围分离泛函的限制

sobEDA和sobEDAw目前不能结合ωB97XD、CAM-B3LYP等范围分离泛函使用。这一限制源于Gaussian程序的Link 608模块在处理范围分离泛函时无法输出总能量中的各种必要成分，导致sobEDA.sh脚本无法提取所需信息。

---

## 9. sobEDA.sh脚本的运行环境要求

运行sobEDA.sh脚本必须满足特定环境要求：必须是Linux环境（包括虚拟机或WSL）；已安装G16 A.03及以后版本；已安装2023-Jun-25以后更新的Multiwfn程序；系统中必须可用dos2unix命令。这些条件确保脚本能够正确调用Gaussian进行计算并使用Multiwfn进行波函数分析。

---

## 10. sobEDA.sh脚本的输入文件

运行sobEDA.sh脚本需在当前目录下准备三个输入文件：system.xyz包含整个体系的结构；fragment.txt定义各片段的原子序号、净电荷和自旋多重度；template.gjf是生成Gaussian输入文件的模板。脚本启动后会自动调用Gaussian和Multiwfn进行计算和数据提取。

---

## 11. sobEDA.sh脚本的关键设置

sobEDA.sh脚本中的关键设置包括gau和mwfn变量（定义Gaussian和Multiwfn的调用命令）、sobEDAw变量（0为sobEDA，1为sobEDAw）和iCP变量（0为不使用counterpoise校正，1为使用）。分析弱相互作用时强烈建议设置iCP=1以改进结果，而分析化学键作用时不建议使用iCP=1。

---

## 12. system.xyz 文件定义

system.xyz 文件包含当前整个体系的原子坐标。该文件可通过 Multiwfn 载入 pdb、mol、mol2 等主流格式文件生成，或从 Gaussian/ORCA 优化输出文件中读取最后一帧结构，在主界面输入 xyz 并指定文件名即可输出。
- 参考链接: http://原作者.com/477, http://原作者.com/379

---

## 13. fragment.txt 文件格式

fragment.txt 文件用于定义能量分解的片段数量、各片段对应的原子序号、净电荷及自旋多重度。所有片段中原子序号的并集必须对应整个体系，首行数字代表片段数量，随后每两行定义一个片段的电荷/多重度及原子序号范围。
- 示例: "3" 代表3个片段，"0 1" 代表电荷0、多重度1，"1-3,7,10-12" 代表原子序号。

---

## 14. 自旋多重度负值含义

在 fragment.txt 文件中，将自旋多重度设置为负值表示该片段的单电子为 beta 自旋。例如 "0 -3" 表示该片段处于三重态，且单电子自旋方向为 beta。

---

## 15. template.gjf 文件构成

template.gjf 是 Gaussian 输入文件的模板，包含计算关键词、电荷、多重度及坐标占位符 [geometry]。#P 和 nosymm 关键词必须存在，ExtraLinks=L608 及文件末尾的数字用于输出能量成分供脚本提取。

---

## 16. template.gjf 末尾数字设置

template.gjf 末尾的第一个数字对应泛函在 Gaussian 中的 IOp(3/74) 参数，必须根据实际泛函查阅手册设置。第二个数字（通常为 5）指定 Link 608 模块使用 ultrafine 积分格点，一般无需修改。
- 常见泛函参数: -5 (B3LYP), -55 (M06-2X), -35 (TPSSh), 1009 (PBE)。

---

## 17. 泛函 D3(BJ) 参数处理

部分泛函（如 TPSSh）在 Gaussian 中未内置 DFT-D3(BJ) 参数，需按照规范在输入文件中自行定义。若不希望使用色散校正，可去掉 em=gd3bj 关键词，此时输出的色散校正项将为 0。

---

## 18. sobEDA 并行计算设置

sobEDA.sh 计算时的并行核数和内存上限可通过 Gaussian 的 Default.Rou 文件设置（如 -P- 96），或直接在 template.gjf 中使用 %nproc 和 %mem 指定。

---

## 19. 相互作用能计算差异原因

sobEDA.sh 输出的总相互作用能与手动计算（整体能量减去片段能量）不符，通常源于几何结构、基组、泛函、积分格点精度、溶剂模型、Counterpoise 校正或电荷/多重度设置的不一致，亦或是波函数收敛至不同解。

---

## 20. sobEDA 溶剂模型使用限制

sobEDA/sobEDAw 定义为真空下的相互作用能分解，不能直接在 template.gjf 中添加 scrf 关键词。若需考虑溶剂效应，需分别计算真空和溶剂下的单点能，通过运算获得溶剂对相互作用能的贡献。

---

## 21. sobEDA.sh 运行报错排查

sobEDA.sh 运行出错或结果异常时，应根据输出信息定位具体出错环节。常见原因包括 Multiwfn/Gaussian 版本过旧、dos2unix 命令不可用、fragment.txt 设置错误、内存不足或 template.gjf 中存在不兼容关键词（如 scf=QC）。

---

## 22. 大体系计算内存设置

对于数百原子的大体系，Gaussian 自带的 formchk 和 unfchk 工具可能因内存上限不足导致转换失败。解决方法是在用户主目录的 .bashrc 文件中添加 export GAUSS_MEMDEF=20GB 以增加可用内存。

---

## 23. 自定义与混合基组报错

使用自定义基组、混合基组或引用外部基组文件时出错，通常是因为格式定义不正确。需参考相关文档确保 gen/genecp 格式正确，且外部基组文件末尾不能有空行，以免干扰 Gaussian 读取后续参数。

---

## 24. 不支持泛函的处理策略

若使用的双杂化泛函或 M06-2X 等方法未被 sobEDAw 直接支持，可使用这些方法计算相互作用能数值，而利用 sobEDAw 支持的泛函（如 B3LYP-D3(BJ) 或 BHandHLYP-D3(BJ)）进行能量分解分析以获得物理成分 insight。

---

## 25. 体系片段选择性分析

若体系包含三个部分但仅需分析其中两部分间的相互作用能，可移除第三部分并将剩余部分定义为两个片段进行计算。此举忽略了被移除部分对这两个片段的极化作用，但对弱相互作用影响通常较小。

---

## 26. SCF 不收敛解决方案

在 sobEDA 计算中若遇到 SCF 不收敛，可在 template.gjf 中添加辅助收敛关键词（如 scf(novaracc,noincfock,conver=6)）。禁止使用 scf=QC、scf=XQC 或 guess=AM1 等不兼容关键词。
- 参考链接: http://原作者.com/61

---

## 27. 片段 SCF 不收敛的外部初猜

若片段计算 SCF 不收敛且已知特定波函数可作为初猜，可按照官方教程（2025-03-25 后更新版本）第6节的方法，让 sobEDA.sh 读取外部提供的 chk 文件中的收敛波函数作为初猜进行计算。

---

## 28. 能量成分输出溢出处理

当体系含有较多重原子且使用全电子基组时，Gaussian 输出的能量成分可能因数值过大显示为星号（ENTVJ=************）导致脚本无法读取。解决方法是将这些原子改用赝势基组，以减小绝对能量数量级。

---

## 29. 实例：H2O...NH3 能量分解

对 H2O...NH3 体系在 B3LYP-D3(BJ)/6-311+G(2d,p) w.CB 级别下进行 sobEDAw 分析，结果显示总相互作用能为 -7.18 kcal/mol。静电作用（-12.15 kcal/mol）是主要吸引项，轨道相互作用（-5.38 kcal/mol）次之，色散贡献（-3.43 kcal/mol）最小。
- 数据吻合性: 与 SAPT2+(3)δMP2 高精度计算结果及各分量比例高度一致。

---

## 30. sobEDA 引用规范

发表的研究工作中使用 sobEDA 或 sobEDAw 方法时，必须引用方法原文 J. Phys. Chem. A, 127, 7023 (2023)。由于脚本依赖 Gaussian 和 Multiwfn，同时也需按照程序要求正确引用这两款软件。
