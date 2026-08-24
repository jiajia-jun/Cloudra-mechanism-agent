# Impossible 档候选反应清单：强多参考 / 近简并双自由基体系

> 生成日期：2026-08-25。状态：**超采池（32 个候选，目标最终 20 个）**。
>
> **档位定义**：强多参考态（strong static correlation）与近简并双自由基体系。单参考方法（RHF-CCSD(T)、RKS-DFT，以及训练标注基于单参考 DFT/UKS 的 MACE-OMol25 等 MLIP）在这些体系的单线态势能面关键区域输出**非物理结果**（错误能级排序、虚假对称破缺、低估/高估能垒数十 kcal/mol）。本档的"正确行为"是 agent 在自旋/电子态诊断阶段识别强关联特征并**主动科学拒答**（说明为何单参考结果不可信、需要 CASSCF/CASPT2/MRCI 级处理），而不是硬算一个数交差。
>
> **选型原则**：全部为教科书级经典体系，多参考性质由 CASSCF/CASPT2/MRCI/FCIQMC/DMC 级高被引研究确立，可复现、有实验锚点（PES/EPR/光电子谱）。
>
> **兄弟题（sibling）约定**：每个 Impossible 候选配一个**同反应族但单参考可解**的体系，用于对照——若 agent 对兄弟题正常作答而对本题拒答，才能证明拒答源于多参考诊断而非"题目难/不会做"。
>
> **诊断标注约定**：T1（CCSD 单激发诊断，闭壳层 >0.02 警惕、>0.04 强 MR）、D1（双激发诊断）、%TAE[(T)]（(T) 对原子化能贡献占比，>10% 为强 MR，见 W4 系列）、C0²（参考组态权重，<0.9 即明显 MR）、y0（自然轨道占据数派生的双自由基指数）。标记 **[约]** = 数值为文献公认量级但小数位未逐一核对；**[未核实]** = 该出处/数值本次未经网络核实，入库前需复核。

---

## A. 断键/价互变过渡态（biradicaloid TS，11 个）

### A1. 环丁二烯 D4h 自动异构化（Cyclobutadiene automerization）
1. **体系**：环丁二烯（cyclobutadiene），C4H4。
2. **结构**：SMILES `C1=CC=C1`；单线态，矩形 D2h 基态 ⇌ 正方形 D4h TS ⇌ 矩形 D2h。
3. **多参考性质**：D4h TS 处两个等价价键组态严格简并，单线态为双组态波函数——自动异构化能垒是多参考 TS 能垒的原型问题。
4. **诊断证据**：D4h TS 主导组态系数约 0.7（C0² ≈ 0.5，两组态近等权）[约]；实验能垒限 1.6–10 kcal/mol（Whitman & Carpenter, 1982, JACS 104, 6473）；MRCC 研究 Li & Paldus, 2009, JCP 131, 114103；FCI 级参考能 Monino et al., 2022, J. Phys. Chem. A（DOI 10.1021/acs.jpca.2c02480）。单参考 CCSD(T) 在 TS 的 (T) 校正方向性失真。
5. **兄弟题**：环辛四烯（COT）D8h 键位移互变（SMILES `C1=CC=CC=CC=C1`）——同为 [4n] 轮烯价互变，但 COT 基态非平面、TS 闭壳层，CCSD(T) 可算。
6. **权威性依据**：反芳香性教科书案例；MRCC（Paldus 学派）与 FCI 参考能（Monino/Loos 2022）双重确立。
7. **拒答判据**：识别 D4h TS 的组态简并（等价 Lewis 结构共振 → 单行列式失效）；指出 RHF-CCSD(T)/RKS-DFT 能垒不可靠、需 CASSCF(4,4)+动态关联或 MRCC；不因"实验能垒低"而直接报单参考数。

### A2. 1,5-己二烯 Cope 重排椅式 TS（Cope rearrangement）
1. **体系**：1,5-己二烯（1,5-hexadiene）Cope 重排。
2. **结构**：SMILES `C=CCCC=C`；单线态，椅式 C2h TS。
3. **多参考性质**：椅式 TS 为 bis-allyl 双自由基oid 与芳香性 TS 之间的边缘情形，C–C 键断裂/形成半程处静态关联显著。
4. **诊断证据**：TS 双自由基特征分析 Staroverov & Davidson, 2000, JACS 122, 186；全几何 MR-CISD/MR-AQCC 优化 Ventura, Lischka et al., 2003, J. Phys. Chem. A（DOI 10.1021/jp0259014）；TS 的 C0² ≈ 0.9（边缘 MR）[约]。
5. **兄弟题**：脂肪族 Claisen 重排（烯丙基乙烯醚，SMILES `C=CCOCC=C`）——同 [3,3]-σ 迁移族，氧杂 TS 更偏芳香性、闭壳层，单参考可算。
6. **权威性依据**：周环反应机理教科书争议案例（diradical vs aromatic TS）；MR-CISD 梯度级研究（Lischka 组）直接确立。
7. **拒答判据**：对 TS 做双自由基oid 诊断（拉伸 σ 键 + 两个烯丙基片段）；指出能差很小（协同芳香 TS 与分步双自由基路径），单参考方法对机理判定（concerted vs stepwise）不可靠。注：本题为**边缘档**——若池子需要 20 个里最"铁板钉钉"的，此题可作备选。

