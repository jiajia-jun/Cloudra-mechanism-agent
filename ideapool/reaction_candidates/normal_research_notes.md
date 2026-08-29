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

- normal.md 可直接过 easy 生成器的 ROW_RE/SMILES_RE/VERIFY_RE/能垒格/舒适区格解析（已用脚本全量验证：40/40 行解析成功，锚点数值=预期，DOI 提取=预期主出处）。
- 关键纪律：(i) 能垒格第一个括号（中英文括号都算）前的第一个阿拉伯数字 = 锚点值，故"3 步/¹⁴C/2017"之类数字一律放括号内；(ii) 每格只出现锚点本人的类型记号（ΔH‡/ΔE‡/ΔG‡/Ea），其余写"垒"；(iii) DOI 后必须随中文标点（；，。）或）；(iv) 无锚点数值就不写数字，JSON barrier=null。
- 我手上的验证脚本在 /tmp/validate_normal.py（一次性，未入仓库）：ROW_RE 行解析 + RDKit 校验（SMILES 合法、原子配平、电荷一致、重原子数与舒适区格一致）。生成器写好前可用同款逻辑做回归。
- 注意 RDKit 写法：水合氢离子必须写 `[OH3+]`（`[H3O+]` 解析失败）；烯醇盐 `[O-]` 单键接碳（`C=C[O-]`，不能 `C=[O-]`）。
