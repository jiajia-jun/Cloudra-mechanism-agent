# Hard 档候选反应清单 — 新颖微观立体化学与手性体系

> 生成日期：2026-08-25。超采 38 个候选（目标最终 20 个）。
> 考核点：三维几何感知、原子空间映射、精细构象搜索 —— torquoselectivity（顺旋方向竞争）、endo/exo 偏好、π-面选择性、椅式/船式竞争、阻转异构消旋阻垒、手性小分子/氢键诱导立体选择性。
>
> **舒适区约束（MACE-OMol25）**：候选体系以小分子量 CHNO 有机体系为主；除特别标注外重原子数 ≤20、闭壳层、单重态。个别候选含 B/Si/S（已在"舒适区自查"中显式标注），均在 OMol25 元素覆盖范围内但训练密度低于 CHNO，入选时需权衡。
>
> **数值约定**：gold 数值（ΔΔG‡/能垒差/选择性比值）为文献锚点的**量级参考**，判题容差建议 ±1 kcal/mol（能垒差）或对数级（比值）。标注"≈"者为从文献数值换算/记忆的近似值，gold 构建阶段需回查原文取准值。
>
> **核实状态**：`[已核实]` = 经 WebSearch 核实文献存在且卷期页码/DOI 与多个独立来源一致；`[部分核实]` = 文献确实存在（有可靠二手引证），但页码或数值未逐字核对；`[未核实]` = 凭领域常识给出，须回查。
>
> **SMILES 说明**：所有含立体化学标记的 SMILES 已用 RDKit 逐一解析验证（重原子数、CIP R/S、E/Z 归属均程序化核对）。个别产物（如 norbornene 系 endo/exo SMILES）的相对构型归属按 PubChem 同系物模式类推，标注"构型待 3D 核对"。

---

## A. Torquoselectivity 与电环化立体专一性（H-01 ~ H-07）

### H-01 3-甲基环丁烯顺旋开环（3-methylcyclobutene conrotatory ring opening）

1. 反应/底物：3-甲基环丁烯热开环 → 1,3-戊二烯，外向/内向旋转竞争。
2. SMILES：`CC1CC=C1` → 主产物 (E)：`C=C/C=C/C`；副产物 (Z)：`C=C/C=C\C`
3. 电荷/自旋：0 / 单重态（闭壳层）
4. 条件：气相或惰性溶剂，~150–200 °C，热反应。
5. gold 机理/选择性：协同顺旋开环；给电子甲基**外向**旋转占优（σ→σ* 超共轭 + 位阻），外向:内向 ΔΔE‡ ≈ 2 kcal/mol（计算），对应 (E):(Z) ≈ 9:1（150 °C 量级）。
6. 锚点：Rondan & Houk, *J. Am. Chem. Soc.* **1985**, 107, 2099–2111, DOI 10.1021/ja00293a046 `[已核实]`；Niwayama, Kallel, Spellmeyer, Sheu & Houk, *J. Org. Chem.* **1996**, 61, 2813–2825, DOI 10.1021/jo950884i `[已核实]`。
7. 舒适区：{C,H}；5 重原子；闭壳层 ✓
8. 权威性：torquoselectivity 奠基性计算研究（Houk 组）；Bachrach《Computational Organic Chemistry》教科书收录。

### H-02 3-甲酰基环丁烯"反向"torquoselectivity（3-formylcyclobutene — inward rotation of an acceptor）

1. 反应/底物：3-甲酰基环丁烯热开环 → (Z)/(E)-2,4-戊二烯醛。
2. SMILES：`O=CC1CC=C1` → 主产物 (Z)：`C=C/C=C\C/C=O`（canonical `C=C/C=C\C=O`）；副产物 (E)：`C=C/C=C/C=O`
3. 电荷/自旋：0 / 单重态
4. 条件：加热（实验 ~120–180 °C）。
5. gold 机理/选择性：强 π-受体 CHO **内向**旋转占优（与给体相反，torquoselectivity 的标志性"理论先于实验"案例），内向:外向 ΔΔE‡ ≈ 2–3 kcal/mol → (Z) 主产物。
6. 锚点：Kirmse, Rondan & Houk, *J. Am. Chem. Soc.* **1984**, 106, 7989–7991 `[已核实]`；Rudolf, Spellmeyer & Houk, *J. Org. Chem.* **1987**, 52, 3708–3710, DOI 10.1021/jo00392a047（"Prediction and experimental verification"，理论预测后被实验证实）`[已核实]`；综述 Dolbier, Koroniak, Houk & Sheu, *Acc. Chem. Res.* **1996**, 29, 471–477 `[已核实]`。
7. 舒适区：{C,H,O}；6 重原子；闭壳层 ✓
8. 权威性：Houk 组"理论预测先于实验"的经典案例，被广泛引用于选择性计算教材。

### H-03 3-甲氧基环丁烯（3-methoxycyclobutene — strong donor outward）

1. 反应/底物：3-甲氧基环丁烯热开环 → 1-甲氧基-1,3-丁二烯。
2. SMILES：`COC1CC=C1` → 主产物 (E)：`C=C/C=C/OC`；副产物 (Z)：`C=C/C=C\OC`
3. 电荷/自旋：0 / 单重态
4. 条件：气相热解（计算对象为主）。
5. gold 机理/选择性：给体 OMe 强烈外向（孤对电子供体效应叠加位阻），外向:内向 ΔΔE‡ 显著大于甲基体系（≈5–7 kcal/mol 量级）→ 几乎单一 (E)。
6. 锚点：Niwayama et al., *J. Org. Chem.* **1996**, 61, 2813–2825 `[已核实]`（该文系统给出 3-取代环丁烯外向/内向能垒差序列）；Rondan & Houk 1985 `[已核实]`。具体数值回查原文 `[部分核实]`。
7. 舒适区：{C,H,O}；6 重原子；闭壳层 ✓
8. 权威性：同 H-01/H-02 系列，构成"给体-受体 torquoselectivity 对比组"。

### H-04 3-(甲氧羰基)环丁烯（methyl cyclobut-3-ene-1-carboxylate — acceptor inward）

1. 反应/底物：3-(甲氧羰基)环丁烯热开环 → (Z)/(E)-2,4-戊二烯酸甲酯。
2. SMILES：`COC(=O)C1CC=C1` → 主产物 (Z)：`C=C/C=C\C(=O)OC`；副产物 (E)：`C=C/C=C/C(=O)OC`
3. 电荷/自旋：0 / 单重态
4. 条件：加热。
5. gold 机理/选择性：受体 CO2Me **内向**旋转占优，ΔΔE‡ ≈ 2–3 kcal/mol（与 CHO 同族行为，略弱）。
6. 锚点：Niwayama et al., *J. Org. Chem.* **1996**, 61, 2813–2825 `[已核实]`；Dolbier et al., *Acc. Chem. Res.* **1996**, 29, 471 `[已核实]`。数值回查原文 `[部分核实]`。
7. 舒适区：{C,H,O}；8 重原子；闭壳层 ✓
8. 权威性：同上；与 H-02 构成受体系列内梯度。

### H-05 顺-3,4-二甲基环丁烯立体专一开环（cis-3,4-dimethylcyclobutene — Woodward–Hoffmann stereospecificity）