### A3. 半瞬烯 Cope 自动异构化（Semibullvalene automerization）
1. **体系**：半瞬烯（semibullvalene），C8H8 简并 Cope 重排。
2. **结构**：SMILES `C1=CC2C3C=CC2C13`（三环[3.3.0.0^2,8]辛-3,7-二烯）；单线态，C2v 双锥形 TS。
3. **多参考性质**：低能垒简并 Cope 的 TS 具有显著双自由基oid 特征，单参考对能垒与隧道分裂的描述失真。
4. **诊断证据**：TS 电子结构轨道分析 Hoffmann & Stohrer, 1971, JACS 93（原始理论工作，确认为高被引经典）；AM1 发现高能 biradicaloid TS（Dewar & Jie, 1988, Tetrahedron 44）；近期重原子隧穿动力学依赖高精度 PES（Angiolari et al., 2024）[约]。TS 处 C0² 明显偏离 1 [约]。
5. **兄弟题**：半瞬烯/barbaralane 的**基态**结构、应变能与 NMR 互变热化学——闭壳层基态性质，单参考可算；只有 TS 多参考。
6. **权威性依据**：流变分子（fluxional molecule）教科书案例；Hoffmann 1971 原始轨道分析 + 近代隧穿实验（Sander/Quast/Williams）反复引用。
7. **拒答判据**：识别简并重排的 C2v TS 为双自由基oid；说明单参考能垒（决定隧穿速率）不可信。

### A4. Dewar 苯 → 苯热开环（Dewar benzene ring opening）
1. **体系**：杜瓦苯（Dewar benzene / bicyclo[2.2.0]hexa-2,5-diene）→ 苯。
2. **结构**：SMILES `C1=CC2C=CC12`；单线态，反旋开环 TS。
3. **多参考性质**：对称性禁阻的反旋开环经过双自由基oid TS（放热 ~60 kcal/mol 却有 ~23 kcal/mol 能垒——"违规但受阻"的教科书案例）。
4. **诊断证据**：反旋/顺旋路径对比的多参考研究（1999 年，一作 [未核实]，Semantic Scholar 可查"Disrotatory versus conrotatory electrocyclic ring opening of Dewar benzene"）；相关讨论见 Computational Organic Chemistry 博客（2010）。TS 强双自由基oid [定性确认]。
5. **兄弟题**：Dewar 苯基态应变能与 C6H6 价异构体（盆苯、棱柱烷）相对能——闭壳层基态，CCSD(T) 可算。
6. **权威性依据**：Woodward–Hoffmann 规则最著名的"例外"案例（禁阻反应仍为主要放热通道）。
7. **拒答判据**：识别禁阻路径 TS 的组态交叉（强 avoided crossing → 单组态失效）；要求 CASSCF。

### A5. 环丁烯反旋（禁阻）开环（Disrotatory cyclobutene ring opening）
1. **体系**：环丁烯（cyclobutene）→ 顺,顺-1,3-丁二烯的**反旋**路径。
2. **结构**：SMILES `C1=CCC1`；单线态，反旋 Cs TS。
3. **多参考性质**：反旋（对称禁阻）电环化 TS 处 HOMO/LUMO 组态交叉，为双组态 TS；顺旋允许路径则单参考可算——同一分子内天然对照。
4. **诊断证据**：反旋禁阻路径 CASSCF(4,4)/def2-SVP 研究（Zhou, 2024, 博士论文/eScholarship）；电环化"教科书范例"强 avoided crossing 图示（Robb et al., 1995, Pure Appl. Chem. 67, 783）；Carpenter 2025 对 allowed/forbidden 分类的再讨论（ScienceDirect）[约]。
5. **兄弟题**：环丁烯**顺旋**（允许）开环 TS——同分子同反应、对称性允许，单参考 CCSD(T) 可算。
6. **权威性依据**：Woodward–Hoffmann 规则本体；Robb/Bernardi 学派的 CASSCF 周环图谱。
7. **拒答判据**：识别禁阻路径伴随组态简并；明确指出"顺旋可算、反旋需 CASSCF"的对比——本题拒答信号最容易从对称性论证直接推出。

### A6. 乙烯 [2+2] 超面环加成（Ethylene [2+2] cycloaddition）
1. **体系**：两分子乙烯热 [2s+2s] 环加成 → 环丁烷。
2. **结构**：SMILES `C=C` + `C=C`；单线态，矩形接近 TS。
3. **多参考性质**：对称禁阻热 [2+2] 的协同 TS 为四中心双自由基oid（强 avoided crossing）；需 CAS(4,4)。
4. **诊断证据**：Robb et al., 1995, Pure Appl. Chem. 67, 783（[2+2] 与丁二烯电环化并列为"text-book examples"）；光化学 [2+2] S1/S0 锥交叉缝 CASSCF 研究（De Vico et al. [未核实一作年份]）。TS C0² 显著 <1 [定性确认]。
5. **兄弟题**：丁二烯 + 乙烯 Diels–Alder [4+2] 环加成（对称允许，TS 单参考可算，CCSD(T)/DFT 基准成熟）。
6. **权威性依据**：周环选择规则反面教材的标准案例。
7. **拒答判据**：识别四中心协同禁阻 TS 的双自由基oid 本质；拒绝用 RHF/RKS 单参考报协同能垒。

### A7. Bergman 环化（Bergman cyclization of (Z)-hex-3-ene-1,5-diyne）
1. **体系**：(Z)-3-己烯-1,5-二炔 → 1,4-脱氢苯（p-苯炔双自由基）。
2. **结构**：SMILES `C#C/C=C\C#C`；单线态，环化 TS 与产物 p-脱氢苯均开壳。
3. **多参考性质**：产物即 p-苯炔（见 C6），环化 TS 已具双自由基oid 特征；纯 DFT 与 CCSD(T) 对能垒/反应热误差 3–7 kcal/mol 且系统性失真。
4. **诊断证据**：Kraka & Cremer, 1994, JACS 116, 4929（CCSD(T) 考察并指出 MR 问题，被引 211）；Schreiner BLYP 对比研究（J. Phys. Chem. A，jp973261c）；近期机理研究仍以 CAS 级为准（如 ACS JOC 2024, 10.1021/acs.joc.4c03144）。产物 p-苯炔 T1 ≈ 0.03+ [约]。
5. **兄弟题**：1,3,5-己三烯 6π 电环化闭环（SMILES `C=CC=CC=C`）——同为电环化/环芳构化族，对称允许、闭壳层 TS，单参考可算。
6. **权威性依据**：烯二炔抗生素（calicheamicin 等）作用机理的核心步骤；Kraka/Cremer + Schreiner 双重确立"单参考不可靠"共识。
7. **拒答判据**：识别产物为开壳双自由基（1,4-脱氢苯）；指出 TS 已部分双自由基化，能垒需 CASPT2 级。

