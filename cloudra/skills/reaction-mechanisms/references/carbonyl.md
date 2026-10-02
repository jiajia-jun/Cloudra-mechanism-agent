# 羰基化合物反应：机理可能性与建模

章节读取：同技能参考用 `get_skill(skill_name="reaction-mechanisms", reference="<文件名>.md")`；下文链接的通用计算参考用 `get_skill(skill_name="dft-calculation", reference="<文件名>.md")`。

范围：醛酮/羧酸衍生物的 sp² 碳上成键（亲核加成、酰基转移、α-碳成键、烯化）。总 SOP 与五问题框架见 [mechanism-elucidation-sop.md](../../dft-calculation/references/mechanism-elucidation-sop.md) 与 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md) §1（羰基加成与酰基转移的基线谓词已并入本文相应节；质子转移通用谓词见 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md) §3.1）。所有数值为典型区间，随底物、亲核试剂、溶剂与催化条件漂移（Hammond），只用于初猜与筛选，裁决永远是频率 + IRC。

## 机理假设空间

| 变体 | 适用底物与条件 | 假设图骨架（一行） | 判别特征（计算证据） |
| :--- | :--- | :--- | :--- |
| 直接亲核加成 | 醛酮 + 中性/阴离子 Nu，无活化 | 反应物络合物 → 加成 TS → 烷氧/氮负离子 → 质子化 | IRC 一端为四面体醇盐；无配位节点 |
| Lewis 酸/金属配位加成 | 有 LA/金属（BF₃、Li⁺、Ti、镧系） | LA·羰基络合物 → 加成 TS → 产物络合物 | 加成 TS 中 O–M 键 < 2.2 Å 且 O 电荷正移；比裸底物能垒低数 kcal/mol |
| 酸催化加成 | 羰基 O 被质子化/H 键供体活化 | O–H⁺ 络合物 → 加成 TS → 去质子 | TS 上有 O···H–A 氢键（< 2.0 Å）；加成与质子转移可能同步 |
| 加成-消除（四面体中间体） | 酯、酰胺、酸酐、多数酰氯 | 加成 TS → 四面体中间体 → 消除 TS | 两步各一个 TS，中间有极小点；IRC 接到四面体中间体 |
| 协同酰基取代 | 强酸/特殊催化下的酯氨解等 | 单一 TS：Nu–C 成与 C–LG 断同步 | 全程无四面体极小点；扫描单峰且中间结构 O 仍近似 sp² 平面恢复中 |
| ketene 路径 | 酰氯/酸酐 + 叔胺 + 有 α-H | 去质子+脱 LG → ketene → Nu 加成 → 烯醇盐 → 质子化 | ketene 节点（C=C=O 近线性）；Nu 加成的碳是 ketene 中心碳 |
| 酰基离子（acylium） | 位阻大的酰氯 + 强离子化溶剂 | C–LG 异裂 → RCO⁺ → Nu 俘获 | 异裂步无 Nu 参与（Nu···C > 3.5 Å 仍成键步在离子之后） |
| 烯醇盐闭环加成（aldol） | 金属烯醇盐 + 醛酮 | 金属双配位预组织 → ZT 六元环 TS → 金属醇盐 | TS 为六元环含 M，两根 O–M 键同时短；椅式 vs 船式竞争 |
| 烯醇盐酰基化（Claisen） | 酯/酮烯醇盐 + 酯 | 烯醇盐 → 加成 TS → 四面体中间体 → 脱烷氧 → β-羰基烯醇盐 | 末尾必有一个强放热去质子节点拉动平衡 |
| 烯胺/亚胺离子路径（Mannich、α-官能化） | 仲胺催化醛酮 + 亲电体 | 缩合 → 烯胺 → C–C/C–X 成键 TS → 亚胺离子 → 水解 | 有烯胺与亚胺离子节点；有机催化 TS 靠 H 键网络定向 |
| 酸催化烯醇路径 | 酸催化 α-卤化、氘代、外消旋 | 羰基质子化 → 去 α-H → 烯醇 → 亲电进攻 → 去质子 | 中间体为中性烯醇（C=C），进攻步无金属配位 |
| Wittig（[2+2] 直接成环） | 磷叶立德 + 醛酮，无/少 Li 盐 | 络合物 → [2+2] TS → 氧磷杂环丁烷 → syn 环反转 → 烯烃 + Ph₃P=O | 无 betaine 极小点；两步 TS（成环、解环） |
| Horner–Wadsworth–Emmons | 膦酸酯碳负离子 + 醛酮 | 加成 → 氧磷杂环丁烷（或开式氧负离子）→ 消除 → E 烯烃 | P 上有额外烷氧基；消除步伴随磷酸酯离去 |
| 羰基还原 | 氢化物/催化氢化/转移氢化 | 参见 [redox.md](redox.md) | — |

