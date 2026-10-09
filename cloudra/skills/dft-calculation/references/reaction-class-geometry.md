# 反应建模参考：如何思考反应过程中的化学问题

> **本文档的定位**：本文档是 agent 的建模参考总入口。领域知识统一保存在 `reaction-mechanisms` 技能的 `references/` 目录，按反应结果分文件加载；本文件只含：建模思考框架（§1）、反应结果分类索引（§2）、跨领域通用基元步与规则（§3）、人类维护指南（§4）。使用方式：先读 §1；按键变化与产物类型在 §2 索引中判定反应结果归属；用 `get_skill(skill_name="reaction-mechanisms", reference="<文件>.md")` 只取对应领域文件；拿不准归属时读相关候选文件（归属判定看"结果"不看机理——机理类型正是要你计算裁决的东西）。

本文件及领域文件的几何/能量区间用于形成假设，不是验收门槛。计算流程、引擎参数、失败处置以 `mechanism-elucidation-sop.md` 和引擎参考为准，方法选择遵循用户当前要求和预算。只有当前 Benchmark 项目使用该题实际的 MethodPolicy；普通研究项目没有默认方法/基组白名单，示例和历史任务不产生限制。其中的轨道/布居诊断只在实际方法提供相应数据时使用。`distance_filters` 是构象筛选条件，不是在后续优化中冻结原子。**建模默认纪律：先 `internal_coordinates` 读键与二面角，能用一根成/断键描述的变化就先做柔性扫描找 TS 初猜，不要直接对非 TS 几何盲跑 OptTS。**

# 1. 建模思考框架：面对任何反应，按这五个问题展开

拿到一个基元步（假设图中的一条边），不要急着写输入文件。依次回答五个问题，每个问题直接映射到一个工具决策：

**Q1：哪些键在断、哪些键在成？**
- 从 reaction SMARTS / 原子映射确定成键、断键原子对。这一步错了后面全错。
- 落地：**先 `internal_coordinates` analyze** 读出真实原子序号与异常键长/角度，再写成 `watch_pairs`、`ts_guess` scan_prepare 的扫描坐标（首选坐标 = 最重要的那根 forming/breaking 键）。不要凭 SMILES 序号或目测猜 XYZ 下标。

**Q2：反应物要摆成什么姿势才能反应？（预组织）**
- 每个反应类都有几何前提（轨道对齐、空间接近、构象要求）。想清楚"不摆对就反应不了"的约束是什么。
- 落地：能写成距离的写进 `conformer_search` 的 `distance_filters`；**二面角/角度约束筛完距离后必须用 `internal_coordinates` 复核**，不满足直接丢弃，不要在错误预组织上硬扫。
- 注意 Curtin-Hammett：起反应的构象不一定是能量最低的构象，不要只取 conf0。

**Q3：TS 应该长什么样？（期望值的来源）**
- 用 Hammond 假说形成初猜：在适用的相关反应系列中，放热步常偏早（更像反应物），吸热步常偏晚（更像产物）。这不是由总反应能直接算键长的规则；速查区间只用于预组织，最终检查实际势能面。
- 用轨道对齐想几何：TS 几何的本质是"让该重叠的轨道重叠"。进攻角、反式共平面这些要求都来自轨道对称性/立体电子效应，不是经验巧合——想清楚是哪个轨道相互作用在起作用（n→σ*、π→π*、σ→σ*），几何谓词就自然写出来了。
- 用 Woodward–Hoffmann 类对称性规则做**假设剪枝**：对称性禁阻的协同路径（如 [1,2]-H suprafacial 迁移）不要进假设图，省一轮白算。

**Q4：哪些竞争路径必须同时进假设图？**
- 立体异构面/取向（Re/Si 面进攻、endo/exo、顺旋/对旋、Saytzeff/Hofmann 取向）：每种取向一条边，选择性由它们的 ΔΔG‡ 决定。
- 机理变体（SN1/SN2、E2/E1cB、直接质子迁移 vs 溶剂介导穿梭、协同 vs 双自由基逐步）：拿不准时两条边都建，让能垒裁决。
- 容易漏的：质子穿梭路径（直接迁移能垒通常极高，溶剂/酸碱介导的链式穿梭往往是真实路径）、四面体中间体等"不起眼"的中间体节点。

