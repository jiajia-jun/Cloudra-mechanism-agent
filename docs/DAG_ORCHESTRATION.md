# DAG 引导编排系统设计（dag_record / dag_guided）

本文档介绍 Cloudra 的 DAG 引导编排子系统（`cloudra/dag/`）的当前架构与运行机制：机理传递图（Delivery DAG）、阶段证据契约（Stage Contracts）、调用复核收件箱（CallReview）、三种编排模式的消融边界、角色权限分工与证据绑定规则，以及 Supervisor 的事件驱动触发机制。

面向需要理解或开发机理编排模块的开发者；前端使用入口：在 Web 界面项目设置中选择编排模式（或在创建项目/会话时指定 `orchestration_mode`）。

## 解决的核心问题

有机反应机理研究是一项长链条、多步骤的严谨工作：包含文献调研、反应映射、构象搜索、过渡态（TS）初猜、结构优化、频率计算、内反应坐标（IRC）分析、反应物/产物端点确认以及热力学校正。

在传统的纯对话交互模式下，“具体完成了哪些计算、物理证据是否充分”只存在于大语言模型的上下文窗口中，随着对话轮次增加、上下文压缩或会话重启，这些关键状态极易丢失。

Cloudra 的 DAG 编排系统将化学机理研究的物理结论（已确立的化学事实与计算证据）固化到持久化存储中：

- **机理传递图（Delivery DAG）是唯一的持久化机理图**：节点代表化学物种（反应物、中间体、产物），边代表基元反应步骤；每个图元素都关联一份有序的**阶段契约（Stage Contract）**（明确该物种或基元步需要哪些计算证据支撑、按什么先后顺序绑定）。
- **调用复核收件箱（CallReview Inbox）**：基于 SQLite 的追加写入表（`dag_call_reviews`），记录每一个与交付相关的工具调用结果或量子化学计算作业终态，等待 Supervisor 统一复核。
- **摒弃任务排产图（No Process DAG）**：系统不记录“下一步做什么”的工作流排产图。机理草稿被接受后，由 Coordinator 自主规划推进节奏；没有中心化的排产队列，也没有复杂的工单分配权限。

图数据库是机理事实的权威来源。图节点仅保存类型化引用（如产物文件 artifact、计算作业 ID、工具执行结果、物种标识）与轻量注解，不嵌入大体积的分子几何坐标、计算日志或原始工具输出；单纯的文件系统路径不能直接作为有效证据。

## 三种编排模式与消融实验设计

`orchestration_mode` 是项目与会话级别的枚举配置；在 runtime_v2 中支持动态切换（前端下拉切换模式时会自动同步给项目内的所有 Agent）：

| 模式 | 运行机制与行为 |
| --- | --- |
| `standard`（标准模式，默认） | 不读写机理图，不启动 Supervisor；作为无图基准，普通交互无额外图维护开销 |
| `dag_record`（自主记录模式） | Coordinator 自主提交机理草稿（由系统环境自动接受），并通过 `dag_bind_evidence` 自行绑定各阶段证据；Supervisor 不参与运行 |
| `dag_guided`（督导复核模式） | Supervisor 负责评审与接受/驳回机理草稿（草稿接受前计算入口保持锁定），并利用 `dag_review_call` 逐条复核收件箱中的计算调用并裁定证据绑定 |

三档模式将“图结构本身的状态记录效果”与“Supervisor 督导复核的控制效果”严格解耦，为科研论文中的三方消融实验提供干净的对照基准。

Web UI 设置、CLI 启动参数（`--orchestration-mode`）与 API 接口调用具有完全等价的控制能力。机理图按项目会话持久化存储，在进程重启后自动恢复；标准模式不会修改已存在的机理图，后续切换到 DAG 模式可以无缝继续研究。

## 主循环流程与角色权限分工

```
Coordinator 提交草稿 dag_propose_mechanism（机理拓扑 + 各元素阶段契约 + 设计理由）
  → dag_guided 模式：由 Supervisor 评审接受（dag_accept_mechanism）；dag_record 模式：系统环境自动接受
  → 机理草稿落盘建图，所有阶段初始标记为 pending，量子化学计算入口解锁
  → Coordinator 与领域子 Agent 协同推进工作（子 Agent 专注于运行专业工具，不直接写图）
  → 交付相关的关键调用完成（日志解析、过渡态初猜、热力学分析或计算作业结束）
      → 自动进入 CallReview 待审收件箱 + 触发 Supervisor 唤醒（相同周期内的触发自动合并）
  → Supervisor 执行复核 dag_review_call：指定目标元素 + 阶段类型 + 裁决（agree / disagree / skip / ignore）
  → 系统内核执行确定性校验（校验绑定顺序、调用成功状态、证据必须为完工解析产物、通过物理检查器验证）
  → 交付与停止审计：每个必需阶段均达到 supported 状态，或附带有效理由被标记为 skipped
```

