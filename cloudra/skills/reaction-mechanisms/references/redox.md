# 氧化还原：机理可能性与建模

章节读取：同技能参考用 `get_skill(skill_name="reaction-mechanisms", reference="<文件名>.md")`；下文链接的通用计算参考用 `get_skill(skill_name="dft-calculation", reference="<文件名>.md")`。

范围：底物与氧化剂/还原剂之间发生形式氧转移、氢（氢化物/氢原子/质子+电子）转移的反应结果——烯烃环氧化、双羟化、醇氧化、羰基与烯还原、C–H 氧化。同一净结果常有多条机理通道（协同氧转移 vs 金属杂环 vs 自由基逐步；直接氢化物转移 vs 表面加氢 vs 环状氢转移），agent 必须先枚举假设再让能垒与电子结构裁决。通用流程见 [mechanism-elucidation-sop.md](../../dft-calculation/references/mechanism-elucidation-sop.md)；五问题框架与通用几何见 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md)；质子穿梭见 [reaction-class-geometry.md](../../dft-calculation/references/reaction-class-geometry.md) §3.1，自由基工作流见 [radical.md](radical.md)（本文不重复展开）。

## 机理假设空间

| 变体 | 适用底物与条件 | 假设图骨架（节点→边） | 判别特征（计算证据） |
| :--- | :--- | :--- | :--- |
| 过酸协同氧转移（Prilezhaev） | 烯烃 + mCPBA 等过酸 | 反应物 → [协同蝴蝶 TS] → 环氧 + 羧酸 | 单 TS 一步；H 同步转移到羰基 O；无中间体 |
| 双氧酮氧转移 | 烯烃 + DMDO/TFDO | 反应物 → [spiro TS] → 环氧 + 酮 | 单 TS；两个 forming C–O 键，spiro 取向 |
| d⁰ 金属过氧物种 Sharpless 型氧转移 | 烯烃 + H₂O₂/tBuOOH，Mo/W/V/Re/Ti 催化 | 活性过氧物种 → [亲电 O 转移 TS] → 环氧 + 再生催化剂 | 进攻沿 σ*(O–O)；无 M–C 键形成；立体专一保持 |
| Mimoun 型金属杂环（基本被淘汰） | 同上（历史假设） | 烯烃配位 → [[3+2] 金属杂环中间体] → 还原消除 → 环氧 | 中间体含 M–C 键（Mayer 键级可验）；与立体专一性矛盾 |
| 金属氧代环氧化（协同 vs 自由基逐步） | 烯烃 + Mn(salen)/卟啉氧代 | 氧代物种 → [O 转移 TS] →（碳自由基中间体）→ 环氧 | cis 烯出 trans 环氧 = 自由基逐步；查自旋布居与旋转 |
| OsO₄ [3+2] 双羟化 | 烯烃 + OsO₄（± 胺配体） | 反应物 → [[3+2] TS] → 环状锇酸酯 → 水解 → 顺式二醇 | 一步成两根 C–O；osmaoxetane 不在路径上 |
| OsO₄ [2+2]→重排（竞争边） | 同上 | 反应物 → [[2+2] TS] → osmaoxetane → [迁移 TS] → 锇酸酯 | 四元环含 Os–C 键；多一个中间体节点 |
| Swern 氧化 | 醇 + DMSO/草酰氯或 TFAA，碱，−78 °C | 活化 → 烷氧基锍盐 → 硫叶立德 → [五元环 Ei TS] → 羰基 | 决速步可为去质子化而非消除；锍盐/叶立德为实测中间体 |
| Dess–Martin（高价碘）氧化 | 醇 + DMP，中性室温 | 配体交换（烷氧基碘烷）→ [环状 α-H 转移 TS] → 羰基 | I–O(醇) 键形成先于 H 转移；无叶立德 |
| 金属催化脱氢 / Oppenauer | 醇 + 金属（Ru/Ir/Al），授体酮 | 烷氧基络合 → [β-氢消除 或 六元环氢转移 TS] → 羰基 + M–H | 需空配位/agostic 预组织 vs 直接六元环 TS，二选一 |
| 硼氢化物氢转移（NaBH₄ 等） | 醛酮 + BH₄⁻，质子性溶剂 | 羰基 → [氢转移 TS] → 烷氧基硼（可继续转移，共 4 个氢） | Bürgi–Dunitz 进攻角；Na⁺/溶剂配位降垒 |
| 催化氢化（表面，Horiuti–Polanyi） | 烯/羰基 + H₂，Pd/Pt/Ni 多相 | H₂ 解离吸附 → 烯 π 吸附 → 逐次加 H → 脱附 | 表面机理，分子簇近似有系统性偏差（见陷阱） |
| MPV 直接氢转移 | 醛酮 + Al(OⁱPr)₃ / iPrOH | 双配位络合物 → [六元环 TS] → 醇 + 丙酮 | 供受体同配位于 Lewis 酸；单步协同 H 转移 |
| 转移氢化 inner-sphere | 酮 + Ru/Ir，iPrOH 或甲酸 | 烷氧基络合 → β-氢消除 → M–H → 羰基插入 → 产物 | 羰基须配位金属；有 M–H 中间体节点 |
| 转移氢化 outer-sphere（Noyori 双功能） | 酮/亚胺 + Ru–H/N–H 催化剂 | 18e 氢化物 → [六元环周环 TS（H⁻/H⁺ 同步）] → 醇 + 16e 酰胺 | 底物不配位金属；N–H 参与 TS；无空配位要求 |
| 金属氧代 HAT-回弹 | C–H + Feᴵⱽ=O / Mnⱽ=O（P450、非血红素） | 氧代物种 → [HAT TS] → M–OH + 碳自由基 → [回弹 TS] → 醇 | 自由基笼内中间体；回弹快 → 构型保持；两态反应性 |
| HAT-非回弹 / 脱饱和 | 同上（合成非血红素体系常见） | HAT → 自由基逃逸笼（扩散/重排/第二次夺氢 → 烯） | 立体化学打乱、自由基钟开环、脱氢副产物 |

