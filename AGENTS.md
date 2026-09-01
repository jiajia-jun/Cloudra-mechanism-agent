# AGENTS.md — Cloudra 项目指南

给 AI 助手与新贡献者的仓库导航。项目定位与三层架构（control plane / research runtime / execution plane）见 `README.md`，这里只讲代码布局、边界约定与开发命令。本文件是**地图不是手册**：每个模块只记职责与坑点，细节读代码。

## 命令

```bash
uv run pytest -q tests/            # 全套测试
uv run pytest -q tests/test_dag*   # 聚焦某个子系统（按文件名前缀选）
uv run ruff check cloudra tests    # lint（select E/F/W/I，line-length 120 但 E501 不强制）
cloudra                          # 构建并启动 Web 前端（API + SPA 单端口；顺带 detach 拉起计算调度守护进程与知识向量服务）
cloudra scheduler                # 前台运行计算调度守护进程（单实例 flock；CLOUDRA_SCHEDULER=off 禁止自动拉起）
uv run python -m compileall -q <改动文件>   # 改完先做语法检查
```

入口：`cloudra`（CLI，`cloudra/cli.py`：默认启动 Web 服务并打开浏览器，`web`/`config`/`skills`/`backup`/`knowledge`（含 install/uninstall/status）/`scheduler` 子命令；任务执行面已收敛到 runtime_v2，CLI 不直接跑任务）。HTTP 控制面唯一实现是 `cloudra/services/api_v2/` 包（uvicorn 以 `cloudra.services.api_v2:create_default_v2_app` factory 拉起，同端口托管 SPA）。Python >= 3.11，POSIX-only（ flock/nice 依赖 fcntl 与 POSIX 语义）。

**v1 已删除**：旧 `services/api*.py`/`service.py`、`runtime/` 执行核心、`core/react.py`、Flet `ui/`、Android 全家桶、device 链均已移除；会话库的六张 legacy 表（`subagent_requests`/`approvals`/`scheduled_reminders`/`client_commands`/`interactions`/`hub_posts`）及其全部读写函数也已移除（v2 审批/提问走 `runtime_v2/pending.py`，提醒走 `runtime_v2/reminders.py` 内存定时器，子 Agent 状态走 core.agents 投影）。继续服役的共享底座：`core/agent.py`、`core/supervisor.py`、`runtime/` 的 prompt_assembler/environment_observer/monitor/compute_executor、`services/session_store.py` + `nodes.py`、`persistence/`（除 conversation_repo/case_bank/context_stats）、`infra/`（除 presentation/email_listener/mobile_storage/native_bridge 等）。

## 模块地图（cloudra/ 包）

包根：`cli.py`、`web_launcher.py`（启动 Web 前端并开浏览器）、`calculator.sh`（package-data 资源）。实现按职责分以下子包：

**`core/` — 共享基类与督导**

- `agent.py` — `Agent`/`Coordinator`/`Follower` 基类与权限模型宿主（v2 会话不经过这里的执行方法）。
- `supervisor.py` — 科学督导，只在 `dag_guided` 模式运行：接受/驳回机理草稿、复核 CallReview 绑阶段；对 delivery 图只读。报告由 `DagController._deliver_supervisor_report` 回投 Coordinator。
- `dag/` — DAG 引导编排子系统（包根一级），见下节。
- `runtime/` 只剩共享件：`prompt_assembler.py`（确定性 system prompt 组装，读 `prompts/*.md` 按签名缓存；AGENTS.md 仅注入 Coordinator）、`environment_observer.py`、`monitor.py`（guard 进程：持 `guard-<id>.lock` 排他 flock → 经 `calc_lock_wrapper` 拉起 calculator（`calc-<id>.lock` 跨 exec 继承，nice +10 降权保控制面调度份额）→ 解析日志写终态 + state json；`--adopt` 对账接管模式：等 calc 锁释放后走同一收尾路径）、`compute_executor.py`（共享执行件 `run_compute`，认领方只有 `scheduler/` 守护进程与 benchmark 进程内实例）、`calc_lock_wrapper.py`（calc 锁 wrapper）。

**`scheduler/` — 计算调度守护进程（进程隔离）**