1. 反应/底物：顺-3,4-二甲基环丁烯（内消旋 3R,4S）热开环。
2. SMILES：`C[C@@H]1C=C[C@@H]1C`（meso）→ 唯一产物 (2E,4Z)-2,4-己二烯：`C/C=C\C=C\C`（顺时针/逆时针顺旋殊途同归）
3. 电荷/自旋：0 / 单重态
4. 条件：加热，~175 °C。
5. gold 机理/选择性：4π 热顺旋（WH 规则）立体专一：meso 底物只给 (E,Z) 二烯；对旋为对称禁阻路径，能垒高 ≫10 kcal/mol。
6. 锚点：Woodward & Hoffmann, *J. Am. Chem. Soc.* **1965**, 87, 395–397, DOI 10.1021/ja01080a054 `[已核实]`；实验：Winter, *Tetrahedron Lett.* **1965**（3,4-二甲基环丁烯开环立体化学）`[部分核实]`；所有本科教科书（Clayden ch.34；Carey & Sundberg Part A）。
7. 舒适区：{C,H}；6 重原子；闭壳层 ✓
8. 权威性：轨道对称性守恒的教科书标准案例。

### H-06 反-3,4-二甲基环丁烯（trans-3,4-dimethylcyclobutene — 顺旋方向 × 位阻双重选择）

1. 反应/底物：反-3,4-二甲基环丁烯（3R,4R/3S,4S 对映对）热开环。
2. SMILES：`C[C@H]1C=C[C@@H]1C` → 主产物 (E,E)（双甲基外向）：`C/C=C/C=C/C`；副产物 (Z,Z)（双甲基内向）：`C/C=C\C=C/C`
3. 电荷/自旋：0 / 单重态
4. 条件：加热。
5. gold 机理/选择性：WH 允许的两条顺旋路径分别给 (E,E) 与 (Z,Z)；位阻使"双外向"占优，实验上 (E,E) 为主（ΔΔE‡ ≈ 2–4 kcal/mol 量级）。
6. 锚点：Woodward & Hoffmann 1965 `[已核实]`；Rondan & Houk 1985（取代基旋转方向理论）`[已核实]`；教材（Clayden ch.34）。
7. 舒适区：{C,H}；6 重原子；闭壳层 ✓
8. 权威性：同 H-05；考核 agent 同时处理对称性约束与 torquoselectivity 位阻偏好。

### H-07 (2E,4Z,6E)-辛三烯对旋闭环（(2E,4Z,6E)-octatriene disrotatory 6π electrocyclization）

1. 反应/底物：(2E,4Z,6E)-辛三烯热闭环 → 顺-5,6-二甲基-1,3-环己二烯。
2. SMILES：`C/C=C/C=C\C=C\C` → 主产物 cis（meso, 5R,6S）：`C[C@@H]1C=CC=C[C@@H]1C`；对映/副产物 trans：`C[C@H]1C=CC=C[C@@H]1C`
3. 电荷/自旋：0 / 单重态
4. 条件：加热（6π 热对旋）。
5. gold 机理/选择性：6π 热对旋立体专一：(E,Z,E) → cis 产物；顺旋路径对称禁阻。
6. 锚点：Woodward & Hoffmann 1965 `[已核实]`；Marvell 组取代己三烯电环化系列实验（Marvell, Caple & Shahidi, *J. Am. Chem. Soc.* **1970** 前后）`[部分核实]`；教材标准案例。
7. 舒适区：{C,H}；8 重原子；闭壳层 ✓
8. 权威性：6π 电环化立体专一性的经典判据反应。

---

## B. Diels–Alder endo/exo 与 π-面选择性（H-08 ~ H-15）

### H-08 环戊二烯 + 顺丁烯二酸酐（cyclopentadiene + maleic anhydride — Alder endo rule）

1. 反应/底物：[4+2] 环加成 → endo-双环[2.2.1]庚-5-烯-2,3-二甲酸酐（carbic anhydride）。
2. SMILES：`C1=CCC=C1` + `O=C1OC(=O)C=C1` → endo 主产物（PubChem CID 2723766）：`C1[C@@H]2C=C[C@H]1[C@@H]3[C@H]2C(=O)OC3=O`
3. 电荷/自旋：0 / 单重态
4. 条件：室温或温和加热，苯/醚类溶剂；不可逆捕获动力学产物。
5. gold 机理/选择性：动力学 **endo** 加成近乎专一（次级轨道相互作用 + 位阻），endo:exo >100:1；endo/exo ΔΔG‡ ≈ 1.5–2 kcal/mol。
6. 锚点：Alder & Stein, *Angew. Chem.* **1937**, 50, 510（endo 规则原始文献）`[已核实]`；Hoffmann & Woodward, *J. Am. Chem. Soc.* **1965**, 87, 4388–4389（次级轨道相互作用解释）`[已核实]`。
7. 舒适区：{C,H,O}；TS 复合物 12 重原子；闭壳层 ✓
8. 权威性：有机化学最著名的选择性规则之一；W–H 原始通讯直接讨论该体系。

### H-09 环戊二烯 + 丙烯醛 ± Lewis 酸（cyclopentadiene + acrolein — Lewis-acid enhanced endo selectivity）

1. 反应/底物：[4+2] → norborn-5-烯-2-甲醛的 endo/exo 比；对比无催化与 BF3 催化。
2. SMILES：`C1=CCC=C1` + `C=CC=O` → endo 主产物（构型待 3D 核对）：`O=C[C@H]1[C@@H]2C=C[C@H]1CC2`；exo：`O=C[C@H]1[C@@H]2C=C[C@@H]1CC2`
3. 电荷/自旋：0 / 单重态（Lewis 酸变体含 BF3 → 元素 B、F，另作标注）
4. 条件：无催化（室温，苯）；或 BF3·Et2O 催化（低温）。
5. gold 机理/选择性：无催化 endo:exo ≈ 3:1；Lewis 酸配位提高 endo 偏好至 >95:5 并加速（FMO 系数/能量变化）。endo/exo ΔΔG‡ 从无催化 ~0.6 kcal/mol 增至催化 ~2 kcal/mol（量级）。
6. 锚点：Houk & Strozier, *J. Am. Chem. Soc.* **1973**, 95, 4094–4096, DOI 10.1021/ja00793a070（Lewis 酸催化 DA 的 FMO 解释）`[已核实]`；Birney & Houk, *J. Am. Chem. Soc.* **1990**, 112, 4127–4133（BF3 催化丁二烯+丙烯醛 TS，选择性起源）`[已核实]`。
7. 舒适区：{C,H,O}；TS 9 重原子（无催化变体纯 CHNO）✓
8. 权威性：Houk 组 DA 选择性物理有机奠基文献。

### H-10 环戊二烯 + 丙烯腈（cyclopentadiene + acrylonitrile — weak endo preference）

