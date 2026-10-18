# Impossible 档候选反应清单：强多参考 / 近简并双自由基体系

> **当前正式题集（2026-10-18）**：按用户“缺测题可删除、保留五十题”的决定，IA8（CH₂OO 成环）和 IB10（甲酰卡宾分步 Wolff 路径）退出有效集合，impossible 由十二题减为十题，全题库共五十题。原条目、registry 定义和全部计算结果继续留档；退出集合不等于改判物理不可达。保留 IB9，已确认的首步参考值沿用，其余缺测值不填零。当前正选名单见文末。

> **⚠ 存量题源（2026-09-21）**：本文件是历史策展入库的 impossible 题池，**不是**本轮「边选边填 gold」的候选清单。新候选不从本文档抄题；现行策略见 `gold_compute/README.md`。
>
> 生成日期：2026-08-25。2026-08-31 扩建 F–J 族 38 条并完成初批 [未核实] 出处核验。状态：**2026-09-27 接收原 normal R4 为 B10（此前 U8 为 B9），现定稿 12 道 I 题；S 对照题全部取消**。
>
> **当前允许方法（2026-10-18）**：仅 xTB、PM7，关闭 DFT。下文保留的 DFT 结果属于历史参考，不代表当前题目允许使用 DFT。
>
> **档位定义**：强多参考态（strong static correlation）与近简并双自由基体系。单参考方法在这些体系的关键区域可能给出错误能级排序、虚假对称破缺或不可信能垒。现行交付协议要求 agent 保留机理图，把无法由允许方法可信计算的节点或边标 `accessible=false`，其余元素照常交付；不能编造数值。
>
> **选型原则**：全部为教科书级经典体系，多参考性质由 CASSCF/CASPT2/MRCI/FCIQMC/DMC 级高被引研究确立，可复现、有实验锚点（PES/EPR/光电子谱）。
>
> **对照题政策（2026-09-26 用户裁决）**：不再生成 S 对照题。下列旧候选条目中的“兄弟题”行只作历史提案留档，不进入登记表或题库。
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
4. **诊断证据**：反旋/顺旋路径对比的多参考研究（Havenith, Jenneskens & van Lenthe, 1999, J. Mol. Struct. (THEOCHEM) 492, 217–224，DOI 10.1016/S0166-1280(99)00166-9，CASSCF(10,10)/6-311G**；结论：顺旋通道优先且不经过 trans-苯）；相关讨论见 Computational Organic Chemistry 博客（2010）。TS 强双自由基oid [定性确认]。
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
4. **诊断证据**：**T1 = 0.043**（CCSD(T) 计算 CH2OO，远超 0.02 阈值；Osborn & Taatjes, 2015, Int. Rev. Phys. Chem. 34, 309，被引 274）；CH2+O2 机理研究再次确认 T1 超阈（Mazarei et al., 2022, PCCP）；全维 MRCI-F12 PES（Dawes/Guo 组：Li, Carter, Bowman, Dawes, Xie & Guo, 2014, J. Phys. Chem. Lett. 5, 2364–2369；振动谱跟进 Yu, Ndengué, Li, Dawes & Guo, 2015, J. Chem. Phys. 143, 084311。2026-08-31 核验修正：无 Lischka 参与的 CH2OO 文献，原署名系与其臭氧合作混淆）。
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
4. **诊断证据**：CASPT2 + ab initio 直接动力学研究（Arenas, López-Tocón, Otero & Soto, 2002, J. Am. Chem. Soc. 124, 1728–1735，DOI 10.1021/ja010750o。2026-08-31 核验修正：期刊为 JACS 而非 J. Chem. Phys.）；¹CH2 的 T1 ≈ 0.04 [约]。
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

## B. 扭转/近简并双自由基（9 个）

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
4. **诊断证据**：phantom 态概念与实验证据（phantom 态原始出处 Saltiel, 1967, JACS 89, 1036–1037；姊妹篇 1968, JACS 90, 6394–6400；"zwitterionic" 定性措辞见 Saltiel 后续回顾工作）；近期非绝热研究（Raucci et al., 2022，顺式芪 S0/S1 锥交叉，OSTI 可查）。
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

### B9. 1-吡唑啉热脱氮与环丙烷生成（1-Pyrazoline denitrogenation）
1. **体系**：原 normal U8：重氮甲烷 + 乙烯先经 [3+2] 环加成形成 1-吡唑啉，再热脱氮生成环丙烷和 N₂。第一步保留为可达；第二步的过渡区标为不可达。
2. **结构**：`C=[N+]=[N-].C=C → C1CN=NC1 → C1CC1.N#N`，净电荷 0，单重态整体反应。
3. **多参考性质**：脱氮需断两根 C–N σ 键，协同与分步路径都可能进入双自由基区域；“协同”本身不保证单参考可描述。旧 normal 图强定单步螯变且以 B3LYP 扫描补垒，不能作为可信 gold。
4. **诊断证据**：Pradhan & Lourderaj, Phys. Chem. Chem. Phys. 2017, 19, 27468–27477, DOI 10.1039/C7CP05320G，以 CASSCF/CASPT2 比较同步、异步协同和异步分步脱氮路径，并指出常规 DFT/MP2 未正确描述双自由基区域。旧 NU8 第二步只有受限 B3LYP 扫描，没有通过 TS/IRC 验证。
5. **判分口径**：IMP 仅允许 xTB、PM7；首步环加成参考已按用户确认更新为 GFN2-xTB 纯电子垒 ΔE‡ = 5.65 kcal/mol（气相 ORCA 6.1.1 / xTB 6.7.1，TS794 相对原料接触体839；不含 ZPE/热校正）。接触体仍有 −29.79/−4.49 cm⁻¹ 两个组分间软模，本次按人工确认接纳，未改写为零虚频或 strict pass；相对零虚频分离单体742+745的能差4.37 kcal/mol另列于 `gold_compute/queue_20261018/results/IB9/GOLD_BACKFILL_20261018.md`。历史 B3LYP 14.74 不再作为当前 Gold。脱氮 TS 标 `accessible=false`，第二步能垒保持缺测；首步回填不代表全题速控步已确定。

---

