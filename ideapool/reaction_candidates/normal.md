# Normal 档候选反应清单（量子化学机理推导 agent benchmark）

- 生成日期：2026-08-25
- 档位定义：**经典可算的多步人名反应（2–4 步小分子网络）**。考核 agent 的多步机理假设生成、中间体捕获、竞争路径能垒排序与反应网络剪枝。
- 金标准引擎：**MACE-OMol25**（ωB97M-V/def2-TZVPD 级训练，含反应轨迹）。舒适区：CHNO 主族、中小分子、闭壳层；P/S/卤素与多步网络在训练数据中密度骤降——含这些元素的候选一律标注 **[低密度风险]**。
- 选型原则：经典权威（March/Carey 级教材人名反应、机理共识明确）；可复现（有高被引 DFT/从头算机理研究反复算过）；gold 能垒只需文献锚点（精确性让位给容差，排序一致性优先）；底物小型化（最简单代表底物，重原子 ≤15 左右）。
- 能垒锚点核实状态标注：**[已核实]** = 已用 WebSearch 确认文献真实存在（2026-08-25）；**[部分核实]** = 文献存在但数值/作者/页码未逐条确认；**[未核实]** = 凭教材记忆给出，入池前必须人工或再检索核实。
- 难度标签：★（易，2 步、机理单一）/ ★★（中，3 步或带一条竞争路径）/ ★★★（难，4 步网络或多路径竞争/多参考风险）。
- 所有体系默认单重态闭壳层；离子中间体在"电荷/多重度"栏注明。SMILES 中催化剂以实际参与物种（如 `[OH-]`、`[H3O+]`）写出，净反应式可能因此多出水等小分子，属正常。

---

## 一、周环反应与 σ 迁移（协同步 + 少量中间体）

### N1. Diels–Alder 反应（Diels–Alder reaction）
- 底物：1,3-丁二烯 + 乙烯 → 环己烯
- SMILES：`C=CC=C.C=C>>C1=CCCCC1`
- 电荷/多重度：0 / 1（协同，无离子中间体）
- 条件：气相热反应，~150–200 °C；无催化剂
- gold 机理：协同 [4+2] 环加成（异步但单一 TS）。竞争路径：双自由基分步路径（已证否，但仍是经典剪枝考点：agent 应能排除 stepwise diradical）
- gold 能垒锚点：Ea = 27.5 kcal/mol（实验）— Rowley & Steiner 1951, *Discuss. Faraday Soc.*, 198–213, DOI 10.1039/df9511000198 **[已核实]**；DFT/从头算反复复算（Wiest, Houk, Black, Thomas, *JACS* 1995, 117, 8594）**[部分核实]**
- 舒适区：{C,H}；重原子 6（产物）；无杂原子
- 经典性：有机化学最著名反应；Woodward–Hoffmann 教材标准案例；Bachrach《Computational Organic Chemistry》第 4 章基准集成员
- 难度：★

### N2. 杂原子 Diels–Alder / oxo-Diels–Alder（hetero-Diels–Alder）
- 底物：1,3-丁二烯 + 甲醛 → 3,6-二氢-2H-吡喃
- SMILES：`C=CC=C.C=O>>C1=COCCC1`
- 电荷/多重度：0 / 1
- 条件：热反应或 Lewis 酸催化；气相/惰性溶剂
- gold 机理：协同 [4+2]（极性增大，TS 更异步）。竞争路径：分步两性离子路径；ene 反应路径（甲醛作亲烯体）——天然网络剪枝考题
- gold 能垒锚点：协同 vs 分步对比计算（CAS-MP2）— Sakai 2003, *J. Mol. Struct. (THEOCHEM)*, 630, 177–185 **[已核实]**；绝对能垒数值 **[未核实]**（较全碳 DA 高）
- 舒适区：{C,H,O}；重原子 6
- 经典性：March 15-45；Danishefsky 二烯化学母体
- 难度：★★

### N3. Claisen 重排（脂肪族）（Claisen rearrangement）
- 底物：烯丙基乙烯基醚 → 戊-4-烯醛
- SMILES：`C=CCOC=C>>C=CCCC=O`
- 电荷/多重度：0 / 1
- 条件：热反应 ~170–200 °C，气相或惰性溶剂
- gold 机理：椅式六元环 TS 的 [3,3]-σ 迁移。竞争路径：船式 TS（能垒差即立体化学来源）；双自由基分步路径（已证否）
- gold 能垒锚点：Ea = 30.6 kcal/mol（实验）— Schuler & Murphy 1950, *JACS*, 72, 3155–3159 **[已核实]**；水中加速 ~10³ 的高级别从头算（Davidson, Hillier, Vincent, *Chem. Phys. Lett.* 1995, 246, 536）**[已核实存在]**
- 舒适区：{C,H,O}；重原子 6
- 经典性：March 18-33；Carey Part A；DFT 周环基准常客（Wiest & Houk, *Top. Curr. Chem.* 1996, 183, 1）
- 难度：★

### N4. 芳香 Claisen 重排（aromatic Claisen rearrangement）
- 底物：烯丙基苯基醚 → 2-烯丙基苯酚
- SMILES：`C=CCOc1ccccc1>>C=CCc1ccccc1O`
- 电荷/多重度：0 / 1
- 条件：~200 °C 热反应
- gold 机理：① [3,3]-σ 迁移生成邻位环己二烯酮（去芳构化中间体，可捕获）；② 烯醇-酚互变异构恢复芳香性。竞争路径：对位重排（邻位被占时；经二次 [3,3] = Cope 串联）——网络剪枝考点
- gold 能垒锚点：Claisen 家族实验 Ea 27–32 kcal/mol 区间 **[部分核实]**（动力学汇编，TUE 综述）；B3LYP/6-311+G** 计算垒 ~35 kcal/mol **[部分核实]**
- 舒适区：{C,H,O}；重原子 10
- 经典性：Claisen 1912 原始反应；March 18-34；同位素标记机理研究充分（McMichael & Korver 1979 等）
- 难度：★★（两步：重排 + 互变异构，考中间体捕获）

### N5. Cope 重排（Cope rearrangement）
- 底物：1,5-己二烯（简并重排）
- SMILES：`C=CCCC=C>>C=CCCC=C`
- 电荷/多重度：0 / 1
- 条件：~200–260 °C 气相
- gold 机理：椅式六元环 TS [3,3]。竞争路径：船式 TS；1,4-环己二基双自由基中间体路径（chameleonic TS 之争，1990s 著名机理辩论——剪枝考点）
- gold 能垒锚点：ΔH‡ ≈ 33.5 kcal/mol、ΔS‡ ≈ −13.8 eu（实验，Doering 小组；NIST 气相动力学汇编收录）**[部分核实]**；椅/船立体化学判据 — Doering & Roth 1962, *Tetrahedron*, 18, 67–74 **[已核实]**
- 舒适区：{C,H}；重原子 6
- 经典性：March 18-32；Bachrach 书第 3 章核心案例；Borden/Hrovat 系列计算
- 难度：★

### N6. 阴离子 oxy-Cope 重排（anionic oxy-Cope rearrangement）
- 底物：1,5-己二烯-3-醇钾（模拟为醇盐）→ 5-己烯醛（经烯醇盐互变异构）
- SMILES：`C=CC([O-])CC=C>>O=CCCCC=C`（净式；中性对照：`C=CC(O)CC=C`）
- 电荷/多重度：−1 / 1（醇盐中间体带负电；产物经质子转移）
- 条件：KH/18-crown-6，THF，室温即可（对比中性 oxy-Cope 需 ~200 °C）
- gold 机理：① 去质子化；② [3,3]-σ 迁移生成烯醇盐（驱动整个平衡，keq ~10⁵）；③ 质子化互变异构。竞争/对照：中性 oxy-Cope（能垒高 ~25–30 kcal/mol）
- gold 能垒锚点：去质子化加速 10¹⁰–10¹⁷ 倍 — Evans & Golob 1975, *JACS*, 97, 4765 **[已核实]**；B3LYP/6-31+G* 计算阴离子垒 6.3–8.3 kcal/mol（Carey Part A 引述）**[部分核实]**
- 舒适区：{C,H,O}；重原子 6；阴离子体系注意 MACE 对裸阴离子的描述（建议带一个 K⁺ 或显式溶剂模型讨论）
- 经典性：Evans 阴离子加速是有机化学教科书级现象
- 难度：★★

### N7. Alder-ene 反应（ene reaction）
- 底物：丙烯（ene）+ 乙烯（enophile）→ 1-戊烯
- SMILES：`C=CC.C=C>>C=CCCC`
- 电荷/多重度：0 / 1
- 条件：高温气相（>300 °C）；Lewis 酸可催化
- gold 机理：协同六电子环状 TS（1,5-H 迁移 + C–C 成键）。竞争路径：双自由基分步；与 DA 路径区分（丙烯也可作二烯前体）——剪枝考点
- gold 能垒锚点：TS 结构从头算 — Loncharich & Houk 1987, *JACS*, 109, 6947, DOI 10.1021/ja00257a008 **[已核实存在]**；协同/分步对比（Sakai, *J. Phys. Chem. A* 2007, DOI 10.1021/jp064588t）**[已核实存在]**；绝对垒 ~35–45 kcal/mol 量级 **[未核实数值]**
- 舒适区：{C,H}；重原子 5
- 经典性：March 15-23；Alder 1943
- 难度：★

