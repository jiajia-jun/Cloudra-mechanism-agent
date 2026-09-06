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

停止语义边界（取消/全停契约）：① 取消单个 agent（`POST /api/v2/agents/{id}/cancel`）立即取消其 run task 与该 session 全部登记后台任务，之后不再新发 LLM 请求，本地终态照常持久化；② 没有项目级一键取消——逐 agent 取消，或以 `cloudra stop` 全停；③ 服务关闭顺序固定：先停准入与 watchdog 自愈，再取消并 await 全部推理/收尾任务，然后关流/客户端，最后回收本进程拥有的 JS host；④ 已发到 provider 的请求远端不可撤销（账单照算），本地保证停止读取/重试/新发并尽量关连接（流式 socket 层 RST）；⑤ 单 agent 取消不连带杀 scheduler/guard/QM 计算（科研计算独立于推理运行），只有 `cloudra stop` 显式全停才回收守护并防自愈拉起；⑥ 只终止有明确归属的任务/进程，禁止按 python/node/用户名等宽字符串匹配杀进程，子进程必须 wait/reap 而非只发信号。

**v1 已删除**：旧 `services/api*.py`、`runtime/` 执行核心、`core/react.py`、Flet `ui/`、Android/device 链、会话库六张 legacy 表均已移除（v2 审批/提问走 `runtime_v2/pending.py`，提醒走 `runtime_v2/reminders.py`，子 Agent 状态走 core.agents 投影）。无兼容回退，别再引用这些名字。

## 模块地图（cloudra/ 包）

包根：`cli.py`、`web_launcher.py`（启动 Web 前端并开浏览器）、`calculator.sh`（package-data 资源）。

**`core/` — 共享基类**

- `agent.py` — `Agent`/`Coordinator`/`Follower` 基类与权限模型宿主（v2 会话不经过这里的执行方法）；`message_history.py` — JSONL 消息历史。

**`runtime/` — 执行面共享件**（v1 执行核心已删，只剩这些）

- `prompt_assembler.py`（确定性 system prompt 组装，读 `prompts/*.md` 按签名缓存；AGENTS.md 仅注入 Coordinator）、`environment_observer.py`。
- `monitor.py` — guard 进程：持排他 flock → 拉起 calculator（nice +10 降权保控制面调度份额）→ 解析日志写终态。**终态判定按引擎分派文本终止标记**（ORCA 认 `ORCA TERMINATED NORMALLY`、xtb 认 `normal termination of xtb`，与 log_parser 共用 `tools/core/` 的 frames 原语；优化另有"跑满步数未收敛"第二判据判 failed），**cclib 只取数据不定成败**。
- `compute_executor.py`（共享执行件 `run_compute`，认领方只有 scheduler 守护与 benchmark 进程内实例）、`calc_lock_wrapper.py`、`compute_notify.py`（`build_compute_knowledge_query` 查询构建）。

**`scheduler/` — 计算调度守护进程（进程隔离）**

- `daemon.py` — `cloudra scheduler` 入口：与 API 彻底分家，状态同步只走中央 `compute.db` 的 `compute_jobs` 表。职责：容量感知认领（槽位+CPU/内存记账）、对账器（探 guard 锁：锁空闲→spawn adopt guard 接管，锁持有→续租防重领）、孤儿 reap；单实例 `data_dir/scheduler.lock` 排他 flock。拉起与自愈由 `services/daemon_supervisor.py` 负责。
- 资源模型：agent 提交时显式申请（`cpus`/`memory_mb`/`priority`），对照节点 `resources` 硬校验超容拒收，**核心链路零输入文件解析**。`job_type` ∈ gaussian/vasp/orca/cp2k/xtb。
- 完成通知：`ComputeNotifyBroker`（`runtime_v2/compute_notify.py`）纯 DB 轮询终态行逐作业投递（API 宕机窗口不丢通知）；投递前自动检索 chem-kb 拼建议（无 provider/检索失败静默降级）。

**`services/` — 服务层 / 控制面**

- `api_v2/` — HTTP 控制面唯一实现（uvicorn factory 拉起，同端口托管 SPA）：`app.py`（装配 + lifespan + daemon-watchdog 自愈任务，测试 conftest 默认 off）、`context.py`（`ApiContext` 显式持有 core/bus，路由零闭包）、`models.py`（全部 pydantic 请求模型）、`sse.py`、`routers/`（九组 APIRouter）。薄路由：写操作一律走 CommandBus；唯一例外 `GET/PATCH /api/v2/runtime/config`。
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

