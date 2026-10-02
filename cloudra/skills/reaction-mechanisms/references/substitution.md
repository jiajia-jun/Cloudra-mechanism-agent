# 取代反应（饱和碳与芳香体系）：机理可能性与建模

章节读取：同技能参考用 `get_skill(skill_name="reaction-mechanisms", reference="<文件名>.md")`；下文链接的通用计算参考用 `get_skill(skill_name="dft-calculation", reference="<文件名>.md")`。

范围界定：本文件覆盖"一个原子/基团被另一个原子/基团替换"这一反应结果——脂肪族碳上的 SN1/SN2、芳环上的亲电取代（SEAr）、芳香亲核取代（SNAr 三变体）、以及饱和碳上的自由基链式取代。净取代结果 ≠ 净机理：同样的"X 换成 Nu"可能走协同双分子、逐步离子对、σ 络合物、芳炔或自由基链路径，假设图必须全部枚举后由计算证据裁决。与消除（E1/E2/E1cB）的竞争细节参见 [elimination.md](elimination.md)；自由基通性（开壳层设置、`<S^2>` 判据）参见 [radical.md](radical.md)。五问题框架见 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md) §1；SN2/SN1 基线谓词已并入本文相应节，此处只补充本领域特有的判别特征与陷阱。

## 机理假设空间

| 变体 | 适用底物与条件 | 假设图骨架（节点→边） | 判别特征（裁决证据） |
| :--- | :--- | :--- | :--- |
| SN2 协同 | 伯/仲碳，好 LG，强 Nu，极性非质子溶剂 | R–LG + Nu → [TS] → R–Nu + LG | 单 TS 无中间体；IRC 两端构型翻转；虚频 = Nu···C···LG 反对称伸缩 |
| SN1（离子对） | 叔/苄/烯丙位碳，差 Nu，极性质子溶剂 | R–LG → 紧密离子对 → 溶剂分离离子对 → R–Nu | 剖面多极小点；决速 C–LG 断裂；产物消旋化/重排 |
| SEAr 经典两步 | 富电子芳烃 + 亲电体（硝化、卤化、Friedel–Crafts） | ArH + E+ → arenium σ 络合物 → 去质子 → ArE | σ 络合物为真实极小点；第一步决速时通常无一级 KIE |
| SEAr 协同/加成-消除变体 | 非极性介质中部分卤化（如苯甲醚氯化） | 单 TS 直接取代；或先加成得环己二烯基加合物再消除 | 沿全坐标扫描找不到 σ 络合物极小点即协同 |
| SNAr 加成-消除（逐步） | 强吸电子基（NO2、CN、杂芳环 N）ortho/para 定位 | ArX + Nu → Meisenheimer σ 络合物 → 脱 LG → ArNu | MC 为真实极小点；两个 TS；负电荷局域在 EWG 上 |
| SNAr 协同 | 弱活化芳环、多数常规 SNAr（2018 后共识：多数协同） | ArX + Nu → [单 TS] → ArNu | 全坐标无 MC 极小点；F 仍是最佳 LG（元素效应反常） |
| SNAr 消除-加成（苯炔） | 未活化卤代芳烃 + 极强碱（NaNH2/NH3） | ArX → 脱 HX → 芳炔 → Nu 加成 → 质子化 → ArNu | 产物出现 cine（重排）取代；芳炔节点弯角三键 |
| SNAr SRN1 | 未活化芳卤 + 可 SET 体系（光、溶剂化电子、烯醇盐） | SET → [ArX]·− → 碎裂 → Ar· → 加 Nu− → [ArNu]·− → 链转移 | 对光/自由基捕获剂敏感；各节点 spin=2；无 σ 络合物 |
| 饱和碳自由基取代 | 烷烃卤化、HAT/XAT 链 | R–H → HAT → R· → 夺卤/SH2 → R–X | 链式；spin=2；立体中心消旋（平面自由基）；细节参见 [radical.md](radical.md) |

## SN2（双分子协同）