## 过酸协同氧转移（Prilezhaev）

- 键变化：forming O(peracid 远端)–C ×2、breaking O–O、O–H→O=C 内质子转移。`watch_pairs`：远端 O 与两个烯碳、O–O、H–O(carbonyl)。首选扫描坐标：O–O（拉长）或 forming O–C（缩短），单坐标通常够。
- 预组织：过酸取分子内氢键构象（plane/spiro 之争：spiro 蝴蝶 TS 即过酸平面与烯垂直）——`distance_filters`：远端 O 到两烯碳均 2.0–3.0 Å；烯丙醇底物加 Henbest 氢键谓词 O–H···O(peracid) ≤ 2.2 Å。
- TS 期望：spiro 取向优于 planar（典型差 ~3–6 kcal/mol，随底物与泛函漂移，源自 n_O(羰基)→σ*(O–O) 次级相互作用）；forming C–O 约 1.9–2.3 Å、breaking O–O 约 1.9–2.2 Å；富电子烯 → 早 TS（Hammond）。典型 ΔG‡ 约 15–25 kcal/mol（漂移大）。
- 必须并建：Re/Si 面两条边；烯丙醇底物 Henbest（H 键导向）vs 位阻面两条边；双氧酮/金属催化条件下不要建此边。
- 误诊信号：TS 优化塌缩出 planar 且能量反而更低 → 检查泛函（早期纯泛函偏好 planar，换杂化泛函复算）；扫描双峰 → 先形成氢键络合物，分段处理。

## 双氧酮氧转移

- 键变化：forming 远端 O–C ×2、breaking O–O。`watch_pairs` 同上（无质子转移）。
- 预组织：`distance_filters` 远端 O 到两烯碳 2.0–3.0 Å；spiro 取向（双氧酮环平面 ⊥ 烯平面）为低垒通道。
- TS 期望：forming C–O 约 2.0–2.3 Å；缺电子烯明显异步（两 forming 键差可达 0.5 Å 以上，Hammond/极性漂移）。典型 ΔG‡ 约 10–20 kcal/mol。
- 必须并建：spiro vs planar 两条边（实验标志性选择性来自 spiro）；两面进攻。
- 误诊信号：planar TS 虚频模式含面内摇摆 → 高阶鞍点风险，verify 确认恰好 1 虚频；电子极其不对称时检查是否已滑向单电子转移/自由基离子对（`electronic_analysis` 查自旋布居）。

