# AGENTS.md — Cloudra 项目指南

给 AI 助手与新贡献者的仓库导航。项目定位与三层架构（control plane / research runtime / execution plane）见 `README.md`，这里只讲代码布局、边界约定与开发命令。

## 命令

```bash
uv run pytest -q tests/            # 全套测试
uv run pytest -q tests/test_dag*   # 聚焦某个子系统（按文件名前缀选）
uv run ruff check cloudra tests    # lint（line-length 120，select E/F/W/I）
cloudra                          # 构建并启动 Electron 前端（浏览器：cloudra web --browser）
uv run python -m compileall -q <改动文件>   # 改完先做语法检查
```

入口：`cloudra`（CLI，`cloudra/cli.py`：默认启动 Electron 前端，`web`/`config`/`logs`/`skills`/`backup` 子命令；任务的执行面已收敛到 runtime_v2，CLI 不再直接跑任务）。HTTP 控制面唯一实现是 `cloudra/services/api_v2.py`（由 Electron/前端进程内 spawn）。Python >= 3.11。

**v1 已删除**：旧 `services/api.py`/`api_v1.py`/`service.py`、`runtime/` 执行核心（runner/executor/workers/mobile_tasks）、`core/react.py`、Flet `ui/`、Android 全家桶、device 链均已移除；下列共享底座继续服役：`core/agent.py`（Agent/Coordinator/Follower 基类）、`core/supervisor.py`、`runtime/prompt_assembler.py` + `environment_observer.py`、`runtime/monitor.py`（计算任务日志监视子进程）、`runtime/compute_executor.py`（领取 `ready` 计算任务并拉起 guard/Slurm；`api_v2` lifespan 启动 `ComputeBroker`）、`services/session_store.py` + `nodes.py`、`persistence/`（除 conversation_repo/case_bank/context_stats）、`infra/`（除 presentation/tool_presentation/email_listener/mobile_storage/native_bridge/android_build）。

## 模块地图（cloudra/ 包）

根目录只留 `cli.py` / `__main__.py` / `__init__.py`（惰性兼容导出）；实现按职责分五个子包：

**`core/` — 共享基类与督导**

- `agent.py` — `Agent`/`Coordinator`/`Follower` 基类与权限模型宿主（supervisor、subagents、部分工具直接继承；v2 会话不经过这里的执行方法）。
- `supervisor.py` — 科学督导（SupervisorAgent、GraphSupervisor），只在 `dag_guided` 模式运行：接受/驳回机理草稿、复核 CallReview 并绑定阶段；对 delivery 图结构只读，不调度工作。
- `dag/` — DAG 引导编排子系统（仍在包根一级），见下节。
- 推理循环的唯一实现是 `runtime_v2/`（见下）；`runtime/` 只剩共享件：`prompt_assembler.py`（确定性 system prompt 组装：`load_role_prompt()` 读 `prompts/*.md`，按 (mtime_ns, size) 签名缓存；AGENTS.md 仅注入 Coordinator）、`environment_observer.py`（工作区快照）、`monitor.py`（计算日志监视子进程，由 `infra/compute_utils.py` 以 `python -m cloudra.runtime.monitor` 拉起；失败路径把可读原因落 `compute_jobs.last_error` 与 state json 的 `error` 字段）、`compute_executor.py`（`ComputeBroker` 扫描会话库 `claim_ready_compute_job`，本地任务 `launch_compute_processes(wait=False)` 后延长 lease 以免重复开算，Slurm 走 `run_slurm_compute` 并在轮询期间续租）。

**`services/` — 服务层 / 控制面**

- `api_v2.py` — 唯一的 HTTP 控制面（薄路由；写操作一律走 CommandBus，DAG/artifact 读直连 dag/ 与 persistence/artifacts）。
- `session_store.py` — 会话级 SQLite 的 schema 迁移与共享写入助手（tools_class 记录事件、dag/controller、artifacts 在用）。
- `nodes.py` — 多节点/Slurm 计算注册表（`submit_compute_job` 工具用）。

**`persistence/` — 持久化 / 状态**

