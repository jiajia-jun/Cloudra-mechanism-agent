# Benchmark 缩减至 60 题：四档重配方案 v3（2026-09-09，已按确认名单落地）

> 依据（用户已确认的口径，2026-09-09 历次修正后）：
> - 总量 ~120 → ~60，四档重新配比；
> - normal 标准 = **多步**；可上网补充池外教材级候选，优先 xtb 友好（气相/闭壳/微溶剂化可闭合、
>   周环级联/热重排多步），找不到满意新题时回退到 48 池内重选；
> - hard 标准 = **立体化学**；可上网补充文献候选；**重原子 ≤20**（可含 B/Si/S/F/Cl/Br，禁过渡
>   金属）；**方法对 hard 开放 B3LYP-D3(BJ)/def2-SVP**（不再被 xtb 卡死，小 ΔΔ 立体选择性可算，
>   ORCA/Gaussian 跑、scorer 可解析）；
> - easy/impossible 维持此前口径（easy=气相闭壳干净单步；impossible=I/S 兄弟对拒答校准）。
> - 状态：**已落地（2026-09-09 用户确认后执行）**——四生成器名单/registry/`reaction_candidates`
>   定稿段已改，JSON 已重生成并删旧，收敛为 easy20 + normal10 + hard10 + impossible20（10 对 I/S）
>   = 60 题；regenerate-identically 与 benchmark 相关测试通过。web 补充未能提供可验证新锚点，
>   线索见附录 D 留作后续替代池。

**v3 总盘（60 题，推荐名单；全为已在库 task id，SMILES/步数/锚点/出处可回溯 ideapool md/JSON）：**

### Easy（20）
`C1 C3 D1 D3 D4 E1 F1 G2 G3 L1 L2 M1 M3 M8 M14 M15 M16 P2 P3 X1`

### Normal（10，全在 48 池/registry 内，已生成 JSON；新增两条 Q1/U3 为池内被裁、无 JSON，需登记）
`NI1 NU5 NU6 NA2 NA5 NO3 NY3 NR1`（8 条现题）+ `NQ1(芳香Claisen) NU3(Wittig)`（2 条新增）
> 池 id 对照：I1→NI1、U5→NU5、U6→NU6、A2→NA2、A5→NA5、O3→NO3、Y3→NY3、R1→NR1、
> Q1→NQ1（新）、U3→NU3（新）。

### Hard（10）
`HA1 HA6 HD2 HE2 HE3 HF1 HG2 HH1 HI1 HL1`
> 考点覆盖：torqueselection×2（HA1/HA6）、立体专一开环 HD2、π-面 HE2、手性催化模型 HE3、
> 氢键导向 HF1、[3,3] 椅/船 HG2、构型阻垒 HH1、有机催化 HI1、几何映射 HL1。全 ≤20 重原子。
> 未入榜备选（同口径可换入）：HJ1/HJ4（syn/anti 加成族）、HE1（ΔΔ0.7–0.9）、HI4、B7 等。

### Impossible（20 = 10 对 I/S）
`IA1/SA1 IA5/SA5 IA7/SA7 IA8/SA8 IA9/SA9 IC3/SC3 ID2/SD2 IE2/SE2 IF3/SF3 IG8/SG8`

> 剔 10 对主因见下（灰区 G7/H7/H8/I8/J6/J7 全剔、¹O₂ 系/苯炔系兄弟题边缘等）。

---

## Easy：保留 20 / 剔除 10

保留（全为气相/闭壳/无判据风险的"干净"题，即筛查报告未列档）：

`C1, C3, D1, D3, D4, E1, F1, G2, G3, L1, L2, M1, M3, M8, M14, M15, M16, P2, P3, X1`

- 覆盖本质：SN2(C1)、双反转机理判别(C3)、DA×3(D1 定标/D3 二聚/D4 含杂 endo)、E2(E1)、
  氢负转移(F1)、双氢转移(G2)、ene(G3，注：md 有协同/分步背景，属边缘但保留)、4π/6π 电环化
  (L1/L2)、轴手性(M1)、N 翻转(M3)、椅式翻转(M8)、s-trans 旋转(M14)、HONO 异构(M15)、
  脱氢(M16)、[1,5]-H(P2)、Claisen(P3)、脱羧挤出(X1)。

