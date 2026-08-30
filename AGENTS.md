# AGENTS.md — Cloudra 项目指南

给 AI 助手与新贡献者的仓库导航。项目定位与三层架构（control plane / research runtime / execution plane）见 `README.md`，这里只讲代码布局、边界约定与开发命令。

## 命令

```bash
uv run pytest -q tests/            # 全套测试
uv run pytest -q tests/test_dag*   # 聚焦某个子系统（按文件名前缀选）
uv run ruff check cloudra tests    # lint（select E/F/W/I，line-length 120 但 E501 不强制）
cloudra                          # 构建并启动 Web 前端（API + SPA 单端口）
uv run python -m compileall -q <改动文件>   # 改完先做语法检查
```

入口：`cloudra`（CLI，`cloudra/cli.py`：默认启动 Web 服务并打开浏览器，`web`/`config`/`skills`/`backup` 子命令；任务的执行面已收敛到 runtime_v2，CLI 不再直接跑任务）。HTTP 控制面唯一实现是 `cloudra/services/api_v2.py`（由 `cloudra`/`cloudra web` 以 uvicorn 拉起，同端口托管 SPA）。Python >= 3.11。

**v1 已删除**：旧 `services/api.py`/`api_v1.py`/`service.py`、`runtime/` 执行核心（runner/executor/workers/mobile_tasks）、`core/react.py`、Flet `ui/`、Android 全家桶、device 链均已移除；下列共享底座继续服役：`core/agent.py`（Agent/Coordinator/Follower 基类）、`core/supervisor.py`、`runtime/prompt_assembler.py` + `environment_observer.py`、`runtime/monitor.py`（计算任务日志监视子进程）、`runtime/compute_executor.py`（领取 `ready` 计算任务并拉起 guard/Slurm；`api_v2` lifespan 启动 `ComputeBroker`）、`services/session_store.py` + `nodes.py`、`persistence/`（除 conversation_repo/case_bank/context_stats）、`infra/`（除 presentation/tool_presentation/email_listener/mobile_storage/native_bridge/android_build）。

## 模块地图（cloudra/ 包）

根目录除 `cli.py` / `__main__.py` / `__init__.py`（惰性兼容导出）外还有 `web_launcher.py`（CLI 默认命令经它启动 Web 前端并打开浏览器）与 `calculator.sh`（package-data 声明的运行时资源）；实现按职责分五个子包：

**`core/` — 共享基类与督导**

- `agent.py` — `Agent`/`Coordinator`/`Follower` 基类与权限模型宿主（supervisor、subagents、部分工具直接继承；v2 会话不经过这里的执行方法）。
- `supervisor.py` — 科学督导（SupervisorAgent、GraphSupervisor），只在 `dag_guided` 模式运行：接受/驳回机理草稿、复核 CallReview 并绑定阶段；对 delivery 图结构只读，不调度工作。督导报告由 `DagController._deliver_supervisor_report` 回投 Coordinator（notices.pin 常驻注入；非 Coordinator 触发时另发 `agent.message` 唤醒）；case-bank 检索版 `Supervisor` 已随 case_bank 一并删除。
- `dag/` — DAG 引导编排子系统（仍在包根一级），见下节。
- 推理循环的唯一实现是 `runtime_v2/`（见下）；`runtime/` 只剩共享件：`prompt_assembler.py`（确定性 system prompt 组装：`load_role_prompt()` 读 `prompts/*.md`，按 (mtime_ns, size) 签名缓存；AGENTS.md 仅注入 Coordinator）、`environment_observer.py`（工作区快照）、`monitor.py`（计算日志监视子进程，由 `infra/compute_utils.py` 以 `python -m cloudra.runtime.monitor` 拉起；失败路径把可读原因落 `compute_jobs.last_error` 与 state json 的 `error` 字段）、`compute_executor.py`（`ComputeBroker` 扫描会话库 `claim_ready_compute_job`，本地任务 `launch_compute_processes(wait=False)` 后延长 lease 以免重复开算，Slurm 走 `run_slurm_compute` 并在轮询期间续租；周期 `_reap_orphans` 把已耗尽重试预算且租约过期的 running 作业置 failed——系统不主动杀进程，死作业靠 `mark_compute_job_failed` 工具显式对账）。

**`services/` — 服务层 / 控制面**

- `api_v2.py` — 唯一的 HTTP 控制面（薄路由；写操作一律走 CommandBus，DAG/artifact 读直连 dag/ 与 persistence/artifacts；唯一例外是 `GET/PATCH /api/v2/runtime/config`：直接改内存 config 单例并原子写回 YAML——那是 per-agent 设置留空时的全局回落槽位 coordinator/follower，key 只写不读）。
- `session_store.py` — 会话级 SQLite 的 schema 迁移与共享写入助手（tools_class 记录事件、dag/controller、artifacts 在用）。
- `nodes.py` — 多节点/Slurm 计算注册表（`submit_compute_job` 工具用）。

**`persistence/` — 持久化 / 状态**

- `database.py` — 会话级 SQLite（ConversationDB；v2里主要服务 DAG 存储与 artifacts）。
- `artifacts.py` — 不可变产物快照（ArtifactService）与短期下载授权。
- `memory.py`（长期记忆 MEMORY.md，prompt_assembler 用）、`core/message_history.py`（JSONL 消息历史；Supervisor 与 legacy llm_call 路径）。
- `paths.py` — data_dir 下所有路径的**唯一事实来源**（含 `knowledge_dir()` / `knowledge_graph_db_path()` = data_dir/knowledge/chem_kg.db）；`fs_utils.py` — 原子写；`workspace.py` — 工作区受限读写。

