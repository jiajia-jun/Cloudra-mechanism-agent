# AGENTS.md — Cloudra 项目指南

给 AI 助手与新贡献者的仓库导航。项目定位与三层架构见 `README.md`。本文件是**地图不是手册**：每个模块只记职责与坑点，细节读代码。

## 命令

```bash
uv run pytest -q tests/test_dag_engine.py   # 按文件名前缀聚焦改动子系统（默认只跑这个粒度）
uv run pytest -q tests/                     # 全套测试——只在收尾交付验证时跑，见"工作约定"
uv run ruff check cloudra tests             # lint（select E/F/W/I，E501 不强制）
uv run python -m compileall -q <改动文件>   # 改完先做语法检查
cloudra                                     # 构建并启动 Web 前端（顺带 detach 拉起 scheduler/kg_vec 守护）
cloudra scheduler                           # 前台跑调度守护（单实例 flock；CLOUDRA_SCHEDULER=off 禁止自动拉起）
cloudra stop                                # 显式全停（不 kill 计算进程）
npm --prefix cloudra/runtime_v2/js_host test   # JS 宿主测试；先 npm ci --ignore-scripts --no-audit --no-fund
```

入口：`cloudra` CLI（`cloudra/cli.py`；执行面已收敛到 runtime_v2，CLI 不直接跑任务）。Python >= 3.11，POSIX-only。

**停止语义边界**：取消单个 agent（`POST /api/v2/agents/{id}/cancel`）级联取消其存活后代，**永不触碰 scheduler/guard/QM 计算**；没有项目级一键取消，全停只能 `cloudra stop`；只终止有明确归属的任务/进程，禁止按进程名宽匹配杀进程，子进程必须 wait/reap；已发给 provider 的请求远端不可撤销。

**v1 已删除**：旧 `services/api*.py`、旧 `runtime/` 执行核心、`core/react.py`、Flet `ui/`、legacy 会话表等均已移除，无兼容回退，别再引用这些名字。

## 模块地图（cloudra/ 包）