剔除及主因：

| 题 | 主因 |
|---|---|
| M12 (Zundel) | 判据2（单阱无 TS，自洽闭环不成立）——**必剔** |
| G1 (氢硼化) | 判据2（气相近无能垒、TST 失效） |
| T3 (HNC→HCN) | 判据2（IRC 反常平坦区） |
| T1 / F3 (水助互变/水合) | 判据1（水质子梭氢键网络） |
| P1 (Cope) | 判据3（impossible 池自注 C0²≈0.9 边缘 MR） |
| C2 / F2 (CN⁻ SN2/加成) | 判据2（近沉没垒，TS 相对渐近线≈0） |
| M10 / M6 (甲基/乙烷旋转) | 判据2（垒 1.1–3.0 kcal，低于 xtb 精度） |

## Normal：重选 10（48 池 → 10）【演进记录 v2：按"多步"标准重做；结论以顶部 v3 总盘为准】

> 用户口径修正：Normal 的筛选标准是**多步**（2–5 基元步、含中间体/竞争网络），不是单步周环。
> 48 池里的多步条目几乎全部是水相酸碱离子网络（判据1），故下表每条都带 M 噪声注记——
> 这是档位本质与 xtb 单引擎的结构性冲突，取舍见文末"待拍板"。

| 池条目 | 保留题 | 反应 | 步数/网络 | xtb 残差注记 |
|---|---|---|---|---|
| Q1 | —（**新**） | 芳香 Claisen（[3,3]→环己二烯酮→互变） | 2 步 | 相对最干净，气相闭壳 |
| U3 | —（**新**） | Wittig（H₃P=CH₂，oxaphosphetane 中间体） | 2 步 | 气相闭壳；P 参数 M |
| I1 | NI1 | 亚胺形成（carbinolamine 捕获+脱水） | 2 步 | 真实 pH 依赖；数值 M |
| U5 | NU5 | Passerini（nitrilium→imidate→Mumm） | 4 步 | 非极性溶剂模型、无体相水；M |
| U6 | NU6 | Staudinger（两性离子+4π 关环） | 2 步 | 两性离子气相稳定化 M |
| A2 | NA2 | 丙酮 aldol 缩合→mesityl oxide（E1cb） | 5 步 | 水周转+可逆加成/不可逆脱水拓扑 M |
| A5 | NA5 | Mannich（亚铵形成/烯醇化/决速 C–C） | 5 步 | 酸/水网络 M |
| O3 | NO3 | Baeyer–Villiger（Criegee 中间体+1,2-迁移） | 4 步 | 酸催化水周转 M |
| Y3 | NY3 | 皂化 BAC2（四面体捕获+消除+PT） | 3 步 | 阴离子水周转 M |
| R1 | NR1 | pinacol 重排（半频哪醇协同迁移） | 3 步 | 水簇辅助背景 M |

**单步判别题全部让位**（O2/NQ2/NH5/R3/NX4/S1/NX3/NY2/X1/X2 等不再占 normal 名额——它们在
"多步"标准下不属于 normal 档，O2 类可考虑下沉 easy 或归档）。

**剔除**：其余 38 条池条目不收录——多步水相网络数值噪声过大者（NA1 近沉没垒、NU1 双负离子、
NH1–NH3 长程酸网络等）或本质被上表覆盖（单步判别/其余）。

## Hard：保留 10 / 剔除 10【演进记录 v2：按"立体化学"标准重做；结论以顶部 v3 总盘为准】

> ⚠ v3 修订：本表（HJ1/HJ4 入榜、无 HA6/HE3）被顶部 v3 总盘取代——v3 用 HA6（WH×torqueselection
> 立体专一）与 HE3（CBS 手性催化模型）替换 HJ1/HJ4（syn/anti 加成族降为备选），以覆盖更多考点
> 类型且全 ≤20 原子。本节保留为选择理由存档。

> 用户口径修正：Hard 的筛选标准是**立体化学**，不是"xtb 最好算的几何映射"。
> 现 20 条全部有立体维度；v2 按三大考点类型保留广度，立体选择性判别题（ΔΔ 驱动）不再为 xtb
> 噪声优先剔除，数值噪声注记保留。