- `database.py` — 会话级 SQLite（ConversationDB；v2 里主要服务 DAG 存储与 artifacts）。
- `artifacts.py` — 不可变产物快照（ArtifactService）与短期下载授权。
- `memory.py`（长期记忆 MEMORY.md，prompt_assembler 用）、`context_manager.py`（Agent 上下文文件；supervisor 与 dag/controller 用）。
- `paths.py` — data_dir 下所有路径的**唯一事实来源**；`fs_utils.py` — 原子写；`workspace.py` — 工作区受限读写。

**`base/` — 数据类与基类**

- `skill_class.py` / `tools_class.py` — 加载器与基类；`tools_class.py` 另持审批钩子 `use_approval_handler`（ContextVar）：设置后 `request_approval` 走钩子而非 SQLite 等待，runtime_v2 的 `LegacyToolExecutor` 执行工具时总是设置它（ask_user 同理走 `use_input_handler`）。
- `session_class.py` / `conversation_class.py` / `log_class.py` — 数据类。

**`infra/` — 支撑设施**

- `config.py`（LLMConfig/CloudraConfig）、`llm_client.py`（OpenAI 兼容传输层）、`web_search_native.py`。
- `events.py`（进程内/间事件门面）、`ipc.py`（会话级事件总线）、`streaming.py`、`token_estimator.py`。
- `slurm.py`、`compute_utils.py`、`operations.py`（数据目录备份/恢复）、`yolo_guard.py`（自动审批安全守卫）。
- `platform_utils.py`、`runtime_profile.py`（运行能力 profile，registry 的 runtime_profiles 过滤用）。

**包根一级子包**：`dag/`、`runtime/`（仅剩共享件，见上）、`tools/`、`subagents/`、`prompts/`、`skills/`。