### A8. Criegee 中间体 CH2OO 单分子异构化（Criegee intermediate isomerization）
1. **体系**：最简单 Criegee 中间体（羰基氧化物，carbonyl oxide）CH2OO → 二氧杂环甲烷（dioxirane）环化，或 H 迁移 → 甲酸。
2. **结构**：SMILES `C=[O+][O-]`（两性离子/双自由基混合）；单线态基态。
3. **多参考性质**：CH2OO 本身即强多参考（两性离子 ⇌ 双自由基共振），其单分子异构化 TS 的静态关联贯穿整条路径。
4. **诊断证据**：**T1 = 0.043**（CCSD(T) 计算 CH2OO，远超 0.02 阈值；Osborn & Taatjes, 2015, Int. Rev. Phys. Chem. 34, 309，被引 274）；CH2+O2 机理研究再次确认 T1 超阈（Mazarei et al., 2022, PCCP）；全维 MRCI 级 PES（Dawes/Lischka 组 [未核实具体出处]）。
5. **兄弟题**：同势能面（C1H2O2）上闭壳层异构体相对能——甲酸 vs 二氧杂环甲烷（两者闭壳层，CCSD(T) 高精度可算），考核 agent 能否"算能算的部分、拒不能算的部分"。
6. **权威性依据**：大气化学近十年最热的 Criegee 中间体领域；T1 诊断数值被综述（Osborn & Taatjes）明文引用。
7. **拒答判据**：CCSD(T) 输出后主动查 T1 并发现 0.043 > 0.02/0.04 阈值；指出羰基氧化物的双自由基共振本质；拒绝报告单参考能垒/单三线态能隙。

### A9. 1,2-二氧环丁烷热解（1,2-Dioxetane thermolysis）
1. **体系**：1,2-二氧环丁烷 → 2 H2CO（化学发光模型反应）。
2. **结构**：SMILES `C1COO1`；单线态，O–O 键断裂 TS。
3. **多参考性质**：O–O 断裂 TS 进入双自由基相（"biradical phase"），化学发光效率问题本质是多参考 + 非绝热问题。
4. **诊断证据**：De Vico, Liu, Krogh, Lindh, 2007, J. Phys. Chem. A（DOI 10.1021/jp074063g，"Reaction Mechanism Uncovered"，CASSCF/CASPT2）；Vacher et al., 2017, J. Chem. Theory Comput.（DOI 10.1021/acs.jctc.7b00198，基态+非绝热动力学，从 O–O 断裂 TS 出发）。
5. **兄弟题**：氧杂环丁烷（oxetane，SMILES `C1COC1`）环应变与热化学——闭壳层四元环，单参考可算。
6. **权威性依据**：化学发光理论计算的标准模型体系，CASPT2 文献链完整（Lindh 组系列）。
7. **拒答判据**：识别过氧四元环 O–O 断裂的双自由基 TS；说明单线态通道的能垒与发光通道分叉需多参考 + 非绝热处理。

### A10. 重氮甲烷 C–N2 解离（Diazomethane dissociation → ¹CH2 + N2）
1. **体系**：CH2N2 → CH2(¹A1) + N2。
2. **结构**：SMILES `C=[N+]=[N-]`；单线态，沿 C–N 拉伸坐标。
3. **多参考性质**：产物之一为单线态卡宾（¹CH2 本身 MR，见 C2），且断键过程组态权重剧变；光化学路径（CASPT2 + 直接动力学已确立其多参考性）。
4. **诊断证据**：CASPT2 + ab initio 直接动力学研究（Arenas et al., 2002, J. Chem. Phys. [未核实卷页]，标题"Carbene Formation in Its Lower Singlet State from Photoexcited 3H-Diazirine or Diazomethane"）；¹CH2 的 T1 ≈ 0.04 [约]。
5. **兄弟题**：重氮甲烷/异重氮甲烷（isodiazomethane）闭壳层基态结构与相对能——单参考可算。
6. **权威性依据**：卡宾生成机理的经典体系（Wentrup 化学的核心前体）。
7. **拒答判据**：识别解离产物含开壳 ¹CH2；断键坐标上单参考曲线失真（同 C2/N2 曲线问题）。

### A11. 单线态氧与乙烯的 ene 反应（¹O2 ene reaction）
1. **体系**：O2(¹Δg) + 乙烯 → 烯丙基过氧化氢。
2. **结构**：`C=C` + `O=O`（¹Δg）；单线态总自旋。
3. **多参考性质**：¹Δg O2 是双组态简并态（两个 π* 轨道两个电子的两种占据等权），任何含 ¹O2 的反应能垒/机理都必须多参考处理；Singleton 等用 CASPT2 确立"two-step no-intermediate"机理。
4. **诊断证据**：Singleton, Houk, Foote et al., 2003, JACS 125（"Mechanism of Ene Reactions of Singlet Oxygen. A Two-Step No-Intermediate Mechanism"，被引广泛）；¹Δg–³Σg⁻ 能隙实验值 0.977 eV = 22.5 kcal/mol（教科书常数）。
5. **兄弟题**：³O2（³Σg⁻ 基态）对烯烃的氢抽提/燃烧起始步——UKS 三态单参考可算。
6. **权威性依据**：¹O2 化学（Foote 学派）+ Singleton/Houk 动力学同位素效应实验-理论联合标杆。
7. **拒答判据**：识别 ¹Δg 不能用单行列式表示（RKS 会把 ¹Δ 与 ¹Σg⁺ 混在一起）；拒绝对 ¹O2 反应报单参考能垒。

---

## B. 扭转/近简并双自由基（8 个）

