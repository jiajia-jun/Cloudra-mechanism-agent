# 化学能力边界：最终200行分析笔记

本笔记基于完整出版表 `evidence/source_publication_scores_per_run.csv`，共50题×4臂；任务图结构从档案记载的 campaign base `53309d0e` 只读提取，不使用后来修改过的当前Gold来重评旧运行。没有运行QM，没有运行评分器，没有改动数据、产品或科学标准。档案目录内没有原生 `.log` 文件；以下案例的能量、频率、IRC内容都是档案作者对运行沙箱的转述，未在本地重读原生日志。旧175行catalog只用作已存在运行的案例证据，未重新套用其全体分类和19/50结论。

## 1. 最大的能力边界是“把一连串步骤接完”，不是hard标签

|Gold最长连续反应链|任务数|运行数|离线整理后均分|Accuracy均值（分母）|
|---|---:|---:|---:|---:|
|1|30|120|0.85576|0.87316（120）|
|2|5|20|0.72984|0.71392（20）|
|3|4|16|0.48217|0.35613（16）|
|4|1|4|0.48325|0.36875（4）|

所有easy和hard的Gold最长连续链都是1；hard的“2条边”通常是并行竞争通道，不是连续完成2步。全部normal都要求2–4步。于是题库名字掩盖了真正增加的任务：连续确认中间体、找下一步、保持正确的能量分母和证据关联。3步组最明显；4步组只有NR1，不能宣称严格单调衰减，也不能把相同任务的4臂当成4个独立化学体系。

normal与hard均完整纳入40次运行，整理后均分分别为0.60611与0.83671。Graph均值为0.76133与0.90291，SC为0.69402与0.72479，Accuracy为0.53629与0.88165。按既定权重，Accuracy贡献占hard−normal组件差的89.9%，该项同时包含步骤覆盖、数值偏差与定性选择性。

hard中4题采用定性favored通道评分；另外6题、24次运行的整理后均分为0.85180，Accuracy均值0.92774（24个值全齐）。题族、方法与评分目标共同变化，分层差异不能单独解释为连续步骤数的因果作用。

## 2. Guided的主要增益在已有化学结论的证据闭合

最终normal+hard全部20题配对中，guided−record均差0.146845；加权Graph贡献+0.008338、SC贡献+0.091938、Accuracy贡献+0.046574，约占5.7%、62.6%、31.7%。Graph与SC合计68.3%。

normal全部10对中，Graph与SC合计占55.3%，Accuracy占44.7%；hard全部10对中，Accuracy贡献约0.000000304，SC贡献+0.086750。全50题中，guided−record的Accuracy贡献为正的+0.005099，而非旧的删减子集给出的负贡献。对同一backbone的主对照中，guided−standard的全50题加权Graph、SC、Accuracy贡献分别为+0.009513、+0.117875、+0.058916；hard10题的SC与Accuracy贡献分别为+0.135250和+0.127391，二者共同构成立体化学任务增益。

## 3. Impossible补齐之后暴露的是所有臂共同的适用域问题

最终40行中，accuracy=1仅4行：brief/IA1、brief/IA9、guided/IG8、standard/IG8；accuracy=0有33行，另有IB9的guided/brief各0.7、record 0.5。逐臂accuracy=1计数：brief 2/10、guided 1/10、standard 1/10、record 0/10。这里严格称“accuracy计分”，不能把其余36行统称错误拒绝：record/IA5是已有文档明确记载的正确拒绝漏计；standard/IA9无原始交付；IC3等又混入证据契约问题。

6题（IA5、IA7、IC3、ID2、IE2、IF3）四臂accuracy均0；IA1/IA9/IG8至少有一臂1，IB9最多0.7。14/40行同时selfc=1且accuracy=0。说明证据看起来齐全并不自动回答“在给定理论方法下这个问题能否被可信回答”。IMP仅允许xTB/PM7（任务白名单与benchmark README），不能把“Gold按该方法/任务契约标不可达”写成“真实反应在物理上不可能发生”。这也不支持旧175行报告把失败集中归因于没有督导的record/standard；guided/brief补齐后同样大面积落在此边界。

## 4. 多臂互补有价值，但共享缺口不会自动消失