1. 反应/底物：[4+2] → 2-氰基 norbornene endo/exo。
2. SMILES：`C1=CCC=C1` + `C=CC#N` → endo（构型待 3D 核对）：`N#C[C@H]1[C@@H]2C=C[C@H]1CC2`
3. 电荷/自旋：0 / 单重态
4. 条件：加热，~80–110 °C。
5. gold 机理/选择性：endo 偏好明显弱于丙烯醛/顺酐体系（endo:exo ≈ 1.3–2:1，量级）；次级轨道相互作用随亲双烯体取代基电负性减弱。
6. 锚点：Hoffmann & Woodward 1965 `[已核实]`；Sauer & Sustmann, *Angew. Chem. Int. Ed.* **1980**, 19, 779（DA 机理与选择性经典综述）`[部分核实]`；实验比值见教材（Carey & Sundberg Part B）。
7. 舒适区：{C,H,N}；TS 9 重原子；闭壳层 ✓
8. 权威性：endo 规则"强度随取代基变化"的对照案例，区分度好。

### H-11 环戊二烯 + 对苯醌（cyclopentadiene + p-benzoquinone — endo with quinone dienophile）

1. 反应/底物：[4+2]（单加成）→ endo-1,4,4a,8a-四氢-1,4-亚甲基萘-5,8-二酮。
2. SMILES：`C1=CCC=C1` + `O=C1C=CC(=O)C=C1` → endo 加成物（SMILES 构型待 3D 核对）：`O=C1C=CC(=O)[C@H]2[C@@H]1[C@H]1C=C[C@@H]2C1`
3. 电荷/自旋：0 / 单重态
4. 条件：室温，苯/乙醇。
5. gold 机理/选择性：endo 加成主产物（醌羰基指向双烯 π 面下方）；ΔΔG‡ ≈ 1.5–2 kcal/mol（量级，类比 MA 体系）。
6. 锚点：Alder & Stein 1937 `[已核实]`；教材（Clayden ch.34 用醌 DA 讲解 endo 规则）。
7. 舒适区：{C,H,O}；TS 13 重原子；闭壳层 ✓
8. 权威性：Alder 学派经典底物组合。

### H-12 环戊二烯自二聚（cyclopentadiene dimerization — endo kinetic vs exo thermodynamic）

1. 反应/底物：两分子 Cp → endo/exo-二环戊二烯。
2. SMILES：2 × `C1=CCC=C1` → endo 主产物（PubChem CID 10176158）：`C1C=C[C@@H]2[C@H]1[C@H]3C[C@@H]2C=C3`；exo 热力学产物：`C1C=C[C@H]2[C@@H]1[C@@H]3C[C@H]2C=C3`
3. 电荷/自旋：0 / 单重态
4. 条件：室温自发二聚（动力学 endo）；高温平衡可 retro-DA → 热力学比较。
5. gold 机理/选择性：动力学 **endo** 主产物（ΔΔG‡ ≈ 2 kcal/mol 量级）；可逆条件下 exo 更稳定（热力学产物）——动力学/热力学选择性分离的教科书案例。
6. 锚点：Woodward & Katz（二环戊二烯结构/机理，*Tetrahedron* **1959**, 5, 70）`[部分核实]`；Hoffmann & Woodward 1965 `[已核实]`；教材。
7. 舒适区：{C,H}；TS 10 重原子；闭壳层 ✓
8. 权威性：每个有机实验室都观察到的自发过程，endo/exo 与可逆性结合的最佳教学案例。

### H-13 呋喃 + N-甲基马来酰亚胺（furan + N-methylmaleimide — reversible DA, endo→exo drift）

1. 反应/底物：[4+2] → 7-氧杂 norbornene 酰亚胺 endo/exo。
2. SMILES：`c1ccoc1` + `CN1C(=O)C=CC1=O` → endo 动力学主产物（构型待 3D 核对）：`CN1C(=O)[C@H]2[C@H](C1=O)[C@H]1C=C[C@@H]2O1`
3. 电荷/自旋：0 / 单重态
4. 条件：室温（动力学控制）或加热长时间（平衡）。
5. gold 机理/选择性：呋喃 DA 高度可逆：低温/短时 **endo** 主产物；高温/长时 **exo**（热力学）累积——endo 规则"失效"的经典反例（动力学 vs 热力学）。
6. 锚点：教材（Clayden ch.34；Carey & Sundberg Part B）`[已核实，教材级]`；定量研究见 DA 可逆性文献（如 Anselme 等呋喃-酰亚胺体系）`[部分核实]`。
7. 舒适区：{C,H,N,O}；TS 13 重原子；闭壳层 ✓
8. 权威性：考核 agent 是否识别"可逆反应中选择性随时间/温度漂移"，Hard 档区分点。

### H-14 5-甲基环戊二烯 + 顺丁烯二酸酐（5-methylcyclopentadiene + maleic anhydride — π-facial syn/anti）

1. 反应/底物：5-取代 Cp 的 DA π-面选择性（亲双烯体从取代基同面/异面进攻）。
2. SMILES：`CC1C=CC=C1` + `O=C1OC(=O)C=C1` → anti 主产物（syn/anti 加成物 SMILES 构型待 3D 核对，名称给出即可）
3. 电荷/自旋：0 / 单重态
4. 条件：低温快速捕获（注意 5-取代 Cp 经 1,5-H 迁移快速异构化——题目需注明锁定异构体）。
5. gold 机理/选择性：小位阻给体取代基 → **anti** 进攻占优（位阻控制，anti:syn 高）；给氧取代基（5-OAc 等）出现"反位阻"（contrasteric）syn 偏好——电子 vs 位阻竞争的标杆体系。
6. 锚点：Gleiter & Paquette, *Acc. Chem. Res.* **1983**, 16, 328（π-面选择性综述）`[已核实]`；Fallis 组 5-取代 Cp 实验系列（*Can. J. Chem.* 1984 起）`[部分核实]`；现代计算复核见 Burnell 等及 distortion/interaction 分析 `[部分核实]`。
7. 舒适区：{C,H,O}；TS 13 重原子；闭壳层 ✓
8. 权威性：π-面选择性概念的发源地体系之一。

### H-15 (E)-1-甲氧基丁二烯 + 丙烯醛（trans-1-methoxybutadiene + acrolein — regioselectivity × endo）

1. 反应/底物：给体-取代双烯与受体亲双烯体的区域选择性（"邻位" vs "对位"加成物）叠加 endo/exo。
2. SMILES：`CO/C=C/C=C` + `C=CC=O` → "邻位"主产物 2-甲氧基-3-甲酰基环己烯（endo，名称锚定，SMILES 构型待 3D 核对）
3. 电荷/自旋：0 / 单重态
4. 条件：加热或 Lewis 酸催化。
5. gold 机理/选择性：FMO 预测"邻位"（OMe 与 CHO 1,2-关系）区域异构体为主 + endo 取向；区域选择性 ΔΔG‡ ≈ 1–2 kcal/mol（量级）。
6. 锚点：Houk, *J. Am. Chem. Soc.* **1973**, 95, 4092–4094, DOI 10.1021/ja00793a069（广义前线轨道与 DA 区域选择性）`[已核实]`；Houk, *Acc. Chem. Res.* **1975**, 8, 361, DOI 10.1021/ar50095a001 `[已核实]`。
7. 舒适区：{C,H,O}；TS 10 重原子；闭壳层 ✓
8. 权威性：DA 区域选择性 FMO 解释的原始文献。

---

## C. Nitrone [3+2] 环加成（H-16 ~ H-18）

