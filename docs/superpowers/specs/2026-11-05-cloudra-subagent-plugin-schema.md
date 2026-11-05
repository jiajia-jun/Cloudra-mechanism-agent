# Cloudra Subagent 插件：MCP schema 草案

首版实现覆盖 list_projects、start_task、send_message、answer_question、get_progress、get_agent_progress、get_result 和结果附带的 MCP 资源。本文其余工具保留为后续接口设计。

Codex 或 Claude Code 可以新发起一项化学研究，也可以接手 Cloudra 已有会话；通过同一组工具派活、判断阻塞、回答提问并取回交付证据。Cloudra 继续自己运行 Agent、调度计算和做科学审查。

两种接法：逐一暴露 Web API，或者按外部 Agent 的工作流组织工具。采用后者：常用的派单、看进度、答问题、取结果无需调用者自己拼表；队列、DAG、Hub 和调用记录按需展开。MCP 接到已有 Cloudra 服务，服务端与 Web 共用命令、状态投影和科学判定。

## 通用约定

- `project_id: string` 是 Cloudra 界面的一条会话（项目）；`session_id: string` 是一个具体 Agent 的持久会话。同角色可有多个实例，发消息和停止时传实例 ID。
- 新委托使用「项目 + Coordinator 的 `session_id`」恢复；后台计算结束唤醒时仍使用原标识。调用者无需填写运行轮次、版本、摘要、幂等键。
- 以下用类型签名表示 JSON schema：`?` 为可省略，`null` 为事实未知或没有该值，`[]` 为确定没有记录。时间为 RFC 3339。文本去掉首尾空白后不得为空。输入拒绝未知字段。
- 首版服务单个可信 Cloudra 操作者，沿用安装级 API 凭据，不做多租户授权。各工具仍校验记录确实属于指定项目。调用者身份记为外部操作者，不冒用 Cloudra Agent。
- 单目标错误使用 MCP 工具错误并返回 `ErrorInfo`；批量发送逐个报告。写调用响应丢失时先查项目或进度，插件不自动重发。相同文本可以是两项独立委托。

## 委托与消息

```ts
type ProjectRef = { project_id: string; name: string; created_at: Time };
type TaskRef = { project_id: string; session_id: string };
type ErrorInfo = {
  code: "invalid_request" | "not_found" | "forbidden" | "state_conflict" | "unavailable";
  message: string;
  project_id?: string;       // start_task 已建项目但未能启动 Coordinator 时返回
};

declare function list_projects(): { projects: ProjectRef[] };

declare function start_task(input: { task: string } & (
  | { name: string; workspace_dir?: string }  // 新项目；默认分配工作目录
  | { project_id: string }                    // 继续使用尚无 Coordinator 的项目
)): TaskRef;

declare function send_message(input: {
  project_id: string;
  recipients: string[];    // 非空，填具体 session_id
  content: string;
}): {
  deliveries: (
    | { session_id: string; message_event_id: string }
    | { session_id: string; error: ErrorInfo }
  )[];
};

declare function answer_question(input: {
  project_id: string;
  interaction_id: string;  // 取自 get_progress().pending
  response: string;
}): { accepted: true };

declare function cancel_agent(input: { project_id: string; session_id: string }): {
  session_id: string;
  state: "cancelled";
};
```

- `list_projects` 只列授权且未归档的会话。接手路径为 `list_projects → get_progress → send_message`，不必重启 Coordinator。
- `start_task` 复用项目创建和带首条消息的 Coordinator 启动两步。已知启动失败时返回已创建的 `project_id`，修正后可用它继续。同一项目已有 Coordinator 时，拒绝重复启动，改用 `send_message`。响应丢失时按项目名称、创建时间与当前 Agent 核对；若仍无法确认，先由操作者确认，不自动创建第二项任务。
- 本机可传操作者明确指定的独立工作目录，在任务中用相对路径引用其中已有的 XYZ、输入文件和日志。远程连接使用 Cloudra 分配的工作目录；跨主机导入文件另做。
- 回执确认消息已持久化入信箱。重复收件人只投递一次；部分收件人失败不影响其他人。发送给已结束的 Agent 可以重新开启工作，此时不能把旧交付当作本次回复。
- `answer_question` 只回答 Cloudra 登记的用户提问。化学方法、阈值等科学决策只转达用户确认的答复。工具审批由用户在 Cloudra 现有入口决定；Supervisor 审查由 Cloudra 处理。两种等待均对外可见。
- `cancel_agent` 沿用现有 Agent 取消语义（含其子 Agent）。已终止且不可取消时返回 `state_conflict`。取消计算作业走独立入口。

