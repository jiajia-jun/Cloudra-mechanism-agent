# Easy 案例核查：F4、G2 与 D1/D3/L2

核查日期：2026-10-31。仅读取原档、正式出版评分表和评分源码；不重跑量化计算，不更改正式分数。

运行身份以正式`publication_scores_per_run.csv`的campaign+arm+task+sandbox四元组为准；FULL中的其它同题试运行不替代正式留存运行。

已完成：FULL归档一次共享定向提取后，核对五题各臂正式留存的根机理图、原生日志、运行报告和benchmark.db；对Guided/G2另外读取runtime-v2.db中的真实门控、交付报告与文件变更事件。

## 先区分 Accuracy 0、完整性短路、SC 扣分和运行门控

- Guided/F4：Graph=0.6009018554、SC_all=1、Accuracy=0、Composite=0.3601。它保留了0.3的SC贡献；若触发Accuracy fail-loud，综合分只会剩0.0601。
- Guided/G2：Graph=0.8888888889、SC=0.5、Accuracy=0、Composite=0.2389。它保留了0.15的SC贡献；若触发fail-loud，综合分只会剩0.0889。
- 因此这两个正式0准确度不是“整体完整性短路”，也不能单凭0分称为运行期科学门控误拒。必须回到参考步骤、根图中的科学声明和可计算的原始证据组合。
- F4的SC_all=1同时伴随SC_gold=0。单凭该组合不能裁定计算内容；本次原件进一步证实其交付的16.02-kcal/mol路径及端点链完整，参考子图0来自历史Gold反应物身份不一致，详见下文。

权威实现：`cloudra/benchmark/accuracy.py:543`起，缺少与参考端点匹配的已交付数值步骤或缺少能垒声明时，仅该参考边记0；`cloudra/benchmark/accuracy.py:646`起的fail-loud针对无据/不一致声明；`cloudra/benchmark/runner.py:516`起的fail-loud综合分才只保留图分。SC层、Accuracy层和运行期DAG门控是三个不同对象。

## D1/D3/L2 的 Accuracy=.7：数值高斯罚分封顶

这里的Gaussian是高斯误差函数，不是Gaussian量化软件的特殊封顶。正式任务均声明`sigma_kcal_mol=3.0`和`max_penalty_fraction=0.3`。对有合法原生日志支持的数值参考边，先计算

`g = exp[-(E_agent-E_gold)^2/(2 sigma^2)]`

再将这一类数值偏差的罚分封顶到0.3，因此单参考边的最终Accuracy最低为0.7。缺步骤、缺声明和无据声明不享受这一数值保底。实现为`accuracy.py:660–674`。

| 正式留存运行 | 原生日志推导能垒 | Gold | 原始高斯分 | 最终Accuracy | 数据库原句 |
|---|---:|---:|---:|---:|---|
| Guided/D1（P2c） | 15.738 | 18.830 | 0.5880 | 0.7000 | `numeric penalty 0.412 capped at 0.3`（原benchmark.db已读） |
| Record/D1（P2b） | 15.738 | 18.830 | 0.5880 | 0.7000 | `numeric penalty 0.412 capped at 0.3`（原benchmark.db已读） |
| Guided/D3（P2b） | 18.147 | 14.650 | 0.5070 | 0.7000 | `numeric penalty 0.493 capped at 0.3`（原benchmark.db已读） |
| Brief/D3（P2c） | 18.147 | 14.650 | 0.5070 | 0.7000 | 原benchmark.db/策展评分记录相互印证 |
| Guided/L2（P2c） | 18.987 | 29.770 | 0.0016 | 0.7000 | 原benchmark.db/策展评分记录相互印证 |
| Standard/L2（P2c） | 18.987 | 29.770 | 0.0016 | 0.7000 | 原benchmark.db/策展评分记录相互印证 |

不能把这些0.7解读为“70%的科学通过率”或“gate拒掉30%的计算”。它们是原有Accuracy函数对数值偏差的具体计分结果。

