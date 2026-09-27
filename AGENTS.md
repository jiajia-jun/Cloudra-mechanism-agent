# AGENTS.md — Cloudra 项目指南

给 AI 助手与新贡献者的仓库导航。项目定位与三层架构见 `README.md`。本文件是**地图不是手册**：每个模块只记职责与坑点，细节读代码。

## 命令

```bash
uv run pytest -q tests/test_dag_engine.py   # 按文件名前缀聚焦改动子系统（默认只跑这个粒度）
uv run pytest -q tests/                     # 全套测试由 CI 跑，本地不跑（除非用户明确要求），见"工作约定"
                                            # ⚠ 别把 pytest 管道进 tail/grep：$? 会被管道掩盖；全套验收用
                                            #   `uv run pytest -q tests/ > /tmp/pytest.log 2>&1; echo EXIT=$?`
uv run ruff check cloudra tests             # lint（select E/F/W/I，E501 不强制）
uv run python -m compileall -q <改动文件>   # 改完先做语法检查
cloudra                                     # 构建并启动 Web 前端（顺带 detach 拉起 scheduler/kg_vec 守护）
cloudra web --host 0.0.0.0 [--port N]       # 自定义绑定（默认仅 127.0.0.1:8000；⚠ 非回环绑定禁止 token=off）
cloudra scheduler                           # 前台跑调度守护（单实例 flock；CLOUDRA_SCHEDULER=off 禁止自动拉起）
cloudra stats tokens|cache|agents|export <id> -o <path>   # LLM 遥测（只读 runtime-v2.db）
cloudra stop                                # 显式全停（不 kill 计算进程）
npm --prefix cloudra/runtime_v2/js_host test   # JS 宿主测试；先 npm ci --ignore-scripts --no-audit --no-fund
```

入口：`cloudra` CLI（`cloudra/cli.py`；执行面已收敛到 runtime_v2，CLI 不直接跑任务）。Python >= 3.11，POSIX-only。**Windows 政策（2026-09-20 定）**：master 是纯 POSIX 目标，不接收 Windows 兼容补丁；Windows 兼容层归 `windows` 分支独有（见该分支 `docs/WINDOWS_PORT.md`），Windows 相关 PR 一律以 `windows` 为 base。`infra/platform_utils.py` 是 POSIX bash 发现逻辑，不是平台兼容层。

**停止语义边界**：取消单个 agent（`POST /api/v2/agents/{id}/cancel`）级联取消其存活后代，**永不触碰 scheduler/guard/QM 计算**；计算作业一键取消是 `POST /api/v2/compute/cancel-all`（账本级取消，Slurm/SSH 远端置 `cancel_requested` 由 poll 循环收尾，本地不杀进程）；全停只能 `cloudra stop`；只终止有明确归属的进程，禁止按进程名宽匹配杀，子进程必须 wait/reap；已发给 provider 的请求远端不可撤销。

**v1 已删除**：旧 `services/api*.py`、旧 `runtime/` 执行核心、`core/react.py`、Flet `ui/`、legacy 会话表等均已移除，无兼容回退，别再引用这些名字。

## 模块地图（cloudra/ 包）

