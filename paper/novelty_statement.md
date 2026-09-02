# Cloudra Novelty Statement (rev. 2026-09-02)

> 目的：把 Cloudra 的 novelty 从"可信度/验证闭环"一维叙事，扩展为**五支柱全景叙事**
> （任务域 / 证据工程 / 工具套件 / 知识图谱 / 架构）。英文正文可直接进论文；中文注释便于快速审阅。
> 依据：`paper/main.tex`（摘要/§1/§2.4/§2.5/§5.2）+ `cloudra/runtime_v2/knowledge.py`、
> `cloudra/knowledge/{store,plugin}.py`、`cloudra/tools/Chemtool/` 实码核实。

---

## 0. 一句话电梯版（Elevator Pitch）

**Cloudra 是第一个把"均相有机反应机理阐明"做成可审计科学合同的自主多智能体系统**：
它用 **Delivery DAG** 把机理研究变成逐级证据绑定的交付契约（根除"自宣完成"），
用一套**计算化学原生的证据工具**（TS 路径一致性证明、IBO/Mayer 电子结构感知、
Z-matrix 结构异常感知、原子映射）让每一步判断都有仪器级物理证据而非模型断言，
并用 **GraphRAG 知识图谱**把领域方法学与排查经验编码成带证据等级、可证伪降权、可溯源的因果决策树。

> 一句话（中文）：别人做的是"会跑脚本的 agent"或"会看表面的 agent"，我们做的是
> "自带物理仪器的 agent"——每一步结论都来自可复现、可审计、可证伪的证据，而不是模型的自圆其说。

---

## 0.5 统领命题（Thesis，rev. 2026-09-03）

> 冷评审后，原"成本感知/性价比优化"这一**营销式 novelty 被否定**（未量化、无对照、易被误读为"降级版"）。
> 统领命题重构为——

**Cloudra 的核心主张：把 "结论正确" 与 "模型聪明" 解耦（decouple conclusion correctness from model smartness），实现模型无关性。**

- 竞品（ChemCrow=GPT-4、ChemAgents=GPT-4o、Virtual Lab=GPT-4、k-agents=GPT-4o、ChemReasoner=GPT-4o/4o-mini）的"通用 agent 取代一切"论断，**全部建立在选用前沿/最贵模型的前提上**——一旦模型降档，其端到端质量通常断崖式坍塌；
- Cloudra 用**可验证工具套件 + Delivery DAG 证据链**把领域判断物化为不可伪造的物理证据（TS 路径一致性、IBO/Mayer 电子结构、结构异常、证据绑定阶段合同），于是**结论的可信度不再依赖模型的推理聪明程度**——同一个机制网络，无论用前沿还是性价比模型驱动，只要走完同一套证据合同，都应给出可复现的结论；
- **成本优势是这一架构原则的自然结果/可测推论**，不是 headline：因为结论靠证据而非模型 smartness，系统可在**低成本模型中档模型**上维持严谨，从而降低端到端算力/API 成本；
- 五支柱（任务域 / 证据工程 DAG / 工具套件 / GraphRAG / 架构）是**实现模型无关性的五个机制**，而非五个并列卖点。

> ⚠️ 诚实边界：模型无关性是**架构原则 + 文献佐证**（竞品模型清单来自 `chemistry_ai_agents_literature_report.md`）。
> **端到端成本-质量曲线 ablation（≥2 模型档 × 各任务域的对照数据）尚未运行**——见 §3。

---

## 1. 五支柱展开

### 支柱一：任务域 —— 均相有机机理阐明（Homogeneous Organic Mechanism Elucidation）

- 现有计算化学 agent 对标（TSAgent/CatDT/AdsMind）几乎全部聚焦**异相催化表面**（NEB、吸附、表面能）；
- 自动化反应路径工具（autodE/AFIR/GRRM）是**非 agent 的确定性脚本**，不具假设生成与自主决策；
- ARplorer 做到了 LLM 引导路径探索，但止于最小能量路径，**不交付端到端机理网络**（无 IRC 端点连通性、无逐基元步自由能剖面、无验证闭环）。
- Cloudra 的任务域 = 从"反应物+产物规格"到"可验证的竞争机理网络 + 自由能剖面"的**端到端均相小分子机理解析**——一个无人系统化占领的细分域。

**§1 可强化点**：在引言画一张"任务域地图"：异相催化 agents（TSAgent/CatDT/AdsMind）| 反应路径工具（autodE/AFIR）| LLM 路径探索（ARplorer）| 均相机理阐明（**Cloudra，本工作**）。当前引言是线性列举，没有这张"空白区"图。

### 支柱二：证据工程 —— Delivery DAG（最 fancy 的那块）

