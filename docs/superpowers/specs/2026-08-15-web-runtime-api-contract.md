# Cloudra Web Runtime：API v2 契约（S1 规格）

> 状态：待评审。评审通过前不进入实现。
> 前置阅读：`2026-08-15-web-runtime-domain-events.md`。
> 版本策略：v2 是唯一 API；v1 与旧 TUI/Flet 在 S1 实现完成后删除，无兼容层。

## 1. 通用约定

- Base：`/api/v2`
- 认证：`Authorization: Bearer <runtime-token>`。Electron main 为本地 runtime 生成随机 token，
  经 preload 注入 renderer；浏览器开发模式由 Vite dev server 代理并注入。
- 所有写操作支持 `Idempotency-Key` 头（或 body 内 `command_id`），重复命令返回首次结果。
- 写操作响应统一含：

```jsonc
{
  "command_id": "cmd_...",
  "accepted": true,
  "event_id": "evt_...",       // 该操作产生的控制事件
  "data": { ... }              // 操作后的最新资源快照
}
```

- 错误统一：

```jsonc
{
  "error": {
    "code": "invalid_request",   // not_found / invalid_request / state_conflict /
                                 // permission_denied / role_forbidden / runtime_unavailable
    "message": "...",
    "details": {}
  }
}
```

- 时间戳一律 RFC3339 UTC；ID 使用 `prj_/as_/evt_/run_/cmd_` 前缀。
- API 永远不回显 `api_key`；只返回 `api_key_set: bool`。

## 2. Runtime

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/runtime/health` | 无鉴权健康检查 |
| GET | `/runtime/capabilities` | 内置 roles、全局工具清单、平台 profile（desktop/android） |
| GET | `/runtime/settings` | 全局默认 RuntimeSettings（掩码） |
| PATCH | `/runtime/settings` | 修改全局默认；只影响后续 spawn |
| GET | `/runtime/stream` | 全局 SSE（所有项目聚合；仅诊断用） |

## 3. Projects

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/projects` | 列表，默认排除 archived；支持 `?state=` |
| POST | `/projects` | `{name, workspace_dir?, settings?}` → Project |
| GET | `/projects/{project_id}` | 详情 + 运行中 Agent 数量摘要 |
| PATCH | `/projects/{project_id}` | 改 name / workspace_dir / archived / settings |
| DELETE | `/projects/{project_id}?archive=true` | 仅归档；不物理删除 |
| GET | `/projects/{project_id}/workspace` | 校验工作区存在、返回其目录列表（受限浏览） |
| GET | `/projects/{project_id}/stream` | 项目聚合 SSE（含全部 Agent 运行事件 + 控制事件） |

`PATCH /projects/{id}` 的 `settings` 变化产生 `project.settings_changed`，**不回溯修改已有 Agent**。

## 4. Agents（统一资源，无 coordinator 特例）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/projects/{project_id}/agents` | 该项目全部 AgentSession；支持 `?state=&role_id=` |
| POST | `/projects/{project_id}/agents` | spawn |
| GET | `/agents/{session_id}` | Agent 详情 + capabilities + children |
| GET | `/agents/{session_id}/transcript` | 规范 transcript 投影 |
| GET | `/agents/{session_id}/events` | `?after=&types=&limit=`，按 session_seq |
| GET | `/agents/{session_id}/events/{event_id}` | 单事件详情 |
| GET | `/agents/{session_id}/stream` | 单 Agent SSE |
| POST | `/agents/{session_id}/messages` | 注入消息（用户或父 Agent） |
| POST | `/agents/{session_id}/cancel` | 取消，级联回收子进程 |
| POST | `/agents/{session_id}/restart` | 同一 session 开新 run |
| PATCH | `/agents/{session_id}/settings` | 运行中改设置，当前会话生效 |
| GET | `/agents/{session_id}/artifacts` | 该 Agent 关联产物 |

### 4.1 spawn

```jsonc
// POST /projects/{project_id}/agents
{
  "role_id": "small_mol",
  "parent_session_id": null,       // 可空
  "display_name": null,            // 可空，默认 role #n
  "query": "优化过渡态 TS-1",
  "settings": { "model": "..." }   // 可空；覆盖项目默认与角色默认
}
// 200 → {command_id, accepted, data: AgentSession}
```

权限：由调用者身份决定——人类用户可 spawn 任何角色；Agent 通过内部 mailbox 发起，
最终仍要经过 `can_spawn + spawn_roles` 校验。

### 4.2 注入消息

```jsonc
// POST /agents/{session_id}/messages
{ "content": "先不要继续，把当前假设写下来" }
// → {command_id, message_id, data: AgentSession}
```