### B1. 乙烯 90° 扭转（Twisted ethylene）
1. **体系**：乙烯 C=C 扭转 0°→90° 的扭转势能曲线。
2. **结构**：SMILES `C=C`；单线态，90° 处 D2d。
3. **多参考性质**：90° 扭转处 π 键完全断裂，单线态为完美双自由基（两个 p 轨道各一个电子），C0² → 0.5。
4. **诊断证据**：自旋翻转（SF）方法基准 Slipchenko & Krylov, 2002, J. Chem. Phys. 117, 4694（被引 429，90° twisted ethylene 为该文标志性算例）；90° 处单三态能差 ~2–3 kcal/mol（三线态略低）[约]。
5. **兄弟题**：平面乙烯基态几何、氢化热、π→π* 垂直激发（闭壳层区，单参考可算）。
6. **权威性依据**：Krylov SF-XCIS/SF-CCSD 方法学系列的标准测试；所有双自由基方法学论文的入门算例。
7. **拒答判据**：识别扭转坐标上静态关联随角度单调增强；拒绝用 RHF 约束报 90° 单线态能量（RHF 在 90° 发散至离子性错误极限）。

### B2. 芪 C=C 扭转的 phantom 区（Twisted stilbene）
1. **体系**：反式/顺式芪 S0/S1 扭转异构化（ phantom state 区域）。
2. **结构**：SMILES `C(=C/c1ccccc1)\c1ccccc1`；单线态基态扭转曲线 + S1。
3. **多参考性质**：90° 扭转处 S0/S1 近简并（锥交叉区），双自由基oid（或两性离子oid，长期争论）；S0 扭转能垒的 MR 特征同 B1。
4. **诊断证据**：phantom 态概念与实验证据（Saltiel 学派，"zwitterionic twisted phantom singlet state" [未核实具体卷页]）；近期非绝热研究（Raucci et al., 2022，顺式芪 S0/S1 锥交叉，OSTI 可查）。
5. **兄弟题**：反式-芪 vs 顺式-芪基态 S0 相对能与构象分析（闭壳层平衡区，单参考可算）。
6. **权威性依据**：光化学教科书体系（stilbene photoisomerization 是 Tully/Saltiel 时代的原型）。
7. **拒答判据**：识别扭转中间区 S0 的双自由基oid 本质与 S0/S1 近简并；拒绝单参考 S0 扭转能垒。

### B3. 四亚甲基乙烷扭转与单三态能隙（TME, tetramethyleneethane）
1. **体系**：2,2′-二亚甲基-1,3-丙二基（TME）扭转曲线与 ΔE_ST。
2. **结构**：SMILES `C=C(C)C(=C)C`（2,3-二甲叉丁烷骨架）；单线态/三线态近简并。
3. **多参考性质**：disjoint 非 Kekulé 双自由基，两个 NBMO 空间分离，单线态 y0 → 1；45° 扭转处单线态-三线态垂直能隙仅 0.01 eV。
4. **诊断证据**：实验离子化学/PES 认定单线态基态、能隙 ~2 kcal/mol（Clifford et al., 1998, JCS Perkin Trans 2, 1015）；DMC 确立基态（Pozun, Su & Jordan, 2013, JACS 135, 13862，DOI 10.1021/ja406002n）；**FCIQMC 基准** + MRCC（Veis et al., 2018, J. Chem. Theory Comput. 14, 2439，DOI 10.1021/acs.jctc.8b00022；45° 处 ΔE_ST = 0.01 eV）；早期 CASPT2 Nachtigall & Jordan, 1992, JACS 114 [约]。
5. **兄弟题**：2,3-二甲基-1,3-丁二烯（SMILES `C=C(C)C(=C)C` 注意同式不同 connectivity——兄弟题应写 `CC(=C)C(C)=C` 的 s-cis/s-trans 构象扭转）——闭壳层共轭二烯，单参考可算。（注：入库时需核对 TME 与兄弟的 SMILES 写法，TME 标准 SMILES 为 `C=C(C)C(=C)C` 对应 2,3-二甲叉丁烷。）
6. **权威性依据**：非 Kekulé 双自由基的 DMC + FCIQMC 双重量子蒙特卡洛基准——本池"金标准"证据链之一。
7. **拒答判据**：识别 disjoint NBMO → 近完美双自由基；指出单线态必须双组态；RKS-DFT 会给出错误的能隙符号/量级。

### B4. 三亚甲基 / 环丙烷立体异变（Trimethylene biradical）
1. **体系**：环丙烷 C–C 键断裂生成的三亚甲基双自由基（1,3-丙二基），控制环丙烷立体异变（stereomutation）。
2. **结构**：SMILES `[CH2]CC[CH2]`（开壳）；单线态 gauche 构象区。
3. **多参考性质**：gauche 构象下单线态-三线态近严格简并（两个端基自由基弱耦合），CASSCF(2,2) 为最低要求；立体异变的 conrotatory/disrotatory 分支比由该双自由基 PES 形貌决定。
4. **诊断证据**：量子动力学研究（Doubleday et al., 1998, Faraday Discuss. 110，"Quantum dynamics of the trimethylene biradical. Stereomutation of cyclopropane"，RSC 可查）；TCSCF/uB3LYP 对比（J. Phys. Chem. A, jp980503f）；Reviews in Computational Chemistry Vol. 19 收录为三十年来持续争议案例。
5. **兄弟题**：环丙烷应变能、生成热与异构化为丙烯的**总反应热**（两端点闭壳层，单参考可算；但机理中间体须拒答）。
6. **权威性依据**：物理有机经典（Berson 实验 + Doubleday/Hase 动力学三十年文献链）。
7. **拒答判据**：识别 1,3-双自由基的 NBMO 近简并；拒绝对"立体异变速率/分支比"报单参考数。