## d⁰ 金属过氧物种 Sharpless 型氧转移

- 适用范围：Mo/W/V/Re/Ti（d⁰）+ H₂O₂ 或烷基过氧化氢；活性种是 η²-过氧（或氢过氧）络合物，不是自由 H₂O₂——**先确定活性种结构再建边**。
- 键变化：forming O(过氧远端，亲电)–C ×2、breaking O–O；M–O 键基本保持。`watch_pairs`：远端 O–C ×2、O–O、M–O。
- 预组织：烯从 σ*(O–O) 反方向接近（沿 O–O 轴背侧），`distance_filters`：远端 O 到两烯碳 2.2–3.2 Å；烯丙醇底物（Sharpless 环氧化）另有烷氧基配位导向，先建底物-催化剂络合物节点。
- TS 期望：forming C–O 约 2.0–2.4 Å（典型区间，随金属与配体漂移）；金属越 Lewis 酸、过氧 O 越亲电 → 越早 TS。
- 必须并建：Mimoun 金属杂环边（下节）作判别；供体配体配位/解离异构体各一条边。
- 误诊信号：TS 上 M–C 出现 partial bond（Mayer > 0.1）→ 已滑向 Mimoun 路径；IRC 接到金属杂环而非环氧 → 该体系 Mimoun 边才是真的。

## Mimoun 型金属杂环（判别用竞争边）

- 键变化：forming M–C 与 O–C（[3+2] 成五元金属杂环），随后还原消除成 C–O。`watch_pairs`：M–C、O–C、M–O。
- TS/中间体期望：金属杂环中间体应出现明确 M–C 键（Mayer 键级 0.3–1.0，典型区间）。
- 判别逻辑：Mo/W/V/Re 体系实验与理论证据压倒性排除 Mimoun（速率与过酸体系平行、无金属杂环特征）；**此边的价值是判别而非主假设**——若 Sharpless 边 IRC 连到杂环或杂环中间体能量显著低于反应物，说明该体系例外，如实记录。
- 误诊信号：找不到金属杂环极小点（优化塌缩成环氧）→ 与共识一致，剪掉此后边。

## 金属氧代环氧化（协同 vs 自由基逐步）

- 键变化：forming O(oxo)–C；若逐步，先成一根 C–O 得碳自由基/阳离子中间体，C–C 旋转后再关环。`watch_pairs`：O–C ×2、M=O。
- 预组织：侧向接近（side-on），烯 π 面向 oxo；`distance_filters`：O 到近端烯碳 2.2–3.0 Å。
- TS 期望：协同 TS forming C–O 约 1.9–2.3 Å（漂移大）；多自旋态（Mn/Fe 体系 S=0/1/2 各建一条边，两态反应性下决速 TS 不一定在基态自旋面）。
- 必须并建：协同 vs 自由基逐步两条边；各自旋态；逐步路径的关环边。
- 误诊信号（机理探针）：cis 烯实验出 trans 环氧 = 逐步（中间体 C–C 旋转）；计算上第一 TS 后 IRC 落到开壳层中间体且关环垒 < 5 kcal/mol → 立体保持由关环与旋转的相对速率决定，不能只报 TS。

## OsO₄ [3+2] 双羟化

- 键变化：forming C–O ×2（两个 oxo 各成一根），Os 由 VIII 还原为 VI。`watch_pairs`：两根 forming C–O、Os=O ×2。首选扫描坐标：一根 forming C–O（同步性好时单扫够）。
- 预组织：烯面向 OsO₄ 的两个 oxo（η² 取向）；`distance_filters`：两个 O 到对应烯碳均 2.2–3.2 Å。胺配体加速体系先建 5/6 配位络合物节点。
- TS 期望：forming C–O 约 2.0–2.4 Å（典型区间，随底物漂移）；通常近同步、略异步；立体化学 syn 加成被环状酯锁死。典型 ΔG‡ 约 10–20 kcal/mol（配体加速可降低）。
- 必须并建：[2+2]→osmaoxetane 边（下节）；Re/Si 面；锇酸酯水解边（配体置换，通常低垒但决速角色随条件变）。
- 误诊信号：[3+2] 扫描无峰/塌缩 → 核对活性种（OsO₄ vs OsO₄L）；产物反式 → 不可能是 OsO₄ 路径，检查是否混入其他氧化剂机理。