### N8. 酯热解 Ei 消除 / retro-ene（ester pyrolysis）
- 底物：乙酸乙酯 → 乙烯 + 乙酸
- SMILES：`CCOC(=O)C>>C=C.CC(=O)O`
- 电荷/多重度：0 / 1
- 条件：~400–500 °C 气相热解
- gold 机理：六元环顺式消除（Ei），单一协同 TS。竞争路径：自由基链式（需排除）；表面催化（实验史公案）
- gold 能垒锚点：Ea ≈ 45–48 kcal/mol（乙酸乙酯热解实验，Blades, *Can. J. Chem.* 1954）**[未核实数值]**；实验+理论快热解研究 Vargas 2020, *Chem. Eng. Res. Des.*（S0263876220300940）**[已核实存在]**
- 舒适区：{C,H,O}；重原子 6
- 经典性：March 17-24；DePuy & King *Chem. Rev.* 1960 热消除综述 **[未核实页码]**
- 难度：★

### N9. Cope 消除（Cope elimination）
- 底物：N,N-二甲基乙胺 N-氧化物 → 乙烯 + N,N-二甲基羟胺
- SMILES：`CC[N+](C)(C)[O-]>>C=C.CN(C)O`
- 电荷/多重度：0 / 1（两性离子底物）
- 条件：~120 °C 热解，DMSO 或水
- gold 机理：五元环顺式 Ei 消除，单一协同 TS。竞争路径：区域选择性（Hofmann 取向——多 β-H 底物时）；本底物仅一个 β-碳，网络简单
- gold 能垒锚点：经典综述 Cope & Trumbull, *Org. React.* 1960, 11, 317 **[部分核实]**；数值锚点 **[未核实]**（同类 Ei 消除 Ea ~ 25–35 kcal/mol 区间）
- 舒适区：{C,H,N,O}；重原子 6；N–O 两性离子
- 经典性：March 17-24；Cope 1949 原始工作
- 难度：★

### N10. Hofmann 消除（Hofmann elimination / exhaustive methylation）
- 底物：乙基三甲基铵氢氧化物 → 乙烯 + 三甲胺 + 水
- SMILES：`CC[N+](C)(C)C.[OH-]>>C=C.CN(C)C.O`
- 电荷/多重度：净 0 / 1（季铵阳离子 + 氢氧根，离子对）
- 条件：季铵碱加热（100–200 °C）
- gold 机理：E2 反式消除（OH⁻ 拔 β-H，三甲胺离去）。竞争路径：SN2 进攻甲基生成甲醇 + 乙基二甲胺——Hofmann vs 取代的经典竞争，排序考点
- gold 能垒锚点：经典综述 Cope & Trumbull, *Org. React.* 1960, 11, 317 **[部分核实]**；数值 **[未核实]**
- 舒适区：{C,H,N,O}；重原子 7（季铵）；裸离子对，注意溶剂化/离子对处理
- 经典性：March 17-5；Hofmann 1851
- 难度：★★

### N11. 环丁烯电环化开环（cyclobutene ring opening）
- 底物：环丁烯 → 1,3-丁二烯
- SMILES：`C1C=CC1>>C=CC=C`
- 电荷/多重度：0 / 1
- 条件：~150 °C 气相
- gold 机理：顺旋（conrotatory）开环，单一 TS。竞争路径：对旋（对称禁阻，高垒）——轨道对称性排序考点
- gold 能垒锚点：Ea = 32.5 kcal/mol，log A = 13.1 — Cooper & Walters 1958, *JACS*, 80, 4220 **[已核实（经 Houk *Acc. Chem. Res.* 1996, 29, 471 转引）]**；ΔH‡(420 K) = 31.9 kcal/mol **[部分核实]**
- 舒适区：{C,H}；重原子 4
- 经典性：Woodward–Hoffmann 理论的成名预测案例（Dolbier, Koroniak, Houk, Sheu, *Acc. Chem. Res.* 1996）
- 难度：★

### N12. 1,3,5-己三烯电环化（hexatriene electrocyclization）
- 底物：(Z)-1,3,5-己三烯 → 1,3-环己二烯
- SMILES：`C=CC=CC=C>>C1C=CC=CC1`
- 电荷/多重度：0 / 1
- 条件：~150–200 °C 热反应
- gold 机理：对旋（disrotatory）6π 电环化关环。竞争路径：逆开环；1,7-H 迁移副路径——剪枝考点
- gold 能垒锚点：Ea ≈ 29 kcal/mol（实验，见 1,6-电环化综述 *Russ. Chem. Rev.*）**[部分核实]**；DFT/从头算 ΔG‡ ~30 kcal/mol（Houk 组 pericyclic 基准，eScholarship 学位论文图 1）**[部分核实]**
- 舒适区：{C,H}；重原子 6
- 经典性：March 18-27；维生素 D 光化学前体的热基态版本
- 难度：★

### N13. Nazarov 环化（Nazarov cyclization）
- 底物：1,4-戊二烯-3-酮（二乙烯基酮，酸活化）→ 环戊-2-烯酮
- SMILES：`C=CC(=O)C=C>>O=C1C=CCC1`
- 电荷/多重度：0 / 1；关键中间体为质子化羟基戊二烯基**阳离子**（+1）
- 条件：强 Brønsted 酸或 Lewis 酸，室温
- gold 机理：① 羰基质子化 → 3-羟基戊二烯基阳离子；② 4π 顺旋电环化关环 → 环戊烯基阳离子；③ 去质子/互变异构 → 环戊烯酮。竞争：顺旋方向（torquoselectivity，本底物对称无区分）；Wagner–Meerwein 型副反应
- gold 能垒锚点：戊二烯基阳离子电环化垒仅 1–10 kcal/mol（计算）— Kallel & Houk 1989, *JOC*, 54, 6006 **[已核实存在]**；Nazarov 系列理论研究 Smith & Ulmer 1991, *Tetrahedron Lett.*, 32, DOI 10.1016/S0040-4039(00)74868-4 **[已核实存在]**
- 舒适区：{C,H,O}；重原子 6；阳离子中间体（closed-shell）
- 经典性：March 15-22；Denmark *Org. React.* 1994, 45, 1
- 难度：★★

### N14. 乙烯基环丙烷-环戊烯重排（vinylcyclopropane rearrangement）
- 底物：乙烯基环丙烷 → 环戊烯
- SMILES：`C=CC1CC1>>C1=CCCC1`
- 电荷/多重度：0 / 1；**注意**：分步路径经单重态双自由基中间体（多参考特征，对 MACE 属外推风险，本身就是考点）
- 条件：~400–500 °C 热解
- gold 机理：竞争：① 协同 [1,3]-σ 迁移；② 双自由基分步（实验支持后者主导母体体系）。竞争路径正是本题的评分核心
- gold 能垒锚点：实验 Ea ≈ 51.7 kcal/mol **[部分核实]**；双自由基机理理论重估 *JACS* 1998, DOI 10.1021/ja971315q **[已核实存在，作者未核实]**
- 舒适区：{C,H}；重原子 5
- 经典性：March 18-35；热重排教材标准案例
- 难度：★★★（多参考风险，MACE 适用性本身就是考核点）

---

## 二、羰基加成与缩合（极性多步网络主战区）

### N15. Aldol 加成（aldol addition）
- 底物：乙醛自缩合（OH⁻ 催化）→ 3-羟基丁醛
- SMILES：`CC=O.CC=O>>CC(O)CC=O`
- 电荷/多重度：0 / 1；烯醇盐中间体 −1
- 条件：稀 NaOH，水，0–25 °C
- gold 机理：① OH⁻ 拔 α-H 生成烯醇盐；② 烯醇盐进攻另一分子羰基 → 烷氧负离子；③ 质子化。竞争路径：脱水缩合（E1cb）；Cannizzaro（乙醛有 α-H 故不竞争，但 agent 应能排除）；烯醇盐 O-烷基化副通道（气相著名）——剪枝考点
- gold 能垒锚点：烯醇盐-醛加成垒计算（Pratt 等, *JOC* 2005, "Computational Strategies for Evaluating Barrier Heights"）**[已核实存在]**；HZSM-5 上 aldol 全流程 DFT（含气相基线，UMass/Vlachos 组）**[已核实存在]**；决速步认定与数值 **[部分核实]**
- 舒适区：{C,H,O}；重原子 6（产物）
- 经典性：March 16-34；所有教材第一章缩合反应
- 难度：★★