### H-16 C,N-二甲基硝酮 + 乙烯（C,N-dimethyl nitrone + ethylene — minimal [3+2] TS 基线）

1. 反应/底物：最小硝酮 1,3-偶极环加成模型 → N-甲基异噁唑烷；考核协同 [3+2] TS 几何与 endo/exo 概念基线。
2. SMILES：`C/C=[N+](/C)[O-]`（(Z)-硝酮）+ `C=C` → 产物 `CN1CCCO1`（异噁唑烷骨架：`CN1CCCO1`）
3. 电荷/自旋：0 / 单重态（硝酮为两性离子共振式，净中性闭壳层）
4. 条件：加热（模型体系，计算对象）。
5. gold 机理/选择性：协同、异步性小的 [3+2]；无立体中心的基线体系，用于标定 TS 搜索与 FMO 类型（Type I/II 归属）。
6. 锚点：Houk, Sims, Duke, Strozier & George, *J. Am. Chem. Soc.* **1973**, 95, 7287–7301, DOI 10.1021/ja00803a017 `[已核实]`；Houk, Sims, Watts & Luskus, *J. Am. Chem. Soc.* **1973**, 95, 7301–7315, DOI 10.1021/ja00803a018 `[已核实]`。
7. 舒适区：{C,H,N,O}；TS 7 重原子；闭壳层 ✓
8. 权威性：1,3-偶极环加成 FMO 理论奠基双论文。

### H-17 (Z)-C-苯基-N-甲基硝酮 + 丙烯酸甲酯（nitrone + methyl acrylate — regio/endo-exo）

1. 反应/底物：Type-I FMO 环加成 → 2-甲基-3-苯基异噁唑烷-5-甲酸酯（5-取代区域异构体为主）+ endo/exo 竞争。
2. SMILES：`C/[N+]([O-])=C/c1ccccc1`（(Z)-硝酮）+ `C=CC(=O)OC` → 主产物（5-CO2Me 区域异构体，反式 C3/C5 相对构型为例）：`COC(=O)[C@@H]1C[C@H](c2ccccc2)N(C)O1`
3. 电荷/自旋：0 / 单重态
4. 条件：苯，回流或室温长时间。
5. gold 机理/选择性：FMO 预测 5-取代异噁唑烷区域异构体为主（5- vs 4-取代 ΔΔG‡ ≈ 2–3 kcal/mol 量级）；endo（CO2Me 指向硝酮 π 面下）略占优。
6. 锚点：Houk et al. 1973 双论文 `[已核实]`；硝酮环加成实验/综述：Tufariello 载 Padwa 编《1,3-Dipolar Cycloaddition Chemistry》（Wiley, 1984）`[部分核实]`；现代 DFT 复核文献众多 `[部分核实]`。
7. 舒适区：{C,H,N,O}；TS 16 重原子；闭壳层 ✓
8. 权威性：硝酮化学最经典底物组合；区域选择性解释是 FMO 理论标志性成功案例。

### H-18 (Z)-C-苯基-N-甲基硝酮 + (E)-巴豆酸甲酯（nitrone + methyl crotonate — stereospecificity）

1. 反应/底物：[3+2] 对双键构型的立体专一保持：E 亲偶极体 → trans-4,5-二取代异噁唑烷。
2. SMILES：`C/[N+]([O-])=C/c1ccccc1` + `C/C=C/C(=O)OC` → 主产物 trans-4,5：`CN1O[C@H](C(=O)OC)[C@@H](C)[C@@H]1c1ccccc1`（相对构型 trans；绝对描述符随面对而异）
3. 电荷/自旋：0 / 单重态
4. 条件：加热，苯。
5. gold 机理/选择性：双超面（suprafacial-suprafacial）协同加成 → E→trans 立体专一（dr 接近单一）；(Z)-巴豆酸酯对照应给 cis-4,5。
6. 锚点：Huisgen 1,3-偶极环加成立体专一性原理（*Angew. Chem. Int. Ed.* **1963**, 2, 565/633）`[部分核实]`；Tufariello 1984 `[部分核实]`。
7. 舒适区：{C,H,N,O}；TS 17 重原子；闭壳层 ✓
8. 权威性：[3+2] 立体专一性的定义性案例。

---

## D. 小环开环立体专属性（H-19 ~ H-23）

### H-19 反-2,3-二甲基环氧乙烷酸催化水解（trans-2,3-dimethyloxirane acid hydrolysis — anti opening）

1. 反应/底物：(2R,3R)-反-2,3-二甲基环氧乙烷 + H3O+ → 2,3-丁二醇。
2. SMILES：`C[C@H]1[C@@H](O1)C`（(2S,3S) 对映体之一）→ 主产物 anti 开环、受进攻碳构型翻转：dl-2,3-丁二醇 (2R,3R)/(2S,3S)：`C[C@H]([C@@H](C)O)O`；meso (2R,3S)：`C[C@H]([C@H](C)O)O` 为"错误"非对映体
3. 电荷/自旋：0 / 单重态（酸催化变体 TS 含质子化环氧 → +1 电荷，标注）
4. 条件：稀酸水溶液，室温。
5. gold 机理/选择性：背面 SN2 型开环 → 反式（anti）邻二醇；立体专一构型翻转，dl 产物（若底物为外消旋）。考核：SN2 背面进攻几何 + 环状底物立体化学映射。
6. 锚点：教材标准案例（Clayden ch.33；Carey & Sundberg Part A ch.5）`[已核实，教材级]`；反式双轴向开环规则 Fürst & Plattner, *Helv. Chim. Acta* **1949**, 32, 275 `[部分核实]`。
7. 舒适区：{C,H,O}；5–6 重原子；闭壳层 ✓
8. 权威性：环氧开环立体专属性是所有物理有机教材的必修案例。

### H-20 环氧环己烷亲核开环（cyclohexene oxide ring opening — Fürst–Plattner trans-diaxial）

1. 反应/底物：环氧环己烷 + 氢氧根（或氢化物）→ 反-2-羟基环己醇。
2. SMILES：`C1CCC2OC2C1` + `[OH-]` → 反式产物：`O[C@@H]1CCCC[C@H]1O`（(1R,2R)-反-1,2-环己二醇单醇形式，构型待 3D 核对）
3. 电荷/自旋：0 / 单重态（亲核试剂为 −1）
4. 条件：NaOH 水溶液加热。
5. gold 机理/选择性：反式双轴向（trans-diaxial）开环唯一产物——椅式构象锁定下 SN2 进攻必须轴向进入；顺式/双赤道开环为高能路径。
6. 锚点：Fürst & Plattner, *Helv. Chim. Acta* **1949**, 32, 275 `[部分核实]`；教材（Clayden；Eliel《Stereochemistry of Carbon Compounds》）。
7. 舒适区：{C,H,O}；TS ≤8 重原子；闭壳层 ✓
8. 权威性：构象分析 × 立体电子效应的经典交汇点。

### H-21 氧化苯乙烯酸/碱条件区位翻转（styrene oxide — regioselectivity switch with inversion）