- 键变化：Nu–C 成、C–LG 断。`watch_pairs` = (Nu, Cα), (Cα, LG)；首选扫描坐标 Nu–Cα（缩短）或 Cα–LG（拉长），二者强耦合单扫即可。
- 预组织：`distance_filters` 取 Nu–Cα < 3.5 Å 且 Nu–Cα–LG 角 > 160°（n_Nu→σ*C–LG 反式对齐）；分子内 SN2（关环）另按 Baldwin 规则预筛环尺寸。
- TS 期望：近似三角双锥五配位碳，三个旁观取代基近似共平面（典型 C–Cα–C 角约 115–125°）；Nu–Cα 与 Cα–LG 均约 2.0–2.5 Å（典型区间，随 Nu 亲核性与 LG 离去能力漂移——Hammond：强 Nu/好 LG → 早 TS、两键更长）。ΔG‡ 典型 15–30 kcal/mol（待核实，强溶剂依赖）。
- 必须并建的竞争边：E2 消除（构象满足反式共平面时必建，参见 [elimination.md](elimination.md)）；SN1 解离边（叔/苄位底物）；邻基参与（邻位有孤对基团时，分子内先关环再开环，净结果是两次翻转 = 构型保持——漏建这条边会把"保持"产物误判为机理错误）。
- 假设剪枝：叔碳底物不要建 SN2 边（位阻 + 碳正离子稳定性使 SN1/E1 主导）。
- 误诊信号：IRC 端点构型未翻转 → 接错边或实际为双翻转（邻基参与）；扫描中出现中间极小点 → 可能是 frontside 络合物/离子-偶极络合物（正常，作 pre-reactive complex 处理）或 SN1 离子对（重新归类）；叔碳底物上"找到"的 SN2 TS ΔG‡ 反而低于解离路径 → 多半坐标/溶剂模型有误，核查 SMD 设置。

## SN1（单分子，离子对）

- 键变化：Cα–LG 异裂（决速），随后 Nu–C 成键。`watch_pairs` = (Cα, LG)；扫描坐标 Cα–LG 拉长。
- 预组织：无亲核体取向要求；关键是溶剂稳定化——隐式溶剂（SMD）几乎必需，气相 SN1 剖面严重失真。`distance_filters` 可不设，或仅用 Cα–LG < 3.0 Å 排除已解离构象。
- TS 期望：Cα–LG 约 2.2–2.8 Å（典型区间，随 LG 与溶剂漂移——Hammond：溶剂极性越大 TS 越早）；中心碳趋于平面（三个旁观键角 → 约 120°）。
- 必须并建的竞争边：碳正离子重排（1,2-H / 1,2-烷基迁移，三元环状 TS）——只要迁移能得到更稳定碳正离子就必须建；E1（同一碳正离子脱 β-H，参见 [elimination.md](elimination.md)）；紧密离子对的"内部返回"（internal return，离子对重组回起始物，使表观速率与立体化学失真）。
- 误诊信号：扫描剖面无清晰峰而是平台/单调升 → 该体系在所用溶剂模型下无解离势垒，机理实为 SN2 或"SN1/SN2 连续体"中间态（糖基化等体系 AIMD 已证实连续体存在，勿强行二选一）；算得碳正离子极小点但 IRC 找不到 Nu 捕获的 TS → Nu 捕获是扩散控制无垒步，报告碳正离子 + Nu 相遇络合物能量即可，不要硬造 TS。

## SEAr（芳香亲电取代，arenium / σ 络合物机理）

