# 周环反应：机理可能性与建模

范围界定：底物通过环状过渡态发生成键/断键重排，产出环加成产物（环己烯、环丁烷、五元杂环）、重排异构体（Cope/Claisen 产物、H 迁移异构体）、开环/闭环产物（电环化）或挤出小分子（CO、N2、SO2）的反应。本文档面向"产物已知、机理未知"的场景：同一产物可能来自协同周环 TS、逐步双自由基/两性离子、或光化学激发态路径，agent 必须并建假设再用计算裁决。
通用流程与五问题框架见 `mechanism-elucidation-sop.md` 与 `reaction-class-geometry.md` §1；DA 与 σ 迁移/电环化的基线数值已并入本文相应节。

## 机理假设空间

| 变体 | 适用底物与条件 | 假设图骨架（节点→边） | 判别特征（计算证据） |
| :--- | :--- | :--- | :--- |
| 协同同步 [4+2]（DA） | 中性二烯 + 亲双烯，加热 | R → concerted TS → P | 两根 forming σ 键等长（差 < 0.3 Å）；1 虚频；闭壳层稳定 |
| 异步协同 DA（含 ambimodal/bis-pericyclic） | 取代不对称二烯/亲双烯、非极性体系 | R → asynchronous TS → P | forming 键长差 0.3–1.0 Å 但 IRC 直连 R 与 P，无中间体；TS 虚频模式两键耦合 |
| 逐步双自由基 DA / [2+2] | 单取代烯、非极性烯，加热 | R → TS1（先成一键）→ diradical I → TS2（闭环/旋转）→ P | 第一步 TS 高度异步（forming 键差 > 1.0 Å）；`<S^2>` 显著偏离 0；IRC 落入自由基中间体极小点 |
| 逐步两性离子 DA / [2+2] | 强给体-受体对（推-拉烯）、极性溶剂、Lewis 酸 | R → TS1 → zwitterion I → TS2 → P | 中间体电荷分离显著（Mulliken/meta-Löwdin 电荷 ±0.5 以上）；闭壳层，`<S^2>` ≈ 0；溶剂化强烈稳定中间体 |
| 光化学 [2+2]（激发态） | 烯 + 烯（或烯酮），hν | S0 R → S1/T1 → 激发态 TS 或 S1/S0 锥形交叉 → P | 基态势能面上无合理低垒协同 TS；TD-DFT/T1 优化（spin=3）有可行路径 |
| 1,3-偶极环加成（协同） | 叠氮/腈氧化物/氧化腈/甲亚胺叶立德 + 烯炔 | R → concerted TS（异步）→ 五元杂环 | 两根 forming 键通常不等长（0.2–0.6 Å 差）但无中间体；闭壳层 |
| 电环化（顺旋/对旋） | 环丁烯开环、己三烯闭环等，加热或 hν | R → conrot/disrot TS → P（每个允许旋转方向一条边） | 虚频模式为端基旋转；产物 E/Z 由旋转方向锁定，IRC 端点立体化学即判别证据 |
| [3,3] σ 迁移（Cope/Claisen） | 1,5-二烯、烯丙基乙烯基醚，加热 | R → 椅式 TS → P（船式为竞争边） | 六元环状 TS；断 σ 键与成 σ 键均约 2 Å 的 partial bond |
| [1,5]-H σ 迁移 | 环戊二烯、戊二烯基体系，加热 | R → 六元环状 suprafacial TS → P | 迁移 H 与两端碳均部分键合；suprafacial 保持面选择性 |
| [1,2]/[1,3] 迁移（禁阻 → 非协同路径） | 碳正离子/自由基/叶立德体系 | R → 三元/四元环 TS（高垒）或分步：解离 → 复合 | 协同 TS ΔG‡ > 35 kcal/mol 即剪枝；真实路径常为自由基对/离子对分步，找分步中间体 |
| ene 反应 | 烯（含 allylic H）+ 亲烯体，加热 | R → 六元环状 TS → P | H 迁移与新 C–C 键形成协同；forming C–C 晚于 H 迁移（异步） |
| 螯变反应（挤出） | 3-环戊烯亚砜（→SO2）、偶氮（→N2）、内酯（→CO2）等 | R → 协同挤出 TS → 二烯 + 小分子 | 两根断键耦合于同一中心原子；小分子放出驱动放热 |

## 协同与异步 Diels–Alder [4+2]

基线几何（s-cis 预组织、forming 键 2.0–2.4 Å、endo/exo 竞争边）已并入本节，以下补机理裁决层。

