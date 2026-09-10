# AGENTS.md — Cloudra 项目指南

给 AI 助手与新贡献者的仓库导航。项目定位与三层架构（control plane / research runtime / execution plane）见 `README.md`，这里只讲代码布局、边界约定与开发命令。本文件是**地图不是手册**：每个模块只记职责与坑点，细节读代码。

## 命令

```bash
uv run pytest -q tests/            # 全套测试
uv run pytest -q tests/test_dag*   # 聚焦某个子系统（按文件名前缀选）
uv run ruff check cloudra tests    # lint（select E/F/W/I，line-length 120 但 E501 不强制）
cloudra                          # 构建并启动 Web 前端（API + SPA 单端口；顺带 detach 拉起计算调度守护进程与知识向量服务）
cloudra scheduler                # 前台运行计算调度守护进程（单实例 flock；CLOUDRA_SCHEDULER=off 禁止自动拉起）
npm --prefix cloudra/runtime_v2/js_host test   # JS 宿主（QuickJS 沙箱）测试；先 npm ci --prefix cloudra/runtime_v2/js_host --ignore-scripts --no-audit --no-fund 装唯一依赖 quickjs-emscripten（运行时/启动绝不自动跑 npm）
uv run python -m compileall -q <改动文件>   # 改完先做语法检查
```

入口：`cloudra`（CLI，`cloudra/cli.py`：默认启动 Web 服务并打开浏览器，子命令 `web`/`config`/`skills`/`backup`/`knowledge`/`scheduler`/`stop`；任务执行面已收敛到 runtime_v2，CLI 不直接跑任务）。`cloudra stop` 是显式全停入口（实现在 `services/shutdown.py`）：落 `data_dir/daemons.stop` 关停标志 → 通知 API 优雅关停（POST `/api/v2/runtime/shutdown`，lifespan 收尾）→ 有界等待复查；**不 kill 计算进程**（铁律不变）。Python >= 3.11，POSIX-only（flock/nice 依赖 fcntl 与 POSIX 语义）。

停止语义边界（取消/全停契约）：① 取消单个 agent（`POST /api/v2/agents/{id}/cancel`）立即取消其 run task 与该 session 全部登记后台任务，并**级联取消它自己的全部存活后代**（BFS 整棵子树，含 launch group 级联停 spawn；子的完成回传按 park-don't-wake 投递信箱驻留、绝不唤醒已取消的父），之后不再新发 LLM 请求，本地终态照常持久化；级联只及于自身的子 agent，**永不触碰 scheduler/guard/QM 计算**；② 没有项目级一键取消——逐 agent 取消，或以 `cloudra stop` 全停；③ 服务关闭顺序固定：先停准入与 watchdog 自愈，再取消并 await 全部推理/收尾任务（含 launch group worker，经 runner `track_background` 登记与 `LaunchGroupManager.cancel_all` 状态收敛），然后关流/客户端，最后回收本进程拥有的 JS host；④ 已发到 provider 的请求远端不可撤销（账单照算），本地保证停止读取/重试/新发并尽量关连接（流式 socket 层 RST）；⑤ 单 agent 取消不连带杀 scheduler/guard/QM 计算（科研计算独立于推理运行），只有 `cloudra stop` 显式全停才回收守护并防自愈拉起；⑥ 只终止有明确归属的任务/进程，禁止按 python/node/用户名等宽字符串匹配杀进程，子进程必须 wait/reap 而非只发信号。

**v1 已删除**：旧 `services/api*.py`、`runtime/` 执行核心、`core/react.py`、Flet `ui/`、Android/device 链、会话库六张 legacy 表均已移除（v2 审批/提问走 `runtime_v2/pending.py`，提醒走 `runtime_v2/reminders.py`，子 Agent 状态走 core.agents 投影）。无兼容回退，别再引用这些名字。

## 模块地图（cloudra/ 包）

包根：`cli.py`、`web_launcher.py`（启动 Web 前端并开浏览器）、`calculator.sh`（package-data 资源）。

**`core/` — 共享基类**

- `agent.py` — `Agent`/`Coordinator`/`Follower` 基类与权限模型宿主（v2 会话不经过这里的执行方法）；`message_history.py` — JSONL 消息历史。

**`runtime/` — 执行面共享件**（v1 执行核心已删，只剩这些）

- `prompt_assembler.py`（确定性 system prompt 组装，读 `prompts/*.md` 按签名缓存；AGENTS.md 仅注入 Coordinator）、`environment_observer.py`。
- `monitor.py` — guard 进程：持排他 flock → 拉起 calculator（nice +10 降权保控制面调度份额）→ 解析日志写终态。**终态判定按引擎分派文本终止标记**（ORCA 认 `ORCA TERMINATED NORMALLY`、xtb 认 `normal termination of xtb`，与 log_parser 共用 `tools/core/` 的 frames 原语；优化另有"跑满步数未收敛"第二判据判 failed，xtb 只对行声明的 opt/ohess 任务生效），**cclib 只取数据不定成败**。xtb 作业的任务参数（`charge`/`multiplicity`/`xtb_task`/`xtb_solvent`/`req_cpus` 列）由 guard 从 compute_jobs 行读出、经 `XtbParams`（`infra/compute_utils.py`）透传给 calculator.sh 拼 `--chrg/--uhf/--opt/--hess/--ohess/--alpb/--parallel`。
- `compute_executor.py`（共享执行件 `run_compute`，认领方只有 scheduler 守护与 benchmark 进程内实例）、`calc_lock_wrapper.py`、`compute_notify.py`（`build_compute_knowledge_query` 查询构建）。