**`runtime_v2/`（事件驱动新内核，按 S1 规格）**：`schemas.py`（API 类型唯一来源）、`events.py`（EventLog/EventHub）、`core.py`（RuntimeCore）、`commands.py`（CommandBus，先事件后状态；`agent.message` 对 failed/cancelled agent 自动 reopen 新 run，用户无需手动 restart）、`agent_host.py`（AgentSession 状态机；restart = 保留身份、开新 run，有效上下文靠 goal/DAG/memory/工作区每轮外化重建，只有 LLM 对话历史不跨 run）、`agent_runner.py`（每 Agent 一个 async task，真并发 + 可取消；turn 崩溃原地自动重试——history 只记录成功 turn，崩溃等于 LLM 请求未完成，重跑是干净重做，落 `run.retry` 事件，默认 2 次退避 2s/4s，仍失败才进 failed）、`turn_pipeline.py`（固定轮次管道，只依赖 PolicyStage；LLM 走流式，token delta 以 `llm.chunk` 只发 EventHub——瞬时不落 log、不持久化、不参与重放；每轮的完整 reasoning 落一条持久 `agent.thinking` 事件（历史轮次 thinking 刷新后仍可见）；带工具调用的中间轮次正文也落持久 `agent.message_emitted` 并立刻推到 hub（stop 轮由 runner 的最终消息承载，不重复；若等整轮工具结束再 flush，前端会在下一轮工具出现时把流式气泡清掉）；`NoticeManager.collect` 只在此处拼进 LLM 消息：先 pins 再 drain 一次性 push）、`policies/`（permission/dag/goal 三个 stage；新 harness 能力只加 stage；dag stage 含 stop 交付门禁——dag 模式调用 `stop` 时经 `DagController.audit_stop` 审计交付覆盖率，有未决 gap 且声明 complete 则 block，项目里有未终态兄弟 agent 时 stop 视为挂起不审计；dag_guided 下督导运行经 `_SupervisionShell` 投影为复用的壳 agent 会话（角色 `supervisor`，不走 LLM 管线，只作 UI 状态投影；壳 spawn 被拒时降级为无投影，不影响督导本体与父 turn）；goal/dag 的常驻注入经 `notices.pin`，不再直接 append）、`mailbox.py`（用户/Agent 间统一投递）、`pending.py`（审批与 ask_user 交互的内核 broker：请求落 `approval.requested`/`interaction.requested` 事件 + future 挂起，agent 翻 waiting_approval/waiting_input；决策经 `approval.decide`/`interaction.respond` 命令解 future；列表为事件投影；请求在轮内自发布到 hub，决策事件由 CommandBus 统一 flush；run 取消时自动过期）、`reminders.py`（`ReminderBroker`：拦截 `schedule` 工具，提醒落 `reminder.scheduled/cancelled/fired`，`schedule_id` 用事件 seq；内存 asyncio 定时器到点经 `agent.message` 投递 `[Reminder]` 并 reopen 终态 agent；FastAPI startup `rearm_all()` 从事件投影重建，过期立即触发）、`notices.py`（`NoticeManager`：`pin`/`unpin` 常驻注入与 `push` 一次性注入，统一渲染为 system 消息）、`compaction.py`（手动上下文压缩：压缩 runner 内存 history，一轮非流式 LLM 摘要 + tool 配对边界对齐；命令 `agent.compact` 置 pending，runner 在轮边界执行，发 `compaction.requested/started/finished`）、`subagent_bridge.py`（Managetool 三工具 SubAgentLauncher/SubAgentSwarm/get_subagent_report 的 v2 原生实现：经 CommandBus spawn 子 agent，launcher/swarm 支持 is_wait 同步等待与父取消级联，swarm 按 `{{item}}` 模板展开 + 并发上限；a-1..a-8 映射到 explorer/writer/researcher/small_mol/md/dft/experiment/env 角色；父非 standard 模式时子 agent 用 dag_record；spawn 时子 agent 继承父的 yolo（前端 YOLO 是项目级开关：写项目 defaults + 级联 PATCH 现存 agent，Inspector 里的 per-agent 勾选是单 agent 覆盖）；由 `LegacyToolExecutor` 在工具执行前拦截）、`hub_bridge.py`（`agent_hub` 论坛的 v2 原生实现：post 落 `hub.posted` 事件（事件日志即论坛存储），browse/read/search 为事件投影（模糊评分复用 legacy 纯函数），to_agent/回复通知与 call 走 `Mailbox.deliver`，call 到角色名时经 CommandBus spawn 新子 agent；同样由 `LegacyToolExecutor` 拦截）、`adapters.py`（旧 LLMClient/工具注册表/PromptAssembler 到新协议的桥；含模型原生联网搜索：命中适配器时剥外置 `web_search` 工具、注入 provider 侧搜索参数、DeepSeek 走 /responses 传输）、`persistence.py`（事件表 + 快照 + 增量重放；恢复时把仍处于 running/waiting 的 agent 落 failed——run 只在内存，恢复出的运行态是上一进程的尸体，用户发消息即可自动重开；快照角色合并覆盖到内置角色表上而非替换，旧快照不会丢掉后加的内置角色）。API 入口：`services/api_v2.py`（薄路由，生产装配 `create_default_v2_app()`）。v1 运行时与旧 API 已全部删除。

**UI 前端**

- `frontend/` — Electron + React SPA（唯一前端）：`src/App.tsx`（项目栏 / AgentBar / 对话 / Inspector 六标签）、`src/DagPanel.tsx`（DAG 机理图 + 阶段状态/复核收件箱/覆盖率报告/mutation 历史/结构化编辑/supervisor replan）、`src/Markdown.tsx`（assistant 输出 markdown + KaTeX 渲染）、`src/api.ts`（v2 客户端）、`electron/main.cjs`（spawn `create_default_v2_app` runtime + 托盘壳）、`electron/preload.cjs`（只暴露 runtimeBaseUrl）。`npm run build` 通过才算前端可用；开发时 `npm run dev`，生产 Electron 加载 `dist/`。

**能力与角色**