- 机理研究被转化为**交付有向无环图**：每个基元步 = 有序阶段合同（TS guess → saddle 优化 → 频率验证 → 双向 IRC → 端点优化 → 拟谐振热化学），阶段推进**必须有可复现的计算证据**，不能靠模型自宣；
- **双重科学闸门**：确定性证据校验（第一闸门，不可伪造的解析产物绑定）+ 独立 Supervisor（第二闸门，科学合理性把关）；
- 反"completion by assertion"：证据等级由 harness 从阶段确定性派生，模型声明不能标记交付完成；
- 可审计性：不可变事件日志 + 证据绑定 + 变更留痕（删除必带 rationale），全程可重放。

### 支柱三：工具套件 = 计算化学工程创新（新增支柱，从"guard"升格为"instrument"）

> 论文 §2.4 目前把工具写成**防御性叙事**（coord_guard=防幻觉防火墙、电子结构感知=防 spin 污染）。
> 你的直觉对：这些工具本身是可复用的计算化学创新，应升格为**进攻性贡献**。

| 工具 | 新颖点（相对现有生态） |
|------|------------------------|
| `ts_guess verify(strict=True)` | **无状态路径方向一致性证明**：单虚频 + 双向 IRC 有效端点 + 两侧端点优化中间体 + 监视原子对距离序检查，给出 pass/fail——这是把"TS 验证"从人工经验变成可自动执行的判据，现有工具链（autodE/AFIR/ASE）没有等价物 |
| `electronic_analysis` | **IBO 局域化**（开源 NBO 替代）+ TS 处 Mayer 键级**部分/新生键检测** + Mulliken vs meta-Löwdin 自旋布居 + ⟨S²⟩ 自旋污染监控——把"反应进行到哪一步了"变成可读取的物理量 |
| `internal_coordinates` | Z-matrix 结构感知 + 键长异常分类（compressed/elongated/breaking_suspect/forming/atomic overlap）+ 杂化期望键角偏差——机理解读的"结构显微镜" |
| `reaction_mapping` | 从 SMILES 生成可检视的原子映射候选 + 反应中心键变化（[i,j] break/form）——机理假设的结构化输入 |
| `conformer_search(distance_filters)` | 反应距离预组织窗口过滤——保留**反应性构象**而非仅最稳定构象（preorganization 是机理工作的刚需） |
| `cdxml_to_graph` | ChemDraw 反应式 → 直接生成 `dag_propose_mechanism` 草稿（节点→SMILES、边→基元步、立体保真）——"纸面机理"到"可审计机理假设"的零手工转化 |
| `format_converter(log→csv)` | QM 日志 → 关键帧 CSV（优化轨迹/扫描曲线/IRC 路径）供程序化分析 |
| `thermo_analysis` | GoodVibes 拟谐振 + 聚合反应热化学（ΔE/ΔH/ΔG + 标准态控制） |

**叙事要点**：这些不是"包装好的脚本"，而是**把计算化学家的领域判断物化为可执行、可验证、可组合的原语**（primitive）。agent 的价值不在于"会用工具"，而在于这套工具本身编码了专家的物理直觉（路径一致性、电子结构感知、结构异常识别）。

### 支柱四：GraphRAG 知识图谱（新增支柱，从"troubleshooting 加速器"升格为"结构化化学记忆"）

> 论文 §2.5 已有专节，但叙事定位是"加速错误恢复、减少浪费算力"——**偏效率叙事**。
> 你的直觉对：它的价值远超"少跑几次任务"，是**知识表示**层面的贡献。

- **决策 DAG 而非扁平语料**：知识被编码为实体 + **带因果语义的边**（rel_type），检索时沿因果边 1–2 跳走**决策树**注入上下文——对比 ChemAgent 的自更新经验库（无因果注记的段落检索）；
- **证据分层 + 证伪降权**（实码核实）：实体/关系带 `evidence_level`（L0 文献 / L1 已验证计算 / L2 模型假设），检索排序 L1 > L0 > L2；**falsified 记录降权保留、绝不删除**（审计友好，失败经验也进记忆）；`source` 全程溯源；
- **三通道混合检索**（实码核实）：语义（bge-m3 向量微服务）+ 图谱（SQLite 知识图 + FTS）+ 模糊兜底，配额结构保证双通道全带；"卡→图缝合"把语义命中与图谱关系联注入（‖图: A—rel→B）；
- **双语**（v11）：中文 label 为唯一事实源 + label_en 挂同一实体，ASCII 查询命中英文通道；
- 数据规模：14,203 实体 / 10,266 关系（v12.1），来源含动力学讲义增量。

**叙事要点**：GraphRAG 让 agent 拥有**不随模型权重更新的领域记忆**——方法学判断（如 spin 污染怎么压、多虚频怎么消、溶剂簇怎么选）以可溯源、可证伪、可更新的结构存在，这是"可更新的科学记忆"，与"参数化记忆"（LLM 权重）和"情节记忆"（ChemAgent 式经验库）形成三足对照。

