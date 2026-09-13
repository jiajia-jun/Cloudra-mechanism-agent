# Cloudra 文档中心 (Documentation Hub)

欢迎查阅 Cloudra 文档。本文档中心汇总了系统架构设计、算法协议、标准作业程序（SOP）、基准评测、工程规格与学术调研资料。

> **快速导航**：
> - 仓库总览与快速上手：查看根目录 [`README_CN.md`](../README_CN.md) 或 [`README.md`](../README.md)
> - 开发者与 AI 助手工作地图：查看根目录 [`AGENTS.md`](../AGENTS.md)
> - 最新版本与演进记录：查看根目录 [`CHANGELOG.md`](../CHANGELOG.md)

---

## 一、核心文档全景速查

为保证科研探索与工程实现的严谨性，Cloudra 遵循**状态严格分离原则**：对“已实现并纳管”、“自动化测试覆盖”、“待批准实验门禁”与“设计稿”做显式区分。

| 文档 | 模块定位 | 核心主题 | 当前成熟度与状态 | 适用读者 |
| :--- | :--- | :--- | :--- | :--- |
| [`novelty.md`](novelty.md) | 学术与技术定位 | 对标 El Agente、机理智能体六大瓶颈、感知层与交付图创新 | **已落地**（项目立项与论文对齐依据） | 科研人员 / 架构师 |
| [`DAG_ORCHESTRATION.md`](DAG_ORCHESTRATION.md) | 编排规范 | 机理交付图（Delivery DAG）、虚频自检、三模式消融实验 | **已落地**（runtime_v2 核心编排） | 开发者 / 算法工程师 |
| [`DAG_SCHEMA_REFACTOR_PLAN.md`](DAG_SCHEMA_REFACTOR_PLAN.md) | 架构演进 | 声明式机理提案、无 ID 交互、督导-子 Agent 闭环通信 | **已落地**（V2 极简 Schema） | 核心开发者 |
| [`TS_PROCESS_SOP.md`](TS_PROCESS_SOP.md) | 实验流水线 | 过渡态搜索 13 阶段自主流水线规格（`prepare`/`resume`） | **设计稿**（未上线、未跑真实计算） | 计算化学 / 算法研究员 |
| [`TS_BACKEND_SELECTION_GATE.md`](TS_BACKEND_SELECTION_GATE.md) | 实验门禁 | TS 后端选型（ORCA NEB-TS / xTB / autodE）比较口径与前置状态 | **前置就绪**（待用户批准参数与预算后运行） | 决策者 / 计算化学家 |
| [`PHASE8_NODE_REGISTRY.md`](PHASE8_NODE_REGISTRY.md) | 部署与调度 | JSON 节点注册表、多工作区路由、Local/Slurm 计算提交 | **已落地**（契约测试已覆盖，实机集群待验） | 运维 / HPC 部署者 |
| [`PLUGINS.md`](PLUGINS.md) | 扩展生态 | 插件生命周期钩子（`setup`/`on_event`/`search`）与 chem-kb 接入 | **已落地**（扩展与知识库框架） | 插件与工具开发者 |
| [`KNOWLEDGE_TAGS.md`](KNOWLEDGE_TAGS.md) | 知识图谱工程 | 5 维受控词表体系（方法/软件/问题/报错/体系）与批量打标管线 | **已落地**（v13 标签化检索系统） | 数据工程师 / 知识库维护者 |
| [`benchmarks/dag-evidence-review-evaluation.md`](benchmarks/dag-evidence-review-evaluation.md) | 评测规范 | DAG 证据摄取与 Supervisor 科学复核控制评测检查点 | **离线检查点**（受控环境测试设计） | 评测工程师 |

---

## 二、架构设计与系统规范 (Architecture & Protocols)

Cloudra 专为有机反应机理的高壁垒计算场景设计，彻底摒弃了以自然语言散文宣布完成的不可信模式。

### 1. 创新点与技术定位
- **文档**：[`novelty.md`](novelty.md)
- **核心内容**：深入剖析以 El Agente（*Matter* 2025）为代表的量子化学通用工作流智能体与 Cloudra 的区别；阐释均相有机小分子机理计算面临的**六大系统性瓶颈**（空间感知盲区、TS 搜索极度敏感、科研工序纪律不足、长周期异步割裂、交付物语义漂移、评测维度错位）；详述 Cloudra 的两大解法：**物理与几何感知层**与**机理交付图契约（Delivery DAG）**。

