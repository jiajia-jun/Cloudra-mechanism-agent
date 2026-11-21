# 运行状态观测接口

下面几个只读接口用来给前端或外部监控查看“Agent 现在到底在干嘛、工具跑到哪一步、关联了哪些计算作业”。它们直接读 `runtime_v2` 事件日志和中央 `compute.db`，走现有 API Token 鉴权，不会启动、重试或取消任何计算。

## 查看项目实时活动

`GET /api/v2/projects/{project_id}/activity`

返回 `project_id`、`as_of_seq`、`observed_at` 和每个 Agent 的当前快照，包括父子关系、运行状态、当前 `goal`、`activity`（如 `running_tool`、`waiting_model`、`waiting_approval`、`waiting_input`、`waiting_background`、`idle` 等）、未结束的工具调用 `active_calls`、明确的等待对象 `waits`、活跃计算作业和待触发提醒。

注意两点：
- 这里有一说一：只有事件里明确记了等待对象才算在等，不会单凭父子关系或后台有计算就瞎猜它卡住了；
- `as_of_seq` 用来衔接项目 SSE 流，没有新事件只说明这段时间安静，不代表进程死了。

## 查看工具调用记录与详情

- **分页列表**：`GET /api/v2/agents/{session_id}/tool-calls?limit=50&before=<session_seq>`（`limit` 范围 1–200，按时间倒序分页，每条摘要最多 500 字）。
- **单条详情**：`GET /api/v2/agents/{session_id}/tool-calls/{request_event_id}`。

注意每条调用的唯一地址是 **`request_event_id`**，而不是模型返回的 `tool_call_id`（后者在审批或重试时可能复用）。详情接口会返回完整原始入参 `arguments`、校验归一化后的 `effective_arguments`、完整原始输出 `result`、阶段进度 `progress`、原始事件列表以及关联的 `compute_jobs`（严格按项目隔离，不会漏出其他项目的作业）。

工具执行状态、副作用状态、计算作业状态和科学验证结论是分开记录的：比如 `submit_compute_job` 成功返回（`completed`）时，对应的量化作业可能还在排队（`ready`）；如果 run 异常中断导致工具没写结束事件，查询时会如实投影成 `status=interrupted`，但不会篡改底层事件或计算账本。

## 实时阶段进度与单作业查询

工具在执行过程中可以通过 `tool.progress` 事件汇报阶段（`validating` / `preparing` / `executing` / `submitting` / `waiting` / `parsing` / `postprocessing`）以及关联的 `compute_job_ids` 和 `waits`。事件先落盘再推 SSE，重放历史不会重新跑工具；只有工具真的汇报了阶段才展示，不会伪造假进度条。

想查某一条计算作业的当前账本状态，直接调 `GET /api/v2/projects/{project_id}/compute/jobs/{job_id}`（未知或跨项目返回 404）。

相关回归测试在 `test_api_v2_observability.py`、`test_runtime_v2_invocation.py`、`test_runtime_v2_subagent_bridge.py` 和 `test_compute.py`。
