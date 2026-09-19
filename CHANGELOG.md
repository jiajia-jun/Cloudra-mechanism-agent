# Changelog

## [Unreleased]

### 变更
- `flower.enabled` 默认开：mechanism_predict（FlowER 机理假设生成）对模型默认可见，未装环境时调用层 fail-loud 引导 `scripts/setup_flower.sh`；显式置 false 才回退 wire 隐藏 + 执行层硬失败。
- 工具面收敛：`role_allowlist` 工具级角色门槛（registry 声明使用者，wire 投影隐藏 + PermissionStage 硬拦两道防线；化学/QM 工具限 coordinator/small_mol/md/dft/experiment，ir/nmr_processor 为 experiment 专属）；裁撤冗余工具 `web_fetch`（能力由 `browser` 静态回退覆盖）与 `todo_read`（todo 提醒改为内联清单，`todo_write` 每次调用回显全量）；email 工具与收件监听器加总开关 `email.enabled`（默认关，config_gate 隐藏 + 执行层硬失败 + 监听器不启动）。
- 上线前可靠性大重构（beta 不留兼容）：计算执行面三进程拓扑定型——Web 控制面（api_v2）、计算调度守护进程（`cloudra scheduler`，flock 单实例，web 启动时自动 detach 拉起）、知识向量服务（chem-kb 插件安装后自动拉起，`CLOUDRA_KG_VEC=off` 关闭）；进程间状态同步只走 SQLite（WAL）与文件锁。执行面铁律固化：永不 kill 计算进程、存活判定只用 flock 探测、核心链路零输入文件解析（资源量由 agent 提交时显式申请）。
- runtime_v2 函数式内核化：CommandBus 四拍（纯 decider → append+publish+persist → 唯一无守卫 `apply_event` → effect 执行），恢复重放与在线路径共用同一应用器（`test_runtime_v2_replay_equivalence.py` 门禁常驻）；快照降级为节流缓存，按每项目高水位线增量重放（修复旧 seq 高水位在多项目交错下丢事件）；重启恢复时孤儿审批/提问显式落 `approval.expired`/`interaction.expired`；compact 请求走 `compaction.requested` 事件；状态外化契约（事件可推导 vs 刻意易失）固化进各模块 docstring。
- config 子系统重做：磁盘 YAML 是唯一事实源，唯一写入口 `mutate_config(fn)`（flock 排他 + 读磁盘 → 应用 → 原子写回 → 刷新单例），序列化由 `model_dump` 派生；`save()`/`reload_config()`/plugins 磁盘合并 hack 删除；新增 `add_plugin`/`remove_plugin` 与 `cloudra knowledge uninstall`/`status`。
- `compute_jobs` 迁中央 `data_dir/compute.db`（`ComputeDB` + `services/compute_store.py`），调度守护单库认领；会话库六张 legacy 死表（subagent_requests/approvals/scheduled_reminders/client_commands/interactions/hub_posts）及读写函数删除；进程内 IPC 事件总线删除，compute 完成通知改纯 DB 细粒度轮询（`ComputeNotifyBroker`），API 宕机窗口不再丢通知。
- 统一日志基建 `infra/logging_setup.py`：api_v2 落 `logs/api.log`，scheduler/kg_vec 经 stream 走各自重定向日志，logger 名全部归一化到 `cloudra.*` 树；`CLOUDRA_LOG_LEVEL` 控级别。
- 上帝文件拆分：`dag/controller.py`（1384 行）拆为门面 + supervision/evidence_inbox/stop_audit/drafts 四个 mixin（公开签名与 `_SUPERVISION_STATES` 类级共享语义不变）；`services/api_v2.py`（1105 行）拆为 `api_v2/` 包（app/context/models/sse + 九组 routers，`ApiContext` 显式注入、路由零闭包，create_v2_app 签名与路由表逐字节不变）。
- calculator 进程 nice +10 降权（`monitor.py` preexec_fn），保控制面调度份额；知识向量服务解释器可由 config `knowledge_vec_python` 指定（缺省探测仓库根 `.venv-trans`）；语义检索通道异常不再静默（warning + `last_health`），新增 `GET /api/v2/knowledge/health` 三通道健康聚合与前端 KnowledgePanel 健康状态条。
- 运行时环境定位 POSIX-only（flock/nice 依赖 fcntl 与 POSIX 语义），README 声明并撤下 Windows 安装指引。