**`knowledge/` — 化学知识库（chem-kb）**

- 数据侧实现，与 `runtime_v2/knowledge.py`（图书馆协议）互补：协议管合并排序，本包管存储与检索。
- `store.py` — chem_kg.db 的 DDL/导入/查询（sync-only，async 调用方 `to_thread`）。实体 12.7k + 行级关系 9k，源自 知识卡片 洁净版抽取（`KG数据/` CSV）。FTS5 trigram + LIKE 回退、1~2 跳 ego 邻域（递归 CTE 取 MIN(hop)、度预聚合、确定性排序）、`relations_of_source`（卡→图缝合，走 `idx_rel_source`）。读路径只读连接、缺库返回空**绝不建库**；写路径只有 `ensure_schema`/`import_csv`（WAL + checkpoint TRUNCATE）。导入幂等（两表 ON CONFLICT DO UPDATE），悬挂引用进坏行报告不中断。
- `plugin.py` — 单一混合 provider（`cloudra.knowledge.plugin:plugin`）：语义通道 = 向量微服务（`CLOUDRA_KG_VEC_URL`，默认 127.0.0.1:8765，httpx 超时 3s，异常该通道为空绝不抛）+ 图谱通道 = 本地 SQLite + 模糊兜底层（`fuzzy.py`，v10）。配额结构性保证双通道全带上：limit=5 → 语义 ceil(3/5)=3 + 图谱 floor(2/5)=2；优先级链 语义 > 模糊 > 图谱补位，终版退化矩阵：✓✓→3+2；✗✓cards在→3模糊+2图谱；✗✓cards缺→5图谱；✓✗→5语义；✗✗cards在→5模糊；全缺→[]。模糊层扫仓库 `向量库/cards.jsonl`（子串 AND，确定性评分；pip 安装无该目录时零参与）。语义命中按 blog_id 缝合 1~2 条卡内关系（"‖图:" 行，content ≤200 码点）。只返回 `KnowledgeEntry` 实例（dict 路径的 float() 会穿透异常隔离，绝不走）。条目前缀 〔卡片〕/〔卡片·模糊〕/〔图谱〕；跨通道分数只是近似排序（bm25 与余弦不同量纲），最终排序以图书馆层的 (level, falsified, -score) 为准。
- `installer.py` — `cloudra knowledge install`：把插件 spec 幂等写进 config.yaml 的 plugins 列表（直接编辑 YAML，非 `save()`）。
- CLI：`cloudra knowledge import/stats/export/search/install`（延迟 import；数据默认取仓库 `KG数据/`）。

**`base/` — 数据类与基类**

- `skill_class.py` / `tools_class.py` — 加载器与基类；`tools_class.py` 另持审批钩子 `use_approval_handler`（ContextVar）：设置后 `request_approval` 走钩子而非 SQLite 等待，runtime_v2 的 `LegacyToolExecutor` 执行工具时总是设置它（ask_user 同理走 `use_input_handler`）。
- `session_class.py` — 会话数据类（reAct 时代的 `conversation_class.py`/`log_class.py` 死模块已删）。

**`infra/` — 支撑设施**

- `config.py`（LLMConfig/CloudraConfig）、`llm_client.py`（OpenAI 兼容传输层）、`web_search_native.py`。
- `events.py`（进程内/间事件门面）、`ipc.py`（会话级事件总线）、`streaming.py`、`token_estimator.py`。
- `slurm.py`、`compute_utils.py`、`operations.py`（数据目录备份/恢复）、`yolo_guard.py`（自动审批安全守卫）。
- `platform_utils.py`、`runtime_profile.py`（运行能力 profile，registry 的 runtime_profiles 过滤用）。
- `json_args.py` — 工具参数 JSON 的宽松解析/修复（LLM 产出的畸形 JSON 在此兜底）。
- `infra/` 基础设施备注：`config.py` 的 `save()` 对 `plugins` 键**磁盘优先合并**（磁盘 YAML 存在非 None 值就原样保留，否则落内存值）——堵住运行中服务用旧内存快照整文件重写、抹掉 `knowledge install` 手写 plugins 的竞态；代价是 `save()` 无法移除 plugins 条目，卸载插件手改 YAML。
**包根一级子包**：`dag/`、`runtime/`（仅剩共享件，见上）、`tools/`、`subagents/`、`prompts/`、`skills/`、`benchmark/`。

**`benchmark/` — 基准评测框架（独立于会话运行时）**

