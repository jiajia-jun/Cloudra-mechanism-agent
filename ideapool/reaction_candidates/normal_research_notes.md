# Normal 档调研笔记（normal.md 的锚点溯源与复查记录）

> 2026-08-30。配套主交付物 `normal.md`（40 条候选池）。本笔记记录每条锚点的查证路径与遗留债务，供评审与生成器作者核对。查证手段：Crossref API（DOI → 标题/卷期页核对）、WebSearch、PubMed/PMC 摘要与全文直读。

## 本次会话直接查证到的文献修正（相对旧池 N1–N62 的著录）

- Houk 环氧化 spiro TS 论文：JACS 1997, **119, 10147–10152**（DOI 10.1021/ja963847x）——旧池误记页码 12982。
- Yamabe Strecker：Beilstein JOC 2014, 10, **1765–1774**（DOI 10.3762/bjoc.10.184）——旧池误记页码 184。
- Henry 反应（甲醛+硝基甲烷阴离子）：Kostal & Jorgensen, **Org. Lett. 2012, 14, 260–263**（DOI 10.1021/ol2030394）。全文表 1 直读：气相 ΔG（相对分离反应物）络合物 +2.3 / TS +5.3（B3LYP/6-31+G**）、TS +5.8（MP2）；AM1/MM 气相 6.7、水中 14.1 kcal/mol → A6 中央垒 3.0 为同表差值。
- Baeyer–Villiger 酸催化加成新机制：Alvarez-Idaboy, **Reyes, Cruz**, Org. Lett. 2006, 8, 1763–1765（DOI 10.1021/ol060261z）——旧池记作 "Alvarez-Idaboy, Reyes, Mora-Diez 2007 OBC"，以本条目为准。
- Curtius：Zabalov & Tiger, **Russ. Chem. Bull. 2005, 54, 2270–2280**（DOI 10.1007/s11172-006-0109-2）。数值（乙酰叠氮协同 32.9 vs 氮宾 32.9 kcal/mol，PBE/TZ2P）转录自 PMC2653059（环丙基/环丙烯酰叠氮 Curtius 综述性研究）的引述 → R3。
- 苯偶姻缩合 DFT：JPCA 2010, **114, 9222–9230**（DOI 10.1021/jp103031q）——旧池的 "He & Xue 2010"。
- Wolff：Comput. Theor. Chem. 2016, **1094, 32–41**（DOI 10.1016/j.comptc.2016.08.020）——旧池的 "Arora 2016"。
- Cannizzaro 中性水助通道：Kua 等，**Life 2024, 14, 933**（DOI 10.3390/life14080933）——formose 核心循环论文，全文直读：CH₂O + CH₂(OH)₂ 歧化 ΔG‡ = 25.8 kcal/mol（B3LYP/6-311G** + PB 连续介质水溶液，未催化最优 TS，氢负直接在碳间转移）；+1 水反而升至 29.5；羧酸/NH₃ 代理催化降 4–8。
- 环氧乙烷水解：Lundin 等，JPCA 2007, 111, 9087–9092（DOI 10.1021/jp073285b），PubMed 摘要直读：B3LYP/6-311+G(d,p) 微溶剂化活化焓——酸性 ≈80 kJ/mol、碱性 ≈60 kJ/mol、中性单水 205 kJ/mol → O4/O5（换算为 14.3/19.1 kcal/mol）。
- 未催化酯化：Lawal 等，J. Mol. Model. 2016, 22, 235（DOI 10.1007/s00894-016-3084-z），摘要直读：乙酸+甲醇未催化环状 TS ΔG‡ = 36 kcal/mol（M06-2X/def2-TZVP）；酸催化姊妹篇 IJQC 2018（DOI 10.1002/qua.25497）→ Y1。
- 杂原子 DA 过渡态系列：McCarrick, Wu & Houk, JOC 1993, 58, 3330–3343（DOI 10.1021/jo00064a020）→ Q2。
- DMDO ee 建模：Schneebeli 等，JACS 2009, 131, 3965–3973（DOI 10.1021/ja806951r）；PMC 直读：spiro 优 planar 7.4 kcal/mol（B3LYP/6-31G*）→ O2。
- Nazarov：Kallel & Houk, JOC 1989, 54, 6006–6008（DOI 10.1021/jo00287a004，torquoselectivity）；Smith & Ulmer, Tetrahedron Lett. 1991, 32, 725–728（DOI 10.1016/S0040-4039(00)74868-4，1,4-戊二烯-3-酮理论）；Flynn 2024 CEJ（UQ eSpace PDF 直读：Tf₂NH/TfOH 催化全取代底物垒 13 kcal/mol）→ Q3。
- MBH：Robiette, Aggarwal & Harvey, JACS 2007, 129, 15513–15525（DOI 10.1021/ja0717865，PubMed 摘要直读——原文底物为**苯甲醛**+丙烯酸甲酯+叔胺，质子转移决速）；Aggarwal, Fulford & Lloyd-Jones, Angew 2005, 44, 1706–1708（DOI 10.1002/anie.200462462）；Price & McQuade, JOC 2005, 70, 3980–3987（DOI 10.1021/jo050202j，半缩醛机理、对醛二级）→ U4。
- Wittig：Robiette, Richardson, Aggarwal & Harvey, JACS 2006, 128, 2394–2409（DOI 10.1021/ja056650q，本次 Crossref 补 DOI）→ U3。
- 阴离子 oxy-Cope：Evans & Golob, JACS 1975, 97, 4765 的**确切 DOI 未落实**（故 Q4 格内不给 DOI）；数值 6.3/8.3（B3LYP/6-31+G* 气相）与 Li⁺ 配位升至 31.8 转录自 Carey Part A 第 10 章的引述（多个教材 PDF 镜像一致）。
- 二苯乙醇酸最小版的相关计算：Sultana, Beilstein JOC 2013, 9, 594–601（DOI 10.3762/bjoc.9.64，环状 1,2-二酮碱催化）→ R6。
- Fischer 吲哚：Koch, Tetrahedron 2021, 91, 132116（DOI 10.1016/j.tet.2021.132116，区域选择性 DFT 模型）→ H1。
- Kolbe–Schmitt：JCIM 2007, 47, 1520–1525（DOI 10.1021/ci700068b，钾酚盐-CO₂ 复合物结构）→ S2。
- 缩醛水解动力学：Kreevoy & Taft, JACS 1955, 77, 5590–5595（DOI 10.1021/ja01626a040）；另有 JACS 1955, 77, 3146（DOI 10.1021/ja01616a075，acetal/chloroacetal 酸水解）→ I3。
- 甲酰胺水解：Bakowies & Kollman, JACS 1999, 121, 5712–5726（DOI 10.1021/ja9837349）；中性双水通道 MP2/aug-cc-pVQZ 垒 19.37 kcal/mol 转录自 J. Braz. Chem. Soc. 论文表格（SciELO 镜像直读，具体卷期未记）→ Y4。
- Menshutkin：Castejon & Wiberg, JACS 1999, 121, 2139–2146（DOI 10.1021/ja983736t）；气相中央垒区间（偶极络合物 −2.9；MP2/6-311++G(2d,2p) 38.5；VBSCF 33.0 偏高；CCSD(T) 级约 30）转录自博论/教程/arXiv 2111.05244 等二手 → S1。
- Prilezhaev：Bach/Schlegel 组过氧酸+烯烃系列中 UQCISD(T) 垒 15.6 kcal/mol（Schlegel 组出版物 PDF 直读）；Shi 2005（J. Mol. Struct. THEOCHEM，ScienceDirect 摘要直读：B3LYP/6-311G(d,p) 系列垒 17.51/19.18/13.93/…）→ O1。
- Michael：JPCA 2018（DOI 10.1021/acs.jpca.7b11803，Cardiff 仓储 PDF 直读：未催化硝基甲烷+肉桂醛 C–C 加成垒 DCM/水 = 31.2/30.5 kcal/mol）→ A7（底物为丙烯醛，按类似体系转录，已登记口径降级）。
- Knoevenagel：JPC B 2017, 121, 5300–5307（DOI 10.1021/acs.jpcb.7b03191，哌啶催化甲醇中全机理）→ A4。
- 亚胺形成：Hall & Smith, JPCA 1998, 102, 4930–4938（DOI 10.1021/jp9810825，G2(MP2,SVP)）→ I1；具体垒值未直读（[部分核实]）。
- Aldol：Pratt, Nguyen & Ramachandran, JOC 2005, 70, 4279–4283（DOI 10.1021/jo0503409，全文 reprint 直读：锂烯醇盐+乙醛气相加成，QCISD 为最佳参考，B3LYP 低估约 5/HF 高估约 6 kcal/mol，垒近沉没）→ A1。