1. 反应/底物：氧化苯乙烯 + 亲核试剂（如甲氧基）：碱性条件进攻末端碳，酸性条件进攻苄位碳，两者均构型翻转。
2. SMILES：`c1ccccc1[C@@H]2CO2`（(R)）→ 碱：苄位保留（未断裂）+ 末端被进攻 → (R)-1-甲氧基? 更正：碱性 → `COCC(O)c1ccccc1`（苄位立体中心保留）；酸性 → `COC[C@@H](c1ccccc1)O` 苄位被进攻翻转
3. 电荷/自旋：0 / 单重态（酸催化 TS 带 +1）
4. 条件：NaOMe/MeOH（碱）；MeOH/H+（酸）。
5. gold 机理/选择性：区位选择性随条件翻转（SN2 位阻控制 vs 部分 SN1 特征的苄位稳定化），立体化学均为背面进攻翻转；ΔΔG‡ ≈ 1.5–3 kcal/mol 量级。
6. 锚点：教材标准案例（Clayden ch.33；March's Advanced Organic Chemistry）`[已核实，教材级]`。
7. 舒适区：{C,H,O}；TS ~11 重原子；闭壳层 ✓
8. 权威性：区域/立体选择性耦合的经典案例。

### H-22 环氧丙烷碱性开环（propylene oxide + hydroxide — 最小 SN2 位阻选择性）

1. 反应/底物：环氧丙烷 + [OH-] → 1,2-丙二醇，SN2 进攻少取代碳。
2. SMILES：`C[C@H]1CO1`（(R)）+ `[OH-]` → 主产物（末端进攻，构型保留）：`C[C@H](O)CO`
3. 电荷/自旋：−1（试剂）/ 单重态
4. 条件：NaOH 水溶液。
5. gold 机理/选择性：SN2 少取代碳进攻 ≫ 多取代碳（ΔΔG‡ ≈ 2–3 kcal/mol 量级）；立体中心不被触及（区域选择性题 + 立体化学"不动点"对照）。
6. 锚点：教材（Clayden ch.33）`[已核实，教材级]`。
7. 舒适区：{C,H,O}；TS ~5 重原子；闭壳层 ✓
8. 权威性：最简单的位阻控制区位选择性模型，作为 D 组基线。

### H-23 2-甲基氮杂环丙烷活化开环（2-methylaziridine — aziridine ring opening stereospecificity）

1. 反应/底物：(R)-2-甲基氮杂环丙烷酸催化（N 质子化活化）醇解开环 → β-氨基醚，进攻位置与构型翻转分析。
2. SMILES：`C[C@H]1CN1`（(R)）+ MeOH/H+ → 主产物（取代碳进攻、翻转）：`C[C@@H](OC)CN` 或区域异构体 `C[C@H](N)COC`（构型待 3D 核对）
3. 电荷/自旋：+1（质子化底物）/ 单重态
4. 条件：酸性醇溶液。
5. gold 机理/选择性：N 活化后进攻取代碳占优（与未活化底物相反），背面进攻翻转；与 H-21 环氧体系构成 O/N 类比对照。
6. 锚点：Dermer & Ham,《Ethylenimine and Other Aziridines》（Academic Press, 1969）`[部分核实]`；教材（Clayden ch.33 氮杂环开环）。
7. 舒适区：{C,H,N,O}；TS ~7 重原子；闭壳层 ✓
8. 权威性：氮杂环化学标准参考专著覆盖的体系。

---

## E. 羰基 π-面选择性与手性还原（H-24 ~ H-26）

### H-24 (S)-3-苯基-2-丁酮硼氢化（Felkin–Anh π-facial selection）

1. 反应/底物：(S)-3-苯基-2-丁酮 + 硼氢化钠 → 赤式/苏式-3-苯基-2-丁醇。
2. SMILES：`CC(=O)[C@@H](C)c1ccccc1`（(S)）+ `[BH4-]` → 两个非对映体：(2S,3R) 型 `C[C@H](O)[C@H](C)c1ccccc1` 与 (2S,3S) 型 `C[C@H](O)[C@@H](C)c1ccccc1`（哪个为主由 Felkin–Anh 预测：绝对描述符归属在 gold 构建时按模型核对）
3. 电荷/自旋：−1（试剂）/ 单重态
4. 条件：NaBH4/MeOH 或 LiAlH4/Et2O，0 °C–室温。
5. gold 机理/选择性：Felkin–Anh 构象（Ph 垂直羰基平面，亲核试剂沿 Bürgi–Dunitz 从最小取代基侧进入）预测主非对映体；实验 dr ≈ 3–5:1（LAH，量级）。考核：无环体系构象系综 + σ* 立体电子效应。
6. 锚点：Chérest, Felkin & Prudent, *Tetrahedron Lett.* **1968**, 2199–2204, DOI 10.1016/S0040-4039(00)89719-1 `[已核实]`；Paddon-Row, Rondan & Houk, *J. Am. Chem. Soc.* **1982**, 104, 7162–7166（Anh–Eisenstein 模型的计算验证）`[已核实]`。
7. 舒适区：{C,H,O,B}；TS ~12 重原子；闭壳层 ✓
8. 权威性：无环羰基面选择性最被引用的模型体系与计算验证。

### H-25 4-叔丁基环己酮还原（4-tert-butylcyclohexanone — axial vs equatorial attack）

1. 反应/底物：构象锁定环己酮 + 氢化物 → 反式（赤道 OH）/顺式（轴向 OH）-4-叔丁基环己醇。
2. SMILES：`CC(C)(C)C1CCC(=O)CC1` + `[BH4-]` → 主产物 trans（赤道 OH，轴向进攻）：`CC(C)(C)[C@H]1CC[C@@H](O)CC1`；副产物 cis：`CC(C)(C)[C@H]1CC[C@H](O)CC1`
3. 电荷/自旋：−1（试剂）/ 单重态
4. 条件：LiAlH4/Et2O 或 NaBH4/醇。
5. gold 机理/选择性：小亲核试剂**轴向进攻**占优（扭转应变控制，Wu–Houk）→ 赤道醇为主（LAH 约 8–9:1，量级）；大位阻试剂反转为赤道进攻。ΔΔG‡ ≈ 1.3–1.5 kcal/mol。
6. 锚点：Chérest, Felkin & Prudent 1968 `[已核实]`；Wu, Tucker & Houk, *J. Am. Chem. Soc.* **1991**, 113, 5018–5027, DOI 10.1021/ja00013a042 `[已核实]`；Eliel 教材。
7. 舒适区：{C,H,O,B}；TS ~12 重原子；闭壳层 ✓
8. 权威性：构象-选择性耦合的教科书标杆，且被 Houk 组定量计算解释。

### H-26 CBS 还原苯乙酮简化模型（Corey–Bakshi–Shibata reduction, small-model）

