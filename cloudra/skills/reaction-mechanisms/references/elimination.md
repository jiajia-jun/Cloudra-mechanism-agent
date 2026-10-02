# 消除反应：机理可能性与建模

章节读取：同技能参考用 `get_skill(skill_name="reaction-mechanisms", reference="<文件名>.md")`；下文链接的通用计算参考用 `get_skill(skill_name="dft-calculation", reference="<文件名>.md")`。

范围：底物脱去两个相邻原子/基团形成 π 键（多为 C=C）的反应结果。覆盖碱诱导消除（E1/E2/E1cB）、分子内热消除（Ei：酯热解、Chugaev、Cope）与脱羧消除（β-酮酸等六元环 TS）。通用五问题框架见 [mechanism-elucidation-sop.md](../../dft-calculation/references/mechanism-elucidation-sop.md) 与 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md) §1（E2/E1cB 基线谓词已并入本文相应节；E1 与 SN1 共用的离子化步基线见 [substitution.md](substitution.md)）；与 SN1/SN2 的竞争判定参见 [substitution.md](substitution.md)。所有数值均为典型区间，随底物、碱强度、离去基团与溶剂漂移（Hammond / More O'Ferrall 可变 TS 模型），仅用于初猜与筛选，裁决靠频率 + IRC。

## 机理假设空间

| 变体 | 适用底物与条件 | 假设图骨架 | 判别特征（计算证据） |
| :--- | :--- | :--- | :--- |
| E2（反式共平面协同） | 强碱；1°–3° 卤代烃/磺酸酯/鎓盐 | R+Base → [络合物] → TS → 烯+Base-H+LG⁻（单边） | 无中间体；TS 同时满足 C–H 断与 C–LG 断的 partial bond；H–C–C–LG ≈ 180°；与 E1 判别：C–LG 扫描无独立离子化边 |
| E2-syn（顺式共平面） | 刚性体系（降冰片基、环上无反式 β-H） | 同上，但二面角 ≈ 0° | 与 anti-E2 共享骨架；一般高 3–8 kcal/mol（典型，待核实）；反式不可达时才建 |
| E1 | 弱碱/无碱，3° 底物，极性质子溶剂 | R → TS1（离子化）→ 碳正离子（+离子对）→ TS2（去质子）→ 烯 | 碳正离子中间体节点；决速步 TS1 中 β-C–H 键级仍≈1；与 SN1 共用 TS1（参见 substitution.md） |
| E1cB（可逆/不可逆） | β-C–H 酸性强（连 EWG：羰基、硝基、芴基等）且 LG 差（OH⁻、OR⁻、F⁻） | R+Base → TS1（夺氢）→ 碳负离子 → TS2（脱 LG）→ 烯 | 碳负离子中间体节点；TS1 中 C–LG 键级仍≈1；E1cB_R（夺氢可逆，TS2 决速）vs E1cB_irr（TS1 决速）由两 TS 相对 ΔG‡ 裁决 |
| Ei：酯热解 | 有 β-H 的羧酸酯，气相/高温（约 350–450 °C） | R → TS（六元环）→ 烯+羧酸（单步协同） | syn 消除：H–C–C–O ≈ 0°；O=C–O–C–C–H 六元环 TS；一级动力学（单分子，无碱节点） |
| Ei：Chugaev（黄原酸酯） | 醇的黄原酸酯（ROC(=S)SR′），约 120–250 °C | 同上，硫酮 S 作 H 受体 | 六元环 TS 中含 C=S；产物 COS+R′SH 稳定使反应不可逆；注意重排副边（见该节） |
| Ei：Cope 消除 | 叔胺 N-氧化物，温和加热（约 25–160 °C） | 同上，N⁺–O⁻ 的 O 作 H 受体 | **五元环** TS（O–N–C–C–H）；强 syn 要求；能垒显著低于酯热解 |
| 脱羧消除（β-酮酸/丙二酸类） | β 位有羰基（或第二个 COOH）的羧酸，加热 | 酸 → TS（六元环）→ CO₂+烯醇 →（互变异构）→ 酮 | 六元环 TS（O=C–C–C–O–H）；产物先是**烯醇**节点；无 β-羰基则此边不建（能垒通常 > 40 kcal/mol） |

## E2（反式共平面协同消除）