- `core/` — `Agent`/`Coordinator`/`Follower` 基类与权限模型宿主；`message_history.py` JSONL 消息历史。
- `runtime/` — 执行面共享件：`prompt_assembler.py`（AGENTS.md 仅注入 Coordinator）、`monitor.py`（guard 进程：持 flock 拉起 calculator、解析日志写终态；**终态按引擎文本终止标记判定，cclib 只取数据不定成败**）、`compute_executor.py`（`run_compute`，认领方只有 scheduler 与 benchmark）、`compute_notify.py`。
- `scheduler/` — `cloudra scheduler` 守护（与 API 分家，状态只走中央 `compute.db`）：容量感知认领、对账器（探 guard 锁）、孤儿 reap；单实例 flock。资源由 agent 提交时显式申请（`cpus`/`memory_mb`），超容拒收，**核心链路零输入文件解析**。完成通知 `ComputeNotifyBroker`（`runtime_v2/compute_notify.py`）纯 DB 轮询投递，宕机窗口不丢。
- `services/` — `api_v2/`（HTTP 控制面唯一实现；薄路由，写操作一律走 CommandBus）、`daemon_supervisor.py`（守护拉起判定链唯一事实源；崩溃循环节流 <60s 跳过）、`shutdown.py`（`cloudra stop`）、`session_store.py`/`compute_store.py`（SQL 入口）、`nodes.py`（多节点/Slurm 注册表）。
- `persistence/` — `database.py`（`ConversationDB` 会话级 + `ComputeDB` 中央计算库 `data_dir/compute.db`）、`artifacts.py`、`memory.py`、`paths.py`（**data_dir 下所有路径唯一事实来源**）、`fs_utils.py`（原子写）、`workspace.py`。
- `knowledge/` — chem-kb 存储与检索：`store.py`（**读路径只读、缺库返回空绝不建库**；实体 props 挂 `label_en`，英文查询自动可搜图谱）、`plugin.py`（语义+图谱+模糊三通道混合 provider）、`health.py`、`installer.py`。
- `base/` — skill/tools 加载器与基类；审批钩子 `use_approval_handler`（ContextVar），未设置时 `request_approval` 直接抛错（ask_user 同理走 `use_input_handler`）。
- `infra/` — `config.py`（**磁盘 YAML 唯一事实源**，唯一写入口 `mutate_config(fn)`；测试重建单例用 `_reset_for_tests()`；`flower` section 是 FlowER 外部环境的路径与总开关）、`llm_client.py`（取消走 `abort_event` + socket 层 RST；**禁止高层 `resp.close()` 跨线程**，会卡锁）、`flocks.py`（**执行面唯一进程存活/互斥判定手段**）、`compute_utils.py`（guard 命令构建、`resolve_log_path`）、`slurm.py`、`operations.py` 等。
- `benchmark/` — 基准评测（独立于会话运行时）：`schema.py`（`TaskSpec` 唯一 schema；交付边逐条声明 `barrier_kcal_mol`，可选 `refusal` 结构化拒答）、`gen_*_tasks.py`（四档确定性生成器；**改题源必须重跑生成器**，`test_*_tasks_regenerate_identically` 守卫同步；白名单 easy/normal/hard 一律 `["xtb","b3lyp/def2svp"]`（组合条目把基组钉进许可）、impossible 保持 `["xtb"]`）、`graph_similarity.py`（子图覆盖打分，多出不罚）、`integrity`/`selfconsistency`/`barrier_evidence`/`accuracy`（三层取证评分；**能垒评分只读交付物**，绝不用最终消息散文兜底）、`refusal.py`（纯结构化拒答分类）、`runner.py`（composite = (0.5·graph + 0.2·selfconsistency + 0.3·accuracy) × binding_quality）、`watch.py`（**SUCCEEDED ≠ 题目完成**）、`batch.py`（Web 批次跑在 live RuntimeCore 上；stop 只取消题目 agent，不碰计算）。
- `runtime_v2/` — 事件驱动内核（推理循环唯一实现）。骨架：`schemas.py`/`roles.py`/`events.py`/`core.py`/`apply.py`（**`apply_event` 唯一状态应用器，禁止在别处写状态**）/`effects.py`/`commands.py`（CommandBus 四拍：纯 decider → append+publish+persist → apply_event → effect）。`agent_host.py`（AgentSession 状态机）、`agent_runner.py`（每 Agent 一个 async task；后台任务一律经 `track_background` 登记，裸 create_task 取消/shutdown 碰不到；**统一运行结束门禁 `_evaluate_completion_gate`**，同缺口指纹无进展退出有界计数，耗尽落 failed 不伪报完成）、`supervision.py`（督导运行时；**待办唯一事实来源是 DAG store**；failed/cancelled 不自动复活）、`turn_pipeline.py`、调用生命周期（`event_writer.py` 有序持久化唯一写口；invocation 五态、executor 恰一次；**持久化失败抛 EventPersistenceError 不伪造终态**）。JS 协议默认：`tool_catalog.py`（**线缆投影唯一来源，禁止在别处新建工具名集合**）、`js_runtime.py`（QuickJS-WASM 沙箱；**JS 堆不跨重启恢复、失败程序不自动重跑**；取消只 SIGTERM/SIGKILL JS host，绝不碰 scheduler/guard/QM）。`policies/` 七个 PolicyStage（permission/unattended/method_policy/dag/goal/schedule/knowledge；新 harness 能力只加 stage）。其余：`mailbox.py`、`pending.py`（重启恢复时孤儿审批/提问落 expired）、`reminders.py`、`compaction.py`、`launch_groups.py`（swarm 并发组，父取消级联）、`persistence.py`（**恢复时 running/waiting agent 落 failed**；恢复路径绝不执行 executor/JS 进程/调度作业）。
- `tools/` — 按领域分组（Bash/Chem/Search/Write/Plan 等；QM 双引擎 + xtb + MLIP 路由；DAG 面是 `dag_tools/`）。`registry.py` 注册，下游只经 `capabilities.py` 投影查询，**禁止在别处新建工具名集合**。`tools/core/` 权限模型、审批流水线、各引擎 frames 解析（纯函数）。重点：`structure_builder.py`（**分片建模唯一实现**；`BuildStatus` 枚举表达状态；「坐标已生成」或「优化返回 0」都不构成「几何可用」）、`complex_assembly.py`（**参数已由用户批准**，见 docstring；力场必须 `ignoreInterfragInteractions=False`）、`structure_artifacts.py`（轨迹流式落盘；失败与不收敛轨迹同样保留）、`crest_runner.py`（**进程退出与科学成功分开表达**；分类用精确整行/token 比对，无正则）、`xtb_path_runner.py`（路径精修必须跑到引擎自判收敛；触顶报 `path_not_converged` 且 `usable_as_guess=False`，绝不默认成功）、`topology_change.py`（拓扑变更**只记录不判定**）。`Chemtool/mechanism_predict.py`（FlowER ML 机理假设生成器：**外部 conda env `flower` 子进程**，主进程永不 import torch，只消费 driver 产出的 network.json；**ML 预测不是计算证据**，不走 dag_evidence_producer；config 开关 `flower.enabled` 默认关，registry 的 `config_gate` 字段控制 wire 投影隐藏 + 执行层硬失败；安装走 `scripts/setup_flower.sh`）。工具无持久状态；给模型的文本一律英文；超大结果（>30k 字符）落盘 `.cloudra/tool_output/`。
- `subagents/`、`prompts/`、`skills/` — 8 个领域子 Agent（`registry.py` 显式清单 a-1..a-8）；`prompts/*.md` 角色 prompt；`skills/` 科研方法技能包。
- `frontend/` — React SPA（唯一前端）；`npm run build` 通过才算可用；生产由 uvicorn 同端口托管 `dist/`。