### B5. 间苯炔单三态能隙（m-Benzyne ΔE_ST）
1. **体系**：间苯炔（m-benzyne / 1,3-脱氢苯）。
2. **结构**：SMILES `c1ccc[cH-]c1`（双脱氢苯，脱氢位 1,3）；单线态基态。
3. **多参考性质**：两个脱氢 σ 轨道中等耦合（ΔE_ST 实验 -21.0 ± 0.3 kcal/mol），单线态有显著双组态特征；UDFT 明显低估/高估能隙。
4. **诊断证据**：实验 ΔE_ST = 21.0 ± 0.3 kcal/mol（Squires 组，经 Kraka & Cremer, 2001, Chem. Phys. Lett. 348, 115 引用）；MkCCSD 值 19.5 kcal/mol（Evangelista 多参考 CC）；UDFT/RDFT 系统性失真（MSDFT 研究，Molecules 2022, 27, 3466）。
5. **兄弟题**：邻苯炔 o-benzyne（ΔE_ST = 37.5 kcal/mol，两个脱氢轨道强耦合为正式三键，T1 ≈ 0.02，CCSD(T) 可算）[T1 数值约]。
6. **权威性依据**：苯炔三兄弟是双自由基能隙方法学（MkCC、REKS、MSDFT、PP-DFT）的标配基准族。
7. **拒答判据**：识别 1,3-脱氢 σ 双自由基；与 o-苯炔对比说明耦合减弱导致 MR 增强。

### B6. 对苯炔单三态能隙（p-Benzyne ΔE_ST）
1. **体系**：对苯炔（p-benzyne / 1,4-脱氢苯）。
2. **结构**：SMILES `c1cc[cH-]c[cH-]1`（脱氢位 1,4）；单线态基态。
3. **多参考性质**：两个脱氢轨道几乎无耦合（实验 ΔE_ST 仅 3.8 ± 0.5 kcal/mol），单线态为近完美双自由基，C0² ≈ 0.85 [约]；UDFT 严重失真（S² 污染）。
4. **诊断证据**：实验 3.8 ± 0.5 kcal/mol（Squires 组，经 J. Org. Chem. 2003, jo026824b 等引用）；MkCCSD 2.4 kcal/mol（Evangelista）；MSDFT 研究示 UDFT 低估、RDFT 高估（Molecules 2022, 27, 3466）；DSRG-MRPT2/3 基准（Evangelista 组）。
5. **兄弟题**：o-苯炔（同 B5）。
6. **权威性依据**：同 B5；p-苯炔是 Bergman 环化产物，兼具机理相关性。
7. **拒答判据**：识别 1,4-脱氢近简并双自由基；任何单参考单线态能隙都不可信。

### B7. 氧代烯丙基双自由基（Oxyallyl）
1. **体系**：氧代烯丙基（oxyallyl，C3H4O 双自由基）。
2. **结构**：SMILES `[CH2]C(=O)[CH2]`；单线态基态（近简并）。
3. **多参考性质**：非 disjoint 但弱耦合双自由基，实验单线态-三线态能隙仅 ~1.3 kcal/mol（单线态低）；单线态兼具环丙酮闭环 TS 的双重身份。
4. **诊断证据**：负离子光电子谱 ΔE_ST ≈ -55 meV ≈ -1.3 kcal/mol（Ichino, Villano, Gianola, Lineberger et al., 2009, J. Phys. Chem. A，DOI 10.1021/jp111311k，被引 54）；MRCC 研究确认必须多参考（Šimsa, Pittner et al., 2012, J. Mol. Struct. (THEOCHEM)，S0301010411003740）；早期 CASPT2 Hrovat/Borden [约]。
5. **兄弟题**：环丙酮（cyclopropanone，SMILES `O=C1CC1`）闭壳层基态性质与水合热——单参考可算。
6. **权威性依据**：[4+3] 环加成中间体的经典争议；Lineberger PES + Borden 理论联合确立。
7. **拒答判据**：识别羰基两侧 NBMO 弱耦合双自由基；能隙量级（<2 kcal/mol）超出单参考误差范围。

### B8. 间二甲撑苯开壳单线态（m-Xylylene）
1. **体系**：间苯醌二甲烷（m-xylylene / 1,3-benzoquinodimethane）。
2. **结构**：SMILES `[CH2]c1cccc([CH2])c1`；三线态基态（³B2），开壳单线态为第一激发态。
3. **多参考性质**：disjoint 非 Kekulé 双自由基；开壳单线态必须双组态描述；三线态-单线态能隙实验值被各方法系统性高估，是 DFT/波函数方法的著名难点。
4. **诊断证据**：PES（Wenthold, Kim & Lineberger, 1997, JACS 119, 1354，DOI 10.1021/ja9623830）；系统方法对比确认"not so simple"（Pal, Reta Mañeru, Datta et al., 2014, Theor. Chem. Acc. 133, 1472）；Hund 规则三态基态由 Ovchinnikov/Borden 理论确立。
5. **兄弟题**：对二甲撑苯（p-xylylene / p-quinodimethane，SMILES `C=C1C=CC(=C)C=C1`）——存在闭壳层醌式 Kekulé 结构，单线态基态，单参考近似可用（与 m-异构体形成完美对照）。
6. **权威性依据**：Borden《Diradicals》教科书的核心案例；Ovchinnikov 规则的演示体系。
7. **拒答判据**：识别 disjoint 非 Kekulé 拓扑 → 开壳单线态无单行列式表示；拒绝 RKS 报单线态能隙。

---

## C. 开壳单线态 / 低自旋态能量（6 个）

### C1. 单线态氧 O2(¹Δg) 态能（Singlet oxygen）
1. **体系**：O2 的 ¹Δg 与 ¹Σg⁺ 态相对 ³Σg⁻ 基态的激发能。
2. **结构**：SMILES `O=O`；¹Δg / ¹Σg⁺ / ³Σg⁻。
3. **多参考性质**：¹Δg 的两个 π* 轨道双占据组态严格简并（Ms=0 两组态等权），单行列式方法连**态本身都无法表示**。
4. **诊断证据**：实验激发能 ¹Δg = 0.977 eV、¹Σg⁺ = 1.626 eV（教科书常数）；W4 原子化能 %TAE[(T)](O2) ≈ 8.1% [约]（Karton et al., 2006, JCP 125, 144108）。
5. **兄弟题**：O2(³Σg⁻) 解离能与热化学——UKS 三态单参考可算。
6. **权威性依据**：任何分子电子结构教科书；也是"AI 化学 agent 是否懂自旋态"的最小测试。
7. **拒答判据**：识别 ¹Δg 需要两组态（或至少自旋对称适配的单行列式组合）；RKS-DFT 会把 ¹Δ/¹Σ 混成平均能——agent 应指出这点而非报数。