- 键变化：Cβ–H 断、Base–H 成、Cα–LG 断、Cα=Cβ 成。`watch_pairs`：Base–H、H–Cβ、Cα–LG、Cα–Cβ。首选扫描坐标：Base–H（缩短）或 Cα–LG（拉长）；两键耦合强，单扫一个通常够，异常时双坐标或 NEB。
- 预组织：σCβ–H 与 σ*Cα–LG 反式共平面重叠（anti-periplanar），H–C–C–LG 二面角 ≈ 180°；环己烷上即 trans-diaxial。**二面角写不进 `distance_filters`**：先用 Base···Hβ < 3.0 Å 筛近接构象，再用 `internal_coordinates` analyze 查二面角；两个 β-H 位点（Saytzeff/Hofmann）各筛一组。
- TS 期望：典型区间（Hammond 漂移明显）Cβ–H 1.2–1.5 Å、Base–H 1.3–1.9 Å、Cα–LG 1.9–2.6 Å（Cl/Br）、新生 C=C 1.36–1.40 Å。强碱/差 LG → TS 偏向碳负离子端（E1cB-like，C–H 断得多）；好 LG/弱碱 → 偏向碳正离子端（E1-like）。虚频模式应为 H 转移与 C–LG 伸缩耦合。
- 必须并建的竞争边：① Saytzeff vs Hofmann 取向各一条（ΔΔG‡ 定选择性，位阻碱/带电荷 LG 时 Hofmann 常赢）；② SN2/E2 竞争边（参见 substitution.md）；③ 刚性体系反式不可达时建 syn-E2 边；④ 入口离子-偶极/氢键络合物节点（双分子反应，ΔG‡ 的参考零点要一致，否则与 E1 比较失真）。
- 误诊信号：扫描全程单调且能垒为零 → 夺氢无垒，实际近 E1cB 边界或扩散控制；TS 上 Cα–LG Mayer 键级 ≈ 1 → 找的是纯夺氢 TS（E1cB 第一步），C–LG 没进坐标；IRC 产物端接出取代产物 → 扫的是 SN2 边。

## E1（单分子消除）

- 键变化：第一步 Cα–LG 异裂（决速）；第二步 Base（或溶剂）夺 β-H。`watch_pairs`：Cα–LG；第二步 Base–H、H–Cβ。扫描坐标：Cα–LG（拉长）。
- 预组织：无强几何要求；离子化需溶剂稳定，**隐式溶剂（SMD）几乎必需**；注意离子对 → 溶剂分离离子对可能给出多峰剖面。
- TS 期望：TS1 中 Cα–LG ≈ 2.2–2.8 Å，中心碳趋平面（→sp2，键角 →120°）；TS2 是晚 TS 之外的常规质子转移（见 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md) §3.1）。
- 必须并建的竞争边：① 碳正离子重排（1,2-H/烷基迁移，三元环状 TS）——有更稳定碳正离子可达时务必建；② SN1 边（共用 TS1，竞争在碳正离子分叉之后，参见 substitution.md）；③ 多个 β-H 位点去质子各一条边（E1 的 Saytzeff 选择性由 TS2 决定，不由底物构象决定）。
- 误诊信号：Cα–LG 扫描无峰、直接解离 → 溶剂化未建模或该底物离子化本无垒（换 E2/E1cB 假设）；IRC 从"离子化 TS"接回反应物但中心碳未平面化 → 初猜落在构象变化鞍点上。

## E1cB（碳负离子中间体）

- 键变化：第一步 Base 夺 β-H 成碳负离子（Cα–LG 不动）；第二步 Cα–LG 异裂。`watch_pairs`：第一步 Base–H、H–Cβ；第二步 Cα–LG、Cα–Cβ。
- 预组织：无共平面要求（逐步机理解除立体电子约束，这是与 E2 的关键判别点）；`distance_filters`：Base···Hβ < 3.0 Å。
- TS 期望：TS1 为常规质子转移（D–H···A 近线性，见 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md) §3.1）；TS2 为 C–LG 拉长至 2.0–2.6 Å（典型区间，随 LG 漂移）伴随碳负离子平面化。E1cB_R：TS2 > TS1（夺氢可逆）；E1cB_irr：TS1 ≥ TS2。
- 必须并建的竞争边：① E2 协同边——E1cB 与 E2 在 More O'Ferrall 面上是连续谱，碳负离子越稳定越靠边；两者都建让能垒裁决；② 碳负离子的其他出路（如对 EWG 的质子化返回，即氘代交换表现）。
- 误诊信号：第一步扫描后碳负离子优化不掉（塌回反应物）→ 该体系碳负离子不是极小点，改 E2 假设；中间体"碳负离子"中 Cα–LG 已自发断裂 → 实际是 E2 无中间体，假设图多建了一个节点。

## Ei：分子内顺式热消除（酯热解 / Chugaev / Cope）