## 已核实的 D3：不同驻点的数值差与两臂共有的端点关联问题

正式留存路径（以下均相对于`/private/tmp/cloudra_revision_full/`；归档中的前缀为`Cloudra-P2-final-20261031/campaign_data/`）：

- Guided：`cloudra-p2b-20261025/guided/r1/sandboxes/D3/batch_c0a6d8a4926b4f71/`
- Standard：`cloudra-p2b-20261025/standard/r1/sandboxes/D3/batch_83e66379d23c4f66/`

| 原生事实 | Guided | Standard |
|---|---|---|
| 绑定TS日志 | `gjf/TS_endo_v1.log` | `ts/ts_0001/jobs/declaration_0014/frequency/frequency.log` |
| E(TS)/Ha | −387.935351329 | −387.941233522 |
| 绑定RC日志 | `gjf/RC_min.log` | `min/rc/jobs/rc1_endo_h33.log` |
| E(RC)/Ha | −387.964270202 | −387.964427951 |
| 绑定产物日志 | `gjf/P_min_check.log` | `min/prod/jobs/pendo.log` |
| E(P)/Ha | −387.996736648 | −387.995962027 |
| TS负频/cm⁻¹ | −473.3456（仅一个） | −442.1728（仅一个） |
| RC与产物负频 | 均0 | 均0 |
| 正常终止 | 三个绑定日志均有原生Normal termination | 三个绑定日志均有原生Normal termination |
| 日志能垒/kcal mol⁻¹ | 18.146867 | 14.554724 |
| 正式Graph/SC/Accuracy/Composite | 1 / .75 / .7 / .7450 | 1 / .75 / .99949582 / .9247 |

两条路径均由原图称为endo Diels–Alder。Guided TS的两条形成键约2.098/2.390 Å，Standard原图记录约2.839/1.970 Å。RC能量只差约0.099 kcal/mol，而TS能量差约3.691 kcal/mol，所以能垒差主要来自交付的不同鞍点，不能未经检验归咎于RC参照或低频门控。这里只陈述各自原图的通道声明和原生日志事实，不凭能量相似或名称判定它们与Gold的几何身份。

原`benchmark.db`对两臂都给SC=.75，均有`TARGET/product: no zero-imaginary minimum matches the declared species`及一侧端点链未闭合的评分警告。这一SC问题与Guided的Accuracy=.7是分开记录的。Guided的PROCESS.md还记录多次原生IRC/端点证据提交、Supervisor对目标匹配问题的诊断，以及为保留数值而增设等价`endo_barrier_measurement`边。模型/Supervisor的归因须与真实日志和事件返回交叉核对，不能单独作为“gate误拒已证实”的依据。

## 已核实的 Record/D1：完整SC与偏差能垒同时存在

正式留存运行：`cloudra-p2b-20261025/record/r1/sandboxes/D1/batch_15b04dbf5d6d4fbf/`。

根图把反应物定义为s-cis丁二烯与乙烯的预反应π复合物，绑定`runs/rc_complex_v3_tight_optfreq.log`，E=−234.426859803 Ha；TS绑定`ts/ts_0002/jobs/declaration_0001/frequency/frequency.log`，E=−234.401779338 Ha、唯一虚频−516.5008 cm⁻¹；产物绑定`runs/cylcohexene_optfreq.log`，E=−234.504281936 Ha。三个日志均正常终止，RC与产物均零负频。能量差推得15.738229 kcal/mol，与根图15.74一致。

原benchmark.db明确给`selfconsistency_passed=1`、SC=1和Accuracy=.7，最后两条notes为`log-derived 15.738 vs gold 18.830 ... -> 0.5880`及`numeric penalty 0.412 capped at 0.3`。这构成直接反例：Accuracy=.7可以与完整SC并存，并非被gate拒收。

## F4：已算出正确的16.02，零准确度来自历史Gold端点身份