## dag/ 子系统（DAG 引导编排）

按会话 opt-in：`orchestration_mode` ∈ `standard`（默认，不读不写图）/ `dag_record`（harness 自动接受草稿，Supervisor 不运行）/ `dag_guided`（Supervisor 逐调用复核）。继承规则唯一解析点 `agent_host.resolve_orchestration_mode`；supervisor 角色默认钉 dag_guided。

- `models.py`（共享类型）、`store.py`（delivery 图持久存储 + 草稿 + CallReview + `dag_evidence_bindings`）、`engine.py`（事务化变更引擎；`remove_edge`/`remove_node` 必须带 rationale，无隐式级联）、`evidence_ingest.py`（驻点校验**三态**：`verified=True` 才算有频率支撑的判定；没频率数据时 `verified=False` 且 `is_valid=False`——「没做频率分析」绝不等于「已验证极小值」）、`completion.py`（`evaluate_delivery()`）、`controller.py`（`DagController` 四 mixin 门面；**CallReview 唯一来源是显式送审 `submit_evidence_for_review`**）、`requirements.py`/`review_requests.py` 等支撑件。
- 关键不变量：图存储是权威（不在模型上下文里）；模型声明不能标记交付完成，证据等级由 harness 确定性派生；`rejected` 不是处置——是仍欠的开放缺口，只能重绑或显式 skip/not_applicable-with-reason 关闭；`submit_compute_job` 调用永远不是证据（只认完工作业的解析产物）；每条督导裁决恰好写一条 durable 通知，投递唯一出口 `flush_review_notifications`（重投幂等、终态收件人 park-don't-wake）。

## 测试约定（tests/）

- 按文件名前缀分组：`test_dag_*`（DAG）、`test_runtime_v2_*`（新内核）、`test_compute`/`test_slurm`（计算执行）、化学工具各一、其余基础设施单测。
- `conftest.py` autouse 隔离 data_dir 到 tmp_path；不要在测试里写真实数据目录。
- 跳过一律按环境探测（缺 `crest`/`xtb` 二进制、无 RDKit/chem extra、无 node>=22 + js_host 依赖、非 POSIX）；无需要真实 LLM key 的测试；可选依赖先探测再 skip，不许硬断言（先例：`tests/test_benchmark_sandbox_fp.py` 的 `_REQUIRES_*`）；计算资源按本机容量申请（`max(1, min(2, os.cpu_count() or 1))`），别写死 `cpus=4`。
- 测试替身（fake/stub）签名对齐真实接口，建议带 `**_kwargs` 防接口加参后变红。
- issue #33 复现材料在 `tests/fixtures/chemtool_issue33/`；issue 里除实测值以外的数值一律标记为未复现，不得写进断言。