- `daemon.py` — `cloudra scheduler` 入口：与 API 彻底分家，状态同步只走中央 `compute.db` 的 `compute_jobs` 表（已迁出会话库，认领/对账每 tick 只打这一份）。职责：容量感知认领（`claim_ready_compute_job_with_capacity`，`priority DESC, id ASC`，槽位+CPU/内存记账，单库即全节点在用量）、对账器（30s+启动：running 的 local 作业逐条探 guard 锁——锁空闲 → spawn adopt guard 接管（conv_id 从行里取）；锁持有 → 续租防重领；Slurm 走既有租约重领）、孤儿 reap。单实例：`data_dir/scheduler.lock` 排他 flock。拉起与自愈由 `services/daemon_supervisor.py` 负责（见 services 节）。
- 资源模型：agent 提交时显式申请（`submit_compute_job` 的 `cpus`/`memory_mb`/`priority`），**核心链路零输入文件解析**；提交时对照节点 `resources`（`nodes.py` 的 `max_concurrent`/`cpus`/`memory_mb`，注册表可配，缺省半机保守值）硬校验，超容拒收。
- 完成通知：guard/Slurm 终态 CAS 写中央库；`ComputeNotifyBroker` 纯 DB 轮询（每 tick 一条全局小 SELECT 扫"终态且 notified_at NULL"，只投递 `conversation_id in core.projects` 的行，未加载项目跳过不落 notified_at，逐作业投递后落 notified_at）——API 宕机窗口内完成的作业不再丢通知。

**`services/` — 服务层 / 控制面**

- `api_v2/` — 包：`app.py`（create_v2_app/create_default_v2_app 装配 + lifespan + SPA 托管；lifespan 内挂 daemon-watchdog 任务——每 30s（`CLOUDRA_DAEMON_WATCHDOG_SECONDS`）`to_thread(ensure_daemons)` 自愈拉起死掉的守护进程，`CLOUDRA_DAEMON_WATCHDOG=off` 关闭，测试 conftest 默认 off）、`context.py`（`ApiContext` 显式持有 core/bus/protected，路由零闭包）、`models.py`（全部 pydantic 请求模型）、`sse.py`、`routers/`（runtime/projects/agents/knowledge/roles/pending/artifacts/dag/events 九组 APIRouter）。薄路由：写操作一律走 CommandBus；唯一例外是 `GET/PATCH /api/v2/runtime/config`（经 `mutate_config` 改 YAML 并刷新内存单例——per-agent 设置留空时的全局回落槽位，key 只写不读）。
- `daemon_supervisor.py` — 守护进程拉起判定链唯一事实源（`ensure_scheduler`/`ensure_kg_vec`/`ensure_daemons`）：env 开关 → 插件已装检查（kg_vec）→ 端口健康探测 → flock 单实例探测 → spawn_detached。**崩溃循环节流**：真实拉起成功后落 `<lock>.last_spawn` 时间戳（原子写），守护死掉但距上次拉起 <60s 则跳过并告警；活实例路径不读时间戳。web_launcher 启动与 api_v2 watchdog 共用这一套。
- `session_store.py` — 会话库中 `session` / `session_events` 两表的共享写入助手与只读查询（`create_session_record`/`ensure_session_record`/`finalize_session`/`arecord_event`/`insert_session_event` 等；compute_jobs 已迁出，六张 legacy 表已删除，本模块不再出现这些表。死代码清理后仅约 260 行，拆分评估为无必要）；`compute_store.py` — 中央 `compute.db` 的 compute_jobs 全部 SQL 入口（提交/认领/租约/终态 CAS/通知扫描，函数显式收 `ComputeDB`）；`nodes.py` — 多节点/Slurm 计算注册表。

**`persistence/` — 持久化 / 状态**

- `database.py`（`ConversationDB` 会话级 SQLite，承载 `session`/`session_events`/`artifacts`/`dag_*` 表，v2 里主要服务 DAG 与 artifacts；`ComputeDB` 中央计算作业库 `data_dir/compute.db`——compute_jobs 唯一宿主，schema 新建即新版、无迁移）、`artifacts.py`（不可变产物快照 + 短期下载授权）、`memory.py`（长期记忆 MEMORY.md）、`core/message_history.py`（JSONL 消息历史）。
- `paths.py` — data_dir 下所有路径的**唯一事实来源**；`fs_utils.py` — 原子写；`workspace.py` — 工作区受限读写。

**`knowledge/` — 化学知识库（chem-kb）**

