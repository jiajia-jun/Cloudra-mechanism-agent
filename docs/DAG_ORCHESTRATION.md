# DAG 引导编排系统设计（dag_record / dag_guided）

本文档介绍 Cloudra 的 DAG 引导编排子系统（`cloudra/dag/`）的当前架构与运行机制：机理传递图（Delivery DAG）、声明式提案（Declarative Proposals）、文件证据摄取与虚频校验（File Evidence Ingest）、定向裁决上下文（Directed Review Context）、三种编排模式的消融边界，以及 Supervisor 的事件驱动触发机制。

面向需要理解或开发机理编排模块的开发者；前端使用入口：在 Web 界面项目设置中选择编排模式（或在创建项目/会话时指定 `orchestration_mode`）。

## 解决的核心问题

有机反应机理研究是一项长链条、多步骤的严谨工作：包含文献调研、反应映射、构象搜索、过渡态（TS）初猜、结构优化、频率计算、内反应坐标（IRC）分析、反应物/产物端点确认以及热力学校正。

在传统的纯对话交互模式下，“具体完成了哪些计算、物理证据是否充分”只存在于大语言模型的上下文窗口中，随着对话轮次增加、上下文压缩或会话重启，这些关键状态极易丢失。

Cloudra 的 DAG 编排系统将化学机理研究的物理结论（已确立的化学事实与计算证据）固化到持久化存储中：

- **机理传递图（Delivery DAG）是唯一的持久化机理图**：节点（`SpeciesNode`）代表研究体系的状态（单物种、络合物或分离物种集合）（而不是孤立催化剂，催化剂再生不等于体系回到原状态；保留 DAG 无环约束），边（`ElementaryStepEdge`）代表基元反应步骤；彻底去除 occurrence / role / 阶段契约数组的沉重负担，模型交互仅使用体系名称、步骤端点与自由文字。
- **文件证据摄取与物理自检**：完工的量子化学计算结果通过文件路径显式送审（`dag_submit_step_evidence` / `dag_submit_species_evidence`）。系统内核负责工作区沙箱路径检查、计算 SHA-256 哈希并将证据快照固定到 `.cloudra/evidence/`，同时复用既有能力严格校验过渡态虚频（TS 必须正好 1 个虚频，基态物种必须 0 个虚频）。
- **定向审查上下文（Directed Review Context）**：Supervisor 每次审查由 harness 捕获并冻结单一活动事项，Supervisor 仅需输出科学裁决 `verdict`（agree / disagree / skip / not_applicable / needs_evidence）与 `reason`，无需向模型暴露内部 ID、哈希指纹或修订版本号。
- **摒弃任务排产图（No Process DAG）**：系统不记录“下一步做什么”的工作流排产图。机理草稿被接受后，由 Coordinator 自主规划推进节奏；没有中心化的排产队列，也没有复杂的工单分配权限。

图数据库是机理事实的权威来源。图节点与边保存单一权威状态（`supported` / `needs_evidence` / `rejected` / `skipped` / `not_applicable`）与不可变证据快照的类型化引用。

## 三种编排模式与消融实验设计

`orchestration_mode` 是项目与会话级别的枚举配置；在 runtime_v2 中支持动态切换（前端下拉切换模式时会自动同步给项目内的所有 Agent）：

| 模式 | 运行机制与行为 |
| --- | --- |
| `standard`（标准模式，默认） | 不读写机理图，不启动 Supervisor；作为无图基准，普通交互无额外图维护开销 |
| `dag_record`（自主记录模式） | Coordinator 自主提交机理草稿（由系统环境自动接受），并通过文件送审工具自行登记确定性证据；Supervisor 不参与运行 |
| `dag_guided`（督导复核模式） | Supervisor 负责评审与接受/驳回机理草稿（草稿接受前计算入口保持锁定），并在定向审查上下文中逐项复核送审证据并裁定有效性 |

三档模式将“图结构本身的状态记录效果”与“Supervisor 督导复核的控制效果”严格解耦，为科研论文中的三方消融实验提供干净的对照基准。

## 主循环流程与角色权限分工

```
Coordinator 提交声明式机理提案 dag_propose_mechanism（species 体系列表 + steps 基元步列表 + 科学理由）
  → dag_guided 模式：由 Supervisor 评审接受（dag_accept_mechanism）；dag_record 模式：系统环境自动接受
  → 机理草稿落盘建图，所有元素初始标记为 pending，量子化学计算入口解锁
  → Coordinator 与领域子 Agent 协同推进工作（子 Agent 专注于运行专业工具，不直接写图）
  → Coordinator / 研究子 Agent 完成关键计算后，通过 dag_submit_step_evidence / dag_submit_species_evidence 送审
      → 系统内核固定文件快照到 .cloudra/evidence/，校验 TS 单虚频 / 基态零虚频，持久化待审事项
  → Supervisor 在单一活动审查上下文中调用 dag_review_step / dag_review_species：输出 verdict + reason
  → 裁决与更新同事务写入 durable 通知，回传给原提交者（failed/cancelled 保持 park-don't-wake）
  → 交付与停止审计：每个必需元素均达到 supported 状态，或附带有效理由被标记为 skipped / not_applicable
```