1. 反应/底物：苯乙酮 + BH3 + 手性 1,3,2-氧氮硼杂环戊烷（简化 CBS 模型：(S)-5-甲基取代）→ 1-苯基乙醇。
2. SMILES：`CC(=O)c1ccccc1` + `B`（BH3）+ 催化剂模型 `C[C@H]1COBN1` → 主产物 (R)-1-苯基乙醇（对映面由催化剂构型决定）：`C[C@H](C1=CC=CC=C1)O`
3. 电荷/自旋：0 / 单重态
4. 条件：THF，−20 °C~室温，催化量 oxazaborolidine。
5. gold 机理/选择性：双配位六元环椅式 TS（B–H 从较小位阻面转移）：酮氧配位催化剂 B、BH3 配位 N；预测 ee 对应 ΔΔG‡ ≈ 2 kcal/mol（≈95% ee 量级，实验 CBS 苯乙酮 96–97% ee）。
6. 锚点：Corey, Bakshi & Shibata, *J. Am. Chem. Soc.* **1987**, 109, 5551–5553, DOI 10.1021/ja00252a056 `[已核实]`；Quallich, Blake & Woodall, *J. Am. Chem. Soc.* **1994**, 116, 8516（小模型 TS 从头算）`[已核实]`；综述 Corey & Helal, *Angew. Chem. Int. Ed.* **1998**, 37, 1986–2012 `[已核实]`；Alagona et al. 2003, DOI 10.1021/ja034928d `[已核实]`。
7. 舒适区：{C,H,O,N,B}；TS 复合物 ~16 重原子；闭壳层 ✓（**含 B，标注**）
8. 权威性：诺贝尔级不对称催化（Corey），小模型 TS 计算自 1994 年起反复复核。

---

## F. 氢键导向环氧化（H-27 ~ H-28）

### H-27 环己-2-烯-1-醇过酸环氧化（Henbest directed epoxidation）

1. 反应/底物：环己-2-烯-1-醇 + 过甲酸 → 顺-2,3-环氧环己醇。
2. SMILES：`OC1C=CCCC1` + `OC(=O)OO` → 主产物 cis（OH 与环氧同侧）：`O[C@H]1[C@@H]2O[C@H]2CCC1`（构型待 3D 核对）
3. 电荷/自旋：0 / 单重态
4. 条件：过苯甲酸/过甲酸，CH2Cl2 或苯，0–25 °C。
5. gold 机理/选择性：烯丙位 OH 与过酸氢键缔合导向 **syn/cis** 环氧化（Henbest 规则）：实验 cis:trans ≈ 91:9（ΔΔG‡ ≈ 1.4 kcal/mol）；蝶形（butterfly）TS 几何。
6. 锚点：Henbest & Wilson, *J. Chem. Soc.* **1957**, 1958–1965 `[已核实]`；计算/模型：Houk et al., *Science* **1986**, 231, 1108–1117 `[已核实]`；91:9 数值出自 Whitham 对 Henbest 体系的重测（见 Glasgow 大学学位论文综述转引）`[部分核实]`。
7. 舒适区：{C,H,O}；TS 9 重原子；闭壳层 ✓
8. 权威性：底物导向立体选择性（substrate-directable reaction）的开端文献；Hoveyda-Evans-Fu *Chem. Rev.* 1993 综述将其列为导向反应范式。

### H-28 无环手性烯丙醇过酸环氧化（(S)-(E)-pent-3-en-2-ol — acyclic allylic alcohol π-face）

1. 反应/底物：(S)-(E)-戊-3-烯-2-醇 + 过甲酸 → threo/erythro-2,3-环氧戊醇。
2. SMILES：`C/C=C/[C@H](C)O`（(4S,E)）+ `OC(=O)OO` → 两个非对映环氧醇（主/次归属按 Houk 模型，构型待 3D 核对）
3. 电荷/自旋：0 / 单重态
4. 条件：过酸，非配位溶剂。
5. gold 机理/选择性：OH 导向 + 无环构象（"inside alkoxy"效应前的 Houk 烯丙醇模型）预测主非对映体；dr ≈ 2–3:1（量级）——比环状体系弱，更考验构象搜索完备性。
6. 锚点：Houk et al., *Science* **1986**, 231, 1108 `[已核实]`；Chamberlin, Mulholland, Kahn & Hehre, *J. Am. Chem. Soc.* **1987**, 109, 672（"inside alkoxy"效应）`[部分核实]`。
7. 舒适区：{C,H,O}；TS 8 重原子；闭壳层 ✓
8. 权威性：Houk "立体选择性反应的理论与建模"名文覆盖的体系。

---

## G. [3,3]-σ 迁移：椅式/船式竞争（H-29 ~ H-31）

### H-29 meso-3,4-二甲基-1,5-己二烯 Cope 重排（Cope rearrangement — chair TS stereospecificity）

1. 反应/底物：meso-(3R,4S)-3,4-二甲基-1,5-己二烯热重排 → (2E,6Z)-辛-2,6-二烯。
2. SMILES：`C=C[C@H](C)[C@H](C)C=C`（meso, (3S,4R)）→ 椅式 TS 主产物 (E,Z)：`C/C=C/CC/C=C\C`（canonical `C/C=C\CC/C=C/C`）
3. 电荷/自旋：0 / 单重态
4. 条件：气相热解，~200–250 °C。
5. gold 机理/选择性：椅式 TS ≫ 船式（实验 ΔΔG‡ ≈ 5.8 kcal/mol；高级别计算椅-船差 11.4 kcal/mol，CASPT2，Khaledy–Houk 2003 转引）→ meso 底物立体专一给出 (E,Z) 二烯。
6. 锚点：Doering & Roth, *Tetrahedron* **1962**, 18, 67（椅/船 TS 与立体专一的奠基实验）`[部分核实，经 Bachrach 教科书引证列表核实存在]`；Khaledy et al., *J. Org. Chem.* **2003**, 68, 572–577, DOI 10.1021/jo020595b `[已核实]`。
7. 舒适区：{C,H}；8 重原子；闭壳层 ✓
8. 权威性：Cope 立体化学的"罗塞塔石碑"实验。

### H-30 (E,E)-巴豆基丙烯基醚 Claisen 重排（Claisen rearrangement — chair preference, syn/anti）

1. 反应/底物：(E)-巴豆基-(E)-丙烯基乙烯基醚热重排 → syn/anti-2,3-二甲基戊-4-烯醛。
2. SMILES：`C/C=C/CO/C=C/C`（(E,E)）→ 椅式（双甲基假赤道）主产物 syn-2,3-二甲基戊-4-烯醛（dl 对之一）：`C=C[C@H](C)[C@H](C)C=O`；anti（meso 型）：`C=C[C@H](C)[C@@H](C)C=O`（syn/anti 与 CIP 对应关系待 gold 构建核对）
3. 电荷/自旋：0 / 单重态
4. 条件：~150–200 °C。
5. gold 机理/选择性：椅式 TS 强烈占优（椅:船 ≥ 95:5，量级），(E,E) → syn 主产物；syn:anti ΔΔG‡ ≈ 2–3 kcal/mol。
6. 锚点：Vance, Rondan, Houk et al., *J. Am. Chem. Soc.* **1988**, 110, 2314, DOI 10.1021/ja00215a059（Claisen TS 从头算）`[已核实 DOI/标题]`；Vittorelli, Winkler, Hansen & Schmid, *Helv. Chim. Acta* **1968**, 51, 1457（椅/船产物比实验）`[部分核实]`。
7. 舒适区：{C,H,O}；8 重原子；闭壳层 ✓
8. 权威性：Claisen 立体化学的实验（Schmid 学派）与计算（Houk 组）双经典。

### H-31 (E)-巴豆基丙酸酯 Ireland–Claisen（Ireland–Claisen — silyl ketene acetal E/Z × chair）