### 2. DAG 引导编排系统
- **文档**：[`DAG_ORCHESTRATION.md`](DAG_ORCHESTRATION.md)
- **核心内容**：
  - **声明式提案（Declarative Proposals）**：Coordinator 仅需提交络合物物种名称与基元反应步，无需人工计算或指定 AST 步骤 ID。
  - **文件证据摄取与物理自检**：严苛校验过渡态虚频（TS 必须正好 1 个虚频，且虚频振动方向对应反应坐标；极小值物种必须 0 虚频）；证据文件落盘固定不可变 SHA-256 快照。
  - **定向审查上下文（Directed Review Context）**：Supervisor 独立进行科学复核（agree / disagree / skip / not_applicable / needs_evidence）。
  - **三档消融模式**：`standard`（无图对照）、`dag_record`（无督导记录组）、`dag_guided`（双智能体同行评议实验组）。

### 3. DAG Schema 瘦身重构方案
- **文档**：[`DAG_SCHEMA_REFACTOR_PLAN.md`](DAG_SCHEMA_REFACTOR_PLAN.md)
- **核心内容**：记录从繁重 AST 算子流向轻量声明式交付图迁移的完整架构设计；重点建立了**“谁提交证据，谁接收督导裁决”**的精准闭环唤醒通信机制，避免 Coordinator 成为二传手瓶颈。

### 4. 节点注册表与 HPC 集群路由
- **文档**：[`PHASE8_NODE_REGISTRY.md`](PHASE8_NODE_REGISTRY.md)
- **核心内容**：说明 JSON 格式的节点注册规范（[`deploy/node-registry.example.json`](../deploy/node-registry.example.json)）、基于路径深度的多工作区路由规则、计算作业状态机（持久化于 `compute.db`）以及 Local（Guard 进程）和 Slurm（`sbatch`/`scancel`）双执行后端的可靠性保证。

### 5. 插件开发与知识库扩展
- **文档**：[`PLUGINS.md`](PLUGINS.md)
- **核心内容**：阐明通用插件接口（`setup` 初始化、`on_event` 全量事件流监听、`search` 知识库接入）；给出 chem-kb 混合知识库的实战部署步骤、故障降级矩阵与上下文注入边界，确保核心数据与插件数据解耦。

### 6. 知识库标签体系与分面检索
- **文档**：[`KNOWLEDGE_TAGS.md`](KNOWLEDGE_TAGS.md)
- **核心内容**：chem-kb 8,594 张知识卡片的多维标签体系；5 个核心分面（`domain` 一级分类、`method` 理论方法、`software` 计算软件、`problem` 科学问题、`error` 报错签名）；批量 LLM 标注流水线（`cloudra knowledge tag build`）与原位行对齐写回保证。

---

## 三、标准作业程序（SOP）与实验门禁 (SOPs & Gates)

为防范大模型在量子化学计算中的发散与幻觉，系统建立了两项关键规范：

### 1. 过渡态搜索 SOP 规格（TS Process SOP）
- **文档**：[`TS_PROCESS_SOP.md`](TS_PROCESS_SOP.md)
- **状态**：**设计稿（未实现、未跑真实计算）**
- **设计原则**：杜绝过度工程，不替 Agent 作决定；不设诱导轮询的查询接口，状态统一经轻量事件注入上下文。
- **Agent 接口契约**：
  ```javascript
  ts.prepare({reactant, product, charge, multiplicity, method, budget, reaction_center?}) -> { run_id }
  ts.resume(run_id, adjusted) -> { ok }
  ```
- **13 阶段流水线**：从几何构建、反应映射、取向构象、初猜路径生成、鞍点优化到单虚频、双向 IRC 与端点产物验证。

### 2. TS 计算后端选型实验门禁
- **文档**：[`TS_BACKEND_SELECTION_GATE.md`](TS_BACKEND_SELECTION_GATE.md)
- **状态**：**前置条件就绪，待用户批准参数与预算后运行**
- **核心内容**：
  - 汇总已具备的测试护栏底座（分片建模、CREST 持久现场、失败分层、拓扑变更记录、Z-matrix 校验等）。
  - 本机引擎事实确认（CREST 2.12、xTB 6.7.1、ORCA 6.1.1、RDKit 2026.03.5；autodE 未安装）。
  - 明确列出 6 项待批参数（候选后端集合、测试体系清单、泛函与基组白名单、计算步数与机时预算、输入契约、多组分组装方案）。
  - 确立不随实验结论飘移的统一比较口径。

---

## 四、基准评测体系与文献调研 (Benchmarks & Surveys)