## 直接亲核加成（含 Lewis 酸/酸催化变体）

- 键变化：Nu–C 成、C=O π 断（C=O 拉长）；酸催化变体另有 O···H–A 键变化。`watch_pairs` = [Nu–C, C–O]（酸催化加 O–Hₐ）。
- 预组织：Bürgi–Dunitz 轨迹 Nu–C=O ≈ 107°（N 亲核约 107°，O 亲核约 110°，可接受约 95–120，源自 n_Nu→π*C=O 最优重叠；典型区间随底物漂移）。`distance_filters`：Nu···C < 3.0；LA 变体加 O–M < 2.5。
- TS 期望：Nu–C 约 1.9–2.3 Å，C=O 从约 1.21 拉长到约 1.25–1.35 Å（Hammond：强亲核/放热 → 早 TS、两键都更长；LA/酸活化使能垒下降、TS 提前）。
- 必须并建的竞争边：Re/Si 面各一条（手性醛酮按 Felkin–Anh 排布构象后分面建边）；直接加成 vs 酸催化加成 vs LA 配位加成三条边（活化模式取决于条件，别预设）；质子化节点放前还是放后（先加成再质子化 vs 同步）。
- 误诊信号：TS 的 Nu–C Mayer 键级 < 0.1 → 坐标/构象错；IRC 产物端不是四面体加成物而是掉回羰基 → 初猜落在排斥墙上；酸催化假设下若去掉酸能垒反而更低 → 活化模式假设错。

## 加成-消除（四面体中间体，酰基转移主路径）

- 键变化：加成步 Nu–C 成、C=O π 断；消除步 C–LG 断、C=O π 复成。`watch_pairs` = [Nu–C, C–LG, C–O]；扫描坐标加成步扫 Nu–C，消除步扫 C–LG。
- 预组织：加成步同 Bürgi–Dunitz 谓词；消除步要求氧孤对与 σ*C–LG 反式共平面（n_O→σ*C–LG），即四面体中间体需转到 LG 与羟基/烷氧基反式的构象——`conformer_search` 对中间体单独跑，消除 `distance_filters`：C–LG < 2.2 且 O(羟基)–C–LG 角 ≈ 170–180。
- TS 期望：两个 TS 近似镜像；加成 TS 中 Nu–C 约 1.8–2.2，消除 TS 中 C–LG 约 1.9–2.4（典型区间，酰胺 N–LG 断更晚，随底物漂移）。
- 必须并建的竞争边：质子穿梭边——直接 [1,2]/[1,3]-H 迁移是三元/四元环 TS 且 suprafacial 禁阻，能垒通常 > 30 kcal/mol，必须另建一分子水/胺/醇介导的六元环穿梭 TS（谓词：穿梭 H···受体 < 1.8，D–H···A 角 > 150）；**决速步是加成、消除还是质子转移随底物与条件而变，不要预设，三条边都算再裁决。**
- 误诊信号：加成 IRC 产物端直接掉到最终产物（没停住四面体中间体）→ 该条件可能走协同取代，改假设；消除步扫描全程单调 → 中间体构象没转到反式共平面，回构象搜索；酰胺类 C–N 部分双键导致中间体翻转/旋转有独立能垒，漏掉会高估总垒。