- **机理图设计归 Coordinator 负责**：初始机理假设由 Coordinator 提出（`dag_propose_mechanism`，草稿接受后仍可调用 `dag_add_species`、`dag_add_step`、`dag_remove_edge`、`dag_update_delivery_element` 动态增删调整）。Supervisor 对图结构仅具备只读权限，不能直接修改图拓扑。
- **Supervisor 仅负责科学裁决**：评审接受或驳回草稿（`dag_accept_mechanism`）、逐项复核活动送审证据（`dag_review_step` / `dag_review_species`）。Supervisor 不直接调度任务，也不自行运行量子化学计算。
- **子 Agent 专注于专业计算工具执行**：子 Agent 不直接维护图结构，运行专业计算后将输出日志汇报给 Coordinator，或经由送审工具提交复核。
- **确定性判定内核（Harness）**：统一负责工作区沙箱边界校验、文件快照与 SHA-256 固化、以及虚频物理自检（TS 必须 `n_imag == 1`，每个声明的基态物种必须 `n_imag == 0`）。大模型的口头声明无法绕过内核检查提升证据等级。
- **机理修剪与删边**：调用 `dag_remove_edge` 移除基元步时**必须附带科学理由（rationale）**，删除记录会永久留存在变更日志中。

## 声明式提案与单一元素状态

机理传递图直接使用声明式结构描述有机反应转化，摒弃复杂的多层 occurrence 实例与 role 分类负担：

- **物种（SpeciesNode）**：表示体系状态，使用体系名称（`name`）与 SMILES（`smiles`）。`"B.C"` 表示络合物，`["B", "C"]` 表示分离物种（显示为 B + C）；二者的极小值证据不能互相替代。名称在图内严格唯一。
- **基元转化步骤（ElementaryStepEdge）**：连接前驱与后继体系状态，使用步骤名称（`name`）、起点（`from`）与终点（`to`）。步骤名称在图内严格唯一。
- **单一权威状态**：
  - `pending`：待计算与送审；
  - `supported`：已获成功量子化学计算与物理自检支持，并获 Supervisor 认可或自主记录核验；
  - `rejected`：被 Supervisor 否决（必须附带理由），**作为未解决的开放缺口保持存在**，绝非处置手段；
  - `skipped`：可算但经科学评估主动放弃（必须附带理由，例如强多参考特征或映射已排除分支）；
  - `not_applicable`：该转化步骤对当前体系不适用（必须附带理由，例如无能垒反应无需 TS）；
  - `needs_evidence`：现有材料不足以定论，关闭待审事项等待提交新证据，不改变元素状态。

图上每个元素拥有单一权威状态，彻底废弃旧版多阶段数组与派生布尔位。

## 文件证据摄取与物理自检

证据送审直接以落盘计算日志文件为载体，由系统内核完成固化与合法性检验：

- **显式送审工具**：
  - `dag_submit_step_evidence`：针对基元步提交 `ts_file`；优化与频率分开时补 `opt_file`，IRC 使用 `irc_file` 或双方向文件；
  - `dag_submit_species_evidence`：针对物种体系提交 `opt_file` 及可选的独立 `freq_file`。
- **不可变固化**：内核校验文件路径严格受限于项目工作区沙箱，计算文件的 SHA-256 哈希值，并将文件快照复制到 `.cloudra/evidence/` 目录。原文件的后续修改或覆盖绝不影响已送审的证据快照。
- **严格物理自检**：
  - `ts_opt` 必须有原生优化收敛标记，频率日志必须描述同一几何；逐文件提交与直接阶段绑定使用相同的几何配对规则。
  - 频率计数只表示 `frequency_count_valid` / `frequency_data_present`，不能单独表示分子身份、反应方向或科学完成。TS 必须正好一个虚频（`n_imag == 1`）；
  - 基态极小点必须无虚频（`n_imag == 0`），真实几何还须匹配声明物种。氢的显式/隐式表示保持一致；组成或成键不匹配时返回实际感知结果。
  - 只有完工并成功解析的产物才被接受；作业提交记录 `submit_compute_job` 绝对不是完成证据。

分离产物先声明为列表（如 `smiles=["B", "C"]`），再用 `dag_submit_species_evidence(species_name="P", opt_file=["B.out", "C.out"])` 一次提交所有组分的正常终止、零虚频且结构匹配的日志；优化与频率分开时，`freq_file` 列表须与 `opt_file` 逐项对应。随后提交步骤的 TS 与真实双向 IRC，`target_minimum_file` 保持可选并可省略，系统复用目标物种已绑定的组分证据。这样可证明分离产物通道，不会验证 `"B.C"` 络合物极小值，也不会把组分能量合并成络合物能量；该步源物种与 TS 的能垒证据仍单独绑定。

## 定向审查上下文与裁决机制

在 `dag_guided` 督导复核模式下，Supervisor 的裁决流程得到大幅精简与加固：