Cloudra 拥有独立的科学评测架构与深度的方法学文献调研底座：

### 1. 评测执行内核（`cloudra/benchmark/`）
代码模块位于 `cloudra/benchmark/`，实现了端到端科学能力度量：
- **题目生成器**：`gen_easy_tasks.py`、`gen_normal_tasks.py`、`gen_hard_tasks.py`、`gen_impossible_tasks.py`（改题源必须重跑生成器并通过确定性同步测试）。
- **复合评分体系**：
  $$\text{Composite Score} = (0.5 \cdot \text{Graph} + 0.2 \cdot \text{SelfConsistency} + 0.3 \cdot \text{Accuracy}) \times \text{BindingQuality}$$
- **三层证据链打分**：
  - `graph_similarity.py`：机理图拓扑覆盖打分（多出不罚）。
  - `accuracy.py` 与 `barrier_evidence.py`：能垒评分仅读取不可变交付物，绝不以文本兜底。
  - `refusal.py`：针对不可能/病态物理题目的结构化拒答精准分类。
- **独立运行与批处理**：`runner.py` 与 `batch.py`，支持 Web 批次运行。

### 2. 评测检查点规范
- **文档**：[`benchmarks/dag-evidence-review-evaluation.md`](benchmarks/dag-evidence-review-evaluation.md)
- **核心内容**：记录受控离线实验的复现元数据要求（代码 SHA、模型采样参数、方法白名单、资源上限、契约版本）以及 6 类故障注入覆盖清单。

### 3. 基准方法学与筛选调研报告（`docs/benchmark_survey/`）
收录了 6 篇详实的评测设计与实验分析文献报告：
- [`agent_benchmark_methodology_survey.md`](benchmark_survey/agent_benchmark_methodology_survey.md)：智能体评测方法学演进与关键启示。
- [`abstention-and-impossibility-benchmark-design-survey.md`](benchmark_survey/abstention-and-impossibility-benchmark-design-survey.md)：结构化拒答（Refusal）与不可能反应基准设计。
- [`llm-chem-agent-benchmark-design-survey.md`](benchmark_survey/llm-chem-agent-benchmark-design-survey.md)：化学大模型智能体评测体系调研。
- [`qm-reaction-benchmark-design-survey.md`](benchmark_survey/qm-reaction-benchmark-design-survey.md)：量子化学反应机理评测基准设计。
- [`xtb_screening_2026-09-09.md`](benchmark_survey/xtb_screening_2026-09-09.md)：基于 GFN2-xTB 的反应初筛实验与方法可行性记录。
- [`xtb_halved_benchmark_60_2026-09-09.md`](benchmark_survey/xtb_halved_benchmark_60_2026-09-09.md)：60 个经典有机反应在 xTB 半阶近似下的评测与能垒分布。

### 4. 候选反应题源与机器学习势能面基准（`ideapool/`）
- `ideapool/reaction_candidates/`：四档反应候选明细（`easy.md`、`normal.md`、`hard.md`、`impossible.md`）。
- `ideapool/mlp_benchmark/`：针对 AIMNet2、MACE-OFF、MACE-MP0、OMol25 等通用机器学习势能（MLIP）在过渡态搜索中的系统评测调研。

---

## 五、设计规格、执行计划与验证报告 (Superpowers)

目录 `docs/superpowers/` 存放经过同行审阅的技术架构设计（Specs）、工程实施方案（Plans）与实验验证数据（Reports）：

### 1. 架构设计规格（`docs/superpowers/specs/`）
- [`2026-08-15-web-runtime-architecture.md`](superpowers/specs/2026-08-15-web-runtime-architecture.md)：Web 运行时架构（控制面、EventHub 总线、SQLite WAL 状态隔离）。
- [`2026-08-15-web-runtime-api-contract.md`](superpowers/specs/2026-08-15-web-runtime-api-contract.md)：HTTP REST API 接口契约与 CommandBus 四拍时序。
- [`2026-08-15-web-runtime-domain-events.md`](superpowers/specs/2026-08-15-web-runtime-domain-events.md)：领域事件类型字典与不可变事件溯源规范。
- [`2026-09-05-event-driven-js-runtime-design.md`](superpowers/specs/2026-09-05-event-driven-js-runtime-design.md)：QuickJS-WASM 沙箱执行环境设计与安全边界。
- [`2026-09-04-dag-evidence-review-design.md`](superpowers/specs/2026-09-04-dag-evidence-review-design.md)：DAG 证据审查机制与通知投递设计。
- [`2026-09-03-tool-surface-native-corpus-design.md`](superpowers/specs/2026-09-03-tool-surface-native-corpus-design.md)：工具表面暴露与 Prompt 语料对齐规范。
- [`2026-08-13-agenthub-call-design.md`](superpowers/specs/2026-08-13-agenthub-call-design.md)：无政府主义 AgentHub 论坛与自由呼叫机制。
- [`2026-08-10-reaction-mapping-thermochemistry-design.md`](superpowers/specs/2026-08-10-reaction-mapping-thermochemistry-design.md)：反应原子映射与热力学校准设计。
- [`2026-08-10-ts-guess-strict-verification-design.md`](superpowers/specs/2026-08-10-ts-guess-strict-verification-design.md)：过渡态初猜的严格物理几何验证设计。