正式运行目录前缀为`cloudra-p2c-20261025/{arm}/r1/sandboxes/F4/`，Guided批次`batch_94084d85d0634ca0`、Standard批次`batch_8b2051b670f348ba`、Record批次`batch_76e567788441411d`、Brief批次`batch_1807f734104147cb`。

### 根图和原生日志事实

Guided根图确实有三个节点和一条目标氢负离子迁移边，`barrier_kcal_mol=16.02`。反应物是Lewis加合物`[BH3-][O+]=C`，产物`COB`，不是漏做此反应，也不是只写一个无据数字。

| 节点/链 | 相对Guided/F4运行目录的真实原件 | 原生SCF能量/Ha | 原生负频 |
|---|---|---:|---|
| Lewis adduct RC | `qc/rc_optfreq.log` | −141.041124115 | 0 |
| TS Opt | `ts/ts_0001/jobs/declaration_0010/ts_opt/refine.log` | −141.015601446 | 一个，−398.7217 cm⁻¹ |
| 独立TS Freq | `ts/ts_0001/jobs/declaration_0010/frequency/frequency.log` | −141.015601446 | 一个，−398.7218 cm⁻¹ |
| Methoxyborane P | `qc/p2_optfreq.log` | −141.113508768 | 0 |
| IRC末帧→RC Opt/Freq | `.cloudra/evidence/a42cdc9b40e29bb1_end_b_optfreq.log` | −141.041124238 | 0 |
| IRC末帧→P Opt/Freq | `.cloudra/evidence/4987018d28c6711c_end_a_optfreq.log` | −141.113508749 | 0 |

以上日志均读到原生正常终止；两个末帧优化日志均有`Optimization completed.`。由绑定RC与TS能量复算`ΔE‡=16.0157166 kcal/mol`，与交付16.02、Gold16.02一致。双向IRC原件为`ts/ts_0001/jobs/declaration_0011/irc/irc.log`；它到达最大点数而非全路径收敛，但真实两侧末帧经后续Opt/Freq收敛至相应零虚频极小值，正是项目既有允许的方向证明口径。运行报告从早期“摆动/构象鞍点”疑虑修正为目标RC→P路径，后续通过同一TS的双向IRC与末帧优化闭合；不能把早期怀疑当最终失败。

四臂交付的相关能量几乎相同：

| Workflow | 根图RC写法 | E(RC)/Ha | E(TS)/Ha | 数值字段 | 正式Composite / SC / Accuracy |
|---|---|---:|---:|---:|---|
| Guided | `[BH3-][O+]=C` | −141.041124115 | −141.015601446 | 16.02 | .3601 / 1 / 0 |
| Brief | `[CH2]=[O+][BH3-]` | −141.041124147 | −141.015601449 | 16.02 | .3601 / 1 / 0 |
| Standard | `[BH3].C=O` | −141.041124245 | −141.015601444 | 16.02 | .9083 / .75 / .99999902 |
| Record | `[BH3].C=O` | −141.041124692 | −141.015601126 | 16.02 | .9167 / .75 / .99999923 |

Standard和Record各自绑定日志：Standard `inputs/ep_rc_optfreq.log`、`ts_work/qm/ts_ts_optfreq.log`、`inputs/ep_p_optfreq.log`；Record `rc_min_m.log`、`ts1_optfreq_v2.log`、`p_conf1.log`。其RC原子几何是相同Lewis加合物，而节点/输入注释沿用了dot-joined分离片段写法。

### 导致零分的确切参考差异