与 `runtime_v2/knowledge.py`（图书馆协议，管合并排序）互补：本包管存储与检索。

- `store.py` — chem_kg.db 的 DDL/导入/查询（sync-only，async 调用方 `to_thread`）。**读路径只读、缺库返回空绝不建库**；写路径只有 `ensure_schema`/`import_csv`，导入幂等。**v11 双语**：实体 `props` 列装载 `label_en`（中文 label 是唯一事实源，英文挂在同一 `kb:{id}` 上；props 属 FTS 索引列故英文查询自动可搜图谱），`search_graph` 行透传 `label_en`。
- `plugin.py` — 单一混合 provider（`cloudra.knowledge.plugin:plugin`）：语义通道（向量微服务 `CLOUDRA_KG_VEC_URL`，异常记 warning + `last_health` 后该通道为空绝不抛）+ 图谱通道（本地 SQLite）+ 模糊兜底（`fuzzy.py` 扫 `vector_store/cards.jsonl` 子串 AND）。配额结构性保证多通道全带上（limit=5 → 语义 3 + 图谱 2），单通道空时按优先级链补位。只返回 `KnowledgeEntry` 实例。**v11 双语**：ASCII 主导查询的图谱条目 title 优先 `label_en`（回退 label）；向量库 cards.jsonl 每卡 zh+en 双行，微服务 `/search` 支持 `lang` 参数且同 card_id 去重。`health()` 实时代理微服务 /health 并叠加最近检索错误。
- `health.py` — 三通道健康聚合唯一实现（`knowledge_health()`：semantic/graph/fuzzy），API `GET /api/v2/knowledge/health` 与 CLI `cloudra knowledge status` 共用。
- `installer.py` — `cloudra knowledge install/uninstall` 经 `add_plugin`/`remove_plugin` 幂等增删 config.yaml 的 plugins 条目（不再直编 YAML）。CLI：`cloudra knowledge import/stats/export/search/install/uninstall/status`（数据默认取 `kg_data/`）。

**`base/` — 数据类与基类**

- `skill_class.py` / `tools_class.py` — 加载器与基类；`tools_class.py` 持审批钩子 `use_approval_handler`（ContextVar），runtime_v2 的 `LegacyToolExecutor` 执行工具时总是设置它，未设置时 `request_approval` 直接抛错（legacy 总线回退已删；ask_user 同理走 `use_input_handler`）。
- `session_class.py` — 会话数据类。

**`infra/` — 支撑设施**

- `config.py`（LLMConfig/CloudraConfig；**磁盘 YAML 是唯一事实源**，唯一写入口 `mutate_config(fn)`＝flock 排他（`config.yaml.lock`）→ 读磁盘覆盖内存 → 应用 fn → 原子写回 → 就地刷新单例；序列化由 `model_dump` 派生，新增字段零写盘代码；`add_plugin`/`remove_plugin` 幂等；`save()`/`reload_config()` 已删除，测试重建单例用 `_reset_for_tests()`；`knowledge_vec_python` 字段指定向量服务解释器，缺省探测仓库根 `.venv-trans`）、`llm_client.py`（OpenAI 兼容传输层）、`logging_setup.py`（统一 `setup_logging`：幂等、RotatingFileHandler/stream 二选一、`CLOUDRA_LOG_LEVEL` 控级别；api_v2 落 `logs/api.log`，CLI 只让 warning+ 上屏）、`web_search_native.py`、`streaming.py`、`token_estimator.py`、`slurm.py`、`compute_utils.py`（guard 命令构建/detach 拉起，guard 日志落盘 `.cloudra/guard-<id>.log`）、`flocks.py`（fcntl flock 原语：执行面唯一的进程存活/互斥判定手段；`try_acquire_lock` 非阻塞 + `locked` 阻塞排他）、`operations.py`（数据目录备份/恢复）、`yolo_guard.py`（自动审批安全守卫）、`runtime_profile.py`、`json_args.py`（LLM 畸形 JSON 工具参数兜底）。

**`benchmark/` — 基准评测框架（独立于会话运行时）**

