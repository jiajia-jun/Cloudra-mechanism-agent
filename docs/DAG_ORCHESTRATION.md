# DAG 引导编排（dag_record / dag_guided）

本文说明 Cloudra 的 DAG 引导编排子系统（`cloudra/dag/`）的当前实现：双图模型、
三种编排模式、分权规则、证据回流契约与 Supervisor 触发时机。面向需要理解或修改
这条链路的开发者；用户使用入口见 [`CLI_API_REFERENCE.md`](CLI_API_REFERENCE.md)
和 TUI 的 `/mode` 命令。

## 解决什么问题

机理研究是长链多步工作：文献调研、映射、构象搜索、TS 初猜、优化、频率、IRC、
端点确认、热化学。纯对话驱动时，"做过什么、证据够不够、下一步做什么"只存在于
模型上下文里，随压缩和重开丢失。DAG 编排把这两件事落到持久存储：

- **process DAG**：计划与已完成的工作（下一步该做什么）；
- **delivery DAG（机理图）**：被研究的化学机理本身（已经确立了什么）。

图存储是权威。节点只存类型化引用（artifact / compute_job / tool_result / species）
和小注解，不嵌几何、日志或工具输出正文；单独的 filesystem 路径不算证据。

## 三种模式与消融边界

`orchestration_mode` 是会话级枚举，创建时选定、执行开始后不可变：

| 模式 | 行为 |
| --- | --- |
| `standard`（默认） | 不读不写任何图，不运行 Supervisor，普通工作零图成本 |
| `dag_record` | 确定性 harness 记录双图，Supervisor 不能影响 agent 也不能改图 |
| `dag_guided` | 记录双图，且 Supervisor 可提交受限的图变更并调度 frontier |

三档把"图簿记本身的效果"和"Supervisor 控制的效果"分开，支撑三方消融实验。
UI（TUI `/mode off|record|guided`）、CLI（`--orchestration-mode`）、API
（session 创建的 `orchestration_mode` 字段）三入口等价。图按会话持久化，
跨过 session 与进程重启存活；standard 会话不碰已有图，之后的 DAG 会话可以继续它。

## 两张图的分工与分权

- **delivery DAG 归 Coordinator 设计**：节点是中间体 occurrence（催化循环里
  `Cat@entry` / `Cat@return` 是指向同一 species_ref 的不同节点，保持图无环），
  边是基元步 occurrence。Supervisor 对它完全只读，引擎直接拒绝其 mutate。
- **process DAG 归 Supervisor 维护**：添加/拆分工作、调优先级、增删依赖边、
  阻塞/重开/跳过、supersede 过时工作（保留审计链）。
- **harness（确定性适配器）**：工具/计算完成时登记不可变产物、发出证据引用、
  推进证据级别。模型声明不能提升证据级别。
- **子 agent**：对 `payload.assignee` 等于自己的 process 节点可回报
  `status/reason/blocked_reason/annotations`；delivery 侧可提交设计变更与证据补挂。
- **删边**：两张图完全放开、不限端点状态，但批次必须带 rationale（删除留在变更
  日志）。agent 对 process 图的删边请求以 `edge_removal_requires_supervisor` 拒绝
  并记日志，harness 唤醒 Supervisor 复核后由它代为执行。

## 证据回流契约

证据只有**排产到工具级**才会回流机理图。harness 只在一次工具调用能唯一绑定到
一个 planned 节点时（匹配 `payload.tool_name` 且状态为 proposed/ready 的节点恰好
一个），才把该次调用的证据挂到对应 delivery 元素并重算级别；绑定不上的调用只落为
`observed_tool_call` 记录，机理图停在 proposed。

排产节点 payload：`tool_name`、`delivery_target_type` + `delivery_target_id`、
`evidence_role`（8 角色词表：`intermediate_optimization` /
`ts_optimization_frequency` / `short_irc` / `endpoint_a_optimization` /
`endpoint_b_optimization` / `endpoint_direction_check` /
`endpoint_identity_match` / `thermochemistry`）、`assignee`。一条基元步通常需要
一串 planned 节点（TS 优化频率 → short_irc → 两端点优化 → 端点一致性/同一性检查）
才到 `endpoint_supported`。

先算后建图的场景走 `attach_ref`（带 `evidence_role`）补挂，harness 自动重跑派生
并唤醒 Supervisor 审核；编造 ref_id 以 `invalid_reference` 拒绝。证据级别词表：
`proposed` / `structure_supported` / `saddle_supported` / `endpoint_supported` /
`thermo_annotated` / `rejected` / `inconclusive`；模型只能手动设
proposed/rejected/inconclusive，更高级别由 harness 从引用证据派生。`ts_guess`、
scan 等 advisory 结果不能单独把边推进到 saddle/endpoint。

## Supervisor 触发时机

Supervisor 不再周期性醒来，由图事件驱动，触发消息附必要上下文：

- `graph_initialization`：会话恢复、机理图已有内容，补齐流程工作；
- `delivery_updated`：Coordinator 的机理图变更或子 agent 的补挂被接受
  （附 `coordinator_request`），安排或调整计算工作；
- `new_evidence`：绑定计算落地新证据，复核并更新节点状态、写反馈；
- `process_node_failed`：绑定计算失败，决定重试、改派还是调整方案；
- `edge_removal_requested`：裁决 agent 的删边申请；
- `user_replan` / `pre_delivery`：停止前审计，给出能补齐缺口的流程工作。

Supervisor 的对话上下文跨触发保留。它的变更批次带 base revision，引擎整批校验、
原子生效；被拒绝（stale_revision 等）时先重新 view 再修订，不进入修复循环。

## 交付完成度

"研究清楚了吗"由 coverage contract 确定性评估，不看模型声明。contract 随会话
持久化、带 revision；`delivery_report` 给出已满足 gate、未解决缺口、不确定 gate
和用户豁免 gate。只有用户能 waive gate 或降低要求；模型（含 Supervisor）只能提出
更严格的要求。交付前报告未完成时，agent 必须继续推进、明确部分交付或请用户
豁免/停止，不得自行宣布完成。

## 持久化与失败行为

图子系统在会话级 SQLite 里拥有自己的表：图元数据、节点、依赖边、跨图链接、
coverage contract 和 append-only 变更日志；当前节点/边行是日志的物化视图，加载
不需要重放全部历史。每次变更记录 revision、session、actor（harness/supervisor/
agent/user）、操作、rationale 和时间戳；乐观 revision 校验 + 事务，失败的操作
两张图都不变。重启恢复读物化状态并校验与日志的 revision 一致；物化视图损坏时
从日志重建。图存储不可用时 dag_record/dag_guided 明确报错（fail closed），
不会静默降级为 standard；standard 模式不依赖图存储。`session_events` 是
best-effort 遥测，永远不作为交付证据。

## 接口

- **agent 工具**：`dag_graph`（t-42），4 个 action——`view`（投影/子图）、
  `mutate`（原子批次）、`delivery_report`、`init_from_template`（空图播种标准
  机理研究骨架）。mutate 的 op data shapes 见 `cloudra/skills/dag-operations/`；
  被拒绝时错误信息附正确格式示例。
- **服务/API**：投影、子图、交付报告、变更历史、用户变更批次、replan，路径见
  [`CLI_API_REFERENCE.md`](CLI_API_REFERENCE.md)。
- **TUI**：DAG 屏幕展示双图与变更事件，用户可直接编辑；`/mode` 切换模式。
  图事件是可靠事件，与 best-effort 遥测区分展示。
