# 重排反应：机理可能性与建模

范围：底物骨架中一个基团（H/烷基/芳基）带电子对从**迁移起点**搬到邻位**迁移终点**的反应。按终点分类：碳正离子（Wagner–Meerwein、pinacol）、缺电子氮（Beckmann、Hofmann/Curtius/Lossen）、缺电子氧（Baeyer–Villiger、Hock/氢过氧化物）、缺电子碳/阴离子体系（Favorskii、[1,2]/[2,3]-Wittig、benzilic acid）。通用 SOP、五问题框架与能垒判读见 `mechanism-elucidation-sop.md` 与 `reaction-class-geometry.md`，本文件不重复。

所有数值为**典型区间（Å / kcal/mol），随底物、取代基、溶剂与催化模式漂移（Hammond）**，只用于初猜与筛选，裁决永远是频率 + IRC。

## 机理假设空间

| 变体 | 适用底物与条件 | 假设图骨架 | 判别特征（计算证据） |
| :--- | :--- | :--- | :--- |
| C1 分步碳正离子 1,2-shift | 能形成稳定碳正离子的底物（3°、苄基、烯丙基），SN1/E1 条件 | 底物 → [C–LG 异裂 TS] → 碳正离子 → [迁移 TS] → 重排碳正离子 | 存在碳正离子极小点；两个独立 TS；迁移步 ΔG‡ 通常 < 10 |
| C2 协同邻基参与 | 弱稳定碳正离子底物、强立体电子约束体系 | 底物 → [单一 TS：迁移∥离去] → 产物 | 无碳正离子极小点（优化即塌缩/迁移）；扫描单峰；迁移键在 TS 已部分成键 |
| C3 Pinacol / semipinacol | 邻二醇 + 酸；semipinacol 为 β-羟基-LG | 质子化二醇 → (C1 或 C2) → 质子化酮 → 去质子 | 分步 vs 协同由碳正离子稳定性裁决；含羰基重建（n_O→σ* 推动） |
| N1 Beckmann | 酮肟 + 强酸/活化剂 | 肟 → 活化（O-质子化/磺酰化）→ [迁移∥脱水] → nitrilium 离子 → 水解 → 酰胺 | anti 基团迁移（立体专一）；小底物可分步（σ/π 阳离子配合物），环状肟（环己酮肟）倾向协同 |
| N2 Hofmann/Curtius/Lossen（协同） | 酰胺+Br₂/碱、酰基叠氮 Δ、异羟肟酸活化 | 前体 → [迁移∥脱 N₂/CO₂/羧酸根 单一 TS] → 异氰酸酯 | 无 nitrene 极小点；**热 Curtius 主流为协同**（实验+DFT 共识） |
| N3 分步 nitrene | 光化学 Curtius、弱协同驱动力底物 | 前体 → [脱 N₂ TS] → **酰基 nitrene** → [迁移 TS] → 异氰酸酯 | 存在 nitrene 极小点；单重态 nitrene 稳定性差需 `stable=opt` 检查 |
| O1 Baeyer–Villiger | 酮 + 过氧酸（可加酸催化） | 酮+过氧酸 → [加成 TS] → **Criegee 中间体** → [迁移∥O–O 断 TS] → 酯/内酯 | 必含 Criegee 四面体节点；迁移步通常决速但**不预设**，两步都算 |
| O2 Hock / 氢过氧化物重排 | 氢过氧化物 + 质子酸/Lewis 酸 | 质子化 OOH → [芳基/烷基迁移∥O–O 异裂 TS] → oxocarbenium → 水解 | 迁移与 O–O 断裂协同；产物经 oxocarbenium 水解而非直接羰基 |
| A1 Favorskii（环丙酮路径） | α-卤代酮 + 碱，两侧均有 α-H | 卤代酮 → 烯醇盐 → [关环∥脱卤 TS] → **环丙酮** → 碱加成 → 开环 → 羧酸 | 对称环状底物缩环；存在环丙酮极小点；无 α′-H 时不可行 → 转 A2 |
| A2 quasi-Favorskii（semibenzilic） | 无 α′-H 的 α-卤代酮 | 碱加成 → 四面体中间体 → [1,2-shift∥脱卤 TS] → 产物 | 无环丙酮节点；迁移终点是羰基碳 |
| A3 [1,2]-Wittig | α-烷氧基碳负离子（强碱） | 碳负离子 → [C–O 均裂] → **自由基对** → 笼内重组 → 醇盐 | 协同 [1,2] 对称性禁阻——不建协同边；须 `electronic_analysis` spin≥2 验证自由基对 |
| A4 [2,3]-Wittig | 烯丙基醚 α-碳负离子 | 碳负离子 → [五元 envelope TS 单一协同] → 高烯丙醇盐 | 热允许协同；envelope 构象决定立体化学；与 A3 竞争边必建 |
| A5 Benzilic acid | 芳基 1,2-二酮 + OH⁻（无 α-H） | 二酮 → [OH⁻ 加成] → 四面体中间体 → [1,2-芳基迁移 TS] → 质子接力 → α-羟基羧酸盐 | 加成-迁移-质子接力多步；环状二酮缩环；迁移终点为羰基碳（部分正电） |