**`scheduler/` — 计算调度守护进程（进程隔离）**

- `daemon.py` — `cloudra scheduler` 入口：与 API 彻底分家，状态同步只走中央 `compute.db` 的 `compute_jobs` 表。职责：容量感知认领（槽位+CPU/内存记账）、对账器（探 guard 锁：锁空闲→spawn adopt guard 接管，锁持有→续租防重领）、孤儿 reap；单实例 `data_dir/scheduler.lock` 排他 flock。拉起与自愈由 `services/daemon_supervisor.py` 负责。
- 资源模型：agent 提交时显式申请（`cpus`/`memory_mb`/`priority`），对照节点 `resources` 硬校验超容拒收，**核心链路零输入文件解析**。`job_type` ∈ gaussian/vasp/orca/cp2k/xtb。
- 完成通知：`ComputeNotifyBroker`（`runtime_v2/compute_notify.py`）纯 DB 轮询终态行逐作业投递（API 宕机窗口不丢通知）；投递前自动检索 chem-kb 拼建议（无 provider/检索失败静默降级）。

**`services/` — 服务层 / 控制面**

- `api_v2/` — HTTP 控制面唯一实现（uvicorn factory 拉起，同端口托管 SPA）：`app.py`（装配 + lifespan + daemon-watchdog 自愈任务，测试 conftest 默认 off）、`context.py`（`ApiContext` 显式持有 core/bus，路由零闭包）、`models.py`（全部 pydantic 请求模型）、`sse.py`、`routers/`（十组 APIRouter）。薄路由：写操作一律走 CommandBus；唯一例外 `GET/PATCH /api/v2/runtime/config`。
- `daemon_supervisor.py` — 守护进程拉起判定链唯一事实源（`ensure_*`）：关停标志 → env 开关 → 端口健康探测 → flock 单实例探测 → spawn_detached；`request_daemons_shutdown(persist=...)` 置关停标志，`clear_daemons_shutdown()` 由显式启动清除。**崩溃循环节流**：距上次真实拉起 <60s 则跳过并告警。
- `shutdown.py` — `cloudra stop` 实现（见上"停止语义边界"）。
- `session_store.py` — 会话库 `session`/`session_events` 两表的写入助手与只读查询；`compute_store.py` — 中央 `compute.db` 的 compute_jobs 全部 SQL 入口；`nodes.py` — 多节点/Slurm 计算注册表。

**`persistence/` — 持久化 / 状态**

- `database.py`（`ConversationDB` 会话级 SQLite 承载 `session`/`session_events`/`artifacts`/`dag_*` 表；`ComputeDB` 中央计算库 `data_dir/compute.db`，schema 新建即新版无迁移）、`artifacts.py`、`memory.py`（MEMORY.md 长期记忆）。
- `paths.py` — data_dir 下所有路径的**唯一事实来源**（含 per-project 默认工作区推导，消除裸相对路径落进程 cwd 的串目录问题）；`fs_utils.py` — 原子写；`workspace.py` — 工作区受限读写。

**`knowledge/` — 化学知识库（chem-kb）**

与 `runtime_v2/knowledge.py`（图书馆协议，管合并排序）互补：本包管存储与检索。

- `store.py` — chem_kg.db 的 DDL/导入/查询（sync-only，async 调用方 `to_thread`）。**读路径只读、缺库返回空绝不建库**；写仅 `ensure_schema`/`import_csv`，导入幂等。双语：实体 props 挂 `label_en`（属 FTS 索引列，英文查询自动可搜图谱）。
- `plugin.py` — 单一混合 provider：语义通道（向量微服务，异常该通道为空绝不抛）+ 图谱通道 + 模糊兜底（`fuzzy.py` 扫 `vector_store/cards.jsonl`）。配额结构性保证多通道全带上，单通道空按优先级链补位；只返回 `KnowledgeEntry` 实例。
- `health.py` — 三通道健康聚合唯一实现，API 与 CLI `cloudra knowledge status` 共用；`installer.py` — `knowledge install/uninstall` 经 `add_plugin`/`remove_plugin` 幂等改 config。

**`base/` — 数据类与基类**

- `skill_class.py`/`tools_class.py` — 加载器与基类；审批钩子 `use_approval_handler`（ContextVar），未设置时 `request_approval` 直接抛错（ask_user 同理走 `use_input_handler`）；`session_class.py`。

**`infra/` — 支撑设施**

- `config.py` — **磁盘 YAML 是唯一事实源**，唯一写入口 `mutate_config(fn)`（flock 排他 → 读磁盘覆盖内存 → 应用 → 原子写回 → 就地刷新单例）；`add_plugin`/`remove_plugin` 幂等；测试重建单例用 `_reset_for_tests()`。`LLMConfig.reasoning_effort`（思考强度，None=不传）是 per-agent `RuntimeSettings.reasoning_effort` 为空时的全局回落（`adapters.legacy_default_settings`）；chat 路径顶层透传，Responses 路径由 `_build_responses_payload` 翻译为 `reasoning.effort`。
- `llm_client.py` — OpenAI 兼容传输层；取消准入 `abort_event`（每次发送前/retry 后/fallback 前检查）；流式取消走 socket 层 shutdown+close 立即 RST，**高层 `resp.close()` 跨线程会卡锁，禁止走**。
- `flocks.py` — fcntl flock 原语，**执行面唯一的进程存活/互斥判定手段**；`compute_utils.py` — guard 命令构建/detach 拉起、`resolve_log_path`（统一的 log_path 来源）；`logging_setup.py`、`slurm.py`、`operations.py`（备份/恢复）、`yolo_guard.py`、`json_args.py`（LLM 畸形 JSON 工具参数兜底）等。

