# Cloudra Agent 子系统改进评审（2026-09-22）

> 文档性质：基于当前仓库代码的阶段性评审，不是已经生效的架构规范。完成相应改造后，应删除已落实条目或将文档整体保留在 `docs/archive/`，不要把它当作长期事实源。

## 1. 结论

Cloudra 的 Agent 核心已经具备较强的工程基础：运行时采用事件溯源；工具调用、上下文压缩、DAG 证据、Supervisor 裁决、取消级联和计算进程隔离都有明确边界。下一阶段最值得投入的方向，不是继续增加 Agent 数量或提示词，而是把现有体系进一步“收口”：

1. 让 Agent 间通信和批量派发完全服从统一的持久化边界，消除进程重启窗口；
2. 合并 runtime_v2 角色模型与仍在生产代码中充当类型/适配层的 legacy Agent 模型；
3. 明确子 Agent 的设置继承、完成依据和结构化交接，减少父 Agent 对自然语言回报的二次猜测；
4. 用事件流建立 Agent 行为遥测和场景级回归评测，使提示词、模型和编排修改能够量化；
5. 收紧角色权限和提示词职责边界，减少“所有专家几乎都是全权限”和同一规则多处复制的问题。

建议先做 P0/P1 收口项，再考虑新增角色、自定义规划器或更复杂的自治策略。

## 2. 本次评审范围

审查重点：

- `cloudra/runtime_v2/`：Agent 生命周期、上下文、通信、子 Agent、监督、工具协议；
- `cloudra/core/agent.py`、`cloudra/subagents/`：仍保留的旧 Agent 类型与角色注册；
- `cloudra/prompts/`、`cloudra/runtime/prompt_assembler.py`：角色提示词与动态上下文；
- `cloudra/tools/registry.py`、`cloudra/tools/capabilities.py`：工具和角色权限投影；
- `cloudra/services/telemetry.py`、`cloudra/benchmark/`：遥测与评测能力；
- 相关测试与前端设置默认值。

不在本次评审中拍板的内容：计算方法、泛函/基组、能垒定义、科学验收阈值、benchmark 权重和拒答科学红线。按照仓库约定，这些决策必须由用户确认。

## 3. 已经做得好的部分

以下能力应保留，不建议为了“换框架”而重写：

- `CommandBus` 的 decide → persist → apply → effect 顺序，已经把命令审计和副作用边界表达得很清楚；
- `ContextBroker` 在发送 LLM 请求前持久化输入，在响应后恰好一次追加输出；
- `_evaluate_completion_gate` 把显式 `stop` 与纯文本结束统一到同一结束边界；
- DAG 的完成状态由证据和阶段契约确定，不由 Agent 自述决定；
- 取消 Agent 不触碰 scheduler/guard/QM 计算，停止语义边界正确；
- 压缩采用结构化摘要、版本守卫和失败拒替换，避免无声截断上下文；
- 工具目录、角色 allowlist 和 Supervisor 能力投影已经有单一注册表的雏形。

后续改进应围绕这些不变量增量推进。

## 4. 优先级总览

| 优先级 | 改进项 | 主要收益 | 改动规模 |
| --- | --- | --- | --- |
| P0 | 修正工具协议默认值的契约漂移 | 避免用户、文档和运行时对默认行为理解相反 | 小 |
| P0 | 统一 Agent 间消息与 launch group 的持久化边界 | 避免重启窗口丢通知、丢排队项或无法查询组状态 | 中到大 |
| P1 | 向 UI/API 暴露“结束”与“验证完成”的区别 | 避免把普通 Agent 自述误显示为已验证成功 | 小到中 |
| P1 | 合并角色与 legacy Agent 的多套事实源 | 降低映射漂移、测试重复和适配层复杂度 | 大 |
| P1 | 明确子 Agent 设置继承与结构化交接 | 提高多 Agent 协作的可预测性和可审计性 | 中 |
| P1 | 按角色最小权限重做权限矩阵 | 缩小 Bash、写文件、邮件和破坏性操作的授权面 | 中 |
| P1 | 增加 Agent 行为遥测 | 让成本、失败、空转和协作质量可量化 | 中 |
| P1 | 建立场景级 Agent 回归评测 | 防止提示词/模型/协议修改通过单测却破坏真实工作流 | 中 |
| P2 | 建立提示词职责与静态检查 | 减少重复规则、陈旧工具名和上下文 token 浪费 | 中 |
| P2 | 结构化失败分类与恢复提示 | 提升故障统计、UI 表达和人工恢复效率 | 小到中 |