## 遗留债务（圈定 30 条后需回补）

- 完全未核实 4 条：A2（丙酮缩合→异亚丙基丙酮，决速步与垒）、A3（Claisen–Schmidt）、A5（Mannich 决速步垒；Bahmanyar & Houk 2003 卷页未确认）、I2（烯胺形成计算出处未定位）。
- 有文献但缺锚点数值（barrier=null）18 条：A4/I1/I2/I3/I4/Y3/Y4/O3/S2/R1/R2/R4/R5/R6/U2/U3/U4/U5/U6/H1/H2 中能直读数值的有限——按 plan 流程，最终参考值将由 MACE-OMol25 试算标定（computed_by_us=true），文献锚点本来就不作硬线。
- Y2 的 26 kcal/mol 来自学位论文（usal.es）机理对比表（甲酸甲酯 AAC2 ΔG‡ 108.7 kJ/mol）的二手转录，一级出处待定位。
- O1 的 15.6 出自 Schlegel 组 PDF（"UQCISD(T) barrier is 15.6 kcal/mol"，过氧甲酸+乙烯系列），对应底物/几何细节待核；O2 的 14–17 为 QCISD(T)//QCISD 级区间（《The Chemistry of Peroxides》书表转录，乙烯本体值在括号中未展示全）。
- Q1（芳香 Claisen）30–35 与 Q2（杂原子 DA）25–30 均为回忆/区间值，待直读原文表（Osuna 2013 EJOC 表 1/2；McCarrick-Wu-Houk JOC 1993 表）。
- Evans & Golob 1975（JACS 97, 4765）DOI 未落实。