### B10. Wolff 重排经甲酰卡宾路径（Wolff rearrangement via formylcarbene）
1. **体系**：原 normal R4：2-重氮基乙醛热脱 N₂ 形成单重态甲酰卡宾，再经 1,2-H 迁移形成乙烯酮。保留原分步路径，不据此断言绕过卡宾的协同通道不可算。
2. **结构**：`O=CC=[N+]=[N-] → O=C[CH].N#N → C=C=O.N#N`，净电荷 0；题设考察单重态路径。
3. **多参考依据**：Novoa, McDouall & Robb, 1987, J. Chem. Soc., Faraday Trans. 2, 83, 1629–1636，DOI [10.1039/F29878301629](https://doi.org/10.1039/F29878301629)，MC-SCF 指出最低单重态甲酰卡宾具有双自由基性质，三重态接近且附近存在态交叉。2023 年 [Gas-phase detection of oxirene](https://pmc.ncbi.nlm.nih.gov/articles/PMC10005165/) 指出甲酰卡宾及相关 TS 的多参考效应，并以 CASPT2 复核。文献结论不是本项目自行计算的诊断数值。
4. **判分口径（2026-09-27 用户批准迁入 IMP）**：反应物与终产物保留可达；甲酰卡宾中间体及两步相关 TS 标 `accessible=false`，两边参考垒留空。频率与 IRC 自洽不构成电子结构方法适用性的证明。题面不给出多参考诊断答案。
5. **历史计算保留**：原 NR4 第二步闭壳层 B3LYP-D3(BJ)/def2-SVP 得 4.34 kcal/mol（作业 344/348/364/365；gold 节点 `NR4/REPORT.md`），仅作方法内自洽的历史结果，不再进入评分锚点；E1 扫描未找到 TS，不能据此证明没有鞍点。原始产物和历史 benchmark runs 不改写。

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
2. **结构**：SMILES `[N]c1ccccc1`（中性氮烯，q=0，与 registry/TaskSpec 一致）；³A2 基态，开壳 ¹A2。
3. **多参考性质**：单线态苯基氮烯为 σ,π 开壳层（与 O2 ¹Δ 同构的电子态问题），实验-理论联合研究的核心结论即"single-t 的 PhN 是 open-shell"；扩环为重氮环庚四烯的能垒涉及该开壳态。
4. **诊断证据**：Borden et al., 2000, Acc. Chem. Res. 33, 765（DOI 10.1021/ar990030a，被引 333，"key to understanding singlet PhN is the recognition that this species has an open-shell electronic structure"）；PES 测 ΔE_ST ≈ 18 kcal/mol（三态基态；Wenthold 组，JACS，DOI 10.1021/ja00076a049）[数值约]。
5. **兄弟题**：三态苯基氮烯的几何与振动频率——UKS 单参考可算。
6. **权威性依据**：Borden/Hrovat/Platz 学派的氮烯化学圣经级综述。
7. **拒答判据**：识别单线态氮烯的 σπ 开壳组态；拒绝 RKS 处理 ¹PhN 及其扩环能垒。

### C4. 三亚甲基甲烷平面单线态（TMM, trimethylenemethane）
1. **体系**：TMM（C4H6 非 Kekulé）单线态-三线态能隙。
2. **结构**：SMILES `C=C(C)C`（2-亚甲基烯丙基骨架 `[CH2]C(=C)[CH2]`）；³A2′ 基态（D3h），平面单线态 NBMO 简并。
3. **多参考性质**：非 disjoint 非 Kekulé → Hund 规则三态基态；平面单线态两个 NBMO 简并，C0² ≈ 0.5 [约]。
4. **诊断证据**：实验 ΔE_ST = 16.1 ± 0.2 kcal/mol（数值已核实，但原挂"Ma et al., 1996, Chem. Phys.，PII 0301010496000468"出处归属 2026-08-31 核验未能坐实——实验值更常溯源 Wenthold/Squires/Lineberger 的 TMM 负离子 PES 系列：Wenthold, Hu, Squires & Lineberger, 1999, JASMS 10, 800，DOI 10.1016/S1044-0305(99)00043-4）；三态基态的实验证明 Dowd（JACS，DOI 10.1021/ja00434a068）；SF 方法基准（Slipchenko & Krylov, 2002）与 CC(P;Q) 基准（JCP 2022, 157, 134101）均收录 TMM。
5. **兄弟题**：异丁烯（2-甲基丙烯，SMILES `C=C(C)C`）——同 C4 骨架的闭壳层烯烃，基态热化学单参考可算。
6. **权威性依据**：非 Kekulé 双自由基第一经典（Longuet-Higgins 1950 理论预言 + Dowd EPR + Lineberger PES）。
7. **拒答判据**：识别平面 D3h 单线态的 NBMO 简并；三态可用 UKS、单线态必须双组态——agent 应区分两者。

### C5. 六并苯开壳单线态基态（Hexacene polyradical character）
1. **体系**：六并苯（hexacene，C26H16）及更长并苯的基态电子结构。
2. **结构**：SMILES `c1ccc2cc3cc4cc5cc6ccccc6cc5cc4cc3cc2c1`；¹Ag 基态。
3. **多参考性质**：n ≥ 6 并苯的基态波函数为开壳单线态双自由基并随链长向多自由基演化；DMRG 确立"polyradical singlet"图像；RKS-DFT 出现对称破缺不稳定。
4. **诊断证据**：Bendikov, Duong, Starkey, Houk, Carter & Wudl, 2004, JACS 126, 7416–7417，DOI 10.1021/ja048919w（理论预言 n>6 开壳单线态基态，被引逾千；勘误 JACS 2004, 126, 10493）；**DMRG 基准** Hachmann, Dorando, Avilés & Chan, 2007, JCP 127, 134309（arXiv:0707.3120，被引 579）；Yang, Davidson & Yang, 2016, PNAS（被引 235：至十并苯基态仍在双自由基连续谱的闭壳端但静态关联显著）[卷页约]。
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
4. **诊断证据**：%TAE[(T)](FOOF) > 10%（W1-F12 强 MR 清单，Karton & Martin, 2012, JCP 136, 124105）；CC + MRCI 联合研究（Feller & Dixon, 2003, J. Phys. Chem. A 107, 9641–9651，DOI 10.1021/jp030267v）；post-CCSD(T) 校正使 F–O 键长变化显著（Karton, Parthiban & Martin, 2009, Mol. Phys. 107 [约]）。
5. **兄弟题**：H2O2 扭转势垒、O–O 键解离能与几何——闭壳层过氧化物，单参考可算。
6. **权威性依据**：Martin 学派的"反常键"系列（FOOF 与 FNO/cis-FONO 并列）。
7. **拒答判据**：识别 O–F σ* 占据导致的静态关联；指出键长/键能需 MRCI 或 post-CCSD(T)（(Q) 级以上）。

### D3. 顺式 NO 二聚体（cis-ONNO）
1. **体系**：(NO)2 顺式二聚体的 N–N 键能与结构。
2. **结构**：SMILES `O=NN=O`（cis 构象）；单线态。
3. **多参考性质**：弱 N–N 键 + 两个 NO π* 体系的耦合使波函数复杂、多参考性著名；RHF-CCSD(T) 给出定性错误的结构/键能。
4. **诊断证据**：CASPT2 研究（Sayós, Valero, Anglada & González, 2000, J. Chem. Phys. 112, 6608–6624，DOI 10.1063/1.481234，被引 85，指出 CASPT2 预言更弱的 N–N 键）；理论化学社区公认为"notorious multireference problem"（如 Rzepa 博客 2025 讨论其 N–N 键级争议）；二聚体结合能实验 ~2 kcal/mol 量级 [约]。
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
4. **诊断证据**：Jankowski & Paldus, 1980, Int. J. Quantum Chem. 18, 1243–1269；Paldus 学派后续所有 MRCC 论文（如 Li & Paldus JCP 系列）均以 H4 为首测。
5. **兄弟题**：H2 平衡区解离曲线前段 / H3⁺ 性质——单参考可算。
6. **权威性依据**：Paldus 模型是多参考 CC 文献的共同语言。
7. **拒答判据**：识别正方形构型的简并；该题可作为"最小可行拒答测试"（计算量极小，纯考判断力）。

---

## F. 非 Kekulé 双自由基与开壳多环芳烃（7 个）

### F1. 苯并烯丙基自由基 π-二聚体的 pancake 键（Phenalenyl radical π-dimer, 2e/12c bond）
1. **体系**：苯并烯丙基自由基（phenalenyl radical，PLY，C13H9•）及其 π-堆积二聚体 PLY2（"pancake 键"，二电子/十二中心 2e/12c 键）。
2. **结构**：单体 SMILES `[CH]1C=CC2=CC=CC3=C2C1=CC=C3`（双线态，D3h）；二聚体为两单体面对面 π-堆积（层间距 ~3.1–3.2 Å，无常规键级），单线态/三线态。
3. **多参考性质**：二聚体低自旋态是两个双态自由基 SOMO 强反铁磁耦合并部分共价化的结果——"多中心长键"介于范德华堆积与共价 σ 键之间；沿解离曲线（二聚体 → 2 个自由基）静态关联持续增强，BS-DFT 自旋污染严重，RHF 参考完全失效。
4. **诊断证据**：实验交换耦合常数 J = −1390 cm⁻¹（SQUID）/ −2910 cm⁻¹（EPR），2,5,8-三叔丁基 PLY 二聚体层间距 3.201 Å（Goto et al., 1999, JACS 121, 1619；Fukui et al., 1999, Synth. Met. 103, 2257，经 Mansikkamäki & Tuononen, 2018, J. Phys. Chem. Lett. 9, 3624，DOI 10.1021/acs.jpclett.8b01507 汇总引用）；二聚化焓实验值 −31.4/−36.8/−39.9 kJ/mol（Small et al., 2004, JACS 126, 13850；Suzuki et al., 2006, JACS 128, 2530）；多中心长键统一理论 Mota, Miller & Novoa, 2009, JACS 131, 7699；pancake 与 vdW 成分分离 Cui, Lischka, Beneberu & Kertesz, 2014, JACS 136, 5539；CASCI-DFT 研究 Ukai et al., 2007, Polyhedron 26, 2313。
5. **兄弟题**：苯并烯（phenalene，SMILES `C1C=CC2=CC=CC3=C2C1=CC=C3`）——同骨架闭壳层烃（sp3 CH2），基态性质单参考可算；另可用芘 π-二聚体（SMILES `c1cc2ccc3cccc4ccc(c1)c2c34`，纯色散堆积，CCSD(T) 基准成熟）作对照。
6. **权威性依据**：pancake 键（2e/mc 键）概念的母体体系，Kertesz/Miller/Novoa/Lischka 多组十余年文献链；实验（EPR/SQUID/X 射线）与理论双重确立。
7. **拒答判据**：识别二聚体低自旋态的 SOMO–SOMO 强反铁磁耦合（有效键级分数、无 Lewis 结构）；指出 RHF-CCSD(T) 参考对 pancake 键的离子性污染、BS-UDFT 的 ⟨S²⟩ 污染；二聚化能/解离曲线需 CASSCF(2,2)+动态关联或经自旋投影的专用处理，拒绝报单参考结合能。

### F2. Chichibabin 烃单三态能隙（Chichibabin's hydrocarbon ΔE_ST）
1. **体系**：Chichibabin 烃（C38H28，4,4′-双（二苯亚甲基）联苯）的单线态基态与单三态能隙。
2. **结构**：双自由基式 SMILES `[C](c1ccccc1)(c1ccccc1)c1ccc(-c2ccc([C](c3ccccc3)c3ccccc3)cc2)cc1`（C38H28，醌式闭壳层共振式与双自由基式竞争）；单线态基态。
3. **多参考性质**：联苯间隔基使两个三苯甲基自由基单元弱耦合，闭壳层醌式与开壳双自由基共振近简并，y0 ≈ 0.72 [约]；单线态波函数双组态，BS-DFT 与 RKS-DFT 对能隙符号/量级系统性失真。
4. **诊断证据**：文献参考 ΔE_ST ≈ −5.5 kcal/mol（单线态低；ppRPA 基准文 Table 6 引用值，arXiv:2305.00369）[约]；y0 = 0.72（BS-DFT，经 NHC 类似物综述引用，Thieme，DOI 10.1055/s-0037-1611887）[约]；1986 年磁化率测定单线态基态 + X 射线醌式键长交替（Montgomery et al., 1986, JACS [卷页 108, 6004 未核实]）；方法学系统对比 Sun et al., 2025, J. Chem. Theory Comput. 21, 1194，DOI 10.1021/acs.jctc.4c01384（被引 14，BS-DFT/SF-TDDFT/MRSF-TDDFT/CASSCF/CASPT2/MC-PDFT 全面 benchmark）；Abe, 2013, Chem. Rev. 113, 7011（Diradicals 综述，DOI 10.1021/cr400056a [DOI 约]）。
5. **兄弟题**：四苯基乙烯（tetraphenylethylene，SMILES `C(=C(c1ccccc1)c1ccccc1)(c1ccccc1)c1ccccc1`）——同三苯甲基/二苯亚甲基砌块的闭壳层烯烃，基态与扭转单参考可算。
6. **权威性依据**：物理有机百年经典（Chichibabin 1907）；2025 年 JCTC 仍以其为双自由基表征标准算例，Abe 综述与 Nakano 学派 y0 框架的核心体系。
7. **拒答判据**：识别两个 NBMO 弱耦合（醌式 BLA 是双自由基特征而非闭壳层证据）；指出 RKS-DFT 对开壳单线态的失真与 BS 解的 ⟨S²⟩ 诊断；能隙须 CASPT2/MC-PDFT 级，拒报单参考 ΔE_ST。

### F3. 三角烯三线态基态（Triangulene triplet ground state）
1. **体系**：三角烯（triangulene，C22H12，最小非 Kekulé 稠环芳烃）的基态自旋态与单三态能隙。
2. **结构**：双自由基式 SMILES `[CH]1C2=C3C(=CC=C2)[CH]C4=CC=CC5=C4C3=C6C1=CC=CC6=C5`（C22H12，D3h，两个 NBMO 无法配对成 Kekulé 结构）；三线态基态（³A2′），开壳单线态为第一激发态。
3. **多参考性质**：非交替子格失衡（Lieb 定理 S=1）使两个 NBMO 近简并，单线态为双组态；RKS 完全无法描述开壳单线态，UKS 对三态可用但单三态能隙超出单参考精度。
4. **诊断证据**：表面合成 + nc-AFM 单分子确证（Pavliček et al., 2017, Nat. Nanotechnol. 12, 308，DOI 10.1038/nnano.2016.305）；三叔丁基三角烯 EPR 三态基态（Inoue/Nakasuji et al., 2001, JACS 123, 12702 [卷页约]）；金属表面三态基态 STS（Li et al., 2020, Phys. Rev. Lett. 124, 177201）；两个最小三角纳米石墨烯磁基态观测（Turco et al., 2023, JACS Au 3, 1358）；计算 ΔE_ST ~ 20 kcal/mol 量级（三态低）[约]。
5. **兄弟题**：芘（pyrene，SMILES `c1cc2ccc3cccc4ccc(c1)c2c34`）——同为 zigzag 边稠环芳烃，闭壳层 Kekulé 体系，基态/激发态单参考可算。
6. **权威性依据**：Clar 非 Kekulé 烃 70 年悬案的实验终结（2017 年期刊封面）；Lieb 定理与 Ovchinnikov 规则的教科书演示体系。
7. **拒答判据**：从子格计数（2 个多余星标原子）直接判定无 Kekulé 结构；区分三态（UKS 可算）与开壳单线态（必须双组态）；拒绝用 RKS 报"单线态基态"能量或能隙。

### F4. 联苯桥联三角烯二聚体的微弱交换耦合（Triangulene dimer linked by para-biphenyl）
1. **体系**：两个三角烯经 para-联苯单元连接的二聚体（C56H30 级）的开壳单线态基态与近零单三态能隙。
2. **结构**：SMILES `[CH]1C2=C3C(=CC=C2)[C](c2ccc(-c4ccc([C]5C6=C7C(=CC=C6)[CH]C8=CC=CC9=C8C7=C%10C5=CC=CC%10=C9)cc4)cc2)C2=CC=CC4=C2C3=C5C1=CC=CC5=C4`（二聚体代表式；每个三角烯单元各含一对 NBMO，单元间弱耦合）；开壳单线态基态。
3. **多参考性质**：单元内 S=1、单元间交换耦合仅 ~meV 级——多自由基（4 个未配对电子）弱耦合极限，低自旋态组态数爆炸；单参考方法连正确的自旋态序列都无法给出。
4. **诊断证据**：Au(111) 表面合成 + STM/nc-AFM/STS 实测 Dimer 1 ΔE_ST = 15 mV（开壳单线态）、柔性前体 Dimer 2′ ΔE_ST = 6.6 mV（Angew. Chem. Int. Ed. 2025，DOI 10.1002/anie.202501874，2025-02 在线）。
5. **兄弟题**：对三联苯（p-terphenyl，SMILES `c1ccc(-c2ccc(-c3ccccc3)cc2)cc1`）——同 para-联苯连接拓扑的闭壳层 π 体系，基态与扭转势垒单参考可算。
6. **权威性依据**：三角烯自旋链/自旋 1/2 海森堡模型研究的最新实验前沿（同一 Au(111) 平台文献族：Pavliček 2017、Turco 2023、本条目 2025）。
7. **拒答判据**：识别"单元内强关联 × 单元间弱耦合"的双重多参考结构；指出 meV 级能隙下任何单参考/BS-DFT 数值都不具预测性；需多组态（CAS 类或有效自旋模型映射）处理，拒报单参考能隙。

### F5. Zethrene 及七并 zethrene 的开壳单线态基态（Zethrene/heptazethrene diradical character）
1. **体系**：zethrene（C24H14，二苯并[de,mn]萘并萘）及纵向延展同系物（heptazethrene/octazethrene）的基态电子结构。
2. **结构**：zethrene SMILES `C1=CC2=C3C(=C1)C=C4C5=CC=CC6=C5C(=CC=C6)C=C4C3=CC=C2`（闭壳层 Kekulé 式，C24H14）；单线态基态，延展同系物开壳特征递增。
3. **多参考性质**：四条 zigzag 边使 HONO/LUNO 占据数偏离 0/2，zethrene 母体 y0 ≈ 0.4 量级 [约]，heptazethrene 起进入开壳单线态基态；RKS-DFT 出现对称破缺不稳定，UKS 解 ⟨S²⟩ 污染显著。
4. **诊断证据**：zethrene 衍生物首批合成（Wu T.-C., Tobe, Wu Y.-T. et al., 2010, Angew. Chem. Int. Ed. 49, 7059，经 Springer Top. Curr. Chem. 2017 综述引用）；**heptazethrenebis(dicarboximide) 首个开壳单线态基态 zethrene 同系物**（Sun, Wu et al., 2011, JACS 133, 11896，DOI 10.1021/ja204501m）；动力学保护 heptazethrene/octazethrene "闭壳还是开壳"系统研究（Li, Wu, Osuka, Casado et al., 2012, JACS 134, 14913，DOI 10.1021/ja304618v）；super-octazethrene 母体 y0 = 81.0%（Zeng, Wu et al., 2018, JACS）[约]；综述 Hu & Wu, 2017, Can. J. Chem. 95, 223（"Modern zethrene chemistry"）。
5. **兄弟题**：苝（perylene，SMILES `C1=CC2=C3C(=C1)C4=CC=CC5=C4C(=CC=C5)C3=CC=C2`）——同尺寸稠环芳烃、全 armchair 边闭壳层，基态与光物理单参考可算。
6. **权威性依据**：Wu/Osuka/Casado 学派开壳 PAH 十年文献链的核心家族；"zethrene 化学"有专门综述（Can. J. Chem. 2017）。
7. **拒答判据**：做 RKS/UKS 稳定性分析发现对称破缺解；查 HONO/LUNO 占据（y0 诊断）；指出 zigzag 边数量与开壳特征的结构关联，拒报单参考带隙/基态能量。

### F6. 七并苯开壳单线态基态（Heptacene open-shell singlet ground state）
1. **体系**：七并苯（heptacene，C30H18）基态电子结构与单三态能隙。
2. **结构**：SMILES `c1ccc2cc3cc4cc5cc6cc7ccccc7cc6cc5cc4cc3cc2c1`；¹Ag（开壳单线态）基态。
3. **多参考性质**：n ≥ 7 并苯的基态波函数为开壳单线态（反铁磁）并向多自由基演化；RKS-DFT 出现对称破缺不稳定，RHF-CCSD(T) 的 (T) 校正失真；与 C5（六并苯，n=6 处于边界）互补——七并苯是"明确越过开壳边界"的代表。
4. **诊断证据**：聚合物基质中光化学生成七并苯（Mondal, Shah & Neckers, 2006, JACS 128, 9612，DOI 10.1021/ja063823i，被引 355）；五/六/七并苯合成-稳定性-光化学系列（Mondal, Tönshoff, Khon, Neckers & Bettinger, 2009, JACS 131, 14281）；自旋极化 DFT 预言 n>7 反铁磁（开壳单线态）基态（Jiang & Dai, 2008, JCP [128, 164706 约]，arXiv:0708.1777，被引 275）；高并苯基态本质 DMRG 研究（Yang, Davidson & Yang, 2016, PNAS [113, E5098 约]，被引 236）；DMRG 基准 Kurashige & Yanai, 2009, JCP 130, 234114 [未核实]；C5 条目已立的 DMRG 证据链（Hachmann et al., 2007）同样覆盖 n=7。
5. **兄弟题**：蒽（anthracene，SMILES `c1ccc2cc3ccccc3cc2c1`）——同族短并苯（n=3），闭壳层，CCSD(T)/DFT 可靠（与 C5 的萘兄弟互补）。
6. **权威性依据**：长并苯基态争议是高被引公共事件（Bendikov 2004 起，被引逾千）；七并苯是唯一有实验谱学锚点的"明确开壳"母体并苯。
7. **拒答判据**：识别 RKS/UKS 不稳定与自然轨道占据偏离；指出单参考带隙/基态能量在 n≥7 不可信；需 DMRG/CAS 级，拒绝硬算。

### F7. Thiele 烃（Thiele's hydrocarbon）【边缘候选】
1. **体系**：Thiele 烃（四苯基对醌二甲烷，C32H24）单线态基态与单三态能隙。
2. **结构**：醌式 SMILES `C1(=C(c2ccccc2)c2ccccc2)C=CC(=C(c2ccccc2)c2ccccc2)C=C1`（C32H24）；单线态基态。
3. **多参考性质**：对醌二甲烷骨架存在闭壳层醌式 Kekulé 结构，故双自由基特征中等（y0 ≈ 0.25–0.35 [约]），弱于 Chichibabin；属"中等 MR 灰色地带"。
4. **诊断证据**：方法学系统对比 Sun et al., 2025, JCTC 21, 1194（DOI 10.1021/acs.jctc.4c01384，Thiele/Chichibabin/Müller 三体系统一 benchmark）；Thiele 类化合物取代基调控双自由基特征（Anglada et al., 2023, J. Org. Chem.，DOI 10.1021/acs.joc.3c00482，被引 14）；实验 ΔE_ST ~ 9 kcal/mol 量级（单线态低）[未核实]；Abe, 2013, Chem. Rev. 113, 7011。
5. **兄弟题**：1,1-二苯基乙烯（SMILES `C(=C)(c1ccccc1)c1ccccc1`）——同二苯亚甲基砌块的闭壳层烯烃，单参考可算。
6. **权威性依据**：醌二甲烷双自由基化学百年经典（Thiele 1904）；2023–2025 年仍被用作 y0 可调性的模型平台。
7. **拒答判据**：识别醌式 BLA 与 NBMO 占据偏离的"中等"信号；本题作为灰色地带判别训练样本——y0 仅中等，终选时可优先淘汰（同 C6 戊搭烯定位）。

---

## 检索说明

**实际核实过的出处**（含检索渠道）：

- **Phenalenyl/pancake 键（F1）**：全文核实 Mansikkamäki & Tuononen, 2018, *J. Phys. Chem. Lett.* 9, 3624–3630（DOI 10.1021/acs.jpclett.8b01507，开放获取全文）——其中 J = −1390 cm⁻¹(SQUID)/−2910 cm⁻¹(EPR)、层间距 3.201 Å、二聚化焓 −31.4/−36.8/−39.9 kJ/mol 均取自该文；其参考文献列表同时核实 Goto 1999 (JACS 121, 1619)、Takano 2002 (JACS 124, 11122)、Small 2004 (JACS 126, 13850)、Suzuki 2006 (JACS 128, 2530)、Huang & Kertesz 2007 (JPCA 111, 6304)、Tian & Kertesz 2010 (JACS 132, 10648)、Mota/Miller/Novoa 2009 (JACS 131, 7699)、Cui/Lischka/Kertesz 2014 (JACS 136, 5539)、Ukai 2007 (Polyhedron 26, 2313)。
- **Chichibabin/Thiele（F2/F7）**：PubMed 核实 Sun et al., 2025, *JCTC* 21, 1194–1202（DOI 10.1021/acs.jctc.4c01384，被引 14）；arXiv:2305.00369（ppRPA 论文）Table 6 核实 Chichibabin ΔE_ST 文献参考值 −5.5 kcal/mol；PMC9136924（*Angew. Chem.* 2022 前言）核实 Montgomery 1986 磁化率/ESR 结论；PMC10336959 核实 Anglada 2023（DOI 10.1021/acs.joc.3c00482）；Thieme 综述（DOI 10.1055/s-0037-1611887）核实 y0(CH)=0.72；FSU 学位论文参考文献核实 Abe, *Chem. Rev.* 2013, 113, 7011 卷页。
- **Triangulene（F3/F4）**：PubMed 核实 Pavliček et al., 2017, *Nat. Nanotechnol.* 12, 308–311（DOI 10.1038/nnano.2016.305）；多篇 arXiv 引文核实 Li et al., 2020, *PRL* 124, 177201 与 Turco et al., 2023, *JACS Au* 3, 1358；Wiley 在线全文核实联苯桥联三角烯二聚体 ΔE_ST = 15 mV / 6.6 mV（DOI 10.1002/anie.202501874）。
- **Zethrene（F5）**：PubMed 核实 Sun et al., 2011, *JACS* 133, 11896（DOI 10.1021/ja204501m）及 Li et al., 2012, *JACS* 134, 14913（DOI 10.1021/ja304618v，PMID 22908899）；Springer *Top. Curr. Chem.* 2017 参考文献核实 Tobe 组 2010（*Angew.* 49, 7059–7062）；Cell Press 参考文献核实 Hu & Wu, *Can. J. Chem.* 2017, 95, 223 与 Zeng et al., 2016, *Angew.* 55, 8615（DOI 10.1002/anie.201602997）；X-MOL 核实 super-octazethrene 母体 y0 = 81.0%。
- **Heptacene（F6）**：PubMed 核实 Mondal et al., 2006, *JACS* 128, 9612–9613（DOI 10.1021/ja063823i，被引 355）；Qucosa 论文集核实 Mondal/Bettinger 2009（JACS 131, 14281）；arXiv:0708.1777 核实 Jiang & Dai "more than seven rings → open-shell singlet" 结论与被引 275；PMC5024645 核实 Yang/Davidson/Yang PNAS 2016（被引 236）。
- **SMILES**：zethrene、heptacene、phenalene、perylene 取自 PubChem PUG-REST；其余手写；全部 14 条 SMILES 已用 RDKit 2026.03.5 解析并核对分子式与自由基数（Chichibabin C38H28/2 自由基、triangulene C22H12/2 自由基、二聚体 C56H30/4 自由基等）。

**标注 [约] 的**（量级可靠、小数位未逐一核对）：Chichibabin ΔE_ST = −5.5 kcal/mol（ppRPA 文转引的文献值）、y0(CH)=0.72（方法依赖）、triangulene ΔE_ST ~20 kcal/mol、zethrene 母体 y0 ≈ 0.4、super-octazethrene y0=81.0%、Jiang & Dai 卷页（JCP 128, 164706）、PNAS 2016 卷页（113, E5098）、Inoue/Nakasuji 2001 卷页、Abe 综述 DOI。

**标注 [未核实] 的**：Montgomery et al., 1986 卷页（JACS 108, 6004 仅为记忆，入库前需复核）；Thiele 实验 ΔE_ST ~9 kcal/mol；Kurashige & Yanai 2009 卷页。

**未纳入的方向及原因**：Clar goblet（C38H18，Mishra et al., 2020, *Nat. Nanotechnol.* 15, 22，被引 464，J_intra ≈ 23 meV 已核实）——是极佳候选，但 PubChem/维基均无该结构记录，手写 SMILES 无法保证拓扑正确，为避免不可解析 SMILES 暂未列入；建议后续从 2025 年溶液合成论文（*Nat. Chem.*，DOI 10.1038/s41557-025-01776-1）的 SI 取标准 SMILES 后补为 F8。Müller 烃——结构记忆不确定（怕写错 SMILES），未单列，其文献锚点已由 F2/F7 的 Sun 2025 JCTC 覆盖。bisphenalenyl——未检索到足够硬的定量锚点，未列。

---

## G. 主族小分子解离曲线与多重键断裂（8 个候选）

### G1. 一氧化碳单线态解离曲线（CO X ¹Σ⁺ dissociation）
1. **体系**：CO 基态 X ¹Σ⁺ 全解离曲线 → C(³P) + O(³P)。
2. **结构**：SMILES `[C-]#[O+]`（已过 RDKit）；单线态，沿 r(C–O) 拉伸。
3. **多参考性质**：碎片 C(³P)+O(³P) 耦合成总单线态需要正确的自旋重耦合（spin recoupling）——RHF 单行列式在拉伸区混入离子组态、解离到错误极限；CCSD(T) 曲线在中长程（≳1.5–2×re）出现非物理行为。平衡区反而单参考良好（W4 级 %TAE[(T)] 低于 10% 阈值），"前半段可算、后半段灾难"的反差正是考点。
4. **诊断证据**：实验 D0 ≈ 11.09 eV ≈ 256 kcal/mol（中性双原子最强键，教科书常数）[约]；拉伸几何 CO 的 MCCI 研究明确指出"both states are strongly multireference"（arXiv:1505.01407）[发表信息未核实]；RHF 解离到离子污染极限为教科书常识（Szabo & Ostlund §3.8 型论证）[约]；平衡区高精度可算性由 W4 光谱常数研究确立（Karton & Martin, 2010, JCP 133, 144102，DOI 10.1063/1.3489113，被引 88，28 个双原子 re 的 RMSD 仅 0.04 pm）。
5. **兄弟题**：CO 平衡区 re/ωe/偶极矩/De（CCSD(T)/CBS 高精度可算）——同一条曲线只考平衡段，仿 E2 模式；对照"段选错了"与"根本不会算"。
6. **权威性依据**：CO 是所有断键曲线方法学论文（DMRG/SHCI/MR-CC）继 N2 之后的第二标配；单线态→三态碎片的自旋重耦合是 CASSCF 教科书的标准开场案例。
7. **拒答判据**：识别解离碎片自旋态（³P+³P）与单线态曲线的耦合要求；声明可信区间（平衡区单参考可行），对拉伸段拒绝报 RHF-CCSD(T)/RKS-DFT 曲线，要求 CASSCF+动态关联级。

### G2. 氟气解离曲线（F2 dissociation）
1. **体系**：F2(X ¹Σg⁺) 全解离曲线 → 2 F(²P)。
2. **结构**：SMILES `FF`（已过 RDKit）；单线态。
3. **多参考性质**：RHF 在平衡键长处即不给束缚态——"Hartree–Fock 连 F2 是稳定分子都算不出来"是量子化学入门课最经典的单参考失败案例；拉伸区静态关联进一步增强。
4. **诊断证据**：RHF 不束缚专题研究："The Hartree–Fock dissociation of F2"（Theor. Chim. Acta，DOI 10.1007/BF00538477：6-31G(d) 下 RHF 波函数在 re 处不稳定、UHF 曲线纯排斥）[作者/年份未核实]；实验 D0 ≈ 1.66 eV ≈ 38 kcal/mol [约]；全价 FCI 级高精度曲线 Bytautas, Nagata, Gordon & Ruedenberg, 2007, JCP 127, 164317（DOI 10.1063/1.2800017，被引 86，CEEIS 方法）；同系列结合能基准 Bytautas & Ruedenberg, 2005, JCP 122, 154110（C2/N2/O2/F2）。%TAE[(T)](F2) 的具体数值本次未核实 [未核实]。
5. **兄弟题**：Cl2 平衡几何、解离能与频率（重卤素单键，CCSD(T)/CBS 可算）[约]——同为卤素单键解离能，对照 F2 的"病态"与 Cl2 的"正常"。
6. **权威性依据**：RHF 不束缚是 Szabo–Ostlund 级教科书内容；Ruedenberg 学派 CEEIS 曲线提供 FCI 质量锚点。
7. **拒答判据**：指出 RHF 参考在 re 处即失效（任何以 RHF 为参考的 MP/CC 起步即带定性错误）；拒绝用 RHF-CCSD(T) 报 F2 全曲线；要求多组态参考或全价 CI 级处理。

### G3. 一氮化硼二聚体的近简并态序（BN X ³Π vs a ¹Σ⁺）
1. **体系**：BN 双原子（与 C2 等电子，10 价电子）的基态归属与 X ³Π–a ¹Σ⁺ 能隙。
2. **结构**：SMILES `[B-]#[N+]`（已过 RDKit）；X ³Π 基态，a ¹Σ⁺ 极低近简并单线态。
3. **多参考性质**：C2（E1）把核换成异核后对称性破缺使态序翻转——BN 基态为三重态，但单线态 a ¹Σ⁺ 与之间距仅数十至一百余 cm⁻¹ 量级，两组态近简并使任何单参考方法对"基态是什么"这一最基本问题都不可靠；高阶 CC 研究显示必须显式计入 T4 才达半定量。
4. **诊断证据**：X ³Π–a ¹Σ⁺ 能隙的实验约束区间 15 cm⁻¹ < Te < 182 cm⁻¹（"Electronic structure of diatomic boron nitride"）[未核实具体出处]；高阶 CC 研究 Karton & Martin, 2006, Theor. Chem. Acc. 115, 330–333（arXiv:physics/0608154："notoriously small X³Π–a¹Σ⁺ excitation energy"，T4 必需、T5 仍影响 ~60 cm⁻¹）；%TAE[(T)]：W4 光谱常数论文明文 "C2, BN, and O3 are pathologically multireference: (T) triples account for as much as 13–19% of the binding energies"（Karton & Martin, 2010, JCP 133, 144102）——BN 为该区间极值端 ~19% [约]；W4-11 数据集同列 BN 为病态（Karton, Daon & Martin, 2011, CPL 510, 165–178）。
5. **兄弟题**：BF（X ¹Σ⁺，与 N2 等电子的闭壳层，SMILES `[B-]#[F+]` 类写法，CCSD(T) 高精度可算）[约]——同为 BX 双原子，对照 BN 的病态与 BF 的正常。
6. **权威性依据**：W4/W4-11 钦定病态 MR 清单 + 高阶 CC 专项研究；与 E1(C2) 构成等电子对照互证。
7. **拒答判据**：识别 ³Π 基态开壳性与近简并 ¹Σ⁺；指出单参考对能隙误差可达数百 cm⁻¹ 量级（连态序都可能报错）；要求 CASSCF+CASPT2/MRCI 或 CCSDTQ 级以上。

### G4. 氧化铍拉伸曲线的自旋重耦合与回避交叉（BeO stretch）
1. **体系**：BeO 基态 X ¹Σ⁺ 沿 r(Be–O) 拉伸的曲线与解离通道。
2. **结构**：SMILES `[Be]=O`（已过 RDKit）；单线态。
3. **多参考性质**：双重陷阱：(i) 基态碎片 Be(¹S)+O(³P) 只能耦合成三态分子态——单线态曲线绝热解离必须走 O(¹D) 激发通道（位于 ³P 之上 1.97 eV），自旋重耦合本质多组态；(ii) 低价离子构型 Be⁺(²S)O⁻(²P) 的 ¹Σ⁺ 曲线与共价曲线回避交叉，曲线中段参考组态权重剧变。W4 学派明文将 BeO 与 BN 并列"病态多参考双原子"。
4. **诊断证据**：Karton & Martin, 2010, JCP 133, 144102（DOI 10.1063/1.3489113，被引 88）摘要明文 "the pathologically multireference BN and BeO diatomics"；离子-共价回避交叉的方法学困难见多参考综述对 LiF 同族问题的讨论（Lischka et al., 2018, Chem. Rev. 118, 7293，多参考方法综述 [卷页约]；LiF FCI 回避交叉位置 Bauschlicher & Langhoff [未核实卷页]）；O(¹D)–O(³P) 间距 1.97 eV（教科书常数）。
5. **兄弟题**：BeO 平衡区 re/ωe 与偶极矩（CCSD(T)/CBS 可算）[约]——同分子只考平衡段；或 BeS 平衡性质 [约]。
6. **权威性依据**：W4/post-W4 论文直接点名；自旋态对称性论证（¹S+³P 无单线态通道）可由 Wigner–Witmer 规则严格推出，无需查表。
7. **拒答判据**：用 Wigner–Witmer 规则推导出单线态曲线无法到达基态碎片；指出离子-共价回避交叉区单参考失效；拒绝报 RHF-CCSD(T) 全曲线与"解离能曲线"结论。

### G5. 乙硅烯解离为两个硅烯（Disilene → 2 SiH2）
1. **体系**：母体乙硅烯 H2Si=SiH2 沿 Si=Si 拉伸 → 2 SiH2(¹A1) 的解离曲线与 Si=Si 键能。
2. **结构**：SMILES `[SiH2]=[SiH2]`（已过 RDKit）；单线态 ¹Ag，近平面 [约]。
3. **多参考性质**：Si=Si 双键拉伸终点是两个弱耦合的 ¹A1 硅烯——波函数沿曲线持续双自由基化（乙烯扭转 B1 的"键拉伸版"重元素类比）；且 SiH2 碎片本身有 σ²/p² 组态混合（类 CH2 但较弱）。CGMT（Carter–Goddard–Malrieu–Trinquier）模型把 trans-bending/解离倾向与碎片 ΔE_ST 直接挂钩：SiH2 的 ¹A1–³B1 能隙 ~21 kcal/mol [约] 是 Si=Si 弱 π 键的结构根源。
4. **诊断证据**：CGMT 模型原始文献 Carter & Goddard, 1986, J. Phys. Chem. 90, 998 [约]；Trinquier & Malrieu, 1987, JACS 109, 5303 [约]；ethene/silaethene/disilene → XH2+YH2 解离的系统对比研究 Sax, 2022（arXiv:2205.01078）[发表信息未核实]；取代乙硅烯在溶液中的解离平衡与 Z→E 异构化经解离-重组路径（ΔG‡(350 K) = 22.7 kcal/mol）见 Kira 综述（Proc. Jpn. Acad. Ser. B 2012，PMC3409869，被引 64）；Si=Si π 键强度 ~23–27 kcal/mol vs C=C ~65 kcal/mol [约]；De(H2Si=SiH2→2 SiH2) 具体数值 [未核实]。
5. **兄弟题**：乙烯 C=C 键能与氢化热（SMILES `C=C`，平衡几何热化学循环，CCSD(T) 可算）——同为"双键强度"问题，对照轻/重主族。
6. **权威性依据**："double bond rule" 与 CGMT 模型是主族多重键教科书内容；Sax 2022 提供直接的同族解离对比计算。
7. **拒答判据**：识别解离渐近为两个 ¹A1 硅烯的开壳单线态耦合；指出 π 键弱到与碎片 ΔE_ST 同量级时单参考键能不可信；要求 CASSCF(4,4) 以上参考。

### G6. 二锗炔 Ar'GeGeAr' 解离为锗炔单体（Digermyne dissociation）
1. **体系**：三联苯基二锗炔 Ar'GeGeAr'（Ar' = C6H3-2,6-Dipp2，Dipp = 2,6-二异丙基苯基）的 Ge≡Ge "三键"解离为两个 Ar'Ge: 单体。
2. **结构**：母体 SMILES `[GeH]#[GeH]`（已过 RDKit；Ar' 取代物 SMILES 过长，入库建议用母体或简化芳基）；单线态，trans-bent C2 构型 [约]。
3. **多参考性质**：形式三键实为一条 σ 键 + 两条近乎瓦解的 π 键——CGMT 极限情形：GeR 碎片单三态能隙大 → trans-bending 极强 → 两端各带孤对电子、仅弱自旋耦合，波函数高度双自由基oid，"三键"键能仅 ~15–20 kcal/mol 量级（真炔 C≡C 的 1/10）。静态关联贯穿整条解离曲线乃至平衡结构。
4. **诊断证据**：合成与结构 Stender, Phillips, Wright & Power, 2002, Angew. Chem. Int. Ed. 41, 1785–1787（"Synthesis and Characterization of a Digermanium Analogue of an Alkyne"）；变温 NMR 给出 Ge–Ge 解离/单体化活化焓 ~15 kcal/mol（经 Chem. Rec. 2011 综述转述，DOI 10.1002/tcr.201100016）[约]；Ge–Ge 键长 ~2.28 Å [约]；弱多重键与孤对效应的理论框架 Power, 1999, Chem. Rev. 99, 3463（"π-Bonding and the Lone Pair Effect in Multiple Bonds between Heavier Main Group Elements"）[约]。定量多参考基准（CASSCF/DMRG 级 Ge2 核心计算）本次未检索到一手出处 [未核实]。
5. **兄弟题**：二苯乙炔 PhC≡CPh（SMILES `C(#Cc1ccccc1)c2ccccc2`，已过 RDKit）——真 C≡C 三键的平衡结构与氢化热，CCSD(T) 可算；同为"形式三键"问题的轻/重对照。
6. **权威性依据**：Power 学派重 14 族多重键化学是近 25 年主族化学的标志性领域（Angew 原始合成 + Chem. Rev. 综述双重确立）；溶液中实际观察到单体-二聚平衡，实验锚点直接。
7. **拒答判据**：识别 trans-bent 几何本身就是"π 键瓦解"的结构信号（CGMT 判据）；指出 DFT（尤其泛函间巨大离散度）与单参考 CC 对 Ge≡Ge 键能不可靠；要求多参考处理二聚体-单体耦合。

### G7. 二硅炔 RSi≡SiR（Disilyne）【边缘候选】
1. **体系**：大位阻硅基取代二硅炔 RSi≡SiR 的 Si≡Si 键性质与解离。
2. **结构**：母体 SMILES `[SiH]#[SiH]`（已过 RDKit）；单线态，trans-bent [约]。
3. **多参考性质**：与 G6 同族的硅版本——Si≡Si 弱 π + 孤对结构，键级争议长期存在；平衡区静态关联预计弱于 Ge 同系物（SiR 碎片 ΔE_ST 较小），属"灰色地带"。
4. **诊断证据**：合成 Sekiguchi, Kinjo & Ichinohe, 2004, Science 305, 1755–1757（"A Stable Compound Containing a Silicon–Silicon Triple Bond"）；Si–Si 键长 ~2.06 Å [约]；键级/多参考性的定量高等级基准本次**未检索到** [未核实]——本题证据链薄于 G6。
5. **兄弟题**：2-丁炔或丙炔的氢化热与平衡结构（闭壳层真三键，CCSD(T) 可算）[约]。
6. **权威性依据**：Science 级合成里程碑，但多参考诊断文献链不完整——**作为边缘候选保留，终选时可优先淘汰或与 G6 合并为"重 14 族炔类似物"一题**。
7. **拒答判据**：同 G6，但需 agent 主动评估"硅版比锗版更接近正常三键"的程度——考察灰色地带判别力。

### G8. 铬二聚体六重键解离曲线（Cr2 sextuple bond）【特例】
1. **体系**：Cr2(X ¹Σg⁺) 全解离曲线——形式六重键（4sσ + 3d 的 1σ+2π+2δ）。
2. **结构**：SMILES 记 `[Cr][Cr]`（已过 RDKit；SMILES 键级上限四重，无法表示六重键，入库需注明形式键级 6）；单线态；re ≈ 1.68 Å，曲线在 ~2.5 Å 处有标志性的浅 shelf（3d 键极短 vs 4s 键长程的双尺度结构）。
3. **多参考性质**：12 个价电子在 3d+4s 壳层的自旋耦合使波函数在任何键长都无主导单组态——价层 CASSCF 在平衡区**连极小值都给不出**，CCSD(T) 既给不出合理键长也完全没有 shelf；这是"平衡区即灾难"的极端案例，比 C2/N2 更甚。
4. **诊断证据**：Larsson, Zhai, Gunst, Umrigar & Chan, 2022, JACS（DOI 10.1021/jacs.2c06357，"The Chromium Dimer: Closing a Chapter of Quantum Chemistry"，被引 137）——DMRG（键维度至 28000、SU(2) 对称）+ SHCI + REPT 组合方与实验曲线定量一致，并修正了振动谱归属；明文记载 "valence CASSCF does not yield a minimum near the equilibrium bond length" 与 "CCSD(T) does not yield a reasonable bond length, nor a shelf region"；DMRG 成名算例 Kurashige & Yanai, 2009, JCP 130, 234114（及 DMRG-CASPT2 跟进 JCP 2011, 135, 094104）；六重键理论史 Goodgame & Goddard, 1981, J. Phys. Chem. 85, 215；Roos, Borin & Gagliardi, 2007, Angew. Chem. Int. Ed. 46, 1469（DOI 10.1002/anie.200603600，"Reaching the Maximum Multiplicity of the Covalent Chemical Bond"）；实验 PES Casey & Leopold, 1993, J. Phys. Chem. 97, 816–830（DOI 10.1021/j100106a005，Cr2⁻ 光电子谱 29 个振动分辨跃迁）；实验 De ≈ 1.4–1.5 eV [约]。
5. **兄弟题**：Na2（或 K2）解离曲线（SMILES `[Na][Na]`，已过 RDKit）——单 σ 键金属二聚体，CCSD 单参考可算的主族对照。**说明：Mo2 不能作兄弟题**——它与 Cr2 同样强多参考（Goodgame & Goddard, 1985, PRL 54, 661 对 Cr2/Mo2 双阱的 GVB 预言即已表明），若收录只能作为另一道 impossible 题而非对照题。
6. **权威性依据**：DMRG（Kurashige–Yanai 2009）与 SHCI/多方法收敛（Larsson–Chan 2022）两代方法的"成名/封笔"算例；"小分子量子化学 grand challenge"的公认地位由 60 年理论-实验拉锯史背书。
7. **拒答判据**：识别六重键 + 近简并 3d/4s 壳层 → 全曲线强静态关联；指出本题连平衡区都不可单参考（区别于 G1/G2 的"平衡区可算"）；唯一正确路径是 DMRG/大活性空间 CASSCF+动态关联，且应声明超出常规 QM 引擎能力——本题同时考核 agent 的"能力边界自知"。

---

## 检索说明

- **检索方式与日期**：2026-08-31，WebSearch + FetchURL（arXiv/PMC/出版社页面）。以下为实际检索到并核实的出处；标注 [约] 的数值为文献公认量级、[未核实] 的为一手出处或小数位本次未查到。
- **已核实的关键出处**（含 DOI/卷页）：
  - Karton & Martin, *J. Chem. Phys.* **133**, 144102 (2010)，DOI 10.1063/1.3489113，被引 ~88（arXiv:1008.4163）——"C2, BN, O3 pathologically multireference, (T) = 13–19% of binding energies" 与 "pathologically multireference BN and BeO diatomics" 两处明文均出自该文，是 G3/G4 的顶梁柱。
  - Karton, Daon & Martin, *Chem. Phys. Lett.* **510**, 165–178 (2011)（W4-11 数据集）。
  - Karton & Martin, *Theor. Chem. Acc.* **115**, 330–333 (2006)（arXiv:physics/0608154）——BN X³Π–a¹Σ⁺ 需 CCSDT(Q) 级。
  - Bytautas, Nagata, Gordon & Ruedenberg, *J. Chem. Phys.* **127**, 164317 (2007)，DOI 10.1063/1.2800017，被引 86（F2 全价 CI 曲线）；Bytautas & Ruedenberg, *J. Chem. Phys.* **122**, 154110 (2005)（C2/N2/O2/F2 结合能）。
  - Stender, Phillips, Wright & Power, *Angew. Chem. Int. Ed.* **41**, 1785–1787 (2002)（digermyne 原始合成，多个论文的参考文献列表交叉确认）。
  - Sekiguchi, Kinjo & Ichinohe, *Science* **305**, 1755–1757 (2004)（disilyne，同上交叉确认）。
  - Larsson, Zhai, Gunst, Umrigar & Chan, *JACS* (2022)，DOI 10.1021/jacs.2c06357，被引 137（Cr2 封笔之作；全文已读，含 valence CASSCF/CCSD(T) 失效的明文引述）；Kurashige & Yanai, *JCP* **130**, 234114 (2009) 与 *JCP* **135**, 094104 (2011)；Roos, Borin & Gagliardi, *Angew.* **46**, 1469 (2007)，DOI 10.1002/anie.200603600；Casey & Leopold, *J. Phys. Chem.* **97**, 816–830 (1993)，DOI 10.1021/j100106a005；Goodgame & Goddard, *JPC* **85**, 215 (1981) 与 *PRL* **54**, 661 (1985)——后五条均从 Larsson 2022 的参考文献列表直接核实。
  - F2 RHF 不束缚专题："The Hartree–Fock dissociation of F2"，*Theor. Chim. Acta*，DOI 10.1007/BF00538477（作者/年份未在检索摘要中显示，标 [未核实]）。
  - digermyne 变温 NMR 活化焓 ~15 kcal/mol：经 *Chem. Rec.* 2011 综述（DOI 10.1002/tcr.201100016）摘要核实 [约]。
- **检索到但放弃/降级的方向**：
  - **Si2 双原子**：多轮检索未能找到"单参考失效/错误态序"的一手权威出处（流传的 HF 错误态序说法无法落实），%TAE[(T)](Si2) 也不在已核实的 W4 清单中——为避免编造，**不列正式候选**；若后续查到 Bauschlicher/Piecuch 组相关工作可再补。
  - **P2**：与 E2(N2) 同构性太强（等电子、同为 ¹Σg⁺ 三重键曲线），且 %TAE[(T)](P2) 数值未核实，判区分度不足，不独立成题。
  - **BF/BO**：BF 判为单参考可算，降级为 G3 的兄弟题；BO 为开壳自由基双原子，证据链不足。
- **SMILES**：全部 13 个拟用 SMILES 已在本地经 RDKit 逐一验证可解析（`[C-]#[O+]`、`FF`、`[B-]#[N+]`、`[Be]=O`、`[SiH2]=[SiH2]`、`[SiH2]`、`[GeH]#[GeH]`、`[SiH]#[SiH]`、`[Cr][Cr]`、`[Na][Na]`、`C=C`、`C(#Cc1ccccc1)c2ccccc2`）。注意 SMILES 键级上限为四重，Cr2 六重键只能记 `[Cr][Cr]` 并另行注明。
- **诚实声明**：所有给出的 DOI、卷页、被引量均来自本次实际检索结果；未查到的数值一律标 [约] 或 [未核实]，无任何虚构引用。G5 的 De(H2Si=SiH2→2 SiH2)、G6/G7 的定量多参考基准是本组条目的主要证据缺口，入库前建议按标注复核。

---

## H. Biradicaloid 过渡态补充族（8 个）

> 与 A 族互补：A 族以烯烃/周环主族反应为主，H 族聚焦**高张力笼状/桥环烃的价异构与桥键断裂**——多数为 C7H8/C6H6/C20H20 等能面上的经典 biradicaloid TS 问题，其中 quadricyclane 兼具 MOST（分子太阳能存储）应用背景。SMILES 均经 RDKit 验证。

### H1. Quadricyclane → Norbornadiene 逆 [2+2] 热开环（Quadricyclane cycloreversion, MOST 回热步）
1. **体系**：四环庚烷（quadricyclane）→ 降冰片二烯（norbornadiene）热环反转，C7H8，MOST 体系的放热回热步。
2. **结构**：SMILES quadricyclane `C1C2C3C2C4C1C34`、norbornadiene `C1C2C=CC1C=C2`（PubChem 连接性 SMILES，RDKit 验证 C7H8）；单线态，TS 为 C1 对称（Q 与 N 均为 C2v）。
3. **多参考性质**：热 π2s+π2s 环反转为 Woodward–Hoffmann 禁阻协同路径，TS 具高双自由基特征（两条 σ 键非同步断裂：IRC 上一条键在 TS 前完全断裂、第二条在 TS 后断裂）；C2v 对称结构实为二阶鞍点。
4. **诊断证据**：MCSCF(8,8)/6-31G(d,p) 定位 C1 TS，MCQDPT2 能垒 32.9–34 kcal/mol，吻合实验 33–33.5 kcal/mol（Qin, Zhao & Davis, 2005, J. Mol. Struct. THEOCHEM 728, 67–70；实验 Frey, 1964, J. Am. Chem. Soc. [卷页未核实] 与 Kabakoff, Buenzli, Oth, Hammond & Berson, 1975, JACS 97[页未核实]）；储能密度 NBD 低于 QC 22 ± 1 kcal/mol（Kabakoff et al.; Rogers; Steele[未核实]）；燃烧动力学建模复现 biradical TS 能垒 36.7 kcal/mol（Wang et al., 2021, Combustion and Flame，被引 17）。
5. **兄弟题**：Q⁺· → N⁺· 自由基阳离子环反转（同连接性、能垒仅 ~5–12 kcal/mol，开壳双重态，UHF/UMP2/UCCSD(T) 单参考研究已确立——THEOCHEM 1998, S0166128098000918）；或 norbornene/norbornadiene 基态氢化热与应变能（闭壳层，CCSD(T) 可算）。
6. **权威性依据**：MOST 分子太阳能存储的核心反应对（综述 Hemauer et al., 2024, ChemPhysChem，被引 42）；直接热异构的 TS 表征直到 2005 年才由 MCSCF 完成——原文明确指出"此前无计算研究，原因正在 TS 的多参考本质"。
7. **拒答判据**：识别禁阻 π2s+π2s 通道 → biradicaloid TS（C2v 约束结构为二阶鞍点）；指出单参考 CCSD(T)/RKS-DFT 对该能垒失真、需 MCSCF(8,8)+动态关联（MCQDPT2/CASPT2）；可对照兄弟题（阳离子通道单参考可算）作答。

### H2. Prismane → 苯价异构化（Prismane → benzene）【证据较弱候选】
1. **体系**：棱柱烷（prismane / Ladenburg benzene，C6H6）→ 苯热异构。
2. **结构**：SMILES `C12C3C1C4C2C34`（PubChem，RDKit 验证 C6H6）；单线态，D3h 笼状 → D6h 平面。
3. **多参考性质**：放热 ~90 kcal/mol [约] 却有约 33 kcal/mol [约] 能垒——与 Dewar 苯（A4）同类的"禁阻但受阻"情形；协同开环须同时断裂两条 σ 键并重组三个 π 键，TS 为双自由基oid；苯光化学反应生成 prismane 的逆过程亦经 1,3-双自由基中间体（光化学教科书共识）。
4. **诊断证据**：实验动力学 Oth, 1968, Angew. Chem. Int. Ed. [未核实卷页]，半衰期约 11 h @ 90 °C、Ea ≈ 33 kcal/mol [约]；**未检索到专门针对 prismane→苯 TS 的 CASSCF/CASPT2 研究**——多参考判据主要由 A4（Dewar 苯）与 H1（quadricyclane）同类禁阻 [2+2] 型环反转的证据链外推 [定性推断]。
5. **兄弟题**：C6H6 价异构体（苯/Dewar 苯/盆苯/prismane/盆烯）基态相对能排序——闭壳层端点热化学，CCSD(T) 可算。
6. **权威性依据**：苯价异构体教科书体系（Scott & Jones, 1972, Chem. Rev. 72, 181 综述 (CH)n 重排）；prismane 全合成（Katz & Acton, 1973）为有机化学经典。
7. **拒答判据**：识别"放热巨大但动力学稳定"蕴含的组态交叉 TS；与 A4 对照说明同为禁阻环反转；**注意本题专门 MR 计算证据缺失，判分时应以"能否类比 A4/H1 推出拒答"为考核点，终选时可作备选**。

### H3. Bicyclo[1.1.0]butane 桥键热开环 → 丁二烯（Bicyclobutane ring opening）
1. **体系**：双环[1.1.0]丁烷 → 1,3-丁二烯（C4H6）热电环开环。
2. **结构**：SMILES `C1C2C1C2`（PubChem，RDKit 验证 C4H6）→ `C=CC=C`；单线态，中央桥 C–C 键断裂 TS。
3. **多参考性质**：桥键断裂半程处为双自由基oid（两个桥头自由基弱耦合）与卡宾oid（3-butenylidene）之间的竞争区域——HF 级计算预言两步机理（3-丁烯叉卡宾中间体），与实验（无卡宾捕获产物、立体专一）冲突，是"单行列式 PES 拓扑定性错误"的教科书级案例。
4. **诊断证据**：HF/3-21G 预言两步机理与实验矛盾、需含关联能重算（Shevlin & McKee, 1988, J. Am. Chem. Soc.，收稿 1987-07-14 [卷页未核实]）；激发态面的 CASSCF 研究将 bicyclobutane 与 butadiene/cyclobutene 并列为必须多组态处理的体系（Chem. Phys. Lett. 2000, PII S0009261400001676 [卷页未核实]）；热开环 Ea ≈ 40 kcal/mol 量级 [约/未核实]。
5. **兄弟题**：bicyclobutane 基态应变能、生成热与氢化热——闭壳层极小点，CCSD(T) 高精度可算（只有 TS 区多参考）。
6. **权威性依据**：Shevlin–McKee 案例被计算有机化学教材与综述反复引用为"HF 伪中间体"代表；C4H6 势能面（butadiene/cyclobutene/bicyclobutane）是 CASSCF 方法学的标准展示体系（COLUMBUS 程序论文亦引用）。
7. **拒答判据**：识别桥键 σ/σ* 近简并 → 单参考 PES 拓扑不可信（可能凭空造出卡宾中间体或漏掉）；要求 CASSCF(4,4) 起步再评机理；区分"基态性质可算"与"开环机理须拒答"。

### H4. 环丙叉卡宾 → 丙二烯开环（Cyclopropylidene → allene）
1. **体系**：单线态环丙叉（cyclopropylidene，C3H4 卡宾）→ 丙二烯（allene）热开环——Doering–Moore–Skattebøl 反应的母体。
2. **结构**：SMILES 卡宾 `[C]1CC1`（二配位卡宾碳，RDKit 记 2 个自由基电子；单线态为成对占据）→ `C=C=C`；单线态。
3. **多参考性质**：反应面上卡宾组态与开壳双自由基组态权重沿坐标剧烈重排；Ruedenberg 学派的全 CI 研究（活性空间从 (4e,4o) 扩到 (8e,8o)，含被拉长的 C–C σ 键相关）表明该面存在分岔（bifurcation）与单构型无法描述的区域——这是"卡宾重排 PES 必须多参考"的奠基性算例。
4. **诊断证据**：全 CI/近全 CI 反应面系列论文（Valtazanos, Elbert, Xantheas & Ruedenberg, 1991, Theor. Chim. Acta 78，系列论文 1–4，DOI 10.1007/BF01112344 与 10.1007/BF01112346，页码按参考文献表为 287/307/327/365 起 [页码对应关系未核实]）；关联效应关键性的通讯（Valtazanos, Elbert & Ruedenberg, 1986, JACS 108, 3147–3149）；MR-CISD/TZ2P//UB3LYP/TZP 现代复核（Bettinger, Schreiner, Schleyer & Schaefer [卷页未核实，约 1998]）；顺旋立体专一生成丙二烯的实验（Doering 系，[未核实具体出处]）。
5. **兄弟题**：丙二烯内旋转能垒与取代丙二烯 R/S 互变热力学——闭壳层扭转坐标，CCSD(T) 可算（同一篇 Bettinger et al. 研究同时覆盖两者，天然对照）。
6. **权威性依据**：Ruedenberg 学派的 C3H4 全面系列是量子化学 PES 分岔理论的经典文献；卡宾开环是全合成中常用的机理模块。
7. **拒答判据**：识别反应物本身即卡宾（二配位碳、σ²/σπ 组态竞争）；指出开环坐标上组态权重剧变、单参考能垒与立体化学预言均不可靠；建议 CASSCF(4,4)+MR-CI/CASPT2。

### H5. 盆苯 → 苯热异构（Benzvalene → benzene）
1. **体系**：盆苯（benzvalene，三环[3.1.0.0^2,6]己-3-烯，C6H6）→ 苯。
2. **结构**：SMILES `C1=CC2C3C1C23`（PubChem，RDKit 验证 C6H6）；单线态，环丙烷环开环 TS。
3. **多参考性质**：放热 ~63 kcal/mol [约] 的价异构化，TS 处环丙烷 σ 键断裂、双自由基oid 特征显著；顺旋/反旋通道的能级排序问题与 H6 的氮杂类似物同源（后者已由多组态波函数研究定量确立）。
4. **诊断证据**：重排动力学与热化学实验（Turro, Renner, Katz, Wiberg & Connon, "Kinetics and Thermochemistry of the Rearrangement of Benzvalene", 1976, JACS [卷页未核实]；活化能 ~26 kcal/mol [约]）；盆苯光化学与量子链过程（Renner, Katz, Turro et al., 1975, JACS 97, 2568）；多组态波函数证据链见氮杂类似物（H6，PCCP 2013，定量锚点齐备）。
5. **兄弟题**：盆苯/富烯（fulvene，SMILES `C=C1C=CC=C1`）/苯的基态相对能与盆苯应变能——闭壳层端点，CCSD(T) 可算。
6. **权威性依据**：苯价异构体家族（Wilzbach & Kaplan 1967 年首次合成盆苯；Scott & Jones 1972 Chem. Rev. 综述）；与 A4（Dewar 苯）构成 C6H6 面上的"禁阻双生子"。
7. **拒答判据**：识别环丙烷开环 biradicaloid TS 与 allowed/forbidden 通道近简并（H6 显示氮杂类似物两者仅差 1.3–8.4 kcal/mol）；单参考方法对通道排序与能垒均不可信。

### H6. 3-氮杂盆苯 → 吡啶 / 3,4-二氮杂盆苯 → 哒嗪（Aza-benzvalene isomerizations）
1. **体系**：3-氮杂盆苯 → 吡啶；3,4-二氮杂盆苯 → 哒嗪（氮杂 Dewar/盆苯家族开环）。
2. **结构**：SMILES 3-氮杂盆苯 `C1=CC2N3C1C23`（RDKit 验证 C5H5N）→ `c1ccncc1`；3,4-二氮杂盆苯 `C1=NN2C3C1C23`（RDKit 验证 C4H4N2）→ `c1ccnnc1`；单线态。
3. **多参考性质**：允许（反旋）与禁阻（顺旋）通道需多组态波函数才能正确定量；禁阻通道经含反式环内双键的中间体（trans-吡啶/哒嗪），反式双键破坏芳香稳定化——allowed/forbidden 能垒差被压到 1.3 kcal/mol（3-氮杂），甚至最低禁阻通道比最高允许通道还低 1.5 kcal/mol，出现"能垒交叉"，Woodward–Hoffmann 排序近乎失效。
4. **诊断证据**：**定量锚点齐备**——Veals et al., 2013, Phys. Chem. Chem. Phys. 15, 13593–13600（DOI 10.1039/c3cp51283e）：多组态波函数方法定位两类通道 TS；3-氮杂盆苯允许/禁阻能垒差 1.3 kcal/mol（Cs 对称，两对通道）；3,4-二氮杂盆苯（C2v）差 8.4 kcal/mol。
5. **兄弟题**：吡啶/哒嗪基态相对热力学、芳香性指数与氮杂苯基态性质——闭壳层芳香体系，单参考可算。
6. **权威性依据**：H5 烃类问题的可计算氮杂版本；PCCP 论文是少数对"盆苯型开环 allowed/forbidden 竞争"给出多组态定量结果的研究。
7. **拒答判据**：识别禁阻通道的组态交叉与反式双键中间体（该中间体本身已偏离单构型描述）；指出 1.3 kcal/mol 量级的通道排序超出任何单参考方法的误差带宽；拒报单参考通道选择性。

### H7. Pagodane ⇌ Dodecahedrane 二电子异构（Pagodane–dodecahedrane isomerization）【机制推理型候选】
1. **体系**：[1.1.1.1]pagodane ⇌ 十二面体烷（dodecahedrane），C20H20 同分异构对——Prinzbach 路线的标志性步骤。
2. **结构**：SMILES pagodane `C1C2C3C4CC5C3C1C67C28C49C56C1CC9C2C8CC7C12`、dodecahedrane `C12C3C4C5C1C6C7C2C8C3C9C4C1C5C6C2C7C8C9C12`（均 PubChem，RDKit 验证 C20H20）；单线态。
3. **多参考性质**：直接协同异构为 2σ→2π 型"二电子过程"，若发生则必经 biradicaloid 过渡区（两条周环 σ 键重组）；Prinzbach 学派长期以 σ-双同芳香（σ-bishomoaromatic）语言讨论该骨架的电子离域——pagodane 双正离子的 σ-双同芳香性已有专门综述。
4. **诊断证据**：pagodane 全合成（Fessner, Sedelmeier, Spurr, Rihs & Prinzbach, 1987, JACS 109, 4626–4642，DOI 10.1021/ja00249a029）；pagodane 路线改进与母体 C20H20 骨架（Wahl, Wörth & Prinzbach, 1993, Angew. Chem. Int. Ed. 32, 1722，DOI 10.1002/anie.199317221）；σ-双同芳香综述（2001, Angew. Chem. Int. Ed. 40, 911，DOI 10.1002/1521-3773(20010302)40:5<911::AID-ANIE911>3.0.CO;2-B）；母体直接异构产率极低、实际路线绕行（Bertau et al., 1997, Chem. Eur. J. [卷页未核实]）。**未检索到针对该中性异构 TS 的多参考计算**——biradicaloid 论断为机理推断 [未核实]。
5. **兄弟题**：pagodane 与 dodecahedrane 的基态异构能差、应变能与振动谱指认——两端点均为闭壳层笼烷，单参考（含色散校正）可算（2024 年 MDPI 振动谱研究即用 DFT 指认 pagodane IR/Raman）。
6. **权威性依据**：十二面体烷合成是 20 世纪有机化学的地标（Paquette 1982 / Prinzbach 1987）；该异构对是"几何分子"与 σ-离域讨论的共同载体。
7. **拒答判据**：识别协同二电子异构的 biradicaloid 本质；说明单参考 TS 搜索很可能给出伪协同结构；同时应承认实验上该反应本就低产率/需多步绕行——agent 可给出"端点可算、机理须拒答"的分层回答。**终选注意：缺专门 MR 计算文献，证据强度弱于 H1/H4/H6，可作备选**。

### H8. [1.1.1]Propellane 中央"反转键"（[1.1.1]Propellane central bond）【边缘候选】
1. **体系**：[1.1.1]螺桨烷（tricyclo[1.1.1.0^1,3]pentane，C5H6）基态中央桥头–桥头键的键性质。
2. **结构**：SMILES `C1C23C1(C2)C3`（PubChem，RDKit 验证 C5H6）；单线态基态。
3. **多参考性质**：中央"反转键"介于无键/弱 σ 键/双自由基之间：VB 研究表明其为电荷转移键（charge-shift bond），共价-离子共振能主导键合——即波函数含显著的双自由基（共价）与离子组态混合；桥头双自由基 VB 结构是理解其反应性（自由基加成）的标准图像。
4. **诊断证据**：电荷转移键论断的 ab initio VB 研究（Wu, Gu, Song, Shaik & Hiberty, 2009, Angew. Chem. Int. Ed. 48, 1407–1410）；实验电子密度研究（Messerschmidt et al., 2005, Angew. Chem. Int. Ed. 44, 3925：中央区 ρ(r) ≈ 0.19 a.u.、∇²ρ > 0——Rzepa 博客 2010 亦讨论）；持续争议的最新文献（Heinz et al., 2025, J. Phys. Chem. A 129, 8973–8981，DOI 10.1021/acs.jpca.5c03794）；VB 视角的反应性综述（Sterling et al., 2020/2021 [期刊卷页未核实]）。专门的 MR 诊断数值（T1/C0²）本次未检索到 [未核实]。
5. **兄弟题**：双环[1.1.1]戊烷（bicyclo[1.1.1]pentane，SMILES `C1C2CC1C2`）基态结构、生成热与桥头取代热化学——同骨架闭壳层分子，单参考可算。
6. **权威性依据**：键性质争议的公共事件级案例（Angew 三次交锋 + 2025 年仍在发 JPCA 质疑文章）；Shaik 电荷转移键理论的招牌体系。
7. **拒答判据**：识别中央键无法用单一 Lewis 结构表示（无键极限 ⇌ 共价键极限 ⇌ 离子极限共振）；指出"用 RKS-DFT 报一个中央键键能/键级数字"无意义；建议 CASSCF(2,2)/VB 级分析。**与 C6 同属边缘候选——考键性质判断而非 TS 能垒，终选时可优先淘汰**。

---

## 检索说明

- **检索方式**：WebSearch × 12 轮 + FetchURL × 3（ScienceDirect 摘要页、Springer 参考文献页、PubMed 摘要页），并用 PubChem PUG-REST 批量拉取连接性 SMILES、本地 RDKit（项目 `.venv`，2026.03.5）逐一解析验证分子式与价态。检索日期 2026-08-31。
- **证据强度分级**：H1（quadricyclane）与 H6（aza-benzvalene）证据最硬——均有专门的多组态计算论文 + 实验能垒定量锚点，可直接定稿；H4（cyclopropylidene→allene）有 Ruedenberg 全 CI 系列奠基文献，权威性强但老文献页码对应关系未逐一核对；H3（bicyclobutane）核心文献（Shevlin & McKee）摘要已核实、卷页未核实；H5（benzvalene）实验文献经 Katz 课题组官方出版物列表核实存在，理论 MR 证据部分依赖 H6 外推；H2（prismane）、H7（pagodane）**未检索到专门的多参考 TS 计算**，多参考论断属机理外推，已如实标注 [未核实] 并建议作备选；H8（propellane）是键性质争议题而非 TS 题，MR 诊断数值缺失，标为边缘候选。
- **未成功核实、已放弃写入的具体项**：Shevlin & McKee 的 JACS 卷页（仅核实到收稿日期与摘要内容）；Nguyen/Gordon 1995 年 bicyclobutane MCSCF 研究（未能确认存在，未引用）；prismane→苯的专门 CASSCF 研究（未找到）；pagodane 中性异构 TS 的任何量子化学计算（未找到）。
- **与已有条目的查重**：A4 为 Dewar 苯（bicyclo[2.2.0]hexa-2,5-diene）开环，H5/H6 为盆苯（tricyclo[3.1.0.0^2,6]hexene 骨架）及其氮杂类似物，骨架与反应坐标不同，不构成重复；A6 为分子间 [2+2]，H1 为笼内逆 [2+2] 且带 MOST 应用语境与完整 MCQDPT2 证据链，保留价值独立。

---

## I. 反常键与原子/小分子插入化学（8 个）

### I1. 二氟化二硫 FSSF ⇌ F2S=S 异构化与反常 S–S 键（Disulfur difluoride isomerism）
1. **体系**：F–S–S–F（disulfane 式，C2）与其支链异构体硫代亚硫酰氟 F2S=S（thiosulfoxide 式，Cs）的相对稳定性与互变异构能垒。
2. **结构**：SMILES `FSSF` 与 `FS(=S)F`；单线态基态。实验 S–S 键长 FSSF 189.0 pm、F2S=S 185.6 pm（对比 ClSSCl 195.0、HSSH 205.5 pm）。
3. **多参考性质**：FOOF 的硫类似物——FSSF 的 S–S 键"反常短"且 S–F 键带部分反键成分；自旋耦合 VB（spin-coupled）分析显示硫上初现超配位特征（incipient hypercoordination），两个近似垂直平面的部分 π 型相互作用使 S–S 键级远超形式单键。该键的电子结构对关联处理极端敏感：Hartree–Fock 在**基组极限**下 S–S 键长仍偏长约 45 pm，且 SCF 层面给出**错误的异构体稳定序**（FSSF > F2S=S，与实验相反）。
4. **诊断证据**：HF 极限 S–S 误差 +45 pm 与 SCF 稳定序错误（Wong, Top. Curr. Chem. 231, 1–29, 2003，DOI 10.1007/b11909，综述 Marsden 等的电子衍射+理论联合研究）；XSSX/X2S=S 异构化系统研究 Bickelhaupt, Solà & Schleyer [未核实卷页，约 1995]；G2/G3/CBS-QB3 生成热研究 Denis & Ventura, J. Mol. Struct. (THEOCHEM), 2004（ScienceDirect S016612800400096X）；FSSF→SSF2 热异构能垒 ~1 eV（基质隔离 IR，Z. Naturforsch. A 1975，DOI 10.1515/zna-1975-0907，CNDO 估计值 [约]）；自旋耦合 VB 成键分析 Cooper et al., JACS [未核实卷页]。注：MP2 级关联可大部分修复几何与稳定序——本题的"不可能"性集中于 RHF 参考本身的定性失败与 (T) 校正对该反常键的敏感性，严格性弱于臭氧族，可作边缘处理。
5. **兄弟题**：HSSH（二硫烷，SMILES `SS`）结构、扭转势垒与振动频率——闭壳层二硫烷，从头算可精确复现（Wong 综述明文），单参考可算。
6. **权威性依据**：Martin/Wong 学派"反常键"系列（FOOF、FNO 的硫族对应物）；Bickelhaupt–Solà–Schleyer 与 Marsden 实验-理论联合链。
7. **拒答判据**：识别 FSSF 的反常键本质（SCF 键长误差 45 pm、SCF 稳定序错误）；指出基于 RHF 参考的廉价方法与单参考 DFT 训练的 MLIP 对 S2F2 异构体相对能/异构化垒不可信；要求 CCSD(T)/CBS 或 Wn 级并核对 T1 诊断。

### I2. 硫代臭氧 S3 的开式 C2v vs 环状 D3h 基态之争（Thiozone）
1. **体系**：S3（thiozone，臭氧的全硫类似物）基态结构、光谱与 S3 → S2 + S 解离。
2. **结构**：SMILES `S=S=S`（开式 C2v 弯曲）；¹A1 基态，实验键长 ~193.2 pm、键角 ~117°。
3. **多参考性质**：臭氧家族成员，基态波函数为闭壳层与双自由基 Lewis 结构的混合（Miliordos 双自由基指数 β = 11%，介于 SSO 的 4.4% 与 O3 的 18% 之间）；**基态构型判定本身是方法敏感的**：SCF/CISD 预言 D3h 环状为全局极小，只有 CASSCF/MR-CISD 才正确给出开式 C2v——单行列式参考直接答错"分子长什么样"。
4. **诊断证据**：SCF/CISD vs CASSCF/MR-CISD 基态序反转（Schaefer et al., 1986 及后续，经 Wong, Top. Curr. Chem. 231, 1 (2003) 综述 [未核实卷页]；D3h 高出 31–44 kJ/mol）；β(S3) = 11%（Miliordos, Ruedenberg & Xantheas, JACS 136, 2808 (2014)，DOI 10.1021/ja410726u，被引 92）；S3 属 Karton/Martin TAEMR 强 MR 子集（%TAE[(T)] > 10%；Karton et al., 2017, J. Comput. Chem. 38, 2063；成员清单经 arXiv:2405.01400 SI 复述为含 BN, C2, Cl2O, FOOF, S3, S4 等）；解离通道 S2(X ³Σg⁻) + S(³P)（Egorov et al., 2024, J. Phys. Chem. A，PubMed 39288079——S2O/S3 首套从头算光谱线表）。
5. **兄弟题**：S2O（disulfur monoxide，SMILES `S=S=O`）基态热化学、几何与频率——同为硫氧化物，但 β 仅 4.4%（Miliordos 2014），¹A' 基态闭壳层主导，CCSD(T) 可算；微波结构早有定论（Tiemann et al., 1974, J. Mol. Spectrosc.）。该对照同时是"陷阱"：硫代臭氧类化合物并非全员多参考。
6. **权威性依据**：TAEMR/W4-17 强 MR 清单 + Schaefer 学派 MR-CI 基态序经典案例 + Miliordos/Xantheas MRCI 成键分析三重证据。
7. **拒答判据**：识别 S3 继承臭氧的双自由基共振（β=11%、%TAE 超阈）；指出 SCF/CISD 会把基态误判为环状 D3h；拒报单参考的 S–S 解离曲线（产物为两个开壳三态碎片）。

### I3. O(¹D) + H2 → H2O 深谷插入反应（Singlet oxygen atom insertion）
1. **体系**：O(¹D) + H2 → H2O(¹A1) 插入（及竞争抽提通道 OH + H）。
2. **结构**：`[O]` + `[H][H]`；总单线态。
3. **多参考性质**：反应物 O(¹D)（2p⁴）是开壳单线态原子，球形对称下需多行列式表示——与 ¹Δg O2 同构的"态本身无法用单行列式表达"问题；1¹A' 面经 C2v 插入无垒进入深约 160 kcal/mol 的 H2O 势阱 [约]，2¹A' 激发面与 ³A'/³A''（O(³P) 通道）面在近入口处交叉/缝，机理判定（插入 vs 抽提 vs 非绝热淬灭）必须多参考 + 非绝热处理。
4. **诊断证据**：插入路径动力学 Hsu, Liu, Pederson & Schatz, JCP 111, 7921 (1999)；激发面效应同组 JCP 111, 7930 (1999)（Schatz 组 O(¹D)+HD 两篇，DOI 10.1063/1.480127 / 10.1063/1.480128）；C2v 插入是否有垒的专门检验 Varandas, Chem. Phys. Lett. 2000（被引 13）；所有可信 PES 均为 MRD-CI/MRCI 级（Schinke–Lester 传统 [未核实卷页]）；O(¹D)–O(³P) 能差 1.967 eV = 45.4 kcal/mol（NIST 原子能级，教科书常数）。
5. **兄弟题**：O(³P) + H2 → OH + H 氢抽提——燃烧化学最经典的三态反应，UKS/UCCSD(T) 单参考可算（同样反应物、不同自旋态，天然对照）。
6. **权威性依据**：反应动力学教科书体系（O(¹D) 是大气化学最重要激发态原子）；Schatz/Liu 实验-理论联合标杆。
7. **拒答判据**：识别 O(¹D) 无单行列式表示；指出 RHF 参考无法均匀描述"开壳单线态原子 + 闭壳层深阱"全路径；拒绝用 RHF-CCSD(T)/RKS-DFT 报插入分支比或速率；指明需 CASSCF/MRCI 级 PES（必要时含旋轨耦合淬灭通道）。

### I4. N2O 单线态解离 N2 + O(¹D) 与自旋禁阻通道（N2O dissociation）
1. **体系**：N2O(X ¹Σ⁺) → N2 + O(¹D)（光解/单线态面）与 N2 + O(³P)（自旋禁阻热解）。
2. **结构**：SMILES `[N-]=[N+]=O`；单线态基态，沿 N–O 拉伸坐标。
3. **多参考性质**：¹A' 解离面绝热关联到开壳单线态 O(¹D)，沿 N–O 拉伸静态关联持续增强；热解主通道 N2 + O(³P) 自旋禁阻，需单/三态势面交叉缝 + 旋轨耦合——同一分子同时考察"¹D 产物的多参考性"与"ISC 机理"，单参考方法只能覆盖平衡区。
4. **诊断证据**：全局 3D ¹A' PES + 波包光解动力学 Schinke, JCP 134, 064313 (2011)，DOI 10.1063/1.3553377，被引 54；N2 + O(¹D) 通道 D0 = 3.699 eV ≈ 85.3 kcal/mol（实验光解文献，193–205 nm 几乎专产 O(¹D)）；单/三态面及其交叉的 MRCI 研究（Chem. Phys. ~2001，ScienceDirect S0301010400002123 [未核实一作]：环状 N2O 异构体高出线性 ~64 kcal/mol，QCISD(T) 垒 ~15 kcal/mol）；热解 Ea ≈ 58–61 kcal/mol（实验 [约]）。
5. **兄弟题**：N2O 平衡区几何、振动频率与热化学——线性闭壳层分子，CCSD(T)/CBS 高精度可算（考核"算能算的、拒不能算的"）。
6. **权威性依据**：大气化学核心物种（平流层 O(¹D) 来源）；Schinke 组 PES-动力学文献链完整。
7. **拒答判据**：识别解离渐近为开壳 ¹D 原子；指出热解速率由 ISC 缝控制、单参考绝热单面框架原则上不适用；只对平衡区性质作答。

### I5. 单线态亚氨基 NH(a¹Δ) + H2 → NH3 插入（Singlet imidogen insertion）
1. **体系**：NH(a ¹Δ) + H2 → NH3 插入反应。
2. **结构**：`[NH]` + `[H][H]`；总单线态。
3. **多参考性质**：NH(a¹Δ) 与 O2(¹Δg) 同构（π² 组态的两种占据严格简并），反应物态本身需双行列式；单线态面经 C2v 插入深 NH3 势阱（放热 >100 kcal/mol [约]），而三态面 NH(X³Σ⁻)+H2 抽提有高垒——自旋态决定机理，单参考方法连反应物都无法正确表示。
4. **诊断证据**：NH(a¹Δ) 淬灭/反应动力学 Bohn & Stuhl, J. Phys. Chem. 97, 7234 (1993)（v 态分辨淬灭速率 [约]，HERO 数据库收录）；三态对照面 N(⁴S)+H2 ⇌ NH(X³Σ⁻)+H 高精度 PES Poveda & Varandas, PCCP 7, 2867 (2005)；NH a¹Δ–X³Σ⁻ 能隙 Te ≈ 1.56 eV（Huber & Herzberg [约]）；¹Δ 双组态本质同 C1（¹O2）。
5. **兄弟题**：NH(X³Σ⁻) + H2 → NH2 + H 氢抽提——UKS 三态单参考可算（同反应物不同自旋态的天然对照，同 D4 模式）。
6. **权威性依据**：¹Δ 双自由基oid 双原子反应性的教科书案例；与 O(¹D)+H2（I3）构成"原子版 vs 双原子版"姊妹题。
7. **拒答判据**：识别 ¹Δ 反应物无单行列式表示（RKS 会把 ¹Δ 与 ¹Σ⁺ 混成平均）；拒绝对单线态插入速率/能垒报单参考数；指明 CASSCF(活性空间含 NH π 体系）+MRCI/CASPT2。

### I6. NH / NF / NCl / SO 的 a¹Δ–X³Σ⁻ 能隙（¹Δ 等电子族）
1. **体系**：O2 ¹Δ 问题的等电子双原子族：NH、NF、NCl、SO 的 a¹Δ 与 b¹Σ⁺ 激发能。
2. **结构**：SMILES `[NH]` / `FN` / `ClN`（可写作 `NCl`）/ `S=O`；X ³Σ⁻ / a ¹Δ / b ¹Σ⁺。
3. **多参考性质**：π*²（或 NH 的 π²）两个电子的两种占据严格简并——¹Δ 在任何单行列式框架内不存在；RKS-DFT 把 ¹Δ 与 ¹Σ⁺ 混为对称破缺平均，系统性低估能隙；该族把 C1（¹O2）的"最小自旋态测试"推广到异核/含氢双原子。
4. **诊断证据**：NH a¹Δ Te ≈ 1.56 eV（Huber & Herzberg [约]）；NF a¹Δ ≈ 1.19 eV [约][未核实精确值]；SO a¹Δ ≈ 0.79 eV（~6350 cm⁻¹ [约]）；NCl(a¹Δ) 作为全气相碘激光储能粒子（I(²P1/2) 能级转移实验：Tang et al., Appl. Opt. 45, 7126 (2006)，PubMed 16946792）；NF a¹Δ 偶极矩实验-理论对照 Harbison et al., 2002（PubMed 11792193）；¹Δg O2 激发能 0.977 eV 作族内锚点（教科书常数，同 C1）。
5. **兄弟题**：各分子 X³Σ⁻ 基态的键长、振动频率与解离能——UKS/UCCSD(T) 单参考可算（同 C1 兄弟题模式）。
6. **权威性依据**：¹Δ 储能粒子是化学激光（COIL/AGIL）物理的核心；Huber & Herzberg 常数表为实验金标准。
7. **拒答判据**：识别 ¹Δ 需两组态（或自旋对称适配）；指出 RKS/RHF 单参考会把 ¹Δ/¹Σ⁺ 混成平均能；只答三态基态性质、拒答单参考 ¹Δ 能隙。

### I7. 硅宾/锗宾 SiH2、GeH2 单三态能隙与 H2 插入（Silylene/germylene）
1. **体系**：SiH2、GeH2 的 ¹A1–³B1 能隙，及 ¹EH2 + H2 → EH4 插入反应（E=Si, Ge）。
2. **结构**：SMILES `[SiH2]` / `[GeH2]`；¹A1 基态（与 CH2 相反，单线态在下）。
3. **多参考性质**：卡宾重同族物——单线态 ¹A1 为 σ²(3p)/π²（sp² 孤对 vs p 空轨道）组态混合，与 ¹CH2 同型但更重；RHF 系统性高估单三态能隙，(T) 诊断超闭壳层阈值；插入反应坐标上 σ 给体/π 受体协同成键使波函数双组态化，RHF 给出人为偏高的插入垒。
4. **诊断证据**：ΔE_ST(SiH2) ≈ 21 kcal/mol（单线态基态；实验值经 Berkowitz et al., JCP, 1987 [未核实卷页] 确立，理论 Balasubramanian & McLean [约]）；ΔE_ST(GeH2) ≈ 22–23 kcal/mol [约]；插入垒 ¹SiH2+H2→SiH4 ≈ 1.7 kcal/mol（高精度理论值，经 Schlegel 组氟代硅烷分解研究引用，wayne.edu Pub 139）；¹GeH2+H2 垒 58(56) kJ/mol vs ¹SiH2 13(6) kJ/mol（Becerra et al., Can. J. Chem. 78 (2000)，被引 46）；T1(¹A1 SiH2) ≈ 0.03 [约][未核实]。
5. **兄弟题**：³B1 SiH2/GeH2 三态几何与振动频率——UKS 单参考可算；或 SiF2 能隙（σ 给体/π 受体氟取代使能隙大、单线态闭壳层主导，CCSD(T) 可算，类比 C2 的 CF2 兄弟题）[约]。
6. **权威性依据**：主族卡宾类似物化学（Gaspar/Becerra/Walsh 动力学学派 + Schlegel/Gordon 理论学派）；半导体 CVD 机理的基础物种。
7. **拒答判据**：查 T1 发现 ¹A1 超阈；识别 σ²/π² 组态混合（同 ¹CH2 判据的重同族推广）；拒报 RHF/RKS 单参考能隙与插入垒；指出需 CASSCF(2,2)+动态关联。

### I8. 磷宾 HP 的单线态问题（Phosphinidene）【边缘候选】
1. **体系**：母体磷宾 H–P（及 PhP）的单线态-三线态能隙。
2. **结构**：SMILES `[PH]`；³Σ⁻（或 ³A''）基态，闭壳层单线态为激发态。
3. **多参考性质**：氮宾/卡宾的磷同族物——三线态基态高出单线态 20–28 kcal/mol；单线态虽为闭壳层，但 σ²/p² 组态混合使 RHF 参考质量差（同 ¹CH2 判据）。**边缘原因**：与 C3（苯基氮烯开壳单线态）不同，HP 单线态是闭壳层，MR 强度较弱；本题主要考核 agent 能否正确迁移"卡宾/氮宾判据"到磷族而非机械拒答。
4. **诊断证据**：母体 PH 三态基态、单线态高出 ~28 kcal/mol（Nguyen et al., JOC 1996，DOI 10.1021/jo9604393，被引 119，"In Search of Singlet Phosphinidenes"）；室温稳定单线态磷宾综述与母体数据复述（Liu et al., Chem 2016，被引 331，"A Singlet Phosphinidene Stable at Room Temperature"：母体 20–28 kcal/mol）；ΔE_ST ≈ 22 kcal/mol（Lu et al., Chem. Eur. J. 2023 综述，DOI 10.1002/chem.202303283）。
5. **兄弟题**：³HP/³PhP 三态基态几何与性质——UKS 单参考可算；或 HCP（磷杂乙炔，SMILES `C#P`）闭壳层基态热化学。
6. **权威性依据**：Nguyen 学派的磷宾电子结构经典 + Bertrand/Lammertsma 稳定化磷宾实验链。
7. **拒答判据**：识别单线态磷宾的组态混合并给出"中等 MR"的定量分级（区别于 TMM/苯炔级强 MR）；三态用 UKS 正常作答——考核分级拒答而非一刀切。

---

## 检索说明

- **已网络核实的出处**（本次检索直接命中）：Miliordos et al., JACS 136, 2808 (2014)，DOI 10.1021/ja410726u（PubMed 24499187，被引 92；β 值 SSO 4.4%、S3 11%、O3 18% 等取自摘要原文）；Wong, Top. Curr. Chem. 231, 1–29 (2003)，DOI 10.1007/b11909（FSSF 的 HF 极限键长误差 45 pm、SCF 稳定序错误、S3 的 SCF/CISD vs CASSCF/MR-CISD 基态序反转、S3 键长 193.2 pm/117° 均取自该综述原文）；Schinke, JCP 134, 064313 (2011)，DOI 10.1063/1.3553377（PubMed 21322686，被引 54）；Hsu/Liu/Pederson/Schatz 两篇 O(¹D)+HD 论文（Schatz 组官方出版物清单核实卷页 JCP 111, 7921/7930 (1999)）；Varandas CPL 2000（被引 13，ScienceDirect 命中）；Poveda & Varandas PCCP 7, 2867 (2005)（第三方论文参考文献列表命中）；Bohn & Stuhl JPC 97, 7234（HERO 收录，年份标 1993 卷 97 [约]）；Tang et al., Appl. Opt. 45, 7126 (2006)（PubMed 16946792）；Harbison et al. 2002（PubMed 11792193）；Nguyen et al., JOC 1996，DOI 10.1021/jo9604393（被引 119，PubMed/kuleuven 全文命中）；Liu et al., Chem 2016（被引 331）；Lu et al., Chem. Eur. J. 2023，DOI 10.1002/chem.202303283；Becerra et al., Can. J. Chem. 78 (2000)（被引 46，SiH2/GeH2+H2 垒 13(6)/58(56) kJ/mol 取自摘要）；Schlegel 组 SiH2+H2 垒 1.7 kcal/mol（Wayne 组出版物 PDF 命中）；Denis & Ventura THEOCHEM 2004 与 1998 双分子通道（ScienceDirect 命中）；Z. Naturforsch. A 1975 基质 IR（DOI 10.1515/zna-1975-0907）；Egorov et al. 2024 JPCA S2O/S3 线表（PubMed 39288079）；N2+O(¹D) 通道 D0 = 3.699 eV（DICP 光解论文）；TAEMR 成员含 S3/S4（arXiv:2405.01400 SI 复述 Karton 等标准）。
- **S2O 的降级处理（重要负面结论）**：用户建议方向中的 S2O（disulfur monoxide）经核实**不适合作为强多参考候选**——Miliordos JACS 2014 给出其基态双自由基指数 β 仅 4.4%，低于 SO2（3.5% 同量级）而远弱于 O3（18%）与 S3（11%）；且 TAEMR 强 MR 清单（阈值 %TAE[(T)]>10%）含 S3、S4 而不含 S2O。故以 **S3（thiozone）替代为 I2**，并把 S2O 改作 I2 的兄弟题——这同时提供了一个有价值的"陷阱对照"：臭氧的硫类似物并非全员多参考，agent 不应见"臭氧类似物"就机械拒答。
- **FSSF 的证据强度说明**：检索确认其失效主要在 **HF/SCF 层面**（键长 +45 pm、稳定序错误），MP2 可大部分修复——严格性弱于臭氧族强 MR 条目，已在条目内明文标注"可作边缘处理"；其 impossible 档合理性来自 Martin/Wong 学派"反常键"传统与 VB 分析的超配位/双自由基oid 键本质。
- **标 [未核实] 的项**：Bickelhaupt–Solà–Schleyer 与 Cooper spin-coupled VB 的卷页、Chem. Phys. ~2001 N2O ISC 论文一作、Berkowitz 1987 SiH2 卷页、Schinke–Lester O(¹D)+H2 PES 原始卷页、T1(¹A1 SiH2)≈0.03、NCl a¹Δ 精确能值。
- **标 [约] 的项**：FSSF 异构垒 ~1 eV（CNDO 估计）、H2O 势阱深度 ~160 kcal/mol、N2O 热解 Ea 58–61 kcal/mol、NH/NF/SO 的 a¹Δ Te（1.56/1.19/0.79 eV）、SiH2/GeH2 能隙 21/22–23 kcal/mol、Schaefer 1986 S3 原始文献卷页。NF a¹Δ 的 Te 我未能从检索中锁定精确值（1.19 eV 为激光文献通行引数，建议入库前查 Huber & Herzberg 或 NIST WebBook 双原子常数表复核）。
- 与现有 32 条无重复：D1（臭氧）与 I2 的关系已在条目内区分；D4（¹CH2+H2）与 I3/I5/I7 为不同反应物族；C1（¹O2）与 I6 为等电子族推广；C2（¹CH2）与 I7 为重同族物对照；C3（氮宾）与 I8 为同族物对照，均在条目内交叉引用。

---

## J. 卡宾/氮烯/硅烯重排与小势能面（7 个候选）

### J1. 乙烯基卡宾 ⇌ 环丙烯重排（Vinylcarbene–cyclopropene rearrangement）
1. **体系**：C3H4 势能面上的单线态乙烯基卡宾（vinylcarbene）⇌ 环丙烯（cyclopropene）——卡宾化学的经典互变，也是丙二烯 ⇌ 丙炔异构化的中间通道。
2. **结构**：乙烯基卡宾 SMILES `C=C[CH]`（¹A′，卡宾碳 σ² 孤对 + 空 pπ 与乙烯基 π 共轭）；环丙烯 SMILES `C1=CC1`（¹A1）；单线态。
3. **多参考性质**：开环/闭环 TS 为环丙烯 C–C σ 键断裂形成的"双自由基 ⇌ 卡宾"二象性中间体；卡宾 HOMO/LUMO 近简并（Mazziotti 组 ACSE 论文摘要原话："卡宾计算必须考虑多参考关联，因为 HOMO 与 LUMO 可近能量简并"）；TS 兼具三元环反芳香oid 特征。
4. **诊断证据**：实验上 1,3-二乙基环丙烯**外消旋比结构异构快约 10 倍**但活化参数几乎相同（log k_rac = 11.8 − 32600/2.3RT；log k_struct = 10.4 − 32300/2.3RT），指向可逆开环的 biradical/carbene 中间体 [约，教科书章节经 ScienceDirect Topics 核实]；单线态乙烯基卡宾实验 ΔHf ≈ 104 kcal/mol vs 环丙烯 66 kcal/mol [约，同来源]；Greenman & Mazziotti, 2010, J. Phys. Chem. A 114, 583–588（ACSE 计算卡宾反应能垒，明示 MR 必要性）；C3H4 全面 PES 研究确认 allene⇌propyne 走 vinylcarbene–cyclopropene 通道（Gu, Guo, Kaiser 等，被引 59 [约]）。
5. **兄弟题**：环丙烯基态应变能、氢化热与热化学（闭壳层三元环，CCSD(T) 可算）；三态乙烯基卡宾（UKS 可算）。
6. **权威性依据**：环丙烯热化学（racemization vs 异构的经典物理有机实验）+ 星际 C3H4 化学 + Mazziotti 2-RDM 方法学的标志性应用对象。
7. **拒答判据**：识别开环 TS 的双自由基/卡宾二象性与卡宾近简并；指出 RHF/RKS 单参考对"外消旋 vs 结构异构速率比"与开环能垒不可靠；需 CASSCF(4,4)+CASPT2 级。

### J2. 亚乙烯基 ⇌ 乙炔异构化（Vinylidene–acetylene isomerization）
1. **体系**：C2H2：H2C=C: ⇌ HC≡CH——最小不饱和卡宾的 1,2-H 迁移，被 Science 2017 称为该反应类型的"prototypical example"。
2. **结构**：亚乙烯基 SMILES `C=[C]`（X̃ ¹A1）；乙炔 SMILES `C#C`（¹Σg⁺）；单线态。
3. **多参考性质**：单线态卡宾的 σ² vs π² 组态混合；异构化能垒仅 ~0.1 eV，落在静态/动态关联平衡极敏感区——半世纪的方法收敛史本身就是一部"电子关联处理史"（RHF 级别下势垒形貌定性错误，浅阱甚至不存在）。
4. **诊断证据**：1981 年两篇原始经典——Krishnan, Frisch, Pople & Schleyer, Chem. Phys. Lett. 79, 408–411（"The vinylidene-acetylene isomerization barrier"）；Osamura, Schaefer, Gray & Miller, JACS 103, 1904–1907（"a very shallow minimum"）；Gallo, Hamilton & Schaefer, JACS 1990, 112（"Vinylidene: the final chapter?"，标题即反映争议史）[页码约]；Chang, Shen & Yu, JCP 1997, 106, 3237（extended ab initio）；CASSCF(10,10) 直接动力学 Hayes, Fattal, Govind & Carter, JACS 2001, 123, 641（"Long live vinylidene!"，被引 105）；现代共识能垒 **~0.1 eV ≈ 2–3 kcal/mol**（DeVine et al., Science 2017, 358, 336–339 正文明写，基于 Carrington et al., JCP 1984, 80, 4347 与 Han, Li & Guo, JCP 2014, 141, 244312 光谱级全维 PES）；异构能 vinylidene 高于乙炔 ≈ 2.0 eV ≈ 46 kcal/mol [约]（Ervin, Ho & Lineberger, JCP 1989, 91, 5974–5992；高精度再估 Lee, Baraban, Field & Stanton, JPCA 2013, 117, 11679）。
5. **兄弟题**：乙炔平衡区键能、键长、频率与原子化能（同一 PES 的乙炔阱底，CCSD(T)/CBS 高精度可算）。
6. **权威性依据**：1,2-H 迁移原型反应；Schaefer/Miller/Bowman/Guo/Field/Neumark 五个学派五十年理论-实验拉锯，证据链从 JCP 1984 连续到 Science 2017。
7. **拒答判据**：识别单线态卡宾双组态；指出 ~2 kcal/mol 能垒低于单参考方法的系统不确定度，且低级别理论下势垒定性错误；需 CASSCF+动态关联或高精度复合方案 + 核量子效应（隧穿混合）；不应报一个无置信度声明的单参考能垒。

### J3. C3H2 三异构体相对能与互变（Cyclopropenylidene / propadienylidene / propargylene）
1. **体系**：C3H2 单线态/三线态势能面：环丙烯亚基（c-C3H2，X̃ ¹A1，全局极小）⇌ 丙二烯亚基（即亚乙烯基卡宾 H2CCC，¹A1）⇌ 丙炔亚基（HCCCH，X̃ ³B 为三线态全局极小，单线态 ã ¹A′ 准线性）。
2. **结构**：c-C3H2 SMILES `C1=C[C]1`；H2CCC SMILES `C=C=[C]`；HCCCH SMILES `[CH]C#C`（卡宾 ⇌ 1,3-双自由基共振）；单线态/三线态并存。
3. **多参考性质**：单线态 propargylene 是 1,3-双自由基 ⇌ 定域卡宾两种电子结构的近简并混合（THEOCHEM 综述明文讨论两种备选结构）；ã ¹A′ 准线性（弯曲势极平），与 X̃ ³B 仅差 ~2 kcal/mol；异构体互变 TS 开壳。
4. **诊断证据**：实验 ΔE_ST(propargylene) ≈ 2.0 kcal/mol（ã ¹A′ Te ≈ 0.09 eV）[约]（Osborn, Vogelhuber, …, McMahon, Stanton, Harding, Ruscic & Lineberger, JACS 2014, 136, 10361–10372，负离子 PES + 理论联合，被引 27）；单线态 propadienylidene 位于 c-C3H2 之上 10–14 kcal/mol [约]（"Singlet and triplet potential energy surfaces of C3H2"，J. Mol. Struct. THEOCHEM，S0166128007004228）；三线态 PES 全局极小为 propargylene X̃ ³B（Kaiser 组 1997 三线态 C3H2 ab initio PES，被引 93 [约]）；CCSD(T)/CBS 级 IE/ΔHf：Lau & Ng, Chin. J. Chem. Phys. 2006, 19, 29（DOI 10.1360/cjcp2006.19(1).29）；c-C3H2 为首个星际探测的环状有机分子、大 ST 能隙 NHC 型 2π 芳香（Lavallo et al., 2006 综述，被引 313）。
5. **兄弟题**：c-C3H2 单线态基态结构、转动常数与偶极矩（闭壳层芳香 NHC，CCSD(T) 高精度可算——正是星际证认的依据）——同一 PES 上"算能算的部分、拒不能算的部分"。
6. **权威性依据**：星际化学明星三异构体；McMahon/Stanton/Lineberger/Ruscic（ATcT）实验-理论联合标杆。
7. **拒答判据**：识别单线态 propargylene 的开壳/双自由基本质与 ~2 kcal 能隙超出单参考误差；拒绝用 RHF 参考报三异构体相对能排序或 ST 能隙；三态可 UKS、单线态必须 CASSCF+CASPT2——agent 应区分处理。

### J4. 甲酰卡宾 ⇌ 环氧乙炔 ⇌ 乙烯酮（Formylcarbene–oxirene–ketene，Wolff 重排原型面）
1. **体系**：C2H2O 单线态 PES 核心区域：甲酰卡宾（formylcarbene/formylmethylene）⇌ 环氧乙炔（oxirene）⇌ 乙烯酮（ketene）——Wolff 重排的最小模型，"oxirene 是不是极小值"是计算化学著名的"存在性问题"。
2. **结构**：甲酰卡宾 SMILES `C(=O)[CH]`（单线态/三线态）；oxirene SMILES `C1=CO1`（¹A1，C2v）；乙烯酮 SMILES `C=C=O`；单线态面。
3. **多参考性质**：oxirene 为 4π 反芳香三元环；**单线态甲酰卡宾与相邻 TS 的 T1 > 0.02**（Sci. Adv. 2023 明写"multireference effects are notable"）；CCSD(T) 与 CASPT2 对"甲酰卡宾 vs oxirene 谁低、是否为极小值"给出**定性相反**的答案；各 DFT 泛函对 oxirene 极小值/TS 归属亦互相矛盾。
4. **诊断证据**：Wang, Marks, Turner, Mebel, Eckhardt & Kaiser, Sci. Adv. 2023, 9, eadg1134（DOI 10.1126/sciadv.adg1134；气相首次探测 oxirene，寿命 ≥ 8±2 μs；文中给出 oxirene T1 = 0.0142、formylcarbene 与 TS1/TS2 的 T1 > 0.02；CCSD(T) 预言 formylcarbene 比 oxirene 低 2.0 kJ/mol，CASPT2(16,14)/CBS 反转为高 20.8 kJ/mol，并指出"formylcarbene 的多参考性此前从未被考虑"）；Scott, Nobes, Schaefer & Radom, JACS 1994, 116, 10159–10164（DOI 10.1021/ja00101a039，CCSD(T)/6-311G(df,p) Wolff 面）；Vacek, Galbraith, Yamaguchi, Schaefer, Nobes, Scott & Radom, J. Phys. Chem. 1994, 98, 8660–8665（标题即"Oxirene: To be or not to be?"）；Guan, Randall, Schaefer & Li, JPCA 2013, 117, 2152–2159（三线态为甲酰卡宾基态，比单线态低 8.4 kJ/mol）；DFT 方法依赖性：Mawhinney & Goddard, THEOCHEM 2003, 629, 263；Wilson & Tozer, CPL 2002, 352, 540。
5. **兄弟题**：乙烯酮基态几何、频率与热化学（闭壳层，CCSD(T)/CBS 可算，ATcT 收录）。
6. **权威性依据**：Wolff 重排百年争议（Kirmse, Eur. J. Org. Chem. 2002, 2193）；Strausz/Schaefer/Radom 学派文献链 + 2023 年实验落锤并在论文中明文给出 T1 诊断——本池证据链最"现成"的条目之一。
7. **拒答判据**：CCSD(T) 输出后查 T1 发现 formylcarbene/TS 超阈；指出 CCSD(T) 与 CASPT2 定性分歧 = 单参考不可信的铁证；识别 oxirene 反芳香性；要求全价 CASPT2 级处理后再谈"oxirene 是否存在、能垒多少"。

### J5. 甲酰氮烯 → 异氰酸（Formylnitrene → HNCO，Curtius 重排原型）
1. **体系**：CHNO：HC(O)N ⇌ H–N=C=O——Curtius 重排（酰基叠氮 → 异氰酸酯）的最小模型，"甲酰氮烯是否为离散中间体、协同 vs 分步"是百年公案。
2. **结构**：甲酰氮烯 SMILES `C(=O)[N]`（¹A′/³A″）；异氰酸 SMILES `N=C=O`；单线态面。
3. **多参考性质**：氮烯单线态的双组态问题（闭壳 σ² vs 开壳 σπ，与 C3 同族）；文献对"单线态（乃至三线态）甲酰氮烯是否为极小值"存在直接冲突——一组工作预言其不稳定、自发重排为 HNCO，另一组给出稳定极小值；方法依赖性本身就是多参考诊断信号。
4. **诊断证据**：计算分歧的明文记录：Zabalov et al., J. Mol. Struct. THEOCHEM 2010（"Why Lewis acids accelerate the thermal Curtius rearrangement of benzoyl azide…"，被引 22，S0166128007004228 同刊条目 S0166128010005804；原文："according to one work formyl nitrene (singlet and triplet) is unstable and spontaneously rearranges to HNCO, whereas from other works…"）；CASPT2 级系统研究：Marchais, Wentrup 等"Formylnitrene, cyanic, isocyanic, fulminic and isofulminic acids and their interrelationships at DFT and CASPT2 levels of theory"（Wentrup 组，经 Marchais 2021 博士论文著录 [期刊卷页未核实]）；芳酰氮烯单线态基态为闭壳层的经典判据（Autrey & Schuster，经同上转述 [约]）；相关羰基氮烯中间体的实验-理论联合研究 Li et al., JPCA 2015, 119, 8903（carbonyl diazide 分解）。
5. **兄弟题**：HNCO 异氰酸基态结构与振动频率（闭壳层准线性分子，单参考高精度可算）；三态甲酰氮烯（UKS 可算）。
6. **权威性依据**：Curtius 重排（1890 年提出）机理核心；Wentrup/Sander 基质隔离学派与 Gritsan/Platz 氮烯化学的直接研究对象。
7. **拒答判据**：识别氮烯单线态双组态与文献级方法分歧；拒绝对"是否存在甲酰氮烯中间体、协同 vs 分步"报单参考结论；要求 CASPT2 级并对单/三线态分别表态。

### J6. 甲氮烯 ⇌ 甲亚胺重排（Methylnitrene → methanimine）【边缘候选】
1. **体系**：CH3N：单线态甲氮烯 1,2-H 迁移 → 甲亚胺 H2C=NH；"单线态甲氮烯是否为离散中间体"的实验争议体系。
2. **结构**：甲氮烯 SMILES `C[N]`（X̃ ³A2 基态）；甲亚胺 SMILES `C=N`；单线态/三线态。
3. **多参考性质**：烷基氮烯单线态以闭壳 σ² 为主，MR 程度弱于芳基氮烯（对比 C3 的开壳 σπ）——本题价值在"灰色地带判别"：能垒小、对方法与组态处理敏感，且存在中间体存在性争议。
4. **诊断证据**：ΔE_ST(CH3N) ≈ 30 kcal/mol（三线态基态）[约]（J. Phys. Org. Chem. 2026, e70074 引为公认值"~30 kcal/mol"）；ATcT ΔHf°(CH3N, g) = 315.3 ± 1.0 kJ/mol（ATcT v1.156，methylimidogen 条目，atct.anl.gov）；单线态甲氮烯中间体存在性的两种诠释（离散中间体 vs 叠氮光解直接重排）见 Gritsan 氮烯动力学综述（会议稿可查 [原始卷页未核实]）；同族对照：乙基亚基（ethylidene）1,2-H 迁移能垒仅 ~1.2 kcal/mol [约]（Platz/Hadad 组，JACS 2002, 124, 7226 引述）。
5. **兄弟题**：甲亚胺基态性质与热化学（闭壳层，ATcT 收录）；三态甲氮烯几何/频率（UKS 可算）。
6. **权威性依据**：氮烯化学入门体系（Platz/Gritsan 学派）；ATcT 热化学锚点现成。
7. **拒答判据**：合格行为是声明置信度、区分单/三线态并指出小能垒对方法的敏感性；**判负行为**是把单线态重排与三态混为一谈盲报能垒。终选时可优先淘汰。

### J7. 二硅烯 ⇌ 硅基硅烯异构面（Disilene ⇌ silylsilylene，Si2H4）【边缘候选】
1. **体系**：Si2H4 单线态 PES：二硅烯 H2Si=SiH2（trans-bent）⇌ 硅基硅烯 H3Si–SiH 及单桥/双桥非经典异构体——乙烯/亚乙基互变在硅族的"答案完全不同"版本。
2. **结构**：二硅烯 SMILES `[SiH2]=[SiH2]`（¹Ag，trans-bent C2h）；单线态。
3. **多参考性质**：Si=Si π 键弱，trans-bent 结构即两个单线态硅宾单元的耦合（二阶 Jahn–Teller / 硅宾-硅宾成键模型），具双自由基oid 特征；硅基硅烯为卡宾类似物（σ² + 空 p），多个近简并非经典极小值曾使单参考排序与实验冲突。
4. **诊断证据**：理论-实验联合确立异构体序：Sari 等"Mono- and dibridged isomers of Si2H3 and Si2H4: the true ground state global minima. Theory and experiment in concert"（被引 83；确认 disilene trans-bent ¹Ag 为 Si2H4 最低异构体）；Si2H4 异构体相对稳定性与热力学系统研究（Chem. Phys. Lett.，S0009261408013808）；非经典桥式结构经毫米波转动光谱探测（经"Nonclassical structures in silicon-containing molecules"综述转述 [未核实卷页]）；二硅烯成键与 trans-bent 综述（Kira 组，Coord. Chem. Rev. 类综述，PMC3409869，被引 64）；同族 Si2H2 面双桥全局极小、单桥高 ~0.44 eV [约]（arXiv:1807.11197）。
5. **兄弟题**：乙烯 H2C=CH2 基态性质与同型 1,2-H 迁移（乙烷骨架）——碳族类似物闭壳层、强 π 键，CCSD(T) 可算；C vs Si 对照本身即考点。
6. **权威性依据**：重主族元素"反常结构"教科书案例（Frenking/Trinquier 理论模型 + 转动光谱实验）；硅宾化学（Becerra/Walsh 动力学学派）基础面。
7. **拒答判据**：识别弱 Si=Si π 键的双自由基oid 本质与卡宾型硅基硅烯；指出单参考方法在该面异构体排序上的历史教训；需 CASSCF 验证波函数稳定性后再报相对能。终选时可优先淘汰。

---

## 检索说明

- **检索方式**：全部条目经 WebSearch/FetchURL 在线核实（检索日期 2026-08-31）。J2、J3、J4 三个条目证据链最硬，关键数值直接取自原文/权威二手（Science 2017 全文、JACS 2014 著录、Sci. Adv. 2023 全文——后者把 T1 诊断与 CASPT2 反转写进正文，几乎为 J4 量身定制）。
- **已在线核实的引用**（DOI 或期刊+卷+页）：J1 的 ACSE 论文（JPCA 2010, 114, 583）；J2 的 CPL 79, 408 / JACS 103, 1904 / JCP 80, 4347 / JACS 2001, 123, 641 / Science 2017, 358, 336 / JCP 1989, 91, 5974 / JPCA 2013, 117, 11679 / JCP 2014, 141, 244312；J3 的 JACS 2014, 136, 10361 与 Chin. J. Chem. Phys. 2006, 19, 29（DOI 10.1360/cjcp2006.19(1).29）；J4 的 Sci. Adv. 2023, 9, eadg1134 / JACS 1994, 116, 10159 / J. Phys. Chem. 1994, 98, 8660 / JPCA 2013, 117, 2152；J5 的 THEOCHEM 2010（被引 22）；J6 的 ATcT 数值（315.3 ± 1.0 kJ/mol）与 JPOC 2026 e70074 转述的 ~30 kcal/mol ST 能隙；J7 的 Sari 等（被引 83）与 Kira 综述（被引 64）。
- **标 [约] 的项**：J1 的外消旋/异构活化参数与 ΔHf（取自教科书章节，原始实验文献未逐篇追溯）；J2 的 46 kcal/mol 异构能与 Gallo 1990 页码；J3 的 propargylene Te ≈ 0.09 eV（Osborn 2014 原文数值未逐项摘出，Berkeley 学位论文引其实验 ST 能隙为 8.57 kJ/mol ≈ 2.05 kcal/mol，与此自洽）；Kaiser 1997 卷页。
- **标 [未核实] 的项**：J5 的 Wentrup 组 CASPT2 论文期刊卷页（仅经 Marchais 博士论文著录）；J6 的 Gritsan 综述原始出处；J7 的单桥 Si2Hn 转动光谱原始卷页。
- **检索后主动放弃的候选**：
  - **苯基卡宾扩环**：与 C3 苯基氮烯同族互补，但单线态苯基卡宾为闭壳 σ²（区别于 PhN 的开壳 σπ），扩环已被常规 DFT 处理（Wong & Wentrup, JOC 1996, 61, 7022–7029，DOI 10.1021/jo960806a；Geise & Hadad, JOC 2002, 67, 2532–2540，DOI 10.1021/jo0162181），MR 诊断信号与 C3 高度重叠且更弱——不收。
  - **羟基卡宾 H–C–OH**：闭壳单线态，其著名问题是**隧穿动力学**而非静态关联（Schreiner et al., Nature 2008, 453, 906；trans-HCOH → H2CO 半衰期 2 h @ 11 K，能垒 29.7 kcal/mol [约]）——不符合本档定义，不收。
  - **SiH2 + H2 插入**：经典直接动力学基准，但单线态硅宾闭壳、MR 特征弱，不收（硅族代表由 J7 承担，且已明确标为边缘候选）。
- **与已有条目的重叠排查**：J2 的 ¹CH2 卡宾化学与 C2/D4 互补（C2 考能隙、D4 考插入反应，J2 考 1,2-H 迁移能垒争议，不重复）；J6 与 C3 同属氮烯但烷基 vs 芳基、闭壳 vs 开壳对照，且 J6 已标边缘；未发现与其他 32 条的实质重复。

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
3. **替代方案**：指明所需方法等级（CASSCF+CASPT2/NEVPT2/MRCI+Q/QMC/FCI 级），并照常交付可可靠计算的图元素。

**判负行为**（不算合理拒答）：仅说"这个体系很难"；报错但不诊断电子结构原因；用单参考方法硬算并报数而无置信度声明；把三态（UKS 可算）与开壳单线态混为一谈。

---

## 定稿圈定（当前 10 条；2026-10-18 移出 A8/B10）

> 2026-09-09 依用户口径重配：总量 ~120 → ~60，impossible 保留 10 对（I/S 兄弟对，每池 id 产
> I+S 两题）。v2 定稿 20 条中剔除：A11（¹O₂ ene，兄弟题开壳）、B5（m-苯炔，兄弟 o-苯炔能隙
> 本身边缘）、G6/G7（重 14 族炔，G7 属灰区）、H7/H8（灰区/证据弱）、I2（S₃ 兄弟设计复杂）、
> I8/J6/J7（灰区）——灰区 6 条全剔，避免"拒答正确性"统计污染。被剔条目留档池内只增不删。
>
> **选题意图不变**：刻意偏向"单参考方法算不了"的体系，考核 agent 是否拒答。

- **当前正选 10（仅产 I 题）**：A1, A5, A7, A9, B9, C3, D2, E2, F3, G8。
- **本轮移出**：A8、B10；不再生成或加载对应正式 JSON，原定义与原始结果保留，缺测不补零，不自动重算。
- **此前正选 12 留档（2026-09-27 新增 B10）**：A1, A5, A7, A8, A9, B9, B10, C3, D2, E2, F3, G8。此名单已由当前十题集合取代。
- **v2 定稿 20 期留档**：A11, B5, G6, G7, H7, H8, I2, I8, J6, J7（v3 剔出）。
- 生成器 `cloudra/benchmark/gen_impossible_tasks.py` 只读当前正选名单；task_id 前缀纪律同
  normal(N)/hard(H)，impossible 用 "I" 前缀（注意与池内 I 族编号撞形，如 II2/II8，生成器
  docstring 需说明消歧约定）。

### 判分哲学（2026-09-01 评审裁决，生成器/runner 设计约束）

- **不内嵌"合理拒答"定义**：上文"拒答判据总则"的三要素与各条目的"拒答判据"字段只是出题质量期望与 judge 上下文素材，**不得**编码为确定性评分规则——勾选式 rubric 可被套话攻破，且实际拒答情境远比三要素复杂。
- **拒答是跨档干扰量，不是本档专利**：agent 在 easy/normal/hard 档同样可能拒答。runner 必须在全部四档把"拒答"统一记录为一等 outcome（区别于"作答"与"失败"）；本档的主指标是**跨档拒答校准**——impossible 该拒、其他档不该拒（其他档拒答按现有 composite 零交付自然扣分）。单看本档拒答率会被"什么都拒"的 agent 刷分。
- **当前判分**：仅保留 I 题的结构化图交付与统一 composite；历史“兄弟题 × 拒答”方案不再执行。

### 风险登记（定稿备注，judge/runner 设计必读）

- **6 条灰色地带正选**（G7 二硅炔、H7 pagodane、H8 propellane、I8 磷宾、J6 甲氮烯、J7 Si2H4）：多参考论断部分为机理外推或"中等 MR"，无专门高等级 MR 计算背书（条目内已标 [未核实]）。这些题上"正确答案"本身在文献中无定论——judge 评估时必须把条目标注的证据强度一并给出，不得按铁板拒答题来判；直接给分方案下建议这些题只进校准矩阵、不进"拒答正确性"统计。