- 键变化：第一步 C(aryl)–E 成键（决速，破坏芳香性）；第二步 C(aryl)–H 断、去质子恢复芳香性。`watch_pairs` = (C_ipso, E), (C_ipso, H)；首选扫描坐标 C–E 缩短。
- 预组织：亲电体位于目标碳正上方附近，`distance_filters` 取 C–E < 3.0 Å；Lewis 酸催化（FeCl3/AlCl3）时必须把催化剂-亲电体络合物作为反应物节点一并建模，裸 Cl2/Br2 的能垒会系统性高估（待核实，催化剂络合降低亲电体生成能）。
- TS 期望：加成 TS 中 C–E 约 1.9–2.4 Å（典型区间，随亲电体活性漂移——Hammond：亲电体越强（如 NO2+）TS 越早、键更长）；被进攻碳开始 sp3 化、翘起出环平面。σ 络合物极小点：C–E 约 1.5–1.7 Å，该碳 sp3（环内键角约 110–115°），正电荷离域于 ortho/para 位（`electronic_analysis` 电荷应见此分布，否则结构可疑）。
- 必须并建的竞争边：每个可进攻位点一条边（ortho/meta/para，ΔΔG‡ 定区域选择性）；ipso 进攻（在已有取代基位点上加成，可能通向取代基迁移/脱除副产物）；协同 SEAr 变体（苯甲醚 + Cl2/CCl4 体系计算表明 arenium 离子非必经，可为单 TS 协同或加成-消除——不要预设两步）；去质子的介导路径（碱/溶剂穿梭，直接分子内 [1,2]-H 迁移对称性禁阻且高垒，勿建）。
- 误诊信号：沿 C–E 扫描全程找不到 σ 络合物极小点 → 该体系是协同 SEAr（单 TS），把两步假设改为一条边；第一步 TS 的 ΔG‡ 异常低（< 10 kcal/mol）而实验慢 → 检查是否漏建模 Lewis 酸络合或溶剂；出现显著一级 KIE 需求（氘代速率变慢）→ 去质子步部分决速，把去质子 TS 一并纳入能量剖面（磺化、部分碘化属此类，第一步可逆）。

## SNAr 加成-消除 vs 协同

- 键变化：两种假设的键变化相同——Nu–C_ipso 成、C_ipso–LG 断；区别只在中间有无 Meisenheimer 络合物（MC）极小点。`watch_pairs` = (Nu, C_ipso), (C_ipso, LG)；扫描坐标 Nu–C_ipso 缩短（能同时穿越加成与消除区，剖面双峰 = 逐步、单峰 = 协同）。
- 预组织：`distance_filters` 取 Nu–C_ipso < 3.2 Å；进攻方向近似垂直于芳环平面（沿 p 轨道），Nu 与环平面法线夹角 < 约 30°（待核实，定性谓词用 Nu 到环平面距离 > Nu 到环心的面内偏移即可）。
- TS 期望：协同 TS 中 Nu–C 约 1.9–2.3 Å、C–LG 约 1.8–2.5 Å（典型区间，随底物漂移——Hammond：环越缺电子 TS 越早）；MC 极小点中 C_ipso sp3 化，Nu–C 与 C–LG 均约 1.45–1.85 Å。边界判据（Rohrbach/Tuttle）：MC 相对反应物越稳定（强 EWG、差 LG）越倾向逐步；Marcus 型论证——MC 能量高于两端则协同。
- 必须并建的竞争边：逐步与协同永远并建（一次扫描即可同判）；多位点进攻边；胺类 Nu 时碱催化去质子边（第二分子胺/溶剂穿梭六元环 TS）。
- 误诊信号：**元素效应反常是最强指纹**——SNAr（尤其协同）中 LG 离去能力 F > Cl ≈ Br > I（加成决速、C–F 键极性助攻），若假设 SN2 式边却算得 F 体系能垒最低，机理归类没错但解释要按 SNAr；MC 在 TS 优化中塌缩 → 它本就不是极小点（"hidden intermediate"），改协同单 TS；杂芳环（吡啶/嘧啶）体系不要漏环氮对位点的活化排序。

## SNAr 消除-加成（经苯炔）

- 键变化：第一步脱 HX 成芳炔（C–H 与 C–LG 同步断裂，碱夺 H）；第二步 Nu 对三键加成生成芳基负离子；第三步质子化。`watch_pairs` 第一步 = (Base, H), (C, LG)；第二步 = (Nu, C1), (Nu, C2)（两个三键碳都要盯）。
- 预组织：LG 的 ortho 位必须有 H——没有 ortho-H 的底物直接剪掉此边；碱与 ortho-H 预接近（`distance_filters`：Base–H < 2.5 Å）。
- TS/中间体期望：苯炔三键约 1.24–1.28 Å、C–C≡C 弯角约 125–135°（典型值，待核实随取代基漂移）；张力能约 45–50 kcal/mol（待核实）意味着生成步 ΔG‡ 通常较高（约 25–35 kcal/mol，强碱条件，典型区间），这是该机理只在极强碱下出现的原因。加成 TS：Nu–C 约 1.9–2.4 Å。
- 必须并建的竞争边：Nu 对芳炔两个碳各一条加成边——区域选择性由 aryne distortion model 裁决（进攻畸变更平坦、线性度更好的那个三键碳，而非位阻更小者；Garg/Houk 模型）；3-取代芳炔的两个取向都建。
- 误诊信号：产物连接位置相对 LG 移位（cine 取代）是苯炔机理的实验指纹——若连接位置不变，苯炔边剪枝；算出脱 HX 步无垒（强碱 + 好 LG）→ 生成决速在扩散/混合，直接比较两条加成边的 ΔΔG‡ 即可。

