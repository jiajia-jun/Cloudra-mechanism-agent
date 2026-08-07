# Agent4Chem 综述文献调研报告（Researcher 交付版）

> 检索日期：2026-02；检索源：OpenAlex / arXiv API / Nature / 网络综合
> 溯源声明：以下每条目的 DOI、作者、期刊均经 OpenAlex 单篇接口或 arXiv API 或出版方页面核验；"溯源度"标注了结论提取自 Abstract 还是正文 Method/SI。本报告为框架收录级调研，未逐篇深入 SI 复现计算参数。

---

## 一、总览表（17 篇核心候选 + 2 篇评测基准）

| # | 框架 | 领域/任务 | 关键特征 | 出处 |
|---|------|-----------|----------|------|
| 1 | Coscientist | 自主合成实验（湿实验闭环） | GPT-4 规划 + 云实验室 API 执行，4 要素认知架构 | Boiko et al., Nature 624:570-578 (2023) |
| 2 | ChemCrow | 合成规划/试剂采购/性质预测 | 18 种化学工具增强，LLM+工具协同 | Bran et al., Nat. Mach. Intell. 6:525-535 (2024) |
| 3 | ChemAgents | 自主化学研究（端侧+机器人） | Llama-3.1-70B 层级多智能体，不需要闭源 API | Song et al., JACS 147(15):12534-12545 (2025) |
| 4 | ChemAgent | 化学推理（记忆机制） | 动态自更新"库"，三种记忆，任务分解编译 | Tang et al., ICLR 2025, arXiv:2501.06590 |
| 5 | ChemToolAgent | 化学问题求解（工具效应评测） | ChemCrow 增强版；**结论反直觉：工具不总优于 base LLM** | Yu et al., NAACL 2025 Findings, arXiv:2411.07228 |
| 6 | El Agente | 量子化学/计算化学任务编排 | 认知架构驱动，QM/DFT 类工作流自动设计 | Zou et al., Matter (2025), DOI:10.1016/j.matt.2025.102263 |
| 7 | k-agents | 量子计算实验室自动化 | 自驱动实验室，agent 控制量子硬件实验 | Cao et al., Patterns (2025), arXiv:2412.07978 |
| 8 | Virtual Lab | 跨学科科研协作 | PI agent + 科学家 agent 团队、会议机制、湿实验验证 | Swanson et al., Nature 646:716-723 (2025) |
| 9 | SciAgents | 科学发现/文献图推理 | 本体知识图谱 + 多 agent 辩论式推理 | Kraus et al., Adv. Mater. (2024), arXiv:2409.05556 |
| 10 | SciAgent | 科学推理（工具增强训练） | MathFunc 语料（30k 样本/6k 工具）+ SFT | Ma et al., EMNLP 2024, arXiv:2402.11451 |
| 11 | AtomAgents | 材料/合金设计 | 物理感知多模态多 agent，知识+模拟+分析 | Ghafarollahi & Buehler, PNAS (2025), arXiv:2407.10022 |
| 12 | Aviary | 科学 agent 训练框架 | 语言决策过程 (LDP) POMDP 形式化 + 在线 RL | Narayanan et al., ICLR 2025, arXiv:2412.21154 |
| 13 | Biomni | 生物医药实验动作挖掘 | 从 17 万篇论文挖掘工具动作序列，训练 agent | Li et al., bioRxiv (2025), DOI:10.1101/2025.05.30.656746 |
| 14 | DrugAgent | 药物发现编程自动化 | 多 agent 协作自动完成 ADMET 性质预测代码 | Liu et al., arXiv:2411.15692 (2024) |
| 15 | DrugPilot | 药物发现推理 | 参数化推理，结构与性质双链反思 | Li et al., arXiv:2505.13940 (2025) |
| 16 | MolAgent | 分子性质估计建模 | agent 自动搭建专家级分类/回归模型流水线 | Gómez-Tamayo et al., JCIM (2025), DOI:10.1021/acs.jcim.5c01938 |
| 17 | MolAct | 分子编辑/性质优化 | **首个 agentic RL 分子设计框架**，两阶段训练 | Yang et al., arXiv:2512.20135 (2025) |
| 18 | ChemBench | LLM 化学能力评测 | 7200 问答 + 220 个专家设计任务；模型接近人类平均水平但未达专家级 | Mirza et al., Nat. Chem. (2025), DOI:10.1038/s41557-025-01815-x |
| 19 | MaCBench | 多模态 LLM 化学评测 | 数据提取/实验执行/结果解读三方面暴露 VLLM 局限 | Alampara et al., Nat. Comput. Sci. (2025), arXiv:2411.16955 |

---

## 二、研究动机与创新点（按叙事线拆解）