1. `git show 53309d0e:ideapool/tasks/easy/F4.json`中的Gold节点`F4_R.smiles=["[BH3].C=O"]`，但同一Gold边的`step_type`已经写明从Lewis adduct出发、参考能垒16.02。
2. `git show 0b7b5e5b -- ideapool/tasks/easy/F4.json`仅把这个反应物节点改为`[BH3-][O+]=C`。该提交说明明确记录：原Gold节点与真实`adduct_opt`参考、题目要求和能垒定义矛盾；修正后的既有验证sandbox中Guided accuracy从0变为1。
3. 交付包`docs/ADJUDICATION_METHOD.md`第430–434行明确写明离线重评分仍使用campaign base `53309d0e`，**不包括**后来的`0b7b5e5b` F4 reference correction。
4. 本次P2c Guided/F4原benchmark.db只有一句Accuracy notes：`gold edge F4_E1 carries a reference barrier but no delivered step matches its endpoint species; scored 0`。根图中明明有16.02，原始日志也直接支持它。
5. Standard/Record原DB仍是修正前的.2583；正式出版表中的.9083/.9167来自`tables/d4_validation.json`已记录的annotation-identity恢复，不是新计算。旧`reports/divergence_table.md`和`catalog.csv`中“missing_adduct_species / .2583”的文字已被该修正超越，不能作为正式结果里的化学失败证据。

**归类：历史参考身份/表示不一致造成的匹配损失。不是漏步骤、漏数值、无据声明短路，也不是本题的低频/IRC门控误拒。** 本核查保持发布分数不动，不把旧验证提交的修正后分数直接替换成新的P2c正式值。

## G2：原生鞍点与约0.845能垒存在，最终图丢掉结构化字段

正式运行目录：`cloudra-p2c-20261025/guided/r1/sandboxes/G2/batch_94084d85d0634ca0/`。

### 计算内容与最终图是两件不同的事实

| 原生日志 | 能量/Ha | 频率/状态 |
|---|---:|---|
| `work/ts_cis/ts_annot/ts1_attemptA.log` | −189.093172517 | 正常终止，唯一虚频−444.9504 cm⁻¹，对应同步双H转移 |
| `work/ts_cis/rc_candidates/candA_optfreq.log` | −189.094518484 | 正常终止，0虚频，cis复合物 |
| `work/final_irc/end_b_optfreq.log` | −189.094518735 | 正常终止，0虚频，IRC所达cis复合物 |
| `work/annotated/p_complex/p_complex.log` | −189.219234176 | 正常终止，0虚频，N₂···乙烷复合物 |

用原生SCF能量复算，两个cis参照分别给`0.8446070`和`0.8447645 kcal/mol`，均接近Gold0.87。过程注释里`.8437/.844/.845`的末位叙述不作为复算输入；这里直接使用日志数值。最后的根`mechanism_graph.json`却有：

- TS节点`sp_23b4012d.properties`仅保留说明文字，缺`energy_hartree`与`evidence_log`；
- 三条边`step_066d0568`、`e2`、`step_dd49a770`全部缺`barrier_kcal_mol`，只有`barrier_text`、`barrier_ts_log`等自由说明；
- “delivery_scope_note”仍声称有数值字段，已经与最终JSON实体内容不符。

原评分notes逐条写明没有显式TS证据绑定、不能由图中TS推导能垒、最后没有可匹配的数值步骤。SC=.5、Accuracy=0、总分.2389；没有发生fail-loud。

### 真实运行事件定位了字段丢失的过程

数据库：`cloudra-p2c-20261025/guided/r1/runtime/runtime-v2.db`；G2 project ID为`prj_0130e29641f44aa8`。

| 原事件 | 类型/事实 |
|---|---|
| `evt_237e1a81b3904e7e`、`evt_49fcca782e3f4344`、`evt_28f2d138d88544f0`、`evt_075852a227314acb` | completion gate四次明确返回`Step 'step_066d0568' cannot declare a barrier before its DAG scientific checks and review pass.` |
| `evt_8a044cebb5ec4de7`、`evt_d20798c852c64959`、`evt_1eefff6ea90242d7`、`evt_7009a17edec0407b`、`evt_93c36c005e8c4c2d` | `dag_delivery_report`真实返回`complete=true, unresolved=[]`，交付目标是另一条`step_dd49a770`及其端点；不是只根据模型自称“complete” |
| `evt_3454973588dc4548`（rowid92414） | `program.submitted`源代码明确循环执行`delete e.barrier_kcal_mol; delete e.barrier;`，改用文本数字；说明理由是避开伴随complex-product边未通过时的barrier声明限制 |
| `evt_993d79fe8e8b4aea`（rowid92443） | 文件write成功，记录`mechanism_graph.json`的前后hash及diff |
| `evt_9902d336b8f74863`（rowid92446） | 程序输出确认`any barrier_kcal_mol: false; any barrier block: false; ts energy claim: false` |

