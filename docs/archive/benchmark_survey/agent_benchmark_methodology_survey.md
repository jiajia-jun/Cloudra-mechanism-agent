# Agent/LLM 基准设计方法学调研笔记（方向 D）

> 调研人：researcher sub-agent（文献调研）
> 目的：为 Cloudra 四级验证测试集（Easy/Normal/Hard/Impossible，机理发现 agent）设计提供高水平基准论文的设计模式依据。
> 覆盖：GAIA、SWE-bench、HELM、BetterBench、数据污染（Leak, Cheat, Repeat）、LLM-as-a-Judge 综述 + 可靠性实证、AbstentionBench（拒答评测）、Can We Trust AI Benchmarks（元综述）。

---

## 1. GAIA: A Benchmark for General AI Assistants

- 出处：Mialon et al., 2023/2024，TMLR 2024（Featured Certification, ICLR 2024 spotlight），arXiv:2311.12983，https://arxiv.org/abs/2311.12983
- 规模与结构：466 道人工设计题，三级难度（Level 1/2/3）；166 题公开（dev，带答案与标注），300 题保留答案用于 leaderboard（test）。
- **难度分级的操作化定义**（Sec 3.3）：按"标注者解题所需步数 × 使用工具数"分级。Level 1：≤1 个工具、≤5 步；Level 2：约 5–10 步、需组合多种工具；Level 3：任意长动作序列、任意工具数、需访问开放世界。作者明确定义是"loose"代理（proxy），不是硬约束，并在 Sec 4 用模型/人类成功率随级别单调下降来**事后验证难度定义的有效性**（GPT-4+plugins 在 L1 不到 30%、L3 为 0%；人类 92%）。
- **Ground truth 构建与验证**（Sec 3.4）：每题由创建者给出答案 + 元数据（用了哪些工具、几步、耗时），再由**两名独立标注者各自重新作答**；三方答案一致才保留。68% 的题一次通过，其余修正或删除。单题含验证约 2 小时人工。
- **评分**：factoid 短答案（数字/几个词/列表），quasi-exact match（按答案类型做归一化），系统提示规定输出格式（"FINAL ANSWER: ..."）。强调**避免 LLM-as-judge**：因为评测 SOTA 模型时 judge 必须更强，且 judge 有位置偏置等系统性偏差。
- **防污染设计**：答案"by design 不以明文存在于互联网/训练语料中"；需要多步执行才能得到答案（类似 proof-of-work），可检查 reasoning trace 防蒙对；对比选择题基准（MMLU）污染更难判定。
- **统计**：能 API 调用的模型跑 3 次取平均；人类基线 92% 作为 ceiling；web-search 基线验证"答案不能直接搜到"。

## 2. SWE-bench

- 出处：Jimenez et al., ICLR 2024（oral），arXiv:2310.06770，https://arxiv.org/abs/2310.06770
- 任务来源与 ground truth：2,294 个真实 GitHub issue + 对应 merged PR（12 个 Python 仓库）。三阶段构建管线（Sec 2.1）：
  1. 抓取 ~90,000 PR；
  2. 属性过滤：PR 必须 resolve 一个 issue 且**贡献了测试文件**；
  3. **执行过滤**：打 patch 前后跑测试，必须至少有一个 fail-to-pass 测试翻转，且无安装/运行错误。
  → 关键模式：**ground truth 不是"参考答案"，而是可执行的验证器（测试）**，客观、无 judge 噪声。
- 评分指标：% resolved（patch 能 apply 且全部相关测试通过）；另有 % Apply 作为中间指标。报告 fail-to-pass 测试数（平均 9.1）+ 回归测试（中位 51 个 pass-to-pass）。
- 难度分析（Sec 5）：按仓库分解 resolved 率；难度与 context 长度相关；oracle-retrieval 消融分离"检索 vs 推理"贡献。**没有形式化难度分级**，难度靠事后分析刻画。
- 防污染：强调"continually updatable"——可用训练截止之后新建的 issue 持续扩充；训练集（SWE-bench-train, 19k 实例）与评测集**仓库不相交（disjoint repos）**。
- 生态衍生（审稿人必问）：SWE-bench Lite（300 题人工筛选自包含子集）；SWE-bench Verified（OpenAI 2024，500 题人工标注筛掉"描述不清/测试不合理"的题）——说明**原基准约相当比例题目存在标注质量问题**，人工筛选子集成为事实标准。
- 统计弱点：原文只报点估计，无置信区间；小样本（Lite 300）下 ±几个百分点即显著。

