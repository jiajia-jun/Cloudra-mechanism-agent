# 可直接采用的结果

源：`/Users/cloudrayyy/Desktop/Cloudra实验数据/Cloudra-P2-final-20261031`。算术已复核；未连远端、未重跑评分/QM、未改源数据。完整来源边界见`NOTES.md`，计算脚本见`analyze_provenance_effort.py`。

1. **200是最终样本，397不是第二个实验样本。** 最终表=3条P2b+197条P2c；raw397=原P2b200+P2c197，排除的197条全为`cancelled by batch stop`。两个200行主表完全相同；175行catalog已有17条分数过时。
2. **官方.705是fair+人工repair。** CSV fair=.6646885；7个standard修复把它抬至.7050695。增量.040381中.035（86.7%）只是移除7个-1，已有证据的正分贡献仅.005381；7个修复分平均.153743，修复交付没有补出完整正确机理。
3. **brief/IC3的人工.4修复已混进fair。** 按已记录“只在repair手修”决定将其从fair拿出，brief fair .741506→.713506、全体fair .6646885→.6576885；排名不变，brief对record优势从.037076缩至.009076。此为协议敏感性，非重新评分原sandbox。
4. **共同15题（60行）的投入与收益见下表。** 来自63条旧投入快照，join最终分数；standard采用repair；brief尚缺HH1所以公平配对排除该题。累计job-h不等于CPU核时/费用/墙钟。

| 臂 | 每题job-h | 最终均分 | ≥.9 |
|---|---:|---:|---:|
| guided | 11.079 | .812413 | 8/15 |
| record | 7.877 | .735953 | 6/15 |
| standard | 7.555 | .649480 | 5/15 |
| brief-errors | 15.590 | .727333 | 6/15 |

brief耗时为record **1.979倍**但均分低.00862；guided比brief **少28.9%耗时且高.08508分**，7/15题同时更快更高分；guided对record是多40.6%耗时换+.07646分，不能笼统说多算毫无收益。此为选择性深挖队列，不泛化全200或推因果。

5. **共同困难比单臂效率更扎实。** NU3/NU5/NU6/NR1四题四臂16行占163.5 job-h（全部63行673.82h的24.3%），最终混合均分.431，0/16≥.9。
6. **旧报告有不能复用的指标。** selfconsistency连续分==1的最终计数guided7/16、record3/16、standard2/16、brief5/15；报告写guided9/15对其余0/0/1，是把清单存在性`undelivered`误作验证结论。9条n_ts_jobs=0却全有TS输入，record/D3甚至ts_processes=3；分类粒度不一致，不能以0宣称没做TS。
7. **保留评分回填说明。** 最终表166条snapshot、28条rescue、6条timeout借raw；六条分项为空，其中brief NU5=.1983，因此展示表“all are high”不实；不能声称200条都独立完成了fix后评分。
8. **P1b只作先导上下文。** 只展开11KB补充包，未展开2.4GB主包。48条=四臂×四题(E1/NB1/HA1/IA1)×三轮，评分器PR#243；P2为50题单轮及后续评分/repair。Standard后续.684883是仅12条的局部整理，其他臂仍旧快照，不能拼成新四臂统一结果；`seconds`为离线评分时间，不能比P2 job-hours。

主用表：`effort_paired_common15.csv`、`effort_by_arm.csv`、`score_track_audit.csv`、`flex_joined_final.csv`。来源逐条说明和过时报告冲突见`NOTES.md`。