normal逐题事后取4臂最高fair均值0.78744，相对guided 0.73702只增加0.05042；赢家guided5题、brief2题、standard2题、record1题。hard事后最高均值0.96240，相对guided 0.95765只增加0.00475。这个oracle使用四次运行及事后答案，绝不是已部署的选择策略。

normal中NR1最高accuracy仍约0.50、NU5最高约0.248、NI5约0.631、NU3约0.667；不同臂补足一些任务，但并没有解决连续网络的共同欠覆盖。NY3的guided整理后score为1，出版表的三分项均已从真实记录补齐；该题四臂的Accuracy最高为1。

## 5. 五个值得写进讨论的案例

### A. HB1：高分可以与数值排序自相矛盾并存

最终record/HB1 fair=0.9700、selfc=1、accuracy=1。旧证据笔记记录其favored标签是endo，却声明endo=10.98、exo=10.47 kcal/mol；按这两个数值exo反而低0.51。Gold为endo8.46、exo10.17（endo低1.71）。所以它拿到了定性通道标签分，不能据此声称预测了正确ΔΔE或能量排序。guided/brief也分别声明11.32/11.87与10.86/12.63，偏移会被定性rubric隐藏。

来源：`reports/evidence_notes.md:95–136`，尤其110–117；对应最终表record/HB1行。类似地guided/HF1最终fair=0.9742、accuracy=1与旧笔记声明syn18.21/anti14.72并不矛盾：favored标签仍选syn。原始0分是Supervisor退出竞争崩溃，不是科学失败；最终fair已救回。来源`reports/evidence_notes.md:227–239`、`docs/KNOWN_ISSUES.md:K4`。HF1旧笔记的具体数值仅保留为归档声明，未复核最终图是否有后续变化。

设计含义：选择性标签、数值排序、证据闭合需要各自报告；定性accuracy=1不能替代后两者的结论。

### B. HA8：误差可以来自分母，不是没有找到TS

guided/record档案值29.46，standard/brief20.43，Gold29.48 kcal/mol。记录明确指出后两臂用反应性cisoid构象而非最低all-s-trans极小值作参照，形成约9.05 kcal/mol差距。最终fair：guided0.9625、record0.9250、standard0.6250、brief0.7450。

来源：`reports/divergence_report.md:58–78`、`reports/catalog.csv`的HA8四行。只对该案例可以归为“能量参照选择”，不能把L2或NI1所有数值偏差一概解释成同一种分母问题；本地没有原生日志足以分离所有TS/构象/理论方法原因。

设计含义：真实IRC接到哪个局部构象，与题目要求用哪个稳定物种参照计算能垒，是两个不同事实。构象搜到了仍可在最终数值解释时用错分母。

### C. NU6：局部证据闭合并不等于覆盖参考机理

brief/NU6最终graph0.4、selfc1、accuracy0、fair0.34。档案记录它验证的是直接concerted asynchronous 2+2路径，Gold却要求经zwitterionic中间体的两步网络，因此两条Gold边均未匹配。guided找到了中间体及第一步（3.92 vs2.66），但寻找后续闭环多次回到concerted鞍点或极小值；档案明确把后一步保留为未找到鞍点、不声明能垒。standard交付两步但E2=18.84 vs15.72且selfc0.625。

来源：`reports/evidence_notes.md:665–706`，guided长channel原文在672行，brief见699–706。该数据足以说“缺少Gold的连续网络”和“存在经证据支持的替代路径”，不足以独立裁定真实势能面只有哪条路、替代路径错误，或宣布Gold错误。

设计含义：不能将selfc=1当作“全研究目标已完成”。研究图需要保留被验证的替代路和未解决的目标边；参考覆盖与本地路径证据是不同维度。

### D. NU5：先区分没找到目标鞍点和把别的鞍点关联到了目标边

旧分类把brief的Gold E3=Mumm重排（31.70）对成0.52 kcal/mol，称wrong saddle；但同一份证据笔记里的运行长文本明确说Mumm没有找到鞍点，INT3附近0.5点是methyl rotor，不能作酰基迁移证据。另有77.4 kcal/mol的质子迁移耦合加成路径和明确的IRC/端点记录。这是“目标步骤未完成，同时证据比较挑到了别的点”的混合现象，不能简化为模型把0.5宣称成Mumm能垒。