- `core/` — **已清空执行栈**：身份/权限/上下文的唯一事实源分别是 `runtime_v2/roles.py` 的 `RoleProfile`、`runtime_v2/tool_catalog.py` 的线缆投影、`runtime_v2/persistence.py` 的会话投影；工具侧身份走 `base/tool_actor.py` 的 `ToolActorContext`。
- `runtime/` — 执行面共享件：`prompt_assembler.py`（身份=静态前缀，AGENTS.md 仅注入 Coordinator；动态观察快照跨轮只追加、绝不重写旧前缀）、`monitor.py`（guard 进程：持 flock 拉起 calculator、解析日志写终态；**终态按引擎文本终止标记判定，cclib 只取数据不定成败**，未知引擎不标成功；**先 CAS 再写 `state_*.json`/入 compute review**）、`compute_executor.py`（`run_compute`，认领方只有 scheduler 与 benchmark）、`remote_compute.py`（SSH 远端作业看守 poller 唯一实现：rsync stage → 远端 sbatch/nohup → 轮询 → 拉回产物 → 本地文本闸门复核）、`compute_notify.py`。
- `scheduler/` — `cloudra scheduler` 守护（与 API 分家，状态只走中央 `compute.db`）：**按节点分池的容量感知认领**（作业只在自己节点的额度内放行，归属节点不在注册表则跳过，**绝不改投别的机器**）；**生效容量 = 注册声明总额度，剩余额度 = 总额度 − 账本在用量**（视图唯一实现 `services/node_capacity.py`；`services/host_capacity.py` 的 OS 余量仅供本机 local 节点观测，不改调度上限、不重复扣账、不参与存活/终态判定）；对账器与孤儿 reap 一律 flock 探测存活（持锁作业不标 failed）；单实例 flock。完成通知 `ComputeNotifyBroker` 纯 DB 轮询投递，宕机窗口不丢。
- `services/` — `api_v2/`（HTTP 控制面唯一实现；薄路由，写操作一律走 CommandBus——例外仅 `POST /api/v2/compute/cancel-all`、`GET /api/v2/compute/nodes`、`routers/hub.py` 论坛面、`DELETE /api/v2/projects/{id}?hard=true`）；**访问控制只验 token**：`api_token.py` 是唯一解析点（`CLOUDRA_API_TOKEN` 或 `data_dir/.api_token`；`=off` 显式关认证仅限测试/CI，**非回环绑定拒绝 off**，off 时只放行回环 client + Host 白名单）；`daemon_supervisor.py`（守护拉起判定链唯一事实源；崩溃循环指数退避）；`shutdown.py`（`cloudra stop`：优雅关停优先，滞留升级 SIGTERM→SIGKILL；`api_stopped` 要求进程真的死，绝不按端口不答谎报）；`session_store.py`/`compute_store.py`（SQL 入口）；`nodes.py`（多节点注册表：`connection` 块声明传输方式，ssh+slurm / ssh+local 正交组合）；`telemetry.py`（LLM 遥测唯一实现：runtime-v2.db 只读聚合 + context 导出，`cli stats` 与 `routers/telemetry.py` 都只是薄壳）。
- `persistence/` — `database.py`（`ConversationDB` 会话级 + `ComputeDB` 中央计算库 `data_dir/compute.db`；补列走幂等 `ALTER`，旧库升级不重建表）、`artifacts.py`、`memory.py`、`paths.py`（**data_dir 下所有路径唯一事实来源**）、`fs_utils.py`（原子写）、`workspace.py`（`resolve_tool_path`/`resolve_existing_tool_path` 路径收口原语，吃外部输入路径的工具一律走它）。
- `knowledge/` — chem-kb 存储与检索：`store.py`（**读路径只读、缺库返回空绝不建库**）、`plugin.py`（语义+图谱+模糊三通道混合）、`health.py`、`installer.py`。
- `base/` — skill/tools 加载器与基类；审批/提问钩子（`use_approval_handler`/`use_input_handler` ContextVar，未设置直接抛错）；`role_identity.py` 是 **v2 role_id ↔ 历史 a-N 词表唯一映射**（别处不得再抄第二张表，`tests/test_role_identity.py` 常驻守卫）。
- `infra/` — `config.py`（**磁盘 YAML 唯一事实源**，唯一写入口 `mutate_config(fn)`；`flower`/`email.enabled`/`compute.allow_local_calculator` 各开关语义见代码）；`llm_client.py`（取消走 `abort_event` + socket RST；**禁止高层 `resp.close()` 跨线程**）；`flocks.py`（**执行面唯一进程存活/互斥判定手段**）；`compute_utils.py`（guard 命令构建、`resolve_log_path`）、`slurm.py`（`COMPLETED` 后复用 monitor 文本闸门复核）、`ssh_transport.py`（SSH 远端传输唯一原语：纯 argv ssh/rsync，同步阻塞，协程一律 `asyncio.to_thread`）、`operations.py` 等。
- `benchmark/` — 基准评测（独立于会话运行时）。`schema.py`：`TaskSpec` 唯一 schema——交付边逐条声明 `barrier_kcal_mol`（ΔE‡ 口径）、hard 竞争通道边加 `channel`/`favored`、性质交付物挂节点 `properties`（键带单位）；算不了的元素在交付图标 `accessible=false`（**没有拒答路线**）；`GoldMechanismGraph` 校验端点引用完整性（悬空即不可解析）；**有效可达性** `edge_effectively_accessible` = 边自身 AND 经由 TS 节点的 accessible，图分/自洽/accuracy 三处同口径。`gen_*_tasks.py`：四档确定性生成器（**改题源必须重跑**，`test_*_tasks_regenerate_identically` 守卫同步；方法白名单内容源是全局 config `method_policy.allowed_methods[_impossible]`，改 config 后必须重跑）。评分三层取证，**只读交付物**（图 JSON + 日志），绝不读散文：
  - `graph_similarity.py` — 子图覆盖唯一模式（gold 嵌入即满分，多出不罚）；**图分 = 证据加权覆盖**：`accessible` 标志不一致代价 1.0（双向都罚），节点有效代价 = 1−(1−替换代价)·绑定质量（未绑定等同缺失）。
  - `integrity.py` — 纯绑定报告（无 passed 判定）：`smiles:` 注释绑定、质子化变体 partial credit、accessible=false 节点不绑。
  - `selfconsistency.py` — 逐图元素覆盖判定（任一合格证据即覆盖，试错残留不参与）：物种=零虚频验证极小值；TS 边=一阶鞍点 + IRC 方向区间证明（与 `ts_guess verify strict` 同口径：唯一谓词 `tools/core/irc_path.py`，材料组装 `tools/core/irc_evidence.py`；不要求收敛，双侧端点几何须位于 TS 与端点极小值之间；原子序无关）；`accessible=false`/有效不可达豁免。
  - `barrier_evidence.py`/`accuracy.py` — 从绑定日志推逐步能垒（只认 ORCA/Gaussian 日志）；gold 边与交付步**按端点物种对应匹配**（gold 边 id 不参与匹配）；**逐边评全部 gold 边**：带参考能垒的走声明↔日志双来源核对 + 高斯容差（σ 小能垒放宽、`max_penalty_fraction` 只封顶这部分罚分、定义差异固定 0.9），无参考但有效可达记 1.0、有效不可达记 0.0；声明无据/不一致 **fail-loud 短路 → final 只留 0.1×图分**；性质锚点逐键比对（σ 查 `_PROPERTY_SIGMAS` 显式表，表外 fail-loud）；hard 选择性题定性分占 accuracy 槽位（恰好一条 `favored:true` 且 channel 命中 → 1.0）。
  - `runner.py` — **composite = 0.1·graph + 0.3·selfconsistency + 0.6·accuracy**（2026-09-25 用户裁决：机理不对时 accuracy 层也会惩罚，图份额不该高；自洽层保持全有或全无布尔）；**自洽回捞**：gold 边被交付步覆盖但该交付步自洽不合格 → 该 gold 边赢下的图分覆盖贡献倒扣（runner 层剔边重算 GED，用 accuracy 端点物种匹配口径；不在 gold 子图里的额外边只落自洽零分不倒扣图分）；图不可解析或没有任何 accessible 物种节点绑到证据 → 倒扣 `-no_evidence_penalty`（纯不可达交付合法不倒扣）；impossible 档走同一 composite（I 题正确交付 = 图照交 + 标 `accessible=false`，满分 0.4；wrongly-solve 由标志闸门与 accuracy 0.0 双杀；2026-09-26 起只生成 I 题，不生成 S 对照题）；持久化 **append-only**（runs 只增不删、批次带溯源快照、沙箱按 `<task_id>/<batch_id>/` 分目录；runs 表迁移只增不删列，删列走整表重建丢旧列）。
  - `watch.py`（**SUCCEEDED ≠ 题目完成**）、`batch.py`（Web 批次跑在 live RuntimeCore 上；题集 = 内置档位 `ideapool/tasks/<tier>` 与 `--tasks-dir` 并存；stop 只取消题目 agent，不碰计算）。