### N16. Aldol 缩合（aldol condensation）
- 底物：丙酮自缩合 → 异亚丙基丙酮（mesityl oxide）+ 水
- SMILES：`CC(=O)C.CC(=O)C>>CC(=O)C=C(C)C.O`
- 电荷/多重度：0 / 1；烯醇盐/烷氧盐中间体 −1
- 条件：NaOH 或 Ba(OH)₂，加热；酸催化也可
- gold 机理：① 烯醇盐生成；② C–C 加成 → 双丙酮醇（diacetone alcohol，可捕获中间体）；③ E1cb 脱水（去质子 → 脱水）。竞争路径：第三步可走 E1（酸催化）或 E2；加成步可逆 vs 脱水步不可逆——网络拓扑考点
- gold 能垒锚点：气相/沸石双丙酮醇路径 DFT 基线（UMass 组 HZSM-5 aldol 研究）**[已核实存在]**；数值锚点 **[部分核实]**
- 舒适区：{C,H,O}；重原子 8（产物）
- 经典性：March 16-34
- 难度：★★★（3 步 + 竞争消除机理）

### N17. Claisen–Schmidt 缩合（Claisen–Schmidt condensation）
- 底物：苯甲醛 + 乙醛（OH⁻）→ 肉桂醛
- SMILES：`O=Cc1ccccc1.CC=O>>O=CC=Cc1ccccc1`
- 电荷/多重度：0 / 1；烯醇盐 −1
- 条件：稀 NaOH 水/乙醇，室温
- gold 机理：① 乙醛烯醇盐；② 进攻苯甲醛；③ E1cb 脱水。竞争路径：苯甲醛无 α-H 可作 Cannizzaro 底物（碱浓时）——两条网络并存，剪枝/排序考点
- gold 能垒锚点：无单独高被引计算锚点 **[未核实]**；可借用 aldol/Cannizzaro 各自锚点（N15/N32）
- 舒适区：{C,H,O}；重原子 10（产物）
- 经典性：March 16-36
- 难度：★★

### N18. Knoevenagel 缩合（Knoevenagel condensation）
- 底物：甲醛 + 丙二酸（哌啶催化）→ 丙烯酸 + CO₂
- SMILES：`C=O.O=C(O)CC(=O)O>>C=CC(=O)O.O=C=O`
- 电荷/多重度：0 / 1；亚铵/烯醇盐离子中间体
- 条件：哌啶/乙酸催化，苯或醇溶剂回流
- gold 机理：① 胺 + 醛 → 亚铵离子；② 丙二酸去质子生成烯醇盐进攻亚铵；③ 脱胺脱水；④ 丙二酸骨架脱羧（六元环 TS）。竞争：Doebner 变体（吡啶中脱羧时机不同）
- gold 能垒锚点：哌啶催化 Knoevenagel 全机理理论（亚铵 vs 烯醇盐角色）*J. Phys. Chem. B* 2017, DOI 10.1021/acs.jpcb.7b03191 **[已核实存在]**；数值 **[未核实]**
- 舒适区：{C,H,O,N}；重原子 ≤7
- 经典性：March 16-38；Knoevenagel 1894
- 难度：★★★（4 步网络 + 脱羧）

### N19. Perkin 缩合（Perkin reaction）
- 底物：苯甲醛 + 乙酸酐（乙酸钠催化）→ 肉桂酸
- SMILES：`O=Cc1ccccc1.CC(=O)OC(C)=O>>O=C(O)C=Cc1ccccc1`
- 电荷/多重度：0 / 1；酸酐烯醇盐 −1
- 条件：AcONa，~180 °C
- gold 机理：① 碱拔酸酐 α-H → 烯醇盐；② 进攻苯甲醛 → 烷氧盐；③ 分子内酰基转移/关环再开环；④ 脱水 + 水解得酸。竞争路径：直接脱水 vs 酰基转移次序——文献有争议，机理假设生成考点
- gold 能垒锚点：**[未核实]**（教材共识机理；无统一 DFT 锚点，入池前需补检索）
- 舒适区：{C,H,O}；重原子 11（产物）
- 经典性：March 16-38；Perkin 1868
- 难度：★★★

### N20. Dieckmann 缩合（Dieckmann condensation）
- 底物：己二酸二甲酯（NaOMe）→ 2-甲氧羰基环戊酮
- SMILES：`COC(=O)CCCCC(=O)OC>>COC(=O)C1CCCC1=O.CO`
- 电荷/多重度：0 / 1；烯醇盐 −1
- 条件：NaOMe/MeOH，回流
- gold 机理：① 拔 α-H → 酯烯醇盐；② 分子内进攻另一端酯羰基 → 四面体中间体；③ 消除 MeO⁻ 关环；④ 产物 β-酮酯去质子驱动平衡。竞争：分子间 Claisen 缩合（二聚/聚合）——网络剪枝考点；五元 vs 七元环化位点选择
- gold 能垒锚点：经典综述 Schaefer & Bloomfield, *Org. React.* 1967, 15, 1 **[部分核实]**；数值 **[未核实]**
- 舒适区：{C,H,O}；重原子 12（底物，上限边缘）
- 经典性：March 16-85
- 难度：★★

### N21. Mannich 反应（Mannich reaction）
- 底物：甲醛 + 甲胺 + 乙醛（酸催化）→ 3-(甲氨基)丙醛
- SMILES：`C=O.CNC.CC=O>>CNCCC=O`
- 电荷/多重度：0 / 1；亚铵中间体 +1（CH₂=NHMe⁺，Eschenmoser 盐母体）
- 条件：弱酸性水/醇溶液
- gold 机理：① 甲醛 + 胺 → 亚铵离子；② 乙醛烯醇（酸催化烯醇化）进攻亚铵；③ 得 Mannich 碱。竞争：烯醇 vs 烯醇盐路径（pH 决定）；双重烷基化副反应
- gold 能垒锚点：脯氨酸催化 Mannich/Aldol 过渡态系列（Bahmanyar, Houk 等, *JACS* 2003/2006）**[未核实，需确认卷页]**；亚铵形成步锚点同 N22
- 舒适区：{C,H,N,O}；重原子 6（产物）
- 经典性：March 16-19；Mannich 1912
- 难度：★★

### N22. 亚胺形成/水解（imine formation / hydrolysis）
- 底物：甲醛 + 甲胺 ⇌ N-甲基甲亚胺 + 水
- SMILES：`C=O.CN>>C=NC.O`
- 电荷/多重度：0 / 1；羟胺（carbinolamine）中性，质子化中间体 +1
- 条件：pH ~4–6 最优（pH 钟形速率曲线是经典物化考题）
- gold 机理：① 胺进攻羰基 → 两性离子 → 羟胺；② 羟胺 O-质子化；③ 脱水生成亚铵 → 去质子得亚胺。竞争：未催化路径（高垒）vs 酸催化；广义碱催化脱水
- gold 能垒锚点：高级别从头算（G2(MP2,SVP)）— Hall & Smith 1998, *J. Phys. Chem. A*, 102, 4930–4938, DOI 10.1021/jp9810825 **[已核实]**（显式水使羟胺生成垒降至 ~14.7 kJ/mol 量级；脱水步决速）
- 舒适区：{C,H,N,O}；重原子 ≤4
- 经典性：March 16-13；Sayer & Jencks 动力学经典
- 难度：★（最合适的入门题之一）

### N23. 烯胺形成（enamine formation / Stork enamine）
- 底物：乙醛 + 二甲胺 → N,N-二甲基乙烯胺 + 水
- SMILES：`CC=O.CN(C)C>>C=CN(C)C.O`
- 电荷/多重度：0 / 1；亚铵 +1
- 条件：酸催化（TsOH），脱水剂或共沸除水
- gold 机理：① 羟胺生成；② 脱水成亚铵；③ α-C 去质子 → 烯胺（与 N22 的分叉在最后一步：N 上无 H 可走 C 去质子）——与亚胺形成的网络分叉考点
- gold 能垒锚点：二甲胺 + 丙醛烯胺形成的 ab initio/DFT 研究（"Computational study of iminium ion formation: effects of amine structure", *JOC* 2006 前后）**[部分核实]**
- 舒适区：{C,H,N,O}；重原子 6
- 经典性：March 16-13；Stork *JACS* 1963 烯胺烷基化
- 难度：★★

### N24. 缩醛形成（acetal formation）
- 底物：甲醛 + 2 甲醇（酸催化）→ 二甲氧基甲烷 + 水
- SMILES：`C=O.CO.CO>>COCOC.O`
- 电荷/多重度：0 / 1；氧鎓/氧碳鎓（oxocarbenium）中间体 +1
- 条件：干 HCl 或 TsOH，甲醇溶剂
- gold 机理：① 羰基质子化；② MeOH 进攻 → 半缩醛；③ 半缩醛 OH 质子化脱水 → 氧碳鎓离子；④ 第二分子 MeOH 进攻 → 去质子。竞争：水解（逆水）与形成平衡——勒夏特列驱动
- gold 能垒锚点：缩醛水解/形成经典物化（Kreevoy & Taft, *JACS* 1955 系列）**[部分核实]**；数值 **[未核实]**
- 舒适区：{C,H,O}；重原子 ≤5
- 经典性：March 16-5
- 难度：★★

