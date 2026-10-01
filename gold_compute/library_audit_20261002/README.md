# 全库逐边闭环审计 · 2026-10-02

## 结论

检查最新发布的 **52 题、81 条边**，发现 **10 条边尚无回填值，且未找到逐边明确放弃/豁免记录**：normal 7 条、hard 3 条。
另有 57 条已回填数值，2 条有明确 PT 参考垒豁免，8 条 impossible 边的 TS 明确不可达，4 条是性质/态变化边。
57 条“已回填数值”中，10 条存在下文列出的科学证据或机制限制；有数值仅说明回填完成，不能据此宣称全部证据验收完成。

## 版本与口径

- 权威题库提交：`3ec62c55c8e3433854246ea50f889668b2659cc4`，本次只读核对 GitHub master 与之相同；读的是该提交的 Git 对象。
- 主工作区 HEAD：`9fa8775b7e29c7f941451b38e516c42422701b09`，存在无关未提交修改；本次没有更新该工作区的题源或 TaskSpec。
- 范围：easy / normal / hard / impossible 的全部活跃生成题。历史候选池、未选 registry 条目和退休题另行保留，不把其历史边列入活跃总数。
- 缺测、搜索失败、预算耗尽、本轮范围外，均不自动等于永久放弃。明确逐边不要求参考垒或方法不可达时才作豁免。
- 分子内互变 PT 规则仅按明确适用边解释；NR1/HL1 的分子间酸活化及 NY3 待重算的 Na⁺ 模型没有被套用该规则。
- 本次为题库/来源/交接一致性审计，没有重算 QM，也没有重新解析所有原始日志验证每条路径。

## 全库汇总

| 档位 | 题数 | 边数 | 已填数值 | 缺测未明确放弃 | 明确 PT 豁免 | TS 不可达 | 性质/态变化 |
|---|---:|---:|---:|---:|---:|---:|---:|
| easy | 20 | 20 | 20 | 0 | 0 | 0 | 0 |
| normal | 10 | 26 | 17 | 7 | 2 | 0 | 0 |
| hard | 10 | 22 | 19 | 3 | 0 | 0 | 0 |
| impossible | 12 | 13 | 1 | 0 | 0 | 8 | 4 |
| **总计** | **52** | **81** | **57** | **10** | **2** | **8** | **4** |

ID2 为纯性质题，0 条边，包含在 52 题范围中。本审计没有把 FOOF 性质要求伪记为能垒边。

## 1. 尚未闭环的 10 条边