- `runtime_v2/` — 事件驱动内核（推理循环唯一实现）。骨架：`schemas.py`/`roles.py`/`events.py`/`core.py`（`session_contexts` 会话级 LLM 上下文投影，唯一写口 `ContextBroker`，一律 persist-then-apply）/`apply.py`（**`apply_event` 唯一状态应用器**）/`effects.py`/`commands.py`（CommandBus 四拍：纯 decider → persist-then-apply → effect）。`agent_runner.py`（每 Agent 一个 async task；后台任务一律 `track_background` 登记；统一完成门禁 `_evaluate_completion_gate`，同缺口指纹无进展耗尽落 failed；LLM 上下文跨 run/重启连续，显式 restart 才重置）。`child_settings.py`（子 Agent 设置继承唯一解析点；秘密永不继承）、`child_manifest.py`（子 Agent 完成回报结构化 manifest 唯一来源）、`supervision.py`（督导运行时；待办唯一事实源是 DAG store；failed/cancelled 不自动复活）、`dispatcher.py`（**Agent 间消息唯一入口**：`commit_and_deliver` 固定四拍，wake 策略四值 park_terminal/park_waiting/idle_only/never）。JS 协议默认：`tool_catalog.py`（**线缆投影唯一来源**）、`js_runtime.py`（QuickJS-WASM 沙箱；JS 堆不跨重启恢复；取消只 SIGTERM/SIGKILL JS host，绝不碰 scheduler/guard/QM）。`policies/` 八个 PolicyStage（新 harness 能力只加 stage）；**通道纪律**：操作级修正进工具结果、行为级引导进 pin 通知（guidance stage，幂等去重、永不阻拦；TS/PES 准备与明确的 Gaussian/ORCA 提交注入 physical-thinking 提醒：先核对条件与模型差距，再审机理假设与坐标耦合，鼓励允许且可用的半经验探索，不自动改模型；`ts_guess` 的无内部峰、路径精修耗尽、验证失败按结构化结果追加反思提示，按材料来源去重，参数/基础设施故障与材料不足不触发）。`compaction.py`（统一全轮次压缩：全量折叠，唯一不压缩的是 harness 前缀；token 口径 `infra/token_estimator.py` 单一事实源；fail-loud 不降级解析）。`launch_groups.py`（swarm 组清单是事件投影；重启绝不重放 spawn）。`persistence.py`（恢复快照含 session_contexts；恢复时 running/waiting 落 failed；恢复路径绝不执行 executor/JS 进程/调度作业）。
- `tools/` — 按领域分组（Bash/Chem/Search/Write/Plan 等；DAG 面是 `dag_tools/`）。`registry.py` 注册，下游只经 `capabilities.py` 投影查询，**禁止在别处新建工具名集合**。角色门槛：registry 条目 `role_allowlist`（空=不限；wire 投影隐藏 + PermissionStage 硬拦两道防线；化学/QM 工具默认限 `_SCIENCE_ROLES`，benchmark 题面 agent 以 coordinator 运行故 coordinator 必须在列）。`tools/core/` 权限模型、审批流水线、各引擎 frames 解析（纯函数）。重点：`structure_builder.py`（分片建模唯一实现；「优化返回 0」不构成「几何可用」）、`complex_assembly.py`（力场必须 `ignoreInterfragInteractions=False`）、`crest_runner.py`（进程退出与科学成功分开表达，无正则，精确 token 比对）、`xtb_path_runner.py`（触顶报 `path_not_converged`，绝不默认成功）、`ts_process.py`（IRC 输入不硬编码统一步数；需逐任务控制原生参数时 agent 走 `qm_input_writer` 手动链，按证据与成本权衡长度；双侧真实外帧经无约束 Opt/Freq、身份匹配和方向区间证明可支持 `verified`，不要求 IRC 自身收敛）、`irc_path.py`（IRC 方向证明唯一谓词）、`irc_evidence.py`（日志 → IRC 端点/末帧几何/虚频数的材料组装唯一实现，benchmark 自洽性与 DAG `short_irc` 闸门共用）、`run_dirs.py`（运行目录编号/进程组终止/产物清点单源）、`preorganization.py`（成环 TS 初猜唯一引导实现）。`Chemtool/mechanism_predict.py`（FlowER ML 假设生成器：外部 conda env 子进程，**ML 预测不是计算证据**）。`Chemtool/ts_search_process.py` 的 `ts_prepare` 支持声明式 `scan={method,scans,freeze}`，`ts_resume` 正常续跑只需 `run_id`；扫描只产初猜，后续精修不继承冻结。引擎工具原子字段统一 Gaussian 1-based / ORCA 0-based，独立结构工具 1-based，流程内部 0-based（旧无版本流程记录不猜编号）。`ring_order` 与 `distance_filters` 独立或叠加引导生成并验收；六元环形状自动描述，不能代替科学证据；多组分 C1 用 1.7×vdW 接触图整体连通，碰撞下限不变。`Chemtool/ts_guess.py` 的 `scan_prepare` 必须显式传 `method`（含 `scan` 准备别名）；`scan_parse` 复用 `watch_pairs`/`distance_table` 报逐帧距离与启发式连接变化，缺帧不猜、不跨缺帧推断反应；`scan_has_internal_peak`/`verification_status`/`path_termination_reason` 提供机读结论，提示不得从 verdict 散文或局部终止标记反推。工具无持久状态；给模型的文本一律英文；超大结果（>30k 字符）落盘 `.cloudra/tool_output/`。
- `prompts/`、`skills/` — 角色 prompt（每个 `RoleProfile` 一份）与科研方法技能包；legacy 子 Agent 类栈已删除，身份唯一事实源是 `runtime_v2/roles.py`。
- `frontend/` — React SPA（唯一前端）；`npm run build` 通过才算可用；生产由 uvicorn 同端口托管 `dist/`。