**`benchmark/` — 基准评测框架（独立于会话运行时）**

- `schema.py` — 任务 JSON 唯一 schema（`TaskSpec`）：机理图边带 `bond_changes`（键级降 break、升 form）；**交付侧**每条边声明 `barrier_kcal_mol`（该步能垒，逐条声明）且 `mechanism_graph.json` 可带可选 `refusal` 结构化拒答声明；gold 侧能垒锚点另记 `barrier_type`/`barrier_reference`；hard 档选择性锚点走 `gold.selectivity`。
- `gen_easy/normal/hard/impossible_tasks.py` — 四档确定性生成器（`ideapool/reaction_candidates/*.md` → `ideapool/tasks/`）；**改题源后必须重跑生成器**，`test_*_tasks_regenerate_identically` 守卫同步。映射 SMILES 与逐题登记拆在 `*_registry/` 子包；bond_changes 由生成器从映射 SMILES 差集推导、禁止手填；校验 fail-loud。方法白名单：easy/normal/hard 一律 `MethodPolicy(allowed_methods=["xtb","b3lyp"])`（B3LYP-D3(BJ)/def2-SVP；xtb 探索路径、b3lyp 做驻点/能垒验证），**impossible 保持 `["xtb"]`**（I 系靠单参考方法边界触发科学拒答，开 DFT 会破坏该校准）；regenerate 守卫已断言该集合。impossible 档特有：`pair_id` 双向互指（I 题拒答 × S 兄弟题作答）、`accessible=False` 节点入 `rubric.impossible_case`、query 统一带拒答协议句（I/S 同款不泄题）。
- `graph_similarity.py` — 化学参数化图评分，默认**子图覆盖**打分（gold 嵌入交付图即满分，多出不罚）；RDKit 可选。
- `integrity.py`/`selfconsistency.py`/`barrier_evidence.py`/`accuracy.py` — 三层取证评分：证据绑定（`smiles:` 注释行；机理图形状的 JSON 不算证据）→ 鞍点/IRC/极小值物理自检 → **能垒评分只读交付物**（`barrier_evidence` 逐步从绑定日志算 `E(TS) − E(起点最小值)` 并取最高者为 RDS；交付 JSON 每条边声明 `barrier_kcal_mol`，两者都必需且一致，复用同一 sigma；缺失/冲突 fail-loud 记 0，绝不用最终消息里的数字兜底）。交付图加载走 Postel 宽松规范化（GH #29）：`type`→`role`（仅识别别名，未知 type fail-loud）、`source`/`target`→`from`/`to`、字符串 SMILES 提升为列表；agent 多写的键忽略、边缺 id 自动补。
- `method_policy.py`/`policy_stage.py` — 纯转引（实现在 `runtime_v2/method_policy.py` 与 `runtime_v2/policies/method_policy.py`）；**无法解析方法时 fail-closed**。
- `backend.py`（runtime_v2 后端，yolo 无人值守，进程内 SchedulerDaemon；后端不回传任何供评分的文本/数字——评分输入只有沙箱交付物）、`api_pool.py`（API 端点池防 429）、`refusal.py`（拒答行为分类 answered/refused/failed 与跨档 TP/FP/FN/TN——impossible 档主指标即跨档拒答 precision/recall；判定纯结构化：可解析交付图→answered、结构化拒答声明→refused、其余→failed，不解析散文）、`runner.py`（`BenchmarkRunner` + 专用 benchmark.db（`runs`+`batches` 两表，旧库缺列整表重建迁移）；composite = (0.5·graph + 0.2·selfconsistency + 0.3·accuracy) × binding_quality，零证据倒扣）。
- `watch.py` — 题目终态监视器 `RunWatcher`（GH #30）：**SUCCEEDED ≠ 题目完成**（wait_background 收尾只是当前 run 休眠，子 agent/计算作业未竟前继续等唤醒）；`WAITING_APPROVAL`(reason=`wait_review`) 是等内部 Supervisor 裁决，不套 300s 人工卡死取消，只有项目内督导全灭才按卡死处理；waiting_input/审批等待照旧 stuck_grace 取消，整体 run_timeout 封顶。CLI backend 与 Web 批次共用。
- `batch.py` — Web 控制面批次（GH #32）：题目跑在 **live RuntimeCore** 上（项目名 `benchmark:{task_id}`，方法白名单走 `ProjectSettings.method_policy`，计算由常规 `cloudra scheduler` 认领），`BenchmarkService` 单例提供 start/stop/status/history + SSE 事件馈送；stop 只级联取消题目 agent，不触碰计算。CLI：`python -m cloudra.benchmark`；Web：`/api/v2/benchmark/*`（`services/api_v2/routers/benchmark.py`）+ 前端 `BenchmarkPanel.tsx`（批次控制/矩阵看板/拒答矩阵/单题下钻到标准项目视图）。