- **单活动审查事项（Active Review Context）**：每个 Supervisor 会话当前只绑定一个明确的活动审查项。Harness 在工具调用发起时冻结上下文快照（包含提交记录、提交者身份、目标元素与依据版本指纹 `basis_fingerprint`），防止乱序或过期裁决。
- **极简模型接口**：
  - `dag_review_step` / `dag_review_species`：Supervisor 模型仅需输入 `verdict`（`agree` / `disagree` / `skip` / `not_applicable` / `needs_evidence`）与 `reason`，无需传内部 ID、版本号或阶段类型。
  - `dag_accept_mechanism`：机理草稿评审仅需输入 `verdict`（`accept` / `reject`）与 `reason`。
- **闭环通知与 Park-Don't-Wake**：
  - 裁决与状态落盘在同一事务内写入一条 durable 裁决通知（`flush_review_notifications`）；
  - 通知精确投递至最初提交送审的 Agent 信箱；若收件人已处于 `failed` 或 `cancelled` 状态，通知驻留信箱而不唤醒（Park-Don't-Wake 机制）。

## 交付完成度与运行结束门禁

交付是否完成完全由客观覆盖率评估决定，大模型的口头宣称无法绕过系统门禁：

- **单一完成度判据（evaluate_delivery）**：
  - 图中所有必需的 species 和 steps 均处于 `supported` 状态，或处于带有科学理由的 `skipped` / `not_applicable` 状态；
  - 任何处于 `pending` 或 `rejected` 状态的元素均视为未决缺口；
  - 缺少 TS 文件或虚频自检不通过的步骤绝不能被判定为完成。
- **统一运行结束门禁（_evaluate_completion_gate）**：
  - 无论是模型调用 `stop` 工具显式结束，还是无工具调用的纯文本回复隐式收尾，系统均在收敛边界调用完成度门禁；
  - 存在未决缺口时拦截退出，要求 Agent 继续推进或请求用户介入处理，禁止虚假汇报完成。

### 最终文件与审批绑定

DAG 模式下，项目工作区存在 `mechanism_graph.json` 时，退出审计会将它对应到权威 DAG；Benchmark 必须先提交该文件。物种使用 DAG ID 或名称，步骤通过明确名称或唯一端点对应，映射记录在最终 receipt 中。同一文件不得重复表示同一 DAG 元素，节点与边 ID 也不得冲突。

文件须覆盖声明的交付目标。需要 TS 的步骤不能通过删掉 `via` 移除要求。`properties.energy_hartree` 与 `properties.evidence_log` 必须指向本次绑定的不可变证据，日志内容、分子几何和原生能量均须对应；能垒从明确的起点和 TS 日志能量核对。这里复用既有声明能量的舍入允许量，不改变 Gold 准确度容差。

部分交付审批绑定文件 SHA。改动、增加或删除交付文件均需重新审查。`stop` 只返回 `request_received`；候选答复在统一门禁放行和最终登记成功后才发布。最终登记在事务内检查图、契约、证据和审查状态仍与审计一致，并保存文件的不可变快照；变化时要求重新审计。

带跳过、豁免或空检查契约的范围完成显示为 `scope_completed`，不显示科学验证通过。Supervisor 批准的部分交付仍显示为 partial。运行结束、范围完成、科学检查和 Benchmark 评分分别记录。

## 持久化存储与无兼容层原则

- 图子系统在 SQLite 数据库中独立维护专用表结构：`dag_graphs`、`dag_nodes`、`dag_edges`、`dag_changelog`、`dag_drafts`、`dag_call_reviews`、`dag_evidence_bindings` 与 `dag_review_requests`。
- **无兼容层设计**：彻底移除旧版 wire schema、阶段兼容映射、多层 occurrence 兼容属性与废弃工具别名；不以“标记废弃”收尾。同时**严格不擦除或删除用户既有数据库**。

## 接口与工具体系

- **声明式提议与图编辑**：
  - `dag_propose_mechanism`：提交声明式机理草稿（`species`, `steps`, `rationale`）；
  - `dag_add_species`：向机理图添加物种体系（`name`, `smiles`）；
  - `dag_add_step`：向机理图添加基元反应步（`name`, `from`, `to`）；
  - `dag_remove_edge`：删除基元反应步（必须提供非空 `rationale`）；
  - `dag_update_delivery_element`：更新物种或步骤的处置与注解；
- **文件证据送审**：
  - `dag_submit_step_evidence`：送审基元步骤的 TS / IRC 计算日志；
  - `dag_submit_species_evidence`：送审物种体系的优化与频率日志；
- **督导复核（Supervisor 独占）**：
  - `dag_accept_mechanism`：评审接受或驳回机理草稿；
  - `dag_review_step`：对活动待审步骤进行定向裁决；
  - `dag_review_species`：对活动待审物种进行定向裁决；
  - `dag_review_evidence`：裁决队列中的结构化复核请求；
- **检查与审计**：
  - `dag_view`：查阅机理拓扑、当前待审事项及未决缺口；
  - `dag_delivery_report`：输出完整的交付覆盖率审计报告；
  - `dag_view_evidence`：查阅送审证据的不可变快照与解析数据；
  - `dag_message_supervisor`：向 Supervisor 发送沟通与申诉请求。