## dag/ 子系统（DAG 引导编排）

按会话 opt-in：`orchestration_mode` ∈ `standard`（默认，不读不写图）/ `dag_record`（harness 自动接受草稿）/ `dag_guided`（Supervisor 异步复核显式送审的证据）。继承规则唯一解析点 `agent_host.resolve_orchestration_mode`；supervisor 角色默认钉 dag_guided。

- 骨架：`models.py`（共享类型）、`store.py`（delivery 图持久存储 + 草稿 + CallReview + 证据绑定）、`engine.py`（事务化变更引擎；`remove_edge`/`remove_node` 必须带 rationale，无隐式级联）、`evidence_ingest.py`（驻点校验**三态**：`verified=True` 才算有频率支撑的判定——「没做频率分析」绝不等于「已验证极小值」）、`completion.py`、`controller.py`（`DagController` 四 mixin 门面；CallReview 唯一来源是显式送审 `submit_evidence_for_review`，非 pending 不可再裁；`delivery_report`/`audit_stop` 每次现读 store 契约）。
- 关键不变量：图存储是权威（不在模型上下文里）；模型声明不能标记交付完成，证据等级由 harness 确定性派生；`rejected` 是仍欠的开放缺口（只能重绑或显式 skip/not_applicable-with-reason 关闭）；`submit_compute_job` 调用永远不是证据（只认完工作业的解析产物）；督导裁决通知唯一出口 `flush_review_notifications`（重投幂等）；工具不得写派生 `evidence_level`。阶段绑定走 `apply_stage_bind`/`bind_stage_attachments`（守卫读到的 revision 做 base，stale 重算）：geometry 要正常结束+0 虚频，`ts_opt` 要正常结束（带频率则须一阶鞍点），`short_irc` 要**几何方向区间证明**（与 `ts_guess strict`/benchmark 自洽性同口径，唯一组装实现 `tools/core/irc_evidence.py`，材料重解析自同边已绑证据的日志，缺材料 fail-loud 拒绑），`thermochemistry` 只认 `thermo_analysis` 的 `status=complete`。
- 逐文件审查：guided 草稿提交即落候选图（accept 只记录审查状态，不重放建图）；`dag_propose_mechanism.delivery_targets` 明示交付范围（省略=纯探索）；文件送审裁决落 `ReviewDecision`，不改机器 stage 状态；`dag_delivery_report` 与最终门禁共用 `DagController.delivery_report()`（`supervisor_supported` vs 纯确定性 `dag_verified`）；以上均不是科学真值，benchmark 独立计分。
- live complete 口径：带 stages 的元素以阶段契约为权威；默认机理草稿边 = advisory `ts_guess` + required `ts_opt`/`frequency`（`cdxml_to_graph` 同口径，不预置 IRC）；IRC/端点/方向**不是**结题必要条件，需要路径证明时才写进该步契约。