## C1 分步碳正离子 1,2-shift（Wagner–Meerwein）

- **键变化**：第一步 C–LG 断；第二步迁移基团 M 的 M–C_origin 断、M–C_terminus 成。`watch_pairs` = (M–C_origin, M–C_terminus, C_origin–LG)。扫描坐标：迁移步首选 M–C_terminus（缩短）。
- **预组织**：迁移基团与终点相邻即可，无强取向要求；但 C–LG 需先异裂。`distance_filters`：M–C_terminus ≤ 3.0 Å（保证邻位），C_origin–C_terminus 1.4–1.6 Å。
- **TS 期望**：迁移 TS 为**三中心桥式**，M 同时与两碳部分键合，M–C 两键典型 1.8–2.3 Å（Hammond：生成更稳定碳正离子 → 早 TS、键变化小）。桥式结构本身可能是极小点而非 TS（如非经典碳正离子）——IRC 端点裁决。
- **竞争边**：不同迁移基团各一条边（迁移能力近似 H ≈ 芳基 > 3° > 2° > 1° > CH₃，漂移大、受条件反转）；E1 消除边；溶剂/亲核试剂捕获边。
- **误诊信号**：优化"碳正离子中间体"时迁移自动发生（无垒）→ 实际是 C2 协同；迁移 TS 上 M–C_terminus 的 Mayer 键级 < 0.1 → 坐标或假设错。

## C2 协同邻基参与（无自由碳正离子）

- **键变化**：M–C_origin 断、M–C_terminus 成、C_origin–LG 断，三者同一 TS。`watch_pairs` 同上三对。扫描坐标：M–C_terminus 缩短为主坐标；异步明显时用 `ts_guess` interpolate 走 NEB。
- **预组织**：立体电子核心是 σ(M–C_origin)→σ*(C–LG) 的 **anti-periplanar** 对齐；二面角 M–C_origin–C_terminus–LG ≈ 180（可接受约 150–180，漂移）。`conformer_search` 用 `distance_filters` 锁 M–C_terminus ≤ 3.0 Å，再用 `internal_coordinates` analyze 核对二面角；不满足的构象直接丢弃。
- **TS 期望**：C_origin–LG 典型 2.0–2.6 Å，M 桥式两键 1.9–2.4 Å（随 LG 离去性与迁移能力漂移）。强吸热迁移 → 晚 TS。
- **竞争边**：C1 分步（两条都建，由碳正离子极小点存在性裁决）；消除；不同迁移基团。
- **误诊信号**：扫描出现平台/双峰 → 实际存在浅碳正离子谷（转 C1 建模）；虚频模式只有 LG 伸缩而无 M 迁移分量 → 找到的是异裂 TS 而非迁移 TS。

## C3 Pinacol / semipinacol

- **键变化**：脱水（C–OH₂ 断）+ M 迁移 + 邻位 O 孤对重建 C=O（n_O→σ* 推动是驱动力）。`watch_pairs` 加 (C_origin–O) 观察羰基化（1.5 → ~1.2 Å）。扫描坐标：协同变体扫 C_origin–OH₂ 或 M–C_terminus。
- **预组织**：迁移基团与离去水需 anti-periplanar（同 C2 谓词）；semipinacol 中立体电子约束常压倒迁移能力排序——先筛构象再谈选择性。
- **TS 期望**：参照 C1/C2；稳定碳正离子可达（叔、苄位）时分步可行，否则协同。计算教学研究共识：**能形成稳定碳正离子→分步，不能→协同**，两条边都建。
- **竞争边**：两个羟基质子化位点各一条（区域选择性来源）；每个可迁移基团一条；半频哪醇环扩张（环烷基迁移）。
- **误诊信号**：区域选择性预测与实验相反 → 漏了另一质子化位点的边；羰基 O 在 TS 仍为单键特征（Mayer 键级 ~1）→ n_O→σ* 未参与，构象错。

