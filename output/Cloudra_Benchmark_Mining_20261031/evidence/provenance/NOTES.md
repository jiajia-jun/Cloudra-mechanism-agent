# P2 来源审计与投入分析（只读，2026-10-31）

输入为 `/Users/cloudrayyy/Desktop/Cloudra实验数据/Cloudra-P2-final-20261031`。这里只读取本地表和文档，未连远端、未重评分 sandbox、未运行 QM、未改原始数据。重算脚本是 `analyze_provenance_effort.py`；机器可读总览是 `analysis.json`。

## 一、先把实际样本和分数口径分开

1. `tables/final_scores_per_run.csv` 与 `runs/all_runs_detail.csv` 逐行相同，均为200条唯一 arm/task。只保留3条 P2b（guided/D3、record/D1、standard/D3）加197条 P2c。`runs/raw_scores_p2.csv` 的397行则是 P2b 200行加P2c197行，其中排除的197条恰好全是 `cancelled by batch stop`，不能按397次有效运行分析。最终表的200个 `raw_final` 与对应原始审计表完全相同。
2. 175行 `reports/catalog.csv` 是旧快照，17行分数和最终 `fair_final` 不同（逐行见 `catalog_final_deltas.csv`）。63行 `reports/flex_table.csv` 同样是旧快照，覆盖16题（59条 conformer/stereo-channel + D3的4条rigid）；brief/HH1尚未进入该表。所以只能把其投入作63条已观测研究记录，不可泛化全200，也不可引用旧报告中的175总体为最终总体。
3. 本地包没有原始sandbox或完整compute.db，无法重新核实失败原因、耗时计算的起止时点、计费核时、日志证据或 late graph 变化。README所称raw在 `/home/ly/cloudra-p2b-20261025` 与 `/home/ly/cloudra-p2c-20261025`。

| 口径 | guided | record | standard | brief-errors | overall |
|---|---:|---:|---:|---:|---:|
| raw（包括-1） | .668070 | .579312 | .284112 | .646812 | .5445765 |
| CSV fair（包括7个standard的-1） | .780322 | .704430 | .432496 | .741506 | .6646885 |
| 按文档让IC3修复独立后的fair* | .780322 | .704430 | .432496 | .713506 | .6576885 |
| README官方fair+repair | .780322 | .704430 | .594020 | .741506 | .7050695 |

*这是依据已记录决定作的口径敏感性，非独立重跑评分器。`docs/KNOWN_ISSUES.md:183-191`明示brief/IC3只在repaired轨道手修，原始为-1；但CSV把同一.4同时写入`fair_final`和`repaired_final`，因此抬高brief fair均值.028、总体.007。四臂排序不变，但brief/record差由.037076变.009076。

`docs/ADJUDICATION_METHOD.md:28-32,297`明确repair不混raw/fair、缺图保留-1；而README明确把8个人工修复纳入官方总分。这是最终交付选择了混合口径，不能把.705写成200次原生成功交付或独立科学成功率。`tables/FINAL_TABLES.md:18-24`写“Fair per arm × tier”却对standard排除-1：easy .847是17条有效行的均值，并非表中所写n=20的全体均值。主CSV可复算，阅读展示表时应自行选择同一分母。

## 二、交付修复抬分，主要在消除负罚分，并没有补出成功机理

7个standard缺图的修复分均值仅 **.153743**。把它们从-1换成修复分，使standard .432496→.594020，全体 .6646885→.7050695，增量.040381；其中 **.035（86.7%）只是把7个-1归零**，正分本身仅贡献.005381。假设只将缺图记0，全体已为.6996885。

因此：系统过早终结会把做过计算的研究压成负分，但修复文件并未解决科学探索本身。缺图修复的分数低，不支持“计算后来完成，所以本来应当高分”的推断。上述修复仅使用已存轨迹而非新算，亦不属于自主交付。

## 三、最终表还有6条借用raw，28条rescue，不能称200条均独立重评分完成

来源计数为snapshot166、rescue28、snapshot_timeout_filled6；rescue各为guided14、brief14，flags只有`rescued_parallel`，本地无详细重评分执行记录。

6条fair=raw为：brief NU5 .1983、P2 .9750；guided HA8 .9625、M16 .9748、NY3 1.0000；standard P2 .9833。`FINAL_TABLES.md:4`称“all are high”不准确，NU5只有.1983；6条graph/selfc/accuracy为空。借用raw是明确记录的回填，不能把空分项当0，也不能断言每条都完成了fix后重评分。去掉这6条后其余194条官方混合均分.700619，接近.705，但这不是新的正式分数。

guided/HI1：`reconstructions/INDEX.md`末段最终结果明确本次自主醒来并交付.9999，旧.9110/.9527只是中途/回退稿，不应再纳入repair。guided/HF1最终fair=.9742（raw crash0），使旧flex均值严重失真；brief/HL1最终raw/fair均.925，不需要按旧K9文字补成0或额外repair。

## 四、共同15题的投入：brief多花约一倍，而guided获得了有代价的改善

63行耗时是**累计job-hours**，不是墙钟时间、CPU核时或费用。为了避免brief缺HH1，以下使用共同15题60条（含D3这个rigid对照）。投入保留旧快照值，分数join最终表；standard按repair替代缺图，其余三臂为最终fair。`effort_pair_details_common15.csv`给出每题配对。