- `schema.py` — 任务 JSON 的唯一 schema（`TaskSpec`：prompt/system/method_policy/gold/rubric）；机理图节点/边携带原子映射的键变化集（`bond_changes` 的 [i, j] 对引用 query 展示的原子映射反应物 SMILES 的映射号：键级下降记 `break`、上升记 `form`，gold 与 agent 交付共用同一套编号），agent 侧线缆键用别名（`from`/`to`/`break`）。gold 的能垒锚点另记类型（`barrier_type`，题源未显式注明则为 null，不默认贴 Ea）与口径（`barrier_reference`：`central_complex` = TS 相对反应物络合物 / `reactants` = TS 相对反应物渐近线；仅元数据，评分只读 `barrier_kcal_mol`）。
- `gen_easy_tasks.py` — 从 `ideapool/reaction_candidates/easy.md` 确定性生成 `ideapool/tasks/easy/*.json`（30 题）；改题源后重跑 `python -m cloudra.benchmark.gen_easy_tasks`，`test_easy_tasks_regenerate_identically` 守卫题库与生成器同步。能垒口径统一 `central_complex`（easy 档不考渐近线口径；个别题覆盖登记在 `_BARRIER_REFERENCE`）；锚点数值属渐近线口径的题保留数值、降 `unverified`（登记在 `_BARRIER_FRAME_UNVERIFIED`，不编造数值）。query 展示的原子映射反应物 SMILES 与 gold 边键变化按 task_id 登记在 `_MAPPED_REACTANTS`/`_BOND_CHANGES`（漏登 KeyError）。
- `graph_similarity.py` — 化学参数化图评分，默认**子图覆盖**打分（gold 图嵌入交付图即满分，交付多出的节点/边不罚——"多想总是好事"；实现为 gold 物种→交付节点的注入式指派（节点+边代价联合优化，退化机理的并列指派由边连通性 tie-break）+ 边按指派端点评估，多项式可控，无尺寸守卫）；`GedConfig(subgraph_scoring=False)` 退回对称 GED 诊断模式（networkx 最坏指数复杂度，受交付尺寸守卫保护）。`protonation_skeleton` 提供质子化/电荷态不变的骨架标识（剥电荷+显式氢后 sanitize 重算隐含氢；纯氢体系退化 canonical hash）。RDKit 可选，缺失时节点代价退化为 SMILES 集合相等、无 partial credit 通道。
- `integrity.py` / `selfconsistency.py` / `accuracy.py` — 三层取证评分：沙箱扫描+证据绑定（证据文件按交付协议携带 `smiles:` 注释行；机理图形状（顶层 nodes+edges）的 JSON 一律不算证据——防交付图改名拷贝自绑；绑定分档——指纹/哈希全等记 1.0，仅质子化/电荷态不同的骨架匹配记可变 partial（质量 = 1-(1-锚点)·指纹相对误差，锚点 `protonation_partial_quality` 默认 0.7，扣分不判零），其余不绑；平均绑定质量 `binding_quality` 作为 composite 乘性因子；TS 节点仅经边端点间接绑定并继承较弱端点质量；交付图宽松加载、gold 图 strict）→ 鞍点/IRC/极小值物理自检（复用 `tools/core` 的 gaussian/orca frames 解析；TS 证据按文件名 `ts` token 识别，其余 QM 日志按极小值检查；超 `MAX_SCAN_BYTES` 的文件两层都不整读）→ 能垒高斯容差评分。
- `method_policy.py` — 方法白名单拦截判定（纯函数，按方法族粒度匹配：`xtb2`/`gfn2-xtb` 归 `xtb`、`mace-*` 归 `mace`，路线卡文本无法区分 MLIP 变体故变体管控在带外；`qm_input_writer` 查 method 字段；`submit_compute_job` 无 method 字段，读 input_file **文件内容**判定；bash 层（工具名 `bash`/`bashtools`）解析 heredoc/echo-printf 重定向写入的 QM 输入内容（Gaussian 全部路由卡含 --Link1--，MLIP 走 `external="engine"` 引擎值即候选、裸 `external` fail-closed；ORCA 关键字行），不扫描命令文本；`referenced_input_paths` 抓命令里引用的磁盘已有 QM 输入路径供调用方过 `check_input_files`；所有方法候选须全部命中白名单，无法解析方法时 fail-closed）。
- `policy_stage.py` — 白名单的运行时执行点 `MethodPolicyStage`（runtime_v2 PolicyStage；`intercept` 裁决 + bash 引用文件补查，block 理由作为普通工具反馈回灌 agent，拦截不扣分）。
- `backend.py` — runtime_v2 后端 `RuntimeV2Backend`（每题起一个进程内 RuntimeCore+TurnPipeline+AgentRunner，沙箱即项目 workspace，方法白名单经 MethodPolicyStage 入管线，`submit_compute_job` 由 per-task ComputeBroker 执行，worker_id 带 pid+task_id 防并行租约串扰；yolo 无人值守，waiting 挂起超 grace 即取消；从最终消息的 `kcal/mol` 数值提取 agent 报告的能垒；core 按 task_id 留存于 `core_by_task()`/`last_core` 供测试内省）。数据目录隔离由 CLI 负责（`CLOUDRA_DATA_DIR` 指向 benchmark 数据目录 + 覆盖全局 config 单例的 data_dir，防 YAML 回落；config_file 独立，LLM 凭据不受影响）。
- `api_pool.py` — API 端点池（防 429）：池成员共享 agent 设置里的模型，只按端点钉 base_url/api_key（空字段回落 settings）；每次 LLM 调用随机洗牌端点顺序（摊初始负载 + 429 不重复试同一端点），单端点内建退避耗尽仍 429 则换下一个端点，非 429 错误不重试；当前端点经 contextvar 传递（并行跑题不串）。CLI `--api-pool pool.json` 启用。
- `runner.py` — 独立 `BenchmarkRunner` + 专用 `benchmark.db`（同步 sqlite3，仅 CLI/测试上下文，不进事件循环；写入由进程内锁串行化）；composite 是分级语义而非门禁：final = (0.5·graph + 0.2·selfconsistency + 0.3·accuracy) × binding_quality——证据完整且机理正确得满分，缺部分证据按比例扣（缺一个不判零），图缺失/不可解析/零证据绑定时倒扣 `no_evidence_penalty`（默认 1.0，负分）；后端崩溃题记 0（基建失败不是 agent 的锅）。`run_all(tasks, concurrency=N)` 受控并行（线程池，每题独立事件循环+沙箱，默认 1 串行）。`python -m cloudra.benchmark` 为 CLI 入口（`--backend none` 默认干跑 / `runtime_v2` 真跑，`--only` 选题，`--timeout` 单题超时，`--concurrency` 并行度）。