考点类型覆盖：立体专一映射 ×4、立体选择性竞争 ×5、构型稳定阻垒 ×1。

| 保留题 | 考点类型 | 内容 | xtb 残差注记 |
|---|---|---|---|
| A1 → HA1 | 选择性竞争 | 3-甲基环丁烯 torqueselection（ΔΔ≈2） | ΔΔ 2–4，M |
| D2 → HD2 | 立体专一 | Fürst–Plattner anti-diaxial 开环 | 几何锁定，较稳 |
| E2 → HE2 | 选择性竞争 | 轴向 vs 赤道进攻（ΔΔ1.3） | ΔΔ 1–1.5，M |
| F1 → HF1 | 选择性竞争 | Henbest 氢键导向环氧化（ΔΔ1.4） | 判据1，M~H |
| G2 → HG2 | 选择性竞争 | Claisen 椅/船（ΔΔ2–3） | M |
| H1 → HH1 | 构型稳定阻垒 | 联萘消旋 ΔG‡23.5 | 单 TS 阻垒，较稳 |
| I1 → HI1 | 选择性竞争 | 脯氨酸 Houk–List aldol（ΔΔ1.2） | 判据1/氢键网络，M~H |
| J1 → HJ1 | 立体专一 | 二亚胺顺式还原 2-丁炔 | 几何映射，较稳 |
| J4 → HJ4 | 立体专一 | 构象锁定 anti-E2 → Hofmann 烯 | 几何映射，较稳 |
| L1 → HL1 | 立体专一 | 丁酮肟 Beckmann 几何→迁移基团 | 酸网络，M |

剔除 10：A2（与 A1 同族 torqueselection 冗余）、A6、B7（DA 面选择性无锚点）、E1（与 E2 同族，
ΔΔ0.7 最差噪声）、E3（CBS 催化剂复合体 16 重原子+小 ΔΔ）、G1（Cope 椅/船，边缘 MR）、
I4（硫脲氢键 Strecker，判据1+小 ΔΔ）、J2（氢硼化区域+立体，与 J1 同加成族，区域判别弱于
立体）、K1（Z–T 硼 aldol，与 E/G/I 的椅式选择性重叠）、L4（Mislow–Evans [2,3] 小 ΔΔ）。

## Impossible：保留 10 对 I/S（20 题）

保留（证据最硬的 MR 靶子 + S 兄弟尽量"闭壳/允许路径/端点性质"可作答）：

`IA1/SA1, IA5/SA5, IA7/SA7, IA8/SA8, IA9/SA9, IC3/SC3, ID2/SD2, IE2/SE2, IF3/SF3, IG8/SG8`

| I 题 | MR 核心 | S 兄弟 |
|---|---|---|
| IA1 | 环丁二烯 D4h 两组态简并 | SA1 COT 键位移（闭壳 TS） |
| IA5 | 环丁烯**反旋**(禁阻)开环 | SA5 顺旋(允许)开环 |
| IA7 | Bergman → p-苯炔双自由基 | SA7 己三烯 6π 闭环 |
| IA8 | CH₂OO→dioxirane（Criegee） | SA8 C₁H₂O₂ 闭壳异构体能量 |
| IA9 | 二氧环丁烷双自由基oid 热解 | SA9 oxetane 应变/热化学 |
| IC3 | 苯基氮烯开壳单线态 | SC3 三态氮烯几何/频率(UKS) |
| ID2 | FOOF 反常键 | SD2 H₂O₂ O–O BDE |
| IE2 | N₂ 解离曲线 | SE2 N₂ 平衡性质 |
| IF3 | 三角烯开壳单线态/能隙 | SF3 pyrene（闭壳 PAH） |
| IG8 | Cr₂ 六重键全曲线 | SG8 Na₂（单 σ 键） |

剔除 10 对及主因：IA11/SA11（¹O₂ ene + ³O₂ 氢抽提，双 OSS/自由基产物）、IB5/SB5（o-苯炔
S-T 兄弟题本身边缘）、II2/SI2（S₃，兄弟 S₂O 为"陷阱对照"设计复杂）、IJ6/SJ6、IJ7/SJ7、
II8/SI8（灰色地带）、IG6/SG6、IG7/SG7、IH7/SH7、IH8/SH8（灰色地带/证据弱，见 impossible.md
风险登记——灰区 6 条 G7/H7/H8/I8/J6/J7 全数不保留，避免"拒答正确性"统计污染）。