## OsO₄ [2+2]→osmaoxetane 重排（判别用竞争边）

- 键变化：第一步 forming Os–C 与 C–O（四元 osmaoxetane）；第二步 Os–C 迁移插入另一 oxo 成锇酸酯。`watch_pairs`：Os–C、C–O、迁移的 Os–C/O–C。
- 判别逻辑：1977 年 Sharpless 提出（环张力论据），Corey 以动力学与同位素证据反驳；DFT（Norrby/Houk 等）一致支持 [3+2] 更低。**建此边是为了裁决**：osmaoxetane 含明确 Os–C 键（`electronic_analysis` 键级），[3+2] 路径任何结构都不应有 Os–C partial bond。
- 误诊信号：osmaoxetane 优化存在且重排垒 < [3+2] 垒 → 认真对待（底物/配体例外体系如实报告两条路径的 ΔΔG‡）。

## Swern 氧化

- 假设图骨架：DMSO 活化（预平衡）→ 烷氧基锍盐中间体 → 碱夺 α-硫甲基氢 → 硫叶立德 → 五元环 Ei 消除（Cα–H 转移到叶立德碳，断 S–O，成 C=O）→ 羰基 + Me₂S。
- 键变化（消除步）：breaking Cα–H、S–O；forming C=O、H–C(ylide)。`watch_pairs`：Cα–H、H–C(ylide)、S–O、C–O。扫描坐标：H–C(ylide)（缩短）。
- 预组织：五元环 Ei 几何（S–C(ylide)···H–Cα–O 成环）；`distance_filters`：叶立德 C 到醇 α-H 1.5–2.5 Å。
- TS 期望：转移的 H 大致在 Cα 与 C(ylide) 之间（各约 1.3–1.6 Å，待核实，随碱强度漂移）。
- 必须并建：**决速步可能是去质子化而非消除**（苄醇体系实测如此，与教科书背离）——去质子化边与消除边都算再裁决；不同活化剂（草酰氯 vs TFAA）给不同锍盐前体，预平衡节点照实建。
- 误诊信号：只算消除步且 ΔG‡ 与实验速率矛盾 → 回查前面节点；MTM 醚副产物对应另一竞争边（α-夺取醇氧上氢）。

## Dess–Martin（高价碘）氧化

- 假设图骨架：醇 O 置换 DMP 上醋酸根（配体交换，预平衡）→ 烷氧基高碘烷 → 环状 TS 将 α-H 转移到配位氧（醋酸根羰基 O），断 I–O → 羰基 + I(III) 副产物。
- 键变化：breaking Cα–H、I–O；forming C=O、O–H。`watch_pairs`：Cα–H、H–O(醋酸根)、I–O、C–O。
- 预组织：环状 TS 要求 α-H 指向受体氧；`distance_filters`：受体 O 到 α-H 1.5–2.5 Å（环大小 5–7 元随配位模式变，待核实）。
- TS 期望：H 部分转移（典型区间同 Swern 消除步，Hammond 随底物酸性漂移）；高价碘中心配位数变化是几何优化常见难点，先 `internal_coordinates` 体检配位层。
- 必须并建：二醇底物的环状双烷氧基中间体 → C–C 断裂边（氧化裂解副反应）；配体交换步本身（可为决速）。
- 误诊信号：直接把游离醇 + DMP 当反应物扫 → 漏了配体交换节点，扫描无峰是预期结果。

## 金属催化脱氢 / Oppenauer

- 两条骨架二选一（按催化剂）：(a) 过渡金属：烷氧基配位 → β-氢消除（需空配位 + agostic 预组织）→ M–H + 羰基；(b) Al 系 Oppenauer：六元环氢转移 TS（MPV 的逆过程，见 MPV 节）。
- 键变化：breaking Cα–H；forming M–H（或受体 C–H）；C–O → C=O。`watch_pairs`：Cα–H、M–H、C–O。
- 预组织：β-氢消除须 agostic 取向——`distance_filters`：M···H–Cα 1.8–2.5 Å，且 M–Cα–H 角 < 120 °（典型区间）；无空配位的饱和络合物先建解离边。
- TS 期望：四元环 β-氢消除 TS，M···H 约 1.7–2.0 Å（典型区间，随金属漂移）；吸热步骤 → 晚 TS。
- 必须并建：配体解离边；Oppenauer 六元环边；M–H 的后续去向（还原消除 H₂ 或转移给授体）。
- 误诊信号：β-氢消除扫描单调升 → 多半没有空配位或 agostic 预组织未满足，回 `conformer_search` 或先建解离节点。