**`runtime_v2/`（事件驱动新内核，按 S1 规格）**：`schemas.py`（API 类型唯一来源）、`roles.py`（角色权限/默认值唯一来源 `BUILTIN_ROLES`，coordinator 不再硬编码特权）、`events.py`（EventLog/EventHub）、`core.py`（RuntimeCore）、`commands.py`（CommandBus，先事件后状态；`agent.message` 对 failed/cancelled agent 自动 reopen 新 run，用户无需手动 restart）、`agent_host.py`（AgentSession 状态机；restart = 保留身份、开新 run，有效上下文靠 goal/DAG/memory/工作区每轮外化重建 + 上下文树种子（见 `context_tree.py`）在新 run 首轮注入，只有 LLM 对话原文不跨 run；`wake()` 苏醒沉睡/空闲 agent——succeeded/queued 开新 run、failed/cancelled 重开、waiting 续跑、running 不动，`agent.message` 与 hub 通知共用；重开终态 agent 时落 `agent.context_reset` 事件显式标记对话历史清零边界（restart 命令同发，reason 区分 auto_reopen/restart_command））、`agent_runner.py`（每 Agent 一个 async task，真并发 + 可取消；turn 崩溃原地自动重试——history 只记录成功 turn，崩溃等于 LLM 请求未完成，重跑是干净重做，落 `run.retry` 事件，默认 2 次退避 2s/4s，仍失败才进 failed；视觉回注：工具结果/inbox 消息带图且 visual_mode × supports_vision 双开时 history 写 image_url parts（base64 data URL），单关则英文文本回落；新 run 首轮 drain inbox 后从上下文树注入种子 history（排除即将投递的 inbox 消息防重复）；run 结束的 finalize（LLM 摘要 + HANDOVER 重写）detach 成独立任务——若内联在 runner task 里，task 会压住 finish_run 后的状态迁移，wake 新 run 时 `schedule()` 去重会把唤醒吞掉）、`turn_pipeline.py`（固定轮次管道，只依赖 PolicyStage；LLM 走流式，token delta 以 `llm.chunk` 只发 EventHub——瞬时不落 log、不持久化、不参与重放；每轮的完整 reasoning 落一条持久 `agent.thinking` 事件（历史轮次 thinking 刷新后仍可见）；带工具调用的中间轮次正文也落持久 `agent.message_emitted` 并立刻推到 hub（stop 轮由 runner 的最终消息承载，不重复；若等整轮工具结束再 flush，前端会在下一轮工具出现时把流式气泡清掉）；`NoticeManager.collect` 只在此处拼进 LLM 消息：先 pins 再 drain 一次性 push；loop 护栏也在此——同一工具调用（name+规范化参数）在同一 run 内连续重复满 3 次起，每次重复落 `loop.detected` 事件并 push 一次性警告要求换思路，不硬 block；tool.finished 汇流处把工作区图片登记为 artifact（artifact_id 回写事件 data 供前端时间线显示））、`policies/`（permission/dag/goal/schedule 四个 stage；新 harness 能力只加 stage；schedule stage 管 autonomous schedule mode——拦截 `stop`，要求先 `schedule` 或已有 pending reminder 才允许休眠；dag stage 含 stop 交付门禁——dag 模式调用 `stop` 时经 `DagController.audit_stop` 审计交付覆盖率，有未决 gap 且声明 complete 则 block，项目里有未终态兄弟 agent 时 stop 视为挂起不审计；dag_guided 下督导运行经 `_SupervisionShell` 投影为复用的壳 agent 会话（角色 `supervisor`，不走 LLM 管线，只作 UI 状态投影；壳 spawn 被拒时降级为无投影，不影响督导本体与父 turn）；goal/dag 的常驻注入经 `notices.pin`，不再直接 append）、`mailbox.py`（用户/Agent 间统一投递；`agent.message` 支持 images 附件——工作区图片路径与 artifact id 写进 `agent.message_injected` data，runner 视觉开则转 image_url parts、关则文本回落）、`pending.py`（审批与 ask_user 交互的内核 broker：请求落 `approval.requested`/`interaction.requested` 事件 + future 挂起，agent 翻 waiting_approval/waiting_input；决策经 `approval.decide`/`interaction.respond` 命令解 future；列表为事件投影；请求在轮内自发布到 hub，决策事件由 CommandBus 统一 flush；run 取消时自动过期）、`reminders.py`（`ReminderBroker`：拦截 `schedule` 工具，提醒落 `reminder.scheduled/cancelled/fired`，`schedule_id` 用事件 seq；内存 asyncio 定时器到点经 `agent.message` 投递 `[Reminder]` 并 reopen 终态 agent；FastAPI startup `rearm_all()` 从事件投影重建，过期立即触发）、`email_listener.py`（`EmailListenerBroker`：会话级收件监听，替代已删除的 v1 `infra/email_listener`——后台轮询 IMAP 未读邮件（同步读取走 `asyncio.to_thread`，读完标 `\Seen` 防重复），`whitelist` 非空时过滤发件人、空则全收；每封落 `email.received` 事件并经 `agent.message` 投递 `[Email]` 给**最近活跃项目**（`Project.updated_at` 最大者）的 coordinator，只注入不自动执行，回邮由 agent 自行用 `email_sender` 决定；无 IMAP 凭据时不启动；`api_v2` lifespan 启停，轮询间隔 `EmailConfig.poll_interval`）、`notices.py`（`NoticeManager`：`pin`/`unpin` 常驻注入与 `push` 一次性注入，统一渲染为 system 消息；**已事件化**——attach 到事件日志后变更落 `context.pin_set`/`context.pin_cleared`/`context.injected`（stage 每轮重 pin 相同内容经去重不落事件），restore 时从投影重建 pins（push 不恢复，事件即审计），外部注入走 `context.inject` 命令 / `POST /api/v2/agents/{id}/context/inject`（只注入不唤醒，要唤醒用 agent.message））、`compaction.py`（手动上下文压缩：压缩 runner 内存 history，一轮非流式 LLM 摘要 + tool 配对边界对齐；命令 `agent.compact` 置 pending，runner 在轮边界执行，发 `compaction.requested/started/finished`；摘要同时追加到工作区 `.cloudra/context_compacts.md` 并把文件指针回写交接消息——跨 run 仍可审计；LLM 400/413 上下文超窗时 runner 先做一次紧急压缩（trigger=context_overflow，留 10 条尾部）再重试同轮一次，仍超才 failed；摘要全文也随 `compaction.finished` 事件落盘进上下文树）、`context_tree.py`（事件溯源上下文树，不另起存储：每个 run 结束落 `context.run_summarized`（轨迹压缩 + seq_range 指回原事件，随时可深挖）与 `context.handover_updated`（系统维护的 HANDOVER 项目状态快照，agent 不再自写 HANDOFF.md；最新快照同步覆写工作区 `.cloudra/handover.md`）；succeeded 由 runner 调一次非流式 LLM 生成（`[RUN LOG]`/`[HANDOVER]` 两节），failed/cancelled/摘要失败退化为事件流派生的确定性摘要；`build_seed_context` 在新 run 首轮重建种子：最新 HANDOVER + 逐字保留的指令消息（用户/spawn query/peer/邮件/提醒）+ 各 run 压缩摘要（进程死亡导致未 finalize 的 run 没有摘要事件，种子构建时从其原始事件补一条确定性摘要，不丢失该 run 的工作），超预算时最旧摘要降级为指向事件 seq 区间的指针行）、`transcript.py`（项目级完整转录渲染器：`GET /api/v2/projects/{id}/transcript` 下载 Markdown——全量事件按时间序渲染、payload 不截断（消息/思维链/工具参数与结果/压缩与上下文树快照），消融诊断用；纯函数无 IO）、`subagent_bridge.py`（Managetool 三工具 SubAgentLauncher/SubAgentSwarm/get_subagent_report 的 v2 原生实现：经 CommandBus spawn 子 agent，launcher/swarm 支持 is_wait 同步等待与父取消级联，swarm 按 `{{item}}` 模板展开 + 并发上限；a-1..a-8 映射到 explorer/writer/researcher/small_mol/md/dft/experiment/env 角色；子 agent 继承父的 orchestration_mode；spawn 时子 agent 继承父的 yolo（前端 YOLO 是项目级开关：写项目 defaults + 级联 PATCH 现存 agent，Inspector 里的 per-agent 勾选是单 agent 覆盖）；由 `LegacyToolExecutor` 在工具执行前拦截）、`hub_bridge.py`（`agent_hub` 论坛的 v2 原生实现：post 落 `hub.posted` 事件（事件日志即论坛存储），browse/read/search 为事件投影（模糊评分复用 legacy 纯函数），to_agent/回复通知与 call 走 `Mailbox.deliver` 并 `AgentHost.wake` 苏醒沉睡收件人（否则消息滞留 inbox 直到下次轮次），call 到角色名时经 CommandBus spawn 新子 agent；browse 返回每个 topic 的最新帖预览（preview/author/post_id）并提示用 read/search 取全文；search 同时带"图书馆层"——已注册知识插件的命中随同一工具结果返回（证据等级 L0/L1/L2、证伪降权，见 `knowledge.py`）；同样由 `LegacyToolExecutor` 拦截）、`knowledge.py`（知识 provider 协议与图书馆检索：`KnowledgeEntry`/`KnowledgeProvider`/`search_library`，证据分层排序 L1>L0>L2、证伪降权不删除；provider 失败只记日志不影响 hub 搜索）、`plugins.py`（通用插件机制：插件 = 带 `name` 的对象 + 可选 hooks——`search`（自动成为图书馆 provider）、`on_event`（挂进事件总线，sync 钩子上工作线程、错误隔离，插件自驱触发/维库/分析的唯一反应面）、`setup(core)`（attach 时拿 CommandBus/只读状态）；`register_plugin`/`attach_plugins(core)` 进程内注册，`plugins` 配置项声明 "pkg.module:attr"（实例或无参工厂），`create_default_v2_app` 启动时 load + attach；核心不回写插件存储——无自演化；进程外插件直接用 HTTP（`/context/inject`、`/messages`、SSE））、`adapters.py`（旧 LLMClient/工具注册表/PromptAssembler 到新协议的桥；含模型原生联网搜索：命中适配器时剥外置 `web_search` 工具、注入 provider 侧搜索参数、DeepSeek 走 /responses 传输；visual 门控同样在 complete 里剥 `visual_tools()`（settings.visual_mode 关时），`supports_vision(agent)` 按 coordinator/follower 槽位判定视觉能力；/responses 翻译携带 image parts）、`persistence.py`（事件表 + 快照 + 增量重放；恢复时把仍处于 running/waiting 的 agent 落 failed——run 只在内存，恢复出的运行态是上一进程的尸体，用户发消息即可自动重开；快照角色合并覆盖到内置角色表上而非替换，旧快照不会丢掉后加的内置角色）。API 入口：`services/api_v2.py`（薄路由，生产装配 `create_default_v2_app()`）。v1 运行时与旧 API 已全部删除。