**`runtime_v2/` — 事件驱动内核（推理循环唯一实现）**

- 骨架：`schemas.py`（API 类型唯一来源）、`roles.py`（角色权限唯一来源 `BUILTIN_ROLES`）、`events.py`、`core.py`、`apply.py`（**`apply_event` 唯一状态应用器；禁止在 apply_event 之外写状态**，恢复重放与在线路径共用）、`effects.py`、`commands.py`（CommandBus 四拍：纯 decider → append+publish+persist → apply_event → 执行 effect）。
- `agent_host.py` — AgentSession 状态机：restart = 保留身份开新 run，只有 LLM 对话原文不跨 run；`wake()` 统一苏醒语义。
- `agent_runner.py` — 每 Agent 一个 async task；turn 崩溃原地退避重试；run 结束的 finalize detach 成独立任务但经 `track_background` 登记（裸 create_task 会让取消/shutdown 碰不到它）；`RuntimeCore.aclose()` 是服务关闭唯一入口（cancel_all → 回收 JS host）。**统一运行结束门禁**：显式 stop 与无 tool_calls 的纯文本最终回复都在收尾前经 `_evaluate_completion_gate` 裁决（各 stage 的 `audit_run_end` 钩子取最保守：wait_background > wait_review > continue_work > allow_final）；同缺口指纹无进展退出有界计数，耗尽落 failed，不伪报完成。
- `supervision.py` — 事件驱动督导运行时入口（督导不在此跑 LLM）。Supervisor 是项目内唯一普通 runtime_v2 agent；**待办唯一事实来源是 DAG store**；通知按状态表（queued/running 投信箱、succeeded wake 开新 run、**failed/cancelled 不自动复活**），刻意走 `mailbox.deliver` + 条件 wake 而非 `agent.message`（其 decide 会自动 reopen 终态 agent）。failed/cancelled 督导 + 可消费待办时另给 Coordinator 发一次性告警（`_sync_terminal_supervisor_alert`：pin 内容即指纹去重、条件消失撤 pin，点名 agent.message / agent.restart 恢复入口）。裁决通知三类（review_decision / call_verdict / draft_verdict）共用同一张 `dag_review_notifications` 表与 `flush_review_notifications` 唯一投递口（pin + mailbox + park-don't-wake + 标记 sent 闭环）。
- `turn_pipeline.py` — 固定轮次管道：`llm.chunk` 只发 EventHub 不落盘；每轮 reasoning 落持久 `agent.thinking`；工具执行收口到 InvocationService；按 run 冻结的 `invocation_protocol` 做线缆路由校验。
- 调用生命周期：`event_writer.py`（有序持久化+幂等发布唯一写口）、`invocation_types.py`/`invocation_context.py`/`invocation.py`（durable requested → policy stages → started → executor 恰一次 → result_recorded → finished；per-agent 锁串行；**持久化失败抛 EventPersistenceError 不伪造终态**）。
- JS 协议（默认，`invocation_protocol` 可切回 traditional）：`tool_catalog.py`（协议+编排模式感知线缆投影唯一来源，**禁止在别处新建工具名集合**；dag_* 工具只在非 standard 模式投影，`supervisor_access='review_decision'` 的裁决工具只在 dag_guided 投影，`unattended` 设置隐藏 ask_user）、`js_protocol.py`、`js_runtime.py`（每程序一个 node 进程跑 QuickJS-WASM 沙箱；**JS 堆不跨重启恢复、失败程序不自动重跑**；取消只 SIGTERM/SIGKILL JS host，绝不碰 scheduler/guard/QM 作业）、`js_host/`（Node 宿主；唯一依赖 quickjs-emscripten 手动 npm ci 安装，不入 git/wheel；威胁模型=本地单用户沙箱，不是 OS 沙箱）。
- `policies/` — permission/unattended/method_policy/dag/goal/schedule/knowledge 七个 PolicyStage（新 harness 能力只加 stage；unattended stage 是 GH #31 的 fail-closed 拦截：`RuntimeSettings.unattended` 的 agent 调 ask_user 直接 block 反馈，绝不进 waiting_input——yolo 只罩审批通道；method_policy stage 是 per-project 方法白名单执行点，在 submit_compute_job/qm_input_writer/bash 三层拦截；dag stage 的 stop 交付审计统一在 runner 收尾边界经 `audit_run_end` 进入）。各 stage 的易失状态纪律与副作用豁免见各模块 docstring。
- 其余组件：`mailbox.py`（统一投递）、`pending.py`（审批/ask_user 内核 broker；**重启恢复时孤儿审批/提问显式落 expired 终态**）、`reminders.py`（schedule 拦截 + 内存定时器 + `check_command.py` 只读检查命令 fail-closed 门）、`notices.py`、`compaction.py`（`compaction.requested` 事件驱动）、`context_tree.py`（事件溯源上下文树）、`transcript.py`、`subagent_bridge.py`/`hub_bridge.py`（子 agent 终态回传父邮箱并 wake；failed/cancelled 收件人 parked 驻留不唤醒）、`launch_groups.py`（非阻塞 swarm 并发组；worker 任务创建即经 `track` 回调登记进 runner 的 `track_background`，父取消经 `CancelLaunchGroups` 效果级联 `cancel_for_parent`、shutdown 经 `cancel_all` 收敛组状态）、`knowledge.py`（证据分层 L1>L0>L2）、`plugins.py`、`adapters.py`、`persistence.py`（事件表 + 快照**节流缓存** + 增量重放；**恢复时把 running/waiting agent 落 failed**，僵尸子的终态同普通完成回传送达父信箱并按 park-don't-wake 唤醒，为未完成调用/程序补终态，恢复路径绝不执行 executor/JS 进程/调度作业）。
- `compute_notify.py` — `ComputeNotifyBroker`（见 scheduler 节）；`email_listener.py` — IMAP 收件监听。