### N25. 缩醛水解（acetal hydrolysis）
- 底物：二甲氧基甲烷 + H₃O⁺ → 甲醛 + 2 甲醇
- SMILES：`COCOC.O>>C=O.CO.CO`
- 电荷/多重度：0 / 1；氧碳鎓 +1
- 条件：稀酸水溶液
- gold 机理：A-1 型：① 一个甲氧基质子化；② C–O 断裂（决速）→ 氧碳鎓 + MeOH；③ 水进攻 → 半缩醛；④ 重复得甲醛。竞争：A-2（水先进攻）通常次要——机理判别考点（本反应的教科书判据：专属酸催化、ΔS‡ ≈ 0、溶剂同位素效应）
- gold 能垒锚点：同 N24（Kreevoy–Taft 系列）**[部分核实]**；A-1 机理共识见 March 16-5 **[教材锚点]**
- 舒适区：{C,H,O}；重原子 ≤5
- 经典性：物化有机教科书机理判别标准案例（A-1 vs A-2）
- 难度：★★

### N26. Strecker 合成（Strecker synthesis）
- 底物：甲醛 + 氨 + HCN → 氨基乙腈
- SMILES：`C=O.N.C#N>>NCC#N`
- 电荷/多重度：0 / 1；亚铵 +1 中间体
- 条件：NH₃/NH₄Cl + HCN（或 NaCN），水
- gold 机理：① 亚胺/亚铵形成；② CN⁻ 进攻 → α-氨基腈。竞争路径：HCN 先进攻羰基（氰醇路径）再氨解 vs 先亚胺再氰化——路径次序是百年机理讨论主题，剪枝考点
- gold 能垒锚点：水簇辅助质子转移 DFT — Yamabe 等 2014, *Beilstein J. Org. Chem.*, 10, 184, DOI 10.3762/bjoc.10.184 **[已核实]**（给出各通道垒，含水簇）
- 舒适区：{C,H,N,O}；重原子 ≤4
- 经典性：March 16-15；Strecker 1850；前生物化学名反应
- 难度：★★

### N27. Henry 反应（nitroaldol / Henry reaction）
- 底物：硝基甲烷 + 甲醛（碱催化）→ 2-硝基乙醇
- SMILES：`C[N+](=O)[O-].C=O>>OCC[N+](=O)[O-]`
- 电荷/多重度：0 / 1；硝酸盐（nitronate）−1
- 条件：催化量碱（NaOH/胺），水/醇
- gold 机理：① 拔硝基 α-H → nitronate；② 进攻羰基（C–C 决速）；③ 质子化。竞争：双重/三重加成（甲醛过量时）；Nef 副反应（酸性条件）
- gold 能垒锚点：**[未核实]**（教材共识；入池前补检索 nitronate 加成垒）
- 舒适区：{C,H,N,O}；重原子 4；NO₂ 基团的 ML 势描述需注意（N 氧化态高）
- 经典性：March 16-35；Henry 1895
- 难度：★

### N28. Michael 加成（Michael addition）
- 底物：丙二酸二甲酯 + 丙烯醛（催化碱）→ 3-氧代丙基丙二酸酯
- SMILES：`COC(=O)CC(=O)OC.C=CC=O>>COC(=O)C(CCC=O)C(=O)OC`
- 电荷/多重度：0 / 1；烯醇盐 −1
- 条件：催化 NaOMe/MeOH 或胺
- gold 机理：① 丙二酸酯去质子；② 1,4-共轭加成 → 烯醇盐；③ 质子化。竞争：1,2-加成（动力学可逆，热力学返回到 1,4）——1,2 vs 1,4 排序是核心考点
- gold 能垒锚点：亚铵催化 Michael 全流程 DFT（含溶剂效应，*J. Phys. Chem. A* 2018, DOI 10.1021/acs.jpca.7b11803）**[已核实存在]**；aza-Michael 的 MEDT 研究（Domingo, *New J. Chem.* 2020, 44, 19002）**[已核实存在]**；本体系精确垒 **[未核实]**
- 舒适区：{C,H,O}；重原子 11（产物，上限边缘；可改用硝基甲烷/丙烯醛缩小）
- 经典性：March 15-18；Michael 1887
- 难度：★★

### N29. Nef 反应（Nef reaction）
- 底物：乙醛硝酸盐（acetonitronate，由硝基乙烷去质子）+ H₃O⁺ → 乙醛 + N₂O
- SMILES：`CC=[N+]([O-])O.[H3O+]>>CC=O.[N-]=[N+]=O`
- 电荷/多重度：净 −1+1 / 1；nitronate −1
- 条件：强酸（稀 H₂SO₄），水
- gold 机理：① nitronate 双质子化 → nitronic acid 阳离子；② 水进攻；③ 碎片化解离出羰基 + N₂O（经 hyponitrite）。竞争：副产物路径（羟胺/腈氧化物）
- gold 能垒锚点：**[未核实]**（Nef 1894；机理共识见 March 16-17 邻近条目；入池前补检索）
- 舒适区：{C,H,N,O}；重原子 5
- 经典性：March 19-66（脱硝基转化）
- 难度：★★★

---

## 三、极性反转、歧化与多组分反应

### N30. Wittig 反应（简化叶立德）（Wittig reaction）
- 底物：亚甲基磷烷（H₃P=CH₂，最小模型叶立德）+ 甲醛 → 乙烯 + H₃P=O
- SMILES：`[CH2-][PH3+].C=O>>C=C.O=[PH3]`
- 电荷/多重度：0 / 1（叶立德两性离子表示；含 **P [低密度风险]**）
- 条件：无盐条件（salt-free）最接近模型化学；THF/Et₂O
- gold 机理：① 叶立德对羰基亲核加成（[2+2] 异步协同）→ 氧磷杂环丁烷（oxaphosphetane）；② 环消除（cycloreversion）→ 烯烃 + 氧化磷。竞争路径：betaine 中间体路径（现代共识：多数体系直接经 oxaphosphetane，betaine 被绕过）——机理共识演变的经典案例；顺/反 oxaphosphetane 非对映选择性
- gold 能垒锚点：Robiette, Richardson, Aggarwal, Harvey 2006, *JACS*, 128, 2394–2409 **[已核实]**；现代机理综述 Byrne & Gilheany 2013, *Chem. Soc. Rev.*, 42, 6670 **[已核实]**
- 舒适区：{C,H,O,**P**}；重原子 3（底物叶立德）；**P 为 MACE-OMol25 训练低密度元素，必标 [低密度风险]——作为分档压力测试保留**
- 经典性： Nobel 1979；March 16-44
- 难度：★★

### N31. Morita–Baylis–Hillman 反应（MBH reaction）
- 底物：甲醛 + 丙烯酸甲酯 + 三甲胺（催化剂）→ 2-(羟甲基)丙烯酸甲酯
- SMILES：`C=O.C=CC(=O)OC.CN(C)C>>C=C(CO)C(=O)OC`
- 电荷/多重度：0 / 1；两性离子烯醇盐中间体（铵⁺/烯醇盐⁻）
- 条件：叔胺催化，室温
- gold 机理：① 胺对丙烯酸酯 Michael 加成 → 两性离子烯醇盐；② 对醛 aldol 加成；③ 质子转移（决速，醇助催化、对醛二级）；④ β-消除释放催化剂。竞争：双醛半缩醛中间体路径（Aggarwal 修正机理）
- gold 能垒锚点：Robiette, Aggarwal, Harvey 2007, *JACS*, 129, 15513–15525, DOI 10.1021/ja0717865 **[已核实]**（质子转移决速）；实验修正机理 Aggarwal, Fulford, Lloyd-Jones 2005, *Angew. Chem. Int. Ed.*, 44, 1706 **[已核实]**
- 舒适区：{C,H,N,O}；重原子 7（产物）
- 经典性：有机催化机理研究范式案例
- 难度：★★★

### N32. Cannizzaro 反应（Cannizzaro reaction）
- 底物：2 甲醛 + OH⁻ → 甲醇 + 甲酸根
- SMILES：`C=O.C=O.[OH-]>>CO.O=C[O-]`
- 电荷/多重度：净 −1 / 1；氢负离子转移 TS
- 条件：浓 NaOH，水
- gold 机理：① OH⁻ 加成醛 → 四面体烷氧盐；② 再去质子 → 双负离子；③ 分子间氢负离子转移到第二分子醛（决速，一级同位素效应证据）；④ 质子转移。竞争：单阴离子直接转移路径（Swain 用 kH₂O/kD₂O 排除了另外两条质子转移耦合路径）
- gold 能垒锚点：Swain, Powell, Sheppard, Morgan 1979, *JACS*, 101, 3576 **[已核实]**（机理与同位素效应；为排序锚点而非精确垒）
- 舒适区：{C,H,O}；重原子 ≤3
- 经典性：March 19-81；歧化反应原型
- 难度：★★

### N33. 二苯乙醇酸重排（最小化版本：乙二醛）（benzilic acid rearrangement）
- 底物：乙二醛 + OH⁻ → 乙醇酸根
- SMILES：`O=CC=O.[OH-]>>O=C([O-])CO`
- 电荷/多重度：净 −1 / 1
- 条件：浓碱水溶液
- gold 机理：① OH⁻ 加成一个羰基 → 四面体加合物；② 1,2-迁移（本底物为 H/甲酰基迁移等价）伴 C=O 重建（决速）；③ 质子转移 → α-羟基羧酸盐。竞争：与分子内 Cannizzaro 的关系判别（同位素实验证明是迁移而非氢负离子转移）
- gold 能垒锚点：机理综述（"Mechanistic and Synthetic Aspects of the Benzilic Acid and Ester Rearrangements"）**[已核实存在]**；数值 **[未核实]**
- 舒适区：{C,H,O}；重原子 4
- 经典性：March 18-6
- 难度：★★