- **机理图设计归 Coordinator 负责**：初始机理假设与阶段契约由 Coordinator 提出（`dag_propose_mechanism`，草稿接受后仍可调用 `dag_add_species`、`dag_add_step`、`dag_update_delivery_element` 动态增删调整）。Supervisor 对图结构仅具备只读权限，不能直接修改图拓扑。
- **Supervisor 仅负责科学裁决**：评审接受或驳回草稿（`dag_accept_mechanism`）、逐项复核工具调用并裁定证据有效性（`dag_review_call`）、以及提升阶段覆盖率契约要求（`dag_set_coverage_contract`，契约要求只能收紧不能单方面放宽；阶段豁免必须由用户操作）。Supervisor 不直接调度任务，也不自行运行量子化学计算。
- **子 Agent 专注于专业计算工具执行**：子 Agent 不直接维护图结构，通过具体的 `tool_call_id` 汇报计算结果；可以在汇报时建议该结果支撑哪个物种或步骤，但这仅作为参考提示，实际绑定必须由 Supervisor 复核（guided 模式）或 Coordinator 自行确认（record 模式）。
- **确定性判定内核（Harness）**：统一负责不可变产物登记、证据引用的格式校验、以及阶段绑定的前置条件检查（例如验证 TS 频率计算中虚频数量必须为 1）。大模型的口头声明无法绕过内核检查提升证据等级。
- **机理修剪与删边**：调用 `dag_remove_edge` 移除基元步时**必须附带科学理由（rationale）**，删除记录会永久留存在变更日志中。Supervisor 发现需要修剪的路径时，通过 `dag_message_supervisor` 与 Coordinator 沟通，由 Coordinator 执行结构修改。

## 阶段契约与证据绑定规则

Coordinator 在机理草稿中为每个图元素声明有序的阶段契约；系统从不凭空推断未声明的阶段要求。

物种节点阶段：`geometry`（几何结构优化） / `frequency`（振动分析） / `single_point`（高精度单点能）；
基元步阶段：`ts_guess`（初猜构型，仅作参考，不能代替收敛过渡态） / `ts_opt`（过渡态优化） / `frequency`（虚频检验） / `short_irc`（IRC 快速连通测试） / `endpoint_a` / `endpoint_b`（反应物与产物端点确认） / `direction`（反应方向验证） / `identity`（产物身份核对） / `thermochemistry`（热力学校正）。

- **严格按序绑定**：绑定第 k 个阶段时，必须确保该元素此前声明的所有必需阶段均已处于 `supported`（已支持）或 `skipped`（已附理由跳过）状态，否则会被系统拒绝并报错 `stage_out_of_order`。
- **完工产物校验**：证据绑定只接受成功执行的解析产物（如计算日志解析器输出）；如果绑定目标是单纯的作业提交记录 `submit_compute_job`，会被直接拒绝（`bind_target_is_submit`）——提交作业本身绝不是完工证据。确定性检查器会严格校验物理指标（例如过渡态绑定必须满足唯一虚频 `n_imag==1`，否则触发 `saddle_check_failed` 拒绝绑定）。
- **被驳回阶段的状态处理**：Supervisor 选择 `disagree` 时会将阶段标记为 `rejected`（必须附带科学反驳理由），该阶段会作为未解决的缺口继续保持开放——只能通过后续重新计算并重新绑定（agree），或由人工附带理由显式跳过（skip）。附带有效理由的 `skipped` 是唯一的非成功处置方式。
- **证据等级派生**：元素级别的综合证据状态（如 `structure_supported` 结构已确立、`saddle_supported` 鞍点已验证、`endpoint_supported` 连通端点已确认、`thermo_annotated` 热力学已标注等）由底层阶段状态确定性派生，仅供展示及兼容查询使用。

## 调用复核收件箱（CallReview Inbox）

为了避免频繁打扰 Supervisor，系统设计了入箱过滤机制：只有在工具注册表中声明了 `dag_review=True` 的解析与分析工具（如 `gaussian_log_parser`、`reaction_mapping`、`thermo_analysis`、`ts_guess`）以及量子化学计算作业的成功/失败，才会向 `dag_call_reviews` 表插入待审记录；常规的文件读写、目录查询以及 `submit_compute_job` 提交调用均不会入箱，也不会触发 Supervisor。

每条待审记录携带上下文元数据（调用角色、工具名称、参数摘要、执行状态、计算作业 ID 等），供 Supervisor 评审时参考。收件箱采用追加写入设计，触发事件会自动进行合并（Coalescing），在 Supervisor 正在运行或排队时，新产生的待审记录会合并到下一次评审周期中统一处理。