## 格式与解析纪律（给生成器作者）

- normal.md 可直接过 easy 生成器的 ROW_RE/SMILES_RE/VERIFY_RE/能垒格/舒适区格解析（已用脚本全量验证：40/40 行解析成功，锚点数值=预期，DOI 提取=预期主出处；2026-08-30 扩编后 48/48 通过同款自检，见末节）。
- 关键纪律：(i) 能垒格第一个括号（中英文括号都算）前的第一个阿拉伯数字 = 锚点值，故"3 步/¹⁴C/2017"之类数字一律放括号内；(ii) 每格只出现锚点本人的类型记号（ΔH‡/ΔE‡/ΔG‡/Ea），其余写"垒"；(iii) DOI 后必须随中文标点（；，。）或）；(iv) 无锚点数值就不写数字，JSON barrier=null。
- 我手上的验证脚本在 /tmp/validate_normal.py（一次性，未入仓库）：ROW_RE 行解析 + RDKit 校验（SMILES 合法、原子配平、电荷一致、重原子数与舒适区格一致）。生成器写好前可用同款逻辑做回归。
- 注意 RDKit 写法：水合氢离子必须写 `[OH3+]`（`[H3O+]` 解析失败）；烯醇盐 `[O-]` 单键接碳（`C=C[O-]`，不能 `C=[O-]`）。