| 边 | 反应步骤 | 当前状态与依据 | 来源 |
|---|---|---|---|
| **HI1_E1** | 脯氨酸烯胺缩合 | null；本轮只验收两条 C–C 加成，E1 未计算且撤回旧 19.2；属于本轮范围外/暂留缺口，没有永久放弃记录。 | [hard_hi1_2026-10-01.md](source_snapshot/published/gold_compute/hard_hi1_2026-10-01.md)、[hard.md](source_snapshot/published/ideapool/reaction_candidates/hard.md) |
| **HI1_E3** | iminium-aldolate 水解 | null；本轮范围外且撤回旧 16.9；未计算不能等同明确永久放弃。 | [hard_hi1_2026-10-01.md](source_snapshot/published/gold_compute/hard_hi1_2026-10-01.md)、[hard.md](source_snapshot/published/ideapool/reaction_candidates/hard.md) |
| **HL1_E1** | Beckmann：肟 OH 质子化 | null；最新源保持 null；旧 Gaussian 的无鞍点扫描与 ORCA 错位 PT 候选均不是现行合格回填。未见正式豁免/放弃。 | [hard_hl1_2026-10-01.md](source_snapshot/published/gold_compute/hard_hl1_2026-10-01.md)、[hard.md](source_snapshot/published/ideapool/reaction_candidates/hard.md) |
| **NI5_E1** | 水溶液亚胺形成：C–N 加成 | null；最新题源明确写尚无无约束 TS 能垒、暂缺测；未见明确放弃。 | [HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[normal.md](source_snapshot/published/ideapool/reaction_candidates/normal.md) |
| **NR1_E1** | 频哪醇 OH 质子化 | null；最新源写 PT 未确立非零垒；旧 Gaussian 约束扫描的 0 不是当前合格回填或正式豁免。分子内互变规则不自动适用于本分子间酸活化。 | [HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[NR1.json](source_snapshot/published/gold_compute/edge_barriers/computed/NR1.json)、[normal.md](source_snapshot/published/ideapool/reaction_candidates/normal.md) |
| **NR1_E2** | 质子化频哪醇脱水 | null；最新源明确未找到独立鞍点，参考垒缺测；搜索失败不是已明确放弃。 | [HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[NR1.json](source_snapshot/published/gold_compute/edge_barriers/computed/NR1.json)、[normal.md](source_snapshot/published/ideapool/reaction_candidates/normal.md) |
| **NU5_E2** | Passerini：甲酸根捕获腈鎓 | null；最新题源明确捕获能垒缺测；旧四步图的 E2/E3 编号及 8.2/0 不可移植到当前三步图。 | [README.md](source_snapshot/local_evidence/gold_compute/verified_evidence/NU5/README.md)、[HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[normal.md](source_snapshot/published/ideapool/reaction_candidates/normal.md) |
| **NY3_E1** | Na⁺ 模型：OH⁻ 加成 | null；用户改为 Na⁺ 制衡中性模型后明确要求重算全图；裸离子旧值作废，未见新模型闭环或放弃记录。 9/26 复盘记录有限 TS/扫描尝试失败及机理耦合疑点，预算耗尽、待科学裁决不是正式放弃。 | [agent_hint_dead_ends_2026-09-26.md](source_snapshot/published/gold_compute/agent_hint_dead_ends_2026-09-26.md)、[HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[normal.md](source_snapshot/published/ideapool/reaction_candidates/normal.md) |
| **NY3_E2** | Na⁺ 模型：甲氧基消除 | null；同上；裸 OH⁻ 旧 12.5 不能回填 Na⁺ 新模型。 9/26 复盘记录有限 TS/扫描尝试失败及机理耦合疑点，预算耗尽、待科学裁决不是正式放弃。 | [agent_hint_dead_ends_2026-09-26.md](source_snapshot/published/gold_compute/agent_hint_dead_ends_2026-09-26.md)、[HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[normal.md](source_snapshot/published/ideapool/reaction_candidates/normal.md) |
| **NY3_E3** | Na⁺ 模型：甲酸→甲氧基 PT | null；同上；该边虽为 PT，源明确三步待 Na 模型战役回填；旧裸离子 0.0 及分子内互变豁免均不自动关闭此边。 9/26 复盘记录有限 TS/扫描尝试失败及机理耦合疑点，预算耗尽、待科学裁决不是正式放弃。 | [agent_hint_dead_ends_2026-09-26.md](source_snapshot/published/gold_compute/agent_hint_dead_ends_2026-09-26.md)、[HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[normal.md](source_snapshot/published/ideapool/reaction_candidates/normal.md) |

**解释 hard 收工的范围：** 已授权的 HI1 两条立体决定 C–C 加成、HL1 下游水解、HA8/HB10 替换生产已收尾。HI1_E1、HI1_E3、HL1_E1 仍是存量完整图的参考垒缺口；当前记录没有承诺它们已全部算完或永久放弃。
下一次若决定处理这些边，应逐边记录补证据、有限新计算或明确豁免的决定；本清单本身不启动新的计算队列。

## 2. 明确不要求补参考垒的边

| 边 | 依据 | 来源 |
|---|---|---|
| NB1_E2 | 明确按既定分子内 PT 规则保留图边，不要求参考垒、不追加大规模扫描。 | [HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[normal_malonic_acid_2026-09-27.md](source_snapshot/published/gold_compute/normal_malonic_acid_2026-09-27.md)、[normal.md](source_snapshot/published/ideapool/reaction_candidates/normal.md) |
| NQ5_E2 | 逐边明确写 barrier deliberately unanchored per 2026-09-25 PT-edge rule，gold 战役不花算力。 | [HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[normal.md](source_snapshot/published/ideapool/reaction_candidates/normal.md) |

impossible 的 8 条反应边：`IA1_E1`, `IA5_E1`, `IA7_E1`, `IA8_E1`, `IA9_E1`, `IB10_E1`, `IB10_E2`, `IB9_E2`。这些边的经由 TS 节点明确 `accessible=false`。

4 条性质/态变化边：`IC3_E1`, `IE2_E1`, `IF3_E1`, `IG8_E1`。源明确为自旋态/解离性质，无活化垒 TS；目标态标不可达。边自身 accessible=true 不改变交付类型。

HE3/HG2 原 TaskSpec 已正式退休留档；HE2 已被 HB1 替换。它们的旧缺测/拒收证据保留在原归档，不属于这次活跃题库的待补边。

## 3. 已回填但仍须保留的 10 条限制

这部分单列为科学质量复核，未擅自撤回数值或改变既有验收口径。部分记录属于历史时点，写作“未找到修复证明”时不推断以后从未修复。

| 边 | 现行值 / kcal mol⁻¹ | 限制 | 来源 |
|---|---:|---|---|
| D1_E1 | 18.83 | 已回填 18.83，但直接 IRC 反应端优化未收敛，仅有独立零虚频络合物，路径端点未严格闭合。 | [easy_backfill_2026-09-23.md](source_snapshot/published/gold_compute/easy_backfill_2026-09-23.md)、[easy_backfill_2026-09-25.md](source_snapshot/published/gold_compute/easy_backfill_2026-09-25.md)、[easy_replacements_2026-09-24.md](source_snapshot/published/gold_compute/easy_replacements_2026-09-24.md) |
| G2_E1 | 0.87 | 已回填 0.87；IRC 产物 vdW 加合物有 −7.6 软虚频，分离 N₂/乙烷零虚频不等于该复合端严格闭合。 | [easy_backfill_2026-09-23.md](source_snapshot/published/gold_compute/easy_backfill_2026-09-23.md)、[easy_backfill_2026-09-25.md](source_snapshot/published/gold_compute/easy_backfill_2026-09-25.md)、[easy_replacements_2026-09-24.md](source_snapshot/published/gold_compute/easy_replacements_2026-09-24.md) |
| G3_E1 | 30.15 | 已回填 30.15；源记录 TS 非协同、具双自由基特征，而 step_type 仍写 concerted。这是机制/适用性审查问题，不自行撤回或补算。 | [easy_backfill_2026-09-23.md](source_snapshot/published/gold_compute/easy_backfill_2026-09-23.md)、[easy_backfill_2026-09-25.md](source_snapshot/published/gold_compute/easy_backfill_2026-09-25.md)、[easy_replacements_2026-09-24.md](source_snapshot/published/gold_compute/easy_replacements_2026-09-24.md) |
| M1_E1 | 15.1 | 已回填 15.10，但为 τ=180° 约束弛豫的软虚频驻点，无约束 OptTS 滑向甲基旋转赝鞍点；不能称无约束相关 TS 全验收。 | [easy_backfill_2026-09-23.md](source_snapshot/published/gold_compute/easy_backfill_2026-09-23.md)、[easy_backfill_2026-09-25.md](source_snapshot/published/gold_compute/easy_backfill_2026-09-25.md)、[easy_replacements_2026-09-24.md](source_snapshot/published/gold_compute/easy_replacements_2026-09-24.md) |
| HL1_E2 | 23.13 | 保留旧 23.13，一阶迁移鞍点存在，但 IRC 反向未回声明 I1 的 partial caveat；本轮没有重新验证 E2。 | [HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[hard_hl1_2026-10-01.md](source_snapshot/published/gold_compute/hard_hl1_2026-10-01.md) |
| IB9_E1 | 14.74 | 已回填 14.74；9/26 复盘记录第一阶段产物 IRC 再优化仍有浅环翻转虚频。本次未见该端点后续零虚频修复证明，列为待复核旧限制；不据此自动撤回数值。 | [agent_hint_dead_ends_2026-09-26.md](source_snapshot/published/gold_compute/agent_hint_dead_ends_2026-09-26.md) |
| NI1_E1 | 27.9 | 已回填 D3BJ 自算 27.90；源明确 IRC 只有一向收敛且端点未重优化闭合。 | [HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md) |
| NI1_E2 | 57.67 | 已回填 D3BJ 自算 57.67；源明确 IRC 只有一向收敛且端点未重优化闭合。 | [HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md) |
| NR1_E4 | 5.74 | 已回填旧 Gaussian 自算 5.74，旧边 NR1_E3 现对应去质子步 E4；原证据记录替代质子接力拓扑及一点评 IRC，仅按 supervisor-supported 接受，须保留身份/拓扑 caveat。 | [HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md)、[NR1.json](source_snapshot/published/gold_compute/edge_barriers/computed/NR1.json) |
| NU6_E1 | 2.66 | 已回填 2.66，但本地旧验收树注明 RC 有 −24.32 软虚频；本次未找到该起点零虚频修正记录，不能把旧源的 verified 当作严格最小值全过。 | [README.md](source_snapshot/local_evidence/gold_compute/verified_evidence/NU6/README.md)、[HANDOFF_CAMPAIGN.md](source_snapshot/published/gold_compute/archive/HANDOFF_CAMPAIGN.md)、[HANDOFF_backfill.md](source_snapshot/published/gold_compute/archive/HANDOFF_backfill.md) |

**IRC 步数到原生上限本身不等于验收失败。** HI1、HA8、HB10、HL1 新边已有实际方向、正确身份和无约束零虚频端点证据，保留原生 IRC 未自收敛说明。它们未被仅因步数上限重复计作缺口。

## 4. 主工作区的版本差异

主工作区有 **10 个 TaskSpec 路径**与发布版本不同。若直接从当前主目录扫描，会漏掉新题并读取旧文献值。完整明细见 [working_tree_differences.csv](working_tree_differences.csv)。

| 路径 | 差异 |
|---|---|
| ideapool/tasks/hard/HA8.json | 发布版本有，本地主工作区缺少 |
| ideapool/tasks/hard/HB1.json | 发布版本有，本地主工作区缺少 |
| ideapool/tasks/hard/HB10.json | 发布版本有，本地主工作区缺少 |
| ideapool/tasks/hard/HE2.json | 仅本地主工作区存在；已不在发布活跃题库 |
| ideapool/tasks/hard/HE3.json | 仅本地主工作区存在；已不在发布活跃题库 |
| ideapool/tasks/hard/HF1.json | 文件内容与发布版本不同 |
| ideapool/tasks/hard/HG2.json | 仅本地主工作区存在；已不在发布活跃题库 |
| ideapool/tasks/hard/HH1.json | 文件内容与发布版本不同 |
| ideapool/tasks/hard/HI1.json | 文件内容与发布版本不同 |
| ideapool/tasks/hard/HL1.json | 文件内容与发布版本不同 |

其中 HF1、HH1、HI1、HL1 本地边值/图仍旧；本次按最新发布值审计，没有覆盖这些文件或其他未提交修改。

## 5. 可检查的数据与复算

- [open_edges.csv](open_edges.csv)：10 条未闭环边及逐边原因。
- [all_edges.csv](all_edges.csv) / [all_edges.json](all_edges.json)：81 条边完整台账，含图端点、有效可达性、数值、状态与出处。
- [numeric_caveats.csv](numeric_caveats.csv)：已回填边的 10 条重点证据限制。
- [tasks.json](tasks.json)：52 道题与无边性质题清单。
- [source_snapshot/](source_snapshot/) / [source_manifest.json](source_manifest.json)：发布题源、TaskSpecs 和使用的本地旧证据快照；逐文件 SHA-256。
- [decisions.json](decisions.json)：显式逐边分类及依据，避免仅凭 null 或文字关键词归类。
- [audit_library.py](audit_library.py)：标准库复算脚本；[audit_notebook.ipynb](audit_notebook.ipynb) 为可运行检查伴随文件。
- [verification.json](verification.json)：计数、唯一性、悬空端点、来源存在性验证，errors 为空。
- [remote_reference.json](remote_reference.json)：本次 GitHub master 只读核对记录。

分类依赖上述固定版本与已审阅的决定表。重跑脚本不会证明新计算已通过；新证据到来时须审查并更新对应决定。
原始 context、数据库、原始计算与最终快照继续保留在 [此前整理的数据入口](../HARD_DATA_INDEX.md)，本审计仅新增独立目录。