## 5. 详细建议

### 5.1 P0：修正 invocation protocol 默认值的契约漂移

#### 现状证据

- `cloudra/runtime_v2/schemas.py` 中 `RuntimeSettings.invocation_protocol` 默认是 `javascript`；
- `frontend/src/App.tsx` 创建 Agent 和设置面板的缺省回退也是 `javascript`；
- `tests/test_public_tool_contracts.py` 明确钉住了 JavaScript 为默认值；
- 但根 `README.md`、`README_CN.md` 和 `docs/superpowers/specs/2026-09-05-event-driven-js-runtime-design.md` 仍写着 `traditional` 默认、JavaScript opt-in。

这不是单纯措辞问题：它会直接影响用户对工具调用方式、Node.js 依赖和失败模式的判断。

#### 建议

以代码和现有测试表达的 `javascript` 默认值为当前事实，先同步 README、中文 README 和相关架构说明。若产品实际上希望回到 `traditional` 默认，应单独做一次明确决策，同时修改 schema、前端、测试和文档，不能只改其中一层。

#### 验收

- 新建项目、新建 Agent、API 返回、前端选择器、`run.started` 事件和 README 对同一默认值一致；
- 增加一个跨层契约测试，至少覆盖 `RuntimeSettings()`、项目默认值和新 Agent 的 `CurrentRun`；
- 不引入按 provider 静默回退协议的逻辑，协议不可用时继续 fail-loud。

### 5.2 P0：统一 Agent 间通信的 persist-before-deliver 边界

#### 现状证据

`EventWriter` 的设计目标是“持久化成功后才发布或执行副作用”，但部分 Agent 间通信仍直接走同步 `Mailbox.deliver()`：

- `cloudra/runtime_v2/hub_bridge.py` 的 mention/call 通知；
- `cloudra/runtime_v2/subagent_bridge.py` 的子 Agent 完成回传；
- `cloudra/runtime_v2/agent_runner.py` 的 completion gate 反馈；
- `cloudra/runtime_v2/compute_notify.py` 和 `cloudra/runtime_v2/supervision.py` 的部分通知。

`Mailbox.deliver()` 当前是“append 内存事件 → 立即入队”，没有在入队前等待 `EventWriter.flush()`。多数正常路径随后会 flush，因此日常运行通常没有问题；但在 append 与后续 flush 之间仍存在进程崩溃窗口，且该路径与 `CommandBus` 的持久化不变量不完全一致。

另一个明显缺口是 `cloudra/runtime_v2/launch_groups.py`：模块自己声明 launch group 是进程内状态。重启后未启动的 queued item、组级状态和 `get_subagent_report(group_id=...)` 查询能力都会消失。已创建的子 Agent 仍可从事件恢复，但“这一批任务原本包含什么、还有哪些未派发”无法完整恢复。

#### 建议

1. 提供唯一的异步消息提交入口，例如 `MessageDispatcher.commit_and_deliver()`：
   - 创建 `agent.message_injected`；
   - 经 `EventWriter` 持久化；
   - 成功后 enqueue；
   - 最后按状态决定是否 wake。
2. Hub post、子 Agent 完成回报、Supervisor 通知、计算通知和 completion gate 反馈全部改走该入口；不要保留“有的先落库、有的最终再 flush”的两套语义。
3. 将 launch group 的创建、item 派发、item 终态和 group 终态写成事件投影。
4. 重启时不要自动重放尚未执行的外部副作用。安全做法是恢复组清单并标记为 `interrupted`，由用户显式恢复；已经存在的 child session 只做状态对账。

#### 验收