事件顺序还记录了之后的“恢复→再拒绝→最终删除”，不能把四次barrier拒绝都说成发生在rowid92414那次早期删除之前：

| 原事件及UTC时间 | 最终交付轨迹 |
|---|---|
| `evt_11ba84b4a00744ed`，05:22:47.808，rowid92959 | Supervisor要求修复后，实际程序恢复三条边的数值barrier，并恢复TS的`energy_hartree`及`evidence_log`。 |
| `evt_075852a227314acb`，05:24:33.345，rowid93256 | 第四次实际barrier拒绝仍指向开放的`step_066d0568`。 |
| `evt_976f396726d849e0`，05:24:39.244，rowid93262 | 先删除两条伴随边数值，暂时保留已选目标`step_dd49a770`的barrier及TS绑定。 |
| `evt_fb7ba6b2e4c54892`，05:25:00.326，rowid93316 | 实际artifact检查进一步返回`TS 'sp_23b4012d' cannot claim saddle evidence without bound converged optimization and frequency logs.` |
| `evt_275b1d315c474d14`，05:25:04.943，rowid93343 | 程序明确删除最后目标边`barrier_kcal_mol`及`barrier`，同时删除TS的`energy_hartree`和`evidence_log`。 |
| `evt_693b8814785341e3`，05:25:09.232，rowid93368；`evt_c5e66fd8e8c34936`，05:25:09.334，rowid93371 | write真实成功且保存diff，随后程序输出`barriers numeric: step_066d0568=undefined,e2=undefined,step_dd49a770=undefined ; ts claim: false`，与本次读取的最终根图一致。 |

当前实际门控代码`cloudra/dag/delivery_artifact.py:245–250`仍明确要求：

```python
step_checks = scientific_checks(element)
checks[edge.id] = step_checks
if step_checks.get('short_irc', {}).get('status') == 'passed':
    step_endpoint_evidence[edge.id] = endpoint_evidence(element)
verified = element.edge_id not in open_targets and all(c['status'] == 'passed' for c in step_checks.values())
if edge.barrier_kcal_mol is not None and not verified:
    raise ValueError(f'Step {edge.id!r} cannot declare a barrier before its DAG scientific checks and review pass.')
```

当同一鞍点同时写成complex-product与separated-products三条边时，已完成的交付目标和仍开放的伴随边并存。这个artifact核对要求使“保留已经算出的数值”和“声称整步所有科学阶段通过”发生耦合。Coordinator在多次核对后删除了数值和TS证据字段；Supervisor的PROCESS.md同时反复要求恢复字段，认为阶段状态不应抹掉已计算事实。这不是“模型没按schema填”这么简单，也不等于放宽IRC判据：**同一个物理结果在DAG、交付目标和根机理图三个表示之间没有由程序单源保存，最终由LLM手动协调，造成可观测的交付退化。**

过程另有真实科学问题：loose N₂···乙烷复合物一侧从真实末帧优化曾落到−305.8 cm⁻¹的libration saddle，不能把它叫“极低虚频被错拒”。后来以各分离产物极小值表达的目标边获得`short_irc`/ts_opt/frequency通过，上表真实delivery报告也确认完成。本文结论只涉及最终字段损失及其实际门控反馈，不据此宣称此前每一次IRC拒绝都是错误。

### 实际backbone比较