**这条线的起点是"LLM 会不会做化学"→"LLM 能不能自己动手做化学"。** 2023 年底 Coscientist 在 Nature 上发表时，核心卖点是第一次让 GPT-4 通过规划-工具调用闭环完成文献检索、反应条件设计、云端机器人执行的完整湿实验（Pd 催化交叉偶联、点击化学等），评审和媒体关注点都在"闭源 LLM 控制实验室"这件事本身。它带出了 agent4chem 领域后来的两个关键词：**多步骤规划**与**工具-实验闭环**。

ChemCrow 紧接着把"工具增强"做成可复用的通用模式，18 种 RDKit/数据库/采购工具挂在 LLM 外面，ReAct 式循环解决问题，并在合成规划、试剂获取、分子性质预测上做了系统评测——这篇的贡献不在某个单点性能，而在"把化学工具插进 LLM 推理循环"的标准范式，后续几乎所有 agent4chem 框架都继承了它的骨架。

2024 年之后分化出几条支线。**层级化/多智能体协作**是声势最大的一条：ChemAgents（JACS 2025）用 Llama-3.1-70B 做端侧部署，四个层级 agent（用户意图理解、通用化学推理、实验方案、机器人执行）覆盖从自然语言指令到机器人实操的完整链路，刻意不用闭源 API，代表"开源模型也能干"的立场；Virtual Lab（Nature 2025）则是另一极——PI agent 主持科学家 agent 团队开"研究会议"，人类只给高层反馈，团队自主拼出 ESM+AlphaFold-Multimer+Rosetta 的 nanobody 设计流水线并过湿实验，92 个设计中 2 个对 JN.1/KP.3 变体结合改善。这两篇的共同叙事是"组织结构即能力"：不是单 agent 变强，而是 agent 之间的角色分工与沟通协议决定了上限。

**记忆与自学习**是另一条和用户课题最相关的线。ChemAgent（ICLR 2025）把化学任务拆成子任务并编译成结构化"库"，查询时检索+精炼，设计了三种记忆类型，在 SciBench 四个化学数据集上把 GPT-4 拉高了最多 46%——它证明"经验积累"比"prompt 技巧"更能稳定提升化学推理。而 ChemToolAgent 给出的却是反向证据：工具 + agent 包装并不总优于裸 LLM，在某些任务上 ChemCrow 系 agent 反而更差。这两篇放一起，恰好构成综述里"什么模块真正有效"的张力点。

**量子化学与计算化学 agent** 支线里，El Agente（Matter 2025，Aspuru-Guzik 团队）把认知架构（意图理解→任务分解→执行→验证）套到量子化学任务上，自动编排 QM 计算工作流；k-agents（Patterns 2025，同一团队+牛津 Leek 组）把 agent 接进量子计算实验平台做自动化。AtomAgents（PNAS 2025）则是材料侧的"物理感知多模态"版本，agent 分工做知识检索、多模态数据整合、物理模拟与结果分析，用于合金设计。这三篇代表 agent4chem 在"计算密集型"任务上的形态。

**训练范式的升级**出现在 Aviary（ICLR 2025）和 MolAct（2025 底）：Aviary 把语言 agent 形式化为"语言决策过程"（POMDP），提供 DNA 克隆、文献问答、蛋白稳定性等科学环境做在线 RL 训练，结论是开源小模型 + 训练 + 推理时扩展可以在多个任务上追平甚至超过 frontier LLM，成本低 100 倍；MolAct 首次把分子编辑/优化形式化为 agentic RL，两阶段训练（先学编辑能力、再学性质优化），7B 模型就能在分子编辑上打赢 DeepSeek-R1 这类"思考型"闭源模型。这两篇预示领域从"prompt 工程 agent"走向"可训练 agent"。

**药物设计**支线相对独立：DrugAgent（arXiv 2411.15692）让多 agent 协作自动写 ADMET 预测代码，把"agent 编程"当核心能力；DrugPilot（arXiv 2505.13940）用参数化推理 + 双链反思（结构链/性质链）做药物发现；MolAgent（JCIM 2025，Johnson & Johnson 团队）解决 agent 化 CADD 的瓶颈——性质模型自动化搭建，系统无关地复现专家级分类/回归流水线。注意 DrugAgent 在 arXiv 上有**两篇同名不同物**（另一篇 2408.13378 做药物-靶点证据整合），综述引用时必须区分。

**评测支线**给综述提供"基准层"素材：ChemBench（Nat Chem 2025）用 7200 个问答 + 220 个专家设计任务对比 LLM 与人类化学家，核心结论是前沿模型接近人类平均水平但尚未达到专家级；MaCBench（Nat Comput Sci 2025）专门打击多模态 VLLM，指出它们在看图读谱这类化学真实场景里局限明显。这两篇是"agent 能力天花板"叙事的实证底座。

