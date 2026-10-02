# 运行透明度后端接口

这些接口复用 runtime_v2 的持久化事件与中央计算账本，使用现有 API 身份验证。
它们只读，不启动、重试或终止计算。前端可用现有项目 SSE 获取更新通知，再按需查询。

## 项目活动

`GET /api/v2/projects/{project_id}/activity`

返回 `project_id`、`as_of_seq`、`observed_at` 和 `agents`。
每个 Agent 包含身份、父 Agent、运行状态、当前 run、`goal`、`activity`、
`active_calls`、`waits`、最后一条相关事件引用、最后一次完成门禁、活跃计算与待触发提醒。

- `active_calls` 包含当前 run 中全部未结束调用，支持并行 JS 子调用。
- `activity` 区分 `running_tool`、`waiting`、`waiting_model`、`waiting_approval`、
  `waiting_input`、`waiting_background`、`queued`、`idle`、`unknown`。
- `waits` 是明确记录的等待目标，包含种类、目标 ID 与来源调用或事件。
  父子关系本身不证明父 Agent 正在等待；活跃计算也不自动证明 Agent 已挂起。
- 后台等待必须有对应已结束 run 的 `wait_background` 门禁；此时提供账本中的
  活跃计算、待触发提醒作为唤醒来源。暂无来源时保持空列表，不猜测原因。
- `goal` 来自既有目标文件；未设置时为 null，不由聊天文本推断。
- `as_of_seq` 只对应事件快照，可用于衔接项目 SSE 的 cursor。计算账本和目标文件
  在工作线程中随后读取；这不是跨多个存储的原子快照。`observed_at` 是完成读取时间。
- 时间戳仅表示记录时间。没有新事件不证明进程死亡，也不触发卡死或失败判定。

## 工具调用列表

`GET /api/v2/agents/{session_id}/tool-calls?limit=50&before=<session_seq>`

返回 `items` 与 `next_before`，按请求时间倒序。`limit` 范围 1–200；`before`
为排他游标，下一页使用 `next_before`，无更多记录时为 null。分页按调用次数，
不会因中途日志多而丢掉一次调用的开始记录。

每次请求用 **`request_event_id`** 标识。模型的 `tool_call_id` 可以跨 run 或审批
重试复用，不能作为调用详情的唯一地址。新运行记录还会在阶段、原始结果和结束
事件上携带请求事件 ID，使重叠调用也能准确关联。

列表提供工具名、run/JS 程序/调用编号、阶段、状态、起止/更新时间、耗时、结果摘要、
副作用状态、错误、原始结果事件 ID、计算 ID 和已登记产物 ID。摘要最多 500 字符，
`summary_truncated` 标明是否截短。完整输入输出只在详情中返回。

## 工具调用详情

`GET /api/v2/agents/{session_id}/tool-calls/{request_event_id}`

除列表字段外还包含：

- `arguments`：原始完整参数；`effective_arguments`：工具适配器或执行器明确报告的
  最新校验/归一化参数。不是对外部程序全部默认参数的推断。
- `result`：完整的 `tool.result_recorded` 返回，包含原始 `data`，不以摘要替代。
- `result_availability`：`pending`、`available` 或 `unavailable`。
- `progress` 与 `events`：本次调用的阶段记录和原始事件，可定位到来源与时间。
- `compute_jobs`：关联作业当前账本记录；`unavailable_compute_job_ids`：无法取得
  的作业编号（缺失或不属于当前项目），不会返回其他项目的作业详情。

工具状态、副作用状态、计算状态与科学验证结论必须分别展示。例如提交工具
`completed` 时，计算可能仍为 `ready`；后处理失败时，工具可以是 `failed`，
而 `effect_state=completed` 且原始结果仍可读取。run 已结束但工具未写结束记录时
投影为 `interrupted`，不会据此修改计算账本。

原始结果只关联到自己的调用尝试，不追随跨会话或其他尝试的任意事件 ID。
原始事件接口 `GET /api/v2/agents/{session_id}/events/{event_id}` 继续可用。

## 实时阶段与计算关联

`tool.progress` 通过现有 EventWriter 先持久化再发布到项目 SSE，重放不会执行工具。
阶段负载由 `ToolProgress`（Pydantic，拒绝多余字段）校验：

- `phase`：validating / preparing / executing / submitting / waiting / parsing / postprocessing。
- `message`：执行器报告的说明；`effective_arguments`：可选归一化参数。
- `compute_job_ids`：正整数作业编号；`waits`：明确等待的 Agent 或计算作业。
- 调用、请求事件与 JS 程序编号由运行时填写，工具不负责猜测关联关系。

已接入通用工具的校验后参数记录、计算提交的准入/入库/同步等待阶段，以及
同步子 Agent 调用（含 swarm）的等待目标。TS 工具通过原始结构化结果的
`usage.jobs` / `waiting_for` 关联计算。普通提交通过阶段记录和 `job_id` 关联计算。
其他工具目前可看到统一生命周期、参数和完整返回；内部细分阶段只有执行器主动
报告时才存在，不生成虚假的进度百分比。

`GET /api/v2/projects/{project_id}/compute/jobs/{job_id}` 返回单个作业的当前账本记录，
包含节点、调度状态、资源和错误。未知项目/作业或跨项目访问返回 404。
账本不存在时查询不创建它；数据库读取失败会报错，不冒充“没有作业”。

## 验证

相关测试位于 `test_api_v2_observability.py`、`test_runtime_v2_invocation.py`、
`test_runtime_v2_subagent_bridge.py` 与 `test_compute.py`。
覆盖完整结果、分页、并发归属、后台等待、事件重放、持久化失败和项目隔离。