**Q5：什么数值说明我错了？（诊断触发器）**
- 扫描曲线单调 → 坐标选错或该步无垒（先 `internal_coordinates` 核对原子序号）；突跳 → 滑谷；极大在边界 → 范围不够（`ts_guess` scan_parse 自动判定这些）。
- 有波函数时可用 Mayer 键级辅助观察成断键；低键级也可能对应早/晚 TS，须结合梯度、虚频模式与路径，不能单独否定机理。
- 2+ 虚频 → 高阶鞍点；IRC 接到非预期产物 → 这条边属于别的基元步（可能是新发现，也可能是初猜错了）。
- 自由基/开壳层：`⟨S²⟩` 偏差 ≳0.1 是**实用触发器**——按 `method-selection.md` 打折单参考结论并做诊断，不是自动 pass/fail 判据。

# 2. 反应结果分类索引

| 反应结果 | 文件 | 覆盖 | 典型反应示例 |
| :--- | :--- | :--- | :--- |
| 取代（一个原子/基团被替换） | [substitution.md](../../reaction-mechanisms/references/substitution.md) | SN1/SN2、SEAr、SNAr（加成-消除/苯炔/SRN1）、自由基取代 | 卤代烃水解、硝化、氟代芳烃取代 |
| 不饱和键加成 | [addition.md](../../reaction-mechanisms/references/addition.md) | 亲电加成（碳正离子/鎓离子/协同）、硼氢化、Michael 与共轭加成 | HX/Br2 加烯、硼氢化、硫醇-Michael |
| 羰基 sp2 碳成键 | [carbonyl.md](../../reaction-mechanisms/references/carbonyl.md) | 亲核加成、酰基转移、烯醇(盐)化学（aldol/Claisen/Mannich/α-官能化）、Wittig/HWE 烯化 | 格氏加成、酯水解、羟醛缩合 |
| 消除（脱去两基团成 π 键） | [elimination.md](../../reaction-mechanisms/references/elimination.md) | E1/E2/E1cB、Ei（酯热解/Chugaev/Cope）、脱羧 | 卤代烃脱 HX、β-酮酸脱羧 |
| 周环（环状 TS 协同） | [pericyclic.md](../../reaction-mechanisms/references/pericyclic.md) | 环加成、电环化、σ 迁移、ene、螯变 | Diels–Alder、Cope/Claisen |
| 自由基（开壳层中间体） | [radical.md](../../reaction-mechanisms/references/radical.md) | 链式三段式、取代/加成/HAT/环化/碎片化、笼效应、开壳层工作流 | 自由基环化、HAT 氟化 |
| 重排（基团带电子对迁移） | [rearrangement.md](../../reaction-mechanisms/references/rearrangement.md) | 碳正离子/缺电子 N/缺电子 O/阴离子重排 | pinacol、Beckmann、Baeyer–Villiger |
| 氧化还原（氧/氢转移） | [redox.md](../../reaction-mechanisms/references/redox.md) | 环氧化、双羟化、醇氧化、氢化物/催化氢化/转移氢化、C-H 氧化 | 环氧化、Swern、NaBH4 还原 |
| 过渡金属偶联 | [coupling.md](../../reaction-mechanisms/references/coupling.md) | 交叉偶联循环、Heck、复分解、CMD | Suzuki、Heck |

归属策略：一个反应可能落进多个结果类（如 Michael 加成既是加成也是羰基化学），此时每个候选文件都读；文件内部按机理变体组织假设空间，枚举后由计算证据裁决，不要因为"觉得像某机理"而跳过假设空间表。

# 3. 跨领域通用基元步与规则