## N1 Beckmann 重排

- **键变化**：迁移基团 M 从 C 到 N（M–C 断、M–N 成），N–O 断（脱水/脱磺酸根），C=N → C≡N⁺（nitrilium）。`watch_pairs` = (M–C, M–N, N–O)。扫描坐标：M–N 缩短或 N–O 拉长。
- **预组织**：**anti 于 N–O 的基团迁移**（立体专一性来源）；肟 E/Z 异构体各建一条边。`distance_filters`：M–N ≤ 3.0 Å；用 `internal_coordinates` 核对 C=N–O 构型。
- **TS 期望**：迁移 M–N 典型 1.9–2.4 Å，N–O 2.0–2.6 Å（随活化方式漂移）。文献共识：**环己酮肟倾向协同**；丙酮肟、苯乙酮肟等小底物可经 σ/π 阳离子配合物分步，**且强烈依赖溶剂/酸簇**——显式 1–3 个酸/水分子常决定路径形态。
- **竞争边**：协同 vs 分步（σ-配合物）；E/Z 肟两条边；nitrilium 水解回酮的副路径；Beckmann 断裂（腈 + 碳正离子，α 位季碳底物时）。
- **误诊信号**：裸肟+单质子模型下路径怪异/能垒 > 40 → 缺显式酸簇，质子接力未建模；IRC 端点落到酮+水 → 走的是水解边而非迁移边。

## N2/N3 Hofmann / Curtius / Lossen（协同 vs nitrene）

- **键变化**：M 从 C 到 N（M–C 断、M–N 成），协同变体同时 N–LG 断（N₂、CO₂/羧酸根、Br⁻）。`watch_pairs` = (M–C, M–N, N–LG)。扫描坐标：N–LG 拉长（脱 N₂ 是强驱动力，常为主坐标）。
- **预组织**：无强构象要求（链状底物）；酰基叠氮取 N–N–N 近平面构象即可。`distance_filters`：M–N ≤ 3.0 Å。
- **TS 期望**：N–N₂ 在 TS 典型 1.8–2.3 Å，M–N 2.0–2.4 Å（待核实，随底物漂移）；热 Curtius ΔG‡ 典型 25–35 kcal/mol（漂移）。**判别逻辑**：先用 `ts_guess` interpolate 分别试协同与"先脱 N₂"两条路径——若酰基 nitrene 优化得到真实极小点且其迁移有独立 TS → N3 分步；若 nitrene 优化直接塌缩到异氰酸酯 → N2 协同。热 Curtius/Hofmann/Lossen 文献主流为协同；光化学 Curtius 常见 nitrene。
- **竞争边**：协同 vs nitrene 分步（必建）；nitrene 的单/三线态（`electronic_analysis` spin≥2，比较相对能量）；异氰酸酯水解/醇解捕获边。
- **误诊信号**：nitrene 单重态波函数不稳定（`stable=opt` 报告非稳）→ 单参考能量不可信，结论标注；协同 TS 的 IRC 一端接出 N₂ 已完全游离的弱络合物 → 接近分步边界，补扫 M–N 坐标确认。

## O1 Baeyer–Villiger