来源：`reports/evidence_notes.md:650–662`，尤其656的运行声明、659–661的评分转述；Gold E3定义取campaign-base任务JSON。最终brief/NU5整理后score=0.1983，Graph=0.662546、SC=0.440000、Accuracy=0.000000；分项来自完整出版表。guided该题selfc0.9583但accuracy0，同样提醒已做的证据很多与目标参考覆盖不足可以并存。

设计含义：低数值差错需要追到“哪一个计算结果被挂在哪条化学边上”，不能看到一个标量就判整场TS搜索失败。

### E. IA9与IA5：会算出鞍点不代表能回答方法适用域，正确拒绝也可能被通道匹配吞掉

standard/IA9原始与fair都缺图=-1；事后重建从自身档案可恢复PM7第一阶鞍点46.73、双向IRC、反应物端极小值，但产物端优化错误终止且无频率。档案忠实保留其“trustworthy PM7 saddle”正向声明，因此repaired0.2583、accuracy0，而没有根据Gold补写accessible=false。来源`reconstructions/standard/IA9/provenance.md:14–25,31–51,55–63`。

这提供了一个清楚的能力边界：即便数值任务出现正规鞍点和局部路径，仍需判断方法能否表达进入diradical区的目标问题；不能把程序正常终止和一个虚频当作方法适用性证明。该“diradical/PM7局限”的化学解释来自档案provenance第51行，不是本次原生日志独立验收。最终brief/IA9的accuracy1对照guided/record0，提示不同臂确实可作出不同的适用域判断，但缺少最终brief原图，不能臆造其拒绝过程。

与此同时，record/IA5档案已经正确拒绝disrotatory通道，单独保留conrotatory33.57；由于两条边相同端点，matcher选到了正向边，最终accuracy仍0。来源`reports/divergence_report.md:150–156,228`。这使“impossible accuracy=0率”只能作为计分事实，不能直接转成“错误拒绝率”。


## 可替换的两个短案例（便于主报告选用）

- **guided/NU3：已经验证的末步不等于整条三步路径。** 最终fair0.5527、selfc0.9167、accuracy0.33333。档案记录119 jobs、56个distinct几何、25个scan inputs，但仅Gold E3（23.77 vs23.76）匹配，前两步仍未匹配。来源`reports/evidence_notes.md:573–586`。这里可以说运行把大量工作投入在局部路径但没有闭合目标网络；不能把任务多说成算力无用，也不能把局部证据缺口归因于某个未复核的原生软件错误。**brief/NU3最终accuracy已变为0.66666，旧报告只E3的描述不能套到最终brief。**
- **guided/NQ5：搜得多不等于选中正确的鞍点/分母组合。** 最终fair0.7075、accuracy0.7；档案值39.23 vs30.96，约+8.27 kcal/mol；记录40个distinct几何、16个scan inputs。record用31.60，fair0.8725、accuracy约0.975；brief用32.83、78个distinct几何与22个scan inputs，fair0.781。来源`reports/evidence_notes.md:482–525`。这个对照支持“搜索量不自动保证最终选择”，不支持“多做计算导致变差”的因果结论。原生日志缺失时，也不能武断把+8.27分成TS身份错与稳定分母选错各多少。

## 数据口径限制

- 全部200次运行的Graph、SC与Accuracy均采用统一离线整理口径；图和文件引用从本次运行已有记录恢复，没有新算或改分。最终总分不变，全部50题进入配对分解。
- 旧证据报告的undelivered标志、misassign/WRONG-STEREO分类不是本次科学验收。HF1旧报告内部对brief的stereo结论存在争议，本笔记不据此重新判定。
- 单题单臂只有一次，任务族、链长度、元素/方法、rubric共变；不做独立因果归因或跨未知题库泛化。分数不是科学通过率。

## 复算产物

- `reproduce.py`：仅标准库，读取最终CSV与git archive 53309d0e task JSON；不写源目录。
- `metrics.json`：所有总体计数、均值、组件分解、oracle、口径标记。
- `task_structure_and_final_scores.csv`：50题结构与四臂最终组件，含原CSV行号。
- `impossible_final_runs.csv`：40行全部impossible成绩与原CSV行号。
- `sequential_depth_summary.csv`：按Gold最长连续链的可复算分组汇总。