- 键变化：`watch_pairs` = 两根 forming σ 键（二烯端基–亲双烯两端）；扫描坐标单扫一根即可起步，明显异步改双坐标或 NEB。
- 预组织：二烯中心单键二面角 ≈ 0°（s-cis）；`distance_filters` 设两组端基对距离均 < 3.2 Å 筛 reactive conformer（典型区间，随底物漂移）。
- TS 期望：forming 键典型 2.1–2.3 Å（典型区间，Hammond：给-受体组合放热强则更早、键更长）。同步性判据 |Δr|：< 0.3 Å 同步协同；0.3–1.0 Å 异步协同（仍允许，常见于不对称取代）；> 1.0 Å 警惕逐步。
- 必须并建的竞争边：endo/exo（Alder 内型规则：次级轨道相互作用使内型通常低 1–3 kcal/mol，位阻大时有例外）；两种区域取向（regioisomeric TS）；逐步双自由基边（尤其非极性底物，如丙烯腈 + 非极性二烯体系计算显示协同与 diradical 能垒差可小至 2–8 kcal/mol，见参考来源）；ambimodal 可能（[6+4]/bis-pericyclic 体系，单个 TS 后势能面分叉——IRC 只能到一种产物，产物比须动力学方法，标注单参考局限）。
- 误诊信号：① TS 两根 forming 键差 > 1.0 Å 且 IRC 中途落入极小点 → 实为逐步，回假设图补 diradical/zwitterion 节点；② `electronic_analysis` 报 `<S^2>` 偏差 > 0.1 → 双自由基特征，闭壳层能垒要打折（spin 投影校正可改变协同/逐步排序 2–5 kcal/mol，待核实具体体系）；③ 频率出现 2+ 虚频且第二虚频是另一根 forming 键的伸缩 → 高阶鞍点，沿该模式位移重搜异步 TS。

## [2+2] 环加成：热禁阻 vs 逐步 vs 光化学

- 键变化：两根 forming σ 键（两个烯的端基交叉配对，共 4 对距离）。`watch_pairs` 全列。
- 预组织：`distance_filters` 两组 forming 对均 < 3.5 Å；两烯平面近平行（π-π 面对齐）。
- 机理裁决优先级：热协同 [2s+2s] 对称性禁阻，**不要建协同边**；热允许变体按序排查：
  1. **逐步双自由基**：先成一根 σ 键（TS1 中 forming 键 ~2.0–2.4 Å，另一对 > 3.0 Å，典型区间），diradical 中间体须绕新 σ 键旋转再闭环（TS2）。用 `electronic_analysis` spin=2 起步查自旋布居；注意 diradical 中间体旋转垒常与失稳（回断键）竞争。
  2. **逐步两性离子**：推-拉烯或 Lewis 酸存在时优先；TS1 后电荷分离中间体（meta-Löwdin 电荷 ±0.5 以上），闭壳层。隐式溶剂模型会显著影响排序，气相结论不可外推。
  3. **[2s+2a] 协同**：仅当一个组分能扭曲成 antarafacial（如烯酮的 C=C 与 C=O 正交轨道、或大环体系）时允许；TS 几何特征为一根 forming 键从 π 面同侧、另一根从对侧接近，`watch_pairs` 中体现为两烯平面二面角显著扭曲。
  4. **光化学**：激发态 supra-supra 允许。基面 S0 上找不到合理路径时，TD-DFT 算 S1 垂直激发能确认可达性，T1 优化（`electronic_analysis`/`submit_compute_job` spin=3）找三重态 diradical 路径；锥形交叉超越单基态 TS 工具链能力，标注"需多参考/表面跳跃，超出当前裁决精度"。
- 误诊信号：基态扫描出"协同 [2+2] TS"且虚频正常但 ΔG‡ > 35 kcal/mol → 这是禁阻路径的高垒鞍点，不是实验机理，回假设图建逐步边；diradical 中间体 `<S^2>` ≈ 1.0 → 接近纯双自由基，单参考能量定性即可。

## 1,3-偶极环加成