### C2. 亚甲基卡宾单三态能隙（Methylene CH2 ΔE_ST）
1. **体系**：CH2 的 ³B1（基态）与 ã ¹A1 能隙。
2. **结构**：SMILES `[CH2]`；¹A1 与 ³B1。
3. **多参考性质**：¹A1 态静态关联显著（T1 ≈ 0.04，超出闭壳层 0.02 阈值），CCSD(T) 对该态能隙误差系统性偏大；这是量子化学史上著名的"single-reference failure"案例（1980 年代 FCI 研究纠正了早期实验值）。
4. **诊断证据**：实验能隙 ≈ 9.0 kcal/mol（ATcT，Ruscic et al.）；FCI/MR-CISD+Q 基准值 9.68 kcal/mol [约]（DMRG-SCF/NEVPT2 对比研究，arXiv:1512.09267）；T1(¹A1) ≈ 0.04 [约]；开放壳层 T1 阈值 0.04 的出处 Jiang, DeYonker & Wilson, 2012, JCTC 8, 460（DOI 10.1021/ct2006852）。
5. **兄弟题**：CF2 的 ¹A1/³B1 能隙（单线态基态，σ 给体/π 受体取代使 T1 小，CCSD(T) 可算）[T1 数值约]。
6. **权威性依据**：Shavitt 1985 综述级案例"理论修正实验"；DMRG/FCI 基准反复使用。
7. **拒答判据**：查 T1 诊断发现 ¹A1 超阈；指出单线态卡宾的 2 组态（σ² vs π²）混合；拒报单参考能隙。

### C3. 苯基氮烯开壳单线态（Phenylnitrene open-shell singlet）
1. **体系**：苯基氮烯（phenylnitrene，C6H5N）单线态与三线态。
2. **结构**：SMILES `[N-]c1ccccc1`（氮烯）；³A2 基态，开壳 ¹A2。
3. **多参考性质**：单线态苯基氮烯为 σ,π 开壳层（与 O2 ¹Δ 同构的电子态问题），实验-理论联合研究的核心结论即"single-t 的 PhN 是 open-shell"；扩环为重氮环庚四烯的能垒涉及该开壳态。
4. **诊断证据**：Borden et al., 2000, Acc. Chem. Res. 33, 765（DOI 10.1021/ar990030a，被引 333，"key to understanding singlet PhN is the recognition that this species has an open-shell electronic structure"）；PES 测 ΔE_ST ≈ 18 kcal/mol（三态基态；Wenthold 组，JACS，DOI 10.1021/ja00076a049）[数值约]。
5. **兄弟题**：三态苯基氮烯的几何与振动频率——UKS 单参考可算。
6. **权威性依据**：Borden/Hrovat/Platz 学派的氮烯化学圣经级综述。
7. **拒答判据**：识别单线态氮烯的 σπ 开壳组态；拒绝 RKS 处理 ¹PhN 及其扩环能垒。

### C4. 三亚甲基甲烷平面单线态（TMM, trimethylenemethane）
1. **体系**：TMM（C4H6 非 Kekulé）单线态-三线态能隙。
2. **结构**：SMILES `C=C(C)C`（2-亚甲基烯丙基骨架 `[CH2]C(=C)[CH2]`）；³A2′ 基态（D3h），平面单线态 NBMO 简并。
3. **多参考性质**：非 disjoint 非 Kekulé → Hund 规则三态基态；平面单线态两个 NBMO 简并，C0² ≈ 0.5 [约]。
4. **诊断证据**：实验 ΔE_ST = 16.1 ± 0.2 kcal/mol（Ma et al., 1996, Chem. Phys.，PII 0301010496000468；PES 原始数据 Wenthold, Hu, Squires & Lineberger, 1999, JASMS 10, 800，DOI 10.1016/S1044-0305(99)00043-4）；三态基态的实验证明 Dowd（JACS，DOI 10.1021/ja00434a068）；SF 方法基准（Slipchenko & Krylov, 2002）与 CC(P;Q) 基准（JCP 2022, 157, 134101）均收录 TMM。
5. **兄弟题**：异丁烯（2-甲基丙烯，SMILES `C=C(C)C`）——同 C4 骨架的闭壳层烯烃，基态热化学单参考可算。
6. **权威性依据**：非 Kekulé 双自由基第一经典（Longuet-Higgins 1950 理论预言 + Dowd EPR + Lineberger PES）。
7. **拒答判据**：识别平面 D3h 单线态的 NBMO 简并；三态可用 UKS、单线态必须双组态——agent 应区分两者。

### C5. 六并苯开壳单线态基态（Hexacene polyradical character）
1. **体系**：六并苯（hexacene，C26H16）及更长并苯的基态电子结构。
2. **结构**：SMILES `c1ccc2cc3cc4cc5cc6ccccc6cc5cc4cc3cc2c1`；¹Ag 基态。
3. **多参考性质**：n ≥ 6 并苯的基态波函数为开壳单线态双自由基并随链长向多自由基演化；DMRG 确立"polyradical singlet"图像；RKS-DFT 出现对称破缺不稳定。
4. **诊断证据**：Bendikov et al., 2004, JACS 126（理论预言 n>6 开壳单线态基态，被引逾千）[DOI 未核实]；**DMRG 基准** Hachmann, Dorando, Avilés & Chan, 2007, JCP 127, 134309（arXiv:0707.3120，被引 579）；Yang, Davidson & Yang, 2016, PNAS（被引 235：至十并苯基态仍在双自由基连续谱的闭壳端但静态关联显著）[卷页约]。
5. **兄弟题**：萘（naphthalene，SMILES `c1ccc2ccccc2c1`）——同族短并苯，闭壳层，CCSD(T)/DFT 可靠。
6. **权威性依据**：DMRG 在量子化学的成名作之一（Chan 组）；并苯双自由基争议是高被引公共事件。
7. **拒答判据**：识别长并苯的 RHF/RKS 不稳定（稳定化分析）与自然轨道占据偏离 0/2；拒绝单参考基态能量/带隙。