**UI 前端**

- `frontend/` — React SPA（唯一前端）：`src/App.tsx`（项目栏按 workspace 分组 + Archived 折叠分区（归档/恢复经 `DELETE`/`PATCH archived`）、AgentBar / 对话 / Inspector 六标签；斜杠命令含 `/visual`——项目级 visual 模式开关 + 级联，visual 开时 composer 可上传图片随消息发送，时间线用户气泡/工具卡片与 artifacts 标签内联显示图片）、`src/GlobalConfig.tsx`（左侧栏底部 "Global settings" 入口的模态：编辑全局 LLM 回落槽位 coordinator/follower 的 model/url/key/context_window/timeout/supports_vision，key 只写不读、留空不覆盖、clear 前弹确认）、`src/AttentionDock.tsx` + `src/attention.ts`（跨项目提醒坞：轮询所有非归档项目的 pending approval/ask_user，非当前项目的请求以右下角浮动卡片呈现并可就地 approve/deny 或回复（问题/命令全文不截断，卡片正文超高时内部滚动），jump 跳转对应项目/agent；桌面通知走浏览器 Notification API（dock 头部按钮申请权限），点击聚焦窗口并跳转；纯函数有 `attention.test.ts` 单测）、`src/AuditLog.tsx`（events 标签的审计日志：工具调用（tool/llm/run/compaction/thinking）与系统事件分区、卡片化字段渲染替代裸 JSON、**懒加载分页**——初始只取最新一页（200 条），"加载更早"按 `before` 会话游标向后翻页、DOM 只渲染一页、SSE 实时合并、按类型/内容过滤；字符串正文不截断；工具栏 "⬇ full log" 下载项目级完整 Markdown 转录，走 `projectTranscriptUrl`）、`src/DagPanel.tsx`（DAG 机理图 + 阶段状态/复核收件箱/覆盖率报告/mutation 历史/结构化编辑/supervisor replan）、`src/Markdown.tsx`（assistant 输出 markdown + KaTeX 渲染）、`src/api.ts`（v2 客户端；`eventsPage()` 走 `before`+`tail=true` 游标分页，`EVENTS_WINDOW` 只约束对话时间线）、`src/timeline.ts`（对话时间线拼装纯函数，compaction.started/finished 按 run 配对渲染为行内提示行，有 `timeline.test.ts` 单测）。`npm run build` 通过才算前端可用；开发时 `npm run dev`；生产由 uvicorn 同端口托管 `dist/`。