| Workflow | E(TS)/Ha | 交付参照及其能量/Ha | 最终数值字段 | 正式Accuracy |
|---|---:|---|---:|---:|
| Guided | −189.093172517（真实日志存在，根TS节点未绑定） | cis RC −189.094518484 / IRC cis RC −189.094518735 | 全部删除，只留文本 | 0 |
| Standard | −189.093173116 | `work/stepwise/RC2_optfreq.log`，−189.098621313 | 3.4 | .8781594 |
| Record | −189.093173143 | `rc_scan/C4_stack_trans_optfreq.log`，−189.098621312 | 3.42 | .8781610 |
| Brief | −189.093173082 | `ts/.../declaration_0006/reactant_frequency/reactant_frequency.log`，−189.094518011 | .844 | .9999864 |

Standard/Record的鞍点与Guided/Brief的能量接近；其约3.419值来自更低的RC参照。Record原PROCESS.md将该RC明确描述为trans-HN=NH stack，并同时给出IRC可达cis参照的约.84；Standard亦记录两参照，称其是同一RC状态的更低构象。这里应保留E/Z化学身份与构象归属的区别，不能只看都写成`N=N.C=C`就自行认定可共用参照；本核查不另裁科学题目或改分。

**归类：科学计算结果存在；最终结构化TS绑定与数值声明丢失；运行门控与多表示手工协调是有事件证据的促发因素。不是错算成0，不是无据声明fail-loud。**

## D1：参照构象而非鞍点能量解释约3.12 kcal/mol差异

正式Guided/D1的TS是−234.401779266 Ha，Standard/D1是−234.401779231 Ha，几乎相同。Guided RC是−234.426859803 Ha，Standard RC是−234.431829587 Ha；参照差3.1185865 kcal/mol，解释15.7382746与18.8568831两种能垒。

原生日志最终Standard orientation中，四个丁二烯碳的二面角C1–C2–C3–C4：Guided `final/RC_complex.log`约26.33°，Standard `rc/rc_opt.log`约−179.93°。前者是折叠的reactive s-cis复合物，后者是s-trans复合物。Guided的PROCESS.md明确讨论了s-cis通道参照；Standard交付了能量更低的verified RC。Record/D1采用与Guided相同的s-cis RC能量和15.74，且其SC=1。三者的差别不是“只会单步”或低虚频拦截，而是物种状态、反应构象和能量参照如何一直保持关联。

## L2：Guided缺稳定构象项，Standard已交两种参照但评分选了局部边

Guided正式L2根图明确使用cZc minimum：E(RC)=−233.233672607 Ha、E(TS)=−233.203414267 Ha，给18.9873950 kcal/mol；并主动注明s-trans,s-trans→cisoid项未算。原生RC日志为`endpoint_combined/.cloudra/execution-510/results/reactant_optfreq.log`，0虚频；TS原生日志为`ts/ts_0001/jobs/declaration_0003/frequency/.cloudra/execution-457/results/frequency.log`，唯一虚频−566.4629 cm⁻¹。Record/Brief则用tZt RC约−233.248473353 Ha，给28.27499 kcal/mol；局部与稳定参照差约9.28761 kcal/mol。

Standard/L2尤其不能误写成“没有考虑稳定参照”：根图**同时**保留`RC` tZt（`hexatriene_tZt_optfreq.log`，−233.248473327 Ha）与`RC_cZc`（`rc_czc_hexatriene_optfreq.log`，−233.233672606 Ha），并交付`e1` cZc→P=18.99、`e2` tZt→P=28.28。原RESULTS.md也明确写出tZt全局极小值和9.288 kcal/mol构象差。

它的benchmark.db却明确匹配`gold L2_E1 -> delivered e1`，从而对18.987实施高斯罚分并封顶为.7。e1/e2的`bond_changes`完全相同；权威`species_substitution_cost`对Gold无立体标记的`C=CC=CC=C`与这两个RC都给0，匹配的末级tie-break按edge ID字典序，于是e1在前。Record/Brief恰好把28.27放在e1，获得.8832。**Standard的数值知识与它被选中评分的那条边不同，Accuracy差还包含重复端点下参照边分配的影响。** 这与当前`accuracy.py:330–378`的候选排序机制一致；此处未重跑或替换正式评分。