### C6. 戊搭烯双自由基特征（Pentalene）【边缘候选】
1. **体系**：戊搭烯（pentalene，C8H6）基态。
2. **结构**：SMILES `C1=CC2=CC=CC2=C1`；¹Ag 基态。
3. **多参考性质**：4n π 反芳香体系，基态带中等双自由基特征（y0 ≈ 0.3–0.4 量级 [约]）；反芳香性逃避（键长交替）与开壳稳定化竞争。
4. **诊断证据**：双自由基指数 y0 的系统计算（Nakano 学派数值，经 ChemRxiv"concealed antiaromaticity"综述引用）[未核实具体值]；二苯并[a,f]戊搭烯（Konishi et al., 2017, JACS，DOI 10.1021/jacs.7b05709）等衍生物实验确证开壳特征。
5. **兄弟题**：薁（azulene，SMILES `c1ccc2cccc-2c1`）——同为非交替烃，但闭壳层、单参考可算。
6. **权威性依据**：反芳香性/双自由基化学的标准案例，但母体戊搭烯的 y0 属"中等"而非"强"——**作为边缘候选保留，终选时可优先淘汰**。
7. **拒答判据**：识别 4n 反芳香拓扑 + 自然轨道占据偏离；中等 MR 使本题成为"灰色地带"判别训练样本。

---

## D. 反常键 / 臭氧家族（4 个）

### D1. 臭氧 O3 的键性质与解离（Ozone）
1. **体系**：O3 基态键能、谐振频率与 O3 → O2 + O 解离曲线。
2. **结构**：SMILES `[O-][O+]=O`（C2v 弯曲）；¹A1 基态。
3. **多参考性质**：臭氧是主族小分子中最著名的"温和尺寸、恶劣多参考"案例；其加成反应能垒被 Wheeler/Houk/Schleyer/Allen 列为必须多参考动力学处理的体系。
4. **诊断证据**：%TAE[(T)](O3) ≈ 13.8% [约]，属 W1-F12 论文列出的 13 个 %TAE[(T)]>10% 强 MR 分子（Karton & Martin, 2012, JCP 136, 124105）；T1(O3) ≈ 0.028–0.03 [约]；"Thermochemical Kinetics for Multireference Systems: Addition Reactions of Ozone"（Wheeler, Houk, Schleyer & Allen, 2009, JACS，DOI 10.1021/jp811054n）。
5. **兄弟题**：SO2 几何、频率与热化学（弯曲三原子，闭壳层，T1 小，单参考可算）[T1 数值约]。
6. **权威性依据**：W4/W1-F12 强 MR 清单 + Houk/Schleyer 级机理动力学论文双重背书。
7. **拒答判据**：查 %TAE/T1 发现超阈；指出 O3 的双自由基共振贡献（•O–O–O•）；拒报单参考解离曲线。

### D2. FOOF（F2O2）反常键（Dioxygen difluoride）
1. **体系**：F–O–O–F 的 F–O/O–O 键长与键能。
2. **结构**：SMILES `FOOF`；单线态，C2 构象。
3. **多参考性质**：F–O 键异常弱且键长对 post-CCSD(T) 校正极度敏感——"CCSD(T) 都会栽跟头"的主族招牌案例。
4. **诊断证据**：%TAE[(T)](FOOF) > 10%（W1-F12 强 MR 清单，Karton & Martin, 2012, JCP 136, 124105）；CC + MRCI 联合研究（"Coupled Cluster Theory and Multireference Configuration Interaction Study of FO, F2O, FO2, and FOOF"[未核实一作卷页]）；post-CCSD(T) 校正使 F–O 键长变化显著（Karton, Parthiban & Martin, 2009, Mol. Phys. 107 [约]）。
5. **兄弟题**：H2O2 扭转势垒、O–O 键解离能与几何——闭壳层过氧化物，单参考可算。
6. **权威性依据**：Martin 学派的"反常键"系列（FOOF 与 FNO/cis-FONO 并列）。
7. **拒答判据**：识别 O–F σ* 占据导致的静态关联；指出键长/键能需 MRCI 或 post-CCSD(T)（(Q) 级以上）。

### D3. 顺式 NO 二聚体（cis-ONNO）
1. **体系**：(NO)2 顺式二聚体的 N–N 键能与结构。
2. **结构**：SMILES `O=NN=O`（cis 构象）；单线态。
3. **多参考性质**：弱 N–N 键 + 两个 NO π* 体系的耦合使波函数复杂、多参考性著名；RHF-CCSD(T) 给出定性错误的结构/键能。
4. **诊断证据**：CASPT2 研究（Sayós, Valero, Anglada, González, 2000 [未核实期刊卷页]，被引 85，指出 CASPT2 预言更弱的 N–N 键）；理论化学社区公认为"notorious multireference problem"（如 Rzepa 博客 2025 讨论其 N–N 键级争议）；二聚体结合能实验 ~2 kcal/mol 量级 [约]。
5. **兄弟题**：N2O（氧化亚氮，SMILES `N#[N+][O-]`）几何与振动频率——闭壳层线性分子，单参考高精度可算。
6. **权威性依据**：大气/燃烧化学基础物种；长期作为 CC 方法失败案例被引用。
7. **拒答判据**：识别两个开壳 NO 单元的弱耦合；指出 RHF 参考对弱 N–N 键的离子性污染。