- `config.py` — **磁盘 YAML 是唯一事实源**，唯一写入口 `mutate_config(fn)`（flock 排他 → 读磁盘覆盖内存 → 应用 → 原子写回 → 就地刷新单例）；`add_plugin`/`remove_plugin` 幂等；测试重建单例用 `_reset_for_tests()`。
- `llm_client.py` — OpenAI 兼容传输层；取消准入 `abort_event`（每次发送前/retry 后/fallback 前检查）；流式取消走 socket 层 shutdown+close 立即 RST，**高层 `resp.close()` 跨线程会卡锁，禁止走**。
- `flocks.py` — fcntl flock 原语，**执行面唯一的进程存活/互斥判定手段**；`compute_utils.py` — guard 命令构建/detach 拉起、`resolve_log_path`（统一的 log_path 来源）；`logging_setup.py`、`slurm.py`、`operations.py`（备份/恢复）、`yolo_guard.py`、`json_args.py`（LLM 畸形 JSON 工具参数兜底）等。

**`benchmark/` — 基准评测框架（独立于会话运行时）**

- `schema.py` — 任务 JSON 唯一 schema（`TaskSpec`）：机理图边带 `bond_changes`（键级降 break、升 form）；能垒锚点另记 `barrier_type`/`barrier_reference`（评分只读 `barrier_kcal_mol`）；hard 档选择性锚点走 `gold.selectivity`。
- `gen_easy/normal/hard/impossible_tasks.py` — 四档确定性生成器（`ideapool/reaction_candidates/*.md` → `ideapool/tasks/`）；**改题源后必须重跑生成器**，`test_*_tasks_regenerate_identically` 守卫同步。映射 SMILES 与逐题登记拆在 `*_registry/` 子包；bond_changes 由生成器从映射 SMILES 差集推导、禁止手填；校验 fail-loud。impossible 档特有：`pair_id` 双向互指（I 题拒答 × S 兄弟题作答）、`accessible=False` 节点入 `rubric.impossible_case`、query 统一带拒答协议句（I/S 同款不泄题）。
- `graph_similarity.py` — 化学参数化图评分，默认**子图覆盖**打分（gold 嵌入交付图即满分，多出不罚）；RDKit 可选。
- `integrity.py`/`selfconsistency.py`/`accuracy.py` — 三层取证评分：证据绑定（`smiles:` 注释行；机理图形状的 JSON 不算证据）→ 鞍点/IRC/极小值物理自检 → 能垒高斯容差评分。
- `method_policy.py`/`policy_stage.py` — 纯转引（实现在 `runtime_v2/method_policy.py` 与 `runtime_v2/policies/method_policy.py`）；**无法解析方法时 fail-closed**。
- `backend.py`（runtime_v2 后端，yolo 无人值守）、`api_pool.py`（API 端点池防 429）、`refusal.py`（拒答行为分类 answered/refused/failed 与跨档 TP/FP/FN/TN——impossible 档主指标即跨档拒答 precision/recall）、`runner.py`（`BenchmarkRunner` + 专用 benchmark.db；composite = (0.5·graph + 0.2·selfconsistency + 0.3·accuracy) × binding_quality，零证据倒扣）。CLI：`python -m cloudra.benchmark`。

**`runtime_v2/` — 事件驱动内核（推理循环唯一实现）**