| 臂 | 每题平均job-h | 中位job-h | 最终均分 | ≥.9条数 | 作业失败+取消/总作业 |
|---|---:|---:|---:|---:|---:|
| guided | 11.079 | 7.06 | .812413 | 8/15 | 208/789 =26.36% |
| record | 7.877 | 8.19 | .735953 | 6/15 | 100/431 =23.20% |
| standard | 7.555 | 4.46 | .649480 | 5/15 | 95/419 =22.67% |
| brief-errors | 15.590 | 12.75 | .727333 | 6/15 | 287/883 =32.50% |

- brief vs record：总job-hours **1.979倍**，最终均分低.00862；此队列没有表现出更多尝试换来更好结果。
- guided vs brief：**少28.9% job-hours，均分高.08508**；15题中7题guided既更快又更高分。两种方式都“做更多事”，但耗费的产出不同。
- guided vs record：**多40.6% job-hours，均分高.07646**，10题更高、3题更低、2题近似持平；这有明确成本，不能沿用旧报告“几臂分数无差”或笼统说更多计算没有收益。这里仍是选择性队列中的描述，不能推因果。

全63条总计2604作业、673.82 job-h。按旧表失败归因，coverage14条消耗159.69h、verification24条215.91h，两类合计55.7%总job-hours；这是旧归因，不是新日志审计。四个多步题NU3/NU5/NU6/NR1的16条合计163.5h（24.3%），最终混合均分.431，0/16达到.9。这个跨臂共同困难比“某臂多跑一些即可”更值得优先解释。

HF1四臂共130.58h，占63条总耗时19.4%；最终≥.9是guided和record两臂，旧报告“only record”随HF1离线恢复已失效。其余standard修复.3425、brief .2937。一次贵的选择性任务，能同时暴露运行终结、后处理评分和科学选择这三类不同问题。

## 五、不可用的两个旧报告结论

1. **undelivered不等于没有机理图，更不等于自洽未通过。** 63行`undelivered=0`分别guided10/16、record0/16、standard0/16、brief1/15。旧report把这组证据清单存在性误读为verification成功率；同表连续selfconsistency==1实际是guided6/16、record3/16、standard2/16、brief5/15；join最终表后guided7/16，其余不变。不能复用报告的“guided9/15、record0/16、standard0/16、brief1/15科学验证通过”。完整科学验收bool在本地最终分表并未提供。参见当前仓库 `docs/benchmarks/p1b_offline_20261025/README.md:43` 对undelivered的明确解释。
2. **n_ts_jobs=0不意味着没找TS。** 9/63条n_ts_jobs为0，但9条都有TS输入；record/D3还记录3个ts_processes而n_ts_jobs=0。10条有IRC输入但n_irc_jobs=0。6条n_ts_jobs+n_irc_jobs大于n_qm_jobs，说明分类重叠或识别口径不同，不能直接加总。这些字段是文件/账本/流程的不同粒度；提取脚本及原库不在包中，无法确定全部细节。可靠的总量是n_qm_jobs（63条每行均等于done+failed+cancelled）和已记录job_hours。

这也意味着不能从这些计数推导“TS调用次数”“真正TS成功率”或用zero ts_hours证明无需精修。全175的rigid/flexible耗时对比所需`case_stats_all.csv`等表不在本地包，不能靠63条的4个rigid病例复现1.9倍总体结论。

## 六、P1b只能当先导上下文，不能和P2硬作进步幅度

只解开11KB补充ZIP到当前输出目录；未展开2.4GB主tar。ZIP的RESCORED/results.csv与桌面复评分补充/results.csv逐行一致。48行是四臂×E1/NB1/HA1/IA1四题×三轮，版本是PR#243；历史均值 guided.978983、record.729242、standard.534467、brief.906733。

P2是50题单轮，后续D1/D2/D4修复与部分人工补图加入，因此直接计算P1b→P2均分变化会同时混入题库、重复轮数、评分器和人工整理差异。P1b字段seconds是**离线评分耗时**，不是研究投入，不能和P2 job_hours比较。

当前仓库 `docs/benchmarks/p1b_offline_20261025/README.md:3-27`另记录Standard12条局部更新：HA1/r2 -1→.805，标准均值.5344667→.6848833，明确其余三臂仍是10/24快照、不是全48次统一重评；两条通道缺完整IRC，科学自洽未通过。不能把.684883和旧三臂历史均值拼成公平四臂榜，也不能当统一新实验。若要严谨跨批次比较，需在相同任务和同一整理/评分契约下统一重评原始证据；本次本地包不具备该证据。

## 输出清单

- `analysis.json`：聚合数值与来源计数。
- `score_track_audit.csv`：raw/fair/repair/IC3独立口径。
- `catalog_final_deltas.csv`：旧175中17条分值改变。
- `flex_joined_final.csv`：63行原投入+最终分数+源CSV行号。
- `effort_by_arm.csv`、`effort_paired_common15.csv`、`effort_pair_details_common15.csv`：共同任务配对。
- `effort_by_task.csv`、`effort_by_snapshot_failure_mode.csv`：投入去向。
- `p1b_historical_summary.csv`与`p1b_supplement/`：先导历史口径。