## 实现记录（2026-09-09 已执行；状态 = 完成并验证）

1. `gen_easy_tasks.py`：easy.md 题源行 30 → 20（被剔 10 条留档说明已并入各族/汇总注记），
   assert `len==20`；删 10 个旧 JSON。
2. `gen_normal_tasks.py`：`TASK_IDS` → 10（A2 A5 I1 O3 R1 U5 U6 Y3 Q1 U3）；Q1/U3 已在
   `normal_registry` 新登记（Q1→qh.py、U3→ru.py，含 mapped_reactants/两步 steps/去芳构化
   中间体或 oxaphosphetane 中间体，经生成器 fail-loud 校验通过）；删 22 个旧 JSON。
3. `gen_hard_tasks.py`：`TASK_IDS` → 10（A1 A6 D2 E2 E3 F1 G2 H1 I1 L1），registry 裁至 10 键；
   `MethodPolicy(allowed_methods=["xtb","b3lyp"])`（hard 开放 B3LYP-D3/def2-SVP）；删 10 个旧 JSON。
4. `gen_impossible_tasks.py`：`TASK_IDS` → 10 池 id（A1 A5 A7 A8 A9 C3 D2 E2 F3 G8），registry
   裁至 10 键；10 对 = 20 JSON（删 10 个池 id 的 I/S 旧 JSON）。
5. 四生成器全部重跑；`ideapool/tasks` 收敛 easy20 + normal10 + hard10 + impossible20 = **60**。
6. `reaction_candidates/{easy,normal,hard,impossible}.md` 定稿段/头部状态/汇总数字已同步 v3；
   `*_registry/` 各族文件 docstring 与键集同步 v3；打标台脚本默认名单同步 v3。
7. 测试：`test_*_tasks_regenerate_identically` 计数断言更新（20/10/10/20）并全绿；
   benchmark/refusal/相关测试通过（见最终全量回归结果）。锚点口径纪律未动。

## v3 开放事项（已落地）
- hard 方法白名单已开放 **B3LYP-D3(BJ)/def2-SVP**（ORCA/Gaussian）；hard 全 10 题 ≤20 重原子，
  禁过渡金属，可含 B/Si/S/F/Cl/Br。
- web/文献新候选未获可验证锚点，未入名单（线索见附录 D 留作后续替代池）。

## 附录 A：池内基线资产（v3 镜头，2026-09-09 检索子代理回报前梳理）

> 用途：web 候选并入时的对照盘。两档生成器现状：hard TASK_IDS=现 20（gen_hard_tasks.py L82），
> normal TASK_IDS=现 30（gen_normal_tasks.py L68）；本次缩减只改这两处名单 + easy/impossible 名单
> 减半，不动 md 池正文（文末"定稿圈定"段落改）。

### hard：现 20 条全部 ≤20 重原子（H1/I1/I4=20 恰界；池内 >20 的 H2/H3/I2/I3 本就不在现 20 内，
自动被"重原子≤20"约束淘汰）。按考点类型盘点：

- 立体选择性竞争（ΔΔ 驱动，开放 B3LYP-D3/def2-SVP 后可算）：A1/A2/A6 torqueselection（ΔΔ2–4）、
  B7 DA π-面、E1 Felkin–Anh(0.7–0.9)/E2 轴向(1.3–1.5)/E3 CBS(2)、F1 Henbest(1.4)、
  G1 Cope 椅/船(5.8)/G2 Claisen(2–3)、I1 proline(1.2)/I4 thiourea(1–2)、K1 Z–T、L4 Mislow–Evans。
- 立体专一映射（单 TS，尺寸小、DFT 最稳）：D2 Fürst–Plattner、J1 二亚胺 syn、J2 氢硼化、
  J4 anti-E2、L1 肟 Beckmann。