**能力与角色**

- `tools/` — 按领域分组的工具（Bashtool/Chemtool/Searchtool/Writetool/Plantool 等；Chemtool 含 `cdxml_to_graph`，基于 molli/RDKit 将 CDXML 反应路线解析为 SMILES 图与可选的 delivery DAG 提案；`pymol_render` 为 PyMOL 无头立体渲染——优先 pymol-open-source 模块、回退系统二进制 `-cq`，产物落工作区 `.cloudra/visual/`；**QM 输入/解析双引擎**：`qm_input_writer` 以 `engine='gaussian'/'orca'` 生成 .gjf/.inp（method/basis/task_type 自动映射到两家的输入语法），`log_parser` 自动嗅探 Gaussian/ORCA 日志并统一输出 schema（引擎写在结果的 `engine` 字段；热化学字段跨引擎同语义——ORCA 的不含 ZPE 热能修正已换算为含 ZPE 口径；ORCA IRC 从主输出的 FORWARD/BACKWARD 迭代块与 PATH SUMMARY 提取点数/收敛/端点能量，逐点坐标在 `*_trj.xyz` 边文件不提取）；`format_converter` 支持 `inp` 出口与 ORCA 日志→CSV）；Plantool 的 DAG 面是 `dag_tools/` verb 族（`dag_view`/`dag_view_evidence`/`dag_propose_mechanism`/`dag_accept_mechanism`/`dag_review_call`/`dag_bind_evidence`/`dag_message_supervisor`（向 supervisor 发消息）/`dag_delivery_report`（交付覆盖率报告）/…，取代已删除的 `dag_graph` 单工具；`dag_schedule_work`/`dag_update_process_node`/`dag_init_from_template`/`dag_review_evidence` 已随 process 图删除；`dag_view_evidence` 读某条 review 背后的完整 arguments+result，`dag_bind_evidence` 在 dag_guided 下把白名单外工具的产物提交进 review 收件箱而非直接绑定）；`tools/registry.py` 注册（每个 `ToolRegistration` 可选声明 `tool_name` 与 DAG/runtime 语义——含 `dag_review`（完成即入 CallReview 收件箱）、`dag_compute_entry`（机理未接受前的计算门禁）与 `visual`（visual 模式门控：`image_reader`/`pymol_render` 两个视觉工具，`visual_mode` 默认开、`/visual` 可关，关闭时 schema 剥除 + permission stage 双闸拦截），下游只能经 `tools/capabilities.py` 投影查询，**禁止在别处新建工具名集合**）；`tools/core/` 含命令分级、权限模型、文件变更审批流水线、`qm_engine.py`（Gaussian/ORCA 日志引擎嗅探）+ `gaussian_frames.py`/`orca_frames.py`（两家日志的关键帧/热化学/任务类型解析，纯函数）、`coord_guard.py`（手写坐标守卫：向 .gjf/.xyz/.com 写入逐字坐标块在 text_writer/edit_file/bashtools 层放行但附警告并点破"绕过 supervisor/DAG 审查"，坐标必须来自 smiles_to_mol/format_converter/qm_input_writer 等工具）、`bash_habit_guard.py`（bash 习惯守卫：heredoc/echo/tee/sed -i 写文件等命令在 bashtools 层附警告）、`delegation_guard.py`（Coordinator 自行 `submit_compute_job` 时在工具结果附轻量提示，照常放行）、`memory_scope_guard.py`（memory 范围守卫：`update_memory` 写入全局 MEMORY.md 前硬拦项目特定内容——绝对路径/data_dir 前缀/job ID 特征命中即 is_success=False 要求改写为项目无关措辞）。Managetool 的 SubAgentLauncher/SubAgentSwarm/get_subagent_report/agent_hub/schedule 五个类只保留 schema 与描述作 LLM 线缆格式，执行被 runtime_v2 的 subagent_bridge/hub_bridge/reminders 按名拦截，tool_call 本体是报错兜底。工具**无持久状态**，结构化输出由 DAG 适配器解释；工具的 DAG 证据派生函数（`derive_delivery_changes`）随工具模块提供并在 registry 声明，现在是阶段绑定的确定性检查器（如 TS frequency 绑定的 n_imag==1），不再自动提升任何图元素。工具输出 schema 的成功字段统一为 `is_success`（布尔），返回给模型的 message/错误文本一律英文。超大工具结果护栏：bashtools 合并输出超 30k 字符时全文原子落盘到工作区 `.cloudra/tool_output/`，模型只收到截断摘要 + 落盘路径，需用 text_reader 的 start_line/end_line 分页读取全文。
- `subagents/` — 领域子 Agent（dft、md、researcher 等 8 个角色；`registry.py` 是 a-1..a-8 到角色的显式注册清单）。
- `prompts/*.md`、`skills/*` — 角色 prompt 与科研方法技能包。