## SNAr SRN1（自由基链）

- 键变化：无常规键变化扫描坐标——核心步是 SET（电子转移）与自由基阴离子碎裂。碎裂步 `watch_pairs` = (C_ipso, X)；C–X 拉长扫描可行（[ArX]·− 态上）。
- 预组织/电子结构：所有自由基阴离子、芳基自由基节点设 `spin=2`（自动 UKS），每步检查 `<S^2>` 与自旋布居（自旋应在假设的载体上：先在环上、碎裂后移向芳基 σ 自由基）。
- 建模策略：SET 步不是普通键断裂，不要用键扫描当 TS——用 ΔG(ET)（供体/受体分别算氧化还原自由能，Marcus 定性判断可行性）；链传播三步（碎裂 → Nu− 加成 → 电子回传给新 ArX）各算 ΔG 与能垒，碎裂步 C–X 扫描可作 TS 初猜。芳基自由基 + Nu− 加成为新 C–Nu 键生成，`distance_filters` Nu–C < 3.0 Å。
- 必须并建的竞争边：氢原子转移副反应（Ar· 从溶剂/底物夺 H → 还原脱卤产物，这是 SRN1 最常见的失败通道，参见 [radical.md](radical.md) 的 HAT 条目）；链终止（自由基偶合）不必建 TS，定性标注即可。
- 误诊信号：底物无 EWG 却在极性/光照/液氨条件下给出高取代产率，且加 TEMPO 类捕获剂被抑制 → 优先排查 SRN1 而非 SNAr；`spin=2` 各节点 `⟨S²⟩` 偏差 ≳0.1 → 按 [method-selection.md](../../dft-calculation/references/method-selection.md) 打折该边结论并诊断自旋污染（实用触发器，非自动 fail）。

## 饱和碳自由基取代（链式卤化 / HAT / SH2）

细节（链引发/传播/终止、开壳层工作流）参见 [radical.md](radical.md)，此处只列取代结果特有的判别与数值。

- 键变化：HAT 步 C–H 断、X–H 成；`watch_pairs` = (X·, H), (C, H)；扫描坐标 C–H 拉长。C–H···X 角要求近线性（160–180°）。
- TS 期望与选择性（Hammond 是本领域的核心）：Cl· 夺氢放热 → 早 TS（C–H 仅拉至约 1.1–1.3 Å，典型区间待核实），3°:2°:1° 位点选择性低（实验每 H 相对速率约 5:4:1，298 K，典型值）；Br· 夺氢吸热 → 晚 TS（C–H 约 1.3–1.6 Å，H–Br 已部分形成），选择性高（约 1600:80:1）。**每个可夺氢位点各建一条边**，ΔΔG‡ 定产物分布；只有 1–3 kcal/mol 的 ΔΔG‡ 差异就能解释 4:1 到 100:1 的选择性，计算精度要按此要求自评。
- SH2 / XAT 边：R· 从 R'–X 夺卤（XAT）或自由基对 σ 键的正面取代（SH2），TS 要求 C–X···R 近线性（σ* 反式对齐）；高位阻碳上 SH2 通常输给 XAT + 自由基偶合组合路径，两条都建。
- 误诊信号：立体中心底物给出消旋产物 → 平面自由基中间体（SN2 边剪枝）；算得某 HAT 边能垒反常低 → 检查是否把极性效应算丢（亲电自由基优先夺富电 H，换泛函/加显式溶剂复算）。