- **键变化**：第一步过氧酸 O–H 的羰基 O 加成 C=O（Bürgi–Dunitz 角 ≈ 107，谓词见 `mechanisms/carbonyl.md` 直接亲核加成节）生成 Criegee 中间体；第二步 M 从 C 到端基 O（M–C 断、M–O 成）、O–O 断、羰基重建。`watch_pairs` = (M–C, M–O_terminal, O–O)。扫描坐标：迁移步扫 M–O 或 O–O。
- **预组织**：两条立体电子约束都须满足——**迁移基团与 O–O 键 anti-periplanar**（一级立体电子效应，σ_M–C→σ*_O–O）；**羟基 O 孤对与迁移基团 anti**（二级效应）。`conformer_search`：Criegee 中间体上 `distance_filters` 锁 M–O_terminal ≤ 3.2 Å，`internal_coordinates` 核对 M–C–O–O 二面角 ≈ 180（可接受约 150–180）。
- **TS 期望**：迁移 TS 中 O–O 典型 1.8–2.2 Å，M–O 2.0–2.5 Å，M 带部分正电（漂移）。迁移步通常决速，但无酸催化时加成步也可决速——**两步两个 TS 都算再裁决**。
- **竞争边**：每个可迁移基团一条边（能力近似 3° > 2° ≈ 苄基 > 苯基 > 1° > CH₃，芳环给电子取代加速）；酸催化 vs 非催化路径（质子穿梭显著降低加成步能垒）。
- **误诊信号**：预测迁移基团与实验相反 → 检查是否建错了 Criegee 构象（立体电子约束未满足的优势迁移基团会被"能迁移"的基团顶替）；迁移扫描单调 → 换扫 O–O。

## O2 Hock / 氢过氧化物重排

- **键变化**：质子化 OOH 后，M（常为芳基）从 C 到近端 O（M–C 断、M–O 成）与 O–O 异裂**协同**；产物为 oxocarbenium + 水/酚。`watch_pairs` = (M–C, M–O, O–O)。扫描坐标：O–O 拉长。
- **预组织**：M 与 O–O 需 anti 对齐（同 BV 谓词，M–C–O–O 二面角 ≈ 180）。`distance_filters`：M–O ≤ 3.2 Å。
- **TS 期望**：O–O 在 TS 典型 1.9–2.4 Å，M–O 2.0–2.5 Å（漂移）；酸催化 ΔG‡ 典型 15–25 kcal/mol（漂移）。Lewis 酸与质子酸路径几何不同（配位数差异），按实际催化剂建模。
- **竞争边**：不同迁移基团；oxocarbenium 被水/分子内羟基捕获的后续边；酸解副反应（自由基 O–O 均裂为竞争路径，spin≥2 检查）。
- **误诊信号**：oxocarbenium 极小点找不到、直接水解 → 建模缺了显式水；Mayer 键级显示迁移基团在 TS 无 partial bond → 对齐构象错。

## A1/A2 Favorskii 与 quasi-Favorskii

- **键变化**（A1 环丙酮路径）：烯醇盐 Cα′–Cα 关环成键 + Cα–X 断 → 环丙酮；然后 OH⁻ 加成 + C–C 开环。`watch_pairs` = (Cα′–Cα, Cα–X)；开环步 `watch_pairs` = (O–C_carbonyl, 断裂的 C–C)。（A2）：OH⁻ 加成后 M 1,2-shift 到羰基碳 + C–X 断。
- **预组织**：关环要求烯醇盐双键与 C–X 同侧（顺式取向）。`distance_filters`：Cα′–Cα ≤ 3.0 Å。
- **TS 期望**：关环 TS 中 Cα′–Cα 典型 2.0–2.4 Å，C–X 2.2–2.8 Å（漂移）。环丙酮节点应力能高，**确认它是真极小点**（全正频率）；其价互变异构体 oxyallyl 为单重态双自由基特征——若怀疑 oxyallyl 参与，单参考 DFT 结论打折，做 `stable=opt`。
- **竞争边**：A1 vs A2（数 α′-H 决定）；烯醇化 vs 直接加成；环状底物缩环取向两条边；酸碱条件下羟醛副反应（脂肪族底物）。
- **误诊信号**：烯醇盐关环能垒 > 35 → 底物可能走 A2；环丙酮"中间体"优化塌缩 → 协同 quasi 路径；裸阴离子气相能垒异常低/高 → 缺显式溶剂/抗衡离子（见陷阱）。

## A3/A4 [1,2]-Wittig 与 [2,3]-Wittig