## 协同酰基取代（无四面体中间体）

- 键变化：Nu–C 成与 C–LG 断在同一 TS（类 SN2 于酰基碳）。`watch_pairs` = [Nu–C, C–LG]；扫描坐标：Nu–C 或 C–LG 单扫。
- 预组织：Nu 从羰基面外接近，Nu–C–LG 近线性（160–180）；`distance_filters`：Nu···C < 3.0。
- TS 期望：Nu–C 与 C–LG 均约 2.0–2.5（典型区间，酸催化酯氨解等体系报道过此类 TS，随底物漂移，待核实面较宽）。
- 必须并建的竞争边：与加成-消除两条边同建裁决——判别证据 = IRC 是否接到四面体极小点、全程扫描是单峰还是双峰；另有实验侧证据（不对称酯/胺产物无外消旋化支持协同，计算上体现为无 sp³ 中间体节点）。
- 误诊信号：单峰剖面不等于协同——四面体中间体可能太浅被扫描步长跳过；用扫描加密或 IDPP 插值（`ts_guess` interpolate）复查谷区。

## ketene 路径（酰氯/酸酐 + 叔胺 + α-H）

- 键变化：ketene 生成步 Cα–H 断 + C–LG 断（E1cB 样或协同）；加成步 Nu–C(ketene 中心碳) 成。`watch_pairs` = [Base–Hα, C–LG, Nu–C(中心碳)]。
- 预组织：碱接近 α-H（Base···H < 2.5）；Nu 进攻 ketene 中心 sp 碳，轨迹近似 Bürgi–Dunitz 于 C=C=O π 体系（进攻角约 90–120，待核实）。
- TS 期望：ketene 中 C=C 约 1.30、C=O 约 1.16、C=C=O 近线性（典型值，待核实）；加成 TS 的 Nu–C 约 1.9–2.3（随亲核漂移）。
- 必须并建的竞争边：与加成-消除边同建——判别证据 = 是否存在 ketene 极小点及其生成能垒 vs 直接加成能垒；ketene 另有 [2+2] 二聚边（常见副反应，放热）。
- 误诊信号：假设加成-消除但加成 TS 始终找不到/能垒反常高，且体系为酰氯 + Et₃N + 可烯醇化 α-H → 回头建 ketene 边；IRC 产物端出现脱共轭/异构酰胺也提示 ketene 中间体。

## 酰基离子路径（acylium，罕见但必须能排除）

- 键变化：C–LG 异裂（无 Nu 参与），然后 Nu 俘获。`watch_pairs` = [C–LG, Nu–C]。
- 预组织/TS 期望：异裂 TS 中 C–LG 约 2.2–2.8（典型区间，随离子化能力漂移）；acylium R–C≡O⁺ 近线性，C=O 约 1.11–1.15（待核实）；隐式溶剂（SMD）必需，注意离子对/溶剂分离多峰。
- 判别特征：异裂步扫描时 Nu···C 保持 > 3.5 Å 仍有势垒峰；若把 Nu 拿掉能垒几乎不变 → 单分子路径；若显著升高 → 实为加成-消除/协同。
- 误诊信号：酰氯底物在无水强极性溶剂中计算给出离谱高垒，常因漏建 acylium 边或漏溶剂化稳定；气相结论不可外推。

## 烯醇盐闭环加成（aldol，Zimmerman–Traxler）

