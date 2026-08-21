# Cloudra Web Runtime：领域模型与事件字典（S1 规格）

> 状态：待评审。评审通过前不进入实现。
> 决策基线：Electron 壳 + 本地 FastAPI runtime；不做任何旧版兼容；所有 Agent 在 API 层完全平行；
> 用户操作一律落为事件并修改内存中的量；单机内多 Agent 真正并发。

## 1. 领域模型

### 1.1 Project（项目）

```jsonc
{
  "id": "prj_...",
  "name": "烯烃臭氧化",
  "workspace_dir": "/data/projects/ozonolysis",   // 项目绑定工作区；spawn 默认继承
  "archived": false,
  "settings": {
    "orchestration_mode": "dag_guided",
    "defaults": { /* RuntimeSettings，见 1.4 */ }
  },
  "created_at": "...",
  "updated_at": "..."
}
```

- `settings.defaults`：本项目新建 Agent 的默认设置。
- `workspace_dir`：唯一绑定点。单个 Agent 可在 spawn 时显式覆盖。
- `archived`：归档不是删除；归档项目不显示在默认列表，数据保留。

### 1.2 RoleProfile（角色模板）

内置角色从包内声明初始化，用户可持久覆盖部分字段。**Coordinator 在领域模型里不特殊**，它只是
`coordinator` 这个 role。

```jsonc
{
  "role_id": "small_mol",              // 同时是内置角色与 Follower 定制的作用域
  "display_name": "Small-molecule compute",
  "description": "...",
  "permissions": {
    "read": true,
    "write": true,
    "manage": false,                    // manage ≈ 可编排其他 Agent
    "script": true,
    "destructive": false
  },
  "can_spawn": false,
  "spawn_roles": null,                  // null = 不限；否则为允许的 role_id 列表
  "tool_policy": {
    "allow": ["*"],
    "deny": ["device.camera.capture"]
  },
  "default_settings": { /* 覆盖 Project.defaults 的部分设置 */ },
  "builtin": true
}
```

- 内置角色不可删除，但 `default_settings` / `tool_policy` 可改（这是 Follower 定制化的入口）。
- `permissions` + `tool_policy` 经 runtime 能力过滤器合成最终的 `AgentSession.capabilities.tools`。

### 1.3 AgentSession（所有 Agent 的唯一资源）

前端顶部切换的每一个 Agent 就是它；API 没有 coordinator 专属资源。

```jsonc
{
  "id": "as_...",                       // 持久身份；跨 restart 不变
  "project_id": "prj_...",
  "role_id": "small_mol",
  "display_name": "small_mol #2",
  "parent_session_id": "as_...",        // 只表达派生关系；不授予任何 API 特权
  "state": "running",
  "settings": { /* RuntimeSettings，spawn 时的有效快照，运行中可变 */ },
  "settings_revision": 3,
  "capabilities": {
    "permissions": { /* 同上 */ },
    "can_spawn": false,
    "spawn_roles": null,
    "tools": ["text_reader", "..."]     // 已过 runtime 过滤的最终工具名列表
  },
  "current_run": {
    "run_id": "run_...",
    "started_at": "..."
  },
  "children": ["as_...", "as_..."],     // 派生视图，不单独存储
  "created_at": "...",
  "updated_at": "..."
}
```

状态机：

```text
queued ──▶ running ──▶ waiting_input ──▶ running
              │   │
              │   └──▶ waiting_approval ──▶ running
              │
              ├──▶ succeeded ──(注入消息)──▶ running   // 同一 session，新 run
              ├──▶ failed ──(restart)──▶ queued
              └──▶ cancelled ──(restart)──▶ queued

任意非终态 ──(cancel)──▶ cancelled
```

- `succeeded` 不是“进程死了”，只是任务结束；用户注入消息即唤醒并开新 `run_id`。
- `restart` 保留同一 `AgentSession` 身份与全部历史事件，新增 run 分段。前端因此能在一个
  AgentView 里看到多次运行。

### 1.4 RuntimeSettings（运行中可变的最小设置集）

```jsonc
{
  "model": "deepseek-4-pro",
  "base_url": "https://api.deepseek.com/",
  "api_key_set": false,                 // API 永远不回显密钥；PATCH 可写 api_key
  "temperature": 0.7,
  "max_tokens": 32768,
  "context_window": 200000,
  "top_p": null,
  "frequency_penalty": 0.0,
  "presence_penalty": 0.0,
  "timeout": 300,
  "yolo": false,
  "native_search": "auto",
  "native_search_params": {},
  "orchestration_mode": "dag_guided"
}
```

生效语义（写入事件即更新内存，无环境变量参与）：

| 字段 | 生效时机 |
|---|---|
| `model` / `base_url` / 采样参数 / `max_tokens` / `context_window` / `timeout` | 当前会话内**下一次 LLM 请求**生效；不打断进行中的流 |
| `yolo` | 当前会话内**下一次危险操作审批检查**生效 |
| `orchestration_mode` | 当前 Agent 下一次推理的 DAG 集成路径生效；只允许在项目 `dag_*` 与 `standard` 间切换 |
| `api_key` | 下一次 LLM 请求生效 |

所有运行期修改都通过 `PATCH /agents/{id}/settings` 或角色/项目默认设置修改，先落
`control_events` 再改内存。

### 1.5 事件与审计

```
control_events  用户/系统对 runtime 的每一次操作（settings、spawn、cancel、inject、审批）
session_events  Agent 运行观察（llm/tool/phase/dag/warning）
```

- 两条流永久追加，只读。
- 每个事件有项目级单调 `seq`；每个 Agent 另有 `session_seq`。
- transcript 是 session_events + 注入消息的**派生投影**，不是独立真相源。

## 2. 事件信封

SSE 与查询接口共用同一信封：