### 修复
- config 并发写丢键：旧 `save()` 用内存快照整文件重写 YAML，运行中服务会抹掉并发写入（如 `knowledge install` 的 plugins）；且 plugins 条目无法经 save 移除。改 `mutate_config` 后结构性消灭。
- 重启后 pending 投影孤儿（审批/提问）无声消失，agent 唤醒看不到终态；现显式落过期事件。
- 快照恢复在多项目交错写入下按全局 seq 高水位过滤会丢事件；改每项目 `last_seqs` + ORDER BY rowid 增量重放。
- 计算完成通知依赖进程内 IPC 总线，API 进程重启即丢；改纯 DB 轮询投递。

### 新增
- 聊天记录分页回看：转录顶部新增「Load earlier」气泡，点击经 `eventsPage`（`before` 游标 + `tail`）向前翻一页 500 条更早事件，滚动位置保持不跳，可连续点击直到翻完；翻到头显示「beginning of history」结束标记。更早分页独立于实时 SSE 窗口存储，不被 `EVENTS_WINDOW` 裁剪。
- `cdxml_to_graph` 工具：基于 molli + RDKit 解析 ChemDraw CDXML 反应路线，生成节点为 isomeric SMILES 的候选机理图；多反应物/产物合并为反应物/产物络合物，支持 DAG 检测与 `dag_propose_mechanism` 提案生成，边信息携带溶剂/条件/试剂供计算参考，可选落盘 mol2。
- runtime_v2 原生提醒唤醒：`reminders.py` 拦截 `schedule` 工具，提醒落 `reminder.scheduled` / `reminder.cancelled` / `reminder.fired`（`schedule_id` 为事件 seq）；到点经 `agent.message` 投递 `[Reminder]` 并自动 reopen 终态 agent。进程启动 `rearm_all()` 从事件投影重建，过期立即触发——修复 v2 下 `schedule` 无人触发、挂起 agent 永睡的停摆。
- `NoticeManager`（`notices.py`）：统一上下文注入。`pin`/`unpin` 按键幂等的常驻注入（goal 钉、DAG 投影），`push` 一次性注入（交付 delta、唤醒附言）；`turn_pipeline` 拼消息时 `collect`（pins 在前，push 耗尽）。
- DAG 工具族：删除未发布的 `dag_graph` 单工具，拆成平铺字段的 `dag_*` verb（`dag_view` / `dag_init_from_template` / `dag_add_species` / `dag_add_step` / `dag_update_delivery_element` / `dag_schedule_work` / `dag_update_process_node` / `dag_remove_edge` / `dag_bind_evidence` / `dag_review_evidence` / `dag_set_coverage_contract` / `dag_message_supervisor` / `dag_delivery_report`）。引擎、分权、变更日志与原子批次不变；督导循环按工具名调度，不再嗅探 `action`。
- 交付即时反馈：`DagController.on_tool_finished` 返回 `DeliveryDelta`；`dag_stage` 把 `[DAG] evidence bound: …` 追加进当轮 tool result，并 `notices.push` 保证跨 run 可见。
- runtime_v2 为唯一运行时：Electron 前端流式输出（LLM token delta 经 `llm.chunk` 直发 SSE，不落事件日志）、thinking 分段折叠（绿标）与工具行（黄标）、Markdown + KaTeX 渲染。
- 前端 DAG 面板：双图真图渲染（dagre+SVG）、节点选中查看/编辑字段（不暴露 JSON）、覆盖率报告、mutation 历史、supervisor replan。
- 前端命令继承：`/goal`（目标锚点）、`/compact`（上下文压缩）、context 统计、skills 列表；审批与 ask_user 交互面板。
- 子 agent 派发 v2 原生化：`subagent_bridge.py`（SubAgentLauncher/SubAgentSwarm/get_subagent_report 经 CommandBus spawn，支持 is_wait 与父取消级联）；`hub_bridge.py`（agent_hub 论坛落 `hub.posted` 事件，通知/呼叫走 Mailbox）；审批/交互由 `pending.py` 内核 broker 承担（事件 + future，决策经 `approval.decide`/`interaction.respond` 命令）。
- 失败自动恢复：turn 崩溃原地重试（保留 history，`run.retry` 事件，默认 5 次退避，2s→30s 递增）；对 failed/cancelled 的 agent 发消息自动 reopen 新 run，前端不再暴露手动 Restart。
- 交付门禁移植到 v2：dag 模式下 `stop(delivery_disposition="complete")` 需通过交付覆盖率审计（`dag_stage` 拦截，复用 `DagController.audit_stop`），有未终态兄弟 agent 时 stop 视为挂起不审计。
- DAG 视图消歧：observed 节点新增 `arguments_summary`（路径参数优先），process 视图（`include_observed=true`）暴露 `tool_call_id`/`arguments_hash`/`arguments_summary`，Coordinator 可在多个同工具 observed 节点间辨认后走 `observed_<hex>` 别名 `bind_evidence`；dag_record/guided 投影提示同步更新。
- 多候选认领在执行者一侧消解：同工具多个计划候选时，`assignee` 恰为当前 agent 的唯一节点被直接认领（不再一律落 observed 留给 Coordinator）；顺带修复 v2 的 role_id 与 DAG 图 legacy assignee 词表（a-0..a-8）的映射缺口——此前子 agent 的 assigned_to_me 投影在 v2 下恒为空。
- Supervisor 活动前端可见：dag_guided 下每次督导触发经 `DagController.on_supervision` 钩子投影成一个复用的壳 agent 会话（角色 `supervisor`，挂在触发者名下，不走 LLM 管线），运行时 AgentBar 显示 running，结束落摘要消息——督导期间界面不再像卡死。
- 工作区按项目隔离，项目栏按工作区划分。
- 子 Agent 按领域重命名：explorer（探索+审查）、writer（论文写作）、researcher（文献）、small_mol（小分子量化）、md（分子动力学）、dft（第一性原理）、experiment（实验设计）、env（环境管理），替换掉 visionary/operator/coder。explorer 只读，writer 读写，其余全权限，危险操作统一走审批。
- 计算类 prompt 方法论：教 SOP 和翻车直觉而不是知识清单，起手先 `getskill` 加载对应 skill。
- AgentHub：加 `hub_posts` 表（schema v6）和 `agent_hub` 工具（post/browse/read/search，支持问答串），并行子 Agent 可共享 SQLite 发帖，只读 Agent 也能发。
- 通用网页搜索：加 `web_search` 工具，Tavily/Brave（需 key）→ Bing/DuckDuckGo（免 key）自动 fallback，和 `web_fetcher` 两段式用。
- 规划工具：加 `todo_write`（多步清单，同一时刻只能有一个 in_progress）和 `goal_set`（目标锚点，压缩后仍钉在上下文里）。
- Textual 全屏 TUI：`cloudra/tui/` 重写成全屏应用，支持对话消息渲染、会话切换、主/子 Agent 上下文分屏、绿/黄主题。
- harness 加固：`context_window`/`timeout` 进配置（不再硬编码）；工具参数校验失败会反馈给 LLM；传输层加超时和状态事件；`bashtools` 返回 `exit_code` 且截断超长首尾输出；主循环死循环检测；上下文压缩概要持久化。
- 模型原生联网搜索：`LLMConfig.native_search`（默认 `auto`）+ `native_search_params`。按 base_url/model 自动识别适配器（openai 搜索模型 / openrouter `web` 插件 / deepseek / gemini / custom），启用后在请求里注入服务商侧搜索工具、剔除外部 `web_search` 函数工具，避免双重搜索；结果以内联引用返回。状态栏显示「联网·<provider>」，聊天区把 `web_search_call` 事件并入「思考过程」。
- DeepSeek 原生搜索走 Responses API：新增 `LLMClient.create_responses`（POST `/responses`），把 chat.completions 风格的 kwargs/响应翻译成 Responses 形状（含流式 SSE 与 tool_call 增量合并），reAct 层零改动；base_url 尾部 `/v1` 自动兼容。
- 联网搜索引导：有搜索能力（原生或 `web_search` 工具）时，在 system prompt 注入「联网搜索（重要）」段落，要求任务依赖实时/外部信息时先搜再答。
- `todo_read` 工具：与 `todo_write`/`goal_set` 配对，随时读取当前任务清单与目标锚点；每 10 轮或 supervisor 反对时注入提醒，让 todo 真正驱动每轮行为。
- 目标严格模式与 `/goal` 命令：TUI 新增 `/goal <目标>`（设置目标锚点并固定到 Coordinator 上下文）、`/goal pause`（暂停当前任务）、`/goal`（查看）。设置目标后任务只有调用 `stop` 才能结束，无工具轮会注入「确认 goal 是否完成」提醒；未设目标时保持传统语义（有正文即完成）。
- 移除 `MAX_STEPS` 步数上限：循环结束由 `stop`/取消/死循环检测决定，不再有硬性步数天花板。
- `submit_compute_job` 支持 CP2K：新增 `cp2k` job_type（`calculator.sh` 分支、PATH 检查、`.out` 日志路径），guard 用轻量文本解析 CP2K 输出（cclib 已移除 CP2K 解析器）；顺带修复 guard 未透传 job_type 导致非 Gaussian 日志路径错配的问题。
- OpenAlex API key：配置项 `openalex_api_key`（`cloudra config set` / `config.yaml` / `CLOUDRA_OPENALEX_API_KEY` / `OPENALEX_API_KEY`）；`openalex_searcher` 有 key 则带上，没有则匿名降级。礼貌池邮箱 `openalex_mailto`（`CLOUDRA_OPENALEX_MAILTO` / `OPENALEX_MAILTO`）写入 User-Agent；未设置则只用通用 UA。