## 3. HELM (Holistic Evaluation of Language Models)

- 出处：Liang et al., 2022/2023，TMLR 2023 / Trans. NY Acad. Sci.，arXiv:2211.09110，https://arxiv.org/abs/2211.09110
- 设计哲学：**先分类再选代表**——对 scenario（任务×领域×语言）与 metric（accuracy/calibration/robustness/fairness/bias/toxicity/efficiency 7 项）做显式 taxonomy，再从覆盖性与可行性出发选 16 个核心场景；多指标并列而非单一总分，暴露 trade-off。
- 标准化：30 个模型全部在**同一标准化条件**（同一 prompt、adaptation 参数）下评测；公开所有原始 prompt 与 completion 保证透明与可复算。
- 统计严谨性（§8.5 及脚注）：人类评测的模型比较全部用 **paired bootstrap（10,000 次重采样），p<0.05 判显著**；作者明确指出局限——只用 3 个随机种子选 in-context 样例、每个数据集只评 1000 条，部分结论可能统计上不显著，并把这点写进 limitation（诚实披露样本量/种子数对显著性的影响，是审稿人欣赏的做法）。
- 聚合方式：head-to-head win rate 聚合，同时强调单一口径分数的局限。
- "Living benchmark"：持续更新场景/指标/模型，显式版本化。

## 4. BetterBench: Assessing AI Benchmarks（基准质量评估框架）

- 出处：Reuel et al., NeurIPS 2024 Datasets & Benchmarks，arXiv:2411.12990，https://arxiv.org/abs/2411.12990
- 46 条最佳实践准则，按基准生命周期五阶段（design/implementation/documentation/maintenance/retirement）组织；评估 24 个常用基准。**对 Cloudra 最相关的硬要求**：
  - Design：被测能力必须显式定义并说明如何映射到任务；报告 human performance level 与 random performance level；metric 的 floor/ceiling；自动评测需经过验证（validated automatic evaluation）。
  - Implementation：评测代码与数据可得；**报告统计显著性或不确定性量化**；包含"模型是否在基准数据上训练过"的检测任务；防污染/防刷分措施（唯一标识、加密、withheld split）。
  - 实测发现：被评基准在"提供复现脚本"上平均仅 3.75/15、"报告统计显著性"仅 5.62/15——即**大多数基准不达标，做到即是加分项**。
  - "Detecting small improvements"：基准应设计成能可靠检测 1% 改进 → 直接约束样本量选择。
- 元综述佐证：*Can We Trust AI Benchmarks?*（AIES 2025，arXiv:2502.06559，https://arxiv.org/abs/2502.06559）汇总约 110 项研究：数据污染、文档不足、signal vs noise 不分、construct validity、刷榜激励等问题是系统性被诟病点。

## 5. 数据污染：Leak, Cheat, Repeat

- 出处：Balloccu et al., EACL 2024，arXiv:2402.03927，https://arxiv.org/abs/2402.03927
- 系统综述 255 篇评测 GPT-3.5/GPT-4 的论文：~42% 的论文通过网页界面把数据喂给 OpenAI，约 4.7M 条样本、263 个基准可能被用于后续训练（"indirect data leaking"）。
- 对评测者的建议清单（Sec 6）：用不泄露数据的访问方式（API 而非网页）；公开 prompt、模型版本、运行时间、采样细节、随机种子；采样要公平（所有方法用相同样本）；不要直接抄前人 SOTA 数字而要重跑；谨慎解读闭源模型性能（污染无法排除）。
- 启示：Cloudra 测试集的反应来自公开文献——必须论证"LLM 背出文献答案 ≠ 能完成计算管线"，即用**可验证的计算产物（TS 能量、IRC 连通性）而非文本答案**做 ground truth，并保留一部分未公开/新构造的反应作为 held-out。

## 6. LLM-as-a-Judge 可靠性

- 综述：Gu et al., *A Survey on LLM-as-a-Judge*，arXiv:2411.15594，https://arxiv.org/abs/2411.15594。核心问题"如何构建可靠的 LLM-as-a-Judge 系统"：一致性提升、偏置缓解（位置偏置、冗长偏置、自我偏好）、可靠性评估方法学与专门基准。
- 实证：Yagubyan, *The Coin Flip Judge?*，arXiv:2606.13685，https://arxiv.org/abs/2606.13685：相同输入重复 50 次评测，pairwise 偏好平均 13.6% 翻转；跨 judge 一致率仅 76%（κ=0.51）；语义等价的 prompt 模板改变 25% 案例的多数判决；要 11–15 次重复多数投票才能以 95% 概率恢复 50 次参考判决；存在显著第一位置偏置（72% A-majority, p=0.024）。→ **单次 LLM judge 判决噪声太大，高风险评测必须多次重复 + 位置随机化 + 报告不确定性**。
- 与 GAIA 的立场一致：能用确定性评分（exact match、可执行测试、数值容差判定）就不要用 LLM judge；不得不用时须做人机一致性验证。