## Supervisor 触发时机

Supervisor 不再采用低效的周期性轮询，而是完全由图事件与调用事件驱动唤醒：

- `mechanism_proposed`：Coordinator 提交了初始机理草稿（附带设计理由），触发 Supervisor 进行整体评审与接受/驳回；
- `tool_call_review`：收件箱中积累了待复核的计算结果，触发 Supervisor 逐条进行评审与阶段绑定；
- `delivery_updated`：Coordinator 在草稿接受后对机理图进行了结构调整，触发 Supervisor 审计变更合理性；
- `coordinator_message`：收到来自 Coordinator 的主动沟通消息（`dag_message_supervisor`）；
- `user_replan` / `pre_delivery`：任务结束前的交付审计——在放行结束前先评估阶段覆盖率报告。

Supervisor 的对话上下文在多次触发之间会完整保留。Agent 调用的各类图操作工具在经内核校验后生效；若被系统拒绝，系统会返回规范错误说明，Agent 可先通过 `dag_view` 查阅图状态后再做修订。

## 交付完成度与覆盖率审计

机理是否“研究清楚”，完全由阶段覆盖率契约进行客观评估，不依赖大模型的口头宣称：

- 任务标记为 `complete` 的充要条件是：图上所有必需阶段均已处于 `supported` 状态，或处于带有效理由的 `skipped` 状态；任何处于 `pending` 或 `rejected` 状态的阶段都会被视为未决缺口，并在交付报告中详细列出。
- 全局性契约要求（例如全路径必须完成热力学分析）会对所有声明了该阶段的图元素统一生效。
- 覆盖率契约随会话持久化存储；`dag_delivery_report` 工具可实时生成完整的交付报告（展示已达标门禁、未决缺口、不确定项以及用户豁免项）。
- 只有人类用户有权豁免特定门禁（Waive Gate）或降低契约要求；Supervisor 只能调用 `dag_set_coverage_contract` 提出更严谨的要求。
- **停止审计机制**：在 DAG 模式下，Agent 调用 `stop` 工具并声称任务完成时，系统会自动审计阶段覆盖率；如果存在未解决的缺口，系统会拦截停止操作并要求 Agent 继续推进、明确标记为部分交付（partial）或请求用户介入处理，禁止虚假汇报完成。

## 持久化存储与异常容错

图子系统在 SQLite 数据库中独立维护专用表结构：包括图元数据表、节点表、边表、覆盖率契约表、变更日志表、机理草稿表（`dag_drafts`）和复核收件箱表（`dag_call_reviews`）。

当前节点与边的数据是基于变更日志的物化视图，读取时无需重放全量历史日志。每次变更均记录版本号（revision）、会话 ID、操作主体、操作类型、原因阐述及时间戳，结合数据库事务保证原子性。对历史会话中的旧版数据保持向下兼容。

重启恢复时系统会直接读取物化视图，并校验其与变更日志的 revision 版本一致性；若物化视图损坏，可自动从日志重建。当图存储发生异常时，`dag_record` 和 `dag_guided` 模式会明确报错并拒绝执行（Fail-Closed 原则），绝不会静默降级为标准模式；而在 `standard` 模式下则完全不依赖图存储模块。

## 接口与工具体系

- **Agent 工具族**（取代旧版单一的 `dag_graph` 工具）：
  - `dag_view`：查询机理图当前状态（默认返回机理缺口、待审记录与近期变更的紧凑投影；支持按分页获取完整子图）；
  - `dag_delivery_report`：生成阶段覆盖率审计报告；
  - `dag_propose_mechanism`：Coordinator 提交初始机理草稿与阶段契约；
  - `dag_accept_mechanism`：Supervisor 评审并接受/驳回机理草稿；
  - `dag_review_call`：Supervisor 对具体计算调用进行裁决并绑定阶段；
  - `dag_bind_evidence`：Coordinator 在自主记录模式下自行绑定阶段证据；
  - `dag_add_species` / `dag_add_step` / `dag_update_delivery_element`：调整机理图节点与边；
  - `dag_remove_edge`：删除机理边（必须附带科学理由）；
  - `dag_set_coverage_contract`：Supervisor 收紧交付覆盖率要求；
  - `dag_message_supervisor`：向 Supervisor 发送沟通消息。
  字段说明与使用时机详见 `cloudra/skills/dag-operations/`。
- **HTTP API 与服务**：提供机理图查询、交付报告获取、变更历史追踪、待审收件箱管理等 RESTful 路由（定义于 `cloudra/services/api_v2.py`）。
- **前端可视化面板**：Web 界面中的 DAG 面板可直观展示机理网络拓扑（带各阶段颜色状态标注）、复核收件箱、历史变更事件流以及结构化编辑交互。