### 变更
- `chemrxiv_searcher` 改名叫 `openalex_searcher`，它其实一直检索整个 OpenAlex，没过滤过 ChemRxiv；Android 工具白名单和文档同步更新。
- 所有工具描述统一成“功能/适用/不适用/关键纪律”结构，把搜索、PDF、文件修改、计算流水线之间的分工边界写清楚。
- CLI 横幅版本号从 `cloudra.__version__` 读取，和 `pyproject.toml` 一致为 2.0.0-beta。
- 死循环检测与步数预算：移除步数预算相关逻辑，保留 `AgentStuckLoop`（相同工具+参数连续调用）作为防空转兜底。
- 联网搜索展示：`web_search_call` 状态事件改为流中段逐条上报，并入「思考过程」面板而非孤立系统框。

### 修复
- `ts_guess` IDPP 插值在原子数 >3 时崩溃：`err (npair,) * diff (npair,3)` 的 numpy 广播只在 npair=3（现有单测）碰巧成立；C6H10 一类体系 npair=120 报 `shapes (120,) (120,3)`。梯度改成先扩成 `(npair,1)` 再乘位移。
- v2 删除 v1 worker/`compute_executor` 后异步 `submit_compute_job` 只把行写成 `ready`，无人 `claim_ready_compute_job`，计算任务永远领不走。已恢复 `runtime/compute_executor.py`：`ComputeBroker` 由 FastAPI lifespan 启动，扫描会话库领取任务并拉起 guard / Slurm。
- 子 agent 跑 `dag_record` 时证据落地不唤醒 Supervisor：`dag_stage` 对 `SubAgentLauncher`/`SubAgentSwarm` 快照 delivery revision + 已绑证据计数，差分有变化即父侧 `new_evidence`。
- `dag_init_from_template` 播种骨架后立即 `graph_initialization` 唤醒督导排产，不再等 Coordinator 留言。
- 前端 Agent 列表按 id 去重，避免 YOLO 级联 PATCH 同一 coordinator 多次抬高 `settings_revision`。
- v2 丢失模型原生联网搜索：`LegacyLLMProvider` 从不解析 native_search 适配器——外置 `web_search` 工具不剔除（模型绕开原生搜索走第三方）、provider 侧搜索参数不注入、DeepSeek 的 /responses 传输不启用；`LegacyPromptProvider` 还把 `web_search_available` 硬编码 False（「联网搜索」prompt 段消失）。已对齐 v1 行为：命中适配器时剥 `web_search` 函数工具、注入原生参数、`transport=="responses"` 走 `create_responses_with_retry`；`legacy_default_settings` 桥接 legacy 配置的 `native_search`/`native_search_params`。
- `DagController.maybe_supervise` 的 `on_supervision` 投影回调改为 best-effort：投影故障（如壳会话 spawn 被拒）只记 warning，督导照常运行、父 turn 不受连累（此前投影异常会在 supervisor.run 之前杀死整个 Coordinator turn，是 process 图从不推进的直接原因）。
- 子 agent 不继承 yolo：YOLO 是 per-agent 设置（spawn 时快照 = 项目 defaults → 角色 defaults → spawn patch），而 `_spawn_child` 只透传 `orchestration_mode`，父开了 yolo 子 agent 仍逐项弹审批。现在 yolo 提为项目级开关：AgentBar 顶栏的 YOLO 勾选写入项目 defaults（新 agent 自动继承）并级联 PATCH 现存 agent（`patch_settings` 原地生效）；spawn 时子 agent 另继承父值（subagent_bridge 与 hub_bridge call 共用 `_spawn_child`）；Inspector 里的 per-agent 勾选保留为单 agent 覆盖。
- `test_stream_marks_replay_boundary` 把全套回归卡死：httpx ASGITransport 缓冲整个响应体，无限 SSE 流经它永远等不到 `project.synced`（`send` 要等 app 跑完才返回，而 app 永不结束）。回放+边界标记逻辑抽成模块级 `_sse_replay` 生成器（端点行为不变），测试直接驱动生成器断言。
- `message_supervisor` 后整个 run 崩掉（`'dict' object has no attribute 'state'`，重试 2 次后 failed，工具气泡显示 interrupted）：旧快照里没有后加的 `supervisor` 内置角色，恢复时角色注册表被快照整个替换，shell spawn 被拒；`_SupervisionShell` 未检查 spawn 是否被拒，把 `{"error": ...}` dict 当 AgentSession 用。恢复改为快照角色合并覆盖到内置角色表上（补丁继续生效、新内置角色不丢）；shell 在 spawn 被拒时降级为无 UI 投影（督导本体照常运行）。
- compute 失败可观测性：guard（runtime/monitor.py）失败路径统一把可读原因落 `compute_jobs.last_error` 与 state json 的 `error` 字段——环境检查/命令构建失败直接落信息；日志解析失败带 calculator 退出码 + 日志尾部；计算失败从日志尾部提取终止标记段（Gaussian `Error termination`、CP2K `ABORT` 等，含上下文行，保序去重）；失败事件内联 `Failure reason:`。`query_compute_job` 的 last_error 不再返回空字符串。
- DAG 投影：failed 的 observed_tool_call 遥测节点不再混入 blockers 视图（它们是不可执行的历史记录，污染真正的排产阻塞项）。
- text_writer 等破坏性工具在 YOLO 模式下报 `'_LegacyAgentBridge' object has no attribute 'context_manager'`：YOLO 守卫改为对无 context_manager 的 v2 壳 bridge 容错（降级为空上下文）。
- 历史轮次的 thinking 被吞：reasoning 原本只经瞬时 `llm.chunk` 流式展示，不落库，刷新/重进后全部消失。现在每轮 LLM 调用落一条持久 `agent.thinking` 事件，前端折叠渲染（绿色标识），SSE 收到持久段时替换对应的流式段避免重复。
- 中间轮次的正文被吞：带工具调用的轮次，模型 narration 只活在流式气泡里，turn 结束即消失。现在 continue 轮的正文落持久 `agent.message_emitted`（stop 轮正文由 runner 最终消息承载，不重复落）。
- stop 轮的最终消息曾是 stop 工具输出 schema 的 JSON dump（模型的最终陈述被吞）：现在用户可见消息 = 模型正文，模型没写正文时回退 stop 输出的 message（保留 reason/[ANSWER] 语义）。
- 前端 SSE 漏注册 `agent.thinking`/`run.retry`/`hub.posted`/`compaction.requested` 事件类型（EventSource 按类型监听，未注册即静默丢弃）：持久 thinking 段实时不送达、去重逻辑不触发，已补齐并与后端 EVENT_TYPES 对齐。
- 重进会话时历史提示重复弹出：SSE 每次连接从 cursor 0 全量回放，审批/LLM 失败等 toast 对回放事件重复触发。现在回放末尾发 `project.synced` 边界标记，回放期只重建状态不弹提示。
- workspace_dir 相对路径静默嵌套：客户端传入剥掉前导 `/` 的路径时，下游会把它和 server 进程 cwd 拼成 `cwd/home/...` 的嵌套怪路径，所有文件/bash 工具全崩。现在 `project.create`/`project.update` 在命令层规范化：非绝对路径直接拒绝（清晰报错），`~` 展开，不存在的目录自动创建。
- 长会话历史事件被窗口截断：events 端点原本只返回最后 500 条且 `query_session` 取尾部，早期 message/thinking 事件掉出窗口（表现为"中间轮 content 被吞"）。端点改为从头分页（`tail=False`），前端翻页拉全量。
- DAG stage 在事件循环线程上同步建 SQLite（护栏告警）：`_controller` 改 async，`init()` 走 `asyncio.to_thread`。
- 非瞬态 LLM 错误（401/402/400 等 4xx）不再触发 runner 原地重试，直接 failed 落错；5xx/429/连接错误保持退避重试。
- 前端时间线：工具行配对（tool.finished）后从 openTools 删除，修复 cancel/run 结束时把历史已完成工具全部误标 interrupted 的问题。
- v2 恢复语义：进程重启后恢复出的 running/waiting agent 没有存活 runner（run 只在内存），restore 时统一落 failed 并记 `run.finished`（"interrupted by process restart"），界面不再僵尸转圈；发消息即可自动重开。
- YOLO 审批时模型没返回 `submit_approval_decision` tool_call 或参数解析失败，不再把“未返回 tool_call”这种内部实现错误当拒绝理由甩给主 Agent，而是在 Guard 内部告警、纠偏并重试（最多 3 次）；耗尽后按默认安全策略拒绝，返回给主 Agent 的是不含实现细节的中性原因。
- TUI 代码块「复制」按钮失效：`on_click` 命中检测未减去边框/内边距 gutter，4×1 热区永远点不中；修复并加回归测试。
- 审批/提问弹窗 `MarkupError` 崩溃：动态内容（工具参数、命令输出）按 console markup 解析遇 `[` 抛错打崩整个 TUI；改为 `SafeStatic`（markup 解析失败自动降级纯文本）+ `markup=False`。
- DeepSeek Responses 流式翻译缺 key：chunk 的 `delta`/`message` 未常驻 `content`/`tool_calls`，reAct 直接属性访问抛 `AttributeError('tool_calls')`；统一补齐占位 key，`ResponseDictWrapper.model_dump` 尊重 `exclude_none`。
- DeepSeek Chat Completions 注入 `web_search` 工具被 400 拒绝（`tools[..].type: unknown variant`）：原生搜索一律走 `/responses`，chat 路径不再注入。