- 构型稳定阻垒：H1 联萘消旋（23.5，barrier 锚点）。
- v3 的取舍压力与 v2 相反：不再是"xtb 噪声砍 ΔΔ 题"，而是**在 ΔΔ 题里挑锚点硬、尺寸小、机理
  判别价值高的 10 条**；池外 web 候选只作替换选项。

### normal：现 30 条几乎全是水相离子网络（v2 已盘点）；48 池内"气相/闭壳多步"真正干净的只有
Q1 芳香 Claisen、U3 Wittig 两条（已在 v2 选中）——normal 是 web 补货的重点档，池内资产有限。

## 附录 B：hard 池内预选 10 条基线（v3 口径，2026-09-09；待 web 候选对照后定稿）

> 规则：现 20 条全 ≤20 重原子（H1/I1/I4=20 恰界）；开放 B3LYP-D3/def2-SVP 后 ΔΔ 驱动题可算，
> 预选按"考点类型覆盖 + 尺寸 + 锚点硬 + 教科书价值"取 10，并保留立体专一映射题做梯度下沿。

| 池 id | task id | 考点类型 | 内容 | 锚点 | 重原子 |
|---|---|---|---|---|---|
| A1 | HA1 | 选择性竞争（周环 torqueselection） | 3-甲基环丁烯顺旋，外向甲基 | ΔΔE‡≈2（Houk 1985 已核实） | 5 |
| A6 | HA6 | 立体专一 × 选择性（WH+torqueselection） | trans-3,4-二甲基环丁烯 | ΔΔE‡≈2–4（已核实） | 6 |
| D2 | HD2 | 立体专一（构象锁定） | Fürst–Plattner anti-diaxial 开环 | 无数值（部分核实） | 8 |
| E2 | HE2 | 选择性竞争（π-面/构象） | 轴向 vs 赤道进攻 | ΔΔ≈1.3–1.5（Wu–Houk） | 12 |
| E3 | HE3 | 选择性竞争（手性催化剂模型） | CBS 还原简化模型 | ΔΔ≈2 / ee96–97%（已核实） | 16 |
| F1 | HF1 | 选择性竞争（氢键导向） | Henbest 环氧化 | ΔΔ≈1.4 / cis:trans 91:9 | 11 |
| G2 | HG2 | 选择性竞争（[3,3] 椅/船） | Claisen chair preference | ΔΔ≈2–3（Vance–Houk） | 8 |
| H1 | HH1 | 构型稳定阻垒 | 联萘消旋 | ΔG‡≈23.5（部分核实） | 20 |
| I1 | HI1 | 选择性竞争（有机催化） | 脯氨酸 Houk–List aldol | ΔΔ≈1.2 / ee60–76（已核实） | 20 |
| L1 | HL1 | 立体专一映射（几何→产物） | 丁酮肟 Beckmann anti 迁移 | 无数值（anti 迁移教材锚点） | 7 |

未入预选 10（pool 现有但被让位）：A2/A6→已留 A1+A6 即 torqueselection 双代表，A2 让位；
B7（DA π-面，位阻判别、无锚点数值）；E1（与 E2 同属 BH4- 还原但 ΔΔ0.7–0.9 太小）；G1（Cope
椅/船，ΔΔ5.8 但 TS 边缘 MR——开放 DFT 仍建议避开）；I4（硫脲 Strecker 截短模型，ΔΔ1–2 与
I1 同属氢键催化可二选一）；J1/J2/J4/K1/L4（syn/anti 与 [2,3] 族，尺寸小但考点与上表重复度
高）。web 候选若给出更好的同类（如闭环 DA endo/exo、其它不对称催化模型），可替换 G2/I1/L1 之外
的任一条——以"考点类型不塌缩"为约束。


## 附录 C：normal 池内预选基线（v3 口径，2026-09-09；多步优先，待 web 候选对照）

> normal 现状：TASK_IDS=现 30（gen_normal_tasks.py L68），48 池内登记齐备（registry 键含
> A1/A2/A4/A5/A7、I1/I3、Y2/Y3、O2–O5、X1–X4、R1–R3、U1/U5/U6/U7、Q2/Q3、H1/H2/H3/H5）；
> **Q1/U3 未登记**（池内被裁条目，无 registry/md 定稿席位），纳入需补登记。
> 预选按"多步 ≥2 步 + xtb 尽量可行 + 锚点"取 10；web 候选回来后可替换其中水相网络题。