### N34. 苯偶姻缩合（最小化：甲醛 + CN⁻）（benzoin condensation）
- 底物：2 甲醛 + CN⁻（催化）→ 乙醇醛（glycolaldehyde）
- SMILES：`C=O.C=O.[C-]#N>>OCC=O`
- 电荷/多重度：净 −1（催化剂）/ 1
- 条件：NaCN，水/醇，温和加热
- gold 机理（Lapworth）：① CN⁻ 加成醛 → 氰醇盐；② 质子转移 → "掩蔽酰基负离子"（umpolung）；③ 进攻第二分子醛；④ 脱 CN⁻ → α-羟基羰基。竞争：氰醇简单形成（副平衡）；极性反转概念验证考点
- gold 能垒锚点：氰化物催化苯偶姻缩合 DFT（四路径对比，基于 Lapworth 机理）— He & Xue 2010 **[已核实存在，期刊卷页待确认]**；Lapworth 1903 原始机理 **[教材锚点]**
- 舒适区：{C,H,O,N}；重原子 ≤4
- 经典性：umpolung 概念的诞生反应；Breslow 噻唑鎓机理的前身
- 难度：★★

### N35. Passerini 反应（Passerini three-component reaction）
- 底物：甲醛 + 甲酸 + 甲基异腈 → N-甲基-2-(甲酰氧基)乙酰胺
- SMILES：`C=O.O=CO.C[N+]#[C-]>>CNC(=O)COC=O`
- 电荷/多重度：0 / 1；异腈为两性离子共振式；nitrilium 中间体 +1
- 条件：非极性溶剂，室温，高浓度
- gold 机理：① 醛 + 羧酸氢键簇集；② 异腈 α-加成 → 腈鎓（nitrilium）；③ 羧酸根捕获 → 亚氨酸酯；④ Mumm 重排（酰基迁移）→ α-酰氧基酰胺。竞争：溶剂/第四组分参与（Maeda 证明"三组分反应实为四组分"）——网络复杂度考点
- gold 能垒锚点：Maeda, Komagawa, Uchiyama, Morokuma 2011, *Angew. Chem. Int. Ed.*, 50, 644, DOI 10.1002/anie.201005336 **[已核实]**；Ramozzi & Morokuma 2015, *JOC*, 80, 5652, DOI 10.1021/acs.joc.5b00594 **[已核实]**
- 舒适区：{C,H,N,O}；重原子 9（产物）
- 经典性：Passerini 1921；多组分反应原型
- 难度：★★★

### N36. Staudinger β-内酰胺合成（Staudinger ketene–imine cycloaddition）
- 底物：乙烯酮 + 甲亚胺 → β-内酰胺（azetidin-2-one）
- SMILES：`C=C=O.C=N>>O=C1CCN1`
- 电荷/多重度：0 / 1；两性离子中间体（烯醇盐⁺/亚胺鎓体系）
- 条件：乙烯酮现场生成；惰性溶剂
- gold 机理：① 亚胺 N 进攻乙烯酮中心碳 → 两性离子；② 顺旋 4π 关环（决定顺/反立体化学）→ β-内酰胺。竞争：协同 [2+2]（轨道禁阻但极性体系可异步协同）vs 分步——百年未决机理问题（Cossío 语），2007 年仍有新研究
- gold 能垒锚点：Cossío, Arrieta, Sierra 2008, *Acc. Chem. Res.*, 41, 925–936, DOI 10.1021/ar800033j **[已核实]**；Domingo 等 2015, *RSC Adv.*, 5, 37119 **[已核实]**
- 舒适区：{C,H,N,O}；重原子 5
- 经典性：Staudinger 1907；β-内酰胺抗生素化学基石
- 难度：★★

---

## 四、羧酸衍生物酰基转移（AAC2 / BAC2 判别）

### N37. Fischer 酯化（Fischer esterification）
- 底物：乙酸 + 甲醇（酸催化）→ 乙酸甲酯 + 水
- SMILES：`CC(=O)O.CO>>CC(=O)OC.O`
- 电荷/多重度：0 / 1；质子化中间体 +1
- 条件：H₂SO₄ 或 HCl 催化，甲醇过量/除水
- gold 机理：AAC2 正向：① 羰基质子化；② MeOH 加成 → 四面体中间体；③ 质子转移；④ 脱水。竞争：酰氧断裂 vs 烷氧断裂（AAL1 仅在特殊底物）——同位素标记判别是教科书案例
- gold 能垒锚点：机理共识见 March 16-61 **[教材锚点]**；数值 **[未核实]**（可用 N38/N39 的计算锚点做交叉标定）
- 舒适区：{C,H,O}；重原子 ≤5
- 经典性：Fischer 1895
- 难度：★★

### N38. 酯酸催化水解 AAC2（acid-catalyzed ester hydrolysis）
- 底物：甲酸甲酯 + H₃O⁺ → 甲酸 + 甲醇
- SMILES：`COC=O.O>>O=CO.CO`（酸催化注明）
- 电荷/多重度：0 / 1；质子化酯 +1
- 条件：稀酸水溶液，加热
- gold 机理：AAC2：① 羰基质子化；② 水加成（决速附近）；③ 质子转移；④ 消除 MeOH。竞争：AAL1（本底物不成立）；BAC2 在碱性下的对偶——同一底物酸碱两面的机理判别考点
- gold 能垒锚点：烷基酯水解反应场计算系列（SVPE；BAC2 中甲酸甲酯垒最低）**[已核实存在]**；AAC2 数值 **[未核实]**
- 舒适区：{C,H,O}；重原子 ≤4
- 经典性：Ingold 酯水解八机理分类的母体案例
- 难度：★★

### N39. 酯碱水解 / 皂化 BAC2（ester saponification）
- 底物：甲酸甲酯 + OH⁻ → 甲酸根 + 甲醇
- SMILES：`COC=O.[OH-]>>O=C[O-].CO`
- 电荷/多重度：−1 / 1；四面体中间体 −1
- 条件：NaOH 水溶液
- gold 机理：BAC2：① OH⁻ 加成 → 四面体中间体；② 消除 MeO⁻（气相计算显示消除步垒更高；溶液中加成决速）。竞争：气相中还有脱质子/水解分叉（Pranata 的离子-偶极复合物研究）；酰氧 vs 烷氧断裂判别（¹⁸O 标记经典实验）
- gold 能垒锚点：Zhan, Landry, Ornstein 2000, *JACS*, DOI 10.1021/ja993311m **[已核实]**；Pranata 气相甲酸甲酯 + OH⁻ IRC 研究 **[已核实存在]**
- 舒适区：{C,H,O}；重原子 ≤4
- 经典性：March 16-59
- 难度：★★

### N40. 酰胺水解（amide hydrolysis）
- 底物：甲酰胺 + H₃O⁺（或 OH⁻ 对照）→ 甲酸 + 铵根
- SMILES：`NC=O.O>>O=CO.N`（酸性注明）
- 电荷/多重度：0 / 1；四面体中间体
- 条件：酸或碱催化，加热（酰胺极惰性——高垒本身是考点）
- gold 机理：酸催化：① O-质子化（计算支持 O-质子化分步路径优于 N-质子化）；② 水加成；③ C–N 断裂（决速区）。碱催化：加成-消除。竞争：N- vs O-质子化位点判别——酰胺化学著名争议
- gold 能垒锚点：碱催化气相/水溶液 — Bakowies & Kollman 1999, *JACS*, DOI 10.1021/ja9837349 **[已核实]**；酸催化 cluster-continuum — Wang & Cao **[已核实存在]**；N/O 质子化对比 — Antonczak, Ruiz-López, Rivail（MP2 IRC）**[已核实存在]**
- 舒适区：{C,H,N,O}；重原子 ≤3
- 经典性：肽键水解模型，生物物理化学基准
- 难度：★★

---

## 五、氧化与环氧化学

### N41. 环氧开环（碱催化）（epoxide ring opening, base）
- 底物：环氧乙烷 + OH⁻ → 乙二醇盐
- SMILES：`C1CO1.[OH-]>>OCC[O-]`
- 电荷/多重度：−1 / 1
- 条件：NaOH 水溶液
- gold 机理：SN2 背面进攻（单一决速步）。竞争：与中性水解（单分子水，高垒）和酸催化 A-2 的能垒排序——三条件对比考点
- gold 能垒锚点：环氧乙烷水解机理研究 *J. Phys. Chem. A* 2008, DOI 10.1021/jp073285b **[已核实]**（单水机制高垒；广义酸催化可降至 ~10 kcal/mol 量级）；绝对垒数值 **[部分核实]**
- 舒适区：{C,H,O}；重原子 ≤4
- 经典性：March 10-7
- 难度：★

