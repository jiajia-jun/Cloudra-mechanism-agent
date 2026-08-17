# DAG 引导编排（dag_record / dag_guided）

本文说明 Cloudra 的 DAG 引导编排子系统（`cloudra/dag/`）的当前实现：单张 delivery
机理图 + stage 契约 + CallReview 收件箱、三种编排模式、分权规则、阶段绑定契约与
Supervisor 触发时机。面向需要理解或修改这条链路的开发者；用户使用入口见
[`CLI_API_REFERENCE.md`](CLI_API_REFERENCE.md)；Web UI 在项目设置中选择模式。

## 解决什么问题

机理研究是长链多步工作：文献调研、映射、构象搜索、TS 初猜、优化、频率、IRC、
端点确认、热化学。纯对话驱动时，"做过什么、证据够不够"只存在于模型上下文里，
随压缩和重开丢失。DAG 编排把被研究的化学机理本身（已经确立了什么）落到持久存储：

- **delivery DAG（机理图）是唯一持久图**：节点是中间体 occurrence，边是基元步；
  每个元素携带一份有序 **stage 契约**（该元素欠哪些证据、按什么顺序绑定）。
- **CallReview 收件箱**（`dag_call_reviews`，append-only 表，不是图）：每个交付相关的
  已完成工具调用 / 计算作业终态落一行，等 Supervisor 复核。
- 不存在 process DAG："下一步做什么"不落图，Coordinator 在草稿被接受后按自己的
  节奏推进；没有 frontier、没有排产、没有 assignee 驱动的写图权限。

图存储是权威。节点只存类型化引用（artifact / compute_job / tool_result / species）
和小注解，不嵌几何、日志或工具输出正文；单独的 filesystem 路径不算证据。

## 三种模式与消融边界

`orchestration_mode` 是会话级枚举；runtime_v2 允许经 `agent.settings_update` 中途切换（前端模式下拉会同步 PATCH 项目内所有现存 agent）：

| 模式 | 行为 |
| --- | --- |
| `standard`（默认） | 不读不写任何图，不运行 Supervisor，普通工作零图成本 |
| `dag_record` | Coordinator 用 `dag_propose_mechanism` 提交草稿（harness 自动接受），并用 `dag_bind_evidence`（带 `stage_kind`）自绑阶段；Supervisor 不运行 |
| `dag_guided` | Supervisor 用 `dag_accept_mechanism` 接受/驳回草稿（接受前计算入口保持关闭），并用 `dag_review_call` 复核收件箱里的每个交付相关调用、绑定阶段 |

三档把"图簿记本身的效果"和"Supervisor 控制的效果"分开，支撑三方消融实验。
Web UI（项目设置）、CLI（`--orchestration-mode`）、API（session 创建的
`orchestration_mode` 字段）三入口等价。图按会话持久化，
跨过 session 与进程重启存活；standard 会话不碰已有图，之后的 DAG 会话可以继续它。

## 主循环与分权

```
Coordinator dag_propose_mechanism（delivery 草稿 + 每元素 stage 契约 + rationale）
  → dag_guided：Supervisor dag_accept_mechanism 接受（dag_record：harness 自动接受）
  → 草稿落图，所有阶段 pending，计算入口解锁
  → Coordinator / 子 agent 按自己的节奏工作（子 agent 只跑工具、不写图）
  → 交付相关调用完成（parsers / ts_guess / thermo_analysis / 计算作业终态）
      → CallReview 收件箱 + （合并后）唤醒 Supervisor
  → Supervisor dag_review_call：target + stage_kind + agree|disagree|skip|ignore
  → harness 确定性校验（顺序、调用成功、ref 是完工产物而非 submit、deriver 检查）
  → stop / coverage：每个 required stage supported，或带非空理由 skipped
```

- **delivery DAG 归 Coordinator 设计**：机理假设与 stage 契约都是它的
  （`dag_propose_mechanism`，接受后仍可 `dag_add_species` / `dag_add_step` /
  `dag_update_delivery_element` 调整）。Supervisor 对它完全只读。
- **Supervisor 只做判定**：接受/驳回草稿（`dag_accept_mechanism`）、逐调用复核
  （`dag_review_call`）、强化 coverage contract（`dag_set_coverage_contract`，
  只能变严；豁免 gate 是用户专属）。它不调度工作、不运行计算。
- **子 agent**：不维护图，跑工具并用具体 tool_call_id 报告结果；可以建议某个结果
  支撑哪个元素/阶段，但这只是提示，绑定只经 Supervisor 复核（guided）或
  Coordinator 自绑（record）发生。
- **harness（确定性适配器）**：注册不可变产物与证据引用、执行阶段绑定的全部校验、
  从阶段派生元素级证据级别。模型声明不能提升证据级别。
- **删边**：走 `dag_remove_edge`，**必须带 rationale**（删除留在变更日志）。Supervisor 对
  delivery 只读，结构性清理由 Coordinator 执行；复核中发现的剪枝诉求经
  `dag_message_supervisor` 转达。

## stage 契约与绑定规则

Coordinator 在草稿里为每个元素选择有序阶段子集；harness 从不推断未声明的链。
occurrence 阶段：`geometry` / `frequency` / `single_point`；基元步阶段：`ts_guess`
（advisory，永远不能满足 `ts_opt`/`frequency`）/ `ts_opt` / `frequency` / `short_irc` /
`endpoint_a` / `endpoint_b` / `direction` / `identity` / `thermochemistry`。

- **严格顺序**：绑定第 k 个阶段要求此前所有 required 阶段已 `supported` 或
  `skipped`，否则 `stage_out_of_order`。