- 键变化：Cα–C(醛) 成；金属从烯醇盐 O 转移到烷氧 O（两根 O–M 键此消彼长）。`watch_pairs` = [Cα–C, O(enolate)–M, O(carbonyl)–M]；扫描坐标 Cα–C。
- 预组织：金属双配位的六元环预组织是前提。`distance_filters`：Cα···C < 3.2、O(carbonyl)–M < 2.5（Li–O 典型约 1.9–2.0，B–O 约 1.36–1.47，金属越共价 TS 越紧，区间随金属漂移）。
- TS 期望：椅式六元环 TS，醛取代基占假平伏位；forming C–C 约 2.0–2.3（Hammond 漂移）。硼烯醇盐有船式 TS 反低个例，椅式优先不是铁律。
- 必须并建的竞争边：椅式 vs 船式各一条；烯醇盐 E/Z 几何各一条（Z → syn、E → anti 的经验映射以计算 ΔΔG‡ 为准）；开式（非螯合）TS 一条（无金属/大位阻 Lewis 酸体系可能反主）；aldol 产物脱水（E1cB）一条——决定拿到的是醇还是烯酮。
- 误诊信号：只用自由烯醇盐（不带金属）建模 → 找不到闭环 TS、选择性结论全错；烯醇盐 E/Z 异构化能垒低于加成垒时 Curtin–Hammett 生效，起始几何归属失效。

## 烯醇盐酰基化（Claisen 缩合 / Dieckmann）

- 键变化：Cα–C(酰基) 成 → 四面体中间体 → C–OR 断；末尾产物 α-H 被碱拔掉（热力学汇）。`watch_pairs` = [Cα–C, C–OR, Base–H(产物α)]。
- 预组织：同 aldol 的金属螯合谓词；Dieckmann 环化另按 Baldwin 规则预筛环尺寸（参见 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md) §3.2）。
- TS 期望：加成 TS forming C–C 约 2.0–2.3；消除 TS C–OR 约 1.9–2.3（典型区间，随底物漂移）。
- 必须并建的竞争边：酮醇副反应（产物 β-酮酯再被烯醇盐进攻）；酯交换边（碱烷氧基与底物烷氧基不匹配时）；自缩合 vs 交叉缩合取向边。
- 误诊信号：ΔG 剖面漏掉末尾去质子节点 → 整个缩合显示为热力学禁行而误判机理不可行；酯 pKa 约 25 vs 醇约 16，烷氧碱生成的烯醇盐是低浓度平衡物种，不要把"烯醇盐"当自由反应物零点。

## 烯胺/亚胺离子路径（Mannich 与有机催化 α-官能化）

- 键变化：Mannich：烯胺 Cα–亚胺 C 成，伴随亚胺 C=N π 断；α-官能化：Cα–E 成。`watch_pairs` = [Cα–C(亚胺), C–N(亚胺)]；扫描坐标 forming C–C。
- 预组织：脯氨酸类催化的 TS 由羧基–亚胺氢键锁定取向：`distance_filters`：Cα···C < 3.2 且 O(羧基)–H···N/C(亚胺) 氢键 < 2.2。烯胺双键构型（E/Z、围绕 N 的顺反）先 `conformer_search` 枚举。
- TS 期望：forming C–C 约 1.9–2.3（典型区间，H 键定向 TS 偏早，随底物漂移）；亚胺 C=N 从约 1.28 拉长（待核实）。
- 必须并建的竞争边：Si/Re 面进攻各一条（ee 来源）；烯胺 vs 烯醇路径（酸催化 Mannich 走烯醇）；亚胺↔亚胺离子互变异构节点；水解断催化剂的边（闭环必须，否则剖面停在亚胺离子）。
- 误诊信号：TS 上氢键网络散了（H···受体 > 2.5）→ 构象初猜错，回构象搜索；把亚胺当电中性 C=N 建模（漏质子化）→ 亲电性全错。

## 酸催化烯醇路径（α-卤化、氘代、外消旋）