## 硼氢化物氢转移（NaBH₄ 等）

- 键变化：forming C–H、breaking B–H；羰基 π 断。`watch_pairs`：B–H、H–C、C–O。扫描坐标：H–C（缩短）。
- 预组织：Bürgi–Dunitz 进攻角（谓词参见 [carbonyl.md](carbonyl.md) 直接亲核加成节）；Na⁺/质子溶剂配位羰基 O 显著降垒——**阳离子与溶剂壳要显式进模型**。`distance_filters`：转移 H 到羰基 C 1.5–2.5 Å；Na⁺–O(carbonyl) 2.0–2.6 Å。
- TS 期望：forming C–H 约 1.4–1.8 Å、breaking B–H 约 1.3–1.6 Å（典型区间，待核实，随 Lewis 酸活化程度漂移）；醛早 TS、酮晚 TS（Hammond）。
- 必须并建：Felkin–Anh 两面（手性酮，谓词见 [carbonyl.md](carbonyl.md) 直接亲核加成节）；第二/三/四次氢转移（BH₄⁻ 四个氢活性递增不同，烷氧基累积改变后续垒）按需要建后续节点；Luche 条件（Ce³⁺）配位模式不同。
- 误诊信号：气相无反离子的裸模型垒虚高 → 不是机理错，是模型缺 Na⁺/溶剂；CBS 类催化还原另有自己的环状 TS，勿套用裸 BH₄ 边。

## 催化氢化（表面，Horiuti–Polanyi）

- 假设图骨架：H₂ 表面解离（均裂或异裂）→ 烯 π 吸附（di-σ 化）→ 第一个表面 H 迁移（半氢化中间体）→ 第二次加 H → 脱附。逐步、非协同，每步一个 TS。
- 键变化：M–H、C–H、C–M 的逐次形成；`watch_pairs` 按各步定（H₂ 解离步：H–H、M–H ×2）。
- TS 期望：数值强烈依赖表面/晶面/覆盖度，**不给区间，标注待核实**；趋势：第二步加氢常为决速（漂移大）。
- 必须并建：H₂ 均裂 vs 异裂；不同晶面/位点（ terrace/step ）作为不同模型而非不同边。
- 误诊信号（模型层级）：用 3–10 原子小簇近似表面 → 收敛性与电荷态系统性偏差，结论只能定性；分子 DFT 全套工具（`ts_guess`/`verify`）适用于簇模型，但报告须写明"簇近似，外推表面需谨慎"。

## MPV 直接氢转移

- 键变化：forming C(受体)–H、breaking C(供体 α)–H；两个 O 同配位于 Al（或 Ln）。`watch_pairs`：供体 C–H、受体 C–H、两 Al–O。
- 预组织：六元环椅式样 TS（O–Al–O 桥 + 两个碳 + 转移 H）；`distance_filters`：转移 H 到受体羰基 C 1.4–2.2 Å；两羰基/醇 O–Al 2.0–2.4 Å。
- TS 期望：转移 H 大致居中（两 C–H 各约 1.3–1.6 Å，典型区间，随取代漂移）；供体与受体氧化还原势差决定 TS 早晚（Hammond）。
- 必须并建：平衡可逆——正逆两条边都验证；氢化物桥双铝物种（aggregates）变体；催化量醇盐 vs 化学计量的节点差异。
- 误诊信号：找不到双配位络合物极小点 → 检查 Al 配位数设定；把 MPV 当单分子扫（漏配位伙伴）是无峰的典型原因。

## 转移氢化 inner-sphere vs outer-sphere