- 在事件持久化失败时，目标 inbox 不出现消息、目标 Agent 不 wake；
- 在持久化成功但进程随即退出后，重启可以重建未消费通知；
- launch group 重启后仍能查询全部 item、child session 和中断原因；
- 恢复测试必须证明不会重复 spawn 子 Agent；
- 取消父 Agent 后，组 worker 与已派发后代仍遵守现有级联取消语义。

### 5.3 P1：区分“运行结束”与“目标已验证完成”

#### 现状证据

`AgentRunner._evaluate_completion_gate()` 在没有任何 stage 提供门禁意见时，会返回 `allow_final`，理由明确写着“agent-declared result (not independently verified)”。随后 run 被写成 `succeeded`。

这对普通问答是合理的，但 API/UI 若只展示 `succeeded`，用户很容易把“模型停止输出”理解为“科研任务已验证完成”。Cloudra 的核心定位恰恰是避免 completion by assertion，因此这里应把已经存在的完成依据显示出来。

#### 建议

不必立即新增 AgentState。优先复用现有 `agent.completion_gate` 事件，在会话摘要和前端投影中增加：

- `run_outcome`: succeeded / failed / cancelled；
- `completion_basis`: declared / dag_verified / supervisor_approved / background_wait 等；
- `verification_label`: 未独立验证 / 部分交付 / 已验证完成。

UI 中把 standard 模式的普通 `succeeded` 显示为“已结束”或“已返回结果”，只有证据门禁确认后才显示“已验证完成”。

#### 验收

- standard 无门禁的回答不会显示成“verified complete”；
- DAG 完整覆盖、部分交付批准、普通声明三者在 API 和 UI 中可区分；
- 不改变现有 DAG 完成算法和科学阈值。

### 5.4 P1：合并角色与 legacy Agent 的多套事实源

#### 现状证据

当前角色/身份至少同时存在以下表达：

- `cloudra/runtime_v2/roles.py` 的 `BUILTIN_ROLES`；
- `cloudra/subagents/registry.py` 的 `a-1`～`a-8` 注册；
- `cloudra/runtime_v2/subagent_bridge.py` 的 `_AGENT_ID_TO_ROLE`；
- 8 个 `cloudra/subagents/*.py` 子类；
- `cloudra/core/agent.py` 中仍带 LLM 调用能力的 `Agent` / `Coordinator` / `Follower`；
- launcher、swarm、skill 和多个 prompt 中重复维护的角色清单。

这使 runtime_v2 已经成为唯一执行内核后，生产代码仍需要 `_LegacyAgentBridge` 和旧类类型标注。`subagent_bridge.py`、`hub_bridge.py` 中“CLI/Flet keep using it”的注释也已经与仓库“Flet/v1 已删除”的当前约定不一致。

#### 建议

1. 以 `RoleProfile` 为实时角色唯一事实源，角色 ID 统一使用 `coordinator`、`small_mol` 等语义名；
2. 将工具真正需要的 Agent 信息抽成轻量 `ToolActorContext` 或 Protocol，只包含 `session_id`、`role_id`、`project_id`、`workspace_dir`、权限和 orchestration mode；
3. 工具不再 import 可执行的 `cloudra.core.agent.Agent`；
4. 移除 live runtime 中的 `a-N` 转换。若历史数据库读取仍需要 `a-N`，把它限制在持久化迁移/读取边界，不再作为新事件和新工具参数的首选身份；
5. 删除不再可达的旧 `llm_call` 路径和旧子类，只保留必要的数据迁移代码。

#### 验收

- 新 Agent、DAG actor、AgentHub directory 和工具上下文都从同一个 `RoleProfile`/session 身份生成；
- 新增或修改角色不需要同步三张映射表；
- `rg "from cloudra.core.agent import" cloudra` 只剩确有必要的迁移边界，最好为零；
- runtime_v2 的相关测试不再依赖 legacy `Coordinator`/`Follower` 实例造 fixture；
- 不保留“新路径失败就退回 legacy 执行”的兼容分支。

### 5.5 P1：明确子 Agent 设置继承，并提供结构化交接

#### 现状证据