> 数值为典型区间（Å / °），受 Hammond 效应支配会漂移，用于初猜与筛选，**最终裁决永远是算出来的频率 + IRC**。

## 3.1 质子转移（通用）

- 几何谓词：D–H···A 角接近线性（160–180）；对称性强氢键 TS 中 H 大致居中。
- 能垒直觉：酸碱驱动力、供受体距离、溶剂重组和预组织共同影响势垒，不能仅凭 pKa 差判断。条件允许时比较直接转移与溶剂/酸碱介导路径。
- 扫描坐标：可先扫 H–受体距离（缩短），同时监测供体–H 与供受体距离；若单调或滑谷，检查耦合坐标及预组织，不能直接宣布无垒。

## 3.2 Baldwin 环化规则（环化基元步的可行性预筛）

- 用途：假设图生成阶段对环化边做可行性预判——disfavored 不是不可能，但有显著能垒惩罚，优先建 favored 边。
- 速查（3–7 元环）：
  - **exo-trig**：3–7 全 favored（5-exo-trig 最常见）；
  - **endo-trig**：3–5 disfavored，6–7 favored（6-endo-trig 可用但常输给 5-exo）；
  - **exo-dig**：3–7 favored；**endo-dig**：5–7 favored，3–4 disfavored；
  - **exo-tet**：5–7 favored；**endo-tet**：3–5 favored。

## 3.3 通用判读速查

| 量 | 区间 | 含义 |
| :--- | :--- | :--- |
| ΔG‡ | < 15 kcal/mol | 室温快速 |
| ΔG‡ | 15–25 | 室温至温和加热可行 |
| ΔG‡ | 25–35 | 需加热/催化 |
| ΔG‡ | > 35 | 温和条件不可行，剪枝或换路径 |
| ΔΔG‡ (298 K) | 1.4 / 2.7 kcal/mol | 选择性 ≈ 10:1 / 100:1 |
| Mayer 键级（TS 成/断键） | 随方法、基组与路径变化 | 辅助诊断；没有通用的 TS 键级通过区间 |
| 扫描突跳 | 相邻 ΔE > 3×中位数且 > 2 kcal/mol | 滑谷信号（`ts_guess` scan_parse 自动判定） |

# 4. 给人类科学家的维护指南

本文档的目标读者是 agent，价值在于**建模决策的可执行性**，而非化学完整性。扩充或修订时请遵守：

1. **每个条目必须回答第 1 节的五个建模问题**（键变化 / 预组织 / TS 期望 / 竞争边 / 误诊信号），写不全的条目不如不写——agent 需要的是决策依据，不是描述性知识。
2. **数值是给初猜和筛选用的，不是判据**。请标注 Hammond/底物依赖性（"典型值""随 XX 漂移"），避免把区间写成硬判据；最终裁决永远留给频率与 IRC。
3. **立体电子效应/轨道分析优先于经验规则**：能用一个轨道相互作用解释的几何要求，就写明是哪个相互作用——agent 由此可以自行推广到表外体系，这才是"会思考"而非"会查表"。
4. **保持条目可消费**：每个几何谓词必须能直接写成 `distance_filters`（原子对 + 距离区间）、`watch_pairs` 或扫描坐标；写不成工具输入的知识对本系统没有价值。
5. **竞争边与常见误诊信号是最稀缺的内容**：教材查不到"agent 会在这里犯什么错"，请优先补充你实际机理计算中踩过的坑（什么体系容易滑谷、什么反应常找错 TS、什么假设常被漏建）。
6. 存疑数值请显式标注"待核实"并附来源；教材推荐 Carey & Sundberg、Anslyn & Dougherty、Clayden，规则类溯原始文献（Bürgi–Dunitz、Baldwin、Woodward–Hoffmann、Felkin–Anh）。
7. **结构规范**：新反应领域在 `reaction-mechanisms/references/` 下新建文件，并同步维护该技能目录与本文件 §2 索引；本文件不内联任何单一领域的内容；跨领域通用知识（如质子转移）才放 §3。