- `schema.py` — 任务 JSON 的唯一 schema（`TaskSpec`）；机理图边带原子映射键变化 `bond_changes`（[i, j] 对引用 query 的原子映射 SMILES 编号，键级降记 break、升记 form）；gold 能垒锚点另记 `barrier_type`（未注明为 null，不默认贴 Ea）与 `barrier_reference`（central_complex/reactants，仅元数据，评分只读 `barrier_kcal_mol`）；hard 档选择性锚点（竞争非对映 TS 的 ΔΔ 能垒差）走 `gold.selectivity`（`SelectivityReference`），绝不塞进 `barrier_kcal_mol`。
- `gen_easy_tasks.py` — 从 `ideapool/reaction_candidates/easy.md` 确定性生成 `ideapool/tasks/easy/*.json`；改题源后重跑 `python -m cloudra.benchmark.gen_easy_tasks`，`test_easy_tasks_regenerate_identically` 守卫同步。原子映射 SMILES 与 bond_changes 按 task_id 登记在 `_MAPPED_REACTANTS`/`_BOND_CHANGES`（漏登 KeyError）。
- `gen_normal_tasks.py` — normal 档同款生成器（`normal.md` → `ideapool/tasks/normal/N*.json`，只生成定稿 30 题 `TASK_IDS`，池子落选条目留档）。与 easy 的差异：多步 gold 图（中间体节点 + 逐基元步边）；登记拆到 `normal_registry/` 按族分文件（ai/yo/x/ru/qh.py，每题登记 mapped_reactants + 每步全体系映射 SMILES），**bond_changes 由生成器从相邻步映射 SMILES 差集自动推导、禁止手填**；校验 fail-loud（逐步映射号守恒/电荷守恒/去映射=池内 SMILES/每步有键变化），分族自检 `python -m cloudra.benchmark.gen_normal_tasks --only A1 ... --check`。task_id 加 N 前缀（normal X 族与 easy X1 撞号）；single_step 一律 false；accuracy σ=2.0、无锚点题 `enabled=false`；`test_normal_tasks_regenerate_identically` 守卫同步。
- `gen_hard_tasks.py` — hard 档（立体化学档）同款生成器（`hard.md` → `ideapool/tasks/hard/H*.json`，只生成定稿 20 题；登记拆到 `hard_registry/`（ab/de/fgk/hi/jl.py，格式契约见其 `__init__.py`），映射 SMILES **保留立体标记**（去映射校验立体敏感，标错即 fail-loud）。hard 特有：gold 图带竞争立体化学副通道（registry `competing` 键：副产物/副中间体节点 + 副 TS 边，子图覆盖要求两条 TS 都交付）；锚点路由 `anchor` 键——"selectivity"（ΔΔ 能垒差入 `gold.selectivity`（`SelectivityReference`），accuracy 暂 disable 待 runner 支持 spread 评分）/"barrier"（绝对垒如 HH1 消旋 ΔG‡ 23.5 入 `reference_computation`，accuracy σ=2.0 照常）/None（无锚点）；rubric 一律 `stereo_tier_rule="hard_stereo_costly"`（runner `_ged_config_for` 已接线到 `GedConfig.stereo_free`）。分族自检 `--only ... --check`；`test_hard_tasks_regenerate_identically` 守卫同步。
- `graph_similarity.py` — 化学参数化图评分，默认**子图覆盖**打分（gold 嵌入交付图即满分，多出不罚）；`GedConfig(subgraph_scoring=False)` 退回对称 GED 诊断。RDKit 可选，缺失时节点代价退化为 SMILES 集合相等。
- `integrity.py` / `selfconsistency.py` / `accuracy.py` — 三层取证评分：证据绑定（`smiles:` 注释行；机理图形状的 JSON 不算证据；骨架级 partial credit；`binding_quality` 作 composite 乘性因子）→ 鞍点/IRC/极小值物理自检 → 能垒高斯容差评分。
- `method_policy.py` — 方法白名单拦截判定（纯函数；`submit_compute_job` 读 input_file 内容判定；bash 层解析 heredoc/重定向写入的 QM 输入；**无法解析方法时 fail-closed**）。`policy_stage.py` — 运行时执行点 `MethodPolicyStage`。
- `backend.py` — runtime_v2 后端（每题一个进程内 RuntimeCore+管线；yolo 无人值守；数据目录隔离由 CLI 负责 `CLOUDRA_DATA_DIR`）；返回 `BackendResult`（最终消息原文 + 提取的能垒——最终消息是拒答分类的输入）。`api_pool.py` — API 端点池防 429（`--api-pool pool.json`）。
- `refusal.py` — 拒答行为分类与跨档统计：每题归 answered/refused/failed（v1 确定性启发式：有交付=answered、无交付+明确拒答声明=refused、其余=failed；只判行为不评理由，拒答质量留给 LLM judge 诊断层）；ground truth = `rubric.expected_outcome`（CORRECT_REFUSAL 应拒、其余应答）；`refusal_stats` 出 TP/FP/FN/TN 与 precision/recall/F1（分母为零记 None）。impossible 档主指标即跨档拒答 precision/recall——单档拒答率会被"什么都拒"刷分。
- `runner.py` — `BenchmarkRunner` + 专用 benchmark.db（同步 sqlite3，仅 CLI/测试上下文）；composite = (0.5·graph + 0.2·selfconsistency + 0.3·accuracy) × binding_quality，零证据绑定时倒扣 `no_evidence_penalty`；每题另记拒答 outcome（runs 表 outcome 列，旧库整表重建迁移）与最终得分正交。CLI：`python -m cloudra.benchmark`（`--backend none/runtime_v2`、`--only`、`--timeout`、`--concurrency`；`--tasks-dir` 可重复传入多目录做跨档拒答统计）。