## 顶层散件

- `kg_data/`（知识图谱 CSV，`cloudra knowledge import` 的输入）、`ideapool/reaction_candidates/`（benchmark 四档题源 md）、`vector_store/`（知识卡片 bge-m3 向量；`scripts/kg_vec_service.py` 微服务跑在外部 `.venv-trans`）、`deploy/`、`docs/`（`docs/superpowers/plans/` 存设计计划）。
- `build/`、`.worktrees/`、`cloudra.egg-info/` 为构建副产物，勿手改；软著源程序清单由 `scripts/gen_copyright_source.py` 重建（改代码后重跑）。

## 工作约定

- **禁止过度工程**：只做被明确要求的事，不预设「将来可能用到」的抽象、配置项、插件点或兜底分支；不加没人调用的参数；不顺手「改进」无关代码；需求三行能写完就不拆模块。每新增一个公开接口、配置键或概念，先回答：现在谁在用？答不上来就别加。
- **测试聚焦改动面，别随手跑全套**：`tests/` 全量大而慢。默认只跑与改动直接相关的测试文件（按前缀挑选）；流程是 `compileall` → `ruff` → 相关测试。全套 `uv run pytest -q tests/` 只在收尾交付验证、改动横跨多个子系统、或用户明确要求时跑。
- **禁止补丁式修复**：项目 beta 未上线，**不考虑向后兼容**。发现问题在架构级根治——不留 legacy 回退分支、不加兼容 shim、不保留死代码、不用「文档注明」替代修复。任何修复必须配能直接把问题测红的测试，先红后绿。
- 最小改动：修 bug 不顺手重构；新代码跟随所在文件的既有风格与注释密度。
- **化学/科学设计决策必须问用户**：评分阈值、方法学验收红线、力场/泛函/基组选择、能垒基准定义、评分权重、拒答规则等——必须先向用户确认，**不允许 agent 自作主张拍板**。
- **事件循环线程禁止同步阻塞调用**：`async` 函数体内不得直接调用同步 SQLite、`time.sleep`、`subprocess.run`、同步网络库——一律 `asyncio.to_thread` 或 `a` 前缀异步变体。护栏 `tests/test_no_sync_on_loop.py` 常驻。
- **执行面可靠性铁律**：调度器/guard 任何路径不得 kill 计算进程（取消只走显式 `cancel_requested` → Slurm scancel 路径）；进程存活判定一律 `infra/flocks.py` 的 flock 探测，禁止 PID/`ps`//proc 文本判定；核心链路禁止解析计算输入文件。子进程归属链：API/CLI →（detach）scheduler/kg_vec 守护 → guard → calculator.sh → 引擎 → 引擎的 external 子进程（如 MACE 由 ORCA 启动，**Cloudra 从不直接 spawn MACE**）。
- **禁止引入正则**：`re` 唯一允许的场合是**解析计算引擎输出文件**（`tools/core/*_frames.py`、`log_parser.py`、`ts_guess.py` 等纯解析）。**校验路径一律不准有正则**——尤其是对 agent/LLM 输出：取值与判定走结构化路径（pydantic 校验、`json.loads`、显式 token 扫描、枚举精确比对）或对物理量做确定性比对，一律 fail-loud。常驻护栏 `tests/test_benchmark.py::test_scoring_modules_do_not_import_regex`。
- 不引入项目未依赖的库；可选能力走 `pyproject.toml` 的 extras（chem/browser/pdf/visual/dev）。
- 改了结构、命令或约定时同步更新本文件。
- 未经明确要求不做 git 提交/推送等变更操作。