### N42. 环氧开环（酸催化）（epoxide ring opening, acid）
- 底物：环氧乙烷 + H₃O⁺ → 乙二醇
- SMILES：`C1CO1.[H3O+]>>OCCO`
- 电荷/多重度：0（净）/ 1；质子化环氧 +1
- 条件：稀酸水溶液
- gold 机理：A-2：① 环氧 O 质子化；② 水进攻伴 C–O 断裂（borderline SN2，部分 SN1 特征）。竞争：SN1-like（叔碳/苄位底物时翻转）——用丙烯氧化物（`CC1CO1`）可做区域选择性扩展题
- gold 能垒锚点：丙烯氧化物酸催化水解 SN1/SN2 对比 — Muniz Filho 等 2010 **[已核实存在]**；同 N41 锚点
- 舒适区：{C,H,O}；重原子 ≤4
- 经典性：March 10-7
- 难度：★★

### N43. Meinwald 重排（Meinwald rearrangement）
- 底物：丙烯氧化物 + H⁺（Lewis/Brønsted 酸）→ 丙醛（或丙酮）
- SMILES：`CC1CO1.[H3O+]>>CCC=O`（竞争产物 `CC(=O)C`）
- 电荷/多重度：净 +1（催化）/ 1
- 条件：酸催化
- gold 机理：① 环氧质子化；② C–O 断裂 + 1,2-迁移（H 迁移 → 醛；甲基迁移 → 酮）协同发生。竞争：H vs Me 迁移性排序 = 区域选择性核心考点；与半频哪醇重排的边界
- gold 能垒锚点：**[未核实]**（教材共识；可借用 N42/N47 锚点做交叉标定）
- 舒适区：{C,H,O}；重原子 4
- 经典性：March 18-4
- 难度：★★

### N44. Prilezhaev 环氧化（Prilezhaev epoxidation）
- 底物：乙烯 + 过甲酸 → 环氧乙烷 + 甲酸
- SMILES：`C=C.O=COO>>C1CO1.O=CO`
- 电荷/多重度：0 / 1
- 条件：过酸现场生成；惰性溶剂，0–25 °C
- gold 机理：协同"蝴蝶型"TS（O 转移 + 质子迁移一体）。竞争：不对称 vs 对称 TS（早期计算争议）；双自由基路径（给电子取代基时才露头）
- gold 能垒锚点：Bach 等 1997（B3LYP vs 高级别对比，过甲酸 + 乙烯/丙烯 TS）**[已核实存在，载体 *JACS/JOC* 待确认]**；Houk 等 1997, *JACS*, 119, 12982, DOI 10.1021/ja963847x **[已核实]**
- 舒适区：{C,H,O}；重原子 ≤5；过氧键 O–O 对 ML 势需注意但属训练分布内（反应轨迹数据含过氧化物）
- 经典性：Prilezhaev 1909；Sharpless 前的通用环氧化
- 难度：★

### N45. 二甲基双环氧乙烷环氧化（DMDO epoxidation）
- 底物：二甲基双环氧乙烷（DMDO）+ 乙烯 → 环氧乙烷 + 丙酮
- SMILES：`CC1(C)OO1.C=C>>CC(C)=O.C1CO1`
- 电荷/多重度：0 / 1
- 条件：DMDO 丙酮溶液，低温
- gold 机理：协同氧转移，**螺环（spiro）TS**（vs planar TS 的选择是著名计算故事）。竞争：spiro vs planar 排序 = 核心考点
- gold 能垒锚点：Houk 等 1997, *JACS*, 119, 12982, DOI 10.1021/ja963847x **[已核实]**；Miaskiewicz & Smith 1998, *JACS*, 120, 1872, DOI 10.1021/ja972800o **[已核实]**；Bach 等 1997（spiro 对称 TS）**[已核实存在]**（计算垒对方法敏感，~10–26 kcal/mol 区间，容差考核合适）
- 舒适区：{C,H,O}；重原子 ≤5
- 经典性：Murray/Adam 双环氧乙烷化学；Shi 环氧化的母体模型
- 难度：★★

### N46. 臭氧解（ozonolysis）
- 底物：乙烯 + O₃ → 甲醛 + 羰基氧化物（CH₂OO，Criegee 中间体）
- SMILES：`C=C.[O-][O+]=O>>C=O.C=[O+][O-]`
- 电荷/多重度：0 / 1；臭氧与羰基氧化物为两性离子共振；**注意单重态双自由基特征（多参考风险）**
- 条件：低温，CH₂Cl₂/甲醇
- gold 机理（Criegee）：① O₃ 的 1,3-偶极环加成 → 初级臭氧化物（POZ，1,2,3-三氧戊环，可捕获）；② POZ 环反转裂解 → 羰基 + 羰基氧化物；③ 两者重组 → 次级臭氧化物（SOZ）或被捕集。竞争：POZ 分步裂解 vs 协同；Criegee 中间体单分子解离通道（OH 生成）——大气化学网络剪枝原型
- gold 能垒锚点：乙烯臭氧解高级别量子化学+动力学 *J. Phys. Chem. A* 2015, DOI 10.1021/acs.jpca.5b02088 **[已核实]**；Criegee 机理综述与 POZ 研究（Cremer/Anglada 系列）**[已核实存在]**
- 舒适区：{C,H,O}；重原子 ≤5
- 经典性：Criegee 机理（1975 Nobel 相关工作）；大气化学核心反应
- 难度：★★★（3 步网络 + 多参考特征）

### N47. Baeyer–Villiger 氧化（Baeyer–Villiger oxidation）
- 底物：丙酮 + 过甲酸 → 乙酸甲酯 + 甲酸
- SMILES：`CC(C)=O.O=COO>>CC(=O)OC.O=CO`
- 电荷/多重度：0 / 1；Criegee 加成物中性
- 条件：过酸，惰性溶剂；酸催化加速
- gold 机理：① 过酸对羰基加成 → Criegee 四面体中间体；② 1,2-烷基迁移伴 O–O 断裂（迁移步，保留构型）；③ 得酯。竞争：加成步 vs 迁移步谁是决速（底物依赖！丙酮 + 过甲酸计算显示加成步决速）——决速步认定是核心考点；甲基迁移性排序（对比取代底物）
- gold 能垒锚点：Alvarez-Idaboy, Reyes, Mora-Diez 2007, *Org. Biomol. Chem.*（丙酮/3-戊酮 + 过甲酸，加成步决速）**[已核实存在，DOI 待确认]**；Bach（过乙酸系列，B3LYP/6-311+G(d,p)）**[已核实存在]**；¹⁸O 标记经典 Doering & Dorfman 1953 **[教材锚点]**
- 舒适区：{C,H,O}；重原子 ≤6
- 经典性：March 18-19；Baeyer & Villiger 1899
- 难度：★★

---

## 六、缺电子 1,2-重排（N/O 缺电子体）

### N48. 频哪醇重排（pinacol rearrangement）
- 底物：频哪醇（2,3-二甲基-2,3-丁二醇）+ H⁺ → 频哪酮
- SMILES：`CC(C)(O)C(C)(C)O>>CC(=O)C(C)(C)C`
- 电荷/多重度：0 / 1；质子化二醇/碳正离子 +1
- 条件：浓 H₂SO₄，加热
- gold 机理：① 一个 OH 质子化；② 脱水 + 1,2-甲基迁移协同（半频哪醇式，避免自由碳正离子）；③ 去质子得酮。竞争：分步碳正离子路径 vs 协同迁移（DFT 显示协同显著占优）；不对称底物时的迁移性排序（最小不对称变体：质子化乙二醇 → 乙醛，H 迁移）
- gold 能垒锚点：乙二醇 → 乙醛 DFT（协同迁移显著低于分步脱水-烯醇路径）**[已核实存在]**；取代质子化乙二醇 ab initio SCF 系列 **[已核实存在]**；数值 **[部分核实]**
- 舒适区：{C,H,O}；重原子 8（频哪醇；乙二醇变体仅 4）
- 经典性：March 18-2；1860 年发现的第一个碳骨架重排
- 难度：★★

### N49. Beckmann 重排（Beckmann rearrangement）
- 底物：丙酮肟 + H⁺ → N-甲基乙酰胺
- SMILES：`CC(C)=NO>>CNC(C)=O`（酸催化注明）
- 电荷/多重度：0 / 1；质子化肟 +1
- 条件：浓 H₂SO₄ 或 PCl₅；工业上发烟硫酸（己内酰胺工艺）
- gold 机理：① 肟 OH 质子化；② 脱水 + 反式基团 1,2-迁移协同 → nitrilium/碳正离子；③ 水加成 → 亚胺酸；④ 互变异构 → 酰胺。竞争：迁移基团立体专属性（anti 迁移）——用丙酮肟无区分，可扩展甲乙酮肟；碎裂副反应（腈 + 碳正离子）
- gold 能垒锚点：硫酸角色 DFT — Lin 等 2016, *Chem. Phys. Lett.*（新机制使垒降 48.1 kJ/mol）**[已核实存在]**；丙酮肟在分子筛上的 DFT（垒随 Brønsted 酸强度变化）*Catal. Sci. Technol.* 2015, DOI 10.1039/c5cy00619h **[已核实]**
- 舒适区：{C,H,N,O}；重原子 5
- 经典性：March 18-17；Beckmann 1886
- 难度：★★