- inner-sphere 骨架：供体（iPrOH/甲酸）配位 → β-氢消除 → M–H + 丙酮 → 羰基底物配位 → 迁移插入 M–H → 烷氧基 → 交换。判别前提：金属有空配位/可腾位；底物必须进配位层。
- outer-sphere（Noyori 双功能）骨架：18e Ru–H/N–H → 六元环周环样 TS（H⁻ 给羰基 C、N–H 质子给 O，协同但异步）→ 醇 + 16e 酰胺 → H₂ 或 iPrOH 再生。判别前提：底物不配位金属；N–H 必须在 TS 中出现 partial bond。
- 键变化（outer-sphere 决速 TS）：forming C–H(来自 Ru–H)、O–H(来自 N–H)；breaking Ru–H、N–H。`watch_pairs` 四对全列。扫描坐标：Ru–H 或 C–H。
- 预组织（outer-sphere）：羰基 C=O 沿 Ru–H···N–H 的六元环取向靠近；`distance_filters`：H(Ru)–C 1.6–2.4 Å、H(N)–O 1.4–2.2 Å。
- 判别特征：outer-sphere TS 上不应有 Ru–O/Ru–C(底物) 键（Mayer < 0.1）；inner-sphere 反之。同位素实验对应计算：交换 N–D 影响速率 → outer-sphere。
- 误诊信号：给 18e 饱和 Noyori 催化剂硬建 inner-sphere 边（需先解离腾位，垒常很高）→ 两条边都算再裁决；忽略离子对（K⁺/碱）参与 → 垒系统性偏高。

## 金属氧代 HAT-回弹

- 假设图骨架：Mⁿ⁺=O（Feᴵⱽ=O、Mnⱽ=O 等）→ [HAT TS] → M–OH + 碳自由基（笼内自由基对）→ [回弹 TS：OH 转移] → 醇 + Mⁿ⁻²。
- 键变化：HAT 步 breaking C–H、forming O–H；回弹步 forming C–O、breaking M–O(H)。`watch_pairs`：C–H、O–H、（回弹）C–O、M–O。扫描坐标：O–H（缩短）。
- 预组织：C–H 指向 oxo，近线性 σ 通道；`distance_filters`：O(oxo) 到目标 H 1.5–2.5 Å；C–H···O 角 > 140 °（π 通道/σ 通道影响位点选择，角度区间典型值，随体系漂移）。
- TS 期望：HAT TS 中 O–H 约 1.2–1.4 Å、C–H 约 1.3–1.5 Å（典型区间，Bell–Evans–Polanyi：垒随 C–H BDE 与极性效应漂移）；回弹垒常很低（约 1–10 kcal/mol，漂移大）。M=O 键长约 1.6–1.7 Å（Feᴵⱽ，典型值）。
- 必须并建：每个可夺氢位点一条 HAT 边（BDE + 极性/位阻排序）；各可行自旋态各一条（两态反应性：HS/LS 面交叉，决速 TS 可能不在基态面）；回弹 vs 非回弹（自由基逃逸、第二次夺氢脱饱和、重排）边。
- 误诊信号：回弹垒 > HAT 垒 → 检查自旋态或该体系实为非回弹机理；中间体优化直接塌缩成醇（无自由基极小点）→ 垒极小，符合快速回弹；`⟨S²⟩` 偏差 ≳0.1 → 按 [method-selection.md](../../dft-calculation/references/method-selection.md) 打折能垒结论并诊断（`electronic_analysis` spin>1 自动 UKS；实用触发器，非自动 fail）。

## 领域级陷阱

- **先定活性种再建边**：H₂O₂/过氧体系真正转移氧的是过酸、金属过氧或金属氧代物种，不是 H₂O₂ 本身；活性种没定（配位数、质子化态、自旋态）就开始扫是全流程最贵的错误。
- **自旋态枚举漏建**：金属氧代/过氧体系每个节点枚举可行自旋态，两态反应性下基态势能面可能不含决速 TS；只算一个自旋面的结论不可信。
- **把已淘汰机理当主假设**：Mimoun 金属杂环、OsO₄ [2+2]、平面过酸 TS 的历史角色是判别对象；正确用法是建成竞争边用键级/IRC/立体化学裁决，而非默认主路径。
- **教科书决速步不可预设**：Swern 苄醇体系实测去质子化决速而非消除；酰基转移类同理（参见 [carbonyl.md](carbonyl.md) 加成-消除节）。预平衡节点全部进假设图，各边都算。
- **多相表面机理的模型层级**：催化氢化簇模型结论不能外推表面；报告必须标注模型层级（簇/ slab /实验），不要拿小簇 ΔG‡ 与实验速率直接定量比较。
- **立体化学是最便宜的机理探针**：cis 烯出 trans 环氧（自由基逐步）、羟化构型打乱（长寿命自由基）、syn vs anti 二醇——算完务必拿产物立体化学回验机理假设，再写结论。