**`tools/` — 工具**

- 按领域分组（Bash/Chem/Search/Write/Plan 等；QM 双引擎 Gaussian/ORCA + xtb 解析 + 外部 MLIP 路由；DAG 面是 `dag_tools/` verb 族）。`registry.py` 注册（`ToolRegistration` 可声明 `dag_evidence_producer`/`dag_compute_entry`/`visual` 等语义），下游只能经 `capabilities.py` 投影查询，**禁止在别处新建工具名集合**。
- `tools/core/` — 权限模型、审批流水线、gaussian/orca/xtb frames 解析（纯函数）与各守卫。Managetool 的 subagent_launcher/subagent_swarm/get_subagent_report/agent_hub/schedule 五类只保留 schema 作线缆格式，执行被 runtime_v2 按名拦截。
  - `structure_builder.py` — **分片建模的唯一实现**：`prepare_structure(request) -> PreparedStructure`。按分子图连通分量拆分（保留原始原子序号映射；重复组分不合并、单原子离子保留）→ 显式加氢并把新增氢登记成 `(父重原子输入序号, 该父原子上的第 k 个氢)` 的**稳定身份**（`AddHs` 后的数组下标绝不充当跨反应映射）→ 逐组分 ETKDGv3 嵌入 + 力场优化，每迭代一帧轨迹 → 多组分再经 `complex_assembly` 组装出复合物候选。状态用 `BuildStatus` 枚举表达（`ok` / `assembly_failed` / `charge_mismatch` / `unsupported_spin` / `missing_parameters` / `optimization_failed` / `invalid_input`），收敛与否另有 `optimization_status`/`convergence_code`：**「坐标已生成」或「优化返回 0」都不构成「几何可用」**。组装需要已嵌入的组分坐标，因此 `embed=False`（只做结构解析）对多组分输入返回 `assembly_failed` 并说明原因。
  - `complex_assembly.py` — 反应复合物组装（**参数已由用户批准**，见该模块 docstring 的参数表：32 个 Fibonacci 球面取向、片间最小原子距 1.0 Å、反应中心引导保留 8 个放置、反应中心窗口 1.8–2.6 Å、能量窗 6.0 kcal/mol、重原子 RMSD 0.5 Å）。**反应模式**（调用方给出反应物/产物映射得到的 `reaction_center`）用 MMFF94 距离约束预优化，只有全部反应中心距离落入窗口才**释放约束**再无约束弛豫；**普通复合物模式**不凭空指定成键中心。力场必须 `ignoreInterfragInteractions=False`（RDKit 默认会让各碎片独立收敛、能量全同，正是 issue #19 的症状）。弛豫后碎片塌回重叠的放置一律丢弃；平移只用来满足碰撞判据，**其本身不算组装**。组装放置的轨迹只记阶段首末帧（32 个放置 × 逐迭代会到数百 MB），逐迭代完整轨迹由每个**组分**的构建负责。多组分输入的构象系综**就是**组装：`conformer_search` 的 RDKit 后端不再对整体做 ETKDG 系综嵌入（那会把碎片相对取向随机化，等于退回随机叠加），而是直接报告组装候选；CREST 后端则拿最佳组装候选当种子并加 `--noreftopo`。
  - `geometry.py` — 共享几何原语（`kabsch_rmsd` / `fibonacci_sphere_directions` / `rotation_matrix_between` / `rotate_about_centroid` / `min_distance`）：构象系综去重与组装候选去重用**同一套**比较。
  - `structure_artifacts.py` — 轨迹契约与流式落盘：`TrajectoryWriter` 每迭代追加一帧到 `frames.xyz` + `frames.jsonl`（一条力场优化是千↔万级迭代，全留内存会到几百 MB），`TrajectoryRecord` 只持初始帧/终态/帧计数/收敛码（`0` 收敛、`1` 达迭代上限、负值=力场不可用或异常），失败与不收敛轨迹**同样保留**。注意本仓库支持的 RDKit 里 `ForceField.MinimizeTrajectory` 返回的 `RDKit::Snapshot` **没有 Python 类**、`Positions()` 只读，因此逐迭代 `Minimize(maxIts=1)` 是取到逐迭代快照的唯一手段——它是同一条连续优化（同一实例、能量单调、终态与一次性 `Minimize(maxIts=N)` 逐位一致，实测 dE ≤ 1e-4 kcal/mol）。
  - `crest_runner.py` — `run_crest(request) -> CrestRunResult`：每次运行落在 `<output_dir>/crest_runs/<label>_<NNNN>/` 的**持久**运行目录（不再跑完即删），原地保留 CREST/xTB 的全部中间现场，外加 `command.txt`/`input.xyz`/`versions.txt`/`stdout.log`/`stderr.log`。**进程退出与科学成功分开表达**：`returncode=0` 命中 `CREST terminated normally.` 且产物完整才算成功；`returncode != 0` 时**即使**磁盘上有部分 `crest_conformers.xyz` 也绝不报成功（部分产物只作证据）。分类用**精确整行/token 比对**（本模块不含正则）：`initial_optimization_failed`（`Initial geometry optimization failed!`）/ `initial_topology_change`（`WARNING! Change in topology detected!`）/ `search_failed` / `timeout` / `incomplete_artifacts`（缺失、空、截断、不可解析分别报错）/ `unknown_failure`（保留原文，不猜原因）。超时只终止**本次运行自己的进程组**（SIGTERM→SIGKILL 并 wait/reap），绝不按进程名匹配杀进程。
  - `topology_change.py` — 拓扑变更**只记录不判定**：对比「交给引擎的输入」与「引擎留下的 `xtbopt.log` 末帧」的连接表差集，逐条标注 `intra_component`/`inter_component`；判据复用 `internal_coordinates.distance_connectivity`（不另立阈值）。元素符号先规范化（xTB 用小写写 `f c cl`，不规范化会把同一体系误判成「元素序列变了」）。给出预期产物时只做连接表一致性对比，**不是「该变化被允许」的判定**。