## dag/ 子系统（DAG 引导编排）

按会话 opt-in：`orchestration_mode` ∈ `standard`（默认，不读不写图）/ `dag_record`（机理草稿由 harness 自动接受，Coordinator 用 `dag_bind_evidence` 自绑阶段，Supervisor 不运行）/ `dag_guided`（Supervisor `dag_accept_mechanism` 接受草稿、`dag_review_call` 逐调用复核绑阶段）。runtime_v2 允许经 `agent.settings_update` 中途切换（v2 前端的模式下拉会同步 PATCH 项目内所有现存 agent）。

- `models.py` — 共享类型与 `build_orchestration_config()`。可写图元素只有 delivery：`OccurrenceNode`（节点）与 `ElementaryStepEdge`（边）；阶段模型 `StageKind`/`StageStatus`/`StageState`/`StageContract`（list 顺序即允许绑定顺序）、`CallReview`（复核收件箱行，含 `source_path`/`result_kind`/`suggested_stage` 等 sidecar 来源/判别元数据，只供判断不构成绑定权威）、`MechanismDraft`（草稿 + stage_contracts）；`_STAGE_GLOSSARY` 阶段语义词典（endpoint_a=target 侧/产物、endpoint_b=source 侧/反应物）随 `DagProjection.to_prompt_text` 注入给 Coordinator 与子 agent。`GraphOperation` 是以 `op` 判别的具名命令联合（AddNode/AddEdge/RemoveEdge/UpdateNode/UpdateEdge/AttachRef/AddLink/SetCoverageContract/WaiveGate）。`PlannedNode`/`ObservedNode`、旧 data-dict 形状与旧词表（workflow/intermediate_occurrence 等）只读兼容，旧 journal 可重放；`AddLink` 写入即拒（`process_graph_removed`）。
- `store.py` — 单张 delivery 机理图持久存储，变更日志 + 物化视图；`dag_drafts`（机理草稿，`mechanism_accepted` = 存在 state='accepted' 的草稿，无单独标志位）与 `dag_call_reviews`（append-only 复核收件箱，直连 INSERT，不经 revisioned 引擎；`find_duplicate_review` 只对仍 pending 的同构 (tool_name, arguments, result) 去重——已裁决的同构重提照常生成新 review）。证据引用存关联表 `dag_evidence_bindings`（读路径以它为准，左连接 `dag_evidence` 重建 GraphRef；节点/边的 `refs` 内联 JSON 列保留为兼容兜底），写路径随阶段绑定记账。旧库的 process 行只读加载、不再写入。
- `engine.py` — 事务化变更引擎 `DagEngine`：原子批次、乐观 revision、无环校验。按图分权：Supervisor 对 delivery 只读；Coordinator 设计 delivery；模型只能以 pending 阶段创建元素、只能手动设 proposed/rejected/inconclusive 证据位。process 图写入一律 `process_graph_removed`；重放旧 journal 时 process 操作记 `ignored_legacy_process_op` 跳过（revision 照常前进）。`remove_edge` 必须带 rationale。`apply_stage_verdict()` 执行阶段绑定守卫：顺序（前置 required 阶段须 supported/skipped/not_applicable，否则 `stage_out_of_order`）、`ts_guess` advisory 永不满足 ts_opt/frequency、`rejected` 阶段可重绑。
- `completion.py` — 交付覆盖率确定性评估 `evaluate_delivery()`（按阶段：complete ⇔ 每个 required stage supported、带非空理由 not_applicable（该槽不成立，记 `stage_not_applicable`），或带非空理由 skipped（记 `branch_disposed`）；pending/rejected 都是开放缺口）与 prompt 投影（delivery 缺口 + pending 复核 + 近期变更）。
- `delta.py` — `DeliveryDelta`，单次工具调用后 delivery 图变更摘要（`DagController.on_tool_finished` 返回）。
- `substantive_gate.py` — 机理接受前的计算门槛（D4）：拦截 `submit_compute_job`/`qm_input_writer`/`ts_guess` 计算型 mode 等实质计算入口。
- `controller.py` — harness 集成 `DagController`：工具证据持久化、DAG prompt 注入（投影含被驳回草稿的 `reject_reason`）、督导触发统一收口 `maybe_supervise`/`_run_supervision`（报告经 `_deliver_supervisor_report` 回投 Coordinator）、CallReview 入箱（只限 registry 声明 `dag_review=True` 的工具与计算作业终态；append-only；唤醒按 D14 合并）、`propose_mechanism`/`accept_mechanism`（草稿校验与落图）、`review_call`/`bind_stage_for_call`（从 tool_call_id 解析 ref：存在性/成功性/非 submit（`bind_target_is_submit`）/deriver 检查如 n_imag==1 的 `saddle_check_failed`）、`submit_evidence_for_review`（白名单外工具的证据通交通道：Coordinator 显式声明某次调用支撑 target 的 stage，`dag_bind_evidence` 在 dag_guided 下走这里而非直接绑定）、`audit_stop`（complete 需过覆盖率审计；未显式 stop 结束的 run 记 partial；有未终态子 agent/pending 提醒/计算作业时 stop 挂起）。