## 进度、消息与结果

```ts
type Time = string;
type AgentActivity =
  | "queued" | "running" | "waiting_background" | "waiting_input"
  | "waiting_approval" | "waiting_review" | "idle" | "failed" | "cancelled";
type Excerpt = { text: string; truncated: boolean };

type AgentProgress = {
  session_id: string;
  name: string;
  role_id: string;
  parent_session_id: string | null;
  activity: AgentActivity;
  detail: string | null;           // 已记录的当前工作或等待原因
  updated_at: Time;
  active_job_ids: number[];
};
type Pending =
  | { kind: "question"; session_id: string; interaction_id: string; prompt: string }
  | { kind: "approval"; session_id: string; approval_id: string; summary: string }
  | { kind: "review"; session_id: string; summary: string };

declare function get_progress(input: {
  project_id: string;
  include_process?: boolean;       // 默认 true
}): {
  project_id: string;
  observed_at: Time;
  agents: AgentProgress[];
  pending: Pending[];
  process: (Excerpt & { updated_at: Time }) | null;
};

type ContextKind = "assistant" | "incoming" | "tool" | "error" | "reasoning";
type ContextItem = Excerpt & {
  event_id: string;
  kind: ContextKind;
  at: Time;
  tool_name: string | null;
  status: CallStatus | null;
};

declare function get_agent_progress(input: {
  project_id: string;
  session_id: string;
  limit?: number;                   // 整数 1–50，默认 1
  filter?: string;                  // JavaScript 布尔表达式；变量名为 entry，最长 4,000 字符
  include_reasoning?: boolean;      // 默认 false
}): {
  agent: AgentProgress;
  pending: Pending[];
  messages: ContextItem[];
  history_truncated: boolean;
};

type ArtifactRef = {
  artifact_id: string;
  name: string;
  mime_type: string;
  size: number;                     // 字节
  uri: string;                      // 供 MCP resources/read 使用，不含凭据
};
type VerificationLabel =
  | "verified" | "supervisor_reviewed" | "partial" | "scope_completed" | "unverified";
type Outcome = {
  terminal_event_id: string;
  run_outcome: "succeeded" | "failed" | "cancelled";
  summary: string | null;
  verification_label: VerificationLabel;
  completion_basis: string | null;
  unresolved: string[];
  artifacts: ArtifactRef[];
};

declare function get_result(input: {
  project_id: string;
  session_id: string;               // 新委托使用 start_task 返回的 Coordinator ID
  wait_seconds?: number;            // 整数 0–20，默认 0
}): (
  | { status: "pending"; agent: AgentProgress; pending: Pending[] }
  | { status: "finished"; result: Outcome }
);
```

- 会话进度读取 Cloudra 的运行事实，再附项目根目录 `PROCESS.md` 的开头（最多 8,000 字符）。未写笔记或请求省略时 `process=null`。状态、笔记和本次观察各标自己的时间。
- 单 Agent 不传 `filter` 时只取已持久化的公开输出，默认一条；若显式启用 `include_reasoning`，同时纳入已记录的 reasoning。传 `filter` 时也纳入来信、工具和错误记录。工具记录使用同一份调用回执的摘要和状态；非工具记录的 `tool_name/status` 为 null。
- `filter` 可由调用者现场编写，每条候选记录以 `entry: ContextItem` 传入。先过滤，再取最近 `limit` 条，按从旧到新返回。表达式看到的是限长后的公开投影（每条最多 2,000 字符），只看该 Agent；未启用 reasoning 时，表达式也看不到它。筛选最多检查最近 500 条候选记录；如果达到扫描上限且还有历史未检查，`history_truncated=true`。
- 过滤表达式使用现有 QuickJS 沙盒和 500 毫秒的累计执行预算，单独用无工具桥接的上下文，仅注入 `entry`，不开放网络、文件或数据库。语法错误、结果不是布尔值或执行超限，明确报 `invalid_request`。无过滤时不启动 JS。
- 结果可短等。目标 Agent 真正终止、它或其子 Agent 有待处理的提问或审批、超时，满足任一项就返回；断连不取消委托。`waiting_background` 仍是 `pending`。新指令重新开启工作后，当前结果再次变为 `pending`。首版只查当前交付；先前返回的产物 ID 仍可独立读取。
- `summary` 来自对应终态的结论，缺失时为 `null`。科学验证沿用 Cloudra 的完成依据。已有机理图或计算 `done` 不自动推出 `verified`。已有未解决项原样传出。
- 首版通过短等收结果。需要逐条监控进度时复用已有持久事件游标，暂不加事件订阅工具。