`subagent_bridge._spawn_child()` 当前显式继承：

- orchestration mode；
- yolo；
- unattended；
- schedule mode；
- clean context。

但 parent 的 `invocation_protocol`、`visual_mode`、model、reasoning effort、temperature 等不会在这个入口继承；child 会重新走 project defaults → role defaults → spawn override。这个结果可能是合理的，但当前继承规则散落在桥接代码和 `AgentHost.effective_settings()` 中，派发回执也没有告诉父 Agent child 最终采用了什么。

此外，子 Agent 完成回报目前主要是自然语言：`[Sub-agent finished] role=... state=...` 加最后一条 message。父 Agent 仍需从文本中提取状态、产物和错误；swarm group 查询也主要返回计数和每项状态。

#### 建议

1. 建立一个 `resolve_child_settings()` 单一解析点，并在代码中明确字段分类：
   - 必须继承的任务授权/运行边界；
   - 应由 child role 决定的模型与领域默认值；
   - 可由派发显式覆盖的字段；
   - 禁止继承的秘密字段。
2. 派发回执返回非敏感的 effective settings 摘要，至少包括 role、model、invocation protocol、orchestration mode、unattended 和 visual mode。
3. 为完成回报增加结构化 manifest：
   - child session / role / terminal state；
   - run outcome 与 failure kind；
   - final summary；
   - 已登记 artifact 路径或 ID；
   - 未解决项和建议下一步。
4. 人类可读文本从 manifest 确定性渲染；事件/API 保留结构化数据，父 Agent 上下文只注入简洁文本和必要字段。

#### 验收

- 同一项目中 parent 单独切换 protocol/model 后，child 的最终设置行为有明确测试；
- 派发回执可以直接解释 child 为什么使用某个 protocol/model；
- child 无最终文本、child failed、child cancelled、swarm 部分失败都有稳定结构；
- 不把 API key、完整原始日志或超大工具输出塞进完成回报。

### 5.6 P1：按角色最小权限重做默认权限矩阵

#### 现状证据

`runtime_v2/roles.py` 中 researcher、small_mol、md、dft、experiment、env 默认都拥有 `write + script + destructive`。`tests/test_agents.py` 也把“除 explorer/writer 外其余全权限”作为固定预期。

与此同时，工具注册表已经能按角色隐藏化学工具，但 Bash、write/edit、email 等通用工具仍依赖粗粒度 PermissionSet 和工具内部判断。于是“领域专家”与“环境管理员”在底层权限上几乎没有区别。

#### 建议

先从现有工具的真实权限需求反推矩阵，而不是直接给六个角色全权限：

- explorer：read；
- writer：read + 限定写；
- researcher：read/search，只有确有交付文件需求时给写；
- experiment：实验/谱图工具 + 限定写，不默认获得任意脚本和破坏性权限；
- small_mol/md/dft：计算所需 write/script/submit 能力，破坏性文件操作仍单独审批；
- env：manage/script，但破坏性操作仍需明确工具风险与审批；
- coordinator：保留管理能力，但不因“统筹”自动绕过工具级安全检查。

如果现有五位布尔权限无法表达“可提交计算但不可任意删除”，应优先把风险声明放进 `ToolRegistration` 并由统一策略消费，而不是继续在各 Tool 类中各自隐藏判断。

#### 验收

- 每个角色都有“允许”和“必须拒绝”的工具/命令测试；
- researcher/experiment 默认不能通过 Bash 执行破坏性命令；
- compute 角色仍能完成现有科学工作流；
- yolo 只影响审批策略，不扩大角色原本没有的能力；
- 权限调整不改变任何科学方法和验收阈值。

### 5.7 P1：增加 Agent 行为遥测，而不只统计 token

#### 现状证据

`cloudra/services/telemetry.py` 当前主要聚合 `llm.completed` 的 token、缓存命中和 latency。事件库其实已经拥有分析 Agent 行为所需的大部分原始数据，但尚未形成面向 Agent 质量的只读指标。

#### 建议

先完全基于既有事件实现纯函数聚合，避免为了统计再给运行链路加写操作。建议指标：