## 参考来源

- Bach, R. D. et al., "Nature of the Transition Structure for Alkene Epoxidation by Peroxy Acid"（spiro vs planar TS，DFT 基准）, https://schlegelgroup.wayne.edu/Pub_folder/195.pdf
- Organic Chemistry Portal: Prilezhaev Reaction（蝴蝶机理与过酸构象）, https://www.organic-chemistry.org/namedreactions/prilezhaev-reaction.shtm
- Sundermeyer 课件（d⁰ 金属过氧 Sharpless vs Mimoun 判别论据）, https://www.uni-marburg.de/de/fb15/arbeitsgruppen/anorganische_chemie/ag-sundermeyer/lehre/files/ac-5-teil-1-technische-katalyse.pdf/@@download/file/AC-5%20Teil%201%20Technische%20Katalyse.pdf
- UTUPub 学位论文（Mo/W/V 环氧化排除 Mimoun 的实验与理论证据综述）, https://www.utupub.fi/server/api/core/bitstreams/5fd75ab5-979c-4587-bb56-2ddf2430a583/content
- Garay-Ruiz et al. 2024（d⁰ 金属过氧氧转移 Sharpless 型共识与周期性趋势）, https://www.research.unipd.it/retrieve/deb02b3e-3dc9-4073-891c-3ec092b16215/garay-ruiz-et-al-2024-periodic-trends-and-fluxionality-effects-on-transition-metal-catalyzed-sulfoxidation.pdf
- Grossman, "The Art of Writing Reasonable Organic Reaction Mechanisms"（OsO₄ [3+2]/[2+2] 之争教材级总结）, https://m.shsbnu.net/pluginfile.php/38279/mod_resource/content/3/The%20Art%20of%20Writing%20Reasonable%20Organic%20Reaction%20Mechanisms.pdf
- Organic Chemistry Portal: Upjohn Dihydroxylation（量子化学计算支持 (3+2)）, https://www.organic-chemistry.org/namedreactions/upjohn-dihydroxylation.shtm
- "Mechanism of the Swern Oxidation: Significant Deviations from the Textbook Mechanism"（去质子化决速证据）, https://pmc.ncbi.nlm.nih.gov/articles/PMC2995308/
- ACS GCI Roundtable Reagent Guide: MPV Reduction（六元环 TS）, https://reagents.acsgcipr.org/reagent-guides/ketone-reduction/list-of-reagents/meerwein-ponndorf-verley-reduction/
- Comas-Vives et al. 2009（Shvo 催化剂氢转移机理的计算解析，inner/outer-sphere）, https://www.sciencedirect.com/science/article/abs/pii/S0166128009001572
- UToronto 学位论文（Noyori 外球双功能机理 DFT 与同位素证据综述）, https://utoronto.scholaris.ca/server/api/core/bitstreams/2e21c2b4-80f5-4ca1-bb30-418482f2cce9/content
- Baglia et al. 2017（Mn/Fe 卟啉类氧代物种 HAT/OAT 反应性综述，DOI: 10.1021/acs.accounts.7b00191）, https://pmc.ncbi.nlm.nih.gov/articles/PMC6058703/
- Cho/Hirao/Shaik/Nam（非回弹机理 tutorial review；合成非血红素体系自由基逃逸）, https://www.researchgate.net/publication/363119037_A_P450_Harboring_Manganese_Protoporphyrin_IX_Generates_a_Manganese_Analogue_of_Compound_I_by_Activating_Dioxygen
- Larson et al. 2020（非血红素 Fe/Mn 氧代 HAT/OAT 综述，自旋态效应）, https://par.nsf.gov/servlets/purl/10177166
- Cano et al. 2021（H₂ 异裂与 Horiuti–Polanyi 机理计算研究）, https://digital.csic.es/bitstream/10261/268418/1/Heterolytic%20cleavage.pdf