关键不变量：图存储是权威（不在模型上下文里）；证据是不可变记录/产物的类型化引用；删除必须带理由且留在变更日志；模型声明不能标记交付完成，证据等级由 harness 从阶段确定性派生；阶段严格按契约顺序绑定；`rejected` 不是处置——是仍欠的开放缺口，只能重绑或显式 skip/not_applicable-with-reason 关闭；`not_applicable`（带理由）标记物理/逻辑上不成立的槽位（无能垒步无 TS、单分子步无 endpoint_b），计入完成且不算欠账；`submit_compute_job` 调用永远不是证据（只认完工作业的解析产物）。

## 测试约定（tests/）

- 按文件名前缀分组：`test_dag_*`（DAG）、`test_runtime_v2_*`（新内核：runner/pipeline/commands/bridges/pending/recovery）、`test_compute` / `test_slurm`（计算执行）、化学工具各一、其余为基础设施单测。
- `conftest.py` autouse 隔离 data_dir 到 tmp_path；不要在测试里写真实数据目录。
- 跳过均按环境探测：缺 `crest`/`xtb` 二进制、无 symlink 权限、非 POSIX。无需要真实 LLM key 的测试。
- 测试替身（fake/stub）签名要对齐真实接口，建议带 `**_kwargs` 防接口加参后变红。

## 顶层散件

- `KG数据/` — 知识图谱 CSV（kg-entities/kg-relations/kg-stats，utf-8-sig；`cloudra knowledge import` 的输入）。
- `向量库/` — 知识卡片 bge-m3 向量四件（cards.jsonl / vectors.f16.npy / meta.json / retrieve.py）；`scripts/kg_vec_service.py` 微服务只读这套文件，向量侧依赖（torch/sentence-transformers）全部留在外部 .venv-trans，cloudra venv 不装 torch；服务不随 cloudra 自启（`scripts/kg_vec_service.ps1` 手动拉起）。
- `deploy/node-registry.example.json` — 多节点/Slurm 注册表示例。
- `docs/` — 专题文档索引；`docs/superpowers/plans/` 存放设计计划（如 DAG 设计）。
- `install.sh` / `install.ps1` — 安装脚本；`web.sh` / `web.ps1` — 开发便捷启动脚本（`run.sh` 调已删的 v1 子命令，已删）；`README_CN.md` 为中文 README。`build/`、`.worktrees/`、`cloudra.egg-info/` 为构建副产物，勿手改。
- `软著申请材料/`、`copyright_docs/`、`*.pdf` 研究报告 — 申报材料，非代码。软著源程序清单由 `scripts/gen_copyright_source.py` 重建（改代码后重跑）；`软著申请材料/06_LaTeX排版/` 为打印递交版，用 conda 环境 `tectonic` 的 tectonic 编译（`conda create -n tectonic -c conda-forge tectonic`，一次性）。

## 工作约定

- 最小改动：修 bug 不顺手重构；新代码跟随所在文件的既有风格与注释密度。
- **事件循环线程禁止同步阻塞调用**：`async` 函数体内不得直接调用同步 SQLite（`db.connect()`/`retry_on_locked`）、`time.sleep`、`subprocess.run`、同步网络库——一律 `asyncio.to_thread` 卸载或用 `a` 前缀异步变体。同步 SQLite 只允许在守护线程 / CLI / 测试上下文使用。曾因此造成跨进程 5 分钟级 "database is locked" 死锁（同步忙等冻结 loop → 同进程 aiosqlite 无法 commit）。护栏：运行时 `ConversationDB.connect()`/`retry_on_locked()`/`init()` 会告警（`CLOUDRA_DB_SYNC_ON_LOOP=raise` 抛错、`=off` 关闭），`tests/test_no_sync_on_loop.py` 静态扫描常驻。
- 不引入项目未依赖的库；可选能力走 `pyproject.toml` 的 extras（chem/browser/pdf/visual/dev，`all` 聚合全部）。
- 改了结构、命令或约定时同步更新本文件。
- 未经明确要求不做 git 提交/推送等变更操作。