---

## 三、核心方法论（Methodology）

**Coscientist**：四要素认知架构（Planner / Web search / Code execution / Automation），GPT-4 驱动，工具通过 API 挂接（Web of Science、PubChem 等），实验经云端实验室（Emerald Cloud Lab）执行。溯源：Abstract + 正文架构描述，未读 SI。

**ChemCrow**：ReAct 循环 + 18 种工具（RDKit 描述符、PubChem、采购网站、Wikipedia 检索等），LLM 决定调用哪个工具并消化返回值，评测覆盖合成、采购、性质预测三类任务。溯源：Abstract。

**ChemAgents**：Llama-3.1-70B 本地部署，四层 agent 层级（意图理解层 → 通用化学推理层 → 实验方案层 → 机器人执行层），每层有专门 prompt 与结构化输出协议，最终驱动自动化实验平台。这是目前少见的"全开源、不依赖闭源 API"端侧方案。溯源：Abstract + OpenAlex 元数据，正文 Method 未逐页深读。

**ChemAgent（ICLR 2025）**：把化学任务分解为子任务并编译进结构化库；面对新问题时检索库中相关知识（称为 memory）并精炼，支持任务分解与方案生成；设计三种记忆类型 + 库增强推理组件，让 LLM 通过经验随时间变好。SciBench 四个数据集上 GPT-4 提升最高 46%。溯源：arXiv Abstract 全文。

**ChemToolAgent**：在 ChemCrow 基础上增强，系统评测专用化学任务 + 通用化学问答；核心发现是 agent 化后并非处处优于 base LLM——这是少见的"负结果"，对综述的方法论讨论价值很高。溯源：arXiv Abstract。

**El Agente**：认知架构驱动，面向量子化学任务（DFT/QM 类）自动设计并执行计算工作流，含失败重试与结果验证环节。注意论文正式标题是 "El Agente: An autonomous agent for quantum chemistry"，"El Agente Q" 是其中的 Q 版架构名。溯源：OpenAlex 元数据 + 摘要。

**k-agents**：agent 接进量子计算自驱动实验室（牛津），控制量子硬件实验流程；arXiv 名 "Agents for self-driving laboratories applied to quantum computing"，Patterns 正式版标题改为 "Automating quantum computing laboratory experiments with an agent-based AI framework"。溯源：arXiv 元数据 + OpenAlex DOI 核验。

**Virtual Lab**：LLM PI agent 主持一组科学家 agent 开会（agenda 驱动），人类研究员给高层反馈；并行会议机制（高温采样制造多样性）+ 合并 agent 提炼最优答案；应用到 nanobody 设计时自主组合 ESM、AlphaFold-Multimer、Rosetta 成流水线，设计 92 个 nanobody，ELISA 湿实验验证，2 个对 JN.1/KP.3 结合改善。溯源：Nature 页面 Abstract + Extended Data 图注（会议机制、并行会议、评分细节），部分 Method 细节来自正文可公开部分。

**SciAgents**：三大件——大规模本体知识图谱（连接科学概念）、LLM + 数据检索工具、多 agent 系统（含 in-situ learning）。用在材料/生物交叉主题上做图推理式科学发现。溯源：arXiv Abstract；Adv Mater 正文 Method 未深读（Wiley 反爬）。

**SciAgent**：提出 tool-augmented scientific reasoning 任务设置；构建 MathFunc 语料（30k+ 样本、约 6k 工具）训练模型"检索-理解-使用工具"；发布 SciToolBench 基准（5 个科学领域）。7B 模型超同尺寸 13%+ 绝对精度。溯源：arXiv Abstract。

**AtomAgents**：物理感知生成式 AI 平台，多 agent 分工做知识检索、多模态数据整合、物理模拟、跨模态结果分析（数值+图像），自动设计合金。溯源：arXiv Abstract。

**Aviary**：把 agent 形式化为语言决策过程（LDP，即语言基础的 POMDP）；实现 5 个 gym 环境（3 个科学：DNA 克隆、文献问答、蛋白稳定性工程）；开源模型在线训练 + 推理时扩展，以低 100 倍成本匹配/超越 frontier LLM 与人类专家。溯源：arXiv Abstract。

**DrugAgent / DrugPilot / MolAgent / MolAct**：DrugAgent 用多 agent 协作写 ADMET 预测代码并自动执行；DrugPilot 做参数化推理 + 结构/性质双链反思；MolAgent 系统无关地自动搭建性质估计流水线（分类+回归）；MolAct 两阶段 agentic RL（先编辑后优化），工具反馈（有效性检查、性质评估、相似性控制）驱动多轮编辑。溯源：arXiv Abstract（DrugAgent/DrugPilot/MolAct）+ OpenAlex 摘要（MolAgent）。