L2另有实际IRC/SC事项：Cs对称IRC端点会落在约−50 cm⁻¹的扭转鞍点，其C₂ cZc零虚频极小值低约.62 kcal/mol。这个非零负频不能只因数值较小就自动当作verified minimum。原SC=.75或.5及frame-to-minimum关联警告与Accuracy对所选参照的.7分别记录；没有证据支持把全部差分都归因于“门控太保守”。

## 分类结论

| Task | 首要可核实原因 | 缺科学计算/步骤？ | 结构化/匹配因素 | 完整性短路？ | 与门控的关系 |
|---|---|---|---|---|---|
| F4 | 历史Gold把Lewis adduct写成分离片段 | 本次原件有16.02与完整TS–IRC–端点链 | Gold端点身份匹配失配；表示修正对不同臂有不同已发布影响 | 否 | 不能把Accuracy0归为低频/IRC误拒 |
| G2 | 最终图删去TS能量/日志绑定及所有数值barrier | 原始日志有约.845同步双H转移；selected DAG目标曾complete=true | 根图科学事实序列化丢失 | 否 | 四次实际barrier门控反馈后发生字段删除，有真实事件链 |
| D1 | s-cis与更低s-trans RC参照 | 交付局部反应路径；能量分母不同 | 科学参照选择 | 否 | .7直接来自高斯数值罚分封顶；SC可以同时1 |
| D3 | 交付鞍点能量不同，RC差很小 | 两臂都有一阶鞍点/原生路径，SC均.75 | 两臂均有产品端匹配警告；Accuracy差由数值决定 | 否 | 不能把Accuracy=.7和端点警告混成同一原因 |
| L2 | cZc局部参照与tZt稳定参照；Standard还存在匹配选边因素 | Guided未交稳定构象项；Standard已交两种参照 | 重复端点/相同键变化候选以edge ID tie-break | 否 | .7是选中局部barrier后的封顶数值罚分；独立SC问题需单独表述 |

## 可直接写入英文论文的最小段落

### Results

Inspection of five Easy tasks traced component scores to specific chemical objects and delivery events. In F4, Guided delivered a log-supported 16.016-kcal/mol hydride-transfer pathway with full graded self-consistency; its zero accuracy arose from the historical reference's reactant-identity mismatch. In G2, native logs supported an approximately 0.845-kcal/mol double-H-transfer barrier. Checks rejected barrier declarations four times; after a restoration attempt and a further saddle-evidence rejection, the final graph lost its numerical barriers and saddle bindings. Brief retained the corresponding numerical result. Accuracy values of 0.7 in D1, D3, and L2 followed the specified numerical-deviation cap. D1's difference from Standard traced to the reactant-conformer reference, whereas D3's barrier difference mainly reflected different saddle energies. L2 distinguished a reactive cZc reference from the lower tZt minimum. Standard delivered both associated barriers, 18.99 and 28.28 kcal/mol, but reference matching selected the former. The released score table retains these outcomes.

### Discussion

These trajectories identify a systems requirement for evidence-guided research: calculated quantities, the scientific claims they support, and the status of remaining validation must persist as separate records of the same chemical object. F4 requires consistent reference identities across task versions. G2 shows how manual reconciliation of a research DAG and its exported mechanism graph can remove already computed facts when numerical declaration is coupled to completion status. D1 and L2 require a persistent distinction between a reactive conformer, the stable-state reference, and the actual IRC endpoint; L2 also requires that this reference distinction survive evaluation matching. Preserving these relations in the program would make subsequent scientific judgment and offline organization operate on the same physical record.

### 数据与措辞边界

本核查未重评分，也没有将已知F4修正后的验证结果当作新的P2c正式分数。当前出版表仍保留其发布值。若以后统一采用修正后的任务定义，需要明确task/scorer版本，并对四臂采用同一规则；不能只给某一条低分定向加分。本文也没有把“模式负频较小”“Supervisor说可以”或“单个阶段状态passed”直接当作物理验收充分条件。