### N50. Schmidt 反应（Schmidt reaction）
- 底物：乙酸 + 叠氮酸 + H⁺ → 甲胺 + CO₂ + N₂
- SMILES：`CC(=O)O.N=[N+]=[N-]>>CN.O=C=O.N#N`
- 电荷/多重度：0 / 1；酰基阳离子/质子化叠氮加成物 +1
- 条件：浓 H₂SO₄
- gold 机理：① 羧酸质子化活化；② HN₃ 加成 → 叠氮加成物；③ 脱水 → 酰基叠氮阳离子；④ 1,2-迁移 + N₂ 挤出 → nitrilium → 水解 → 胺 + CO₂。竞争：与 Curtius（先分离酰基叠氮）的机理连续谱；酮版 Schmidt（加成-迁移次序不同）
- gold 能垒锚点：Aubé 组 Schmidt/改良 Schmidt 机理研究（含计算）**[部分核实]**；数值 **[未核实]**
- 舒适区：{C,H,N,O}；重原子 ≤6；叠氮 N₃ 单元注意 ML 势描述
- 经典性：March 18-16
- 难度：★★★

### N51. Curtius 重排（Curtius rearrangement）
- 底物：乙酰叠氮 → 甲基异氰酸酯 + N₂
- SMILES：`CC(=O)N=[N+]=[N-]>>CN=C=O.N#N`
- 电荷/多重度：0 / 1；**若分步则经单重态酰基氮宾（nitrene，多参考风险）**
- gold 机理：热条件下协同 1,2-迁移 + N₂ 挤出（主流）；竞争：分步酰基氮宾路径（实验：测压法与光谱法给出相同速率 → N₂ 挤出决速）——协同 vs 分步判别考点；syn/anti 构象效应
- 条件：加热 ~80 °C，惰性溶剂
- gold 能垒锚点：丙二酰叠氮 Curtius 理论评估 — Kishi 2024 **[已核实存在]**；草酰二叠氮 DFT（*J. Mol. Graph. Model.* 2021）**[已核实存在]**；苯甲酰叠氮 Lewis 酸加速研究 **[已核实存在]**
- 舒适区：{C,H,N,O}；重原子 6
- 经典性：March 18-14
- 难度：★★

### N52. Hofmann 重排（Hofmann rearrangement）
- 底物：乙酰胺 + BrO⁻（Br₂/NaOH）→ 甲基异氰酸酯 →（水解）甲胺
- SMILES：`CC(=O)N.[BrO-]>>CN=C=O`（含 **Br [低密度风险]**）
- 电荷/多重度：净 −1 / 1；N-溴代酰胺 −1 中间体
- 条件：Br₂/NaOH 水溶液，0 °C → 温热
- gold 机理：① N-溴代；② 去质子 → N-溴酰胺负离子；③ 1,2-迁移 + Br⁻ 离去（决速）→ 异氰酸酯；④ 水解 → 胺 + CO₂。竞争：自由基路径（Hofmann–Löffler 不相关，勿混）；与 Curtius/Lossen/Schmidt 的同构性比较是教学考点
- gold 能垒锚点：**[未核实]**（教材共识；入池前补检索）
- 舒适区：{C,H,N,O,**Br**}；重原子 ≤6；**Br 低密度风险**
- 经典性：March 18-13
- 难度：★★

### N53. Wolff 重排（Wolff rearrangement）
- 底物：2-重氮基乙醛 → 乙烯酮 + N₂
- SMILES：`O=CC=[N+]=[N-]>>C=C=O.N#N`
- 电荷/多重度：0 / 1；**若分步则经单重态氧代卡宾（ketocarbene，多参考风险）**
- 条件：热或光解（本基准取热基态）
- gold 机理：① N₂ 挤出 + 1,2-H/甲酰基迁移（协同，小环/脂肪族底物多为协同）→ 乙烯酮；②（含水时）水解得乙酸。竞争：分步酮卡宾路径 vs 协同；oxirene 中间体假说（Arndt–Eistert 同位素打乱实验史）——剪枝考点
- gold 能垒锚点：重氮羰基化合物 Wolff 机理理论研究 — Arora 等 2016, *Comput. Theor. Chem.* **[已核实存在]**；非环双氮羰基的协同 Wolff **[已核实存在]**
- 舒适区：{C,H,N,O}；重原子 4
- 经典性：March 18-8；Arndt–Eistert 同系化的关键步
- 难度：★★

### N54. Wolff–Kishner 还原（Wolff–Kishner reduction）
- 底物：甲醛腙 + OH⁻ → 甲烷 + N₂
- SMILES：`C=NN.[OH-]>>C.N#N`
- 电荷/多重度：净 −1 / 1；腙负离子/碳负离子中间体 −1
- 条件：KOH，二甘醇，~200 °C（Huang-Minlon 变体）
- gold 机理：① 碱拔末端 N–H → 腙负离子；② 质子转移到碳 → 偶氮/碳负离子（diimide-like）；③ 再拔 N–H → 碳负离子；④ N₂ 挤出 → 碳负离子；⑤ 质子化 → 烷烃。竞争：Szmant 机理的各步次序；半卡巴腙变体——多步离子网络考点
- gold 能垒锚点：Wolff–Kishner 底物依赖反应通道 DFT（首例计算研究）*Beilstein J. Org. Chem.* 2014 **[已核实存在]**；Szmant 实验机理系列 **[教材锚点]**
- 舒适区：{C,H,N,O}；重原子 ≤3
- 经典性：March 19-63
- 难度：★★★

### N55. Favorskii 重排（Favorskii rearrangement）
- 底物：氯丙酮 + OH⁻ → 丙酸根（经环丙酮）
- SMILES：`CC(=O)CCl.[OH-]>>CCC(=O)[O-]`（含 **Cl [低密度风险]**）
- 电荷/多重度：净 −1 / 1；烯醇盐 −1；环丙酮中性中间体
- 条件：NaOH 水溶液
- gold 机理：① 拔 α'-H → 烯醇盐；② 分子内 SN2 关环脱 Cl⁻ → **环丙酮中间体**（对称化！¹⁴C 标记实验证明两端等价）；③ OH⁻ 加成；④ 开环 → 羧酸盐。竞争：直接 SN2 取代（伪 Favorskii）；半苯偶酸型机理——环丙酮中间体捕获是核心考点
- gold 能垒锚点：环丙酮中间体立体控制开裂证据 — Rappe, Knutsson, Turro, Gagosian 1970, *JACS*, 92, 2032 **[已核实存在]**；Loftfield ¹⁴C 标记 1951 **[未核实]**；数值 **[未核实]**
- 舒适区：{C,H,O,**Cl**}；重原子 5；**Cl 低密度风险**
- 经典性：March 18-7
- 难度：★★★

---

## 七、杂环构建与其他经典反应

### N56. Fischer 吲哚合成（核心步）（Fischer indole synthesis）
- 底物：苯肼 + 乙醛 → 吲哚（酸催化）
- SMILES：`NNc1ccccc1.CC=O>>c1ccc2[nH]ccc2c1.N.O`
- 电荷/多重度：0 / 1；质子化腙/亚铵阳离子
- 条件：AcOH/HCl 或 ZnCl₂，加热
- gold 机理（核心 4 步）：① 腙形成；② 腙-烯肼互变异构；③ **[3,3]-σ 迁移**（决速，去芳构化中间体）；④ 环化-芳构化-脱 NH₃。竞争：腙 E/Z 几何决定哪个烯肼可重排；1,2-迁移假说（已证否）——中间体捕获密集考点
- gold 能垒锚点：机理共识见 Robinson《The Fischer Indole Synthesis》(Wiley, 1982) **[教材锚点]**；List 不对称 Fischer 吲哚（CPA 催化 [3,3] 机理，2011）**[已核实存在]**；DFT 垒数值 **[未核实]**
- 舒适区：{C,H,N}；重原子 9（吲哚）
- 经典性：March 18-30 邻近；Fischer 1883；吲哚合成第一名反应
- 难度：★★★

### N57. Knorr 吡唑合成（Knorr pyrazole synthesis）
- 底物：2,4-戊二酮 + 肼 → 3,5-二甲基吡唑
- SMILES：`CC(=O)CC(C)=O.NN>>Cc1cc(C)n[nH]1`
- 电荷/多重度：0 / 1
- 条件：乙醇，加热，弱酸催化
- gold 机理：① 一个羰基成腙；② 分子内进攻第二羰基 → 环化羟胺中间体；③ 两次脱水芳构化。竞争：单腙 vs 双腙副产物；区域选择性（不对称二酮时）
- gold 能垒锚点：**[未核实]**（Knorr 1883；机理共识）
- 舒适区：{C,H,N,O}；重原子 7
- 经典性：吡唑合成标准方法
- 难度：★★