### 2. 演进实施计划（`docs/superpowers/plans/`）
记录了从 2026 年 8 月至今的关键系统里程碑执行计划（共 16 篇），包括事件驱动迁移、DAG 瘦身重构、工具沙箱等。

### 3. 基线与验证报告（`docs/superpowers/reports/`）
包含环境缓存连续性验证数据与基线报告（如 `2026-09-13-harness-cache-validation.md` 等）。

---

## 六、学术论文、文献调研与领域知识包 (Research & Domain)

### 1. 学术论文手稿（`paper/`）
- `paper/draft.md` 与 `paper/main.tex`：Cloudra 核心科研学术论文草稿与 LaTeX 排版源文件。
- `paper/literature_gap_analysis.md`：文献引用缺口分析，对齐本领域前沿研究。
- `paper/benchmark_construction.md` 与 `benchmark_construction_narrative.md`：机理基准题目的构建叙事与科学原则。
- `paper/supplementary_information.md`：补充材料（SI）规范。

### 2. 化学 AI Agent 综述文献调研
- **报告路径**：[`chemistry_ai_agents_literature_report.md`](../chemistry_ai_agents_literature_report.md)
- **核心内容**：2026 年 2 月调研收录的 17 个核心智能体框架（Coscientist, ChemCrow, ChemAgents, ChemAgent, ChemToolAgent, El Agente, k-agents, Virtual Lab, SciAgents, SciAgent, AtomAgents, Aviary, Biomni, DrugAgent, DrugPilot, MolAgent, MolAct）以及 2 个评测基准（ChemBench, MaCBench）的系统性横向对比。

### 3. 计算化学领域知识与技能参考（`cloudra/skills/`）
领域专长智能体在运行中动态加载的科学规范与计算模板：
- `cloudra/skills/dft-calculation/references/`：
  - `gaussian-inputs.md` / `orca-inputs.md`：Gaussian 与 ORCA 高保真输入模板。
  - `mechanism-elucidation-sop.md`：反应机理解析干实验标准操作流。
  - `reaction-class-geometry.md`：加成、消除、重排、偶联等各类反应的典型过渡态几何特征。
  - `method-selection.md`：量子化学泛函、基组与溶剂模型选择策略。
- `cloudra/skills/first-principles-calculation/references/`：
  - `surface-modeling-sop.md` / `heterogeneous-catalysis-mechanisms.md`：多相催化与表面建模指南。
  - `vasp-cp2k-production-blueprints.md`：VASP / CP2K 生产环境计算蓝图。

### 4. 仿真运行现场记录
- [`HARNESS_NOTES.md`](../HARNESS_NOTES.md)：特定仿真运行（如乙醛自身羟醛缩合反应）中的工具调用、调度行为与解析器异常现场实录。

---

## 七、文档维护约定 (Documentation Principles)

所有向本仓库提交文档的开发者与 AI 助手必须严格遵守以下约定（摘自根目录 [`AGENTS.md`](../AGENTS.md)）：

1. **真实性与状态分层**：
   - “已实现”、“自动化测试通过”、“真实环境验收通过”与“设计方案/SOP 规格”必须分开表述，严禁未经实测宣布完成。
2. **拒绝过度工程**：
   - 只记录被明确要求的事项，不记录未有调用者的臆想接口。
3. **消除文档死链接**：
   - 引用仓库内部文件时一律使用相对路径，严禁使用本地绝对路径。修改文件名或模块结构时，必须同步重构引用该路径的文档索引。
4. **中英双语同步**：
   - 根目录对外发布的 [`README.md`](../README.md) 与 [`README_CN.md`](../README_CN.md) 必须保持核心功能、命令与主导航同步更新。

