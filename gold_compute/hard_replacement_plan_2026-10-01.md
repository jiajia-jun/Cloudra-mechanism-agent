# Hard 换题执行记录 — 2026-10-01

## 用户决策与当前状态

用户原话：**“是难算还是根本没算，难算就换题”。**

HE3 与 HG2 已实际多轮计算，仍缺题目声明的有效通道，按本次授权启动换题。
不是未启动，也不把失败计算称为完成。既有证据及正式题历史保留。
HI1 当前 69/70/71/72 共 32CPU/50576MB 在运行，优先当前批次验收。
HL1 保留已验收的下游结果；E1 空值及 E2 caveat 不抹去。

本文件是新策展与执行方案，**不是正式 TaskSpec 或已验证 gold**。
正式 hard 名单目前仍为原十题；新候选通过科学验收后逐题替换 HE3/HG2。

## 新候选（来自本次独立文献检索）

### H6PI 候选：(2E,4Z,6E)-2,4,6-辛三烯热 6π 电环化

- 目标：立体专一映射到 cis-5,6-二甲基-1,3-环己二烯。
- C8H12，8 重原子、20 总原子，q0/m1。无催化剂、显式水或多步质子网络。
- 原始实验来源：Marvell 等，Tetrahedron 1973，29，3781–3789，
  [DOI 10.1016/0040-4020(73)80195-4](https://www.sciencedirect.com/science/article/abs/pii/0040402073801954)。
  原文报告纯 E,Z,E 底物热环化，氧化裂解所得 meso 二甲基琥珀酸支持 cis 身份。
- 本次只考第一热环化；不纳入后续 1,5-H 迁移、E,Z,Z/Z,Z,Z 平衡或光化学。
- 不把禁阻顺旋途径硬算为第二闭壳层通道；不构造虚假选择性能垒。
- 拟定自算口径：ORCA6.1.1，B3LYP-D3BJ/def2-SVP RIJCOSX/def2/J，TightSCF，气相。
  原文溶液实验活化参数仅作独立科学背景，不能混入气相电子能 gold。
- 必须核对三处 E/Z、原子映射与最终 cis；RC、相关一阶 TS、双向 IRC 和零虚频端点齐后方能入库。

### HDA_CN 候选：环戊二烯 + 丙烯腈 endo/exo Diels–Alder

- 目标：分别定位 endo/exo 立体路径，实际差值决定报告，不预设 favored。
- 合计 C8H9N，9 重原子、18 总原子，q0/m1；环戊二烯刚性预组织。
- 原始计算来源：James 等，J. Org. Chem. 2013，78，6582–6592，
  [DOI 10.1021/jo400900x，作者全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC3731169/)。
  该体系实验只给 DA 加成物；原文定位 endo/exo 协同 TS，竞争自由基路线较高。
- endo/exo 接近简并是预先披露的风险。不能拟合文献或放大微小差值，
  不能把近简并称为方法必然失败；报告两个通过验收的同方法能垒。
- 拟定口径同上，气相，RC 与所有 TS 统一 ORCA6.1.1。共用最低正确 RC。
- 两种独立相关一阶 TS、双向 IRC、端点身份/endo-exo 与零虚频全部验收后入库。
  不探索聚合/自由基或新增长 NEB。

## 去重与边界

本次对当前 ideapool/tasks/{easy,normal,hard} 与 hard_registry 检索，
没有辛三烯或丙烯腈正式条目。H6PI 与 easy 无取代己三烯不同，
HDA_CN 与 HB1 顺丁烯二酸酐不同；两者仍与现有周环题同族，
减少题型多样性是本次优先可算性的取舍。
不从旧题池抄队列；旧资料仅用于限制与去重。
遵守已有 1,3-偶极环加成排除、多参考体系排除规定。

## 执行顺序

1. 完成映射、立体结构与候选输入准备，保存独立目录；此阶段不提交 QM。
2. HI1 必要任务优先，不杀计算、不改运行输入。总资源不超过 32CPU/56000MB。
   只有已准备充分且存在真实资源余量时才唯一提交候选 QM；不为选题空等租机。
3. 新计算优先 8CPU；内存与 maxcore、账本一致，不设 Cloudra timeout/MaxIter。
   失败先分析，禁止提高迭代上限或无限初猜循环。
4. 科学验收通过后写新策展题源、registry、生成器和 TaskSpec，聚焦验证、提交推送。
   未通过的候选不替换正式题，不用文献数值冒充自算 gold。
5. 原 HE3/HG2 证据、缺测原因与历史标识保留，不覆盖原始文件。
6. 全部必要远端 QM 完成且无必要续算后完整增量备份、SQLite backup 一致快照、SHA 核验，
   再核对控制台正确实例停止计算计费。既有归档和费用诚实报告要求保持。

## 尚未完成

已在 `hard_replacements_20261001/` 完成映射及 MMFF 初猜：H6PI 反应物三处 E/Z=E,Z,E，
cis 产物两个中心 CIP=S,R；HDA_CN 两个产物经桥原子与 CN 相对环面同侧/异侧区分 endo/exo。
重原子统一按 map 升序；OptFreq 草案均8核/14GB/maxcore1536、气相，无自设上限。
HDA_CN 的共同 RC、两题 TS 均尚未准备；未提交新 QM，未修改正式名单。
小型体系可算性是筛选判断，并非保证成功或费用/时长承诺。


## 20:58 SGT independent audit and live execution

Original H6PI product seed was trans and is retained as rejected preparation evidence. Corrected remote ts_prep/product_cis is cis/meso, globally mirrored canonical SMILES unchanged; actual unmapped 3D CIP is (2S,7R). Reactant actual E,Z,E verified. HDA corrected product geometry gives endo CN anti to bridge and exo CN syn. Unmapped 3D CIP is endo (2S,4S,7S), exo (2S,4S,7R); mapped/stale report values require correction. Atom-map removal and clearing old stereochemical properties matter when reporting canonical descriptors. Independent details: INDEPENDENT_AUDIT_20261001.json.

Remote HDA coordinator submitted unique74 RC and75 endo TS;76 exo was queued and now running.74 normal terminal awaits own identity/frequency audit. Existing child is handed74/75/76; coordinator reviews only. Initial Calc_Hess eigenvalues diagnose seed risk, never replace final OptTS+Freq acceptance or authorize killing/changing a running input. H6PI remains prepared/unsubmitted until capacity; no mandatory20-point DFT scan. Neither replacement is formal until scientific acceptance.


## 21:21 SGT production acceptance progress

HDA_CN75/76 both normal, converged, each one relevant negative final mode (-457.47/-455.01 cm-1), E=-364.441022024494/-364.441377753618 Eh. Independent final Hessian audit confirms both forming-bond distance derivatives have the same sign (asynchronous concerted closure candidate). Provisional barriers vs shared RC74: endo13.88/exo13.66 kcal/mol; near0.22 difference is not robust favored evidence. Both IRC plus endpoints still required. Unique executor submitted78 endo IRC running/79 exo IRC ready, reads actual final TS XYZ/Hess, uncapped. H6PI executor submitted77 direct TS running and80 extended EZE RC ready; no mandatory scan. Live72/73/77/78:32CPU/53288MB,79/80 queued resources not counted twice. HI1 needed endpoint followups retain higher priority. Nothing formally replaced yet.

New private terminal backup75:14 files3804991 bytes;76:14 files3978298 bytes, all SHA match; previous69/70/71/74 retained. Final whole-machine archive/billing-stop still pending.


## 21:50 SGT acceptance update

HI1 major E2 TS67 + IRC68 (forward self-converged, backward native20-step limit) + minima71/72 now accepted, headline15.5173 vs lowest correct RC51; own-reactant15.03 diagnostic only. Independent71 graph: iminium N4+/alkoxide O28-, two components including water, rings5/6, C8R+C29R. Independent72: neutral enamine+water+benzaldehyde, three components, rings5/6, C8R; COOH/H2O protons retained. Report typo C1=R corrected through actual author; CaC1 is CH2. Full HI1 remains pending minor73 and endpoints.

H6PI77 true related TS candidate E=-311.574110153506, one final imag-496.14;80 true EZE reference minimum E=-311.621082862658, zero imag, provisional29.48 kcal/mol. Executor automatically parsed and uniquely submitted81 both-directionIRC with actual final TS XYZ/Hess, uncapped. No second guess/scan.

Current73/78/79/81 running32CPU/55000MB; no ready.72 terminal backup15 files13402568 bytes;77 14 files5787334 bytes;80 13 files2765067 bytes, all SHA verified. Full final archive and platform billing-stop still pending.


## 2026-10-01 23:00 SGT authoritative acceptance and formal replacement

Both independently curated candidates passed actual same-method saddle/IRC-interval/zero-frequency endpoint and stereochemistry checks. H6PI workstream owner independently confirmed final PASS14:50Z. Original HE3→HA8 (H6PI), HG2→HB10 (HDA_CN) swaps now update source/registry/generator/TaskSpecs; all original source rows and evidence remain. Retired TaskSpecs are preserved in gold_compute/archive/retired_tasks_20261001. H6PI headline29.48 vs known-lowest qualified80 (not claimed global minimum); HDA endo14.34/exo14.12 vs shared lower86, near0.22 gap is not scored as a robust favored channel. All new IRC directions hit native20 steps; subsequent actual correct minima are frequency-verified. Full evidence/caveats: hard_replacements_verified_2026-10-01.md. Four focused regeneration/graph/no-answer-leak/selectivity-contract checks pass. HI1 job83 remains running; final whole-machine archive and platform-stop are pending.