- 键变化：两根 forming σ 键（偶极体两个端基 → 亲偶极体两端），偶极体内部 π 键级重排（如 N3 的 N–N）。`watch_pairs` 两根 forming + 偶极体内部键。
- 预组织：偶极体与亲偶极体近平行接近（Huisgen parallel-planes 取向）；`distance_filters` 两组 forming 对均 < 3.5 Å。应变促进体系（环辛炔 SPAAC）由预弯曲降低畸变能，能垒可低至 ~8 kcal/mol（非应变炔 ~16 kcal/mol，典型区间，见参考来源）。
- TS 期望：forming 键典型 2.0–2.4 Å，**天然异步**（差 0.2–0.6 Å 常见，典型区间，Hammond），不要把不等长误判为逐步；共识机理为协同单步（可为异步），逐步 diradical/两性离子仅在强极性推拉组合时出现，拿不准就并建。
- 必须并建的竞争边：两种区域异构取向（FMO 系数大端对大端，可用 `electronic_analysis` 原子电荷/轨道系数辅助预判）；多种偶极体构象（如甲亚胺叶立德 E/Z）。
- 误诊信号：forming 键 Mayer 键级一根 < 0.1 而另一根已 0.5+ 且 IRC 出中间体 → 逐步；偶极体端基电荷分布与假设的共振式不符 → 换共振式重标电子推动。

## 电环化：顺旋/对旋与 torquoselectivity

- 键变化：断（或成）的环 σ 键 + 端基旋转二面角。`watch_pairs` = 断 σ 键；扫描坐标 = 该 σ 键拉长（开环方向）或端基–端基距离（闭环方向）。
- 预组织：开环体系（环丁烯等）预组织天然满足；闭环体系（己三烯）需构象把两端基拉近，`distance_filters` 端基对 < 3.0 Å。
- TS 期望：断 σ 键典型 2.0–2.3 Å（典型区间，随取代漂移）；虚频模式必须是端基同向（顺旋）或反向（对旋）旋转——这是验证的核心。
- 选择规则（热）：4n 电子顺旋、4n+2 对旋；光化学反转。禁阻模式（如环丁烯热对旋）**不建边**。
- 必须并建的竞争边：**允许模式下的两个旋转方向各一条边**（torquoselectivity）。3-取代环丁烯：给电子/σ 给体取代基 outward，π 受体（含 SiR3、CF3 等 contrasteric 基团）inward——立体位阻判断常错，电子效应可反转直觉，两条边都算 ΔΔG‡ 裁决，典型差 1–5 kcal/mol（随取代漂移）。
- 误诊信号：① 找到的"TS"虚频模式是纯 σ 键伸缩而非端基旋转 → 找错鞍点，沿旋转坐标重扫；② 产物 E/Z 与 W–H 允许模式不符 → 检查是否混入逐步（如环丙基正离子/负离子开环分步路径）；③ 两旋转方向 TS 能量差与实验产物比矛盾 → 核对构象初猜与溶剂模型。

## [3,3] σ 迁移（Cope / Claisen）

- 键变化：断 σ 键（C3–C4）与成 σ 键（C1–C6），两 π 键移位。`watch_pairs` 两 σ 键；扫描坐标 = 断键拉长或成键缩短。
- 两个 SMILES 的落地例：`C=COCC=C` → `C=CCCC=O` 在无标签时原子映射并不唯一，先让 `reaction_mapping` 返回候选。教材 [3,3] 候选的 product-heavy→reactant-heavy 映射为 `[4,5,6,1,2,3]`，对应断 C3–O4、成 C1–C6；应显式选择该候选，再把具体显式氢结构绑定所得 `atom_map` 交给 `ts_guess interpolate`，不能因为另一个候选图编辑数更少就静默换掉机理。
- 该反应在 `mechanism-elucidation-sop.md` §3 有 Claisen DAG-guided 示例：delivery DAG 保存中间体 occurrence、候选 elementary edges、stage 契约及证据指针。初猜和扫描只能支撑 `ts_guess` advisory 阶段；鞍点、双向路径、两侧优化极小点、方向与身份需要独立证据。当前绑定顺序和 ORCA strict 验证器限制见 SOP；不能为满足工具形式要求而重复已充分的计算。
- 预组织：1,5-二烯骨架须能取六元环状椅式排列；`distance_filters` 成键端基对（C1–C6）< 3.0 Å 筛预组织构象。
- TS 期望：椅式六元环 TS 优先；断/成 σ 键均典型 1.95–2.25 Å（典型区间，芳香性稳定化体系如 Claisen 可偏早）。船式高 5–10 kcal/mol（教材值，随底物漂移）；简并 Cope（bullvalene 类）注意 TS 与中间体之分——某些体系"TS"实为双自由基中间体两侧的耦合鞍点。
- 必须并建的竞争边：椅式多种取向（决定 Claisen E/Z、手性转移）；船式；解离为两个烯丙基自由基的分步边（含稳定自由基取代基时，如 2,5-二苯基体系，diradical 路径可与协同竞争——`electronic_analysis` spin>1 检查）。
- 误诊信号：① TS 两 σ 键长度悬殊（一根 ~1.6、一根 > 2.5）且 `<S^2>` 偏高 → 解离-复合分步面，不是协同 [3,3]；② IRC 两端接到同一物种（简并重排）属正常，不是失败；③ 势能面分叉（单个 TS 通多个产物，已有 Cope 分叉的计算报道）→ IRC 只给一条路径，产物比标注需动力学。