三类共用骨架：受体原子 X（酯羰基 O、黄原酸酯硫酮 S、氧化胺 O）经环状 TS 夺 syn-β-H，同时 C–O（或 C–N）断裂成烯。**均为 syn 消除：H–C–C–Y ≈ 0°（Y = O 或 N）**，这是与碱诱导 anti-E2 的判别核心。

- 键变化：`watch_pairs`：X–H、H–Cβ、Cα–Y（Y=O/N）、Cα=Cβ。扫描坐标：X–H（缩短）或 Cα–Y（拉长）；环状协同步单坐标通常够。
- 预组织（`distance_filters` 直写）：
  - 酯热解（六元环 O=C–O–C–C–H）：羰基 O···Hβ < 2.5 Å；Cα–O 可拉长方向不受阻。
  - Chugaev（六元环 S=C–S–C–C–H）：硫酮 S···Hβ < 3.2 Å（S 更大，环更松）。
  - Cope（**五元环** O–N–C–C–H）：N-氧 O···Hβ < 2.5 Å；环更小，对 syn 共平面要求最苛刻。
  - 筛完务必用 `internal_coordinates` 查 H–C–C–Y 二面角 ≈ 0°（0–30° 可接受窗口，典型区间）。
- TS 期望（典型区间，随底物漂移）：X–H 1.2–1.6 Å、Cβ–H 1.2–1.5 Å、Cα–Y 1.8–2.4 Å。极性 TS（Xδ⁻···Hδ⁺），给电子烷基加速。近似能垒量级（气相/溶液，仅作可行性锚，非判据）：酯热解 ΔG‡ ≈ 40–48 kcal/mol（需 350–450 °C，计算研究支持六元环协同 TS）；Chugaev 更低（约 30–35，120–250 °C 可行，C=S 极性更强）；Cope 最低（约 20–30，室温至 160 °C，五元环预组织好）。具体数值随级别与底物显著漂移。
- 必须并建的竞争边：① 多个 syn-β-H 位点各一条（区域选择性，Ei 通常给 Hofmann 倾向的低取代烯，但仍以 ΔΔG‡ 裁决）；② Chugaev/碳酸酯热解的重排副边——MP2 研究显示多条竞争路径，部分给出醚/酮重排产物而非烯，产物分布异常时建边核对；③ 均裂边（高温下 C–O 均裂、自由基路径）在高温模拟时至少估算一次。
- 误诊信号：只能找到 anti 取向的 TS → 假设错了（Ei 必须 syn，回构象搜索找顺式构象；找不到顺式可及构象说明该底物不走 Ei）；五元/六元环数错（把 Cope 建成六元环或把酯热解建成四元 [1,3]-迁移）——芳基酯脱烯酮走四元环 [1,3]-H 迁移 TS，与烷基酯 Ei 是不同机理，别混用。

## 脱羧消除（β-酮酸、丙二酸类）

- 键变化：O–H（羧基）断、H···O（β-羰基氧）成、Cα–COOH 断、Cα=C（烯醇）成、CO₂ 中 C=O 重组。`watch_pairs`：O–H、H···O_keto、Cα–C(COOH)、Cα–C_keto。首选扫描坐标：Cα–C(COOH)（拉长）或 H···O_keto（缩短）。
- 预组织：分子内氢键把 COOH 的 H 递到 β-羰基氧上，形成六元环 O=C–C–C–O–H。`distance_filters`：O_keto···H(COOH) < 2.0 Å；筛后查 O=C–C–C 主链二面角使两端可闭环。丙二酸类第二个 COOH 的羰基氧充当受体，谓词同构。
- TS 期望：六元环状协同 TS（半椅式），典型区间：O–H 1.1–1.4 Å、H···O 1.2–1.6 Å、C–CO₂ 1.9–2.3 Å（Hammond 漂移）。能垒锚点：β-酮酸气相计算约 20–30 kcal/mol（甲酰乙酸报道 28.6 kcal/mol、其负离子 20.6 kcal/mol，**待核实**，随级别漂移）；无 β-受体时直接脱羧通常 > 40 kcal/mol，不要硬建。
- 必须并建的竞争边：① 产物是**烯醇节点**——后续酮-烯醇互变异构必须单独建边，直接 [1,3]-H 迁移 suprafacial 禁阻，真实路径为溶剂/酸碱介导穿梭（穿梭谓词见 [carbonyl.md](carbonyl.md) 加成-消除节与 reaction-class-geometry.md §3.1）；② 羧酸负离子路径（去质子后脱羧，能垒常更低，碱性/水相条件必建）；③ 若体系另有 β-H 与 LG，经典消除边（E1cB/E2）并行。
- 误诊信号：六元环 TS 优化塌缩成羧酸二聚体/氢键络合物 → 初猜的氢键取向错，先把反应物预组织成环内氢键构象再扫；IRC 产物端给出酮而非烯醇 → TS 连的是互变异构后的边，检查是否把两步并成了一步。