1. 反应/底物：(E)-巴豆基丙酸酯 → LDA/TMSCl 捕获为 (E)- 或 (Z)-O-硅基烯酮缩醇 → 椅式重排 → syn/anti-2,3-二甲基戊-4-烯酸（TMS 酯水解后）。
2. SMILES：底物 `C/C=C/COC(=O)CC`；(E)-烯酮缩醇 `C/C=C/CO/C(=C/C)/O[Si](C)(C)C`；(Z)-烯酮缩醇 `C/C=C/CO/C(=C\C)/O[Si](C)(C)C` → 产物酸：`C=C[C@H](C)[C@H](C)C(=O)O`（dl 对之一）
3. 电荷/自旋：0 / 单重态
4. 条件：LDA/THF/−78 °C → TMSCl（THF 给 Z(O)，HMPA 添加给 E(O)）→ 室温重排 → 水解。
5. gold 机理/选择性：烯酮缩醇几何决定相对构型（E(O)/Z(O) 分别经椅式 TS 给出相反的非对映体）；椅式 TS 中取代基假赤道排布；dr 常 >95:5。
6. 锚点：Ireland, Mueller & Willard, *J. Am. Chem. Soc.* **1976**, 98, 2868–2877, DOI 10.1021/ja00426a033 `[已核实]`；计算：Khaledy, Kalani, Khuong, Houk, Aviyente, Neier, Soldermann & Velker, *J. Org. Chem.* **2003**, 68, 572–577, DOI 10.1021/jo020595b `[已核实]`。E(O)/Z(O)→syn/anti 助记对应关系 `[部分核实，gold 构建时按原文图核对]`。
7. 舒适区：{C,H,O,Si}；TS ~13 重原子；闭壳层 ✓（**含 Si，标注**）
8. 权威性：立体选择性烯醇化学的教科书反应（Ireland 1976 被引 >2000）；Houk 组直接计算过椅/船偏好起源。

---

## H. 阻转异构消旋阻垒（H-32 ~ H-34）

### H-32 1,1′-联萘消旋化（1,1′-binaphthyl atropisomerization）

1. 反应/底物：(R)/(S)-1,1′-联萘经 peri-H 挤过的双叶翻转 TS 消旋。
2. SMILES：对映体（轴手性 R_a/S_a）：`C1=CC=C2C(=C1)C=CC=C2C3=CC=CC4=CC=CC=C43`（消旋体表示；轴手性标记可用 `[C@]`/`[C@@]` 四面体约定或 PubChem 3D 锚定，gold 构建时确认）
3. 电荷/自旋：0 / 单重态
4. 条件：热消旋（动力学测定 ~50 °C，极性溶剂）。
5. gold 机理/选择性：消旋阻垒 ΔG‡ ≈ 23.5 kcal/mol（t1/2 ≈ 14.5 min @ 50 °C）；两条路径（syn/anti peri-H 对穿）能差 ~1 kcal/mol 量级。
6. 锚点：Cooke & Harris, *J. Chem. Soc.* **1963**（消旋动力学测定，23.5 kcal/mol 与 14.5 min 半衰期经二手文献一致转引）`[部分核实]`；Carter & Liljefors, *Tetrahedron* **1976**, 32, 2915–2922, DOI 10.1016/0040-4020(76)80145-7（构象反转的分子力学研究）`[已核实]`。
7. 舒适区：{C,H}；20 重原子（恰在边界）；闭壳层 ✓
8. 权威性：轴手性消旋动力学的第一个定量经典体系之一。

### H-33 6,6′-二硝基联苯-2,2′-二甲酸（6,6′-dinitrodiphenic acid — first resolved atropisomer）

1. 反应/底物：历史上首例被拆分的阻转异构体（Christie & Kenner 1922）；热消旋阻垒测定对象。
2. SMILES（PubChem CID 95234）：`C1=CC(=C(C(=C1)[N+](=O)[O-])C2=C(C=CC=C2[N+](=O)[O-])C(=O)O)C(=O)O`
3. 电荷/自旋：0 / 单重态
4. 条件：加热消旋（溶液）。
5. gold 机理/选择性：邻位四取代（2,2′-COOH + 6,6′-NO2）使室温可拆分；阻垒估计 ~28–32 kcal/mol `[未核实具体数值，gold 构建需查原始动力学文献或 Eliel 教材表格]`。
6. 锚点：Christie & Kenner, *J. Chem. Soc., Trans.* **1922**, 121, 614–620, DOI 10.1039/CT9222100614 `[已核实]`。
7. 舒适区：{C,H,N,O}；**24 重原子，超出 ≤20 预算，标注**；若超限可降级为 2,2′-二硝基联苯（18 重原子）变体。闭壳层 ✓
8. 权威性：阻转异构现象的"开天辟地"文献，史论意义极高。

### H-34 1,1′-联萘-2,2′-二酚（BINOL racemization barrier）

1. 反应/底物：(R)/(S)-BINOL 热消旋。
2. SMILES（消旋体表示）：`Oc1ccc2ccccc2c1-c1c(O)ccc2ccccc12`
3. 电荷/自旋：0 / 单重态
4. 条件：高温（>100 °C）溶液消旋；酸/碱催化加速。
5. gold 机理/选择性：消旋阻垒 ΔG‡ ≈ 35–37 kcal/mol（中性条件 100 °C 长期稳定；diglyme 150 °C 20 h 仅 ~10% 消旋——实验锚点）；计算研究给出 syn 路径 ~37 kcal/mol。
6. 锚点：实验稳定性与消旋速率：*Can. J. Chem.* **1980**, 58, 2134（DOI 10.1139/v80-021）`[已核实]`；DFT 阻垒：Meca, Řeha & Havlas, *J. Org. Chem.* **2003**, 68, 5677 `[未核实页码，需回查]`。
7. 舒适区：{C,H,O}；**22 重原子，略超预算，标注**；闭壳层 ✓
8. 权威性：不对称催化中最著名的轴手性骨架，消旋稳定性是其实用性的根基。

---

## I. 手性小分子/氢键催化诱导（H-35 ~ H-38）

### H-35 脯氨酸催化直接 Aldol（List–Barbas aldol：acetone + benzaldehyde）

1. 反应/底物：(S)-脯氨酸催化丙酮与苯甲醛直接羟醛 → 4-羟基-4-苯基-2-丁酮，单一绝对构型为主。
2. SMILES：`CC(C)=O` + `O=Cc1ccccc1` + 催化剂 `O=C(O)[C@@H]1CCCN1`（L-脯氨酸 (S)）→ 主产物（(S)-脯氨酸 → 可预测绝对构型，gold 构建按 Houk–List TS 核对）：`CC(=O)C[C@H](O)c1ccccc1`
3. 电荷/自旋：0 / 单重态
4. 条件：20–30 mol% (S)-脯氨酸，DMSO，室温。
5. gold 机理/选择性：烯胺机理 + Houk–List 金属自由 Zimmerman–Traxler 型椅式 TS（羧基质子转移 + 氢键网络），单分子脯氨酸参与；苯甲醛 ee ≈ 60–76%（对硝基苯甲醛 76%，List 2000），ΔΔG‡ ≈ 1.2 kcal/mol。
6. 锚点：List, Lerner & Barbas, *J. Am. Chem. Soc.* **2000**, 122, 2395–2396, DOI 10.1021/ja994280y `[已核实]`；Bahmanyar & Houk, *J. Am. Chem. Soc.* **2001**, 123, 11273–11283, DOI 10.1021/ja011403h `[已核实]`；Hoang, Bahmanyar, Houk & List, *J. Am. Chem. Soc.* **2003**, 125, 16–17, DOI 10.1021/ja028634o `[已核实]`。
7. 舒适区：{C,H,N,O}；TS ~20 重原子（边界）；闭壳层 ✓
8. 权威性：2021 诺贝尔化学奖核心反应 + Houk–List TS 模型（不对称有机催化计算解释的范式）。