- 工具**无持久状态**；输出 `is_success` 统一、给模型的文本一律英文；超大结果（>30k 字符）全文落盘 `.cloudra/tool_output/`，模型只收截断摘要。

**`subagents/`、`prompts/`、`skills/`**

- 8 个领域子 Agent（`registry.py` 是 a-1..a-8 显式注册清单）；`prompts/*.md` 角色 prompt；`skills/` 科研方法技能包。

**UI 前端**

- `frontend/` — React SPA（唯一前端）：`src/App.tsx`（项目栏 + 对话 + Inspector；斜杠命令）、`AttentionDock.tsx`（跨项目审批/提问坞）、`DagPanel.tsx`/`KnowledgePanel.tsx`/`AuditLog.tsx`、`api.ts`（v2 客户端）。`npm run build` 通过才算前端可用；生产由 uvicorn 同端口托管 `dist/`。

## dag/ 子系统（DAG 引导编排）

按会话 opt-in：`orchestration_mode` ∈ `standard`（默认，不读不写图）/ `dag_record`（harness 自动接受草稿，Coordinator 自绑阶段，Supervisor 不运行）/ `dag_guided`（Supervisor 接受草稿、逐调用复核绑阶段）。**继承规则（唯一解析点 `agent_host.resolve_orchestration_mode`，spawn 时物化进 agent settings 快照）**：`ProjectSettings.orchestration_mode` 是项目级默认值（压过 `project.settings.defaults` 里的冗余镜像），每个 agent 未显式设置即继承；`RuntimeSettingsPatch.orchestration_mode` 非 None 即显式覆盖（优先级：role default_settings < 显式 patch）。子 agent spawn 复制父的**生效**模式；supervisor 角色默认钉 dag_guided。可经 `agent.settings_update` 中途切换——切入 dag_guided 迁移沿与 `project.update` 一样发 `ReconcileSupervision` 补督导通知；启动 reconcile 也覆盖 standard 项目里带 guided 覆盖的 agent。

- `models.py` — 共享类型：可写图元素只有 delivery（`SpeciesNode`/`ElementaryStepEdge`，无 occurrence/role）；`CallReview`（**source=explicit 才可消费**，legacy_auto/auto 仅审计）；`MechanismDraft`；`GraphOperation` 命令联合（含 `RemoveNode`/`RemoveEdge` 删图命令）。
- `store.py` — 单张 delivery 图持久存储（变更日志 + 物化视图）+ `dag_drafts` + `dag_call_reviews`（append-only）+ `dag_evidence_bindings`（证据引用，支持 file/tool_result，读路径以它为准）。
- `engine.py` — 事务化变更引擎（原子批次、乐观 revision、无环校验、节点/步骤名称唯一性约束）；`apply_stage_verdict()` 执行阶段顺序守卫；`remove_edge`/`remove_node` 必须带 rationale（删节点前必须已无连线，返回 `node_has_edges` 与关联边标识，不提供隐式级联）；删除在图事务内同步收敛待审项（定向到被删目标的 pending CallReview → `ignored` + `call_verdict(target_deleted)` 通知、queued 结构化请求 → `superseded`，历史行与证据不删）。
- `evidence_ingest.py` — 文件证据沙箱固定与 QM/TS 校验（沙箱边界校验、sha256 计算、.cloudra/evidence 快照与虚频复用现有 Chemtool/core 解析）。驻点校验是**三态**：`verified=True` 才算「有频率数据支撑的判定」；没有频率数据时 `verified=False` **且 `is_valid=False`**——「没做频率分析」绝不能被当成「已验证的驻点极小值」，否则 opt-only 甚至中途崩溃的作业会被 `dag_submit_species_evidence` 登记成已完成的物种。`dag_submit_species_evidence` / `dag_submit_step_evidence` 的拒绝文本据此区分「未验证」与「验证不通过」。
- `review_context.py` — Supervisor 唯一持久活动审查项绑定与版本一致性检查。
- `completion.py` — 交付覆盖率确定性评估 `evaluate_delivery()`（支持单一 "supported" 状态及有理由处置）；`substantive_gate.py` — 机理接受前的计算门槛。
- `controller.py` — harness 集成门面 `DagController`，由四个 mixin 组合：`supervision.py`（待办持久化后经 runtime_v2 的 `notify_supervisor` 按状态表通知；显式送审的通知也在这里的 `_trigger_supervisor_after_tool` 完成钩子按新建 review 回执发出）、`evidence_inbox.py`（**CallReview 唯一来源是显式送审 `submit_evidence_for_review`**——只验证与原子持久化，本身不通知；直接存储调用不启动督导，中断窗口由 reconcile 扫持久信箱恢复；工具完成只登记证据快照/派生事实，不自动入箱；`review_call` 的每种终态裁决与落态同事务写一条 call_verdict 通知给提交者）、`stop_audit.py`（`audit_stop` 四态 StopGate；隐式退出与显式 stop 到达同一结束门禁）、`drafts.py`（`accept_mechanism` 的 accept/reject 与落态同事务写一条 draft_verdict 通知给 proposer——legacy actor id 由 flush 解析到活 session）。裁决通知的 flush 触发口在 dag policy stage 的 after_tool（dag_review_evidence / dag_review_call / dag_accept_mechanism 成功）与 reconcile。
- `requirements.py`/`review_requests.py`（结构化送审请求与裁决协议，contract_version=2，basis_fingerprint 不匹配不收裁决）/`evidence_facts.py`/`fact_adapters.py`/`supervisor_tools.py` — 支撑件，细节读代码。