- 骨架：`schemas.py`（API 类型唯一来源）、`roles.py`（角色权限唯一来源 `BUILTIN_ROLES`）、`events.py`、`core.py`、`apply.py`（**`apply_event` 唯一状态应用器；禁止在 apply_event 之外写状态**，恢复重放与在线路径共用）、`effects.py`、`commands.py`（CommandBus 四拍：纯 decider → append+publish+persist → apply_event → 执行 effect）。
- `agent_host.py` — AgentSession 状态机：restart = 保留身份开新 run，只有 LLM 对话原文不跨 run；`wake()` 统一苏醒语义。
- `agent_runner.py` — 每 Agent 一个 async task；turn 崩溃原地退避重试；run 结束的 finalize detach 成独立任务但经 `track_background` 登记（裸 create_task 会让取消/shutdown 碰不到它）；`RuntimeCore.aclose()` 是服务关闭唯一入口（cancel_all → 回收 JS host）。**统一运行结束门禁**：显式 stop 与无 tool_calls 的纯文本最终回复都在收尾前经 `_evaluate_completion_gate` 裁决（各 stage 的 `audit_run_end` 钩子取最保守：wait_background > wait_review > continue_work > allow_final）；同缺口指纹无进展退出有界计数，耗尽落 failed，不伪报完成。
- `supervision.py` — 事件驱动督导运行时入口（督导不在此跑 LLM）。Supervisor 是项目内唯一普通 runtime_v2 agent；**待办唯一事实来源是 DAG store**；通知按状态表（queued/running 投信箱、succeeded wake 开新 run、**failed/cancelled 不自动复活**），刻意走 `mailbox.deliver` + 条件 wake 而非 `agent.message`（其 decide 会自动 reopen 终态 agent）。
- `turn_pipeline.py` — 固定轮次管道：`llm.chunk` 只发 EventHub 不落盘；每轮 reasoning 落持久 `agent.thinking`；工具执行收口到 InvocationService；按 run 冻结的 `invocation_protocol` 做线缆路由校验。
- 调用生命周期：`event_writer.py`（有序持久化+幂等发布唯一写口）、`invocation_types.py`/`invocation_context.py`/`invocation.py`（durable requested → policy stages → started → executor 恰一次 → result_recorded → finished；per-agent 锁串行；**持久化失败抛 EventPersistenceError 不伪造终态**）。
- JS 协议（默认，`invocation_protocol` 可切回 traditional）：`tool_catalog.py`（协议感知线缆投影唯一来源，**禁止在别处新建工具名集合**）、`js_protocol.py`、`js_runtime.py`（每程序一个 node 进程跑 QuickJS-WASM 沙箱；**JS 堆不跨重启恢复、失败程序不自动重跑**；取消只 SIGTERM/SIGKILL JS host，绝不碰 scheduler/guard/QM 作业）、`js_host/`（Node 宿主；唯一依赖 quickjs-emscripten 手动 npm ci 安装，不入 git/wheel；威胁模型=本地单用户沙箱，不是 OS 沙箱）。
- `policies/` — permission/method_policy/dag/goal/schedule/knowledge 六个 PolicyStage（新 harness 能力只加 stage；method_policy stage 是 per-project 方法白名单执行点，在 submit_compute_job/qm_input_writer/bash 三层拦截；dag stage 的 stop 交付审计统一在 runner 收尾边界经 `audit_run_end` 进入）。各 stage 的易失状态纪律与副作用豁免见各模块 docstring。
- 其余组件：`mailbox.py`（统一投递）、`pending.py`（审批/ask_user 内核 broker；**重启恢复时孤儿审批/提问显式落 expired 终态**）、`reminders.py`（schedule 拦截 + 内存定时器 + `check_command.py` 只读检查命令 fail-closed 门）、`notices.py`、`compaction.py`（`compaction.requested` 事件驱动）、`context_tree.py`（事件溯源上下文树）、`transcript.py`、`subagent_bridge.py`/`hub_bridge.py`（子 agent 终态回传父邮箱并 wake）、`launch_groups.py`（非阻塞 swarm 并发组）、`knowledge.py`（证据分层 L1>L0>L2）、`plugins.py`、`adapters.py`、`persistence.py`（事件表 + 快照**节流缓存** + 增量重放；**恢复时把 running/waiting agent 落 failed**，为未完成调用/程序补终态，恢复路径绝不执行 executor/JS 进程/调度作业）。
- `compute_notify.py` — `ComputeNotifyBroker`（见 scheduler 节）；`email_listener.py` — IMAP 收件监听。

**`tools/` — 工具**

- 按领域分组（Bash/Chem/Search/Write/Plan 等；QM 双引擎 Gaussian/ORCA + xtb 解析 + 外部 MLIP 路由；DAG 面是 `dag_tools/` verb 族）。`registry.py` 注册（`ToolRegistration` 可声明 `dag_evidence_producer`/`dag_compute_entry`/`visual` 等语义），下游只能经 `capabilities.py` 投影查询，**禁止在别处新建工具名集合**。
- `tools/core/` — 权限模型、审批流水线、gaussian/orca/xtb frames 解析（纯函数）与各守卫。Managetool 的 subagent_launcher/subagent_swarm/get_subagent_report/agent_hub/schedule 五类只保留 schema 作线缆格式，执行被 runtime_v2 按名拦截。
- 工具**无持久状态**；输出 `is_success` 统一、给模型的文本一律英文；超大结果（>30k 字符）全文落盘 `.cloudra/tool_output/`，模型只收截断摘要。

**`subagents/`、`prompts/`、`skills/`**