### H-36 脯氨酸催化三组份 Mannich（List Mannich：syn-β-氨基酮）

1. 反应/底物：(S)-脯氨酸催化丙酮 + N-苄亚甲基甲胺（模型亚胺）→ syn-4-甲氨基-4-苯基-2-丁酮。
2. SMILES：`CC(C)=O` + `C/N=C/c1ccccc1` + `O=C(O)[C@@H]1CCCN1` → syn 主产物：`CC(=O)C[C@H](c1ccccc1)NC` 的对映/非对映归属按 Houk–List TS 核对
3. 电荷/自旋：0 / 单重态
4. 条件：脯氨酸催化，DMSO/DMF，室温。
5. gold 机理/选择性：烯胺对亚胺 si/re 面进攻 → **syn** 非对映体高 dr + 高 ee（实验 syn:anti >10:1，ee >90% 量级）；TS 中羧基同时活化亚胺并定向烯胺。
6. 锚点：List, *J. Am. Chem. Soc.* **2000**, 122, 9336–9337, DOI 10.1021/ja001923x `[已核实]`；Bahmanyar, Houk, Martin & List, *J. Am. Chem. Soc.* **2003**, 125, 2475（Mannich 选择性的量子力学预测）`[已核实，经多个引证来源]`。
7. 舒适区：{C,H,N,O}；TS ~21 重原子（**略超，标注**；可换甲醛亚胺变体降载）；闭壳层 ✓
8. 权威性：List 诺奖工作 + Houk 组定量 TS 分析。

### H-37 Hajos–Parrish 环化（proline-catalyzed intramolecular aldol desymmetrization）

1. 反应/底物：前手性三酮 2-甲基-2-(3-氧丁基)环戊烷-1,3-二酮 + (S)-脯氨酸 → 双环烯二酮（Wieland–Miescher 型），去对称化。
2. SMILES：`CC(=O)CCC1(C)C(=O)CCC1=O` + `O=C(O)[C@@H]1CCCN1` → 主产物（(S)-(+)-双环酮醇，绝对构型按文献核对）
3. 电荷/自旋：0 / 单重态
4. 条件：1–3 mol% (S)-脯氨酸，DMF/DMSO，室温。
5. gold 机理/选择性：去对称化分子内羟醛：烯胺进攻两个前手性羰基之一 → 93% ee（原始 Hajos–Parrish 数据，已优化至 >99%）；单脯氨酸 Houk–List TS。
6. 锚点：Hajos & Parrish, *J. Org. Chem.* **1974**, 39, 1615–1621 `[已核实]`；Hoang, Bahmanyar, Houk & List 2003, DOI 10.1021/ja028634o `[已核实]`；Bahmanyar & Houk, *J. Am. Chem. Soc.* **2001**, 123, 12911–12912, DOI 10.1021/ja011714s `[已核实]`。
7. 舒适区：{C,H,N,O}；TS ~21 重原子（**略超，标注**）；闭壳层 ✓
8. 权威性：有机催化的"创世纪"反应（1971/1974），去对称化立体选择性的原型。

### H-38 手性硫脲催化 Strecker 简化模型（thiourea-catalyzed Strecker, minimal chiral model）

1. 反应/底物：简化 Jacobsen 模型：(S)-N-甲基-N′-(仲丁基)硫脲催化 HCN 对 N-苄亚甲基甲胺的加成 → α-氨基腈。
2. SMILES：催化剂 `CC[C@H](C)NC(=S)NC`（(S)）+ 亚胺 `C/N=C/c1ccccc1` + `C#N` → 主产物：`CNC[C@H](C#N)c1ccccc1`（构型归属按 gold 核对）
3. 电荷/自旋：0 / 单重态
4. 条件：低温，甲苯（模型体系为计算对象）。
5. gold 机理/选择性：硫脲双氢键结合亚胺 N、酰胺 NH 定向 + 多重非共价作用稳定优势 TS（Zuend–Jacobsen 机理研究）；模型体系 ΔΔG‡ 预期 1–2 kcal/mol 量级。注意：催化剂为人工截短模型，gold 以"催化剂两个非对映 TS 竞争"形式出题，不直接对标实验 ee。
6. 锚点：Sigman & Jacobsen, *J. Am. Chem. Soc.* **1998**, 120, 4901–4902, DOI 10.1021/ja980139y `[已核实]`；Zuend & Jacobsen, *J. Am. Chem. Soc.* **2009**, 131, 15358–15374（TS 多重非共价作用机理）`[已核实，经 CORE 引证库]`。
7. 舒适区：{C,H,N,O,S}；TS 复合物 ~20 重原子；闭壳层 ✓（**含 S，标注**）
8. 权威性：氢键有机催化的奠基工作（Jacobsen 组），机理被 JACS 2009 大篇幅计算解析。

---

## 汇总表

| 组 | 选择性类型 | 候选编号 | 数量 |
|---|---|---|---|
| A | torquoselectivity / 电环化立体专一 | H-01–H-07 | 7 |
| B | Diels–Alder endo/exo、π-面、区域 | H-08–H-15 | 8 |
| C | [3+2] 面/区域/立体专一 | H-16–H-18 | 3 |
| D | 小环开环立体专属/区位翻转 | H-19–H-23 | 5 |
| E | 羰基 π-面 / CBS 手性还原 | H-24–H-26 | 3 |
| F | 氢键导向环氧化 | H-27–H-28 | 2 |
| G | [3,3]-σ 迁移椅/船竞争 | H-29–H-31 | 3 |
| H | 阻转异构消旋阻垒 | H-32–H-34 | 3 |
| I | 手性小分子/氢键催化诱导 | H-35–H-38 | 4 |
| **合计** | | | **38** |

## 入选权衡说明

- 纯 CHNO 候选：除 H-24/H-25（B）、H-26（B）、H-31（Si）、H-38（S）外全部满足；四个例外均可在 gold 构建阶段替换等效试剂（如 BH4− → 无金属氢化物模型）或直接接受（OMol25 覆盖 B/Si/S）。
- 重原子边界：H-32=20（恰界）、H-34=22、H-33=24（超，附降级建议）、H-36/H-37=21（略超，附降载建议）。
- 题面为 SMILES-only：所有底物均有程序化验证过的立体化学 SMILES；产物 SMILES 中标注"构型待 3D 核对"者（H-09、H-10、H-11、H-13、H-14、H-20、H-23、H-27、H-28、H-30、H-31、H-32、H-35、H-36、H-37、H-38）在 gold 构建时需以文献结构图/PubChem 3D 锚定。