- 每个 run 的总时长、LLM 请求数、turn 数、工具调用数；
- tool 成功率、业务失败率、policy block/wait 比例；
- provider retry 次数和最终失败率；
- completion gate 的 declared/continue/wait_review/allow 分布；
- 相同 gap 的 exit strike 次数；
- compaction 次数、拒替换原因、耗时、摘要 token 成本、clamped source 数；
- 子 Agent fan-out、成功/失败/取消比例、父子总 token；
- AgentHub call/post/被唤醒次数；
- compute wait、Supervisor review wait 和人工输入 wait 的时长；
- 用户在 Agent failed 后重新发消息恢复的比例。

可以新增 `cloudra stats agents` 和只读 API，前端先做表格，不必立即做复杂图表。

#### 验收

- 聚合器只读 runtime-v2.db，且核心函数可直接吃 events 列表；
- 同一事件 fixture 在 CLI/API 得到完全一致结果；
- 指标能区分主 Agent 与 summary LLM 调用；
- 不记录 API key、完整 prompt 或工具原始大结果；
- 能用一条查询定位“token 很高但没有有效工具进展”的 run。

### 5.8 P1：建立场景级 Agent 回归评测

#### 现状

仓库已有大量 runtime_v2 单元测试和化学 benchmark，但二者之间仍有一层空白：一次完整 Agent 任务是否按预期经过“读取指令 → 选择工具 → 等待/唤醒 → 提交证据 → 结束门禁”。提示词修改、默认 protocol 修改或角色权限修改，可能全部通过局部单测，却改变真实轨迹。

#### 建议

建立小型场景级 harness，使用 scripted/fake provider，不依赖真实 LLM key，也不对自然语言逐字 snapshot。断言事件和状态不变量：

1. 普通问答：纯文本结束，completion basis 为 declared；
2. small_mol：需要计算时先加载技能，再走允许的计算入口；
3. 异步子 Agent：parent 可继续工作，child 完成后恰好一次回传并唤醒；
4. provider 暂态错误：按预算重试，永久 4xx 立即失败；
5. context overflow：最多一次 overflow 压缩，成功后继续原任务；
6. unattended：不能进入 waiting_input；
7. dag_guided：证据不足不能成功结束，Supervisor 裁决后正确恢复；
8. 重启：不重复工具副作用，不重复 spawn，不丢已持久化未消费消息。

另设可选的真实模型行为评测，用于比较 prompt/model/protocol 版本，但不进入要求 API key 的普通 CI。它应记录模型版本、prompt revision、tool catalog revision 和随机性参数，结果只做趋势分析。任何科学评分阈值仍需用户确认。

#### 验收

- 测试断言事件序列和结构化结果，不断言模型措辞；
- 每个已修复的 Agent 级故障都有对应场景；
- 修改 prompt、角色权限或 protocol 默认值时能明确看到影响了哪些场景；
- 默认本地测试仍按改动子系统聚焦运行，不新增强制真实 LLM 测试。

### 5.9 P2：建立提示词职责边界和静态检查

#### 现状证据

同一信息目前可能同时存在于：角色 prompt、工具 description、`PromptAssembler` 动态 guidance、skill、launcher/swarm 描述和 AGENTS.md。例如角色 roster 和 `a-N` 映射至少在 registry、两个派发工具、subagent-prompting skill 中重复。

`PromptAssembler` 还维护 `_OUTPUT_ONLY_ROLES` 这样的第二角色分类；该分类没有从 `RoleProfile` 推导。随着角色变更，提示词和运行时权限可能发生漂移。

#### 建议

明确内容归属：

- runtime/policy stage：不可违反的运行不变量；
- tool schema/description：参数、结果、失败语义和工具局部流程；
- role prompt：角色使命、交付格式、领域边界；
- skill：可按需加载的长 SOP；
- AGENTS.md：仓库级开发与用户指令；
- launcher/swarm：只描述派发协议，不复制完整角色手册。

增加一个无正则的静态检查脚本：