**`runtime_v2/` — 事件驱动内核（推理循环唯一实现）**

- 骨架：`schemas.py`（API 类型唯一来源）、`roles.py`（角色权限唯一来源 `BUILTIN_ROLES`）、`events.py`（EventLog/EventHub）、`core.py`、`apply.py`（`apply_event` 唯一状态应用器，无守卫，恢复重放与在线路径共用；等价门禁 `test_runtime_v2_replay_equivalence.py`）、`effects.py`（EventDraft + Effect 联合与 Decision：EnsureDir/ScheduleAgent/CancelRunner/DeliverMessage/PatchApiKey + ResultRef）、`commands.py`（CommandBus 四拍：纯 decider → append+publish+persist → apply_event → _execute_effect；`agent.message` 对 failed/cancelled agent 自动 reopen；agent.compact/approval.decide/interaction.respond/context.inject 保留薄 wrapper）。**禁止在 apply_event 之外写状态**。
- `agent_host.py` — AgentSession 状态机：restart = 保留身份开新 run，只有 LLM 对话原文不跨 run（有效上下文靠 goal/DAG/memory/工作区每轮外化重建 + 上下文树种子注入）；`wake()` 统一苏醒语义（succeeded/queued 开新 run、failed/cancelled 重开、waiting 续跑、running 不动）；重开终态 agent 落 `agent.context_reset` 事件。
- `agent_runner.py` — 每 Agent 一个 async task；turn 崩溃原地自动重试（默认 2 次退避，落 `run.retry`）；视觉回注（visual_mode × supports_vision 双开才写 image_url parts）；run 结束的 finalize（LLM 摘要 + HANDOVER 重写）**detach 成独立任务**（内联会压住状态迁移吞掉唤醒）。
- `turn_pipeline.py` — 固定轮次管道：`llm.chunk` 只发 EventHub（不落 log/不持久化）；每轮完整 reasoning 落持久 `agent.thinking`；`NoticeManager.collect` 只在此处拼进 LLM 消息（先 pins 再 drain push）；loop 护栏（同一工具调用连续重复 3 次起落 `loop.detected` + push 警告，不硬 block）；tool.finished 汇流处把工作区图片登记为 artifact。
- `policies/` — permission/dag/goal/schedule 四个 PolicyStage（新 harness 能力只加 stage；dag stage 含 stop 交付门禁 `audit_stop`；goal/dag 常驻注入经 `notices.pin`）。状态纪律：GoalStage 决策已纯化（`resolve_goal_content`，文件 IO 由 shell 经 `PipelineContext.goal` 传入）；ScheduleStage 的 stop 拦截握手、DagPolicyStage 的 controller/窗口缓存为**刻意易失**（重启即弃，安全语义如此），副作用豁免与理由见各模块 docstring。
- 其余组件：`mailbox.py`（统一投递，支持 images 附件）、`pending.py`（审批/ask_user 内核 broker，事件投影 + future 挂起；**重启恢复时孤儿审批/提问显式落 `approval.expired`/`interaction.expired`**，agent 唤醒见明确终态）、`reminders.py`（schedule 拦截 + 内存定时器 + startup rearm）、`email_listener.py`（IMAP 收件监听投递给最近活跃项目的 coordinator）、`notices.py`（pin/push 注入，已事件化）、`compaction.py`（手动压缩 + LLM 400/413 超窗时紧急压缩重试一次；**compact 请求走 `compaction.requested` 事件**，`core.pending_compactions` 是其投影）、`context_tree.py`（事件溯源上下文树：run 摘要 + HANDOVER 快照 + 新 run 种子构建）、`transcript.py`（项目级完整 Markdown 转录，消融诊断用）、`subagent_bridge.py` / `hub_bridge.py`（SubAgentLauncher/SubAgentSwarm/agent_hub 的 v2 原生实现，由 `LegacyToolExecutor` 按名拦截）、`knowledge.py`（知识 provider 协议与图书馆检索，证据分层 L1>L0>L2、证伪降权不删除）、`plugins.py`（通用插件机制：search/on_event/setup hooks，配置项 "pkg.module:attr"）、`adapters.py`（旧 LLMClient/工具注册表/PromptAssembler 桥接；含模型原生联网搜索与 visual 门控）、`persistence.py`（事件表 + 快照 + 增量重放；快照只是**节流缓存**，meta 存每项目 `last_seqs`，恢复按 `events_after(last_seqs)` 逐项目 ORDER BY rowid 增量重放；**恢复时把仍处于 running/waiting 的 agent 落 failed**——run 只在内存，发消息即可自动重开）。状态外化契约（事件可推导 vs 刻意易失两类清单）见 `core.py` 模块 docstring。