## 领域级陷阱

1. **默认教材机理假设**：SNAr 教材画逐步 MC，但 2018 年后计算共识是多数常规 SNAr 协同；SEAr 教材画两步 arenium，非极性介质中部分卤化实为协同/加成-消除。逐步与协同永远并建，让剖面裁决。
2. **气相 vs 溶剂模型**：SN1/SN2 能垒与剖面形状对溶剂模型极端敏感（气相 SN2 双井势、SN1 完全失真）；离子型中间体必须 SMD 起步，质子性溶剂必要时加 1–2 个显式溶剂分子。
3. **去质子/质子化步想当然**：SEAr 去质子、SNAr 胺 Nu 的去质子都不可分子内直接迁移（对称性禁阻高垒），必须建碱/溶剂穿梭边；漏建会把加成步误判为唯一决速步。
4. **苯炔区域选择性归因错误**：用位阻解释会错——是 aryne distortion（畸变能/三键弯曲程度）控制；建模时对两条加成边都做 `electronic_analysis` 看电荷与几何畸变。
5. **把 SET 当普通基元步**：SRN1 的引发/链转移是电子转移，无键扫描坐标可扫；用氧化还原自由能 + Marcus 定性评估，不要硬造 ET 过渡态。
6. **取代-消除竞争漏建**：饱和碳底物只要 β-H 与构象允许，E2/E1 边必建（参见 [elimination.md](elimination.md)）；产物是烯烃还是取代往往只差 1–2 kcal/mol 的 ΔΔG‡。

## 参考来源

- Kwan EE, Zeng Y, Besser HA, Jacobsen EN. "Concerted nucleophilic aromatic substitutions." Nat. Chem. 2018, 10, 917–923. DOI: 10.1038/s41557-018-0079-7
- Rohrbach S, Murphy JA, Tuttle T. "Computational Study on the Boundary Between the Concerted and Stepwise Mechanism of Bimolecular SNAr Reactions." J. Am. Chem. Soc. 2020, 142, 14871–14876. DOI: 10.1021/jacs.0c04520
- Neumann CN, Hooker JM, Ritter T. "Concerted nucleophilic aromatic substitution with 19F and 18F−." Nature 2016, 534, 369–373. DOI: 10.1038/nature17667
- Galabov B et al. "Arenium Ions Are Not Obligatory Intermediates in Electrophilic Aromatic Substitution: The Case of Anisole." ChemistryOpen 2014. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4104905/
- Fu Y et al. "Ab Initio Molecular Dynamics Simulations of the SN1/SN2 Mechanistic Continuum in Glycosylation Reactions." JACS Au 2021. https://pmc.ncbi.nlm.nih.gov/articles/PMC8162065/
- Rossi RA, Pierini AB, Peñéñory AB. "Nucleophilic Substitution Reactions by Electron Transfer (SRN1)." Chem. Rev. 2003, 103, 71–168. DOI: 10.1021/cr020065h
- "Steric Effects Compete with Aryne Distortion to Control Regioselectivities of Nucleophilic Additions to 3-Silylarynes" (Garg/Houk 芳炔畸变模型). https://pmc.ncbi.nlm.nih.gov/articles/PMC3445038/
- Tan H et al. "Switchable chemoselective aryne reactions..." Nat. Commun. 2024（M06-2X/6-31+G(d) 芳炔加成 TS 实例）. https://www.nature.com/articles/s41467-024-47952-8
- Gazitúa M et al. "Experimental Analyses Emphasize the Stability of the Meisenheimer Complex in a SNAr Reaction." Front. Chem. 2020. https://www.frontiersin.org/journals/chemistry/articles/10.3389/fchem.2020.00583/full
- Master Organic Chemistry: "Selectivity in Free-Radical Reactions: Bromination vs Chlorination" / "Nucleophilic Aromatic Substitution (2) – The Benzyne Mechanism"（卤化选择性与苯炔张力能数值核对）. https://www.masterorganicchemistry.com/2013/10/31/selectivity-in-free-radical-reactions-bromine-vs-chlorine/ ; https://www.masterorganicchemistry.com/2018/09/17/nucleophilic-aromatic-substitution-2-benzyne/