## [1,5]-H 与禁阻的 [1,2]/[1,3] σ 迁移

- [1,5]-H：键变化 = H 从 C1 断、与 C5 成；六元环状 suprafacial TS。`watch_pairs` = C1–H、H–C5；扫描坐标 = H–C5 缩短。TS 中 C–H···C 角大（> 140°，典型区间），两段 C···H 约 1.3–1.5 Å（Hammond 漂移）。预组织：C1 与 C5 须空间可达，`distance_filters` C1···C5 < 3.2 Å。
- [1,2]/[1,3]-H（碳骨架）：suprafacial 对称性禁阻，三元/四元环 TS ΔG‡ 通常 > 35 kcal/mol（典型区间），**假设图剪枝，不建协同边**。若机理必需：建分步路径——异裂/均裂成离子对或自由基对 → 片段复合（carbene/ylide 体系的 Stevens、[1,2]-Wittig 重排大量计算证据支持自由基对分步）。判别特征：分步面有成对中间体节点与笼内复合 TS；自旋布居/电荷分离可证。
- [1,3] antarafacial 几何可达性：仅在长链柔性体系勉强可能，TS 严重扭曲；算出来高垒就剪枝。
- 误诊信号：强行优化"协同 [1,3]-H TS"收敛出 2+ 虚频或塌缩 → 该面不存在此鞍点，改分步假设。

## ene 反应与螯变反应

- ene：键变化 = 新 σ 键（ene 端基–亲烯体端基）+ allylic H 迁移 + π 键移位。`watch_pairs` 三对：forming C–C、断 C–H、成 H–X。六元环状 TS；forming C–C 典型 2.1–2.5 Å、H 转移两端 1.2–1.5 Å（典型区间，常显著异步：C–C 成键晚于 H 迁移，反之亦有，随亲烯体漂移）。预组织：`distance_filters` forming 对 < 3.2 Å 且迁移 H 与受体 < 2.8 Å。竞争边：exo/endo 取向、 Lewis 酸催化变体（可能转两性离子分步）。分子内 retro-ene 类（β-羟基烯热解等）同框架处理。
- 螯变（挤出）：两根 σ 键在同一中心原子（S、N、C）上协同断裂，如 3-吡咯啉 N-亚硝基→N2、丁二烯砜→SO2。`watch_pairs` 两根断键 + 新生 π 键端基。扫描坐标 = 单根断键拉长（同步体系）。断键典型拉长至 2.2–2.8 Å（待核实，随挤出基团漂移）；强放热驱动（小分子 + 二烯生成）→ 早 TS。线性螯变（如 SO2 加成）要求挤出基团孤对轨道与二烯端基同面——TS 几何中挤出原子保持在二烯平面中垂线上。W–H：4n+2 二烯 + 挤出为允许线性螯变；环戊二烯酮→CO 等按同规则。
- 误诊信号：ene 扫描单调 → H 迁移无独立垒，可能坐标只拉了 C–C 未含 H，核对 `watch_pairs` 覆盖；螯变两断键严重不等长且 `<S^2>` 漂移 → 分步挤出（如某些 SO2 挤出经环状亚砜中间体），补中间体节点。

## Woodward–Hoffmann 规则的系统性剪枝用法

在假设图生成阶段（Step 0）执行，规则只做**剪枝与枚举**，不做能量裁决：

1. 数参与电子数（4n / 4n+2）→ 定热允许模式：环加成 [4+2] supra-supra、[2+2] 仅 supra-antara（几何多不可达）→ 剪协同热 [2+2]；电环化 4n 顺旋 / 4n+2 对旋；[1,j] 迁移 j=5 热 supra、j=3/7 热 antara（j=3 几何禁）→ 剪协同 [1,3]；ene/[1,5] 同属 6e 环状允许。
2. 光化学全部反转：禁阻热路径若实验条件含 hν，转入激发态假设而非直接丢弃。
3. 剪枝不是删除机理，而是删除**协同表示**：禁阻路径以逐步（diradical/两性离子/自由基对）形式重新入图。
4. 落地动作：被剪的边不进 `ts_guess` 队列；保留的允许模式每个立体变体（旋转方向、面、取向）一条边，ΔΔG‡ 裁决选择性。