- 键变化：O 质子化 → Cα–H 断（烯醇化，通常为决速步）→ 烯醇 C=C 进攻亲电体。`watch_pairs` = [Base–Hα, Cα–E]；扫描坐标 Cα–H 或 Base–H。
- 预组织：烯醇 C=C 约 1.33–1.36（待核实），亲电体接近 Cα；`distance_filters`：E···Cα < 3.2。
- 必须并建的竞争边：碱催化（烯醇盐）路径一条——同一产物两种机理，酸 vs 碱条件判别；多卤代连续取代边（卤素吸电子使剩余 α-H 更酸，haloform 反应的成因）。
- 误诊信号：扫描 Cα–H 全程无峰 → 漏了接受质子的碱/溶剂分子（裸气相去质子垒不可靠）；烯醇↔酮互变异构若算出双峰，中间的烯醇极小点必须入图。

## Wittig 烯化（[2+2] 直接成氧磷杂环丁烷）

- 键变化：成环步 C(叶立德)–C(羰基) 成 + P···O 成；解环步（syn 环反转）P–C 断 + C–O 断，生成烯烃 + Ph₃P=O。`watch_pairs` = [C–C, P–O, P–C, C–O]；扫描坐标：成环扫 C–C，解环扫 C–O 或 P–C。
- 预组织：叶立德 C 对羰基的近似 Bürgi–Dunitz 接近；`distance_filters`：C(叶立德)···C < 3.0、P···O < 3.5。无 Li 盐条件下主流共识为一步 [2+2] 直接成环，betaine 不是极小点——不要给 betaine 建节点除非 IRC 真的接出来。
- TS 期望：非稳定叶立德 → 早、皱褶（puckered）四元环 TS → cis-氧磷杂环丁烷 → Z 烯烃；稳定叶立德 → 晚、近平面 TS → E 倾向（Hammond 框架下的典型图景，选择性强弱随取代漂移）。TS 中 forming C–C 约 2.0–2.4、P···O 约 2.2–2.8（待核实，区间宽）；氧磷杂环丁烷中间体 P–O 约 1.7–1.9、P–C 约 1.8–1.9（待核实）。解环是强放热步（P=O 驱动），通常成环决速。
- 必须并建的竞争边：cis/trans 氧磷杂环丁烷两条成环边（E/Z 选择性来源）；含 Li 盐体系另建 Li 配位变体边（Li 配位改变机理与选择性，无盐结论不可外推）；半稳定叶立德介于两类之间，四类 TS 都可建。
- 误诊信号：IRC 从"成环 TS"接出一个疑似 betaine 的开链极小点 → 该体系可能真有逐步成分，如实记录而非强行归类；TS 虚频模式是环的皱褶翻转而非 C–C 形成 → 找到的是构象互变鞍点，重搜。

## Horner–Wadsworth–Emmons 烯化

- 键变化：膦酸酯碳负离子 C–C(羰基) 成 → 氧磷杂环丁烷（或开式氧负离子中间体）→ 断 P–O/C–O 消除，P=O 形成驱动。`watch_pairs` = [C–C, P–O, C–O, P–C]。
- 预组织：膦酸酯氧与金属抗衡离子螯合羰基氧时建闭环 TS；`distance_filters`：C(负碳)···C < 3.0。与 Wittig 的差别：P 上两个烷氧基提供额外配位/螯合位点。
- TS 期望：加成 TS forming C–C 约 2.0–2.4（典型区间，待核实）；通常给 E 烯烃，机理解释有加成步可逆 + 消除步快慢之别，建图时加成边允许双向。
- 必须并建的竞争边：E/Z 两条边；闭环（螯合）vs 开式加成 TS；Still–Gennari 型（双三氟乙基膦酸酯给 Z）作为取代效应提醒——不要换底物套旧结论。
- 误诊信号：加成中间体优化直接消除成产物（无中间体极小点）→ 该体系加成消除近似协同，剖面合并为一条边处理。

## 领域级陷阱