**ChemBench / MaCBench**：ChemBench 7200 个问答（27 个化学子领域）+ 220 个专家设计任务，人类基线来自 22 位化学家；MaCBench 测 VLLM 在数据提取、实验执行、结果解读三类的表现。溯源：Abstract 级；正式版论文 Method 未深读。

---

## 四、课题关联度（对 agent4chem 综述的具体价值）

**1. 分类骨架可以直接采用"时间线 × 能力模块"双轴。** 时间线上 2023→2026 从"工具增强"（ChemCrow）演进到"可训练 agent"（Aviary、MolAct），从"闭源 GPT-4"（Coscientist）演进到"开源端侧"（ChemAgents）再到"人机混合协作"（Virtual Lab）。能力模块上，记忆（ChemAgent）、规划（Coscientist/El Agente）、工具（ChemCrow/ChemToolAgent）、多 agent 协作（ChemAgents/Virtual Lab/SciAgents）、训练（SciAgent/Aviary/MolAct）五块可以独立成节。

**2. 记忆机制是综述里最值得深挖的"软肋"话题。** ChemAgent 是唯一把"动态自更新记忆库"做成核心卖点的化学 agent，且给出了量化提升（最高 46%）；把它和 ChemToolAgent 的负结果对照，能支撑"记忆/经验模块比堆工具更关键"的论点——这也可以自然带出你们自研系统的差异化定位。

**3. 必须避开的坑。**
- ChemToolAgent：工具不一定有益——综述若只强调"工具增强必然有效"会被审稿人抓住；
- DrugAgent 同名两篇（2411.15692 vs 2408.13378），引用前必须用 arXiv ID 区分；
- El Agente 的论文正式名不是 "El Agente Q"，k-agents 的 arXiv 名与 Patterns 正式名不同，User 指定的名字与真实出处有偏差，需在综述中统一用正式标题；
- SciAgents（Adv Mater）与 SciAgent（EMNLP）拼写极易混淆，一个"多 agent 图推理科学发现"、一个"工具增强科学推理训练"，建议在综述里并列时加注。

**4. 评测叙事要引用 ChemBench + MaCBench 双证据。** ChemBench 说"接近人类平均、未达专家级"，MaCBench 说"多模态能力在真实化学任务里受限"——这两个结论共同支撑"agent4chem 仍处早期、评测缺口大"的判断，也是你们综述"未来方向"部分的实证出口。

**5. 覆盖盲区提示。** 现有框架大多覆盖合成规划/性质预测/实验自动化/药物设计，但**文献级知识推理**（SciAgents 部分涉及）、**计算化学具体工具链的纵深编排**（El Agente 刚起步）、**从工具到湿实验的自动闭环在开源模型上的表现**（只有 ChemAgents）仍是明显空白，可写进综述的"开放问题"。

---

## 五、用户指定但未检索到的框架（重要）

对 User 名单中的 **AgentSynthe、ChemLogic、MoleculeAgent、LabAgent** 四个名字做了 OpenAlex title.search、arXiv API 全文检索、网络综合搜索，均**未找到对应的化学 agent 框架论文**：

- AgentSynthe：仅有 AgentSynth（arXiv:2506.14205，通用 computer-use agent 任务生成，与化学无关）；
- ChemLogic：仅有 PyPI 同名包（neurosymbolic GNN）及 arXiv:2507.13987（描述逻辑，非 LLM agent）；
- MoleculeAgent：无精确命中，最接近的是已收录的 MolAgent/MolAct；
- LabAgent：无精确命中，arXiv 上命中结果均为无关领域（如 Ask WhAI 信念形成研究）。

推测这些名字来自公众号/二手转述或用户记忆偏差（可能与 El Agente、ChemAgent 等发音/拼写混淆）。**建议 Coordinator 与 User 核实原始出处，或在综述中直接使用已核实名单，删除这四个条目。**

---

## 六、引用来源与溯源度汇总

- 逐条 DOI / 作者 / 期刊：经 OpenAlex works 单篇接口核验（bashtools curl，2026-02）；
- arXiv ID 与摘要：经 arXiv API 与 arxiv.org/abs 页面抓取核验；
- Virtual Lab / Nature 页面：出版方页面 Abstract + Extended Data 图注核验；
- 未逐篇深入 Method/SI：本次为框架收录级调研，计算参数、prompt 细节、训练超参等如需在综述正文引用，建议后续对 ChemAgent、El Agente、MolAct 三篇做 PDF 级深读（这几篇方法细节最值得写进综述 Method 对比表）。