取最近三次失败调用：

```json
{
  "project_id": "prj_example",
  "session_id": "sess_example",
  "limit": 3,
  "filter": "entry.kind === 'tool' && entry.status === 'failed'"
}
```

[当前运行结束分支](../../../cloudra/runtime_v2/agent_runner.py#L780-L785)：

```python
final_answer = gate.final_answer if gate.final_answer is not None else candidate_answer
if gate.action == "allow_final" and final_answer:
    self._emit_run_message(agent, run_id, final_answer)
elif gate.action == "wait_background":
    self._emit_run_message(agent, run_id, gate.reason or "Run paused awaiting background work.")
await core.agent_host.finish_run(agent, outcome="succeeded")
```

真正交付和让出执行权等待后台都可能写入 `succeeded`。实现复用[后台等待判定](../../../cloudra/runtime_v2/agent_host.py#L203-L217)、[子 Agent 终态报告](../../../cloudra/runtime_v2/child_manifest.py#L132-L192)与[完成依据](../../../cloudra/runtime_v2/completion.py#L19-L37)，同一含义由现有运行时定义。

## 计算、DAG 与产物

```ts
type ComputeState = "ready" | "running" | "cancel_requested" | "done" | "failed" | "cancelled";
type ComputeJob = {
  job_id: number;
  project_id: string;
  session_id: string | null;
  job_type: string | null;
  state: ComputeState;
  node_id: string | null;
  scheduler: string | null;
  scheduler_job_id: string | null;
  guard_pid: number | null;
  calc_pid: number | null;
  last_error: string | null;
};

declare function list_compute_jobs(input: (
  | { project_id: string; scope?: "project"; active_only?: boolean }
  | { scope: "global"; active_only?: boolean }
)): { jobs: ComputeJob[] };

declare function cancel_compute_job(input: {
  project_id: string;
  job_id: number;                   // 正整数
  reason: string;
}): { job_id: number; state: ComputeState };

type DagIssue = {
  code: string;
  target_type: "graph" | "node" | "edge";
  target_id: string;
  detail: string;
};
type DagView = {
  mode: "standard" | "dag_record" | "dag_guided";
  graph: {
    nodes: { node_id: string; label: string; evidence_level: string }[];
    edges: {
      edge_id: string;
      source_node_id: string;
      target_node_id: string;
      label: string;
      evidence_level: string;
    }[];
  } | null;
  report: { complete: boolean; unresolved: DagIssue[]; inconclusive: DagIssue[]; waived: DagIssue[] } | null;
  graph_artifact: ArtifactRef | null;
};

declare function get_dag(input: { project_id: string }): DagView;

declare function list_artifacts(input: { project_id: string; session_id?: string }): {
  artifacts: ArtifactRef[];
};

declare function read_artifact(input: { project_id: string; artifact_id: string; start_line?: number }): {
  text: string;
  next_line: number | null;
  truncated_line: boolean;
};
```

- 默认 `active_only=true`，活跃包含等待、运行、待取消；false 取最近 100 条含终态。全局必须显式选 `scope="global"`，只在本机操作者连接上启用。PID 是节点上曾记录的值，可能为空或过期；操作按作业 ID。`cancel_requested` 表示执行端尚未确认退出。
- DAG 读现有交付视图，缺图时不初始化。Standard 的 `graph/report` 为 null，已有根目录交付图则返回 `graph_artifact`。DAG 模式的图按节点和边索引，完整的机理图按交付文件取。报告复用现有未满足项和审查结果。
- 正式交付时使用现有 artifact registry 固定交付引用中的文件版本，并把 ID 绑定到对应终态。读取结果时不从工作区重新登记旧证据；旧会话没有绑定版本的产物不补造。首版固定已提交 DAG 交付报告的图快照。Standard 图、量化原始日志与后续的独立 DAG 查询另行接入。已绑定的产物可通过 MCP 资源取回。
- `read_artifact` 为文本和量化日志的分页入口，`start_line` 从 1 开始，默认 1，每页最多 12,000 字符。超长单行截断时 `truncated_line=true`，原件或二进制用 URI 读取。资源同样检查项目授权，URI 不指向服务器绝对路径。

## AgentHub 与调用诊断

```ts
type HubPost = {
  post_id: string;
  topic: string;
  content: string;
  kind: "finding" | "question" | "answer" | "broadcast" | "message";
  author: string;
  parent_id: string | null;
  at: Time;
};

type CallStatus = "queued" | "running" | "waiting" | "blocked" | "completed"
  | "failed" | "cancelled" | "interrupted" | "unknown";

declare function hub_read(input: {
  project_id: string;
  topic?: string;
  keyword?: string;
  limit?: number;                  // 整数 1–50，默认 20
}): { posts: HubPost[] };

declare function hub_post(input: {
  project_id: string;
  topic: string;
  content: string;
  kind?: HubPost["kind"];          // 默认 finding
  to_session_id?: string;          // kind=message 时必填
  parent_id?: string;              // 回帖；同一项目及主题
}): { post_id: string };

type ToolCall = {
  request_event_id: string;
  session_id: string;
  tool_name: string;
  status: CallStatus;
  duration_ms: number | null;
  summary: string | null;
  compute_job_ids: number[];
  artifact_ids: string[];
};

declare function tool_stats(input: { project_id: string; session_id?: string }): {
  by_tool: { tool_name: string; counts: Partial<Record<CallStatus, number>> }[];
};

declare function list_tool_calls(input: {
  project_id: string;
  session_id?: string;
  status?: CallStatus;
  limit?: number;                  // 整数 1–100，默认 20
  cursor?: string;                 // 原样回传上次的 next_cursor
}): { items: ToolCall[]; next_cursor: string | null };

declare function get_tool_call(input: { project_id: string; request_event_id: string }): ToolCall & {
  arguments: Record<string, unknown> | null;
  result: unknown;
  error: string | null;
};
```

- Hub 无筛选时看近期帖；`topic` 定位主题，`keyword` 复用内置搜索。外部发帖以外部调用者身份记录；点名仍然是公开帖。目录已由 `get_progress` 提供。原生 Hub 的 `call` 依赖一个 Cloudra 内部发起者；外部派活走 `start_task` 或 `send_message`。
- 调用记录按实际尝试计数，范围是该会话或 Agent 的已保留历史。统计、列表和详情使用同一批调用回执；先过滤再分页。工具提交作业成功，不代表作业执行成功。详情只返回持久化且允许展示的内容；缺失则为 null。

## Codex 插件

采用本地或仓库 marketplace。插件名 `cloudra-subagent`，首版以 stdio 启动 Cloudra 提供的适配命令，适配器连已运行的 Cloudra API。服务未运行就明确报错。插件不会启动第二个运行实例、不读取数据库，退出也不影响计算。地址和凭据从 Cloudra 本机配置获取；远程连接由操作者配置，不写入 manifest。Claude Code 可连同一个 MCP 入口。

计划放在 `plugins/cloudra-subagent/`。[便携插件格式](https://developers.openai.com/plugins/build/plugins)的根目录 `plugin.json` 草案：

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "cloudra-subagent",
  "version": "0.1.0",
  "description": "Delegate chemical mechanism research to a running Cloudra instance."
}
```

根目录 `mcp.json`（`cloudra mcp` 为拟新增命令，依赖已安装 Cloudra）：

```json
{
  "mcpServers": {
    "cloudra": {
      "type": "stdio",
      "command": "cloudra",
      "args": ["mcp"]
    }
  }
}
```

附一个 `skills/delegate-research/SKILL.md`：如何选已有会话或派新任务，先看阻塞再决定是否问人，最后提交结论与证据。参数和状态语义以 MCP 定义为准。首版不做 UI、hooks 或公开发布。

## 验收

- 已有会话：列项目、定位两个同角色 Agent、群发、看各自回执，无须查询数据库。
- 单 Agent：过滤先于条数截断；不显式开启 reasoning 时过滤器也读不到；报错和越权调用不能读文件、调工具或改变 Agent 状态。
- 新研究：派单、收到并回答提问。等计算期间不误报完成，插件断线后仍能查。
- 交付：Standard 图文件和 DAG 审查结果有明确区别；可取回正式图和原始日志。部分交付列出已有未解决项。
- 停止 Agent 不改写计算账本；单作业取消显示待确认。队列与调用记录保留各自状态。
- 用同一组行为用例验证直接调用 Cloudra 服务和经插件调用。使用脚本化 Agent 及已有作业记录，无须真实量化计算。