- 对 `running`：进入该 Agent 的事件队列，其 ReAct 循环按现有外部事件语义处理。
- 对 `waiting_input`：等价于回答 pending interaction？**否**——message 是消息，response 走
  `/interactions/{id}/response`，两者不混用。
- 对 `succeeded`：唤醒并开新 `run_id`。
- 对 `failed` / `cancelled`：拒绝（先 restart）。

### 4.3 cancel / restart

```jsonc
// POST /agents/{session_id}/cancel
{ "message": "方向错了" }
// message 可选；只作为用户信息进入控制事件与 transcript，不要求被取消的任务消费
// → AgentSession state=cancelled；agent.cancelled 表示子进程已回收

// POST /agents/{session_id}/restart
{ "message": "换模型重跑", "settings": {} }   // 均可选
// message 会成为新 run 的第一条用户消息；省略则沿用原任务 query
// → 同一 session_id，新 run_id，state=queued/running
```

### 4.4 运行中改设置

```jsonc
// PATCH /agents/{session_id}/settings
{ "yolo": true, "model": "deepseek-v4", "temperature": 0.3 }
// → {command_id, accepted, data: {agent, settings_revision, event_id}}
```

- 部分更新；未知字段 `invalid_request`。
- `orchestration_mode` 只接受 `standard / dag_record / dag_guided`。
- 写前校验 model/base_url 格式；密钥只写不回显。
- 每次修改产生 `agent.settings_changed`，携带 `settings_revision`。

## 5. Roles

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/roles` | 全部角色模板 |
| GET | `/roles/{role_id}` | 详情 |
| PATCH | `/roles/{role_id}` | 改 default_settings / permissions / tool_policy / can_spawn / spawn_roles |

- 只影响之后 spawn 的 Agent；对运行中 Agent 用 `PATCH /agents/{id}/settings` 单独改。
- `builtin` 角色不可删；`permissions` 收窄必须显式确认（body 带 `confirm=true`）。

## 6. 控制面（审批 / 交互 / 产物 / DAG）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/projects/{project_id}/approvals` | 待处理/最近审批 |
| POST | `/approvals/{approval_id}/decision` | `{decision: "approve"|"deny", reason?}` |
| GET | `/projects/{project_id}/interactions` | pending interactions |
| POST | `/interactions/{interaction_id}/response` | `{response}` |
| GET | `/projects/{project_id}/artifacts` | 产物列表 |
| GET | `/artifacts/{artifact_id}/download` | 受控下载 |
| GET | `/projects/{project_id}/dag/process` | process 图 |
| GET | `/projects/{project_id}/dag/delivery` | delivery 图 |
| GET | `/projects/{project_id}/dag/report` | coverage report |
| GET | `/projects/{project_id}/dag/history` | mutation journal |
| POST | `/projects/{project_id}/dag/mutations` | 用户/UI 提交图变更 |

DAG 路由形状沿用现有确定性引擎语义；在 S1 只重新挂载到 project 资源下，不改推导规则。

## 7. SSE 细节

- 订阅：`GET /projects/{id}/stream?cursor=<seq>&include_control=true`
- 游标：项目级 `seq`；重连时用最近收到的 `seq` 续传，不丢事件。
- 心跳：15 秒一条 `{type: "heartbeat"}`。
- 每事件为单个 SSE `event: <type>` + `data: <envelope JSON>`。
- 事件表提供 30 天滚动保留（可配置）；transcript 永久保留，大结果只存 artifact_ref。

## 8. Electron 与开发模式

- Electron main 负责：单实例锁、启动/重启 runtime 子进程、生成 token、托盘、原生通知、
  目录选择对话框。
- preload 只暴露：`runtimeBaseUrl`、`runtimeToken`、`selectDirectory()`、`platform`、
  `onDeepLink`（预留）。
- renderer 通过普通 `fetch` + `EventSource` 访问 runtime；不直接访问文件系统或 Node API。
- 开发模式：Vite dev server + 环境变量指向已启动的 runtime，脱离 Electron 调试。
- 浏览器 fallback：同一 SPA 可直接在浏览器访问 localhost runtime，作为隐藏能力保留。

## 9. 实现边界（S1 明确不做）

- 不做多 runtime / 多机调度。
- 不做用户账号与多用户隔离（单机单用户）。
- 不做 Python 侧 API 客户端 SDK；前端 TS 客户端放 renderer 工程内。
- 不做移动端响应式布局（M6 再做，但 API 不预留特例）。
- 不做旧 v1 路由兼容。

## 10. 待评审问题

1. DELETE project 只归档、不可物理删除，可以吗？
2. spawn/cancel/restart/message 的权限模型：**人类用户全权**，Agent 之间走 mailbox + role
   权限；同意吗？
3. transcript 作为事件投影返回、不做单独消息表；同意吗？
4. 事件保留 30 天滚动（transcript 永久），同意吗？