- **校验**：绑定只接受成功调用的完工产物（parser 输出等）；追溯到
  `submit_compute_job` 调用的绑定以 `bind_target_is_submit` 拒绝——submit 永远不是
  证据。deriver 成为检查器（如 TS `frequency` 绑定要求解析日志里 n_imag==1，
  否则 `saddle_check_failed`）。
- **`rejected` 不是处置**：`disagree` 把阶段标为 `rejected`（必须附理由），它是
  仍欠的开放缺口——只能靠后续调用的重新绑定（agree）或显式 skip-with-reason 关闭。
  `skipped` 带理由是唯一的非成功处置。
- 元素级证据级别（`structure_supported` / `saddle_supported` / `endpoint_supported` /
  `thermo_annotated` 等）由阶段确定性派生，仅作展示与旧库兼容。

## CallReview 收件箱

入箱节流：只有 registry 声明 `dag_review=True` 的工具（`gaussian_log_parser` /
`reaction_mapping` / `thermo_analysis` / `ts_guess`）与计算作业的完成/失败会落
`dag_call_reviews` 行；普通 bash/文件读写和 `submit_compute_job` 调用本身都不入箱、
不唤醒 Supervisor。每行携带 sidecar 数据（caller role 与 legacy a-N id、父会话、
工具名、参数摘要、成功位、compute_job_id 与终态），供 Supervisor 判断——sidecar
不构成任何自动绑定权限。收件箱是 append-only 直连 INSERT（无乐观 revision），
唤醒按触发合并（coalesced），已有排队/进行中的 Supervisor 运行时新触发折叠进去。

## Supervisor 触发时机

Supervisor 不再周期性醒来，由图事件驱动，触发消息附必要上下文：

- `mechanism_proposed`：Coordinator 提交了机理草稿（附 rationale），接受或驳回；
- `tool_call_review`：收件箱有 pending 复核（附清单），逐条 `dag_review_call`；
- `delivery_updated`：Coordinator 在接受后改了机理（附 rationale 摘要），审计变更；
- `coordinator_message`：`dag_message_supervisor` 成功投递原文；
- `user_replan` / `pre_delivery`：停止前审计——先读 coverage report 再放行。

Supervisor 的对话上下文跨触发保留。各 verb 工具经引擎校验后生效；被拒绝时先
`dag_view` 再修订，不进入修复循环。

## 交付完成度

"研究清楚了吗"由 coverage contract 按阶段确定性评估，不看模型声明：`complete` ⇔
每个 required stage `supported`，或 `skipped` 且带非空理由；`pending` 与 `rejected`
都是未决缺口（rejected 缺口连同理由出现在报告里）。contract 级要求（如必需
thermochemistry）按阶段评估，对所有元素生效，不被"分支已处置"跳过。contract 随会话
持久化、带 revision；`dag_delivery_report` 给出已满足 gate、未解决缺口、不确定 gate
和用户豁免 gate。只有用户能 waive gate 或降低要求（豁免不能替代缺失的阶段理由）；
Supervisor 可用 `dag_set_coverage_contract` 提出更严格的要求。停止审计：`stop`
声明 `complete` 需通过覆盖率审计；未显式 stop 而结束的 run 在 dag 模式下记
`partial`；有未终态子 agent / pending 提醒 / pending 计算作业时 stop 视为挂起。
交付前报告未完成时，agent 必须继续推进、明确部分交付或请用户豁免/停止，
不得自行宣布完成。

## 持久化与失败行为

图子系统在会话级 SQLite 里拥有自己的表：图元数据、节点、边、coverage contract、
append-only 变更日志、`dag_drafts`（机理草稿；`mechanism_accepted` =
存在 state='accepted' 的草稿，无需单独标志位）、`dag_call_reviews`（收件箱）；
当前节点/边行是日志的物化视图，加载不需要重放全部历史。每次变更记录 revision、
session、actor（harness/supervisor/agent/user）、操作、rationale 和时间戳；乐观
revision 校验 + 事务，失败的操作图不变。旧库的 process 图行与日志只读兼容：
重放时 process 操作记为 `ignored_legacy_process_op` 后跳过。重启恢复读物化状态
并校验与日志的 revision 一致；物化视图损坏时从日志重建。图存储不可用时
dag_record/dag_guided 明确报错（fail closed），不会静默降级为 standard；
standard 模式不依赖图存储。`session_events` 是 best-effort 遥测，永远不作为交付证据。

## 接口

- **agent 工具族**（取代单一 `dag_graph`）：`dag_view`（默认投影 = delivery 缺口 +
  pending 复核 + 近期变更；`graph_kind=delivery` 取紧凑分页子图）、
  `dag_delivery_report`、`dag_propose_mechanism`（Coordinator 提交草稿 + stage 契约）、
  `dag_accept_mechanism`（Supervisor 接受/驳回）、`dag_review_call`（Supervisor
  逐调用阶段判定）、`dag_bind_evidence`（Coordinator 且仅 dag_record，必填
  `stage_kind`）、`dag_add_species` / `dag_add_step` / `dag_update_delivery_element`
  （Coordinator 设计 delivery）、`dag_remove_edge`（必填 rationale）、
  `dag_set_coverage_contract`（Supervisor only，只能变严）、`dag_message_supervisor`。
  字段含义与选用时机见 `cloudra/skills/dag-operations/`；被拒绝时错误信息附正确
  格式示例。
- **服务/API**：delivery 图、交付报告、变更历史、投影（delivery + pending 复核 +
  coverage）、复核收件箱、当前草稿、用户变更批次、replan，路径见
  [`CLI_API_REFERENCE.md`](CLI_API_REFERENCE.md)；旧 `/dag/process` 返回 410。
- **Web UI**：DAG 面板展示机理图（带阶段状态）、复核收件箱、变更事件和 mutation
  编辑框。图事件是可靠事件，与 best-effort 遥测区分展示。