**UI 前端**

- `frontend/` — React SPA（唯一前端）：`src/App.tsx`（项目栏 + AgentBar / 对话 / Inspector 六标签；斜杠命令含 `/visual` 视觉模式开关）、`GlobalConfig.tsx`（全局 LLM 回落槽位编辑）、`AttentionDock.tsx`（跨项目审批/提问提醒坞，可就地处置）、`AuditLog.tsx`（审计日志懒加载分页 + full log 转录下载）、`DagPanel.tsx`（DAG 机理图面板）、`KnowledgePanel.tsx`（chem-kb 浏览面板，顶部三通道健康状态条）、`api.ts`（v2 客户端）、`timeline.ts`（对话时间线拼装纯函数，配单测）。`npm run build` 通过才算前端可用；开发 `npm run dev`；生产由 uvicorn 同端口托管 `dist/`。

**能力与角色**

- `tools/` — 按领域分组的工具（Bashtool/Chemtool/Searchtool/Writetool/Plantool 等；QM 输入/解析双引擎 Gaussian/ORCA：`qm_input_writer`/`log_parser`/`format_converter`；DAG 面是 `dag_tools/` verb 族）。`tools/registry.py` 注册（`ToolRegistration` 可声明 `dag_review`/`dag_compute_entry`/`visual` 等语义），下游只能经 `tools/capabilities.py` 投影查询，**禁止在别处新建工具名集合**。`tools/core/` 含权限模型、审批流水线、gaussian/orca frames 解析（纯函数）与各守卫（coord_guard/bash_habit_guard/delegation_guard/memory_scope_guard）。Managetool 的 SubAgentLauncher/SubAgentSwarm/get_subagent_report/agent_hub/schedule 五类只保留 schema 作线缆格式，执行被 runtime_v2 按名拦截。工具**无持久状态**；输出 schema 成功字段统一 `is_success`，给模型的文本一律英文；超大工具结果（>30k 字符）全文落盘 `.cloudra/tool_output/`，模型只收截断摘要。
- `subagents/` — 领域子 Agent（8 个角色；`registry.py` 是 a-1..a-8 显式注册清单）。
- `prompts/*.md`、`skills/*` — 角色 prompt 与科研方法技能包。

## dag/ 子系统（DAG 引导编排）

按会话 opt-in：`orchestration_mode` ∈ `standard`（默认，不读不写图）/ `dag_record`（harness 自动接受草稿，Coordinator 自绑阶段，Supervisor 不运行）/ `dag_guided`（Supervisor 接受草稿、逐调用复核绑阶段）。可经 `agent.settings_update` 中途切换（前端模式下拉同步 PATCH 项目内所有 agent）。