关键不变量：图存储是权威（不在模型上下文里）；证据是不可变记录/产物的类型化引用；删除必须带理由且留在变更日志；模型声明不能标记交付完成，证据等级由 harness 从阶段确定性派生；阶段严格按契约顺序绑定；`rejected` 不是处置——是仍欠的开放缺口，只能重绑或显式 skip/not_applicable-with-reason 关闭；`not_applicable`（带理由）计入完成且不算欠账；`submit_compute_job` 调用永远不是证据（只认完工作业的解析产物）；每条督导裁决（结构化请求 / per-CallReview / 机理草稿）与落态同事务恰好写一条 durable 裁决通知，投递唯一出口是 `flush_review_notifications`（重投幂等、终态收件人 park-don't-wake）。

## 测试约定（tests/）

- 按文件名前缀分组：`test_dag_*`（DAG）、`test_runtime_v2_*`（新内核）、`test_compute`/`test_slurm`（计算执行）、化学工具各一、其余基础设施单测。
- issue #33 的固定复现材料在 `tests/fixtures/chemtool_issue33/`：逐字保存的输入 xyz、CREST stdout、xTB `SUMMARY`/`[ERROR]` 尾部、`--noreftopo` 能力核对、引擎版本与命令行，以及把「观察事实」与「根因假设」分开写的复现表。**issue 里除实测值以外的数值一律标记为未复现**，不得写进测试断言。
- 结构构建/CREST 现场相关护栏：`tests/test_structure_builder.py`（拆分守恒、稳定氢身份、轨迹自洽、失败轨迹保留）、`tests/test_crest_runner.py`（假 `crest` 可执行文件走完整 subprocess 路径覆盖全部终止类别 + 真实引擎验收）、`tests/test_compute_failed_job_artifacts.py`（失败作业仍可提取几何，但频率/TS 验证不得被伪标完成）。
- `conftest.py` autouse 隔离 data_dir 到 tmp_path；不要在测试里写真实数据目录。
- 跳过均按环境探测：缺 `crest`/`xtb` 二进制、无 symlink 权限、非 POSIX。无需要真实 LLM key 的测试。JS 宿主集成测试额外探测 node>=22 + `js_host/node_modules/quickjs-emscripten`，缺失才 skip（最终验收要求真实 Node 跑通，不允许全 skip）；宿主侧自身测试用 `npm --prefix cloudra/runtime_v2/js_host test`。**CI 不装宿主依赖**（node 也不钉版本）：宿主用例在 CI 里按探测整片 skip，这是既有约定「缺失才 skip」的直接后果——真实 Node 的验收在开发机手动跑（`npm ci` 后跑那六个宿主 suite，本机 80 用例 0 skip）。
- 测试替身（fake/stub）签名要对齐真实接口，建议带 `**_kwargs` 防接口加参后变红。
- 可选依赖同样要探测、不许硬断言：CI 只装 `.[dev]`（**没有 RDKit / chem extra，也不装 JS 宿主依赖**）。凡经 `qm_input_writer`、RDKit 化学指纹或 JS 宿主的用例先探测再 skip（先例：`tests/test_benchmark_sandbox_fp.py` 的 `_REQUIRES_HOST`/`_REQUIRES_RDKIT`/`_REQUIRES_HOST_AND_RDKIT`、`tests/test_benchmark_tool_paths.py` 的 `_REQUIRES_RDKIT`、`tests/test_conformer_search.py::test_crest_backend`）。同理**计算资源按本机容量申请**（`max(1, min(2, os.cpu_count() or 1))`，节点容量就是 `os.cpu_count()`），别写死 `cpus=4`——2 核 runner 会按规则合法拒收。本地装了 chem extra 时，用屏蔽 RDKit 的 pytest 插件 + `os.cpu_count` 打桩成 2 的插件复现 CI 环境跑全套，是提交前自检手段。

## 顶层散件