### 支柱五：架构 —— peer-collective + 事件溯源（无 commander 的科研集体）

- **AgentHub 水平 P2P**：8 个专职 agent 平等协作、无 commander，发现（低能构象、基组参数、spin 警告）以可寻址话题形式广播——避免中心化树形瓶颈；
- **Runtime v2 事件驱动 + 不可变事件日志**：状态迁移、工具调用、agent 对话全部落不可变事件流，跨中断可重放（reproducibility by construction）；
- 已有 §2.3 覆盖，作为"工程可靠性"支柱保留。

---

## 2. 与对标系统的对照表

| 维度 | TSAgent | CatDT | AdsMind | El Agente | ChemGraph | ARplorer | ChemAgent | ChemCrow / Coscientist | **Cloudra** |
|------|---------|-------|---------|-----------|-----------|----------|-----------|--------------------------|-------------|
| 任务域 | 异相催化 TS | 异相催化网络验证 | 表面吸附发现 | 通用 QM 脚本生成 | 热力学工作流 | LLM 路径探索 | 化学推理/记忆 | 通用实验/合成 | **均相有机机理阐明（端到端）** |
| 验证闭环 | NEB | 数字孪生 | 物理反馈 | 无（脚本执行） | 部分热力学 | 无（止于 MEP） | 无 | 实验台验证 | **逐基元步证据绑定 + Supervisor 双闸门** |
| 证据不可伪造 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **Delivery DAG + coord_guard + 终态解析产物绑定** |
| 化学工具原创性 | 常规 NEB | 常规 | 常规 | 脚本 | 常规 | 常规 | 记忆库 | 调用现成 API/库 | **ts_guess 严格验证 / IBO-Mayer 感知 / Z-matrix 感知 / cdxml→DAG** |
| 知识图谱 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 自更新记忆（段落级） | ✗ | **因果决策 DAG + L0/L1/L2 分层 + 证伪降权 + 溯源** |
| 知识可证伪 | — | — | — | — | — | — | ✗（旧经验不降权） | — | **falsified → 降权保留（审计友好）** |
| 架构 | 单体/层级 | 单体 | 单体 | 单体 | 单体 | 单体 | 单体/记忆 | 单体或轻层级 | **peer-collective + AgentHub P2P + 事件溯源** |
| 可重复执行 | ✗ | ✗ | 部分 | 部分 | ✗ | ✗ | ✗ | 部分 | **不可变事件日志重放** |

---

## 3. 诚实边界（不吹的 claims）

- **模型无关性 / 成本-质量曲线 ablation 未运行（用户决定）**：模型无关性是**架构原则 + 竞品模型文献佐证**，不是已实测的对照数据。
  **端到端成本-质量曲线（≥2 模型档 × 各任务域）的 ablation 我们组现阶段做不起复杂模型 → 不在本文跑，留在 novelty 里作为可测试论点**，等审稿人质询时再补（届时给出：系统质量随模型降档**平滑衰减** vs 竞品**断崖坍塌**）。
  当前正文与 novelty 均**不下“便宜”“性价比领先”这种未量化的结论**，只陈述“结论正确与模型聪明解耦”这一架构原则；成本优势作为推论带过。
- 不做"可训练策略"（Aviary/MolAct 是未来方向，§5.4 已声明）；
- 知识图谱**不自演化**（设计上无自动沉淀；"自扩展"是 §5.4 未来方向，与实码一致）；
- GraphRAG 检索排序（L1>L0>L2）与论文 §2.5 文字描述顺序（先列 L0）需注意措辞不造成"L0 优先"误解（实码 L1 优先）。

---

## 4. 已对齐 / 建议微调的正文措辞

**已对齐（无需改）**：摘要已有 GraphRAG 决策树、coord_guard、电子结构感知、100 反应四档基准、三案例闭环。

**建议微调**：
1. 摘要 GraphRAG 句："To accelerate troubleshooting and error recovery" → 可升格为
   "distills domain methodology and troubleshooting heuristics into **evidence-tiered, falsification-aware causal decision trees**"（把"效率"叙事扩成"知识表示"叙事）；
2. §2.4 标题/开头：从"Deterministic Gating"扩展一句"tools as scientific instruments"——
   "Beyond guarding against hallucination, Cloudra's chemistry-native tools (ts_guess strict path verification, IBO/Mayer electronic-structure perception, structure anomaly detection) convert agent judgment into instrument-grade, reproducible measurements.";
3. 引言（§1）任务域地图：在列举后加一句收束——"yet none of these systems targets end-to-end **homogeneous organic mechanism elucidation** with verified endpoint connectivity and free-energy profiles"（当前只有"either...or..."二分）。