```jsonc
{
  "stream": "agent",                    // "agent" | "project"
  "event_id": "evt_...",
  "project_id": "prj_...",
  "session_id": "as_...",               // project 流中的控制事件可为空
  "run_id": "run_...",                  // agent 运行事件必填
  "seq": 881,                           // 项目内单调，SSE 游标使用
  "session_seq": 74,                    // Agent 内单调
  "type": "tool.finished",
  "data": { /* 各类型负载 */ },
  "created_at": "..."
}
```

## 3. 事件字典

### 3.1 控制事件（`stream: "project"`）

| type | data 要点 | 语义 |
|---|---|---|
| `project.created` | `project` | 项目建立 |
| `project.updated` | `changes`, `actor` | 名称/工作区/归档变化 |
| `project.settings_changed` | `changes`, `actor` | 项目默认设置变化（只影响后续 spawn） |
| `role.updated` | `role_id`, `changes`, `actor` | 角色模板变化（只影响后续 spawn） |
| `agent.spawn_requested` | `role_id`, `parent_session_id`, `command_id` | 幂等创建请求已受理 |
| `agent.spawned` | `agent` | AgentSession 已建立并入队 |
| `agent.spawn_rejected` | `code`, `reason` | 拒绝（权限/参数） |
| `agent.settings_changed` | `changes`, `actor`, `settings_revision` | 运行期设置已写入内存 |
| `agent.message_injected` | `message_id`, `content` | 用户/父 Agent 注入消息 |
| `agent.cancel_requested` | `message?`, `actor` | 取消请求受理；`message` 是用户附言，只进事件与 transcript，不要求被取消的任务消费 |
| `agent.cancelled` | `session_id` | 取消完成（含子进程回收完成） |
| `agent.restart_requested` | `message?`, `actor` | 重启请求受理；`message` 成为新 run 的首条用户消息 |
| `agent.restarted` | `run_id`, `agent` | 新 run 入队 |
| `approval.requested` | `approval_id`, `session_id`, `tool`, `summary` | 危险操作等待审批 |
| `approval.decided` | `approval_id`, `decision`, `actor` | 审批完成 |
| `interaction.requested` | `interaction_id`, `session_id`, `prompt` | ask_user 等交互 |
| `interaction.responded` | `interaction_id`, `actor` | 交互已回答 |
| `command.rejected` | `command_type`, `code`, `message` | 命令被拒绝也落审计事件 |

### 3.2 Agent 运行事件（`stream: "agent"`，并转发进 project 聚合流）

| type | data 要点 | 语义 |
|---|---|---|
| `agent.state_changed` | `from`, `to`, `reason` | 状态机唯一合法迁移 |
| `run.started` | `run_id`, `settings_summary`（掩码） | 新一轮运行开始 |
| `run.finished` | `run_id`, `outcome`, `usage` | 运行结束与 token 汇总 |
| `llm.request_started` | `model`, `prompt_revision`, `tool_revision` | 本轮请求配置快照 |
| `llm.chunk` | `delta` | 流式增量 |
| `llm.completed` | `usage`, `finish_reason`, `latency_ms` | 单请求完成 |
| `llm.failed` | `error_code`, `message` | 请求失败 |
| `tool.started` | `tool_call_id`, `tool_name`, `arguments_summary` | 工具开始；摘要不含大对象 |
| `tool.blocked` | `tool_call_id`, `tool_name`, `stage`, `message` | policy stage 拦截工具 |
| `tool.finished` | `tool_call_id`, `tool_name`, `is_success`, `result_summary`, `artifact_ref?`, `duration_ms` | 工具结束；大结果只放 artifact_ref |
| `tool.approval_requested` | `tool_call_id`, `approval_id` | 与 `approval.requested` 对偶 |
| `dag.gate_blocked` | `gate`, `message` | 实质性门槛拦截 |
| `compaction.started` / `compaction.finished` | `summary_tokens`, `new_tokens` | 上下文压缩 |
| `loop.detected` | `tool_name`, `repeat` | 相同调用循环检测（已实现：turn_pipeline 按 run 跟踪连续相同 name+规范化 arguments 的工具调用，连续 3 次起每次落事件并向模型 push 换思路的 notices 软警告，不硬 block；阈值 spec 未定，实现取 3） |
| `agent.warning` | `code`, `message` | 守卫类软警告 |

### 3.3 查询接口的事件过滤

- `GET /agents/{id}/events?types=tool.*,llm.chunk&after=session_seq`
- `GET /agents/{id}/events/{event_id}` 返回完整事件；`tool.finished` 的大结果通过
  `artifact_ref` 指向工作区/产物，前端需要时再单独拉取，**不把大 JSON 塞进 SSE**。

## 4. 并发与取消语义

- runtime 单进程、单事件循环；所有 AgentSession 是 loop 内的 async task，项目间真正并行。
- 任何阻塞操作（外部程序、浏览器、同步 DB）一律挂到 Agent 的可取消执行句柄，或卸载到线程。
- `cancel(agent)` 的顺序：请求 LLM 循环停止 → 终止该 Agent 当前持有的所有 subprocess →
  状态置 `cancelled` → 广播。`agent.cancelled` 必须代表“子进程也已回收”。
- settings 只由事件循环内单写者修改；DB 只保存投影，事件表是真相源。

## 5. 待评审决策（已暂定，最终确认）

1. `restart` 保留同一 session 身份、用 `run_id` 分段；不是新 session。可接受？
2. `succeeded` 后注入消息即开新 run；不另设 resume 端点。可接受？
3. `orchestration_mode` 放进每 Agent 的 RuntimeSettings；切换立即对下一轮生效。可接受？
4. 密钥只支持“写入 / 不回显 / api_key_set 标志”；不做多密钥管理。可接受？
