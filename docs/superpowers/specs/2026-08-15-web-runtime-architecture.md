# Cloudra Web Runtime：事件管道与模块架构（S1 规格）

> 状态：待评审。评审通过前不进入实现。
> 前置阅读：`2026-08-15-web-runtime-domain-events.md`、`2026-08-15-web-runtime-api-contract.md`。

## 1. 架构原则（还原论约束）

1. **一切皆事件**：用户操作、Agent 间消息、LLM/tool/DAG 观察，全部是事件。模块间不靠
   “调用大 service 对象”通信；运行时状态由事件投影产生。
2. **管道组合，而不是控制器**：每个行为切成单一职责的小阶段，按配置顺序组合。新增
   harness 能力 = 新增一个 stage，不改主循环。
3. **Agent 无政府**：所有 AgentSession 平行，只通过 Mailbox 通信。没有中心调度器。
   `coordinator` 只是 `can_spawn=true` 的角色；`supervisor` 只是被 DAG 事件唤醒的角色。
4. **内存是权威，数据库是投影**：运行中读内存；SQLite 持久化投影用于恢复；事件表是
   永久审计源。所有写路径先 append 事件，再 apply 到内存。
5. **阶段无隐藏依赖**：每个 stage 输入只有 `PipelineContext`，输出只允许三类信号：
   `allow / warn / block`（或观察副作用事件）。禁止 stage 反手调用 API。

## 2. 顶层拓扑

```text
Electron renderer (React SPA)
      │ REST + SSE（只认 /api/v2）
      ▼
FastAPI v2（薄路由：解析 → 校验 → 提交命令）
      ▼
CommandBus ──▶ ControlEventLog（append-only）
      │              │
      ├──▶ Projectors（内存态 + SQLite 投影）
      │              │
      ▼              ▼
RuntimeCore:  ProjectRegistry / AgentHost / Mailbox / EventHub

AgentHost
  ├─ AgentSession #1（async task）
  ├─ AgentSession #2
  └─ ...每个 Agent 拥有：
        Inbox ──▶ TurnPipeline ──▶ PolicyStages ──▶ ExecutionHandles

EventHub ── SSE ──▶ 前端（项目聚合流 / 单 Agent 流）
Mailbox   ──▶ Inbox（用户消息与 Agent 间消息同构投递）
```

依赖规则（可维护性的核心）：

- **API 层只能 import CommandBus 的 schema 和 submit 函数**，不知道 AgentHost 内部。
- **Command handlers 只能 import Projectors + AgentHost/Mailbox 的显式操作**。
- **Pipeline stages 只能 import PipelineContext 类型与事件写入接口**。
- **AgentHost 不 import 任何具体工具类**；工具经 `ToolRegistry` 在管道中解析。
- 任何模块需要“广播”时只写事件；EventHub 订阅事件做 SSE 扇出，写者不知道读者。

## 3. 命令管道（用户操作）

所有用户操作（换设置、spawn、cancel、restart、注入消息、审批）走同一条管道：

```text
HTTP request
  → Pydantic schema 解析
  → 身份/作用域校验（人类用户全权；范围校验 project/agent 存在性）
  → Idempotency-Key 查重
  → 构造 Command{type, target, payload, actor}
  → append control_event（这一步成功才算“受理”）
  → 在事件循环内 apply：
        Projector 更新内存（settings / state / mailbox 投递）
        SQLite 投影异步落盘
  → EventHub 广播
  → 返回 {command_id, event_id, 最新资源快照}
```

关键点：

- **先事件后状态**。任何 `accepted=true` 的响应都意味着事件已落盘；前端可完全信任
  `event_id` 用于审计。
- apply 阶段在 runtime 事件循环内同步完成，不跨线程修改内存，因此无需分布式锁/CAS。
- 幂等表只保留最近窗口；重复命令返回首次的 `command_id` 和快照。
- 命令 handler 一个命令一个函数，注册在字典里；新增命令不触碰路由代码。

## 4. Agent 执行管道（TurnPipeline）

每个 AgentSession 是事件循环上的一个 async task，消费自己的 Inbox。一轮推理是固定
管道，任何阶段都可让这一轮终止（不是让进程崩）：

```text
Inbox dequeue
  → 1. merge：用户/邮箱消息、审批结果、工具唤醒、reminder
  → 2. snapshot：settings_revision + capabilities + 当前 run_id
  → 3. assemble：身份 prompt + 项目工作区快照 + DAG 投影 + 事件注入
  → 4. llm：流式请求（逐 chunk 写 llm.chunk 事件）
  → 5. parse：工具调用 / 文本 / 截断与死循环检测
  → 6. before-tool policy chain（permission → DAG gate → approval → guards）
  → 7. execute：工具执行（阻塞部分挂 ExecutionHandle）
  → 8. after-tool policy chain（observe → evidence derive → supervisor trigger）
  → 9. persist：transcript 投影、token 用量、状态事件
  → 10. decide：continue / wait_input / wait_approval / stop / spawn
```

并发契约：

- LLM 与工具执行期间的流式事件立即广播，前端无感知延迟。
- 任何阻塞调用（subprocess、浏览器、同步 DB）必须挂到该 Agent 的 `ExecutionHandle`
  集合；`cancel` 会先请求管道在最近的决策点停止，再强制终止全部 handles。
- `agent.cancelled` 事件只能在 handles 回收完成后广播。

## 5. PolicyStage：harness 的扩展点

这就是你要求“以后 harness 层改动方便”的落点。DAG gate、evidence、Supervisor 触发、
审批、bash 守卫全部降级为同一种 stage：

```python
class PolicyStage(Protocol):
    name: str

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult: ...
    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result: ToolResult) -> None: ...
    async def before_llm(self, ctx: PipelineContext, messages: list[dict]) -> None: ...
```