- 8 个领域子 Agent（`registry.py` 是 a-1..a-8 显式注册清单）；`prompts/*.md` 角色 prompt；`skills/` 科研方法技能包。

**UI 前端**

- `frontend/` — React SPA（唯一前端）：`src/App.tsx`（项目栏 + 对话 + Inspector；斜杠命令）、`AttentionDock.tsx`（跨项目审批/提问坞）、`DagPanel.tsx`/`KnowledgePanel.tsx`/`AuditLog.tsx`、`api.ts`（v2 客户端）。`npm run build` 通过才算前端可用；生产由 uvicorn 同端口托管 `dist/`。

## dag/ 子系统（DAG 引导编排）

按会话 opt-in：`orchestration_mode` ∈ `standard`（默认，不读不写图）/ `dag_record`（harness 自动接受草稿，Coordinator 自绑阶段，Supervisor 不运行）/ `dag_guided`（Supervisor 接受草稿、逐调用复核绑阶段）。可经 `agent.settings_update` 中途切换。

- `models.py` — 共享类型：可写图元素只有 delivery（`OccurrenceNode`/`ElementaryStepEdge`）；阶段模型（list 顺序即允许绑定顺序）；`CallReview`（**source=explicit 才可消费**，legacy_auto/auto 仅审计）；`MechanismDraft`；`GraphOperation` 命令联合。
- `store.py` — 单张 delivery 图持久存储（变更日志 + 物化视图）+ `dag_drafts` + `dag_call_reviews`（append-only）+ `dag_evidence_bindings`（证据引用，读路径以它为准）。
- `engine.py` — 事务化变更引擎（原子批次、乐观 revision、无环校验）；`apply_stage_verdict()` 执行阶段顺序守卫（前置 required 未决则 out_of_order；rejected 可重绑）；`remove_edge` 必须带 rationale。
- `completion.py` — 交付覆盖率确定性评估 `evaluate_delivery()`；`substantive_gate.py` — 机理接受前的计算门槛。
- `controller.py` — harness 集成门面 `DagController`，由四个 mixin 组合：`supervision.py`（待办持久化后经 runtime_v2 的 `notify_supervisor` 按状态表通知）、`evidence_inbox.py`（**CallReview 唯一来源是显式送审 `submit_evidence_for_review`**；工具完成只登记证据快照/派生事实，不自动入箱）、`stop_audit.py`（`audit_stop` 四态 StopGate；隐式退出与显式 stop 到达同一结束门禁）、`drafts.py`。
- `requirements.py`/`review_requests.py`（结构化送审请求与裁决协议，contract_version=2，basis_fingerprint 不匹配不收裁决）/`evidence_facts.py`/`fact_adapters.py`/`supervisor_tools.py` — 支撑件，细节读代码。

关键不变量：图存储是权威（不在模型上下文里）；证据是不可变记录/产物的类型化引用；删除必须带理由且留在变更日志；模型声明不能标记交付完成，证据等级由 harness 从阶段确定性派生；阶段严格按契约顺序绑定；`rejected` 不是处置——是仍欠的开放缺口，只能重绑或显式 skip/not_applicable-with-reason 关闭；`not_applicable`（带理由）计入完成且不算欠账；`submit_compute_job` 调用永远不是证据（只认完工作业的解析产物）。

## 测试约定（tests/）

- 按文件名前缀分组：`test_dag_*`（DAG）、`test_runtime_v2_*`（新内核）、`test_compute`/`test_slurm`（计算执行）、化学工具各一、其余基础设施单测。
- `conftest.py` autouse 隔离 data_dir 到 tmp_path；不要在测试里写真实数据目录。
- 跳过均按环境探测：缺 `crest`/`xtb` 二进制、无 symlink 权限、非 POSIX。无需要真实 LLM key 的测试。JS 宿主集成测试额外探测 node>=22 + `js_host/node_modules/quickjs-emscripten`，缺失才 skip（最终验收要求真实 Node 跑通，不允许全 skip）；宿主侧自身测试用 `npm --prefix cloudra/runtime_v2/js_host test`。
- 测试替身（fake/stub）签名要对齐真实接口，建议带 `**_kwargs` 防接口加参后变红。

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
- 不引入项目未依赖的库；可选能力走 `pyproject.toml` 的 extras（chem/browser/pdf/visual/dev，`all` 聚合全部）。
- 改了结构、命令或约定时同步更新本文件。
- 未经明确要求不做 git 提交/推送等变更操作。
