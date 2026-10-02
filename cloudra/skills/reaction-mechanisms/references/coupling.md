# 过渡金属催化偶联：机理可能性与建模

章节读取：同技能参考用 `get_skill(skill_name="reaction-mechanisms", reference="<文件名>.md")`；下文链接的通用计算参考用 `get_skill(skill_name="dft-calculation", reference="<文件名>.md")`。

范围界定：Pd/Ni 催化的 C–C（与 C–杂原子）偶联——经典交叉偶联（Suzuki/Stille/Negishi/Kumada 等，氧化加成–转金属–还原消除循环）、Heck 烯基化、烯烃复分解、C–H 活化偶联。假设生成与 TS 验证的通用流程见 [mechanism-elucidation-sop.md](../../dft-calculation/references/mechanism-elucidation-sop.md)，五问题框架见 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md)；本文只补充金属有机循环特有的机理变体与几何谓词。所有数值为典型区间，随底物、配体、金属与溶剂漂移（Hammond），**不是硬判据**。

## 机理假设空间

| 变体 | 适用底物与条件 | 假设图骨架（节点→边） | 判别特征（计算证据） |
| :--- | :--- | :--- | :--- |
| Pd(0)/Pd(II) 经典循环 | 芳基/烯基卤（拟卤）+ 有机金属试剂（B/Sn/Zn/Mg），膦/NHC 配体，常需碱 | LnPd(0) →[氧化加成] LnPd(II)(R)(X) →[转金属] LnPd(II)(R)(R') →[还原消除] 产物 + LnPd(0) | 三步均为闭壳层单重态；各步 TS 可独立定位；Mayer 键级显示部分 M–C/M–X 键（`electronic_analysis` spin=1） |
| Ni(0)/Ni(II) 双电子循环 | Ni/膦体系，同 Pd 的经典图 | 同上，金属换 Ni | 闭壳层；但 Ni 更亲氧、β-H 消除竞争更强（Heck 型副边必须建） |
| Ni(I)/Ni(III) 单电子/自由基链 | Ni/NHC、pincer、双氮配体；交叉亲电偶联（XEC）、光氧化还原双催化、Mn/Zn 还原剂 | Ni(I) →[捕获自由基/SET] Ni(III)(R)(R') →[还原消除] 产物 + Ni(I)；侧挂烷基自由基节点 | 必须开壳层计算（spin≥2，UKS）：Ni(I) d9 二重态、Ni(III) d7；自旋布居在烷基碳与 Ni 间的迁移是核心证据；自由基钟/捕获实验对应"自由基中间体"节点 |
| Heck 循环 | 芳基/烯基卤 + 烯烃，碱，Pd(0)（阳离子或中性路径） | Pd(0) →[OA] ArPd(II)X →[烯烃配位+迁移插入] σ-烷基 Pd(II) →[β-H 消除] 烯基产物 + HPd(II)X →[碱辅助还原消除/脱 HX] Pd(0) | 无转金属步；决速常在迁移插入；β-H 消除要求 syn-coplanar 与空顺式配位点——查中间体是否存在 agostic 结构 |
| 烯烃复分解（Chauvin） | Ru 卡宾（Grubbs/Hoveyda）或 Mo/W 卡宾 + 烯烃 | M=CHR →[烯烃配位] π-络合物 →[[2+2] 环加成] 金属环丁烷 →[环逆转] 新 M=CHR' + 新烯烃 | 金属环丁烷中间体是标志性节点（可用 `ts_guess` interpolate 端点建模）；产物/非生产性环逆转互为竞争边 |
| C–H 活化偶联（CMD） | 导向基团定位的芳烃/烷烃 C–H，Pd(II)/Ru(II)/Ir(III) 等 + 羧酸盐/碳酸盐碱 | LnM(II)(OAc) →[底物配位] →[CMD 六元环 TS] 环金属化 M(II) →[与偶联伙伴 OA/转金属/插入…] 产物 | C–H 断裂不经氧化加成、金属价态不变（判别：CMD TS 中金属配位数与 d 电子计数不变；C–H 的 H 被羧酸根氧接住）；KIE>2 时 CMD 常为决速 |

## Pd(0)/Pd(II) 交叉偶联：氧化加成

- **Q1 键变化**：C–X 断、Pd–C 与 Pd–X 成。`watch_pairs` = (C, X), (Pd, C), (Pd, X)。首选扫描坐标：C–X（拉长）；协同三元环 TS 中 Pd···C 与 Pd···X 同步缩短，必要时双坐标。
- **Q2 预组织**：底物 C–X 需接近金属中心。`distance_filters`：Pd···C ≈ 2.5–3.5 且 Pd···X ≈ 2.8–3.8（预反应 π/σ 络合物区间，典型值，随 X 漂移）。
- **Q3 TS 期望**：协同三元环 TS（C–X–Pd 近似共面）；C–X 在 TS 典型拉长至 2.0–2.6（Ar–I 更长、Ar–Cl 更短，Hammond：富电金属/弱 C–X → 早 TS）。能垒典型 5–20 kcal/mol（Ar–I 低、Ar–Cl 高，随配体漂移，待核实下限）。单配位 L1Pd 通常比 L2Pd 活性高——**配体解离边必须单独建模**（解离能 15–30 kcal/mol 量级，典型值）。
- **Q4 竞争边**：(a) 协同 OA vs 对 sp3 烷基卤的 SN2 型背面 OA（后者 Pd–C–X 角 ≈ 180，产物构型翻转）；(b) L1 vs L2 配位数路径；(c) 卤素桥双核 OA（二聚 Pd 前体时）；(d) 对烷基卤的 SET/自由基 OA（接入 Ni 单电子变体的判别框架）。
- **Q5 误诊信号**：扫描单调下坡→OA 无垒（络合后直接异裂，该边改记为扩散控制）；TS 上 Pd–C Mayer 键级 <0.1→真实路径是解离型或 SN2 型；产物侧 IRC 落到 trans 构型而后续还原消除需要 cis——提示中间插入了顺反异构边。

## 转金属（transmetalation）

- **Q1 键变化**：R'–M'（M'=B/Sn/Zn）断、Pd–R' 成、Pd–X（或 Pd–O）断、M'–X 成。`watch_pairs` = (Pd, R'α碳), (R'α碳, M'), (Pd, X), (M', X)。扫描坐标：Pd–C(R')（缩短）或 M'–C（拉长）。
- **Q2 预组织**：Suzuki 需先形成桥联预络合物。`distance_filters`：Pd···O(硼酸根) ≈ 2.0–2.5 且 B···C(R') 成键端靠近 Pd：Pd···C(R') ≈ 2.8–3.5（典型区间）。
- **Q3 TS 期望**：四元环状 TS（Pd–O–B–C 排列，boronate 路径）；新 Pd–C 与旧 B–C 在 TS 均部分成键（Mayer 键级 0.2–0.6，典型值）。两条竞争子路径：**boronate 路径**（碱先活化硼 → ArB(OH)3− 进攻 Pd–X）vs **oxo-Pd 路径**（碱先置换 X 得 Pd–OH，再与中性硼酸转金属）——并建，能垒裁决（文献共识：硼酸酯路径常占优，随碱与底物漂移）。
- **Q4 竞争边**：boronate vs oxo-Pd；cis/trans 异构的转金属前体；Stille 的开放（associative，五配位）vs 环状（cyclic）TS；Negishi/Kumada 无碱时的直接四中心 TS。
- **Q5 误诊信号**：四元环 TS 找不到/能垒 >35 kcal/mol→换另一条子路径或检查碱是否显式建模（只写"base"不建模分子是常见漏项）；转金属中间体 Pd–C 键级接近 0→预络合物构型错，回 `conformer_search` 补桥联构象。

## 还原消除

- **Q1 键变化**：Pd–R 与 Pd–R' 断、R–R' 成。`watch_pairs` = (Pd, Rα), (Pd, R'α), (Rα, R'α)。扫描坐标：Rα–R'α（缩短）最稳健。
- **Q2 预组织**：两个 R 基团必须 **cis** 顺式相邻。trans 中间体需先建"trans→cis 异构化"边（可经由膦解离-再结合或伪旋转，能垒典型 5–15 kcal/mol，随配体漂移）。`distance_filters`：Rα···R'α ≈ 2.4–3.2 且 Rα–Pd–R'α 角 ≈ 75–105。
- **Q3 TS 期望**：三元环 TS，forming C–C 典型 2.0–2.4（Hammond：消除多放热 → 早 TS，键更长）。能垒通常较低（典型 5–15 kcal/mol），C–F、C–CN 消除显著更高（>25，待核实上限）。双齿大咬角配体加速消除。
- **Q4 竞争边**：cis 位还原消除 vs β-H 消除（烷基 Pd(II) 有 β-H 时必建，Heck 型副反应）；三配位 vs 四配位消除；Pd(IV) 路径（强氧化剂/高价试剂时，接入下述高价变体）。
- **Q5 误诊信号**：TS 优化塌缩成 trans 中间体→初猜来自 trans 构象，回 `conformer_search` 取 cis reactive conformer；forming 键 Mayer 键级 <0.1 且两 Pd–C 键级仍接近 1→扫描坐标选错（误扫 Pd–C）。

## Ni 变体：Ni(0)/Ni(II) vs Ni(I)/Ni(III)

- **框架差异**：膦配体 Ni 体系多按 Ni(0)/Ni(II) 双电子建模（各节直接沿用 Pd 条目）；NHC/pincer/联吡啶 + 交叉亲电偶联、光氧化还原、化学还原剂（Mn/Zn）体系**必须并建 Ni(I)/Ni(III) 单电子假设图**：Ni(II) 被还原为 Ni(I) → 捕获烷基自由基生成 Ni(III) → 还原消除回 Ni(I)。
- **Q1 键变化**：关键边 = Ni(I)–C(sp3) 成键（自由基捕获）。`watch_pairs` = (Ni, C自由基)。自由基本身作为独立节点（`electronic_analysis` spin=2 确认自旋布居在碳上）。
- **Q2 预组织**：自由基捕获对几何要求宽松（扩散控制常无垒）；若扫描单调下坡则该步记为扩散控制，决速上移至 SET 或消除。
- **Q3 TS 期望**：Ni(III) 还原消除能垒通常比同构 Pd(II) 低（典型 5–12 kcal/mol，随配体漂移，待核实）；Ni(I) 为 d9 二重态、Ni(III) d7——全部 spin≥2 计算，检查 `<S²>`。
- **Q4 竞争边**：双电子 vs 单电子两条总循环并建（用"烷基自由基节点是否能量可达"裁决）；自由基笼外逃逸/重组（ radical clock 对应外消旋化边）；Ni(II) 直接 OA vs Ni(I) 先捕获。
- **Q5 误诊信号**：闭壳层单重态下优化出的"Ni(I)"结构电荷/键级不合理→漏了自旋态；自旋布居显示自由基特征却 `<S²>` 严重偏离→自旋污染，见 SOP 决策表；单电子路径全垒低于双电子但实验无自由基钟信号→核对还原剂建模是否显式。

## Heck 循环（迁移插入–β-H 消除）

- **Q1 键变化**：迁移插入 = Pd–C(aryl) 断（形式迁移）、C(aryl)–Cα 成、Pd–Cβ 成；`watch_pairs` = (C_aryl, Cα), (Pd, Cβ), (Cα, Cβ)。β-H 消除 = Cβ–H 断、Pd–H 成、Cα=Cβ 重建；`watch_pairs` = (Cβ, Hβ), (Pd, Hβ)。扫描坐标分别取 C_aryl–Cα（缩短）与 Cβ–Hβ（拉长）。
- **Q2 预组织**：插入要求烯烃与 Pd–R **顺式共平面**（四中心 syn 插入）：`distance_filters`：Pd···Cα ≈ 2.5–3.2、Pd···Cβ ≈ 2.5–3.2，二面角 C_aryl–Pd–Cα–Cβ ≈ 0。β-H 消除要求 **syn-coplanar** 且 β-C–H 能转到 Pd 顺式空位：Pd···Hβ ≈ 1.8–2.4（agostic 预组织）、二面角 Pd–Cα–Cβ–Hβ ≈ 0；若中间体无 agostic 构象，先构象搜索旋转 Cα–Cβ。
- **Q3 TS 期望**：插入 TS 四元环状、Pd–Cβ forming 典型 2.0–2.3、C_aryl–Cα forming 典型 2.0–2.4（典型区间，阳离子 Pd 路径 TS 更早）。β-H 消除 TS 中 Cβ–Hβ 拉长至 1.2–1.4、Pd–Hβ 缩短至 1.6–1.9（典型值）。中性 vs 阳离子路径（X 是否解离）是两组不同的 TS，配位数不同。
- **Q4 竞争边**：区域选择性（Markovnikov vs anti-Markovnikov 插入两条边，决定直链/支链产物）；中性 vs 阳离子路径；β-H 消除后再插入（链行走/异构化边）；E/Z 烯烃产物几何各一条边。
- **Q5 误诊信号**：插入 TS 中烯烃与 Pd–R 二面角 >30→syn 共面未满足，回构象；β-H 消除找不到 TS→检查是否存在顺式空配位点（双齿配体螯合时该步被禁，提示机理改走碱辅助脱质子或转金属终止）；IRC 接到 Pd–H 与内烯烃 → 链行走已发生，补异构化节点。

## 烯烃复分解（Chauvin 金属卡宾循环）

- **Q1 键变化**：[2+2] 环加成 = M=C 与 C=C 各断一根 π、M–C 与 C–C 各成一根 σ；`watch_pairs` = (M, C_卡宾), (M, C_烯近端), (C_卡宾, C_烯远端), (Cα, Cβ 烯烃)。环逆转为镜像。扫描坐标：C_卡宾–C_烯远端（缩短）。
- **Q2 预组织**：烯烃需 η2 配位于 M=C 键侧面、`C=C` 与 `M=C` 近似平行接近。`distance_filters`：M···两烯烃碳均 ≈ 2.4–3.0，且 C_卡宾···C_烯远端 ≈ 2.4–3.2。Grubbs 体系需先膦解离生成 14e 活性卡宾——**解离边单独建模**（典型 15–25 kcal/mol，含熵效应，温度敏感）。
- **Q3 TS 期望**：[2+2] TS 为近似平面四中心（M–C–C–C），forming M–C 与 C–C 典型 2.0–2.3（典型区间，Hammond：卡宾越亲电 TS 越早）。金属环丁烷中间体为浅阱，环加成/环逆转能垒典型 5–15 kcal/mol（随 Ru vs Mo/W、取代基漂移）。两 forming 键长差 >0.3 提示异步 TS（判读参见 [pericyclic.md](pericyclic.md) 协同与异步 Diels–Alder 节的同步性判据）。
- **Q4 竞争边**：生产性 vs 非生产性环逆转（金属环丁烷两个开裂方向，端点互换即得）；E/Z 烯烃产物各一条边；底物进攻卡宾的两种取向（决定 RCM/交叉复分解区域与立体化学）；引发步（膦解离）vs 链增长步的决速竞争。
- **Q5 误诊信号**：金属环丁烷优化塌缩回 π-络合物→初猜中 forming 键过长或取向非平行，回 `conformer_search` 补 η2 构象；找不到 [2+2] 协同 TS 却找到分步双自由基路径→检查自旋态（Ru 卡宾通常为闭壳层，出现强双自由基特征时单参考结论打折）；E/Z 选择性算反→确认比较的是环逆转而非环加成的 ΔΔG‡。

## C–H 活化偶联（CMD，concerted metalation–deprotonation）

- **Q1 键变化**：C–H 断、M–C 成、羧酸根 O–H 成、M–O(羧酸根) 部分断（κ2→κ1 或全断）。`watch_pairs` = (C, H), (O_acetate, H), (M, C), (M, O)。首选扫描坐标：C–H（拉长）；六元环耦合强时改扫 O–H（缩短）。
- **Q2 预组织**：导向基团配位固定底物，羧酸根必须处于可接 H 的位置。`distance_filters`：M···C ≈ 2.4–3.0 且 O_acetate···H ≈ 1.6–2.4；六元环预折叠（M–O···H–C 近似共面）。无导向基团时先建底物 π-络合物节点（芳烃 η2 配位，M···C ≈ 2.2–2.5）。
- **Q3 TS 期望**：**六元环状 TS**（M–O–C(carboxyl)–O···H–C 成环）；C–H 拉长至典型 1.2–1.4、O–H forming 1.2–1.5、M–C forming 2.1–2.4（典型区间，随金属与碱漂移）。能垒典型 15–30 kcal/mol（sp2 低于 sp3；强碱/亲电金属更低）。CMD/AMLA 为同族机理不同命名，建模相同。
- **Q4 竞争边**：CMD vs 氧化加成 C–H（金属变价 +2，低氧化态富电金属时）vs σ-键复分解（d0 金属）；内碱（配位羧酸根）vs 外碱（游离碳酸盐，需显式建模碱分子）；多个 C–H 位点各一条边（区域选择性）；C–H 活化后接 OA/转金属/迁移插入的下一段循环（接到上面相应条目）。
- **Q5 误诊信号**：扫描 O–H 单调、扫 C–H 有峰但 TS 中 O···H >2.0→碱没进配位层，预组织失败；KIE 实验 >2 而算得 CMD 垒远低于后续步→决速步归属矛盾，核对是否漏了配体解离/底物配位前平衡；找到"OA 型"C–H TS 但金属价态不合理（如 Pd(II)→Pd(IV) 垒 >35）→该边剪枝，回 CMD。

## 领域级陷阱

1. **配位数与配体解离被当成黑箱**：L2→L1 解离、X 解离（中性/阳离子路径切换）往往是隐含决速步；每个循环边都要显式写出配位数的节点，解离能用热化学校正后的 ΔG（熵贡献大，单电子能会系统性低估）。
2. **碱/抗衡离子不显式建模**：转金属与 CMD 的碱是结构参与者（进四元/六元环 TS），只加隐式溶剂不建碱分子会得到假高垒或找不到 TS。
3. **泛函依赖性大**：3d/4d 金属成键与能垒对泛函敏感——基准研究显示 M06 对 Ni/Pd 键活化能垒表现最好之一、双杂化（B2PLYP）对反应能量好（Steinmetz 2013）；至少用两个泛函（如 M06 与 ωB97X-D）复算决速步单点，加色散校正（D3）；Pd 用相对论 ECP 基组（def2/SDD），几何与频率同基组、单点升级（SOP §5）。
4. **多参考与自旋污染**：Ni(I)/Ni(III)、3d 金属、双核物种有近简并风险；`⟨S²⟩` 偏差 ≳0.1 或 T1 诊断偏大（>0.02 量级，经验阈值，待核实）时，按 [method-selection.md](../../dft-calculation/references/method-selection.md) 将单参考 DFT 能垒只作定性证据并标注不确定性；必要时换泛函/开壳层单重态（`guess=mix`）交叉验证。
5. **trans 中间体直接拿去扫还原消除**：还原消除只能 cis，漏建顺反异构边会假性否决整条循环；同样，β-H 消除漏建顺式空位/agostic 预组织会找不到 TS。
6. **把单电子边当闭壳层算**：XEC/光氧化还原/Ni 自由基链在闭壳层下可能给出看似合理实则错误的中间体；假设图含 SET/自由基节点时全路径 spin≥2 重算并核对自旋布居迁移。

## 参考来源

- García-Melchor, M. et al. "Computational Perspective on Pd-Catalyzed C–C Cross-Coupling Reaction Mechanisms", *Acc. Chem. Res.* 2013. https://pubmed.ncbi.nlm.nih.gov/23848308/
- D'Alterio, M. C. et al. "Mechanistic Aspects of the Palladium-Catalyzed Suzuki–Miyaura Cross-Coupling Reaction", *Chem. Eur. J.* 2021. https://chemistry-europe.onlinelibrary.wiley.com/doi/10.1002/chem.202101880
- Jover, J. et al. "A computational study of phosphine ligand effects in Suzuki–Miyaura coupling". https://www.sciencedirect.com/science/article/abs/pii/S1381116910000725
- "Mechanisms of nickel-catalyzed reductive cross-coupling reactions"（综述，Ni0/NiII/NiIII 与自由基链）. https://www.oaepublish.com/articles/cs.2023.20
- Steinmetz, M., Grimme, S. "Benchmark Study of the Performance of DFT for Bond Activations with (Ni,Pd)-Based Transition-Metal Catalysts", 2013. https://pmc.ncbi.nlm.nih.gov/articles/PMC3703816/
- "Understanding the effect of ancillary ligands on concerted metalation-deprotonation"（CMD 六元环 TS 的 DFT 研究）. https://experts.umn.edu/en/publications/understanding-the-effect-of-ancillary-ligands-on-concerted-metala/
- Sanford, M. S., Ulman, M., Grubbs, R. H. "New Insights into the Mechanism of Ruthenium-Catalyzed Olefin Metathesis Reactions", *JACS* 2001. https://doi.org/10.1021/ja003582t（及 Grubbs 催化剂机理综述，14e 活性物种与金属环丁烷）
- "Heck-Type Reactions of Imine Derivatives: A DFT Study"（Heck 四步循环：OA–迁移插入–β-H 消除–再生）. https://aces.onlinelibrary.wiley.com/doi/10.1002/asia.200900744
- "Oligothiophene Synthesis by a General C–H Activation Mechanism: Electrophilic CMD (eCMD)". https://pmc.ncbi.nlm.nih.gov/articles/PMC7377630/