### N58. Paal–Knorr 吡咯合成（Paal–Knorr pyrrole synthesis）
- 底物：2,5-己二酮 + 氨 → 2,5-二甲基吡咯
- SMILES：`CC(=O)CCC(C)=O.N>>Cc1ccc(C)[nH]1`
- 电荷/多重度：0 / 1；半胺醛/亚铵中间体
- 条件：AcOH，加热
- gold 机理：① 氨加成 → 半胺醛；② 脱水 → 亚胺/烯胺互变；③ 分子内进攻第二羰基关环；④ 脱水芳构化。竞争：环化时机（先脱水再环化 vs 反之）——实验动力学表明半胺醛环化决速
- gold 能垒锚点：Paal–Knorr 动力学机理（Amarnath 等, *JOC* 1995 前后）**[未核实]**；数值 **[未核实]**
- 舒适区：{C,H,N,O}；重原子 8
- 经典性：March 16-54 邻近；Paal & Knorr 1884/85
- 难度：★★★

### N59. Prins 反应（Prins reaction）
- 底物：甲醛 + 丙烯 + H₃O⁺ → 丁-3-烯-1-醇
- SMILES：`C=O.C=CC.[H3O+]>>C=CCCO`
- 电荷/多重度：0 / 1；碳正离子中间体 +1
- 条件：稀酸水溶液，加热
- gold 机理：① 羰基质子化；② 烯烃进攻 → β-羟基碳正离子；③ 水捕获 → 1,3-二醇（再脱水得烯丙醇）或直接脱质子 → 烯丙醇。竞争：2:1 加合生成 1,3-二氧六环；carbonyl-ene 路径——多产物网络剪枝考点
- gold 能垒锚点：经典 Prins 反应首个计算研究（新中间体）— *Beilstein J. Org. Chem.* 2013, 9, 51 **[已核实]**（Yamabe 等，纯水/酸催化 CHO 体系）
- 舒适区：{C,H,O}；重原子 5（产物）
- 经典性：March 16-54；Prins 1919
- 难度：★★

### N60. Menshutkin 反应（Menshutkin reaction）
- 底物：氨 + 氯甲烷 → 甲铵氯化物
- SMILES：`N.CCl>>C[NH3+].[Cl-]`（含 **Cl [低密度风险]**）
- 电荷/多重度：0 → 离子对 / 1
- 条件：极性溶剂（溶剂效应巨大：气相→水的垒差是溶剂化理论基准）
- gold 机理：SN2 甲基转移（中性反应物 → 离子产物）。竞争：气相高垒 vs 溶液低垒的溶剂化排序；与离子型 SN2（OH⁻ + CH₃Cl）的 Born 溶剂化对比
- gold 能垒锚点：Castejon & Wiberg 1999, *JACS*, 121, DOI 10.1021/ja983736t（CASSCF + PCM）**[已核实]**；Abboud/Solà 系列溶剂效应研究 **[已核实存在]**；Turan 等溶剂效应综述 2021 **[已核实存在]**
- 舒适区：{C,H,N,**Cl**}；重原子 2；**Cl 低密度风险**
- 经典性：溶剂化模型的标准测试反应（几乎所有显式/隐式溶剂方法论文都用它）
- 难度：★

### N61. Kolbe–Schmitt 反应（Kolbe–Schmitt reaction）
- 底物：苯酚钠 + CO₂ → 水杨酸钠
- SMILES：`[O-]c1ccccc1.O=C=O>>O=C([O-])c1ccccc1O`
- 电荷/多重度：−1 / 1
- 条件：~125 °C，CO₂ 加压
- gold 机理：① 酚盐-CO₂ 预复合物（阳离子配位模板，K⁺/Na⁺ 效应显著）；② 邻位亲电进攻（经环己二烯酮中间体，去芳构化）；③ 互变异构恢复芳香性。竞争：邻位 vs 对位羧化（阳离子/温度控制）——排序考点
- gold 能垒锚点：Kolbe–Schmitt 机理与酚盐-CO₂ 复合物结构 *J. Chem. Inf. Model.* 2007, 47, DOI 10.1021/ci700068b **[已核实]**；碱金属阳离子影响研究 **[已核实存在]**；Kosugi 等 2003, *Org. Biomol. Chem.*, 1, 817 **[已核实]**
- 舒适区：{C,H,O}（+ 金属阳离子计数外）；重原子 10
- 经典性：工业阿司匹林原料反应；Kolbe 1860
- 难度：★★

### N62. 卤仿反应（haloform reaction）
- 底物：丙酮 + 3 ClO⁻ → 乙酸根 + 氯仿
- SMILES：`CC(=O)C.[OCl-]>>CC(=O)[O-].ClC(Cl)Cl`（含 **Cl [低密度风险]**）
- 电荷/多重度：净 −3 / 1；烯醇盐 −1；三卤甲基碳负离子 −1
- 条件：NaOCl（或 Cl₂/NaOH）水溶液
- gold 机理：① 连续三次 α-氯化（烯醇盐 + ClO⁻，越氯化越快——拉电子诱导效应，速率递增是经典考点）；② OH⁻ 进攻羰基 → 四面体中间体；③ C–C 断裂（CX₃⁻ 是"好"离去基）→ 羧酸 + CHCl₃。竞争：单/双卤代中间体的进一步反应分叉
- gold 能垒锚点：Guthrie & Cossar 卤仿反应动力学（*Can. J. Chem.* 1986 前后）**[未核实]**；机理共识见 March 16-42/12-31
- 舒适区：{C,H,O,**Cl**}；重原子 5；**Cl 低密度风险**
- 经典性：碘仿试验（甲基酮鉴别反应）母体
- 难度：★★

---

## 附录 A：统计速览

- **候选总数：62**（目标最终 30，超采 ~2.1×）
- 类型分布：周环/σ 迁移 14；羰基加成缩合 15；极性反转/多组分 7；酰基转移 4；氧化/环氧 7；缺电子 1,2-重排 8；杂环/其他 7
- 难度分布：★ 11；★★ 33；★★★ 18
- 含 P/S/卤素（低密度风险）：5（N30 Wittig/P、N52 Hofmann/Br、N55 Favorskii/Cl、N60 Menshutkin/Cl、N62 卤仿/Cl）——均为故意保留的压力测试题
- 含 N 的候选：18；纯 CHO：39；纯 CH：7
- 重原子 >10 的底物/产物：N4(10)、N17(10)、N19(11)、N20(12)、N28(11)、N61(10)——均在 ≤15 预算内

## 附录 B：核实状态

- **[已核实]**（文献存在经 WebSearch 确认，部分含 DOI/数值）：N1, N3, N5, N6, N11, N13, N15, N22, N26, N30, N31, N32, N34, N35, N36, N39, N40, N41, N42, N44, N45, N46, N47, N49, N51, N53, N54, N59, N60, N61 → 30 条（另有多条 [部分核实] 数值/页码待补）
- **[部分核实]**：N2, N4, N7, N8, N9, N10, N12, N14, N16, N20, N23, N24, N25, N33, N38, N41(数值), N42, N48, N50 → 计入"已核实/部分核实"合计 ~48/62 ≈ **77%**
- **[未核实]**（教材记忆，入池前必查）：N17, N18(数值), N19, N21(卷页), N27, N29, N37, N43, N52, N55(数值), N56(数值), N57, N58, N62 → 14 条

## 附录 C：Top-15 推荐短名单（覆盖 + 锚点 + 梯度）

| 排名 | 编号 | 反应 | 推荐理由 |
|---|---|---|---|
| 1 | N1 | Diels–Alder | 实验 Ea 精确锚点，纯 CH，最易校准题 |
| 2 | N22 | 亚胺形成 | G2 级别锚点已核实，2–3 步网络最小完整题 |
| 3 | N3 | Claisen 重排 | 实验 + 多组计算锚点，船/椅竞争天然评分点 |
| 4 | N25 | 缩醛水解 | A-1 vs A-2 机理判别经典，CHNO 小分子 |
| 5 | N15 | Aldol 加成 | 烯醇盐生成/加成/副反应剪枝全要素 |
| 6 | N39 | 酯皂化 BAC2 | Zhan/Landry JACS 锚点已核实，四面体中间体捕获 |
| 7 | N41+N42 | 环氧开环（酸/碱对） | 同一底物双条件对比，计算锚点已核实 |
| 8 | N47 | Baeyer–Villiger | 决速步认定 + 迁移性排序，锚点已核实 |
| 9 | N49 | Beckmann 重排 | 含 N 重排代表，2015/2016 计算锚点已核实 |
| 10 | N32 | Cannizzaro | Swain 同位素锚点，氢负离子转移/歧化网络 |
| 11 | N11 | 环丁烯开环 | 对称性允许/禁阻排序，实验锚点已核实 |
| 12 | N16 | Aldol 缩合（丙酮） | 3 步 + 消除机理竞争，难度档上限代表 |
| 13 | N46 | 臭氧解 | 3 步 Criegee 网络 + 多参考风险，最高难度代表 |
| 14 | N28 | Michael 加成 | 1,2 vs 1,4 排序核心题，锚点部分核实需补强 |
| 15 | N30 | Wittig（简化叶立德） | 唯一 P 元素压力测试，JACS 2006 锚点已核实 |

备选替补：N5 Cope、N6 阴离子 oxy-Cope（离子体系对照）、N35 Passerini（多组分最高难度）、N36 Staudinger（两性离子机理争议）、N56 Fischer 吲哚（杂环+多步）。