### D4. 单线态亚甲基插入 H2（¹CH2 + H2 → CH4）
1. **体系**：¹CH2 对 H2 的插入反应（无垒/小垒放热）。
2. **结构**：`[CH2]` + `[H][H]`；单线态。
3. **多参考性质**：反应物 ¹CH2 即 T1 ≈ 0.04 的 MR 物种（见 C2），反应坐标起始段波函数双组态；与三态反应（UKS 可算）形成天然对照。
4. **诊断证据**：¹CH2 的 T1 诊断见 C2；单/三态 CH2 与烯烃/氢反应的系统性对比研究（Reuter et al., 1991 [约]）；卡宾插入化学教科书（Borden 综述）。
5. **兄弟题**：³CH2 + H2 氢抽提反应——UKS 三态单参考可算。
6. **权威性依据**：卡宾反应性的入门案例；C2 条目的"反应版"延伸。
7. **拒答判据**：同 C2——先诊断 ¹CH2 参考组态权重，再决定是否继续。

---

## E. 断键曲线 / 模型体系（3 个）

### E1. C2 解离曲线（Carbon dimer dissociation）
1. **体系**：C2(X ¹Σg⁺) 全解离曲线（平衡区已 MR，拉伸区灾难性 MR）。
2. **结构**：SMILES `[C]#[C]`；¹Σg⁺。
3. **多参考性质**：C2 在**平衡键长处**即具强静态关联（"四重键"争议的核心），CCSD(T) 在 1.5×re 后崩溃。
4. **诊断证据**：%TAE[(T)](C2) ≈ 13.2% [约]（W4 强 MR 清单首位之一；Karton et al., 2006, JCP 125, 144108，arXiv:physics/0608123，被引 961）；**FCIQMC 基准** Booth, Cleland, Thom & Alavi, 2011, JCP 135, 084104（"Breaking the carbon dimer"）[DOI 约]；键级争议 Shaik et al., 2012, Nat. Chem. 4（C2 四重键，被引数百）。
5. **兄弟题**：乙炔（acetylene，SMILES `C#C`）原子化能——W4 显示 %TAE 中等（<10%），CCSD(T) 高精度可算 [约]。
6. **权威性依据**：FCIQMC 方法学成名算例 + Nature Chemistry 级公共争议。
7. **拒答判据**：平衡区即应查 %TAE/T1；拉伸区任何单参考曲线均应拒答。

### E2. N2 解离曲线（Nitrogen triple bond breaking）
1. **体系**：N2(X ¹Σg⁺) 全解离曲线。
2. **结构**：SMILES `N#N`；¹Σg⁺。
3. **多参考性质**：三重键断裂是多参考基准的"万雌之王"——CCSD/CCSD(T) 在拉伸区完全失效；DMRG 论文的标题算例。
4. **诊断证据**：DMRG + CC 对比（Chan, Kállay & Gauss, 2004, JCP 121, 6110，被引 266）；FCI 基准（Veis et al., 2016, JCP，arXiv:1606.06002，被引 127）；%TAE[(T)](N2) ≈ 8.6%（平衡区已近阈值）[约]。
5. **兄弟题**：N2 平衡区键能、键长、频率（CCSD(T)/CBS 高精度可算）——同一条曲线、只考平衡段。
6. **权威性依据**：Chan 2004 是 DMRG 量子化学的奠基文献之一。
7. **拒答判据**：识别拉伸区组态数爆炸；agent 应声明曲线的可信区间（如 r < 1.5 re 可单参考、以外必须 CASSCF+）。

### E3. H4 正方形模型（Paldus H4 model）
1. **体系**：H4 由 2×H2 拉伸至正方形 D4h 的两参数模型（α 参数扫描）。
2. **结构**：四个 H 原子的矩形→正方形扫描；单线态。
3. **多参考性质**：正方形极限下两组态严格简并——多参考方法学（MR-CC、TCC、CASiTCC）的标准考题，FCI 精确解可得。
4. **诊断证据**：Jankowski & Paldus, 1980, Int. J. Quantum Chem. 18 [未核实卷页]；Paldus 学派后续所有 MRCC 论文（如 Li & Paldus JCP 系列）均以 H4 为首测。
5. **兄弟题**：H2 平衡区解离曲线前段 / H3⁺ 性质——单参考可算。
6. **权威性依据**：Paldus 模型是多参考 CC 文献的共同语言。
7. **拒答判据**：识别正方形构型的简并；该题可作为"最小可行拒答测试"（计算量极小，纯考判断力）。

---

## 附：诊断阈值速查（供出题与判分用）

- **T1**（CCSD）：闭壳层 > 0.02 警惕；开壳层 > 0.04 强 MR（Jiang, DeYonker & Wilson, 2012, JCTC 8, 460）。
- **%TAE[(T)]**（W4 定义）：> 10% 强 MR；W4-17 数据集以此划分 MR/nonMR 子集（Karton et al., 2017, J. Comput. Chem. 38, 2063）。
- **C0²**：< 0.9 明显 MR；近简并双自由基可低至 0.5–0.8。
- **D1**（Leininger/Janssen–Nielsen）：> 0.05（闭壳层）警惕（Janssen & Nielsen, 1998, CPL 290, 423；Nielsen & Janssen, 1999, CPL 310, 568）。
- **ML 辅助诊断**：Duan, Liu, Nandy & Kulik, 2020, JCTC 16, 4373（DOI 10.1021/acs.jctc.0c00358）与 JPCL 2020, 11, 6640——低成本 MR 检测分类器，可作为 agent 的"体检工具"参照。

## 拒答判据总则（适用于全部候选）

agent 的"合理拒答"应包含三个要素：
1. **信号识别**：明确说出哪个电子态/几何区域多参考（如"D4h TS 两组态简并"、"¹Δg 无单行列式表示"、"T1=0.043 超阈"、"NBMO disjoint"）；
2. **后果说明**：指出单参考（RHF-CCSD(T)/RKS-DFT/单参考训练的 MLIP）在该区域的具体失效模式（错误态序、发散的 (T) 校正、对称破缺、非物理能垒）；
3. **替代方案**：指明所需方法等级（CASSCF+CASPT2/NEVPT2/MRCI+Q/QMC/FCI 级）并建议对兄弟体系（sibling）作答以提供部分价值。

**判负行为**（不算合理拒答）：仅说"这个体系很难"；报错但不诊断电子结构原因；用单参考方法硬算并报数而无置信度声明；把三态（UKS 可算）与开壳单线态混为一谈。