- prompt 中引用的工具名必须存在；
- 角色 prompt 引用的工具必须对该角色可见；
- role roster 从 `RoleProfile` 生成，不手写多份；
- 检查 README/default setting 与 schema 的关键枚举/默认值；
- 输出每个 prompt source 的 token 数，结合 telemetry 决定是否精简。

不要为了省 token 把确定性安全规则从 policy stage 移回 prompt；优先删除重复说明，而不是删除执行层护栏。

#### 验收

- 新增角色或改工具名时，静态检查能指出所有失效引用；
- launcher、swarm、skill 不再各自维护 `a-1`～`a-8` 表；
- prompt revision 变化仍可被现有上下文缓存机制正确感知；
- 压缩前缀和动态 snapshot 的职责保持不变。

### 5.10 P2：为 run 失败增加结构化分类

#### 现状证据

`run.finished` 目前主要记录 `outcome` 和自由文本 `error`。Provider 失败、事件持久化失败、completion gate 无进展耗尽、进程重启中断等都会落到 `failed`，后续只能解析字符串才能统计或给出恢复建议。

#### 建议

在不改变 `AgentState` 的前提下，为 `run.finished` 增加有限枚举 `failure_kind`，例如：

- `provider_transient_exhausted`；
- `provider_permanent`；
- `event_persistence`；
- `pipeline_internal`；
- `completion_no_progress`；
- `runtime_interrupted`；
- `policy_terminal`。

保留 `error` 供人阅读，但 UI、遥测和恢复提示只按枚举分流。异常到分类的转换放在一个函数中，不允许各调用点自行拼字符串判定。

#### 验收

- 所有 failed run 都有 failure kind；
- 重启中断不再和科学/任务失败混在同一统计桶；
- UI 能针对 provider 配置、持久化故障、无进展退出给出不同的下一步；
- 不通过正则解析异常或 Agent 文本。

## 6. 推荐实施顺序

### 阶段 A：先消除认知和观测盲区

1. 同步 invocation protocol 默认值文档；
2. 暴露 completion basis；
3. 增加 failure kind；
4. 增加只读 Agent 行为遥测。

这一步改动较小，却能为后续改造提供基线数据。

### 阶段 B：收口多 Agent 协作契约

1. 统一 child settings 解析；
2. 结构化 child completion manifest；
3. 所有消息改为 persist-before-deliver；
4. launch group 事件化并补重启测试。

### 阶段 C：删除双栈与重复事实源

1. 引入轻量 ToolActorContext；
2. 工具脱离 `cloudra.core.agent.Agent`；
3. 合并角色注册和 prompt 元数据；
4. 删除 live runtime 中的 `a-N` 与旧 llm_call 路径；
5. 收紧默认权限矩阵。

### 阶段 D：建立持续评测

1. 增加场景级 fake-provider harness；
2. 建立可选真实模型行为评测；
3. 用 telemetry + benchmark 结果迭代 prompt，而不是凭主观感觉继续堆规则。

## 7. 不建议做的事情

- 不建议再引入一套第三方 Agent framework 包住 runtime_v2；当前问题是事实源和边界尚未完全收口，不是缺少框架。
- 不建议让 LLM Supervisor 直接修改 DAG 或替代确定性证据门禁。
- 不建议进程重启后自动重放未确认的工具调用、JS 程序或子 Agent spawn。
- 不建议新增“万能规划器”“自动反思层”或更多角色，除非行为遥测先证明现有角色存在稳定缺口。
- 不建议用更长 prompt 修复本可由 policy、schema 或状态机确定性解决的问题。
- 不建议把 Agent `succeeded` 当作科研结论正确率指标；科研质量仍应读 DAG/benchmark 交付物。

## 8. 建议首个改动批次

若只选择一个低风险批次，建议包含：

1. README/README_CN 改成 JavaScript 为当前默认协议；
2. API/UI 显示 completion basis；
3. `run.finished` 增加 failure kind；
4. 新增 `cloudra stats agents` 的纯事件聚合；
5. 为上述四项补聚焦测试。

这个批次不改科学逻辑、不改计算执行、不改 DAG 验收标准，却能立刻减少误解，并为后续多 Agent 可靠性改造提供数据。