- **质子穿梭永远要单独建边**：羰基化学里几乎每个加成/消除/互变异构步都含质子转移；直接分子内迁移（三/四元环 TS）能垒常 > 30 kcal/mol 且 [1,2]/[1,3]-suprafacial 对称性禁阻，真实路径多为水/醇/胺/第二分子底物介导的六元环穿梭。漏建 = 整条剖面高垒误诊。
- **金属抗衡离子不是旁观者**：烯醇盐、HWE、aldol 的选择性全部来自金属螯合的闭环 TS；裸离子（只算阴离子）或纯隐式溶剂自由离子模型会给出错误的机理与选择性。要么显式带金属，要么明确声明模型局限。
- **四面体中间体的构象翻转是隐藏能垒**：加成产物构象未必满足消除的 n_O→σ*C–LG 反式共平面要求；直接拿加成 IRC 端点扫消除常失败。对中间体独立跑 `conformer_search`。
- **热力学汇漏节点**：Claisen、aldol 缩合类反应由产物去质子/脱水拉动；剖面只画到中性产物会误判"反应不可行"。假设图必须包含去质子/脱水节点及相应碱。
- **单峰 ≠ 协同**：加成-消除的四面体中间体浅时，约束扫描可能只显示一个宽峰；用更小步长或 IDPP 插值复查谷区，再下"协同酰基取代"结论。
- **酮-烯醇/亚胺-烯胺互变异构的归属**：TS 归属错误（把互变异构 TS 当成键 TS）是该领域最常见的 2+ 虚频/接错端点来源；verify 接错时先核对是不是踩到了互变异构通道。

## 参考来源

- Bürgi, Dunitz, Shefter, JACS 1973, 95, 5065（Bürgi–Dunitz 轨迹原始文献）；角度综述见 chemeurope.com/en/encyclopedia/Bürgi-Dunitz_angle.html（105±5 → 107，N/O 亲核差异）及 jb243.github.io/pages/1358 整理。
- 碱催化酰胺水解 TS 与四面体中间体：Xiong et al., J. Phys. Chem. B（PMC2892839, https://pmc.ncbi.nlm.nih.gov/articles/PMC2892839/）。
- 乙酸催化酯氨解：协同酰基取代机理（无四面体中间体），Chinese Chemical Letters 2018, https://html.rhhz.net/zghxkb/20180811.htm。
- ketene 化学机理与计算综述：Recent advances in ketene chemistry, https://pdfs.semanticscholar.org/e69f/11664b8290c48bd27f514227f90e7179864d.pdf。
- Zimmerman–Traxler 模型与 Li–O/B–O 键长：Oxford SBM-CDT stereocontrol 讲义, https://www.oxfordsynthesiscdt.ox.ac.uk/resources/SBM-CDT-Stereocontrol.pdf；硼烯醇盐船式 TS 例：北海道大学学位论文, https://eprints.lib.hokudai.ac.jp/dspace/bitstream/2115/96068/1/111470.pdf。
- 有机催化（脯氨酸 Mannich、烯胺/亚胺离子）计算综述：Cheong et al., "Quantum Mechanical Investigations of Organocatalysis", https://pmc.ncbi.nlm.nih.gov/articles/PMC3154597/。
- Wittig 机理统一图景（无 Li 盐 [2+2]、cis-OPA 选择性）：Gilheany 组实验证据（ResearchGate 记录）及 McLeod 博士论文, https://macsphere.mcmaster.ca/bitstream/11375/20458/2/McLeod_David_A_201609_phd.pdf；氧磷杂环丁烷形成的计算分析：Chamorro et al. 2020, https://pubmed.ncbi.nlm.nih.gov/32293888/；P–C/C–O 扫描网格实例：Quapp et al., https://www.mathematik.uni-leipzig.de/MI/quapp/Wittig_OEEF06_GA.pdf。
- Claisen 缩合机理与去质子驱动：β-二酮配体综述（MDPI Molecules）及 Clayden《Organic Chemistry》2nd ed. 相关章节。
- 反应类跨领域通用判读（质子转移、Baldwin 规则、判读速查）：[reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md) §3；还原反应参见 [redox.md](redox.md)。