### 移除
- v1 运行时整体删除：旧 FastAPI 面（`services/api.py`/`api_v1.py`）、`services/service.py` 应用服务层、legacy 执行核心（`runtime/runner|executor|workers|compute_executor|mobile_tasks`、`core/react.py`）、Flet GUI（`ui/`、`flet_app.py`）、Android 全家桶（`android/`、`extensions/cloudra_native/`、`device/`、`device_broker`、mobile/remote 相关 infra 与文档）、legacy 论坛存储（hub_posts）、`control_store`/`interactions`/`conversation_repo`/`case_bank`/`context_stats` 及对应测试。Managetool 四个跨 agent 工具只保留 schema（执行由 runtime_v2 桥接拦截）。
- CLI 收敛为启动器与运维命令（`web`/`config`/`logs`/`skills`/`backup`）；`run`/`gui`/`sessions`/`history`/`devices`/`android` 子命令移除。

## [1.8.0] - 2026-07-18

### 新增
- `first-principles-calculation` skill 加 `references/`（`ase-guide.md`、`ase-quick-reference.md` 和 3 个可运行示例脚本），内容来自 [jkitchin/skillz](https://github.com/jkitchin/skillz)（MIT，已保留版权声明）。写 ASE 脚本前可用 `getskill` 的 `other` 参数按需加载。
- LLM 调用全链路迁到 `AsyncOpenAI`（agent / yolo_guard / supervisor / context_manager / memory），解决同步调用冻结事件循环的问题。
- Token 级流式输出：`reAct` 把 LLM 增量以流式写入 `llm_chunk` 事件，前端 SSE 实时渲染；子 Agent（Follower）默认开启流式。
- 任务打断：API/前端可请求打断 Session，先置 `cancel_requested` 由 Agent 自行退出，超时后 SIGTERM 兜底，支持级联取消子 Agent 和计算任务。
- 对话式运行视图：前端运行区改成按 Session 分面板的 transcript，区分思考/内容/工具气泡，Coordinator 和子 Agent 各自署名；终态后在对话末尾只展示一个“最终结果”总结。
- 前端补齐 CLI 全部功能：YOLO 按 Session 勾选、设置弹窗（`GET/POST /api/config`）、日志查看器（`/logs`）、跨会话 Sessions 监控（`/api/sessions` 聚合）、Skills 列表。
- 配置 API：`GET /api/config`（脱敏）和 `POST /api/config/set`（带类型 coercion），与 `cloudra config set` 共用实现。

### 变更
- 移除 Tauri 桌面端和预构建的 `frontend/dist/` 目录；当前控制界面以 Textual TUI 为准，`cloudra gui` 仅作为实验性入口保留，暂不推荐生产使用。

### 修复
- 数据库锁冲突：遥测写入改成异步可丢弃；LLM 调用对 429/5xx 加指数退避重试。
- `reAct stop` 结果：`session.result` 现在取最后一条 assistant 正文，不再保存 stop 工具的原始 JSON 返回。
- pip 包缺数据文件：`pyproject.toml` 补 `package-data`（prompts / skills / `calculator.sh`），修复 wheel 安装后 `_load_prompt` 报错。

## [1.7.1] - 2026-07-12

### 新增
- 会话清空：左侧栏加“清空会话”按钮，二次确认后删除所有 Conversation / Session / 消息 / 审批记录。

### 改进
- 后端 API：新增 `DELETE /api/conversations` 和 `CloudraService.delete_all_conversations()`；CORS 支持 DELETE。
- 后端数据模型：调整 `session` 表结构以支持新的 Session 生命周期和事件记录。

## [1.7.0] - 2026-07-09

### 新增
- 自我学习与记忆：Agent 可以从过去的对话和成功案例里学习和反思。
- 科研监督员：新增独立 Agent，监督实验进度、确保科研严谨性并验证结果。
- 全局案例库：案例存储结构从原来的局部 DB 升级到全局 Case Bank，支持跨对话检索和经验复用。

### 改进
- PDF 解析：用 PyMuPDF 重构 PDF 提取逻辑，改到后台线程异步执行。
- YOLO Guard 网络：请求头被 OpenAI 或中转站拦截时，自动切换 User-Agent 做 fallback 请求。
- Function Calling 健壮性：根据参数反推工具名的兜底机制，兼容部分中转站返回空工具名的情况。

## [1.6.3] - 2026-07-07

### 新增
- `research-paper-writing` skill：指导 AI 写学术论文、Markdown/LaTeX 排版、期刊模板格式化。覆盖 storytelling、introduction、abstract、method、experiments、conclusion、related-work 等章节；包含 IEEE/Nature/Elsevier/ACM/APA 的 LaTeX 模板；包含 Pandoc/LaTeX 编译和文献管理工具用法。

### 改进
- 更新 writer prompt，要求写论文时调用 `research-paper-writing` skill，约束行文风格，禁用夸大其词。

## [1.6.2] - 2026-07-04

### 新增
- Coordinator 异步计算等待与事件唤醒：异步提交计算任务后，Coordinator 不再立即退出，而是保持存活并轮询后台任务；当 `guard` 注入计算完成事件后，Coordinator 被唤醒继续处理结果。
  - `_wait_for_subtasks` 扩展为 `_wait_for_background_tasks`，同时等子 Agent 任务和计算任务。
  - `run_task_async` 加事件唤醒循环。
  - 新增 `tests/test_run_task_async.py` 测试。

## [1.6.1] - 2026-07-04

### 新增
- `--yolo` CLI 选项：危险操作不再等用户审批，由独立 LLM Agent 自动判断是否合理。
  - 新增 `cloudra/yolo_guard.py` 安全判断模块。
  - 新增 `prompts/yolo_guard.md` 审计员 prompt。
  - 新增 `tests/test_yolo_guard.py` 测试。
- 上下文压缩：上下文超过模型窗口一半时，自动对最近 10 轮 assistant 之前的历史消息调 LLM 生成概要，避免无限增长。
  - 新增 `cloudra/token_estimator.py` 轻量 token 估算器。
  - 新增 `tests/test_context_manager.py` 测试。
- 多模态渲染优化：图片 base64 编码、视觉降级、视觉历史窗口（最近 10 轮）全部下沉到 `ContextManager.build_messages()`，简化 `Agent.llm_call()`。
- 模型视觉能力配置：`LLMConfig` 加 `supports_vision` 字段，可在 `config.yaml` 里分别为 Coordinator/Follower 配置。

### 改进
- `Agent.llm_call()` 大幅简化，移除重复的消息构建和异常驱动降级逻辑。
- `ContextManager` 成为上下文的唯一渲染来源，职责更清晰。
- 区分 `max_tokens`（生成限制）与 `context_window`（上下文窗口），避免大上下文模型配置冲突。
- 统一依赖源到 `pyproject.toml`，删除独立的 `requirements.txt`，补齐 `fastapi`/`uvicorn`。
- `cloudra.__version__` 作为唯一版本来源，`cli.py` 和 `api.py` 同步读取。

### 移除
- 删除废弃的临时脚本 `draw_caffeine.py`。

## [1.6.0] - 2026-06-18

### 新增
- 异步计算任务基础设施。
- `ContextManager` 统一上下文管理。
- sqlite 迁到 aiosqlite。

## [1.5.1] - 2026-05-23

### 改进
- 重构 prompts。
- 限制 Coordinator 可用工具范围。
- 改进 UX 反馈。
