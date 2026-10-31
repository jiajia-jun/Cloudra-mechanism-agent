# P2 配对统计：完整200次运行、600个正式分项

主来源为 `evidence/source_publication_scores_per_run.csv`。所有总分与Graph、Self-consistency、Accuracy采用相同离线整理口径：整理每次运行已有的机理图、文件引用和原始产物，再按既定规则评分。总分不变，没有新增实验、科学结论或评分规则。全部50题进入每一组配对分解。

## 主对照：Guided与同一backbone的standard

最终均分分别为0.780322与0.594020，逐题均差+0.186302；normal为+0.163970，hard为+0.268900，hard10题10胜。全50题的加权Graph、SC、Accuracy贡献分别为+0.009513、+0.117875、+0.058916。准确度贡献为正，SC与目标答案准确度共同构成增益。

normal+hard全部20题均差+0.216435，对应Graph+0.008041、SC+0.124688、Accuracy+0.083712。hard全部10题的SC+0.135250、Accuracy+0.127391；normal全部10题的SC+0.114125、Accuracy+0.040033。应将立体化学收益写作候选判断与证据闭合共同改善，不能沿用旧7题组件子集只突出SC的推断。

## 消融：Record与Brief

Guided、Record、Backbone、Brief均分分别为0.780322、0.704430、0.594020、0.741506。Guided−Record均差+0.075892，在全部50题上分解为Graph+0.009121、SC+0.061675、Accuracy+0.005099。旧47题子集的负Accuracy贡献不再成立。

Guided−Record在normal+hard全部20题均差+0.146845：Graph+0.008338（5.7%）、SC+0.091938（62.6%）、Accuracy+0.046574（31.7%）。normal10题中Accuracy贡献+0.093148；hard10题中Accuracy几乎相同，SC贡献+0.086750。

Guided−Record的全题逐题bootstrap95%区间为[+0.012134,+0.143818]，27胜、8负、15平；Guided−Brief均差+0.038816，区间[−0.031704,+0.107648]。IMP中Brief均分0.48294略高于Guided0.44506，优势集中IA1、IA9，IG8则相反；Guided逐题赢5、Brief赢3、2题平。分数不是科学验收率，accuracy零不普遍等于错误拒绝。

## 其余发现与方法

原始运行的交付生命周期、63条深挖快照和其中共同15题的QM投入分析仍保留。这里的15是投入资料的共同任务集合，与正式组件完整性无关。最终总分不变，因此逐题胜负、50题总分bootstrap与事后互补上限保持不变。四臂逐题最高均分为0.851248；这是观察到的结果互补，不能直接当作在线选择策略。

100000次任务cluster bootstrap保留同题四组关系，seed=20261031。区间描述题库构成不确定性，不包含同题重复运行方差。原始raw/fair和历史流程标记另存供过程分析；不因此从正式完整分解排除任务。

复算顺序：`python analyze_paired.py`，`python derive_findings.py`，`python extract_baseline_comparison.py`。真实分项与总分在5.1e-5内一致；`component_exclusions.csv`无排除行，`component_pareto.csv`覆盖全部50题×4组。