- `tools/` — 按领域分组的工具（Bashtool/Chemtool/Searchtool/Writetool/Plantool 等）；Plantool 的 DAG 面是 `dag_tools/` verb 族（`dag_view`/`dag_propose_mechanism`/`dag_accept_mechanism`/`dag_review_call`/`dag_bind_evidence`/…，取代已删除的 `dag_graph` 单工具；`dag_schedule_work`/`dag_update_process_node`/`dag_init_from_template`/`dag_review_evidence` 已随 process 图删除）；`tools/registry.py` 注册（每个 `ToolRegistration` 可选声明 `tool_name` 与 DAG/runtime 语义——含 `dag_review`（完成即入 CallReview 收件箱）与 `dag_compute_entry`（机理未接受前的计算门禁），下游只能经 `tools/capabilities.py` 投影查询，**禁止在别处新建工具名集合**）；`tools/core/` 含命令分级、权限模型、文件变更审批流水线、`coord_guard.py`（手写坐标守卫：向 .gjf/.xyz/.com 写入逐字坐标块在 text_writer/edit_file/bashtools 层放行但附警告并点破"绕过 supervisor/DAG 审查"，坐标必须来自 smiles_to_mol/format_converter/gjf_writer 等工具）、`bash_habit_guard.py`（bash 习惯守卫：heredoc/echo/tee/sed -i 写文件等命令在 bashtools 层附警告）、`delegation_guard.py`（Coordinator 自行 `submit_compute_job` 时在工具结果附轻量提示，照常放行）。Managetool 的 SubAgentLauncher/SubAgentSwarm/get_subagent_report/agent_hub/schedule 五个类只保留 schema 与描述作 LLM 线缆格式，执行被 runtime_v2 的 subagent_bridge/hub_bridge/reminders 按名拦截，tool_call 本体是报错兜底。工具**无持久状态**，结构化输出由 DAG 适配器解释；工具的 DAG 证据派生函数（`derive_delivery_changes`）随工具模块提供并在 registry 声明，现在是阶段绑定的确定性检查器（如 TS frequency 绑定的 n_imag==1），不再自动提升任何图元素。工具输出 schema 的成功字段统一为 `is_success`（布尔），返回给模型的 message/错误文本一律英文。超大工具结果护栏：bashtools 合并输出超 30k 字符时全文原子落盘到工作区 `.cloudra/tool_output/`，模型只收到截断摘要 + 落盘路径，需用 text_reader 的 start_line/end_line 分页读取全文。
- `subagents/` — 领域子 Agent（dft、md、researcher 等 8 个角色）。
- `prompts/*.md`、`skills/*` — 角色 prompt 与科研方法技能包。

## dag/ 子系统（DAG 引导编排）

按会话 opt-in：`orchestration_mode` ∈ `standard`（默认，不读不写图）/ `dag_record`（机理草稿由 harness 自动接受，Coordinator 用 `dag_bind_evidence` 自绑阶段，Supervisor 不运行）/ `dag_guided`（Supervisor `dag_accept_mechanism` 接受草稿、`dag_review_call` 逐调用复核绑阶段）。runtime_v2 允许经 `agent.settings_update` 中途切换（v2 前端的模式下拉会同步 PATCH 项目内所有现存 agent）。

- `models.py` — 共享类型与 `build_orchestration_config()`。可写图元素只有 delivery：`OccurrenceNode`（节点）与 `ElementaryStepEdge`（边）；阶段模型 `StageKind`/`StageStatus`/`StageState`/`StageContract`（list 顺序即允许绑定顺序）、`CallReview`（复核收件箱行）、`MechanismDraft`（草稿 + stage_contracts）；`GraphOperation` 是以 `op` 判别的具名命令联合（AddNode/AddEdge/RemoveEdge/UpdateNode/UpdateEdge/AttachRef/AddLink/SetCoverageContract/WaiveGate）。`PlannedNode`/`ObservedNode`、旧 data-dict 形状与旧词表（workflow/intermediate_occurrence 等）只读兼容，旧 journal 可重放；`AddLink` 写入即拒（`process_graph_removed`）。
- `store.py` — 单张 delivery 机理图持久存储，变更日志 + 物化视图；`dag_drafts`（机理草稿，`mechanism_accepted` = 存在 state='accepted' 的草稿，无单独标志位）与 `dag_call_reviews`（append-only 复核收件箱，直连 INSERT，不经 revisioned 引擎）。证据引用存关联表 `dag_evidence_bindings`（读路径以它为准，左连接 `dag_evidence` 重建 GraphRef；节点/边的 `refs` 内联 JSON 列保留为兼容兜底），写路径随阶段绑定记账。旧库的 process 行只读加载、不再写入。
- `engine.py` — 事务化变更引擎 `DagEngine`：原子批次、乐观 revision、无环校验。按图分权：Supervisor 对 delivery 只读；Coordinator 设计 delivery；模型只能以 pending 阶段创建元素、只能手动设 proposed/rejected/inconclusive 证据位。process 图写入一律 `process_graph_removed`；重放旧 journal 时 process 操作记 `ignored_legacy_process_op` 跳过（revision 照常前进）。`remove_edge` 必须带 rationale。`apply_stage_verdict()` 执行阶段绑定守卫：顺序（前置 required 阶段须 supported/skipped，否则 `stage_out_of_order`）、`ts_guess` advisory 永不满足 ts_opt/frequency、`rejected` 阶段可重绑。
- `completion.py` — 交付覆盖率确定性评估 `evaluate_delivery()`（按阶段：complete ⇔ 每个 required stage supported 或带非空理由 skipped；pending/rejected 都是开放缺口）与 prompt 投影（delivery 缺口 + pending 复核 + 近期变更）。
- `controller.py` — harness 集成 `DagController`：工具证据持久化、DAG prompt 注入、CallReview 入箱（只限 registry 声明 `dag_review=True` 的工具与计算作业终态；append-only；唤醒按 D14 合并）、`propose_mechanism`/`accept_mechanism`（草稿校验与落图）、`review_call`/`bind_stage_for_call`（从 tool_call_id 解析 ref：存在性/成功性/非 submit（`bind_target_is_submit`）/deriver 检查如 n_imag==1 的 `saddle_check_failed`）、`audit_stop`（complete 需过覆盖率审计；未显式 stop 结束的 run 记 partial；有未终态子 agent/pending 提醒/计算作业时 stop 挂起）。