## 测试约定（tests/）

- 按文件名前缀分组：`test_dag_*`（DAG）、`test_runtime_v2_*`（新内核）、`test_compute`/`test_slurm`（计算执行）、化学工具各一、其余基础设施单测。
- `conftest.py` autouse 隔离 data_dir 到 tmp_path；不要在测试里写真实数据目录。
- 跳过一律按环境探测（缺 `crest`/`xtb` 二进制、无 RDKit/chem extra、无 node>=22 + js_host 依赖、非 POSIX）；无需要真实 LLM key 的测试；可选依赖先探测再 skip，不许硬断言；计算资源按本机容量申请（`max(1, min(2, os.cpu_count() or 1))`），别写死 `cpus=4`。
- **场景级回归**：`tests/agent_scenarios.py` 是场景 harness（`ScriptedProvider` 零 API key，按 role 分流；`ScenarioHarness` 装真实 core/runner/工具执行器与默认 8 个 PolicyStage）；断言只落在**事件序列/结构化字段/状态不变量**上，绝不断言模型措辞；新增「Agent 级故障」修复应补一个场景。
- 测试替身（fake/stub）签名对齐真实接口，建议带 `**_kwargs` 防接口加参后变红。
- issue #33 复现材料在 `tests/fixtures/chemtool_issue33/`；issue 里除实测值以外的数值一律标记为未复现，不得写进断言。