---

## 2026-08-30 扩编（40 → 48，只增不删）：新条目锚点查证记录

Normal 定义当日更新为**循序渐进三带**（路线竞争判别 → 简单多步 → 复杂人名网络），扩编方向为经典竞争（新 X 族）与杂环化学（H3–H5），另补 U7（铵叶立德，Wittig 考点的 CHNO 版）。**新增条目一律纯 CHNO(F)**；存量含 P/Cl 的 S1/R5/U3 保留，去留待评审打标。以下查证全部由子代理经 Crossref API + PMC/PubMed 全文/摘要直读完成，DOI 逐条核实、未凭记忆填写。

### X 族（取代/消除/取向竞争）

- **X1（F⁻ + 2-氟丙烷，SN2 vs E2）**：二级**氟**代物的气相 PES 是文献空白（Zhen 2023 原文明示 "there is no report available previously for isopropyl halide reactions"，且该文做的也是 Cl/I）。主锚点取最近的二级体系 **F⁻ + iPrCl**：Zhen 等，*Molecules* **2023**, 28, 6269（DOI 10.3390/molecules28176269，PMC10488877 全文 Table 1 直读）：MP2/aug-cc-pVDZ，络合物 −20.7；anti-E2 ΔE₀‡ = **9.1**、inv-SN2 = **11.6** kcal/mol（TS 相对反应物络合物口径，直接符合 central_complex）；CCSD(T)/aug-cc-pVTZ 单点复核 9.0/10.4。体系差异（Cl→F）已登记口径降级。补充：Gronert 1993 JACS 115, 652（DOI 10.1021/ja00055a039，[已核实存在]）；一级氟代物参照 Bento/Bickelhaupt 2008 JCTC 4, 929（DOI 10.1021/ct700318e，[部分核实]）与 Ensing & Klein 2005 PNAS 102, 6755（DOI 10.1073/pnas.0408094102，PMC 直读，有限温自由能口径）。
- **X2（F⁻ + 2-氟丁烷，Zaitsev vs Hofmann 取向）**：Saunders & Gronert, *JOC* **2015**, 80, 10787–10793（DOI 10.1021/acs.joc.5b01983，PubMed 摘要直读）：体系精确命中；结论 E1cb-like TS → **Hofmann（1-丁烯）取向占优**；能垒数值公开渠道查不到（正文付费、SI 无相对能量表）→ 能垒未核，机理锚点 [已核实存在]。注意该文仅 3 次引用，无数值转录可借。
- **X3（乙基三甲基铵 + OH⁻，Hofmann 消除）**：Chempath 等，*JPCC* **2010**, 114, 11977–11983（DOI 10.1021/jp9122198，Crossref+OSTI 双核，摘要直读）：Hofmann 消除 ΔG‡ = **12.8**、SN2 = 23.0 kcal/mol（溶液相 DFT 自由能垒 298 K；参考态未明，已登记口径降级）。辅助：Long 2012 JPCC 116, 9419（DOI 10.1021/jp3014964）、Edson 2012 J. Membr. Sci. 399-400, 49（DOI 10.1016/j.memsci.2012.01.025）。
- **X4（Cope 消除，syn Ei）**：正向气相垒未能核到（Komáromi & Tronchet 1997 JPCA 101, 3554，DOI 10.1021/jp970617b，付费墙 → [已核实存在] 机理锚点）。**逆 Cope** 方向有可核对数值：Krenske & Houk 2012 JACS 134, 2434（DOI 10.1021/ja211568k，PMC3271141 全文直读）：气相分子间 ΔH‡ = 18.2（M06-2X）、ΔG‡ ≈ 31.7（CBS-QB3，相对分离反应物）——方向相反，只写在格内作参考、不作锚点。溶剂效应：Acevedo & Jorgensen 2006 JACS 128, 6141（DOI 10.1021/ja057523x）。