- **键变化**（A3）：C–O 均裂 → 自由基对 → M–C 重组。`watch_pairs` = (M–O, M–C_new)。（A4）：五元 envelope TS 中 O–C_allyl 断、C_carbanion–C_allyl 成。`watch_pairs` = (O–C_allyl, C_carbanion–C_allyl 末端)。扫描坐标（A4）：forming C–C 缩短。
- **预组织**（A4）：烯丙基与碳负离子需构成五元环几何。`distance_filters`：C_carbanion–C_allyl_末端 ≤ 3.2 Å；envelope 取向决定立体化学，多个 envelope 构象各建边。
- **TS 期望**（A4）：forming C–C 与 breaking O–C 典型均 2.0–2.4 Å（漂移）；阴离子加速，能垒通常明显低于对应中性 [2,3]。A3 **不要建协同 [1,2] 边**（suprafacial 对称性禁阻，交叉引用 `mechanisms/pericyclic.md` [1,5]-H 与禁阻的 [1,2]/[1,3] σ 迁移节）；建模走 C–O 均裂扫描 + 自由基对重组，`electronic_analysis` spin≥2 验证自旋布居与 `<S²>`。
- **竞争边**：A3 vs A4（烯丙基醚两类都建，能垒裁决）；A3 笼内重组 vs 自由基逃逸（溶剂笼效应用系综/显式溶剂粗评）；阴离子稳定性差时 [2,3] 可走异裂分步（Haeffner 等 DFT 工作）。
- **误诊信号**：A4 TS 出现显著自旋布居/双自由基特征 → 机制滑向 A3；`⟨S²⟩` 偏差 ≳0.1 → 按 `method-selection.md` 打折能垒结论并诊断（实用触发器，非自动 fail）。

## A5 Benzilic acid 重排

- **键变化**：OH⁻ 加成 C=O（四面体中间体）→ M（芳基）1,2-shift 到邻位羰基碳 + 供体羰基重建 → 质子接力成羧酸盐。`watch_pairs` = (O_oh–C, M–C_donor, M–C_acceptor)。扫描坐标：迁移步 M–C_acceptor 缩短。
- **预组织**：加成后需绕 C–C 旋转把 M 摆到迁移位（文献：加成、旋转、迁移、质子接力四事件）。`distance_filters`：M–C_acceptor ≤ 3.0 Å。
- **TS 期望**：迁移终点只是**部分正电的羰基碳**（非完整碳正离子），迁移 TS 较晚、M 带部分正电荷（计算示例甲基迁移电荷 +0.22，待核实量级）；M–C 两键典型 1.9–2.4 Å（漂移）。建议显式 3–4 个水分子承载 OH⁻ 与质子接力。
- **竞争边**：迁移 vs 四面体中间体直接解离；环状 1,2-二酮缩环取向；烷氧基亲核试剂 → benzilic ester 变体；有 α-H 时羟醛副反应边。
- **误诊信号**：不加显式水时质子接力步能垒 > 35 → 直接 [1,2]/[1,3]-H 迁移禁阻/高垒，必须走溶剂接力（交叉引用 `reaction-class-geometry.md` §3.1）；IRC 接回二酮+OH⁻ → 加成-解离占优，迁移边需重新预组织。

## 领域级陷阱

1. **协同 vs 分步是本领域的第一判别问题**，且答案随底物翻转（Beckmann：环己酮肟协同、小肟分步；Curtius：热协同、光分步；pinacol：稳碳正离子分步、否则协同）。判别证据 = 中间体极小点存在性 + IRC 端点，**不是靠扫描峰数**（平台/肩峰会骗人）。
2. **立体电子约束（anti-periplanar）没预组织就硬扫是本领域最大浪费源**：BV 的 M–C–O–O、semipinacol 的 M–C–C–LG、Hock 的 M–C–O–O 二面角必须先在 `conformer_search`/`internal_coordinates` 层面锁定；不满足约束的构象上扫出来的"迁移 TS"全是错的。
3. **阴离子重排的环境与基组**：溶液结论需适当溶剂化，涉及抗衡离子/质子穿梭时显式建模；气相任务保留气相定义。几何/能量检查弥散函数需求；不能仅为布居/键级分析而删掉描述阴离子所需的弥散函数，见 `method-selection.md` §2。
4. **质子位置与酸簇决定路径**（Beckmann 的 N- vs O-质子化、BV 的催化 vs 非催化）：质子化异构体是不同的反应物，各建节点；显式 1–3 个酸/水分子常把"不可能的能垒"变为合理值。
5. **开壳层中间体漏检**：nitrene、oxyallyl、[1,2]-Wittig 自由基对都可能是单重态双自由基——做单重态稳定性检查（`stable=opt`）与 `electronic_analysis` 自旋布居；不稳定则单参考 DFT 能垒只作定性参考。
6. **桥式/π-配合物中间体漏建**：芳基迁移可经 phenonium 型桥式结构、Beckmann 可经 σ/π 配合物——IRC 端点出现非预期物种时，优先怀疑漏了这类节点，而不是计算失败。