## 7. AbstentionBench（拒答/越界处理——直接对应 Impossible 级）

- 出处：Kirichenko et al., Meta FAIR, 2025，arXiv:2506.09038，https://arxiv.org/abs/2506.09038
- 35k+ 不可回答题，20 个数据集，归纳出 **6 类应拒答场景**：Answer Unknown / False Premise / Stale / Subjective / Underspecified Context / Underspecified Intent。Cloudra 的 Impossible 级（多参考态超出 xTB 能力）属于"Answer Unknown（能力外）"场景，可借鉴其**场景化分类与显式定义**：拒答 = 不给出确定答案（表达不确定、说明缺失信息、或部分作答）。
- 指标：**abstention recall**（该拒时拒的比例）为主，配合 precision（防过度拒答）与 F1；同时测非拒答题的 correctness，形成"答题能力 × 拒答能力"两轴。→ Cloudra 应同时报告：Easy/Normal/Hard 成功率（防"全拒答刷高拒答率"）与 Impossible 级拒答 recall/precision。
- Judge 验证模式：LLM judge（Llama 3.1 8B）做拒答判定，**在人工标注子集上验证 judge 准确率 88%** 并报告——用 judge 必须先验证。
- 警示性发现：推理微调使拒答率平均下降 24%——"更努力的系统更容易硬答"，对 Cloudra 的 Impossible 级设计是重要预期（系统可能伪造 TS/能量结果而非拒答）。

---

## 8. 可借鉴设计模式汇总（→ Cloudra 四级测试集）

1. **难度分级操作化**：学 GAIA，用可观测代理变量定义级别（反应步数/中间体数/电子态复杂度/是否多参考），并用"基线系统与人类专家成功率随级别单调下降"做事后验证；明确定义是 loose proxy。
2. **Ground truth = 可执行验证器**：学 SWE-bench，以确定性判据（优化收敛、恰好一个虚频、IRC 两端连通到声明物种、能量/ΔG 在容差内匹配文献值）代替文本比对；每个任务至少一个 fail-to-pass 型判据 + 回归判据。
3. **标注质量控制**：学 GAIA 双独立标注者一致才保留 + SWE-bench Verified 人工筛选；报告标注一致率与剔除比例。
4. **统计严谨性**：学 HELM——paired bootstrap CI、报告种子数与样本量的局限；每级样本量按"能检测的目标效应"论证（BetterBench 的 1% 检测原则）；多次运行取平均并报告方差（GAIA 3 次）。
5. **评分指标分层**：每级成功率 + 全流程端到端成功率 + 中间产物正确率（conformer/TS/IRC/热化学分阶段得分，类似 SWE-bench % Apply 中间指标）；报 ceiling（专家/已知文献解）与 floor（随机/单 LLM 无工具基线）。
6. **拒答处理**：学 AbstentionBench——Impossible 级单独报 abstention recall/precision/F1，防过度拒答；拒答判定若用 LLM judge，先在人工标注子集上验证并报告准确率；预期并检测"伪造计算结果"式失败（比单纯不拒答更糟）。
7. **污染防控**：文献反应做近重复检测（n-gram/结构相似度 vs 常见训练语料中的教材反应）；核心论证是"计算产物无法靠背答案伪造"；保留未公开 held-out 子集；公开题目但 withhold 答案（GAIA 166/300 模式）。
8. **透明与复现**：公开全部 prompt、评分脚本、原始轨迹（HELM 模式）；版本化测试集；报告模型版本与运行日期（Leak Cheat Repeat 清单）。
9. **消融设计**：DAG 三模式消融与有图/无图消融应对每级分别报告效应量 + bootstrap CI（不要只报总分 delta）；学 SWE-bench oracle 消融分离"检索/知识 vs 编排"贡献。
10. **防 leaderboard 诟病**：避免单一总分排行；多指标并列（HELM）；明确声明测试集的目的与边界（construct validity）；提供复现脚本（BetterBench 最低质保清单）。