### H 族扩编（杂环化学）

- **H3（Paal–Knorr 呋喃）**：Abbat, Dhaked, Arfeen & Bharatam, *RSC Adv.* **2015**, 5, 88353（DOI 10.1039/c5ra16246g，Crossref 核实；原文被 RSC 反爬挡住）：水介导环化步 Ea = **11.5** kcal/mol、无催化路径垒约 40，总反应气相吸热 +2.5——数值经奥克兰大学学位论文（70–71 页）二手转录、方法级别（M06 vs G2MP2）未核 → [部分核实] + 口径登记。经典实验机理锚点：Amarnath & Amarnath 1995 JOC 60, 301（DOI 10.1021/jo00107a006，注意不是直觉的 jo00108a003）——H2 所引 Amarnath 吡咯版的呋喃姊妹篇。**配平勘误**：呋喃版只脱 **1** 分子水（一个羰基 O 成为呋喃环氧），RDKit 校验时发现初稿写 2 水不配平，已修正。
- **H4（Knorr 吡唑）**：无能垒数值锚点。机理锚点：Singh 等 2000 Can. J. Chem. 78, 1109（DOI 10.1139/v00-104，半经验机理计算，[已核实存在]）；Flood & Dawson 2018 Angew 57, 11634（DOI 10.1002/anie.201805191，PMC6126375 全文直读：腙形成快、**分子内环化决速**、pH 7 时腙被困）。量级估计（室温 ~1 h ⇒ ΔG‡ 约 20–22）为速率反推，不入 gold。
- **H5（雷酸 + 乙炔 → 异噁唑）**：Nguyen, Chandra, Sakai & Morokuma, *JOC* **1999**, 64, 65–69（DOI 10.1021/jo980723p，原文 PDF 直读）：经典垒 **13–14** kcal/mol（CCSD(T)/G2/CASPT2 互证，含 ZPE，**相对分离反应物渐近线** → 口径登记）；SC-VB 独立值 13.5（Karadakov/Cooper/Gerratt 1998）。机理史锚点：Hiberty, Ohanessian & Schlegel 1983 JACS 105, 719（DOI 10.1021/ja00342a007，支持双自由基路径的早期多参考计算——剪枝考点）。Sexton 2016 JPCA 120, 8400（DOI 10.1021/acs.jpca.6b07975）：HCNO+乙烯 11.3（CCSD(T)-F12），vdW 络合物稳定化 1.4–5.8。

### U7（铵叶立德 [2,3] vs [1,2]）

- 主锚点：Heard & Yates, *JOC* **1996**, 61, 7276–7284（DOI 10.1021/jo952227w，Crossref+PubMed 双核）：[1,2] 与 [2,3] 活化能差仅 2 kJ/mol @ ROMP/6-311+G(d,p)（摘要直读）；绝对垒（MP2/6-31G(d) 气相相对叶立德，单分子体系即 central 口径）：[2,3] ≈ 32 kJ/mol（**7.6** kcal/mol）、[1,2] ≈ 44 kJ/mol（10.5）——绝对值转录自 Denmark 组 2005 组会幻灯片扫描件（Table 9 逐字核读），未独立核对原文 → [部分核实]。
- 机理锚点：Biswas, Collins & Singleton 2014 JACS 136, 3740（DOI 10.1021/ja4128289，PMC3971961 全文直读：[1,2] 产物大部分穿过同一 [2,3] TS 后动力学分叉产生）；Ghigo 2010 JOC 75, 3608（DOI 10.1021/jo100367z：Stevens 通道双自由基 vs 协同的底物依赖性）。
- **出题注意**：未取代烯丙基叶立德的 [1,2] 与 [2,3] 产物 connectivity 简并（同为 N,N-二甲基丁-3-烯-1-胺），必须用巴豆基（或同位素标记）才可区分——题面因此取巴豆基底物 `[CH2-][N+](C)(C)CC=CC`（8 重原子）。