## 参考来源

- Yamabe et al., "Is the Beckmann Rearrangement a Concerted or Stepwise Reaction? A Computational Study", J. Org. Chem. 2005. DOI: 10.1021/jo0508346
- Ring Size and Substituent Effects in the Beckmann Rearrangement, ChemRxiv. https://chemrxiv.org/doi/pdf/10.26434/chemrxiv.15000860
- Tarwade et al., "The Curtius Rearrangement of Cyclopropyl Azides" (实验+DFT，热 Curtius 协同性), PMC. https://pmc.ncbi.nlm.nih.gov/articles/PMC2653059/
- Kishi et al., "A theoretical assessment of Curtius rearrangement of malonyl azide", J. Mol. Liq. 2024. https://www.sciencedirect.com/science/article/abs/pii/S0167732224001338
- Name Reactions for Homologations (Curtius 机理史料：nitrene 捕捉失败、KIE 证据). http://chemistry-chemists.com/chemister/Mechanizms/name-reactions-for-homologations-partII-2009.pdf
- Alvarez-Idaboy et al., BV 机理 DFT/速率常数工作（MPWB1K 与实验速率吻合）. https://www.researchgate.net/publication/8245218
- Noyori 刚性双环底物 BV 立体电子效应（anti 迁移证据），综述转引. https://core.ac.uk/download/pdf/36425744.pdf
- Stereoelectronic and steric effect in the BV rearrangement of steroidal α-chlorocyclobutanones, Tetrahedron 2015. https://www.sciencedirect.com/science/article/pii/S004040201201304X
- Theoretical Investigation of the Mechanism of the Hock Rearrangement with InCl₃ as Catalyst, ChemRxiv. https://chemrxiv.org/engage/api-gateway/chemrxiv/assets/orp/resource/item/6426ef74db1a20696e4dfc8a/original/theoretical-investigation-of-the-mechanism-of-the-hock-rearrangement-with-in-cl3-as-catalyst.pdf
- Yudin et al., "Rearrangements of organic peroxides and related processes", Beilstein J. Org. Chem. 2016. https://pmc.ncbi.nlm.nih.gov/articles/PMC4979652/
- Zhao et al., 频哪醇重排机理与迁移规律的计算教学研究（分步 vs 协同判据）, 大学化学. https://www.dxhx.pku.edu.cn/CN/article/downloadArticleFile.do?attachType=PDF&id=38017
- PM3 研究 Wagner–Meerwein 迁移能力排序（非环 pinacol 体系）. https://link.springer.com/article/10.1007/BF02708200
- The [1,2]- and [1,4]-Wittig rearrangement（自由基对机理综述）, Tetrahedron/Chem 2022. https://www.sciencedirect.com/science/article/abs/pii/S0040402019312657
- Haeffner et al., "Concerted rearrangement versus heterolytic cleavage in anionic [2,3]- and [3,3]-sigmatropic shifts. A DFT study", J. Org. Chem. 2003. DOI: 10.1021/jo0268761
- Kang et al., "The catalytic enantioselective [1,2]-Wittig rearrangement cascade of allylic ethers"（[1,2] 对称性禁阻、[2,3] 协同 DFT）, Nat. Chem. 2025. https://www.nature.com/articles/s41557-025-02022-4
- Yamabe et al., "A FMO-controlled reaction path in the benzil-benzilic acid rearrangement"（加成、旋转、迁移、质子接力四事件）. https://pubmed.ncbi.nlm.nih.gov/16496961/
- A computational study of base-catalyzed reactions of cyclic 1,2-diones. https://www.sciencedirect.com/org/science/article/pii/S1860539721000426
- Grossman, The Art of Writing Reasonable Organic Reaction Mechanisms（Favorskii 环丙酮/oxyallyl、benzilic 半频哪醇类比）. 教材
- 烷氧基稳定 oxyallyl 的 DFT 与捕捉实验（Favorskii oxyallyl 单重态双自由基基态）, Synlett 2014. https://www.thieme-connect.com/products/ejournals/html/10.1055/s-0034-1379490