- `kg_data/` — 知识图谱 CSV（`cloudra knowledge import` 的输入；v12.1 起 14,203 实体 props.label_en 全覆盖 / 10,266 行级关系）。
- `ideapool/reaction_candidates/` — benchmark 候选池（easy/normal/hard/impossible 四档 md，定稿圈定见各文末；打标台 HTML 由 `scripts/gen_*_tagging.py` 重新生成，条目变更后重跑）。
- `vector_store/` — 知识卡片 bge-m3 向量五件；`scripts/kg_vec_service.py` 微服务只读这套文件，跑在外部 `.venv-trans` 解释器下（cloudra venv 不装 torch；插件已装时自动 detach 拉起，flock 单实例，`CLOUDRA_KG_VEC=off` 关闭；重编码入口 `vector_store/encode.py --model 模型名`）。
- `deploy/` — 多节点/Slurm 注册表示例与 MACE-OMol25 + ORCA external 计算栈配置文档。
- `docs/` — 专题文档索引；`docs/superpowers/plans/` 存设计计划。
- `install.sh`/`install.ps1`、`web.sh`/`web.ps1` — 安装与开发启动脚本；`build/`、`.worktrees/`、`cloudra.egg-info/` 为构建副产物，勿手改。
- `软著申请材料/`、`copyright_docs/`、`*.pdf` — 申报材料，非代码；软著源程序清单由 `scripts/gen_copyright_source.py` 重建（改代码后重跑）。

## 工作约定

- **禁止补丁式修复**：项目仍是 beta、尚未上线，**不考虑向后兼容**。发现问题必须在架构级根治——能改数据结构就改数据结构、能删代码就删代码、能拆模块就拆模块；不允许打补丁盖过问题（不留 legacy 回退分支、不加兼容 shim、不保留死代码、不用"文档注明"替代修复）。任何修复必须配能直接把问题测红的测试，先红后绿，修完即绿。
- 最小改动：修 bug 不顺手重构；新代码跟随所在文件的既有风格与注释密度。
- **化学/科学设计决策必须问用户**：任何涉及化学或科学方法的设计决策——评分阈值、方法学验收红线、力场/泛函/基组选择、能垒基准定义、评分权重、拒答规则等——必须先向用户确认清楚，**不允许 agent 自作主张拍板**。曾发生 agent 未经确认便写入"TS 虚频 ≥100 cm⁻¹"这类化学阈值；此类影响科学结论的参数必须经用户批准后才能生效。
- **事件循环线程禁止同步阻塞调用**：`async` 函数体内不得直接调用同步 SQLite、`time.sleep`、`subprocess.run`、同步网络库——一律 `asyncio.to_thread` 卸载或用 `a` 前缀异步变体。同步 SQLite 只允许在守护线程 / CLI / 测试上下文使用。护栏：运行时 `ConversationDB.connect()`/`retry_on_locked()`/`init()` 会告警（`CLOUDRA_DB_SYNC_ON_LOOP=raise` 抛错、`=off` 关闭），`tests/test_no_sync_on_loop.py` 静态扫描常驻。
- **执行面可靠性铁律**：调度器/guard 任何路径不得 kill 计算进程（取消只走用户/agent 显式 `cancel_requested` → Slurm scancel 既有路径）；进程存活判定一律 `infra/flocks.py` 的 flock 探测，禁止 PID/`ps`//proc 文本判定；核心链路禁止解析计算输入文件（资源量来自 agent 提交时显式申请）。子进程归属链：API/CLI →（detach）scheduler/kg_vec 守护（自持 flock，刻意长存，`cloudra stop` 的 marker 令其自检退出）；scheduler → guard → calculator.sh → 引擎 → 引擎的 external 子进程（如 MACE 由 ORCA 启动，**Cloudra 从不直接 spawn MACE**）；runtime_v2 → JS host（登记+`aclose()` 回收，父被 SIGKILL 时 host 靠 stdin EOF 自清理）。
- **禁止引入正则**：`re` 唯一允许出现的场合是**解析计算引擎输出文件的内容**（`tools/core/*_frames.py`、`log_parser.py`、`ts_guess.py` 这类按 Gaussian/ORCA/xtb 格式读日志与输入文件的纯解析）。**校验路径一律不准有正则**——尤其是**对 agent/LLM 输出**（最终消息、工具参数、声明文本、拒答判定、能垒抓取等）：取值与判定一律走结构化路径（pydantic schema 校验、`json.loads`、显式 token 扫描、枚举精确比对）或直接对物理量做确定性比对，且一律 fail-loud，绝不"匹配上就算过、匹配不上就静默取默认"。理由：正则匹配自然语言/畸形文本是"看起来能跑"的假校验，无法枚举反例、抓错一处即静默错判，且与"证据必须可验证"的项目前提直接冲突。**评分/校验链路对 agent 输出的正则已清除**（`benchmark/refusal.py` 的行为分类与 `benchmark/backend.py` 的能垒抓取都改成只读交付物；`tests/test_benchmark.py::test_scoring_modules_do_not_import_regex` 是常驻护栏）：不得再引入，也不得把最终消息散文接回评分。
- 不引入项目未依赖的库；可选能力走 `pyproject.toml` 的 extras（chem/browser/pdf/visual/dev，`all` 聚合全部）。
- 改了结构、命令或约定时同步更新本文件。
- 未经明确要求不做 git 提交/推送等变更操作。