## 领域级陷阱

- **二面角谓词的盲区**：anti/syn 共平面是消除机理的判别核心，但 `distance_filters` 只能筛距离。统一做法：距离筛近接 → `internal_coordinates` 查二面角 → 不满足就换构象，不要在错误构象上硬扫（硬扫会得到滑谷或假 TS）。
- **双分子边的参考零点**：E2/E1cB 含碱，入口有氢键/离子-偶极络合物（常比分离反应物低 5–15 kcal/mol）。比较 E2 与 E1 的 ΔG‡ 时零点必须统一（分离反应物 or 各自络合物），否则机理裁决失真。
- **E2↔E1cB 是连续谱不是开关**：可变 TS（More O'Ferrall）意味着 TS 键级分布沿"碳负离子化程度"连续变化。判定靠是否存在碳负离子极小点（扫描谷 + 优化驻留），不要靠 TS 长得像不像。
- **环大小张冠李戴**：Ei 家族里 Cope=五元环、酯热解/Chugaev/脱羧=六元环、芳基酯脱烯酮=四元环 [1,3]-迁移。环数错 → TS 搜索必败或找到错误机理的鞍点。
- **选择性归因错误**：Saytzeff/Hofmann 由竞争 TS 的 ΔΔG‡ 决定，不是由产物烯烃相对能量决定（热力学烯稳定性只在晚 TS/平衡控制时近似成立）。两个取向的边都要算完再下结论。
- **高温机理的遗漏边**：Ei 与脱羧都在高温进行，均裂/自由基副路径（`electronic_analysis` spin≥2 检查）和重排边容易被漏建；实验产物分布对不上时优先补这些边。

## 参考来源

- Rzepa, H. S. "An orbital analysis of the stereochemistry of the E2 elimination reaction"（ωB97XD 计算 E2 TS 的轨道分析）, https://www.ch.ic.ac.uk/rzepa/blog/?p=6205
- Shojaei, S. H. R. et al. "Computational studies on thermo-kinetics aspects of pyrolysis of isopropyl acetate and its methyl, bromide and hydroxyl derivatives"（ωB97XD/M06-2X/CBS-QB3，酯热解六元环 TS）, 2022, https://pmc.ncbi.nlm.nih.gov/articles/PMC9626549/
- Zhu, X., Zhou, X., Zhang, W., Wu, P. "A Kinetic Isotope Effect Study of the Tschugaeff Reaction"（MP2/6-31G(d)，Chugaev/碳酸酯热解 12 条竞争路径与六元环 TS 决速）, https://www.researchgate.net/publication/237848850_A_KINETIC_ISOTOPE_EFFECT_STUDY_OF_THE_TSCHUGAEFF_REACTION
- Organic Chemistry Portal, "Cope Elimination"（五元环、6 电子、syn 协同）, https://www.organic-chemistry.org/namedreactions/cope-elimination.shtm
- More O'Ferrall, R. A. "Isotope Effect Studies on Elimination Reactions. XI"（E2/E1cB 可变 TS 连续谱模型，经典）, https://www.researchgate.net/publication/237856233
- Woon, D. E. 等关于甲酰乙酸脱羧能垒的报道（28.6 / 20.6 kcal/mol，经 Smolecule 综述转引，原始文献待核实）, https://www.smolecule.com/products/s776361
- Patai/Rappoport 体系气相消除 FT-ICR 研究（Van Berkel, de Koning, Nibbering："Temperature and pressure effects on the elimination reactions of diethyl ether with hydroxide and amide ions"，可变 E2 TS 的实验证据）, https://www.researchgate.net/publication/257575562
- Wu, Y.-D. 等 F⁻ + RY 的 E2/SN2 竞争 MP2 研究（anti-E2/syn-E2 与取代路径共享反应物络合物）, https://www.researchgate.net/publication/373480858
- "Potential for release of pulmonary toxic ketene from vaping pyrolysis of vitamin E acetate"（M06-2X：芳基酯脱烯酮为四元环 [1,3]-H 迁移 TS）, 2020, https://pmc.ncbi.nlm.nih.gov/articles/PMC7104367/
- Clayden, Greeves, Warren, *Organic Chemistry* 2nd ed., ch. 19（E2 反式共平面、Saytzeff/Hofmann，教材级共识；节录见 https://mail.almerja.net/more.php?idm=264835）