## 顶层散件

- `kg_data/`（知识图谱 CSV，`cloudra knowledge import` 的输入）、`ideapool/reaction_candidates/`（**存量** benchmark 四档题源 md；新候选见 `gold_compute/README.md`）、`vector_store/`（知识卡片 bge-m3 向量，微服务跑在外部 `.venv-trans`）、`deploy/`、`docs/`（治理规则见 `docs/README.md`：阶段性文档完成使命即归档）。
- `gold_compute/`（gold 战役权威说明在 `README.md`：主线是边选反应边填自算 gold，存量题不承诺全边 DFT 清零）、`archive/`（一次性实验/运行残留，gitignored；`archive/NA1_clean_env` 仍跟踪为例外）。
- `build/`、`.worktrees/`、`cloudra.egg-info/` 为构建副产物，勿手改；软著源程序清单由 `scripts/gen_copyright_source.py` 重建（改代码后重跑）。

## 工作约定

- **禁止过度工程**：只做被明确要求的事，不预设「将来可能用到」的抽象、配置项、插件点或兜底分支；每新增一个公开接口、配置键或概念，先回答：现在谁在用？答不上来就别加。
- **测试聚焦改动面，别随手跑全套**：流程是 `compileall` → `ruff` → 相关测试（按前缀挑选）。**全套 `uv run pytest -q tests/` 是 CI 的事，本地不跑**（除非用户明确要求）。
- **禁止补丁式修复**：项目 beta 未上线，**不考虑向后兼容**。发现问题在架构级根治——不留 legacy 回退分支、不加兼容 shim、不保留死代码。修复应配能覆盖该问题的测试。
- 最小改动：修 bug 不顺手重构；新代码跟随所在文件的既有风格与注释密度。
- **化学/科学设计决策必须问用户**：评分阈值、方法学验收红线、力场/泛函/基组选择、能垒基准定义、评分权重、accessible 豁免口径等——必须先向用户确认，**不允许 agent 自作主张拍板**。
- **事件循环线程禁止同步阻塞调用**：`async` 函数体内不得直接调用同步 SQLite、`time.sleep`、`subprocess.run`、同步网络库——一律 `asyncio.to_thread` 或异步变体。护栏 `tests/test_no_sync_on_loop.py` 常驻。
- **执行面可靠性铁律**：调度器/guard 任何路径不得 kill 计算进程（取消只走显式 `cancel_requested` 路径）；进程存活判定一律 `infra/flocks.py` 的 flock 探测；核心链路禁止解析计算输入文件。子进程归属链：API/CLI →（detach）scheduler/kg_vec 守护 → guard → calculator.sh → 引擎 → 引擎的 external 子进程（如 MACE 由 ORCA 启动，**Cloudra 从不直接 spawn MACE**）。
- **禁止引入正则**：`re` 唯一允许的场合是**解析计算引擎输出文件**。**校验路径一律不准有正则**——尤其是对 agent/LLM 输出：走结构化路径（pydantic、`json.loads`、显式 token 扫描、枚举精确比对）或对物理量做确定性比对，一律 fail-loud。常驻护栏 `tests/test_benchmark.py::test_scoring_modules_do_not_import_regex`。
- 不引入项目未依赖的库；可选能力走 `pyproject.toml` 的 extras（chem/browser/pdf/visual/dev）。
- 改了结构、命令或约定时同步更新本文件。
- 未经明确要求不做 git 提交/推送等变更操作。