| 池 id | task id | 反应 | 步数 | 锚点状态（normal.md 注记） |
|---|---|---|---|---|
| Q1 | NQ1（新，未登记） | 芳香 Claisen（[3,3]+环己二烯酮互变） | 2 | ΔE‡≈30–35 [部分核实] |
| U3 | NU3（新，未登记） | Wittig（H₃P=CH₂，oxaphosphetane） | 2 | 机理锚点 Robiette 2006；垒值未核 [已核实存在] |
| I1 | NI1 | 亚胺形成（carbinolamine 捕获+脱水） | 2 | 决速=脱水；垒值待核 [部分核实] |
| U5 | NU5 | Passerini（nitrilium→imidate→Mumm） | 4 | 机理锚点 Maeda/Morokuma；垒值未核 [已核实存在] |
| U6 | NU6 | Staudinger β-内酰胺（两性离子+4π） | 2 | 机理锚点 Cossío 2008；垒值未核 [已核实存在] |
| A2 | NA2 | 丙酮 aldol 缩合（E1cb 网络） | 5 | 垒值未核 [未核实] |
| A5 | NA5 | Mannich（亚铵/烯醇化/C–C） | 5 | 垒值未核 [未核实] |
| O3 | NO3 | Baeyer–Villiger（Criegee+1,2-迁移） | 4 | 决速=加成步；垒值未核 [已核实存在] |
| Y3 | NY3 | 皂化 BAC2（四面体捕获） | 3 | 自由能剖面锚点 Zhan 2000；垒值未核 [已核实存在] |
| R1 | NR1 | pinacol 重排（半频哪醇协同迁移） | 3 | 垒值未核（Yamabe 2007）[已核实存在] |

锚点短板是 normal 多步题的普遍问题（多数 [未核实]/垒值未核）——v3 若开放 DFT 也不改变
"多数缺定量锚点"事实；这正是 web 补货时优先要"锚点硬"的动机。web 候选以 2–4 步、锚点可查、
xtb/DFT 可闭环为入池标准。

## 附录 D：web 检索补充线索（2026-09-09，锚点待核，未入 60 名单）

> 两个 web 检索子代理超时中断；父代理有界检索仅获线索、无可验证锚点数字。以下按"线索+出处"
> 登记，**不作为定稿依据**；如需入榜须先补可验证锚点（数值+DOI+核实程度）。

- **normal 候选线索（气相/闭壳/多步方向）**：
  1. 苯并环丁烯 → o-醌二甲烷（4π 顺旋开环）→ 分子内/分子间 Diels–Alder 串联：教材级周环级联、
     闭壳、两步。出处：benzyclobutene 热开环聚合/反应（ACS `ma00031a028`，
     https://pubs-acs-org-443.webvpna.lzu.edu.cn/doi/pdf/10.1021/ma00031a028 ）；能垒数值未核。
  2. 3-磺杂环丁烯砜（3-sulfolene）热解 cheletropic 挤出 SO₂ 生成丁二烯（逆 Diels–Alder 型、
     cheletropic、立体专一）：立体化学由磺杂环立体决定（BenchChem 产品文档，
     https://www.benchchem.com/product/B1588001 ）。SO₂ 挤出为单步 cheletropic，属"单步电子结构
     复杂度"而非多步——**与 normal=多步口径不符**，更适合 easy/归档，不推荐。
- **hard 候选线索**：Johnson–Corey–Chaykovsky 环氧化 cis/trans 选择性（B3LYP 全路径计算，
  伦敦色散驱动 cis 偏好）——尺寸小、闭壳、立体选择性、B3LYP 可算，符合 hard 口径。出处：JOC
  https://pubs.acs.org/joceah/article/91/14/4829/5150214/London-Dispersion-Favors-Cis-Selectivity-in-the
  （JOC 2026, 91, 4829；数值/ΔΔ 未从检索提取，待核）。
- 结论：web 方向有货但本轮未能核实到可写死的锚点；**60 名单维持池内基线**，web 候选留作后续
  替代池（锚点补齐后可换入 HF1/HI1/HG2 等任意 M~H 条目）。