- `PolicyResult` 只有四类：`allow` / `warn(annotation)` / `block(message)` / `ask(approval)`。
- stage 通过 `ctx.emit_event(type, data)` 产生观察事件；通过 `ctx.read_once(key)` 在
  同一轮内交换确定性信息（例如 DAG stage 把 coverage 投影给 assemble 阶段）。
- stage 注册表显式排序，`dag_guided` 模式只是启用了 DAG 相关 stage，而不是
  `if orchestration_mode == ...` 的分叉。这是本次重构和现有代码最大的区别：
  **模式 = stage 集合，不再是 if/elif**。
- 新增“证据绑定”“新守卫”“新门槛”= 新增 stage 文件 + 注册表加一行；`TurnPipeline`
  零修改。现有刚完成的 `tools/capabilities` 投影继续作为 stage 的数据来源。

默认 stage 顺序：

```text
permission → workspace_guard → dag_gate → approval → coord_guard
  → bash_habit_guard → delegation_guard
```

## 6. Mailbox：Agent 间无政府通信

- 用户向任意 Agent 注入消息、父 Agent 派单、AgentHub 呼叫、Supervisor 留言，统一是
  `mailbox.deliver(from, to, envelope)`。
- `from` 可以是 `user`、任意 `AgentSession`、或 `system`。
- 投递 = append `agent.message_injected` 事件 → 写入目标 Inbox → 若目标在
  `succeeded/waiting_*` 状态则按状态机唤醒。
- spawn 请求是特殊 envelope：AgentHost 校验发起者的 `can_spawn + spawn_roles`，人类
  用户绕过该限制（人类全权）。
- 不做中心调度：DAG Supervisor 只订阅 `dag.*` 事件被唤醒，它没有比任何 Agent 更高的
  API 身份。

## 7. 模块边界（S1 落地目录）

```text
cloudra/runtime_v2/
  schemas.py          Pydantic：Project/AgentSession/RoleProfile/RuntimeSettings/Event/Command
  events.py           EventLog（append/query）+ EventHub（内存订阅/SSE 扇出）
  commands.py         CommandBus + 每命令一个 handler
  projectors.py       内存态投影 + SQLite 投影写
  projects.py         ProjectRegistry
  roles.py            RoleProfile 加载/覆盖/校验
  agent_host.py       spawn/cancel/restart 生命周期
  agent_session.py    AgentSession 状态机 + Inbox
  turn_pipeline.py    固定管道骨架，只依赖 PolicyStage 协议
  policies/
    __init__.py       stage 注册表（显式顺序）
    permission.py
    dag_gate.py
    evidence.py
    approvals.py
    guards.py         coord/bash/delegation 等轻守卫合一入口
  mailbox.py          agent-to-agent / user-to-agent 投递
  capabilities.py     角色权限 + 工具过滤（复用现有 tools.capabilities 的语义投影）
  persistence.py      恢复：启动时从事件/投影重建内存
```

API 层只保留 `cloudra/services/api_v2.py` 一个薄文件；旧 `services/service.py`、
`runtime/workers.py`、`core/react.py` 在 S1 后被替换/删除。DAG 的确定性引擎
（`dag/models/engine/store/completion`）继续保留，由 `policies/evidence.py` 调用。

## 8. 可维护性护栏（评审后写入工程约束）

1. **OpenAPI 即契约**：FastAPI 生成的 OpenAPI 是唯一 API 文档，前端用
   openapi-typescript 生成类型；手写接口定义在评审时视为违约。
2. **每个 stage 必须无状态**（跨轮状态放 `ctx` 或 AgentSession 显式字段）。
3. **每个事件类型有 schema**，写入 `events.py` 的事件注册表；未注册事件类型在测试
   模式下报错。
4. **命令 handler 不超过一屏**：编排逻辑拆 stage，路由逻辑拆 handler。
5. **测试按层**：
   - schema 契约测试（OpenAPI 快照）
   - 每个 stage 的输入输出单测
   - TurnPipeline 用 fake LLM/fake tools 走全管道
   - AgentHost 并发/取消/重启集成测试（双项目同时跑）
   - SSE 断线重连游标测试
6. **产品红线**：SSE 单事件不超过 4 KB；大结果必须 `artifact_ref`；任何事件必须
   30 天内可查询；所有用户可见错误使用稳定 `code`。

## 9. S1 实现顺序（评审通过后）

1. `schemas.py` + OpenAPI 契约测试（先定 API，再写实现）
2. `events.py` + 事件注册表 + 持久化
3. `commands.py` + `projectors.py`：settings/spawn/cancel/restart/message 的最小闭环
4. `agent_session.py` + `turn_pipeline.py`：fake LLM/tool 跑通一轮
5. `policies/`：迁移 permission → DAG gate → evidence 现有逻辑为 stages
6. `agent_host.py`：真并发、取消回收、恢复
7. `api_v2.py`：把命令挂到路由
8. 删除 v1/TUI/Flet 的调度入口（S6 才删 UI，S1 只停用默认入口）

## 10. 待评审决策

1. `runtime_v2` 作为新包并行开发、旧模块冻结，S1 完成时切换入口——接受吗？
2. PolicyStage 四类返回 `allow/warn/block/ask` 是否足够？还是现在就需要
   `rewrite(工具参数)`（把守卫升级成可修正工具调用）？
3. 命令先 append 事件、后 apply 内存、异步落投影——接受“崩溃恢复时以事件重放为准”吗？
4. Agent 执行管道固定 10 步，stage 只能插在 before_tool / after_tool / before_llm 三个
   挂点；如果不够，未来再加挂点而不是让 stage 绕过管道。接受吗？