关键不变量：图存储是权威（不在模型上下文里）；证据是不可变记录/产物的类型化引用；删除必须带理由且留在变更日志；模型声明不能标记交付完成，证据等级由 harness 从阶段确定性派生；阶段严格按契约顺序绑定；`rejected` 不是处置——是仍欠的开放缺口，只能重绑或显式 skip-with-reason 关闭；`submit_compute_job` 调用永远不是证据（只认完工作业的解析产物）。

## 测试约定（tests/）

- 按文件名前缀分组：`test_dag_*`（DAG）、`test_runtime_v2_*`（新内核：runner/pipeline/commands/bridges/pending/recovery）、`test_compute` / `test_slurm`（计算执行）、化学工具各一、其余为基础设施单测。
- `conftest.py` autouse 隔离 data_dir 到 tmp_path；不要在测试里写真实数据目录。
- 跳过均按环境探测：缺 `crest`/`xtb` 二进制、无 symlink 权限、非 POSIX。无需要真实 LLM key 的测试。
- 测试替身（fake/stub）签名要对齐真实接口，建议带 `**_kwargs` 防接口加参后变红。

## 顶层散件

- `deploy/node-registry.example.json` — 多节点/Slurm 注册表示例。
- `docs/` — 专题文档索引；`docs/superpowers/plans/` 存放设计计划（如 DAG 设计）。
- `install.sh` / `install.ps1` — 安装脚本；`build/`、`.worktrees/`、`cloudra.egg-info/` 为构建副产物，勿手改。
- `软著申请材料/`、`copyright_docs/`、`*.pdf` 研究报告 — 申报材料，非代码。

## 工作约定

- 最小改动：修 bug 不顺手重构；新代码跟随所在文件的既有风格与注释密度。
- **事件循环线程禁止同步阻塞调用**：`async` 函数体内不得直接调用同步 SQLite（`db.connect()`/`retry_on_locked`）、`time.sleep`、`subprocess.run`、同步网络库——一律 `asyncio.to_thread` 卸载或用 `a` 前缀异步变体。同步 SQLite 只允许在守护线程 / CLI / 测试上下文使用。曾因此造成跨进程 5 分钟级 "database is locked" 死锁（同步忙等冻结 loop → 同进程 aiosqlite 无法 commit）。护栏：运行时 `ConversationDB.connect()`/`retry_on_locked()`/`init()` 会告警（`CLOUDRA_DB_SYNC_ON_LOOP=raise` 抛错、`=off` 关闭），`tests/test_no_sync_on_loop.py` 静态扫描常驻。
- 不引入项目未依赖的库；可选能力走 `pyproject.toml` 的 extras（chem/browser/pdf/dev）。
- 改了结构、命令或约定时同步更新本文件。
- 未经明确要求不做 git 提交/推送等变更操作。