## 领域级陷阱

- **异步协同 ≠ 逐步**：forming 键长差 0.3–1.0 Å 在周环 TS 中普遍且正常（尤其 1,3-偶极、杂原子 DA）；裁决靠 IRC 是否直连两端、有无中间体极小点、`<S^2>`，不靠键长差本身。
- **diradical 自旋污染系统性歪曲能垒排序**：协同 vs 逐步 diradical 竞争时，spin 污染使 diradical 能量虚高，校正可翻转结论（文献差值 2–8 kcal/mol 量级）；单参考结论必须标注。
- **激发态工具链边界**：光化学路径的锥形交叉、S1/S0 穿越超出"TS+IRC"范式，能做的是 TD-DFT 激发能 + T1 优化 + 基态面排除法；不要强行在 S0 面上"找到"光化学反应的 TS。
- **ambimodal/势能面分叉**：一个 TS 通多个产物时 IRC 验证必然"漏接"另一产物，这不是 TS 错误；产物分布需动力学（准经典轨迹）定性说明，超出常规闭环。
- **torquoselectivity 反直觉**：contrasteric 取代基（F、SiR3、CF3、带正电基团）电子性 inward，用位阻直觉预剪旋转方向会剪掉真实路径——两个方向永远都算。
- **泛函敏感性**：周环 TS 的几何与同步性对泛函（尤其色散、HF 交换比例）敏感，B3LYP 与 M06-2X 可给出不同异步程度；能垒报告注明泛函，重要结论用两个泛函交叉。

## 参考来源

- Sengupta, Li, Svatunek, Liu, Houk, "Cycloaddition Reactivities Analyzed by Energy Decomposition Analyses and the Frontier Molecular Orbital Model", Acc. Chem. Res. 2022, 55, 2467（畸变/相互作用与 FMO 框架）. https://pubs.acs.org/doi/10.1021/acs.accounts.2c00561
- Goldstein, Beno, Houk, "Density Functional Theory Prediction of the Relative Energies of Concerted and Stepwise Diels–Alder Reactions", J. Am. Chem. Soc. 1996, 118, 6036（协同 vs diradical 2.3–7.7 kcal/mol、spin 投影问题）. https://doi.org/10.1021/ja954149t
- Pham, Houk 等, "Diels–Alder Reactions of Allene with Benzene and Butadiene: Concerted, Stepwise, and Ambimodal Transition States", J. Org. Chem. 2014, 79, 8968. https://pmc.ncbi.nlm.nih.gov/articles/PMC4184448/
- Ess, Houk, "Theory of 1,3-Dipolar Cycloadditions: Distortion/Interaction and Frontier Molecular Orbital Models", J. Am. Chem. Soc. 2008, 130, 10187（SPAAC 畸变能 ~8 vs ~16 kcal/mol）. https://doi.org/10.1021/ja800009z
- Houk 等, "Origins of Inward Torquoselectivity by Silyl Groups and Other σ-Acceptors in Electrocyclic Reactions of Cyclobutenes", J. Am. Chem. Soc. 2008, 130, 2721. https://doi.org/10.1021/ja710192h
- Poddar 等, "Unraveling unusual torquoselectivity in ring-opening electrocyclic reactions: a DFT perspective", Phys. Chem. Chem. Phys. 2026, 28, 862. https://doi.org/10.1039/d5cp04207k
- Zhou 等, "A 21st Century View of Allowed and Forbidden Electrocyclic Reactions", J. Org. Chem. 2023（轨道对称-能垒现代观点）. https://pmc.ncbi.nlm.nih.gov/articles/PMC10804416/
- 1,3-偶极环加成机理共识（协同为主、可异步；逐步 diradical/dipolar 竞争）：爱丁堡大学博士论文综述章节. https://era.ed.ac.uk/bitstreams/94e608b3-2e02-461e-89c3-8dd2070eaa54/download
- Grossman, "The Art of Writing Reasonable Organic Reaction Mechanisms"（W–H 环加成速查表与螯变面选择性讨论）. https://m.shsbnu.net/pluginfile.php/38279/mod_resource/content/3/The%20Art%20of%20Writing%20Reasonable%20Organic%20Reaction%20Mechanisms.pdf
- MSU 虚拟有机化学教材：Pericyclic Reactions（[4+2] suprafacial 立体专一性与高阶环加成规则）. https://www2.chemistry.msu.edu/faculty/reusch/virttxtjml/pericycl.htm