- `models.py` — 共享类型：可写图元素只有 delivery（`OccurrenceNode`/`ElementaryStepEdge`）；阶段模型（`StageKind`/`StageState`/`StageContract`，list 顺序即允许绑定顺序）；`CallReview` 复核收件箱行；`MechanismDraft`；`GraphOperation` 命令联合（`AddLink` 写入即拒 `process_graph_removed`）。旧数据形状只读兼容。
- `store.py` — 单张 delivery 图持久存储（变更日志 + 物化视图）；`dag_drafts`（accepted 草稿存在即 mechanism_accepted）；`dag_call_reviews`（append-only 直连 INSERT）；证据引用存关联表 `dag_evidence_bindings`（读路径以它为准）。
- `engine.py` — 事务化变更引擎（原子批次、乐观 revision、无环校验）；Supervisor 对 delivery 只读，Coordinator 设计 delivery，模型只能以 pending 阶段创建元素；`remove_edge` 必须带 rationale；`apply_stage_verdict()` 执行阶段顺序守卫（前置 required 未决则 `stage_out_of_order`；`ts_guess` advisory 永不满足 ts_opt/frequency；rejected 可重绑）。
- `completion.py` — 交付覆盖率确定性评估 `evaluate_delivery()` 与 prompt 投影。`delta.py` — 单次工具调用后的图变更摘要。`substantive_gate.py` — 机理接受前的计算门槛（拦截 `submit_compute_job` 等实质计算入口）。
- `controller.py` — harness 集成门面 `DagController`（由四个 mixin 组合而成，实现按职责分居）：`supervision.py`（督导触发收口；`_SUPERVISION_STATES` 仍是 mixin 上的单一类级可变 dict，跨实例共享语义不变）、`evidence_inbox.py`（CallReview 入箱——只限 registry 声明 `dag_review=True` 的工具与计算作业终态——、`review_call`/`bind_stage_for_call`（从 tool_call_id 解析 ref，deriver 检查如 n_imag==1）、`submit_evidence_for_review`（白名单外工具的证据通道）、模块级 `enqueue_compute_review`）、`stop_audit.py`（`audit_stop` 交付覆盖率审计）、`drafts.py`（`propose/accept_mechanism`）。DAG prompt 注入与工具证据持久化留在门面。

关键不变量：图存储是权威（不在模型上下文里）；证据是不可变记录/产物的类型化引用；删除必须带理由且留在变更日志；模型声明不能标记交付完成，证据等级由 harness 从阶段确定性派生；阶段严格按契约顺序绑定；`rejected` 不是处置——是仍欠的开放缺口，只能重绑或显式 skip/not_applicable-with-reason 关闭；`not_applicable`（带理由）计入完成且不算欠账；`submit_compute_job` 调用永远不是证据（只认完工作业的解析产物）。

## 测试约定（tests/）

- 按文件名前缀分组：`test_dag_*`（DAG）、`test_runtime_v2_*`（新内核）、`test_compute` / `test_slurm`（计算执行）、化学工具各一、其余为基础设施单测。
- `conftest.py` autouse 隔离 data_dir 到 tmp_path；不要在测试里写真实数据目录。
- 跳过均按环境探测：缺 `crest`/`xtb` 二进制、无 symlink 权限、非 POSIX。无需要真实 LLM key 的测试。
- 测试替身（fake/stub）签名要对齐真实接口，建议带 `**_kwargs` 防接口加参后变红。

## 顶层散件