### 扩编后的回归

- 全表 48/48 行通过解析纪律自检（ROW_RE/SMILES_RE/VERIFY_RE/能垒格/DOI）+ RDKit 校验（合法、配平、电荷一致、重原子数与舒适区格一致）；新 SMILES 与既有 40 条及 easy 档无重叠。
- 新增口径登记：X1（氯代物转录）、X3（溶液自由能、参考态未明）、H3（二手转录/路径中间体络合物基准）、H5（渐近线口径）；U7 单分子叶立德可挂 CENTRAL。

### 2026-08-30 规范化二轮（题面对 agent 零猜测）

- 规则变更：**催化剂与副产物一律写入 SMILES 两侧**（头部 SMILES 约定已改；原"哌啶等有机碱催化剂不入 SMILES"条款作废）。
- 改动 8 条：A4 哌啶以二甲胺 `CNC` 建模写入（重原子 9→12，上限边缘；JPC B 2017 锚点的哌啶/甲醇体系变为近似建模，已在格内注明）；A5/I2/O3/H1/H2/H3/H4 的酸催化以 `[OH3+]` 写入两侧（电荷 0→+1，重原子各 +1）。
- Q2 条件列 "热反应或 Lewis 酸催化" 改为 "气相热反应（Lewis 酸为经典加速条件，本基准不加入）"——消去可选催化剂歧义。
- 回归：48/48 通过解析纪律 + RDKit 校验 + 新催化剂写入检查（条件列点名催化/酸碱时 SMILES 必含对应物种）；计量性碱（Y3/O4/R5/U1/X3 的 OH⁻）只出现在反应物侧属正常消耗，不算违规。
- 统计联动：电荷态 0×18 / −1×15 / +1×14 / −2×1；重原子 3–7×32 / 8–10×12 / 11–12×4（U4/H1/A3/A4）。

## 2026-08-31 定稿 30 题 + 生成器落地

- **定稿**（按 normal_essence_mining.md 的本质覆盖最大化）：正选 A1 A2 A4 A5 A7 I1 I3 Y2 Y3 O2 O3 O4 O5 X1 X2 X3 X4 R1 R2 R3 U1 U5 U6 U7 Q2 Q3 H1 H2 H3 H5；裁掉 18 条（S1/U3/R5/S2 四个本质整条裁，高周期元素或苯环冗余；其余为同本质归并）。判别对偶双收：Y2/Y3、O4/O5、X1/X2、H2/H3。本质覆盖 27/32。
- **Q2 池子 bug 修正**：产物 SMILES 曾误写 `C1=COCCC1`（3,4-二氢-2H-吡喃，烯醇醚异构体，与题名"3,6-二氢-2H-吡喃"名实不符；Q/H 登记代理穷举发现纯 [4+2] 键账无法得到该连通性）。已改为 `C1=CCOCC1`。
- **生成器**：`cloudra/benchmark/gen_normal_tasks.py`（`python -m cloudra.benchmark.gen_normal_tasks`）+ `cloudra/benchmark/normal_registry/` 按族登记（ai/yo/x/ru/qh.py）。bond_changes 不手填——由相邻步映射 SMILES 差集推导；校验 fail-loud（逐步映射号守恒/电荷守恒/去映射=池内 SMILES/每步有键变化）。task_id 加 N 前缀（normal X 族与 easy X1 撞号）。
- 产物：`ideapool/tasks/normal/N*.json` 30 题（1–5 基元步，single_step=false，accuracy σ=2.0，无锚点题 enabled=false，口径登记 10 题降 unverified）。`test_normal_tasks_regenerate_identically` 守卫同步；tests/test_benchmark.py 86 项全绿。
- H5 注记：池内雷酸 `[C-]#[N+]O` 的 H 在 O 上（RDKit 解析），环加成步含 O→C 质子迁移（登记已处理，显式 [H:6]）。