- `kg_data/` — 知识图谱 CSV（kg-entities/kg-relations/kg-stats，utf-8-sig；`cloudra knowledge import` 的输入）。v12 后含动力学讲义增量、v12.1 移除软件安装类目：14,203 实体（props.label_en 全覆盖）/ 10,266 行级关系（source 含 `kb:dyn01`~`kb:dyn08`）。
- `ideapool/reaction_candidates/` — benchmark 候选池（easy.md 已定稿 30 题；normal.md 48 条池、已定稿 30 题见文末"定稿圈定"；hard.md 51 条池（立体化学档，2026-08-31 升级为线缆格式）、已定稿 20 条见文末"定稿圈定"（C 族 1,3-偶极按规则整体剔除）；impossible.md 70 条池（强多参考/拒答档：初批 A–E 32 + 2026-08-31 扩建 F–J 38），已定稿 20 条见文末"定稿圈定"——选题意图为单参考不可算体系的科学拒答，gold 是拒答质量而非机理图，含兄弟题对照设计）；打标台为自包含 HTML（normal_tagging.html / hard_tagging.html / impossible_tagging.html，打标存 localStorage 不回写 md），由 `scripts/gen_normal_tagging.py` / `scripts/gen_hard_tagging.py` / `scripts/gen_impossible_tagging.py` 从对应 md 重新生成（条目变更后重跑）。
- `vector_store/` — 知识卡片 bge-m3 向量五件（cards.jsonl / vectors.f16.npy / meta.json / retrieve.py / encode.py）；`scripts/kg_vec_service.py` 微服务只读这套文件（向量侧依赖 torch/sentence-transformers 全部留在外部 .venv-trans，cloudra venv 不装 torch；kg_vec 跑在 .venv-trans 解释器下、cloudra 包不可导入，只能 stdlib 自理）。**插件已装时自动 detach 拉起该服务**（拉起判定链在 `services/daemon_supervisor.py`，web 启动与 api_v2 watchdog 共用；flock 单实例 `data_dir/kg_vec.lock` 由服务进程经 `--lock-file` 自持，端口健康探测防重，`CLOUDRA_KG_VEC=off` 关闭；解释器取 config `knowledge_vec_python`，缺省探测仓库根 `.venv-trans`）。查询模型与 meta.json 记录的库编码模型不一致时启动即告警；一键重编码入口 `vector_store/encode.py --model 模型名`；bge 系模型自动加专用查询前缀。v12.1 后 17,188 行（8,594 卡 zh+en 成对，其中动力学 1,569 卡）。
- `deploy/node-registry.example.json` — 多节点/Slurm 注册表示例。
- `docs/` — 专题文档索引；`docs/superpowers/plans/` 存放设计计划（如 DAG 设计）。
- `install.sh` / `install.ps1` — 安装脚本；`web.sh` / `web.ps1` — 开发便捷启动脚本；`README_CN.md` 为中文 README。`build/`、`.worktrees/`、`cloudra.egg-info/` 为构建副产物，勿手改。
- `软著申请材料/`、`copyright_docs/`、`*.pdf` 研究报告 — 申报材料，非代码。软著源程序清单由 `scripts/gen_copyright_source.py` 重建（改代码后重跑）；`软著申请材料/06_LaTeX排版/` 用 conda 环境 `tectonic` 编译（一次性）。

## 工作约定

- **禁止补丁式修复**：项目仍是 beta、尚未上线，**不考虑向后兼容**。发现问题必须在架构级根治——能改数据结构就改数据结构、能删代码就删代码、能拆模块就拆模块；不允许打补丁盖过问题（不留 legacy 回退分支、不加兼容 shim、不保留死代码、不用"文档注明"替代修复）。任何修复必须配能直接把问题测红的测试，先红后绿，修完即绿。
- 最小改动：修 bug 不顺手重构；新代码跟随所在文件的既有风格与注释密度。
- **事件循环线程禁止同步阻塞调用**：`async` 函数体内不得直接调用同步 SQLite（`db.connect()`/`retry_on_locked`）、`time.sleep`、`subprocess.run`、同步网络库——一律 `asyncio.to_thread` 卸载或用 `a` 前缀异步变体。同步 SQLite 只允许在守护线程 / CLI / 测试上下文使用。曾因此造成跨进程 5 分钟级 "database is locked" 死锁。护栏：运行时 `ConversationDB.connect()`/`retry_on_locked()`/`init()` 会告警（`CLOUDRA_DB_SYNC_ON_LOOP=raise` 抛错、`=off` 关闭），`tests/test_no_sync_on_loop.py` 静态扫描常驻。
- **执行面可靠性铁律**：调度器/guard 任何路径不得 kill 计算进程（取消只走用户/agent 显式 `cancel_requested` → Slurm scancel 既有路径）；进程存活判定一律 `infra/flocks.py` 的 flock 探测，禁止 PID/`ps`//proc 文本判定；核心链路禁止解析计算输入文件（资源量来自 agent 提交时显式申请）。
- 不引入项目未依赖的库；可选能力走 `pyproject.toml` 的 extras（chem/browser/pdf/visual/dev，`all` 聚合全部）。
- 改了结构、命令或约定时同步更新本文件。
- 未经明确要求不做 git 提交/推送等变更操作。
